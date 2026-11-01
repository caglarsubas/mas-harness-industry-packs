#!/usr/bin/env python3
"""Closed IND-BANK-001 banking business-domain acceptance handler."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402
from pyshacl import validate as shacl_validate  # noqa: E402
from rdflib import BNode, Graph, Literal, Namespace, URIRef  # noqa: E402
from rdflib.namespace import OWL, RDF, RDFS  # noqa: E402

from planeon_industry_packs import __version__ as framework_version  # noqa: E402
from planeon_industry_packs.canonical import canonical_json_bytes  # noqa: E402
from planeon_industry_packs.index import build_index  # noqa: E402
from planeon_industry_packs.loader import ValidatedPack, load_pack  # noqa: E402
from planeon_industry_packs.package import archive_bytes  # noqa: E402

EXPECTED_DISTRIBUTIONS = {"pyshacl": "0.40.1", "rdflib": "7.6.0"}
EVIDENCE = {"published": False, "runtimeEvidence": False, "assuranceEvidence": False, "tenantAcceptance": False}
ANSWER_SET_FIELDS = {"apiVersion", "kind", "id", "stage", "synthetic", "answers", "evidence", "expectedDecision"}
QUESTIONNAIRE_FIELDS = {"apiVersion", "kind", "id", "stage", "title", "questions"}
RESPONSE_TYPES = {"string", "boolean", "number", "choice"}
ROLE_QUESTIONS = (
    "business-owner-role", "domain-owner-role", "risk-owner-role",
    "compliance-owner-role", "data-steward-role", "evidence-approver-role",
)
BANK = Namespace("urn:planeon:banking:")
SH = Namespace("http://www.w3.org/ns/shacl#")
ADMITTED_IRI_PREFIXES = (
    "urn:planeon:banking:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "http://www.w3.org/2000/01/rdf-schema#",
    "http://www.w3.org/2001/XMLSchema#",
    "http://www.w3.org/2002/07/owl#",
    "http://www.w3.org/ns/shacl#",
)
CHOICE_BINDINGS = {
    "primary-business-objective": "BusinessObjective",
    "product-family-scope": "ProductFamily",
    "channel-scope": "Channel",
    "kpi-scope": "KeyPerformanceIndicator",
    "pilot-decision-scope": "PilotDecisionScope",
    "deferred-institution-specific-choices": "InstitutionSpecificChoice",
    "acceptance-outcome": "AcceptanceOutcome",
}
GLOSSARY_MEMBERS = (BANK.stableId, RDFS.label, RDFS.comment, BANK.termVersion, BANK.provenance, BANK.answersBusinessQuestion)
PROVENANCE = {"AUTHORED_CLEAN_ROOM", "NAMED_STANDARD_CONCEPT"}
ALIGNMENT_LITERALS = {"ISO 20022 PaymentInstruction", "ISO 13616 IBAN", "ISO 17442 LEI", "ISO 4217 currency code", "FIBO LegalEntity"}
GOVERNANCE_SCOPE = "automated-decision-out-of-pilot-scope"
# The one declared disallowed value: country code XX (unassigned), check digits 90, all-zero BBAN; built, never typed.
PINNED_VALUE = "XX" + "90" + "0" * 16
PINNED_FIXTURE = "fixtures/answers/personal-data-in-answer.json"
PACKET_OWNED_FILES = (
    "ci/handlers/ind_bank_001.py", "ci/targets/ind-bank-001.json",
    "tests/banking/test_banking_business_domain.py", "docs/banking/business-domain.md",
)
IBAN_CANDIDATE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}[0-9]{2}(?:[A-Z0-9]{11,30}|(?: [A-Z0-9]{4}){2,7}(?: [A-Z0-9]{1,3})?)(?![A-Za-z0-9])")
DIGIT_RUN = re.compile(r"(?<![0-9])[0-9](?:[ -]?[0-9]){12,18}(?![0-9])")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def luhn_valid(digits: str) -> bool:
    total = 0
    for position, character in enumerate(reversed(digits)):
        value = int(character)
        if position % 2:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def iban_valid(candidate: str) -> bool:
    compact = candidate.replace(" ", "")
    if not 15 <= len(compact) <= 34:
        return False
    rearranged = compact[4:] + compact[:4]
    return int("".join(str(int(character, 36)) for character in rearranged)) % 97 == 1


def find_disallowed(text: str) -> list[str]:
    """Structural scan: mod-97-valid IBAN shapes and Luhn-valid 13-19 digit runs."""
    found = {match.group(0) for match in IBAN_CANDIDATE.finditer(text) if iban_valid(match.group(0))}
    for match in DIGIT_RUN.finditer(text):
        digits = re.sub(r"[ -]", "", match.group(0))
        if 13 <= len(digits) <= 19 and luhn_valid(digits):
            found.add(match.group(0))
    return sorted(found)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def questionnaire_contract(pack: ValidatedPack) -> tuple[dict[str, dict[str, Any]], list[tuple[str, str]]]:
    """Return the closed question map and every prompt/title string with its location."""
    questions: dict[str, dict[str, Any]] = {}
    texts: list[tuple[str, str]] = []
    for resource in pack.manifest["content"]["questionnaires"]:
        path = resource["path"]
        if not path.startswith("questions/business/"):
            raise ValueError(f"questionnaire outside the business stage: {path}")
        document = yaml.safe_load(pack.files[path])
        if set(document) != QUESTIONNAIRE_FIELDS:
            raise ValueError(f"questionnaire fields are not closed: {path}")
        texts.append((f"{path}#title", document["title"]))
        for question in document["questions"]:
            identifier = question["id"]
            if identifier in questions:
                raise ValueError(f"duplicate question id: {identifier}")
            if question["responseType"] not in RESPONSE_TYPES or not isinstance(question["required"], bool):
                raise ValueError(f"question type is not closed: {identifier}")
            if question["responseType"] == "choice":
                expected = {"id", "prompt", "responseType", "required", "choices", "multiple"}
                choices = question.get("choices")
                if not isinstance(choices, list) or not choices or len(choices) != len(set(choices)) or not isinstance(question.get("multiple"), bool):
                    raise ValueError(f"choice question is not closed: {identifier}")
            else:
                expected = {"id", "prompt", "responseType", "required"}
            if set(question) != expected:
                raise ValueError(f"question fields are not closed: {identifier}")
            questions[identifier] = question
            texts.append((f"{path}#{identifier}", question["prompt"]))
    return questions, texts


def _answer_present(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _validate_answer_type(identifier: str, value: Any, question: dict[str, Any]) -> None:
    response_type = question["responseType"]
    if response_type == "choice":
        candidates = value if question["multiple"] else [value]
        if not isinstance(candidates, list) or not candidates or any(not isinstance(item, str) for item in candidates):
            raise ValueError(f"choice answer type mismatch: {identifier}")
        if len(candidates) != len(set(candidates)) or any(item not in question["choices"] for item in candidates):
            raise ValueError(f"choice answer outside closed set: {identifier}")
    elif response_type == "string" and not isinstance(value, str):
        raise ValueError(f"string answer type mismatch: {identifier}")
    elif response_type == "boolean" and not isinstance(value, bool):
        raise ValueError(f"boolean answer type mismatch: {identifier}")
    elif response_type == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise ValueError(f"number answer type mismatch: {identifier}")


def evaluate_answer_set(value: dict[str, Any], questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Refuse (ValueError) an invalid vector; otherwise return the deterministic decision."""
    if not isinstance(value, dict) or set(value) != ANSWER_SET_FIELDS:
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
        if _answer_present(answers[identifier]) or not question["required"]:
            _validate_answer_type(identifier, answers[identifier], question)

    reasons: set[str] = set()
    if any(not _answer_present(answers[identifier]) for identifier in ROLE_QUESTIONS):
        reasons.add("MISSING_ACCOUNTABLE_OWNER")
    if not _answer_present(answers["outcome-evidence-refs"]):
        reasons.add("INCOMPLETE_OUTCOME_EVIDENCE")
    if _answer_present(answers["institution-specific-claims"]) and answers["tenant-evidence-verified"] is not True:
        reasons.add("UNVERIFIED_INSTITUTION_SPECIFIC_CHOICE")
    if answers["role-separation-confirmed"] is not True:
        reasons.add("ROLE_SEPARATION_UNCONFIRMED")
    if answers["pilot-decision-scope"] == GOVERNANCE_SCOPE:
        reasons.add("DECISION_SCOPE_REQUIRES_GOVERNANCE_STAGE")
    if any(find_disallowed(text) for answer in answers.values() for text in _strings(answer)):
        reasons.add("PERSONAL_DATA_FORBIDDEN")
    special = set(ROLE_QUESTIONS) | {"outcome-evidence-refs"}
    if any(question["required"] and identifier not in special and not _answer_present(answers[identifier]) for identifier, question in questions.items()):
        reasons.add("INCOMPLETE_REQUIRED_ANSWER")
    if answers["acceptance-outcome"] != "pilot-scope-approved" and not reasons:
        reasons.add("NON_READY_ACCEPTANCE_OUTCOME")
    decision = {"status": "BLOCKED" if reasons else "READY", "reasonCodes": sorted(reasons)}
    if decision != value["expectedDecision"]:
        raise ValueError(f"declared and computed decisions differ: {value['id']}")
    return decision


def load_graph(*paths: Path) -> Graph:
    graph = Graph()
    for path in paths:
        graph.parse(path, format="turtle", publicID="urn:planeon:explicit-local-graph:")
    return graph


def check_graph_surface(graph: Graph, label: str) -> None:
    if (None, OWL.imports, None) in graph:
        raise ValueError(f"RDF import declared: {label}")
    for triple in graph:
        for term in triple:
            if isinstance(term, URIRef) and not str(term).startswith(ADMITTED_IRI_PREFIXES):
                raise ValueError(f"IRI outside the admitted namespaces: {label}")
            if not isinstance(term, (URIRef, BNode, Literal)):
                raise ValueError(f"unexpected RDF term: {label}")


def stable_ids(graph: Graph, class_name: str) -> set[str]:
    return {str(value) for subject in graph.subjects(RDF.type, BANK[class_name]) for value in graph.objects(subject, BANK.stableId)}


def check_glossary(graph: Graph, questions: dict[str, dict[str, Any]]) -> int:
    classes = set(graph.subjects(RDF.type, OWL.Class))
    terms = classes | {subject for cls in classes for subject in graph.subjects(RDF.type, cls)}
    for term in terms:
        for member in GLOSSARY_MEMBERS:
            if not any(isinstance(value, Literal) and str(value) for value in graph.objects(term, member)):
                raise ValueError(f"glossary member missing: {term} {member}")
        if {str(value) for value in graph.objects(term, BANK.termVersion)} != {"1.0.0"}:
            raise ValueError(f"term version is not 1.0.0: {term}")
        provenance = {str(value) for value in graph.objects(term, BANK.provenance)}
        alignment = {str(value) for value in graph.objects(term, BANK.alignsWithStandard)}
        if len(provenance) != 1 or not provenance <= PROVENANCE or not alignment <= ALIGNMENT_LITERALS:
            raise ValueError(f"provenance or alignment is not closed: {term}")
        if (provenance == {"NAMED_STANDARD_CONCEPT"}) != bool(alignment):
            raise ValueError(f"named-standard provenance and alignment disagree: {term}")
        if not {str(value) for value in graph.objects(term, BANK.answersBusinessQuestion)} <= set(questions):
            raise ValueError(f"term serves an unknown question: {term}")
    identifiers = [str(value) for term in terms for value in graph.objects(term, BANK.stableId)]
    for question, class_name in CHOICE_BINDINGS.items():
        if set(questions[question]["choices"]) != stable_ids(graph, class_name):
            raise ValueError(f"choices and ontology stable ids differ: {question}")
    if {identifier for identifier, question in questions.items() if question["responseType"] == "choice"} != set(CHOICE_BINDINGS):
        raise ValueError("a choice question is not bound to the ontology")
    if len(identifiers) != len(terms):
        raise ValueError("every glossary term needs exactly one stable id")
    return len(terms)


def shacl_result(pack_root: Path, fixture: str) -> tuple[bool, Graph]:
    data = load_graph(pack_root / "ontology/banking.ttl", pack_root / f"fixtures/answers/{fixture}")
    shapes = load_graph(pack_root / "ontology/banking.shacl.ttl")
    conforms, report, _ = shacl_validate(data, shacl_graph=shapes, inference="none", advanced=False, js=False, do_owl_imports=False)
    if not isinstance(report, Graph):
        raise ValueError("SHACL result graph is unavailable")
    return bool(conforms), report


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["banking"]:
        raise SystemExit("IND-BANK-001 accepts only PACK=banking")
    versions = {name: importlib.metadata.version(name) for name in EXPECTED_DISTRIBUTIONS}
    if versions != EXPECTED_DISTRIBUTIONS:
        raise SystemExit(f"dependency versions differ: {versions}")
    if framework_version != "0.1.1":
        raise SystemExit(f"framework version differs: {framework_version}")

    pack_root = ROOT / "packs/banking"
    pack = load_pack(pack_root, common_root=ROOT / "common")
    common = load_pack(ROOT / "common")
    if pack.manifest["metadata"]["id"] != "banking.financial-services" or pack.manifest["metadata"]["version"] != "0.1.0":
        raise SystemExit("banking pack identity differs")
    if pack.files["contracts.lock.json"] != common.files["contracts.lock.json"] or pack.files["journey.yaml"] != common.files["journey.yaml"]:
        raise SystemExit("banking bindings are not byte copies of common.foundation")
    first_index, second_index = build_index(pack_root), build_index(pack_root)
    first_archive, second_archive = archive_bytes(pack_root), archive_bytes(pack_root)
    if canonical_json_bytes(first_index) != canonical_json_bytes(second_index) or first_archive != second_archive:
        raise SystemExit("banking index or archive is not byte reproducible")
    if first_index["evidence"] != EVIDENCE:
        raise SystemExit("pack index asserted unavailable evidence")

    questions, question_texts = questionnaire_contract(pack)
    ontology = load_graph(pack_root / "ontology/banking.ttl")
    for relative in ("ontology/banking.ttl", "ontology/banking.shacl.ttl", "fixtures/answers/ontology-valid.ttl", "fixtures/answers/ontology-invalid.ttl"):
        check_graph_surface(load_graph(pack_root / relative), relative)
    glossary_terms = check_glossary(ontology, questions)

    positive, _ = shacl_result(pack_root, "ontology-valid.ttl")
    negative, negative_report = shacl_result(pack_root, "ontology-invalid.ttl")
    if not positive or negative:
        raise SystemExit("SHACL positive or negative boundary failed")
    components = set(negative_report.objects(None, SH.sourceConstraintComponent))
    if not {SH.MinCountConstraintComponent, SH.InConstraintComponent} <= components:
        raise SystemExit("negative SHACL graph did not report minimum-count and closed-value failures")
    if set(negative_report.objects(None, SH.focusNode)) != {BANK.SyntheticIncompleteKpi}:
        raise SystemExit("negative SHACL failures are not confined to the negative fixture")

    role_ids = {str(value): {str(item) for item in ontology.objects(subject, BANK.answersBusinessQuestion)} for subject in ontology.subjects(RDF.type, BANK.AccountableRole) for value in ontology.objects(subject, BANK.stableId)}
    findings: list[tuple[str, str, str]] = []
    decisions: dict[str, dict[str, Any]] = {}
    answer_digests: dict[str, str] = {}
    for path in sorted((pack_root / "fixtures/answers").glob("*.json")):
        relative = f"fixtures/answers/{path.name}"
        raw = path.read_bytes()
        value = json.loads(raw)
        if raw != canonical_json_bytes(value) + b"\n":
            raise SystemExit(f"answer vector is not canonical sorted UTF-8 JSON: {path.name}")
        decisions[path.name] = evaluate_answer_set(value, questions)
        answers = value["answers"]
        if set(answers["deferred-institution-specific-choices"]) != set(questions["deferred-institution-specific-choices"]["choices"]):
            raise SystemExit(f"a synthetic vector resolves an institution-specific choice: {path.name}")
        for question in ROLE_QUESTIONS:
            if _answer_present(answers[question]) and question not in role_ids.get(answers[question], set()):
                raise SystemExit(f"role answer is not the matching accountable role: {path.name}")
        findings += [(relative, key, hit) for key, answer in sorted(answers.items()) for text in _strings(answer) for hit in find_disallowed(text)]
        answer_digests[path.name] = _sha256(canonical_json_bytes(value))
    ready = sorted(name for name, decision in decisions.items() if decision["status"] == "READY")
    blockers = sorted(code for decision in decisions.values() for code in decision["reasonCodes"])
    if len(decisions) != 7 or ready != ["accepted-pilot.json"] or len(blockers) != 6 or len(set(blockers)) != 6:
        raise SystemExit("answer vectors are not one READY pilot and six single-reason blockers")

    findings += [(location, "text", hit) for location, text in question_texts for hit in find_disallowed(text)]
    for relative in ("ontology/banking.ttl", "ontology/banking.shacl.ttl"):
        literals = {str(term) for triple in load_graph(pack_root / relative) for term in triple if isinstance(term, Literal)}
        findings += [(relative, "literal", hit) for text in sorted(literals) for hit in find_disallowed(text)]
    if findings != [(PINNED_FIXTURE, "outcome-evidence-refs", PINNED_VALUE)]:
        raise SystemExit("disallowed-data scan did not find exactly the one declared value in the one declared vector")

    raw_hits = [(path, hit) for path, data in sorted(pack.files.items()) for hit in find_disallowed(data.decode("utf-8"))]
    raw_hits += [(path, hit) for path in PACKET_OWNED_FILES for hit in find_disallowed((ROOT / path).read_text(encoding="utf-8"))]
    if raw_hits != [(PINNED_FIXTURE, PINNED_VALUE)]:
        raise SystemExit("a card- or account-like literal exists outside the one declared vector")

    print(
        canonical_json_bytes(
            {
                "answerDigests": answer_digests,
                "archiveSha256": _sha256(first_archive[1]),
                "decisions": decisions,
                "dependencyVersions": versions,
                "disallowedDataFindings": [[location, key] for location, key, _ in findings],
                "frameworkVersion": framework_version,
                "glossaryTerms": glossary_terms,
                "indexSha256": _sha256(canonical_json_bytes(first_index)),
                "packDigest": pack.digest,
                "retainedArtifacts": False,
                "shaclNegativeComponents": sorted(str(item).rsplit("#", 1)[1] for item in components),
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
