#!/usr/bin/env python3
"""Closed IND-WG-001 business-domain acceptance handler."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from pyshacl import validate as shacl_validate
from rdflib import Graph, Namespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from planeon_industry_packs import __version__ as framework_version  # noqa: E402
from planeon_industry_packs.canonical import canonical_json_bytes  # noqa: E402
from planeon_industry_packs.index import build_index  # noqa: E402
from planeon_industry_packs.loader import ValidatedPack, load_pack  # noqa: E402
from planeon_industry_packs.package import archive_bytes  # noqa: E402

EXPECTED_DISTRIBUTIONS = {
    "pyshacl": "0.40.1",
    "rdflib": "7.6.0",
}
ANSWER_SET_FIELDS = {
    "apiVersion",
    "kind",
    "id",
    "stage",
    "synthetic",
    "answers",
    "deferredPlantSpecificChoices",
    "evidence",
    "expectedDecision",
}
EVIDENCE = {
    "published": False,
    "runtimeEvidence": False,
    "assuranceEvidence": False,
    "tenantAcceptance": False,
}
ROLE_QUESTIONS = {
    "business-owner-role",
    "domain-owner-role",
    "quality-owner-role",
    "data-steward-role",
    "evidence-approver-role",
}
WG = Namespace("urn:planeon:white-goods:")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _questionnaire_contract(pack: ValidatedPack) -> dict[str, dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {}
    for resource in pack.manifest["content"]["questionnaires"]:
        if not resource["path"].startswith("questions/business/"):
            continue
        value = yaml.safe_load(pack.files[resource["path"]])
        for question in value["questions"]:
            identifier = question["id"]
            if identifier in questions:
                raise ValueError(f"duplicate question id: {identifier}")
            questions[identifier] = question
    return questions


def _answer_present(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _validate_answer_type(identifier: str, value: Any, question: dict[str, Any]) -> None:
    response_type = question["responseType"]
    multiple = question.get("multiple", False)
    if response_type == "choice":
        candidates = value if multiple else [value]
        if not isinstance(candidates, list) or not candidates or any(not isinstance(item, str) for item in candidates):
            raise ValueError(f"choice answer type mismatch: {identifier}")
        if len(candidates) != len(set(candidates)) or any(item not in question["choices"] for item in candidates):
            raise ValueError(f"choice answer outside closed set: {identifier}")
    elif response_type == "string":
        if not isinstance(value, str):
            raise ValueError(f"string answer type mismatch: {identifier}")
    elif response_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"boolean answer type mismatch: {identifier}")
    elif response_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"number answer type mismatch: {identifier}")
    else:
        raise ValueError(f"unsupported response type: {response_type}")


def evaluate_answer_set(value: dict[str, Any], questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(value) != ANSWER_SET_FIELDS:
        raise ValueError("answer-set fields are not closed")
    if value["apiVersion"] != "harness.planeon.ai/industry-answer-set/v1alpha1" or value["kind"] != "IndustryAnswerSet":
        raise ValueError("answer-set identity is invalid")
    if value["stage"] != "evidence-and-acceptance" or value["synthetic"] is not True:
        raise ValueError("answer set must be synthetic evidence-and-acceptance data")
    if value["evidence"] != EVIDENCE:
        raise ValueError("answer set cannot assert platform evidence")
    answers = value["answers"]
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ValueError("answer keys do not match the closed questionnaire")
    for identifier, question in questions.items():
        answer = answers[identifier]
        if _answer_present(answer):
            _validate_answer_type(identifier, answer, question)
        elif not question["required"]:
            _validate_answer_type(identifier, answer, question)

    deferred = value["deferredPlantSpecificChoices"]
    declared_deferred = answers["deferred-plant-specific-choices"]
    normalized_deferred = [item.replace("-", " ") for item in declared_deferred]
    if not isinstance(deferred, list) or not deferred or len(deferred) != len(set(deferred)):
        raise ValueError("deferred plant-specific choices must be a unique non-empty list")
    if deferred != normalized_deferred:
        raise ValueError("deferred choices do not match the questionnaire answer")

    reasons: set[str] = set()
    if any(not _answer_present(answers[identifier]) for identifier in ROLE_QUESTIONS):
        reasons.add("MISSING_ACCOUNTABLE_OWNER")
    if not _answer_present(answers["outcome-evidence-refs"]):
        reasons.add("INCOMPLETE_OUTCOME_EVIDENCE")
    if _answer_present(answers["plant-specific-claims"]) and answers["tenant-evidence-verified"] is not True:
        reasons.add("UNVERIFIED_PLANT_SPECIFIC_CHOICE")
    if answers["role-separation-confirmed"] is not True:
        reasons.add("ROLE_SEPARATION_UNCONFIRMED")
    special = ROLE_QUESTIONS | {"outcome-evidence-refs"}
    if any(question["required"] and identifier not in special and not _answer_present(answers[identifier]) for identifier, question in questions.items()):
        reasons.add("INCOMPLETE_REQUIRED_ANSWER")
    if answers["acceptance-outcome"] != "pilot-scope-approved" and not reasons:
        reasons.add("NON_READY_ACCEPTANCE_OUTCOME")
    decision = {"status": "BLOCKED" if reasons else "READY", "reasonCodes": sorted(reasons)}
    if decision != value["expectedDecision"]:
        raise ValueError(f"declared and computed decisions differ: {value['id']}")
    return decision


def _load_graph(path: Path) -> Graph:
    graph = Graph()
    graph.parse(path, format="turtle", publicID="urn:planeon:local-graph:")
    return graph


def _shacl_result(pack_root: Path, fixture: str) -> tuple[bool, Graph]:
    data = _load_graph(pack_root / "ontology/white-goods.ttl")
    data.parse(pack_root / f"fixtures/answers/{fixture}", format="turtle", publicID="urn:planeon:local-fixture:")
    shapes = _load_graph(pack_root / "ontology/white-goods.shacl.ttl")
    conforms, report_graph, _ = shacl_validate(
        data,
        shacl_graph=shapes,
        inference="none",
        advanced=False,
        js=False,
        do_owl_imports=False,
    )
    if not isinstance(report_graph, Graph):
        raise ValueError("SHACL result graph is unavailable")
    return bool(conforms), report_graph


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["white-goods"]:
        raise SystemExit("IND-WG-001 accepts only PACK=white-goods")
    versions = {name: importlib.metadata.version(name) for name in EXPECTED_DISTRIBUTIONS}
    if versions != EXPECTED_DISTRIBUTIONS:
        raise SystemExit(f"dependency versions differ: {versions}")
    if framework_version != "0.1.1":
        raise SystemExit(f"framework version differs: {framework_version}")

    pack_root = ROOT / "packs/white-goods"
    pack = load_pack(pack_root, common_root=ROOT / "common")
    first_index, second_index = build_index(pack_root), build_index(pack_root)
    first_archive, second_archive = archive_bytes(pack_root), archive_bytes(pack_root)
    if canonical_json_bytes(first_index) != canonical_json_bytes(second_index) or first_archive != second_archive:
        raise SystemExit("white-goods index or archive is not byte reproducible")
    if first_index["evidence"] != EVIDENCE:
        raise SystemExit("pack index asserted unavailable evidence")

    positive, _ = _shacl_result(pack_root, "ontology-valid.ttl")
    negative, negative_report = _shacl_result(pack_root, "ontology-invalid.ttl")
    if not positive or negative:
        raise SystemExit("SHACL positive or negative boundary failed")
    sh = Namespace("http://www.w3.org/ns/shacl#")
    if (None, sh.sourceConstraintComponent, sh.MinCountConstraintComponent) not in negative_report:
        raise SystemExit("negative SHACL graph did not report a minimum-count failure")

    questions = _questionnaire_contract(pack)
    answer_digests: dict[str, str] = {}
    for path in sorted((pack_root / "fixtures/answers").glob("*.json")):
        raw = path.read_bytes()
        value = json.loads(raw)
        evaluate_answer_set(value, questions)
        answer_digests[path.name] = _sha256(canonical_json_bytes(value))

    print(
        canonical_json_bytes(
            {
                "answerDigests": answer_digests,
                "archiveSha256": _sha256(first_archive[1]),
                "dependencyVersions": versions,
                "frameworkVersion": framework_version,
                "indexSha256": _sha256(canonical_json_bytes(first_index)),
                "packDigest": pack.digest,
                "retainedArtifacts": False,
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
