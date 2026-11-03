#!/usr/bin/env python3
"""Closed IND-BANK-002 banking data-readiness acceptance handler."""

from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import io
import json
import re
import sys
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from planeon_industry_packs import __version__ as framework_version  # noqa: E402
from planeon_industry_packs.canonical import canonical_json_bytes  # noqa: E402
from planeon_industry_packs.index import build_index  # noqa: E402
from planeon_industry_packs.io import media_type  # noqa: E402
from planeon_industry_packs.loader import ValidatedPack, load_pack  # noqa: E402
from planeon_industry_packs.package import archive_bytes, package_pack  # noqa: E402

PACK_ROOT = ROOT / "packs/banking"
COMMON_ROOT = ROOT / "common"
PACK_ID = "banking.financial-services"
PACK_VERSION = "0.2.0"
ARCHIVE_NAME = "banking.financial-services-0.2.0.tar.gz"
PACK_FILE_COUNT = 38
PACK_RESOURCE_COUNT = 35
COMMON_PACK_DIGEST = "3cfea19e6e0a4a653d63622e250f40001b4f8221ebab18fa5bfc1601b8eddea3"
TOOLCHAIN_SHA256 = {
    "pyproject.toml": "331f31f6fbe122a860325e23256b95f2cdbfcffd82e3f95e3a0d99fde332b1ba",
    "uv.lock": "12ab191dedad208ea14f88a388006c395b63fbc4e9f23ea6583d802a30653e8f",
}

# Scanner reuse (DESIGN 4.5): the predecessor handler is loaded by file location under a fixed module name, never as
# __main__, and exactly these three functions are taken from it.
PREDECESSOR_PATH = ROOT / "ci/handlers/ind_bank_001.py"
PREDECESSOR_MODULE = "ind_bank_001_handler"
SCANNER_NAMES = ("find_disallowed", "luhn_valid", "find_disallowed_raw")
PACKET_OWNED_FILES = (
    "ci/handlers/ind_bank_002.py", "ci/targets/ind-bank-002.json",
    "tests/banking/test_banking_data_readiness.py", "docs/banking/data-readiness.md",
)

CONTRACTS_REPOSITORY = "mas-harness-contracts"
CONTRACT_BINDING = {
    "apiVersion": "harness.planeon.ai/data-contract-binding/v1alpha1",
    "kind": "DataContractBinding",
    "id": "banking.data.contract-binding",
    "stage": "data-readiness",
    "repository": CONTRACTS_REPOSITORY,
    "commit": "2146278a95344cd2a8e22596b2f315b46edffc88",
    "readinessSchema": {
        "path": "schemas/v1alpha1/readiness/data-readiness-assessment.schema.json",
        "sha256": "ffe003a1a7ec0773f49d8f394ac3dd6281114bd4335ff05c87d223412faf92a5",
    },
    "commonSchema": {
        "path": "schemas/v1alpha1/guidance/common.schema.json",
        "sha256": "4d77297073d4c2e559f1131fbada566b499197f87113f7e28b136f0b4ae5f429",
    },
    "historicalLockObservation": {
        "recordedPath": "schemas/v1alpha1/guidance/data-readiness-assessment.schema.json",
        "authoritativePath": "schemas/v1alpha1/readiness/data-readiness-assessment.schema.json",
        "contentDigestMatches": True,
        "status": "DOCUMENTED_NOT_CORRECTED",
    },
    "schemaBytesCopied": False,
}

FILES_DESCRIPTION = (
    "Synthetic product terms and policy text written for this pack; not an institution document. "
    "Each tenant replaces it with its own approved sources."
)
CLASS_LABEL = "illustrative, tenant-overridable"
MINIMUM_METRICS = ("completeness", "classificationCoverage", "provenanceCoverage")
MAXIMUM_METRICS = ("freshnessMinutes", "duplicateRate")
# Per-source-class (PASS bound, WARN bound); examples only, every tenant binds its own approved policy.
BANDS = {
    "api": {
        "completeness": ("0.98", "0.95"), "freshnessMinutes": ("60", "240"), "duplicateRate": ("0.01", "0.02"),
        "classificationCoverage": ("1.00", "0.98"), "provenanceCoverage": ("1.00", "0.98"),
    },
    "events": {
        "completeness": ("0.99", "0.97"), "freshnessMinutes": ("5", "15"), "duplicateRate": ("0.000", "0.005"),
        "classificationCoverage": ("1.00", "0.99"), "provenanceCoverage": ("1.00", "0.99"),
    },
    "files": {
        "completeness": ("0.95", "0.90"), "freshnessMinutes": ("10080", "43200"), "duplicateRate": ("0.02", "0.05"),
        "classificationCoverage": ("1.00", "0.98"), "provenanceCoverage": ("1.00", "0.99"),
    },
    "postgresql": {
        "completeness": ("1.00", "0.99"), "freshnessMinutes": ("1440", "2880"), "duplicateRate": ("0.000", "0.001"),
        "classificationCoverage": ("1.00", "0.99"), "provenanceCoverage": ("1.00", "0.99"),
    },
}


def _policy_metrics(bands: dict[str, tuple[str, str]]) -> dict[str, dict[str, str]]:
    return {
        name: {"passMinimum": first, "warnMinimum": second} if name in MINIMUM_METRICS else {"passMaximum": first, "warnMaximum": second}
        for name, (first, second) in bands.items()
    }


READINESS_POLICY = {
    "apiVersion": "harness.planeon.ai/data-readiness-policy/v1alpha1",
    "kind": "DataReadinessPolicy",
    "id": "banking.data.readiness-policy",
    "stage": "data-readiness",
    "version": "0.2.0",
    "illustrative": True,
    "tenantReplacementRequired": True,
    "decisionPrecedence": ["FAIL", "WARN", "PASS"],
    "missingDataReasonCode": "MISSING_DATA",
    "sourceClasses": {name: {"label": CLASS_LABEL, "metrics": _policy_metrics(bands)} for name, bands in BANDS.items()},
}
READINESS_RULE = {
    "apiVersion": "harness.planeon.ai/pack-rule/v1alpha1",
    "kind": "PackRule",
    "id": "banking.data.block-unready",
    "stage": "data-readiness",
    "when": {
        "any": [
            {"in": ["answers.data-readiness-evaluator-state", ["warn", "fail"]]},
            {"eq": ["answers.tenant-readiness-policy-approved", False]},
        ]
    },
    "action": {
        "type": "BLOCK_READINESS",
        "target": "banking.data.readiness",
        "message": "Banking data readiness remains blocked until deterministic evidence passes under a tenant-approved policy.",
    },
}
RULE_IDS = ["banking.data.block-unready"]
READINESS_IDS = ["banking.data.contract-binding", "banking.data.dataset-lock", "banking.data.readiness-policy"]

ROLE_IDS = ("business-owner", "domain-owner", "risk-owner", "compliance-owner", "data-steward", "evidence-approver")
PRODUCT_FAMILIES = ("deposits", "payments", "cards", "consumer-lending", "commercial-lending")
SOURCE_CLASSES = ("api", "postgresql", "events", "files")
DATA_QUESTIONNAIRES = {
    "banking.data.readiness-evidence": "questions/data/readiness.yaml",
    "banking.data.sources": "questions/data/sources.yaml",
}
QUESTION_CONTRACT = {
    "banking.data.readiness-evidence": {
        "expected-observation-count": ("number", True, None, None),
        "nonnull-required-field-count": ("number", True, None, None),
        "latest-observation-time": ("string", True, None, None),
        "duplicate-observation-count": ("number", True, None, None),
        "classified-observation-count": ("number", True, None, None),
        "provenanced-observation-count": ("number", True, None, None),
        "evidence-refs": ("string", True, None, None),
        "cross-source-reconciliation-confirmed": ("boolean", True, None, None),
        "readiness-policy-evidence-refs": ("string", True, None, None),
        "data-readiness-evaluator-state": ("choice", True, False, ("pass", "warn", "fail")),
        "tenant-readiness-policy-approved": ("boolean", True, None, None),
    },
    "banking.data.sources": {
        "data-source-class-scope": ("choice", True, True, SOURCE_CLASSES),
        "data-owner-role": ("choice", True, False, ROLE_IDS),
        "data-custodian-role": ("choice", True, False, ROLE_IDS),
        "data-classification-scope": ("string", True, None, None),
        "source-evidence-refs": ("string", True, None, None),
        "synthetic-examples-confirmed": ("boolean", True, None, None),
    },
}
FORBIDDEN_PROMPT_TERMS = (
    "credential", "secret", "password", "connection string", "endpoint", "account number", "card number",
    "regulatory conclusion", "customer record", "transaction record", "production fact",
)

OWNER_ROLE = "domain-owner"
CUSTODIAN_ROLE = "data-steward"
SOURCES = {
    "banking.source.api": ("api", "internal-synthetic", ("data/api/product-catalogue.json",), ("banking.evidence.api-inspection",)),
    "banking.source.events": ("events", "restricted-synthetic", ("data/events/transactions.jsonl",), ("banking.evidence.events-inspection",)),
    "banking.source.files": ("files", "internal-synthetic", ("data/files/product-terms.md",), ("banking.evidence.files-inspection",)),
    "banking.source.postgresql": (
        "postgresql", "restricted-synthetic",
        ("data/postgresql/accounts.csv", "data/postgresql/parties.csv"), ("banking.evidence.postgresql-inspection",),
    ),
}
SOURCE_FIELDS = {"id", "sourceClass", "ownerRole", "custodianRole", "classification", "dataPaths", "evidenceIds", "description"}
DATA_PATHS = tuple(sorted(path for _, _, paths, _ in SOURCES.values() for path in paths))
LOCK_FIELDS = {"apiVersion", "kind", "id", "stage", "synthetic", "algorithm", "members"}
MEMBER_FIELDS = {"path", "mediaType", "recordCount", "size", "sha256"}
API_FIELDS = ("recordId", "productFamily", "rateType", "rateBasisPoints", "observedAt")
EVENT_FIELDS = ("transactionId", "accountId", "transactionType", "amount", "currency", "bookingTime", "valueTime")
CSV_HEADERS = {
    "data/postgresql/accounts.csv": ("account_id", "holder_party_id", "product_family", "status", "opened_date", "observed_at"),
    "data/postgresql/parties.csv": ("party_id", "segment", "party_type", "observed_at"),
}
CURRENCIES = ("EUR", "GBP", "USD")
TIME_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
AMOUNT_PATTERN = re.compile(r"^[0-9]{1,5}\.[0-9]{2}$")
STABLE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
# Literal rule (DESIGN 4.2): no decimal digit run of 13 or more after removing single spaces and hyphens.
LONG_DIGIT_RUN = re.compile(r"[0-9](?:[ -]?[0-9]){12,}")

GATE_ORDER = (
    "business.owner", "business.outcome", "data.owner", "data.quality", "data.completeness",
    "data.freshness", "data.provenance", "data.classification", "integration.readiness", "autonomy.boundary",
)
GATE_IDS = frozenset(GATE_ORDER)
GATE_STATUSES = {"PASS", "NEEDS_INPUT", "BLOCKED", "NOT_APPLICABLE"}
STATUS_FOR_STATE = {"PASS": "PASS", "WARN": "NEEDS_INPUT", "FAIL": "BLOCKED"}
METRIC_CODES = {
    "completeness": ("COMPLETENESS_NEEDS_INPUT", "INCOMPLETE_DATA"),
    "freshnessMinutes": ("FRESHNESS_NEEDS_INPUT", "STALE_DATA"),
    "duplicateRate": ("DUPLICATE_RATE_NEEDS_INPUT", "DUPLICATE_DATA"),
    "classificationCoverage": ("CLASSIFICATION_NEEDS_INPUT", "UNCLASSIFIED_DATA"),
    "provenanceCoverage": ("PROVENANCE_NEEDS_INPUT", "UNPROVENANCED_DATA"),
}
METRIC_GATES = {
    "data.completeness": ("completeness", "data.completeness-needs-input", "data.incomplete"),
    "data.freshness": ("freshnessMinutes", "data.freshness-needs-input", "data.stale"),
    "data.provenance": ("provenanceCoverage", "data.provenance-needs-input", "data.unprovenanced"),
    "data.classification": ("classificationCoverage", "data.classification-needs-input", "data.unclassified"),
}
MISSING_CODE = "MISSING_DATA"
RECONCILIATION_CODE = "DATA_RECONCILIATION_MISMATCH"
PERSONAL_DATA_CODE = "PERSONAL_DATA_FORBIDDEN"
MEASUREMENT_EVIDENCE = "banking.evidence.synthetic-measurements"
FIXED_GATE_EVIDENCE = {
    "business.owner": "banking.evidence.business-owner",
    "business.outcome": "banking.evidence.business-outcome",
    "data.owner": "banking.evidence.data-owner",
}
SESSION_ID = "banking.session.synthetic-data-readiness"
READINESS_EVIDENCE = {
    "published": False, "deploymentEvidence": False, "runtimeEvidence": False, "assuranceEvidence": False, "tenantAcceptance": False,
}
INDEX_EVIDENCE = {"published": False, "runtimeEvidence": False, "assuranceEvidence": False, "tenantAcceptance": False}
FIXTURE_FIELDS = {
    "apiVersion", "kind", "id", "stage", "synthetic", "sourceClass", "evaluationTime", "measurements",
    "reconciliation", "mutation", "expectedDecision", "evidence", "assessment",
}
MEASUREMENT_FIELDS = {
    "expectedObservationCount", "observedRecordCount", "nonnullRequiredFieldCount", "duplicateObservationCount",
    "classifiedObservationCount", "provenancedObservationCount", "latestObservationTime",
}
RECONCILIATION_FIELDS = {"unresolvedHolderCount", "unresolvedEventAccountCount"}
MUTATION_FIELDS = {"member", "field", "builder"}
MUTATION_BUILDER = "luhn-valid-16-digit-run"
EXPECTED_VECTORS = {
    "fail-disallowed-data.json": ("api", "FAIL", (PERSONAL_DATA_CODE,)),
    "fail-duplicate.json": ("events", "FAIL", ("DUPLICATE_DATA",)),
    "fail-missing.json": ("postgresql", "FAIL", (MISSING_CODE,)),
    "fail-reconciliation.json": ("postgresql", "FAIL", (RECONCILIATION_CODE,)),
    "fail-stale.json": ("events", "FAIL", ("STALE_DATA",)),
    "fail-unclassified.json": ("postgresql", "FAIL", ("UNCLASSIFIED_DATA",)),
    "fail-unprovenanced.json": ("files", "FAIL", ("UNPROVENANCED_DATA",)),
    "pass.json": ("events", "PASS", ()),
    "warn-freshness.json": ("events", "WARN", ("FRESHNESS_NEEDS_INPUT",)),
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_luhn_run(length: int = 16) -> str:
    """Return a Luhn-valid decimal run built from arithmetic at run time; it is never a committed literal."""
    body = [(5 * index + 2) % 10 for index in range(length - 1)]
    total = 0
    for position, value in enumerate(reversed(body)):
        if position % 2 == 0:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return "".join(str(item) for item in body) + str((10 - total % 10) % 10)


def _load_predecessor() -> tuple[Callable[[str], list[str]], Callable[[str], bool], Callable[[str], list[str]]]:
    try:
        spec = importlib.util.spec_from_file_location(PREDECESSOR_MODULE, PREDECESSOR_PATH)
        if spec is None or spec.loader is None:
            raise ImportError("no loader for the predecessor handler")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        functions = tuple(getattr(module, name) for name in SCANNER_NAMES)
    except Exception as exc:  # every load failure is a refusal, never a fallback
        raise SystemExit(f"IND-BANK-002 refuses: the predecessor scanner did not load ({type(exc).__name__})") from None
    if module.__name__ != PREDECESSOR_MODULE or not all(callable(item) for item in functions):
        raise SystemExit("IND-BANK-002 refuses: a predecessor scanner function is unavailable")
    strict, luhn, raw = functions
    probe = build_luhn_run()
    try:
        working = (
            luhn(probe) is True
            and strict(f"ref {probe} end") == [probe]
            and raw(f"ref {probe} end") == [probe]
            and strict("synthetic-evidence") == []
            and raw("synthetic-evidence") == []
        )
    except Exception:  # a scanner that raises has failed
        working = False
    if not working:
        raise SystemExit("IND-BANK-002 refuses: a predecessor scanner function failed its run-time probe")
    return strict, luhn, raw


find_disallowed, luhn_valid, find_disallowed_raw = _load_predecessor()


def literal_runs(text: str) -> list[str]:
    return [match.group(0) for match in LONG_DIGIT_RUN.finditer(text)]


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not TIME_PATTERN.match(value):
        raise ValueError(f"time is not ISO 8601 UTC with T and colon separators: {label}")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def _count(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"count is not a non-negative integer: {label}")
    return value


def check_data_questionnaires(pack: ValidatedPack) -> list[str]:
    """Close the two data questionnaires against QUESTION_CONTRACT and return their prompts."""
    declared = {item["id"]: (item["path"], item["stage"]) for item in pack.manifest["content"]["questionnaires"] if item["stage"] == "data-readiness"}
    if declared != {identifier: (path, "data-readiness") for identifier, path in DATA_QUESTIONNAIRES.items()}:
        raise ValueError("data questionnaire declarations differ")
    prompts: list[str] = []
    for identifier, path in sorted(DATA_QUESTIONNAIRES.items()):
        document = yaml.safe_load(pack.files[path])
        if set(document) != {"apiVersion", "kind", "id", "stage", "title", "questions"}:
            raise ValueError(f"data questionnaire fields are not closed: {path}")
        if (document["apiVersion"], document["kind"], document["id"], document["stage"]) != (
            "harness.planeon.ai/questionnaire/v1alpha1", "Questionnaire", identifier, "data-readiness",
        ):
            raise ValueError(f"data questionnaire identity differs: {path}")
        contract: dict[str, tuple[Any, ...]] = {}
        for question in document["questions"]:
            closed = {"id", "prompt", "responseType", "required"} | ({"choices", "multiple"} if question.get("responseType") == "choice" else set())
            if set(question) != closed or question["id"] in contract:
                raise ValueError(f"data question is not closed: {path}")
            contract[question["id"]] = (
                question["responseType"], question["required"], question.get("multiple"),
                tuple(question["choices"]) if "choices" in question else None,
            )
            prompts.append(question["prompt"])
        if contract != QUESTION_CONTRACT[identifier]:
            raise ValueError(f"data question contract differs: {path}")
        prompts.append(document["title"])
    scope_prompt = next(question["prompt"] for question in yaml.safe_load(pack.files[DATA_QUESTIONNAIRES["banking.data.sources"]])["questions"] if question["id"] == "data-source-class-scope")
    if FILES_DESCRIPTION not in scope_prompt:
        raise ValueError("the files option does not carry the exact files sentence")
    if any(term in prompt.casefold() for prompt in prompts for term in FORBIDDEN_PROMPT_TERMS):
        raise ValueError("a data question requests a forbidden kind of information")
    return prompts


def check_contract_binding(binding: Any, contracts_lock: Any, pack: ValidatedPack) -> None:
    """The binding names the contracts repository by name only; the lock's repository value is compared by suffix and never printed."""
    if binding != CONTRACT_BINDING:
        raise ValueError("public readiness contract binding differs")
    repository = contracts_lock.get("repository") if isinstance(contracts_lock, dict) else None
    if not isinstance(repository, str) or repository.rsplit("/", 1)[-1] != binding["repository"]:
        raise ValueError("contracts lock repository suffix differs from the binding record")
    if contracts_lock.get("commit") != binding["commit"]:
        raise ValueError("contracts lock commit differs from the binding record")
    schemas = {entry["path"]: entry["sha256"] for entry in contracts_lock["schemas"]}
    if schemas.get(binding["commonSchema"]["path"]) != binding["commonSchema"]["sha256"]:
        raise ValueError("guidance schema digest differs from the contracts lock")
    observation = binding["historicalLockObservation"]
    if schemas.get(observation["recordedPath"]) != binding["readinessSchema"]["sha256"] or observation["authoritativePath"] in schemas:
        raise ValueError("historical guidance-path observation no longer matches the contracts lock")
    for path in (binding["readinessSchema"]["path"], binding["commonSchema"]["path"]):
        if (ROOT / path).exists():
            raise ValueError(f"contract schema bytes are present in the repository: {path}")
    if any(path.endswith(".schema.json") for path in pack.files):
        raise ValueError("schema bytes are present in the banking pack")


def check_policy(policy: Any) -> None:
    if policy != READINESS_POLICY:
        raise ValueError("readiness policy differs")
    for name, entry in policy["sourceClasses"].items():
        if entry["label"] != CLASS_LABEL:
            raise ValueError(f"source class is not labelled illustrative, tenant-overridable: {name}")


def check_source_inventory(inventory: Any, ontology_text: str) -> dict[str, dict[str, Any]]:
    """Close the four sources and return them by source class."""
    if not isinstance(inventory, dict) or set(inventory) != {"apiVersion", "kind", "id", "stage", "synthetic", "sources"}:
        raise ValueError("source inventory fields are not closed")
    if (inventory["apiVersion"], inventory["kind"], inventory["id"], inventory["stage"], inventory["synthetic"]) != (
        "harness.planeon.ai/source-inventory/v1alpha1", "SourceInventory", "banking.data.source-inventory", "data-readiness", True,
    ):
        raise ValueError("source inventory identity differs")
    sources = inventory["sources"]
    if [source.get("id") for source in sources] != sorted(SOURCES):
        raise ValueError("source inventory ids differ")
    by_class: dict[str, dict[str, Any]] = {}
    for source in sources:
        if set(source) != SOURCE_FIELDS:
            raise ValueError(f"source fields are not closed: {source['id']}")
        source_class, classification, paths, evidence = SOURCES[source["id"]]
        if source["sourceClass"] != source_class:
            raise ValueError(f"source class differs: {source['id']}")
        if source["classification"] != classification:
            raise ValueError(f"source classification differs: {source['id']}")
        if tuple(source["dataPaths"]) != paths:
            raise ValueError(f"source data path differs: {source['id']}")
        if tuple(source["evidenceIds"]) != evidence or not all(STABLE_ID.match(item) for item in evidence):
            raise ValueError(f"source evidence ids differ: {source['id']}")
        if (source["ownerRole"], source["custodianRole"]) != (OWNER_ROLE, CUSTODIAN_ROLE):
            raise ValueError(f"source owner or custodian role differs: {source['id']}")
        for role in (source["ownerRole"], source["custodianRole"]):
            if role not in ROLE_IDS or f'bank:stableId "{role}"' not in ontology_text:
                raise ValueError(f"source role is not a banking ontology role id: {source['id']}")
        description = source["description"]
        if source_class == "files":
            if description != FILES_DESCRIPTION:
                raise ValueError("the files source description is not the exact files sentence")
        elif not isinstance(description, str) or not description or description == FILES_DESCRIPTION:
            raise ValueError(f"source description is invalid: {source['id']}")
        by_class[source_class] = source
    return by_class


def _closed_record(value: Any, fields: tuple[str, ...], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or tuple(value) != fields:
        raise ValueError(f"data member record fields are not closed: {label}")
    return value


def member_records(path: str, data: bytes) -> list[Any]:
    """Parse one data member and check every field shape; the record list is what dataset.lock.json counts."""
    text = data.decode("utf-8")
    if path == "data/api/product-catalogue.json":
        value = json.loads(text)
        if set(value) != {"apiVersion", "kind", "id", "stage", "synthetic", "records"} or value["synthetic"] is not True:
            raise ValueError(f"data member envelope differs: {path}")
        records = [_closed_record(item, API_FIELDS, path) for item in value["records"]]
        for record in records:
            if not re.fullmatch(r"rate-[0-9]{4}", record["recordId"]) or record["productFamily"] not in PRODUCT_FAMILIES:
                raise ValueError(f"product catalogue record differs: {path}")
            if type(record["rateBasisPoints"]) is not int or not 0 <= record["rateBasisPoints"] <= 9999:
                raise ValueError(f"illustrative rate is out of range: {path}")
            _time(record["observedAt"], path)
        key = "recordId"
    elif path == "data/events/transactions.jsonl":
        if not text.endswith("\n") or "\n\n" in text:
            raise ValueError(f"event member lines are not closed: {path}")
        records = [_closed_record(json.loads(line), EVENT_FIELDS, path) for line in text.splitlines()]
        for record in records:
            if not re.fullmatch(r"txn-[0-9]{4}", record["transactionId"]) or not re.fullmatch(r"acct-[0-9]{4}", record["accountId"]):
                raise ValueError(f"event ids are not opaque: {path}")
            if not AMOUNT_PATTERN.match(record["amount"]) or record["currency"] not in CURRENCIES:
                raise ValueError(f"event amount or currency differs: {path}")
            if not re.fullmatch(r"[a-z]+(?:-[a-z]+)*", record["transactionType"]):
                raise ValueError(f"event type differs: {path}")
            _time(record["bookingTime"], path)
            _time(record["valueTime"], path)
        key = "transactionId"
    elif path in CSV_HEADERS:
        rows = list(csv.reader(io.StringIO(text)))
        if not rows or tuple(rows[0]) != CSV_HEADERS[path] or any(len(row) != len(rows[0]) for row in rows[1:]):
            raise ValueError(f"tabular member header or width differs: {path}")
        records = [dict(zip(rows[0], row)) for row in rows[1:]]
        for record in records:
            _time(record["observed_at"], path)
            if path.endswith("parties.csv"):
                if not re.fullmatch(r"party-[0-9]{4}", record["party_id"]) or record["party_type"] not in {"natural-person-role", "legal-entity"}:
                    raise ValueError(f"party record differs: {path}")
                if record["segment"] not in {"retail", "small-business", "corporate"}:
                    raise ValueError(f"party segment differs: {path}")
            else:
                if not re.fullmatch(r"acct-[0-9]{4}", record["account_id"]) or not re.fullmatch(r"party-[0-9]{4}", record["holder_party_id"]):
                    raise ValueError(f"account ids are not opaque: {path}")
                if record["product_family"] not in PRODUCT_FAMILIES or record["status"] not in {"active", "dormant"}:
                    raise ValueError(f"account record differs: {path}")
                if not DATE_PATTERN.match(record["opened_date"]):
                    raise ValueError(f"account opened date differs: {path}")
        key = rows[0][0]
    elif path == "data/files/product-terms.md":
        if FILES_DESCRIPTION not in text:
            raise ValueError(f"files member does not carry the files sentence: {path}")
        return [text]
    else:
        raise ValueError(f"undeclared data member: {path}")
    identifiers = [record[key] for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"data member ids are not unique: {path}")
    return records


def check_dataset_lock(lock: Any, files: dict[str, bytes]) -> dict[str, list[Any]]:
    """Bind every data member by path, media type, record count, size and SHA-256; return the parsed records."""
    if not isinstance(lock, dict) or set(lock) != LOCK_FIELDS:
        raise ValueError("dataset lock fields are not closed")
    if (lock["apiVersion"], lock["kind"], lock["id"], lock["stage"], lock["synthetic"], lock["algorithm"]) != (
        "harness.planeon.ai/synthetic-dataset-lock/v1alpha1", "SyntheticDatasetLock", "banking.data.dataset-lock", "data-readiness", True, "SHA-256",
    ):
        raise ValueError("dataset lock identity differs")
    if [member.get("path") for member in lock["members"]] != list(DATA_PATHS):
        raise ValueError("dataset member paths differ")
    records: dict[str, list[Any]] = {}
    for member in lock["members"]:
        path = member["path"]
        if set(member) != MEMBER_FIELDS:
            raise ValueError(f"dataset member fields are not closed: {path}")
        if path not in files:
            raise ValueError(f"dataset member is absent: {path}")
        data = files[path]
        if member["mediaType"] != media_type(path):
            raise ValueError(f"dataset member media type differs: {path}")
        if type(member["size"]) is not int or member["size"] != len(data):
            raise ValueError(f"dataset member size differs: {path}")
        if member["sha256"] != _sha256(data):
            raise ValueError(f"dataset member digest differs: {path}")
        records[path] = member_records(path, data)
        if type(member["recordCount"]) is not int or member["recordCount"] != len(records[path]):
            raise ValueError(f"dataset member record count differs: {path}")
    return records


def reconciliation_counts(records: dict[str, list[Any]]) -> dict[str, int]:
    parties = {row["party_id"] for row in records["data/postgresql/parties.csv"]}
    accounts = {row["account_id"] for row in records["data/postgresql/accounts.csv"]}
    return {
        "unresolvedHolderCount": sum(row["holder_party_id"] not in parties for row in records["data/postgresql/accounts.csv"]),
        "unresolvedEventAccountCount": sum(row["accountId"] not in accounts for row in records["data/events/transactions.jsonl"]),
    }


def check_data_members(files: dict[str, bytes]) -> None:
    """The literal rule and the strict scan over the five data members (no hit expected)."""
    for path in DATA_PATHS:
        text = files[path].decode("utf-8")
        if literal_runs(text):
            raise ValueError(f"data member holds a decimal digit run of thirteen or more: {path}")
        if find_disallowed(text):
            raise ValueError(f"data member holds a disallowed value: {path}")


def apply_mutation(mutation: Any, source: dict[str, Any], files: dict[str, bytes]) -> list[str]:
    """Inject the run-time Luhn value into an in-memory copy of the source member and return the strict-scan hits."""
    if not isinstance(mutation, dict) or set(mutation) != MUTATION_FIELDS or mutation["builder"] != MUTATION_BUILDER:
        raise ValueError("disallowed-data mutation is not closed")
    member = mutation["member"]
    if member not in source["dataPaths"] or not member.endswith(".json"):
        raise ValueError("disallowed-data mutation targets an undeclared member")
    parts = mutation["field"].split(".")
    if len(parts) != 3 or parts[0] != "records" or not parts[1].isdigit():
        raise ValueError("disallowed-data mutation field is not closed")
    value = copy.deepcopy(json.loads(files[member]))
    record = value["records"][int(parts[1])]
    if parts[2] not in record:
        raise ValueError("disallowed-data mutation field is absent")
    record[parts[2]] = build_luhn_run()
    return find_disallowed(json.dumps(value, sort_keys=True))


def evaluate_fixture(value: dict[str, Any], sources: dict[str, dict[str, Any]], files: dict[str, bytes]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return the deterministic decision and the metric detail (None for missing data)."""
    if not isinstance(value, dict) or set(value) != FIXTURE_FIELDS:
        raise ValueError("readiness fixture fields are not closed")
    if (value["apiVersion"], value["kind"], value["stage"], value["synthetic"]) != (
        "harness.planeon.ai/data-readiness-fixture/v1alpha1", "DataReadinessFixture", "data-readiness", True,
    ) or value["evidence"] != READINESS_EVIDENCE:
        raise ValueError(f"readiness fixture identity or evidence differs: {value.get('id')}")
    source_class = value["sourceClass"]
    if source_class not in BANDS:
        raise ValueError(f"readiness fixture names an unknown source class: {value['id']}")
    evaluation_time = _time(value["evaluationTime"], value["id"])
    measurements = value["measurements"]
    reconciliation = value["reconciliation"]
    if not isinstance(measurements, dict) or set(measurements) != MEASUREMENT_FIELDS:
        raise ValueError(f"measurement fields are not closed: {value['id']}")
    if not isinstance(reconciliation, dict) or set(reconciliation) != RECONCILIATION_FIELDS:
        raise ValueError(f"reconciliation fields are not closed: {value['id']}")
    counts = {name: _count(measurements[name], name) for name in sorted(MEASUREMENT_FIELDS - {"latestObservationTime"})}
    unresolved = {name: _count(reconciliation[name], name) for name in sorted(RECONCILIATION_FIELDS)}
    observed = counts["observedRecordCount"]
    if observed == 0:
        if measurements["latestObservationTime"] is not None or any(counts[name] for name in counts if name != "expectedObservationCount"):
            raise ValueError(f"zero-observation fixture carries observations: {value['id']}")
        return {"status": "FAIL", "reasonCodes": [MISSING_CODE]}, None
    expected = counts["expectedObservationCount"]
    if expected == 0 or counts["nonnullRequiredFieldCount"] > expected:
        raise ValueError(f"expected count is inconsistent: {value['id']}")
    if any(counts[name] > observed for name in ("duplicateObservationCount", "classifiedObservationCount", "provenancedObservationCount")):
        raise ValueError(f"a measurement exceeds the observed count: {value['id']}")
    latest = _time(measurements["latestObservationTime"], value["id"])
    if latest > evaluation_time:
        raise ValueError(f"latest observation is after the evaluation time: {value['id']}")
    metric_values = {
        "completeness": Decimal(counts["nonnullRequiredFieldCount"]) / Decimal(expected),
        "freshnessMinutes": Decimal(int((evaluation_time - latest).total_seconds())) / Decimal(60),
        "duplicateRate": Decimal(counts["duplicateObservationCount"]) / Decimal(observed),
        "classificationCoverage": Decimal(counts["classifiedObservationCount"]) / Decimal(observed),
        "provenanceCoverage": Decimal(counts["provenancedObservationCount"]) / Decimal(observed),
    }
    states: dict[str, str] = {}
    for name, (pass_bound, warn_bound) in BANDS[source_class].items():
        metric, first, second = metric_values[name], Decimal(pass_bound), Decimal(warn_bound)
        if name in MINIMUM_METRICS:
            states[name] = "PASS" if metric >= first else "WARN" if metric >= second else "FAIL"
        else:
            states[name] = "PASS" if metric <= first else "WARN" if metric <= second else "FAIL"
    codes = {METRIC_CODES[name][0 if state == "WARN" else 1] for name, state in states.items() if state != "PASS"}
    banking: set[str] = set()
    if any(unresolved.values()):
        banking.add(RECONCILIATION_CODE)
    if value["mutation"] is not None and apply_mutation(value["mutation"], sources[source_class], files):
        banking.add(PERSONAL_DATA_CODE)
    if banking or "FAIL" in states.values():
        status = "FAIL"
    elif "WARN" in states.values():
        status = "WARN"
    else:
        status = "PASS"
    return {"status": status, "reasonCodes": sorted(codes | banking)}, {"states": states, "banking": banking}


def _gate(gate_id: str, status: str, evidence: list[str], reason: str) -> dict[str, Any]:
    return {"gateId": gate_id, "status": status, "evidenceIds": sorted(set(evidence)), "reasonCode": reason}


def build_assessment(identifier: str, decision: dict[str, Any], detail: dict[str, Any] | None, source: dict[str, Any]) -> dict[str, Any]:
    """Build the one nested DataReadinessAssessment with the ten contract gates in order."""
    evidence = sorted(set(source["evidenceIds"]) | {MEASUREMENT_EVIDENCE})
    gates = {gate_id: _gate(gate_id, "PASS", [item], "evidence.satisfied") for gate_id, item in FIXED_GATE_EVIDENCE.items()}
    for gate_id in ("integration.readiness", "autonomy.boundary"):
        gates[gate_id] = _gate(gate_id, "NOT_APPLICABLE", [], "scope.not-applicable")
    if detail is None:
        gates["data.quality"] = _gate("data.quality", "BLOCKED", [], "data.missing")
        for gate_id in METRIC_GATES:
            gates[gate_id] = _gate(gate_id, "NOT_APPLICABLE", [], "data.no-observations")
    else:
        status, states, banking = decision["status"], detail["states"], detail["banking"]
        non_pass = {name for name, state in states.items() if state != "PASS"}
        if status == "PASS":
            reason = "evidence.satisfied"
        elif banking == {RECONCILIATION_CODE} and not non_pass:
            reason = "data.reconciliation-mismatch"
        elif non_pass == {"duplicateRate"} and not banking:
            reason = "data.duplicate" if status == "FAIL" else "data.duplicate-needs-input"
        else:
            reason = "data.quality-blocked" if status == "FAIL" else "data.quality-needs-input"
        gates["data.quality"] = _gate("data.quality", STATUS_FOR_STATE[status], evidence, reason)
        for gate_id, (metric, warn_reason, fail_reason) in METRIC_GATES.items():
            state = states[metric]
            gates[gate_id] = _gate(gate_id, STATUS_FOR_STATE[state], evidence, {"PASS": "evidence.satisfied", "WARN": warn_reason, "FAIL": fail_reason}[state])
        if PERSONAL_DATA_CODE in banking:
            gates["data.classification"] = _gate("data.classification", "BLOCKED", evidence, "data.personal-data-forbidden")
    ordered = [gates[gate_id] for gate_id in GATE_ORDER]
    return {
        "apiVersion": "harness.planeon.ai/v1alpha1",
        "kind": "DataReadinessAssessment",
        "metadata": {"id": identifier, "version": PACK_VERSION},
        "spec": {
            "questionnaireSessionId": SESSION_ID,
            "overallStatus": "READY" if decision["status"] == "PASS" else "BLOCKED",
            "gateResults": ordered,
            "missingGateIds": sorted(item["gateId"] for item in ordered if item["status"] in {"NEEDS_INPUT", "BLOCKED"}),
        },
    }


def check_assessment_contract(assessment: Any) -> None:
    """Refuse any gate id outside the ten, any reordering and any inconsistent summary."""
    if not isinstance(assessment, dict) or set(assessment) != {"apiVersion", "kind", "metadata", "spec"}:
        raise ValueError("assessment fields are not closed")
    if assessment["apiVersion"] != "harness.planeon.ai/v1alpha1" or assessment["kind"] != "DataReadinessAssessment":
        raise ValueError("assessment identity differs")
    spec = assessment["spec"]
    if not isinstance(spec, dict) or set(spec) != {"questionnaireSessionId", "overallStatus", "gateResults", "missingGateIds"}:
        raise ValueError("assessment spec fields are not closed")
    gates = spec["gateResults"]
    identifiers = [item.get("gateId") if isinstance(item, dict) else None for item in gates]
    if any(identifier not in GATE_IDS for identifier in identifiers):
        raise ValueError("assessment carries a gate id outside the ten contract gates")
    if identifiers != list(GATE_ORDER):
        raise ValueError("assessment gates are not the ten ordered contract gates")
    for item in gates:
        if set(item) != {"gateId", "status", "evidenceIds", "reasonCode"} or item["status"] not in GATE_STATUSES:
            raise ValueError(f"gate result is not closed: {item['gateId']}")
        if item["evidenceIds"] != sorted(set(item["evidenceIds"])) or not all(STABLE_ID.match(entry) for entry in item["evidenceIds"]):
            raise ValueError(f"gate evidence ids are not sorted stable ids: {item['gateId']}")
    if any(item["status"] != "NOT_APPLICABLE" for item in gates[-2:]):
        raise ValueError("integration and autonomy gates must be NOT_APPLICABLE")
    missing = sorted(item["gateId"] for item in gates if item["status"] in {"NEEDS_INPUT", "BLOCKED"})
    if spec["missingGateIds"] != missing:
        raise ValueError("missing gate ids do not match the non-pass gates")
    if (spec["overallStatus"] == "READY") != (not missing) or spec["overallStatus"] not in {"READY", "BLOCKED"}:
        raise ValueError("assessment readiness contradicts the gate results")


def check_fixture(name: str, value: Any, sources: dict[str, dict[str, Any]], files: dict[str, bytes]) -> dict[str, Any]:
    if name not in EXPECTED_VECTORS:
        raise ValueError(f"undeclared readiness vector: {name}")
    source_class, status, codes = EXPECTED_VECTORS[name]
    decision, detail = evaluate_fixture(value, sources, files)
    if value["id"] != f"banking.readiness.{name[:-5]}" or value["sourceClass"] != source_class:
        raise ValueError(f"readiness vector identity or class differs: {name}")
    if decision != value["expectedDecision"] or decision != {"status": status, "reasonCodes": list(codes)}:
        raise ValueError(f"declared and computed decisions differ: {name}")
    if (value["mutation"] is not None) != (name == "fail-disallowed-data.json"):
        raise ValueError(f"only the disallowed-data vector declares a mutation: {name}")
    expected_reconciliation = {"unresolvedHolderCount": 1 if name == "fail-reconciliation.json" else 0, "unresolvedEventAccountCount": 0}
    if value["reconciliation"] != expected_reconciliation:
        raise ValueError(f"reconciliation block differs: {name}")
    check_assessment_contract(value["assessment"])
    if value["assessment"] != build_assessment(value["id"], decision, detail, sources[source_class]):
        raise ValueError(f"declared and computed assessments differ: {name}")
    return decision


def check_manifest(pack: ValidatedPack, common: ValidatedPack) -> None:
    metadata, content = pack.manifest["metadata"], pack.manifest["content"]
    if metadata["id"] != PACK_ID or metadata["version"] != PACK_VERSION or pack.manifest["compatibility"]["frameworkVersion"] != "0.1.0":
        raise ValueError("banking pack identity or framework compatibility differs")
    if common.digest != COMMON_PACK_DIGEST or pack.manifest["extends"]["packDigest"] != COMMON_PACK_DIGEST:
        raise ValueError("common pack digest differs")
    if pack.files["contracts.lock.json"] != common.files["contracts.lock.json"] or pack.files["journey.yaml"] != common.files["journey.yaml"]:
        raise ValueError("banking bindings are not byte copies of common.foundation")
    if [item["id"] for item in content["rules"]] != RULE_IDS or [item["id"] for item in content["readiness"]] != READINESS_IDS:
        raise ValueError("rule or readiness ids differ")
    if content["controls"] or content["providerPreferences"]:
        raise ValueError("controls and provider preferences stay empty in banking 0.2.0")
    if len(pack.files) != PACK_FILE_COUNT or len(pack.resource_ids) != PACK_RESOURCE_COUNT:
        raise ValueError("banking file or resource inventory differs")
    for name, digest in TOOLCHAIN_SHA256.items():
        if _sha256((ROOT / name).read_bytes()) != digest:
            raise ValueError(f"toolchain file differs: {name}")


def run() -> dict[str, Any]:
    pack = load_pack(PACK_ROOT, common_root=COMMON_ROOT)
    common = load_pack(COMMON_ROOT)
    check_manifest(pack, common)
    check_data_questionnaires(pack)
    check_contract_binding(json.loads(pack.files["data/contract-binding.json"]), json.loads(pack.files["contracts.lock.json"]), pack)
    check_policy(json.loads(pack.files["data/readiness-policy.json"]))
    if json.loads(pack.files["rules/data-readiness.json"]) != READINESS_RULE:
        raise ValueError("data-readiness rule differs")
    sources = check_source_inventory(json.loads(pack.files["fixtures/sources/source-inventory.json"]), pack.files["ontology/banking.ttl"].decode("utf-8"))
    lock = json.loads(pack.files["data/dataset.lock.json"])
    records = check_dataset_lock(lock, pack.files)
    check_data_members(pack.files)
    if reconciliation_counts(records) != {"unresolvedHolderCount": 0, "unresolvedEventAccountCount": 0}:
        raise ValueError("committed data members do not reconcile")

    vector_paths = sorted(path for path in pack.files if path.startswith("fixtures/readiness/"))
    if [path.rsplit("/", 1)[1] for path in vector_paths] != sorted(EXPECTED_VECTORS):
        raise ValueError("readiness vector inventory differs")
    decisions: dict[str, dict[str, Any]] = {}
    vector_digests: dict[str, str] = {}
    for path in vector_paths + ["fixtures/sources/source-inventory.json"]:
        if literal_runs(pack.files[path].decode("utf-8")):
            raise ValueError(f"fixture holds a decimal digit run of thirteen or more: {path}")
    for path in vector_paths:
        name = path.rsplit("/", 1)[1]
        value = json.loads(pack.files[path])
        decisions[name] = check_fixture(name, value, sources, pack.files)
        vector_digests[name] = _sha256(canonical_json_bytes(value))

    raw_hits = [(path, hit) for path in PACKET_OWNED_FILES for hit in find_disallowed_raw((ROOT / path).read_text(encoding="utf-8"))]
    if raw_hits:
        raise ValueError("a card- or account-like literal exists in a packet-owned file")

    first_index, second_index = build_index(PACK_ROOT, common_root=COMMON_ROOT), build_index(PACK_ROOT, common_root=COMMON_ROOT)
    first_archive, second_archive = archive_bytes(PACK_ROOT, common_root=COMMON_ROOT), archive_bytes(PACK_ROOT, common_root=COMMON_ROOT)
    if canonical_json_bytes(first_index) != canonical_json_bytes(second_index) or first_archive != second_archive:
        raise ValueError("banking index or archive is not byte reproducible")
    if first_archive[0] != ARCHIVE_NAME or first_index["evidence"] != INDEX_EVIDENCE:
        raise ValueError("banking archive name or index evidence differs")
    with tempfile.TemporaryDirectory(prefix="ind-bank-002-") as temporary:
        written = package_pack(PACK_ROOT, Path(temporary) / "package", common_root=COMMON_ROOT)
        if written.name != ARCHIVE_NAME or written.read_bytes() != first_archive[1]:
            raise ValueError("temporary package differs from the in-memory archive")
    if Path(temporary).exists():
        raise ValueError("a temporary output was retained")

    return {
        "archiveSha256": _sha256(first_archive[1]),
        "contractBindingSha256": _sha256(canonical_json_bytes(CONTRACT_BINDING)),
        "datasetLockSha256": _sha256(canonical_json_bytes(lock)),
        "decisions": decisions,
        "evidence": READINESS_EVIDENCE,
        "frameworkVersion": framework_version,
        "indexSha256": _sha256(canonical_json_bytes(first_index)),
        "packDigest": pack.digest,
        "packVersion": PACK_VERSION,
        "retainedArtifacts": False,
        "scannerModule": PREDECESSOR_MODULE,
        "vectorDigests": vector_digests,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["banking"]:
        raise SystemExit("IND-BANK-002 accepts only PACK=banking")
    if framework_version != "0.1.1":
        raise SystemExit(f"framework version differs: {framework_version}")
    try:
        summary = run()
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"IND-BANK-002 refuses: {exc}") from None
    print(canonical_json_bytes(summary).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
