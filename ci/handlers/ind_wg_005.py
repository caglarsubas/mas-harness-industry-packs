#!/usr/bin/env python3
"""Closed IND-WG-005 source-certification fixture acceptance handler."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_pack_manifest import (  # noqa: E402
    EVIDENCE_BOUNDARY,
    EXCLUDED_PATHS,
    LOCK_PATH,
    MANIFEST_PATH,
    build_lock,
    build_manifest,
    document_bytes,
    validate_lock,
    validate_manifest,
    verify_tamper_vectors,
)
from planeon_industry_packs import __version__ as framework_version  # noqa: E402
from planeon_industry_packs.canonical import canonical_json_bytes  # noqa: E402
from planeon_industry_packs.index import build_index  # noqa: E402
from planeon_industry_packs.loader import ValidatedPack, file_records, load_pack  # noqa: E402
from planeon_industry_packs.package import archive_bytes  # noqa: E402

PACK_ROOT = ROOT / "packs/white-goods"
COMMON_ROOT = ROOT / "common"
SCENARIOS = ("air-gap", "minimal-amd64", "minimal-arm64", "regulated-openshift", "silo")
NEW_PATHS = {
    *(f"fixtures/e2e/{slug}.json" for slug in SCENARIOS),
    "fixtures/e2e/tamper-vectors.json",
    LOCK_PATH,
    MANIFEST_PATH,
}
PREDECESSOR_BINDING = {
    "commit": "3814e642c8c8eb9f9bf77f230930eeff209de565",
    "packDigest": "38a056e7f3008aa9980fc12f1677f6f160dddb18aa156e63258921b911ab1773",
    "packYamlSha256": "29e8732b5e6730ecc42e54bed8f00487ece81cde4c50fc1521f711b65240defb",
    "archiveSha256": "3f0a3b22e1152526324fd7f7940a8d45331b2d182da309f249ef94956476856c",
    "indexSha256": "022a9d685c52cb73dad7b51d53c4d02a0168680ad138af99503076af9bd6783b",
    "fileCount": 64,
    "resourceCount": 61,
    "frameworkWheelSha256": "d34a1a3c523b1e60f10602fff072d5dbf83f46f2220f29a4f13b9a31facf91f4",
}
PREDECESSOR_IMMUTABLE_FILE_COUNT = 63
PREDECESSOR_IMMUTABLE_DIGEST = "29fab4d63fa7210c7c00751400c59186c6bbdf01609442419757b6ba66fe5867"
BINDING_FIELDS = {"path", "sha256"}
SCENARIO_FIELDS = {
    "apiVersion",
    "kind",
    "id",
    "stage",
    "synthetic",
    "profileSlug",
    "bindings",
    "expectedOutcome",
    "evidenceBoundary",
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json(files: dict[str, bytes], path: str) -> dict[str, Any]:
    value = json.loads(files[path])
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def _validate_pack_contract(pack: ValidatedPack, common: ValidatedPack) -> None:
    if pack.manifest["metadata"] != {
        "id": "white-goods.manufacturing",
        "version": "0.5.0",
        "title": "White-goods business, data, governance, provider-profile, and source-certification foundation",
        "industry": "white-goods",
        "license": "Apache-2.0",
        "packKind": "SECTOR",
    }:
        raise ValueError("white-goods pack metadata differs")
    if pack.manifest["compatibility"]["frameworkVersion"] != "0.1.0":
        raise ValueError("pack format compatibility differs")
    if common.manifest["metadata"]["version"] != "1.0.0" or pack.manifest["extends"]["packDigest"] != common.digest:
        raise ValueError("common foundation binding differs")
    if len(pack.files) != 72 or len(pack.resource_ids) != 69:
        raise ValueError("white-goods file or resource inventory differs")
    declared = {
        resource["path"]: (resource["id"], resource["stage"])
        for category in pack.manifest["content"].values()
        for resource in category
    }
    expected_new = {
        **{
            f"fixtures/e2e/{slug}.json": (
                f"white-goods.certification.scenario.{slug}",
                "evidence-and-acceptance",
            )
            for slug in SCENARIOS
        },
        "fixtures/e2e/tamper-vectors.json": (
            "white-goods.certification.tamper-vectors",
            "evidence-and-acceptance",
        ),
        LOCK_PATH: ("white-goods.certification.pack-lock", "evidence-and-acceptance"),
        MANIFEST_PATH: (
            "white-goods.certification.artifact-manifest",
            "evidence-and-acceptance",
        ),
    }
    if {path: declared.get(path) for path in NEW_PATHS} != expected_new:
        raise ValueError("IND-WG-005 resource declarations differ")
    predecessor_files = {
        path: value
        for path, value in pack.files.items()
        if path != "pack.yaml" and path not in NEW_PATHS
    }
    if len(predecessor_files) != PREDECESSOR_IMMUTABLE_FILE_COUNT:
        raise ValueError("predecessor immutable inventory differs")
    predecessor_digest = _sha256(canonical_json_bytes(file_records(predecessor_files)))
    if predecessor_digest != PREDECESSOR_IMMUTABLE_DIGEST:
        raise ValueError("predecessor immutable bytes changed")


def validate_scenarios(files: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    scenarios: dict[str, dict[str, Any]] = {}
    for slug in SCENARIOS:
        path = f"fixtures/e2e/{slug}.json"
        value = _json(files, path)
        if set(value) != SCENARIO_FIELDS:
            raise ValueError(f"scenario fields differ: {slug}")
        if (
            value["apiVersion"] != "harness.planeon.ai/industry-certification-scenario/v1alpha1"
            or value["kind"] != "IndustryCertificationScenario"
            or value["id"] != f"white-goods.certification.scenario.{slug}"
            or value["stage"] != "evidence-and-acceptance"
            or value["synthetic"] is not True
            or value["profileSlug"] != slug
            or value["expectedOutcome"] != "SOURCE_CONTRACT_READY"
            or value["evidenceBoundary"] != EVIDENCE_BOUNDARY
        ):
            raise ValueError(f"scenario identity or boundary differs: {slug}")
        governance_path = (
            "fixtures/governance/ready-reversible-write.json"
            if slug == "regulated-openshift"
            else "fixtures/governance/ready-read-only.json"
        )
        expected_paths = {
            "businessAnswers": "fixtures/answers/accepted-pilot.json",
            "dataReadiness": "fixtures/readiness/pass.json",
            "governanceDecision": governance_path,
            "providerDemand": f"fixtures/demands/{slug}.json",
            "providerGolden": f"fixtures/expected/{slug}.json",
        }
        bindings = value["bindings"]
        if not isinstance(bindings, dict) or set(bindings) != set(expected_paths):
            raise ValueError(f"scenario binding inventory differs: {slug}")
        for name, expected_path in expected_paths.items():
            binding = bindings[name]
            if not isinstance(binding, dict) or set(binding) != BINDING_FIELDS or binding["path"] != expected_path:
                raise ValueError(f"scenario binding fields differ: {slug}/{name}")
            if expected_path not in files or binding["sha256"] != _sha256(files[expected_path]):
                raise ValueError(f"scenario referenced bytes differ: {slug}/{name}")
        business = _json(files, expected_paths["businessAnswers"])
        readiness = _json(files, expected_paths["dataReadiness"])
        governance = _json(files, expected_paths["governanceDecision"])
        demand = _json(files, expected_paths["providerDemand"])
        golden = _json(files, expected_paths["providerGolden"])
        if business.get("id") != "white-goods.answers.accepted-pilot" or business.get("expectedDecision") != {"status": "READY", "reasonCodes": []}:
            raise ValueError("business source contract is not ready")
        if readiness.get("id") != "white-goods.readiness.pass" or readiness.get("expectedDecision") != {"status": "PASS", "reasonCodes": []}:
            raise ValueError("data source contract is not ready")
        expected_governance_id = f"white-goods.governance.fixture.{'ready-reversible-write' if slug == 'regulated-openshift' else 'ready-read-only'}"
        if governance.get("id") != expected_governance_id or governance.get("expectedDecision") != {"status": "READY", "reasonCodes": []}:
            raise ValueError("governance source contract is not ready")
        if demand.get("id") != f"white-goods.providers.demand.{slug}" or golden.get("id") != f"white-goods.providers.golden.{slug}":
            raise ValueError("provider fixture identity differs")
        scenarios[slug] = value
    return scenarios


def validate_tamper_catalog(files: dict[str, bytes]) -> dict[str, Any]:
    value = _json(files, "fixtures/e2e/tamper-vectors.json")
    if set(value) != {"apiVersion", "kind", "id", "stage", "synthetic", "vectors"}:
        raise ValueError("tamper catalog fields differ")
    if (
        value["apiVersion"] != "harness.planeon.ai/industry-certification-tamper-catalog/v1alpha1"
        or value["kind"] != "IndustryCertificationTamperCatalog"
        or value["id"] != "white-goods.certification.tamper-vectors"
        or value["stage"] != "evidence-and-acceptance"
        or value["synthetic"] is not True
        or not isinstance(value["vectors"], list)
        or len(value["vectors"]) != 5
    ):
        raise ValueError("tamper catalog identity or inventory differs")
    if [item.get("mutationKind") for item in value["vectors"]] != [
        "CONTENT_BYTES_CHANGED",
        "MEMBER_MISSING",
        "UNDECLARED_MEMBER",
        "LOCK_PAYLOAD_DIGEST_CHANGED",
        "MANIFEST_LOCK_BINDING_CHANGED",
    ]:
        raise ValueError("tamper mutation order differs")
    return value


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["white-goods"]:
        raise SystemExit("IND-WG-005 accepts only PACK=white-goods")
    if framework_version != "0.1.1":
        raise SystemExit(f"framework version differs: {framework_version}")

    pack = load_pack(PACK_ROOT, common_root=COMMON_ROOT)
    common = load_pack(COMMON_ROOT)
    _validate_pack_contract(pack, common)
    scenarios = validate_scenarios(pack.files)
    lock = _json(pack.files, LOCK_PATH)
    manifest = _json(pack.files, MANIFEST_PATH)
    if pack.files[LOCK_PATH] != document_bytes(lock) or pack.files[MANIFEST_PATH] != document_bytes(manifest):
        raise SystemExit("lock or manifest committed bytes are not canonical")
    validate_lock(pack.files, lock)
    if lock != build_lock(pack.files):
        raise SystemExit("payload lock does not reconstruct exactly")
    validate_manifest(manifest, lock, pack.files[LOCK_PATH])
    if manifest != build_manifest(lock, pack.files[LOCK_PATH]):
        raise SystemExit("artifact manifest does not reconstruct exactly")
    tamper_catalog = validate_tamper_catalog(pack.files)
    tamper_results = verify_tamper_vectors(pack.files, lock, manifest, tamper_catalog["vectors"])

    first_index, second_index = build_index(PACK_ROOT), build_index(PACK_ROOT)
    first_archive, second_archive = archive_bytes(PACK_ROOT), archive_bytes(PACK_ROOT)
    if canonical_json_bytes(first_index) != canonical_json_bytes(second_index) or first_archive != second_archive:
        raise SystemExit("white-goods index or archive is not byte reproducible")
    if first_index["evidence"] != {
        "published": False,
        "runtimeEvidence": False,
        "assuranceEvidence": False,
        "tenantAcceptance": False,
    }:
        raise SystemExit("pack index asserted unavailable evidence")
    print(
        canonical_json_bytes(
            {
                "archiveSha256": _sha256(first_archive[1]),
                "evidence": EVIDENCE_BOUNDARY,
                "frameworkVersion": framework_version,
                "indexSha256": _sha256(canonical_json_bytes(first_index)),
                "manifestSha256": _sha256(pack.files[MANIFEST_PATH]),
                "packDigest": pack.digest,
                "packVersion": pack.manifest["metadata"]["version"],
                "payloadDigest": lock["payloadDigest"],
                "payloadEntryCount": len(lock["entries"]),
                "predecessorBinding": PREDECESSOR_BINDING,
                "retainedArtifacts": False,
                "scenarioCount": len(scenarios),
                "tamperDenials": tamper_results,
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
