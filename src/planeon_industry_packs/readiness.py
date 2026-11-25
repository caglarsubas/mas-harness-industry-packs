"""Tenant data-readiness evaluator: `harness-pack readiness-evaluate <pack_root> --input <dir>`.

The evaluator reads a tenant input directory that holds a v1alpha1 SourceInventory (`source-inventory.json`) and the
data members it names, measures each source, and judges the measurements against the DataReadinessPolicy of the pack.
It fails closed on a symbolic link, a non-regular file or a path that escapes the input directory. It runs no network
call, subprocess or connector, and it never imports the repository's `ci/` handlers.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import stat
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path, PurePosixPath
from typing import Any

from .canonical import canonical_json_bytes
from .loader import load_pack

INVENTORY_NAME = "source-inventory.json"
INVENTORY_IDENTITY = ("harness.planeon.ai/source-inventory/v1alpha1", "SourceInventory")
INVENTORY_FIELDS = {"apiVersion", "kind", "id", "stage", "synthetic", "sources"}
SOURCE_FIELDS = {"id", "sourceClass", "ownerRole", "custodianRole", "classification", "dataPaths", "evidenceIds", "description"}
POLICY_KIND = "DataReadinessPolicy"
MINIMUM_METRICS = ("completeness", "classificationCoverage", "provenanceCoverage")
MAXIMUM_METRICS = ("freshnessMinutes", "duplicateRate")
METRIC_CODES = {
    "completeness": ("COMPLETENESS_NEEDS_INPUT", "INCOMPLETE_DATA"),
    "freshnessMinutes": ("FRESHNESS_NEEDS_INPUT", "STALE_DATA"),
    "duplicateRate": ("DUPLICATE_RATE_NEEDS_INPUT", "DUPLICATE_DATA"),
    "classificationCoverage": ("CLASSIFICATION_NEEDS_INPUT", "UNCLASSIFIED_DATA"),
    "provenanceCoverage": ("PROVENANCE_NEEDS_INPUT", "UNPROVENANCED_DATA"),
}
MISSING_CODE = "MISSING_DATA"
RECONCILIATION_CODE = "DATA_RECONCILIATION_MISMATCH"
PERSONAL_DATA_CODE = "PERSONAL_DATA_FORBIDDEN"
MUTATION_BUILDER = "luhn-valid-16-digit-run"
EVIDENCE = {"published": False, "runtimeEvidence": False, "assuranceEvidence": False, "tenantAcceptance": False}
TIME_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
IBAN_CANDIDATE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}[0-9]{2}(?:[A-Z0-9]{11,30}|(?: [A-Z0-9]{4}){2,7}(?: [A-Z0-9]{1,3})?)(?![A-Za-z0-9])")
DIGIT_RUN = re.compile(r"(?<![0-9])[0-9](?:[ -]?[0-9]){12,18}(?![0-9])")
QUANTUM = Decimal("0.0001")


class ReadinessInputError(ValueError):
    """The input directory is refused; the evaluator fails closed and produces no verdict."""


# --- input reading (fail closed) -------------------------------------------------------------------------------------


def _checked_directory(path: Path) -> Path:
    try:
        mode = os.lstat(path).st_mode
    except OSError as exc:
        raise ReadinessInputError("input directory is absent") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise ReadinessInputError("input directory is not a plain directory")
    return path.resolve(strict=True)


def _safe_member(base: Path, relative: Any) -> Path | None:
    """Return the regular file at `relative` under `base`, None when it is absent; refuse links and escapes."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ReadinessInputError("input path is not a relative POSIX path")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in relative.split("/")):
        raise ReadinessInputError("input path escapes the input directory")
    current = base
    for index, part in enumerate(pure.parts):
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(mode):
            raise ReadinessInputError("input path is a symbolic link")
        last = index == len(pure.parts) - 1
        if last and not stat.S_ISREG(mode):
            raise ReadinessInputError("input path is not a regular file")
        if not last and not stat.S_ISDIR(mode):
            raise ReadinessInputError("input path parent is not a directory")
    resolved = current.resolve(strict=True)
    if resolved != base and base not in resolved.parents:
        raise ReadinessInputError("input path escapes the input directory")
    return current


def _read_regular(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ReadinessInputError("input path is not a regular file")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


# --- structural personal-data scan (own implementation; the ci/ scanner is never imported) -------------------------


def _luhn_valid(digits: str) -> bool:
    total = 0
    for position, character in enumerate(reversed(digits)):
        value = int(character)
        if position % 2:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def _iban_valid(candidate: str) -> bool:
    compact = candidate.replace(" ", "")
    if not 15 <= len(compact) <= 34:
        return False
    rearranged = compact[4:] + compact[:4]
    return int("".join(str(int(character, 36)) for character in rearranged)) % 97 == 1


def personal_data_hits(text: str) -> list[str]:
    """Mod-97-valid IBAN shapes and Luhn-valid 13-19 digit runs (single spaces or hyphens allowed between digits)."""
    found = {match.group(0) for match in IBAN_CANDIDATE.finditer(text) if _iban_valid(match.group(0))}
    for match in DIGIT_RUN.finditer(text):
        digits = re.sub(r"[ -]", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            found.add(match.group(0))
    return sorted(found)


def luhn_run(length: int = 16) -> str:
    """A Luhn-valid decimal run computed at run time (never a committed literal), for the disallowed-data mutation."""
    body = [(3 * index + 7) % 10 for index in range(length - 1)]
    for check in range(10):
        candidate = "".join(str(item) for item in body) + str(check)
        if _luhn_valid(candidate):
            return candidate
    raise AssertionError("no Luhn check digit")


# --- members and measurements ---------------------------------------------------------------------------------------


def _time(value: Any) -> datetime:
    if not isinstance(value, str) or not TIME_PATTERN.match(value):
        raise ReadinessInputError("time is not ISO 8601 UTC")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def _member_records(path: str, data: bytes) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReadinessInputError("data member is not UTF-8") from exc
    try:
        suffix = PurePosixPath(path).suffix.casefold()
        if suffix == ".json":
            value = json.loads(text)
            records = value.get("records") if isinstance(value, dict) else None
        elif suffix == ".jsonl":
            records = [json.loads(line) for line in text.splitlines() if line.strip()]
        elif suffix == ".csv":
            records = [dict(row) for row in csv.DictReader(io.StringIO(text))]
        elif suffix in {".md", ".txt"}:
            records = [{"document": path, "text": text}] if text.strip() else []
        else:
            raise ReadinessInputError("data member type is not supported")
    except (json.JSONDecodeError, csv.Error) as exc:
        raise ReadinessInputError("data member does not parse") from exc
    if not isinstance(records, list) or not all(isinstance(item, dict) and item for item in records):
        raise ReadinessInputError("data member records are not objects")
    return records


def _record_times(record: dict[str, Any]) -> list[datetime]:
    return [_time(value) for value in record.values() if isinstance(value, str) and TIME_PATTERN.match(value)]


def _measure(source: dict[str, Any], members: dict[str, list[dict[str, Any]] | None]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    duplicates = 0
    present = False
    for path in source["dataPaths"]:
        rows = members[path]
        if rows is None:
            continue
        present = True
        key = next(iter(rows[0])) if rows else None
        identifiers = [row.get(key) for row in rows]
        duplicates += len(identifiers) - len(set(map(json.dumps, identifiers)))
        records.extend(rows)
    observed = len(records)
    times = [moment for row in records for moment in _record_times(row)]
    classified = observed if isinstance(source["classification"], str) and source["classification"] else 0
    provenanced = observed if source["evidenceIds"] else 0
    return {
        "present": present,
        "expectedObservationCount": observed,
        "observedRecordCount": observed,
        "nonnullRequiredFieldCount": sum(all(value not in (None, "") for value in row.values()) for row in records),
        "duplicateObservationCount": duplicates,
        "classifiedObservationCount": classified,
        "provenancedObservationCount": provenanced,
        "latest": max(times) if times else None,
    }


def _reconciliation(members: dict[str, list[dict[str, Any]] | None]) -> dict[str, int]:
    rows = [row for value in members.values() if value for row in value]
    parties = {row["party_id"] for row in rows if "party_id" in row}
    accounts = {row["account_id"] for row in rows if "account_id" in row}
    return {
        "unresolvedHolderCount": sum(row["holder_party_id"] not in parties for row in rows if "holder_party_id" in row),
        "unresolvedEventAccountCount": sum(row["accountId"] not in accounts for row in rows if "accountId" in row),
    }


# --- the decision (shared with the equivalence test on the nine readiness fixtures) ----------------------------------


def _bounds(entry: dict[str, Any], name: str) -> tuple[Decimal, Decimal]:
    metric = entry["metrics"][name]
    if name in MINIMUM_METRICS:
        return Decimal(metric["passMinimum"]), Decimal(metric["warnMinimum"])
    return Decimal(metric["passMaximum"]), Decimal(metric["warnMaximum"])


def decide(policy: dict[str, Any], source_class: str, evaluation_time: datetime, counts: dict[str, int],
           latest: datetime | None, unresolved: int, personal_data: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    """Judge one source's measurements against the policy; returns the decision and the per-metric detail."""
    entry = policy["sourceClasses"].get(source_class)
    if entry is None:
        raise ReadinessInputError("source class is not in the readiness policy")
    observed = counts["observedRecordCount"]
    if observed == 0:
        return {"status": "FAIL", "reasonCodes": [MISSING_CODE]}, {}
    expected = counts["expectedObservationCount"]
    if expected == 0 or counts["nonnullRequiredFieldCount"] > expected or latest is None or latest > evaluation_time:
        raise ReadinessInputError("measurements are inconsistent")
    values = {
        "completeness": Decimal(counts["nonnullRequiredFieldCount"]) / Decimal(expected),
        "freshnessMinutes": Decimal(int((evaluation_time - latest).total_seconds())) / Decimal(60),
        "duplicateRate": Decimal(counts["duplicateObservationCount"]) / Decimal(observed),
        "classificationCoverage": Decimal(counts["classifiedObservationCount"]) / Decimal(observed),
        "provenanceCoverage": Decimal(counts["provenancedObservationCount"]) / Decimal(observed),
    }
    states: dict[str, str] = {}
    for name in entry["metrics"]:
        first, second = _bounds(entry, name)
        metric = values[name]
        if name in MINIMUM_METRICS:
            states[name] = "PASS" if metric >= first else "WARN" if metric >= second else "FAIL"
        else:
            states[name] = "PASS" if metric <= first else "WARN" if metric <= second else "FAIL"
    codes = {METRIC_CODES[name][0 if state == "WARN" else 1] for name, state in states.items() if state != "PASS"}
    banking = set()
    if unresolved:
        banking.add(RECONCILIATION_CODE)
    if personal_data:
        banking.add(PERSONAL_DATA_CODE)
    status = "FAIL" if banking or "FAIL" in states.values() else "WARN" if "WARN" in states.values() else "PASS"
    detail = {name: {"state": states[name], "value": format(values[name].quantize(QUANTUM, rounding=ROUND_HALF_EVEN), "f")} for name in states}
    return {"status": status, "reasonCodes": sorted(codes | banking)}, detail


def evaluate_readiness_fixture(policy: dict[str, Any], fixture: dict[str, Any], files: dict[str, bytes]) -> dict[str, Any]:
    """Decide one pack readiness fixture (fixtures/readiness/*.json) with the evaluator's own logic and scanner."""
    measurements = fixture["measurements"]
    counts = {name: measurements[name] for name in measurements if name != "latestObservationTime"}
    latest = None if measurements["latestObservationTime"] is None else _time(measurements["latestObservationTime"])
    personal = False
    mutation = fixture["mutation"]
    if mutation is not None:
        if mutation["builder"] != MUTATION_BUILDER:
            raise ReadinessInputError("mutation builder is not closed")
        value = json.loads(files[mutation["member"]])
        _, index, field = mutation["field"].split(".")
        value["records"][int(index)][field] = luhn_run()
        personal = bool(personal_data_hits(json.dumps(value, sort_keys=True)))
    unresolved = sum(fixture["reconciliation"].values())
    decision, _ = decide(policy, fixture["sourceClass"], _time(fixture["evaluationTime"]), counts, latest, unresolved, personal)
    return decision


# --- entry point ----------------------------------------------------------------------------------------------------


def _policy(pack_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    pack = load_pack(pack_root)
    policies = []
    for resource in pack.manifest["content"]["readiness"]:
        path = resource["path"]
        if path.endswith(".json"):
            value = json.loads(pack.files[path])
            if isinstance(value, dict) and value.get("kind") == POLICY_KIND:
                policies.append(value)
    if len(policies) != 1:
        raise ReadinessInputError("the pack does not declare exactly one readiness policy")
    return pack.manifest, policies[0]


def _inventory(base: Path) -> dict[str, Any]:
    path = _safe_member(base, INVENTORY_NAME)
    if path is None:
        raise ReadinessInputError("source inventory is absent")
    try:
        inventory = json.loads(_read_regular(path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReadinessInputError("source inventory does not parse") from exc
    if not isinstance(inventory, dict) or set(inventory) != INVENTORY_FIELDS:
        raise ReadinessInputError("source inventory fields are not closed")
    if (inventory["apiVersion"], inventory["kind"]) != INVENTORY_IDENTITY or not isinstance(inventory["sources"], list) or not inventory["sources"]:
        raise ReadinessInputError("source inventory identity differs")
    seen: set[str] = set()
    for source in inventory["sources"]:
        if not isinstance(source, dict) or set(source) != SOURCE_FIELDS:
            raise ReadinessInputError("source fields are not closed")
        if not isinstance(source["dataPaths"], list) or not source["dataPaths"] or not isinstance(source["evidenceIds"], list):
            raise ReadinessInputError("source data paths or evidence ids are not lists")
        if source["id"] in seen:
            raise ReadinessInputError("source ids are not unique")
        seen.add(source["id"])
    return inventory


def evaluate(pack_root: Path, input_dir: Path) -> dict[str, Any]:
    """Return the canonical readiness verdict for `input_dir` under the readiness policy of `pack_root`."""
    base = _checked_directory(Path(input_dir))
    manifest, policy = _policy(Path(pack_root))
    inventory = _inventory(base)
    members: dict[str, list[dict[str, Any]] | None] = {}
    texts: dict[str, str] = {}
    for source in inventory["sources"]:
        for relative in source["dataPaths"]:
            path = _safe_member(base, relative)
            if path is None:
                members[relative] = None
                continue
            data = _read_regular(path)
            members[relative] = _member_records(relative, data)
            texts[relative] = data.decode("utf-8")
    measured = {source["id"]: _measure(source, members) for source in inventory["sources"]}
    times = [item["latest"] for item in measured.values() if item["latest"] is not None]
    if not times:
        raise ReadinessInputError("the input carries no observation time")
    evaluation_time = max(times)
    reconciliation = _reconciliation(members)
    results = []
    for source in sorted(inventory["sources"], key=lambda item: item["id"]):
        item = measured[source["id"]]
        counts = {name: item[name] for name in item if name not in {"present", "latest"}}
        # A member without record timestamps (a document) is observed as of the input snapshot.
        latest = item["latest"] if item["latest"] is not None else (evaluation_time if item["observedRecordCount"] else None)
        unresolved = 0
        paths = set(source["dataPaths"])
        if any(row and "holder_party_id" in row[0] for path in paths if (row := members.get(path))):
            unresolved += reconciliation["unresolvedHolderCount"]
        if any(row and "accountId" in row[0] for path in paths if (row := members.get(path))):
            unresolved += reconciliation["unresolvedEventAccountCount"]
        personal = any(personal_data_hits(texts[path]) for path in source["dataPaths"] if path in texts)
        decision, detail = decide(policy, source["sourceClass"], evaluation_time, counts, latest, unresolved, personal)
        results.append({
            "sourceId": source["id"],
            "sourceClass": source["sourceClass"],
            "status": decision["status"],
            "reasonCodes": decision["reasonCodes"],
            "observedRecordCount": item["observedRecordCount"],
            "latestObservationTime": None if latest is None else latest.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "metrics": detail,
        })
    ready = all(item["status"] == "PASS" for item in results)
    return {
        "apiVersion": "harness.planeon.ai/readiness-verdict/v1alpha1",
        "kind": "ReadinessVerdict",
        "packId": manifest["metadata"]["id"],
        "packVersion": manifest["metadata"]["version"],
        "policy": {"id": policy["id"], "version": policy["version"]},
        "sourceInventoryId": inventory["id"],
        "evaluationTime": evaluation_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": results,
        "overallStatus": "READY" if ready else "BLOCKED",
        "evidence": dict(EVIDENCE),
    }


def verdict_bytes(verdict: dict[str, Any]) -> bytes:
    return canonical_json_bytes(verdict)
