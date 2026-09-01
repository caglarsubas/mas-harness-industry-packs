#!/usr/bin/env python3
"""Closed IND-WG-004 provider-profile and golden-output acceptance handler."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from planeon_industry_packs import __version__ as framework_version  # noqa: E402
from planeon_industry_packs.canonical import canonical_json_bytes  # noqa: E402
from planeon_industry_packs.index import build_index  # noqa: E402
from planeon_industry_packs.loader import ValidatedPack, load_pack  # noqa: E402
from planeon_industry_packs.package import archive_bytes  # noqa: E402

PACK_ROOT = ROOT / "packs/white-goods"
COMMON_ROOT = ROOT / "common"
PROFILE_PATH = "provider-preferences/profiles.json"
BINDING_PATH = "provider-preferences/contract-binding.json"
OUTPUT_NAMES = (
    "profile.json",
    "bom.json",
    "install-plan.json",
    "evidence-plan.json",
    "explanation.md",
    "profile.sha256",
)
STABLE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
CATALOG_DIGEST = "sha256:26d442c4e90a19d767d32e80ef9df3d154b3146d3238dc0eecf29ee773913a26"
CONTRACTS_COMMIT = "2146278a95344cd2a8e22596b2f315b46edffc88"
COMPILER_SHA256 = "0b0960c87bc1214e795144968db3976bd548c80e6002b03bc3f6e292303a764b"
PREDECESSOR_BINDING = {
    "commit": "219cafc97d89513e89b9f0eaa0349756a2a3954c",
    "packDigest": "798665b769140b621feb0346ab37f32a6804a950b9028f71d921a5b7fc650447",
    "packYamlSha256": "b21aae64acda0eb21eeb63c57aed7458d18926867e1d33e1558f1f492f7ccc67",
    "fileCount": 52,
    "resourceCount": 49,
    "frameworkWheelSha256": "d34a1a3c523b1e60f10602fff072d5dbf83f46f2220f29a4f13b9a31facf91f4",
}
NEW_FILE_SHA256 = {
    "fixtures/demands/air-gap.json": "4f6411b6ea53edb974bc5a5dca801c6979985ba378ca48193d28978f70a93465",
    "fixtures/demands/minimal-amd64.json": "afdeeff6ba418d4c7cad3f4cdf3430ed364b53b9169be07d7fa5ca581a69a8dc",
    "fixtures/demands/minimal-arm64.json": "487ef4f31c118f2e7ecbc7adabfbb11a0b86f7d91cd7234f79439049becfdd7c",
    "fixtures/demands/regulated-openshift.json": "6e3df92e67f4c962ee42f245179098a549179fc4aaa5a9f5db0f9d60bde3f4d5",
    "fixtures/demands/silo.json": "d9caf639e75fe0db29aeb68e063bc490f7eeed5eb60ff8966a745d2abfe0c376",
    "fixtures/expected/air-gap.json": "3d2d663695b758211c3c4753fba55413677e4d73304e0e92fa483e95436c4300",
    "fixtures/expected/minimal-amd64.json": "0363fba5902669fc35711ebf989f16c85a0bdbbb9566acb3a2c73d90c98fb290",
    "fixtures/expected/minimal-arm64.json": "5879ebffaf89d0ed27e8b544db90a295217a701278f6936d5143e134d5674466",
    "fixtures/expected/regulated-openshift.json": "7b1ebb01c56c37882d8180bc323d5a4e71db61e5fce7f415268e8012c10d87b4",
    "fixtures/expected/silo.json": "43d424062e684eed9f99b70bafc7f5542f50cc723a8a5606e3113ca5a989e442",
    BINDING_PATH: "49a20d498196dcb0a4af832ec271d5c0b75d40baff8e6ffc1c9929fd2029a08b",
    PROFILE_PATH: "519b536a06d8b98c4fceb53960b4c40e6d3cccb0f1fca353a48312c76b641575",
}
EVIDENCE_BOUNDARY = {
    "source": True,
    "candidate": False,
    "ci": False,
    "merge": False,
    "artifact": False,
    "publication": False,
    "deployment": False,
    "runtime": False,
    "assurance": False,
    "tenantAcceptance": False,
    "crossRepositoryConformance": False,
}


def _selection(group: str, selector: str, provider: str) -> dict[str, str]:
    return {"groupId": group, "selectorCapability": selector, "providerId": provider}


PROFILE_CONTRACT: dict[str, dict[str, Any]] = {
    "minimal-arm64": {
        "posture": "MINIMAL_LOCAL",
        "requested": ["model.local-cpu", "platform.k3s", "platform.provider.k3s", "provider.planeon.llamacpp"],
        "prerequisites": ["trust.observability-finops", "trust.security-safety"],
        "environment": {
            "deploymentMode": "self-managed",
            "architecture": "arm64",
            "operatingSystem": "linux",
            "kubernetesDistribution": "k3s",
            "capabilities": ["architecture.arm64-available", "connectivity.connected", "tenant.namespace-isolation"],
        },
        "selections": [
            _selection("group.infrastructure-provider", "platform.provider.k3s", "provider.runtime.infrastructure.k3s"),
            _selection("group.model-backend", "provider.planeon.llamacpp", "provider.planeon.llamacpp"),
        ],
        "resources": {"planningClass": "SMALL", "cpuMillicores": 2000, "memoryMiB": 4096, "ephemeralStorageMiB": 8192, "modelStorageMiB": 8192, "capacityAttestationRequired": True},
        "budget": {"maxConcurrentTasks": 1, "maxTaskSeconds": 300, "maxRetries": 1, "maxToolCalls": 12, "maxModelTokens": 32768},
        "isolation": {"boundary": "TENANT_NAMESPACE", "networkPolicy": "DENY_BY_DEFAULT_TENANT_LOCAL_ALLOWLIST", "runtimeDownloadsAllowed": False, "externalTelemetryAllowed": False, "artifactSource": "TENANT_SUPPLIED_DIGEST_PINNED"},
    },
    "minimal-amd64": {
        "posture": "MINIMAL_LOCAL",
        "requested": ["deployment.kubernetes", "model.local-cpu", "platform.provider.kubernetes-upstream", "provider.planeon.llamacpp"],
        "prerequisites": ["trust.observability-finops", "trust.security-safety"],
        "environment": {
            "deploymentMode": "self-managed",
            "architecture": "amd64",
            "operatingSystem": "linux",
            "kubernetesDistribution": "upstream",
            "capabilities": ["architecture.amd64-available", "connectivity.connected", "tenant.namespace-isolation"],
        },
        "selections": [
            _selection("group.infrastructure-provider", "platform.provider.kubernetes-upstream", "provider.runtime.infrastructure.kubernetes-upstream"),
            _selection("group.model-backend", "provider.planeon.llamacpp", "provider.planeon.llamacpp"),
        ],
        "resources": {"planningClass": "SMALL", "cpuMillicores": 4000, "memoryMiB": 8192, "ephemeralStorageMiB": 16384, "modelStorageMiB": 16384, "capacityAttestationRequired": True},
        "budget": {"maxConcurrentTasks": 2, "maxTaskSeconds": 300, "maxRetries": 1, "maxToolCalls": 16, "maxModelTokens": 65536},
        "isolation": {"boundary": "TENANT_NAMESPACE", "networkPolicy": "DENY_BY_DEFAULT_TENANT_LOCAL_ALLOWLIST", "runtimeDownloadsAllowed": False, "externalTelemetryAllowed": False, "artifactSource": "TENANT_SUPPLIED_DIGEST_PINNED"},
    },
    "regulated-openshift": {
        "posture": "REGULATED_POLICY",
        "requested": ["agent.governed-action", "assurance.required", "model.local-cpu", "platform.openshift", "platform.provider.openshift", "provider.planeon.llamacpp"],
        "prerequisites": ["trust.governance-agentops", "trust.observability-finops", "trust.security-safety"],
        "environment": {
            "deploymentMode": "self-managed",
            "architecture": "amd64",
            "operatingSystem": "linux",
            "kubernetesDistribution": "openshift",
            "capabilities": ["architecture.amd64-available", "connectivity.connected", "platform.openshift.arbitrary-uid", "tenant.namespace-isolation"],
        },
        "selections": [
            _selection("group.infrastructure-provider", "platform.provider.openshift", "provider.runtime.infrastructure.openshift"),
            _selection("group.model-backend", "provider.planeon.llamacpp", "provider.planeon.llamacpp"),
        ],
        "resources": {"planningClass": "MEDIUM", "cpuMillicores": 8000, "memoryMiB": 16384, "ephemeralStorageMiB": 32768, "modelStorageMiB": 32768, "capacityAttestationRequired": True},
        "budget": {"maxConcurrentTasks": 4, "maxTaskSeconds": 600, "maxRetries": 1, "maxToolCalls": 24, "maxModelTokens": 131072},
        "isolation": {"boundary": "TENANT_NAMESPACE_ARBITRARY_UID", "networkPolicy": "DENY_ALL_EXCEPT_TENANT_APPROVED_CLUSTER_LOCAL", "runtimeDownloadsAllowed": False, "externalTelemetryAllowed": False, "artifactSource": "TENANT_SUPPLIED_DIGEST_PINNED"},
    },
    "silo": {
        "posture": "TENANT_SILO",
        "requested": ["agent.read-only", "deployment.kubernetes", "model.local-cpu", "platform.provider.kubernetes-upstream", "provider.planeon.llamacpp", "retrieval.cited"],
        "prerequisites": ["knowledge.data-integration", "knowledge.domain-semantic", "trust.governance-agentops", "trust.observability-finops", "trust.security-safety"],
        "environment": {
            "deploymentMode": "self-managed",
            "architecture": "amd64",
            "operatingSystem": "linux",
            "kubernetesDistribution": "upstream",
            "capabilities": ["architecture.amd64-available", "connectivity.connected", "connectivity.silo", "tenant.namespace-isolation"],
        },
        "selections": [
            _selection("group.infrastructure-provider", "platform.provider.kubernetes-upstream", "provider.runtime.infrastructure.kubernetes-upstream"),
            _selection("group.model-backend", "provider.planeon.llamacpp", "provider.planeon.llamacpp"),
        ],
        "resources": {"planningClass": "MEDIUM", "cpuMillicores": 8000, "memoryMiB": 16384, "ephemeralStorageMiB": 32768, "modelStorageMiB": 32768, "capacityAttestationRequired": True},
        "budget": {"maxConcurrentTasks": 4, "maxTaskSeconds": 600, "maxRetries": 2, "maxToolCalls": 24, "maxModelTokens": 131072},
        "isolation": {"boundary": "TENANT_NAMESPACE", "networkPolicy": "TENANT_SILO_ALLOWLIST_ONLY", "runtimeDownloadsAllowed": False, "externalTelemetryAllowed": False, "artifactSource": "TENANT_SUPPLIED_DIGEST_PINNED"},
    },
    "air-gap": {
        "posture": "AIR_GAPPED",
        "requested": ["deployment.airgap", "model.local-cpu", "platform.k3s", "platform.provider.k3s", "provider.planeon.llamacpp"],
        "prerequisites": ["trust.observability-finops", "trust.security-safety"],
        "environment": {
            "deploymentMode": "air-gapped",
            "architecture": "amd64",
            "operatingSystem": "linux",
            "kubernetesDistribution": "k3s",
            "capabilities": ["architecture.amd64-available", "connectivity.airgap", "tenant.namespace-isolation"],
        },
        "selections": [
            _selection("group.infrastructure-provider", "platform.provider.k3s", "provider.runtime.infrastructure.k3s"),
            _selection("group.model-backend", "provider.planeon.llamacpp", "provider.planeon.llamacpp"),
        ],
        "resources": {"planningClass": "MEDIUM", "cpuMillicores": 4000, "memoryMiB": 8192, "ephemeralStorageMiB": 32768, "modelStorageMiB": 32768, "capacityAttestationRequired": True},
        "budget": {"maxConcurrentTasks": 2, "maxTaskSeconds": 600, "maxRetries": 1, "maxToolCalls": 16, "maxModelTokens": 65536},
        "isolation": {"boundary": "TENANT_NAMESPACE", "networkPolicy": "DENY_ALL_OUTBOUND", "runtimeDownloadsAllowed": False, "externalTelemetryAllowed": False, "artifactSource": "TENANT_LOCAL_OCI_LAYOUT_OR_REGISTRY_DIGEST_PINNED"},
    },
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def compiler_json_bytes(value: Any) -> bytes:
    """Reconstruct the bound compiler's trailing-newline canonical JSON."""

    return canonical_json_bytes(value) + b"\n"


def _json(pack: ValidatedPack, path: str) -> dict[str, Any]:
    value = json.loads(pack.files[path])
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def _require_fields(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} fields differ")
    return value


def _require_stable(value: Any, label: str) -> str:
    if not isinstance(value, str) or STABLE_ID.fullmatch(value) is None:
        raise ValueError(f"{label} is not a stable id")
    return value


def _attestation_digest(environment: dict[str, Any]) -> str:
    payload = {
        key: environment[key]
        for key in (
            "tenantId",
            "deploymentMode",
            "architecture",
            "operatingSystem",
            "kubernetesDistribution",
            "capabilities",
        )
    }
    return "sha256:" + _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def validate_contract_binding(value: dict[str, Any]) -> None:
    _require_fields(
        value,
        {
            "apiVersion", "kind", "id", "stage", "repository", "commit",
            "releaseManifestSha256", "compiler", "catalog", "schemas",
            "schemaBytesCopied", "compilerBytesCopied", "catalogBytesCopied",
            "upstreamPathRequiredAtAcceptance", "crossRepositoryConformanceClaimed",
        },
        "contract binding",
    )
    if (
        value["apiVersion"] != "harness.planeon.ai/industry-provider-contract-binding/v1alpha1"
        or value["kind"] != "IndustryProviderContractBinding"
        or value["id"] != "white-goods.providers.contract-binding"
        or value["stage"] != "environment-and-provider-fit"
        or value["repository"] != "caglarsubas/mas-harness-contracts"
        or value["commit"] != CONTRACTS_COMMIT
        or value["compiler"]["sha256"] != COMPILER_SHA256
        or value["compiler"]["outputNames"] != list(OUTPUT_NAMES)
        or value["compiler"]["canonicalization"] != "SORTED_UTF8_JSON_V1"
        or value["catalog"]["catalogDigest"] != CATALOG_DIGEST
    ):
        raise ValueError("public compiler binding differs")
    false_fields = (
        "schemaBytesCopied", "compilerBytesCopied", "catalogBytesCopied",
        "upstreamPathRequiredAtAcceptance", "crossRepositoryConformanceClaimed",
    )
    if any(value[field] is not False for field in false_fields):
        raise ValueError("contract binding asserts copied bytes or conformance")
    if len(value["schemas"]) != 12:
        raise ValueError("schema binding inventory differs")
    for binding in value["schemas"].values():
        if set(binding) != {"path", "sha256"} or not re.fullmatch(r"[0-9a-f]{64}", binding["sha256"]):
            raise ValueError("schema binding is not closed")


def validate_profile_catalog(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    _require_fields(
        value,
        {"apiVersion", "kind", "id", "stage", "version", "recommendationDisposition", "tenantExplicitAcceptanceRequired", "implicitFallbackAllowed", "profiles"},
        "profile catalog",
    )
    if (
        value["apiVersion"] != "harness.planeon.ai/industry-provider-profile-catalog/v1alpha1"
        or value["kind"] != "IndustryProviderProfileCatalog"
        or value["id"] != "white-goods.providers.profiles"
        or value["stage"] != "environment-and-provider-fit"
        or value["version"] != "0.4.0"
        or value["recommendationDisposition"] != "PROPOSED_SELECTOR_ONLY"
        or value["tenantExplicitAcceptanceRequired"] is not True
        or value["implicitFallbackAllowed"] is not False
    ):
        raise ValueError("profile catalog authority differs")
    profiles = value["profiles"]
    if not isinstance(profiles, list) or len(profiles) != 5:
        raise ValueError("profile inventory differs")
    by_slug: dict[str, dict[str, Any]] = {}
    fields = {
        "id", "profileId", "displayName", "posture", "disposition", "demandPath",
        "expectedOutputEnvelopePath", "environment", "recommendations",
        "acceptedSelections", "requestedCapabilities", "acceptedPrerequisiteHarnessIds",
        "expectedSelectedHarnessIds", "expectedSelectedModuleIds",
        "expectedSelectedProviderIds", "resourceEnvelope", "executionBudget",
        "isolationRequirements", "exclusions", "explanation",
    }
    for profile in profiles:
        _require_fields(profile, fields, "profile")
        profile_id = _require_stable(profile["id"], "profile id")
        prefix = "white-goods.providers.profile."
        if not profile_id.startswith(prefix):
            raise ValueError("profile id prefix differs")
        slug = profile_id.removeprefix(prefix)
        if slug in by_slug or slug not in PROFILE_CONTRACT:
            raise ValueError("profile slug is unknown or duplicated")
        contract = PROFILE_CONTRACT[slug]
        expected_environment = {"tenantId": f"tenant.white-goods-{slug}", **contract["environment"]}
        if (
            profile["profileId"] != f"profile.white-goods-{slug}"
            or profile["posture"] != contract["posture"]
            or profile["disposition"] != "PROPOSED_SELECTOR_ONLY"
            or profile["demandPath"] != f"fixtures/demands/{slug}.json"
            or profile["expectedOutputEnvelopePath"] != f"fixtures/expected/{slug}.json"
            or profile["environment"] != expected_environment
            or profile["requestedCapabilities"] != contract["requested"]
            or profile["acceptedPrerequisiteHarnessIds"] != contract["prerequisites"]
            or profile["acceptedSelections"] != contract["selections"]
            or profile["expectedSelectedProviderIds"] != sorted(item["providerId"] for item in contract["selections"])
            or profile["resourceEnvelope"] != contract["resources"]
            or profile["executionBudget"] != contract["budget"]
            or profile["isolationRequirements"] != contract["isolation"]
        ):
            raise ValueError(f"profile contract differs: {slug}")
        recommendations = profile["recommendations"]
        if len(recommendations) != 2:
            raise ValueError("each profile requires two provider recommendations")
        normalized = []
        for recommendation in recommendations:
            _require_fields(
                recommendation,
                {"groupId", "selectorCapability", "providerId", "disposition", "releaseStatus", "providerCredentialsRequired", "externalTelemetry", "runtimeDownloadsAllowed"},
                "provider recommendation",
            )
            if (
                recommendation["disposition"] != "PROPOSED_SELECTOR_ONLY"
                or recommendation["releaseStatus"] != "PLANNED"
                or recommendation["providerCredentialsRequired"] is not False
                or recommendation["externalTelemetry"] is not False
                or recommendation["runtimeDownloadsAllowed"] is not False
            ):
                raise ValueError("provider recommendation violates no-bill planning boundary")
            normalized.append({key: recommendation[key] for key in ("groupId", "selectorCapability", "providerId")})
        if normalized != contract["selections"]:
            raise ValueError("recommendation and explicit selection differ")
        if profile["exclusions"] != [
            "AUTOMATIC_SELECTOR_ACCEPTANCE", "CLOUD_PROVISIONING", "EXTERNAL_TELEMETRY",
            "FABRICATED_ARTIFACT_DIGEST", "PAID_PROVIDER", "RUNTIME_DOWNLOAD",
        ]:
            raise ValueError("profile exclusions differ")
        if not profile["explanation"]:
            raise ValueError("profile explanation is empty")
        by_slug[slug] = profile
    if set(by_slug) != set(PROFILE_CONTRACT):
        raise ValueError("profile set differs")
    return by_slug


def validate_demand(slug: str, profile: dict[str, Any], request: dict[str, Any]) -> None:
    _require_fields(request, {"schemaVersion", "metadata", "questionnaireAnswerSet", "readinessAssessment", "demand"}, "compile request")
    if request["schemaVersion"] != "harness.planeon.ai/compile-request/v1alpha1":
        raise ValueError("compile request version differs")
    metadata = request["metadata"]
    expected_ids = {
        "tenantId": f"tenant.white-goods-{slug}",
        "demandId": f"demand.white-goods-{slug}",
        "profileId": f"profile.white-goods-{slug}",
        "version": "0.4.0",
    }
    if metadata != expected_ids:
        raise ValueError("compile request metadata differs")
    demand = request["demand"]
    _require_fields(demand, {"requestedCapabilities", "acceptedPrerequisiteHarnessIds", "environment", "assuranceSubjects", "executionBudget"}, "demand")
    if (
        demand["requestedCapabilities"] != profile["requestedCapabilities"]
        or demand["acceptedPrerequisiteHarnessIds"] != profile["acceptedPrerequisiteHarnessIds"]
        or demand["executionBudget"] != profile["executionBudget"]
        or demand["assuranceSubjects"] != {"harnessIds": [], "capabilityIds": []}
    ):
        raise ValueError("demand selection, prerequisites, subjects, or budget differs")
    environment = demand["environment"]
    _require_fields(environment, {"tenantId", "deploymentMode", "architecture", "operatingSystem", "kubernetesDistribution", "capabilities", "attestationDigest", "signatureStatus"}, "environment")
    if (
        {key: environment[key] for key in profile["environment"]} != profile["environment"]
        or environment["attestationDigest"] != _attestation_digest(environment)
        or environment["signatureStatus"] != "VERIFIED"
    ):
        raise ValueError("synthetic environment attestation fixture differs")
    answers = request["questionnaireAnswerSet"]
    readiness = request["readinessAssessment"]
    if answers["kind"] != "QuestionnaireAnswerSet" or readiness["kind"] != "DataReadinessAssessment":
        raise ValueError("embedded guidance kinds differ")
    if answers["spec"]["status"] != "SUBMITTED" or readiness["spec"]["overallStatus"] != "READY":
        raise ValueError("guidance is not submitted and ready")
    if answers["spec"]["questionnaireSessionId"] != readiness["spec"]["questionnaireSessionId"]:
        raise ValueError("guidance session differs")
    answer_map = {item["questionId"]: item["value"] for item in answers["spec"]["answers"]}
    if len(answer_map) != len(answers["spec"]["answers"]):
        raise ValueError("duplicate answer id")
    selector_values = sorted(item["selectorCapability"] for item in profile["acceptedSelections"])
    if (
        answer_map.get("question.selectors-explicitly-accepted") is not True
        or sorted((answer_map.get("question.infrastructure-selector"), answer_map.get("question.model-provider"))) != selector_values
        or answer_map.get("question.requested-capabilities") != profile["requestedCapabilities"]
        or answer_map.get("question.accepted-prerequisites") != profile["acceptedPrerequisiteHarnessIds"]
    ):
        raise ValueError("questionnaire does not explicitly accept exact selectors")
    gates = readiness["spec"]["gateResults"]
    if len(gates) != 10 or readiness["spec"]["missingGateIds"] != []:
        raise ValueError("readiness gate inventory differs")
    if any(gate["status"] != "PASS" or len(gate["evidenceIds"]) != 1 for gate in gates):
        raise ValueError("readiness fixture is not fully evidenced")


def compile_request_from_fixture(slug: str, value: dict[str, Any]) -> dict[str, Any]:
    _require_fields(value, {"apiVersion", "kind", "id", "stage", "synthetic", "compileRequest"}, "demand fixture")
    if (
        value["apiVersion"] != "harness.planeon.ai/industry-provider-demand-fixture/v1alpha1"
        or value["kind"] != "IndustryProviderDemandFixture"
        or value["id"] != f"white-goods.providers.demand.{slug}"
        or value["stage"] != "environment-and-provider-fit"
        or value["synthetic"] is not True
        or not isinstance(value["compileRequest"], dict)
    ):
        raise ValueError("demand fixture identity differs")
    return value["compileRequest"]


def reconstruct_outputs(envelope: dict[str, Any]) -> dict[str, bytes]:
    _require_fields(envelope, {"apiVersion", "kind", "id", "stage", "synthetic", "compileRequestPath", "contractsCommit", "compilerSha256", "catalogDigest", "canonicalization", "outputNames", "outputs", "evidenceBoundary"}, "golden envelope")
    if (
        envelope["apiVersion"] != "harness.planeon.ai/industry-provider-golden-output-envelope/v1alpha1"
        or envelope["kind"] != "IndustryProviderGoldenOutputEnvelope"
        or envelope["stage"] != "evidence-and-acceptance"
        or envelope["synthetic"] is not True
        or envelope["contractsCommit"] != CONTRACTS_COMMIT
        or envelope["compilerSha256"] != COMPILER_SHA256
        or envelope["catalogDigest"] != CATALOG_DIGEST
        or envelope["canonicalization"] != "SORTED_UTF8_JSON_V1"
        or envelope["outputNames"] != list(OUTPUT_NAMES)
    ):
        raise ValueError("golden envelope authority differs")
    if envelope["evidenceBoundary"] != {
        "sourceContract": True, "candidate": False, "ci": False, "merge": False,
        "artifact": False, "publication": False, "deployment": False,
        "runtime": False, "assurance": False, "tenantAcceptance": False,
        "crossRepositoryConformance": False,
    }:
        raise ValueError("golden envelope escalates evidence")
    records = envelope["outputs"]
    if set(records) != set(OUTPUT_NAMES):
        raise ValueError("golden output set differs")
    outputs: dict[str, bytes] = {}
    for name in OUTPUT_NAMES:
        record = records[name]
        if name.endswith(".json"):
            _require_fields(record, {"mediaType", "sha256", "value"}, f"golden {name}")
            if record["mediaType"] != "application/json":
                raise ValueError("golden JSON media type differs")
            content = compiler_json_bytes(record["value"])
        else:
            _require_fields(record, {"mediaType", "sha256", "text"}, f"golden {name}")
            expected_media = "text/markdown" if name.endswith(".md") else "text/plain"
            if record["mediaType"] != expected_media or not isinstance(record["text"], str):
                raise ValueError("golden text media type differs")
            content = record["text"].encode("utf-8")
        if not isinstance(record["sha256"], str) or SHA256.fullmatch(record["sha256"]) is None:
            raise ValueError("golden digest shape differs")
        if record["sha256"] != "sha256:" + _sha256(content):
            raise ValueError(f"golden digest differs: {name}")
        outputs[name] = content
    return outputs


def validate_golden(slug: str, profile: dict[str, Any], envelope: dict[str, Any]) -> dict[str, str]:
    if (
        envelope["id"] != f"white-goods.providers.golden.{slug}"
        or envelope["compileRequestPath"] != profile["demandPath"]
    ):
        raise ValueError("golden envelope identity differs")
    first = reconstruct_outputs(envelope)
    second = reconstruct_outputs(json.loads(json.dumps(envelope)))
    if first != second:
        raise ValueError("golden reconstruction is not byte-identical")
    expected_profile_sha = "sha256:" + _sha256(first["profile.json"]) + "\n"
    if first["profile.sha256"].decode("ascii") != expected_profile_sha:
        raise ValueError("profile.sha256 does not bind exact profile bytes")
    profile_document = json.loads(first["profile.json"])
    compiled_profile = profile_document["profile"]
    spec = compiled_profile["spec"]
    if (
        spec["state"] != "PLANNED"
        or spec["catalogDigest"] != CATALOG_DIGEST
        or spec["requestedCapabilities"] != profile["requestedCapabilities"]
        or spec["acceptedPrerequisiteHarnessIds"] != profile["acceptedPrerequisiteHarnessIds"]
        or spec["providerSelections"] != profile["acceptedSelections"]
        or spec["selectedHarnessIds"] != profile["expectedSelectedHarnessIds"]
        or spec["selectedModuleIds"] != profile["expectedSelectedModuleIds"]
        or spec["selectedProviderIds"] != profile["expectedSelectedProviderIds"]
    ):
        raise ValueError("compiled profile closure differs")
    if any(proposal["disposition"] != "PROPOSED_SELECTOR_ONLY" for proposal in spec["proposedSelectors"]):
        raise ValueError("compiler proposal became a selection")
    if {item["groupId"] for item in spec["providerSelections"]} != {"group.infrastructure-provider", "group.model-backend"}:
        raise ValueError("active provider groups are incomplete or ambiguous")
    if profile_document["tenantDemand"]["spec"]["executionBudget"] != profile["executionBudget"]:
        raise ValueError("compiled execution budget differs")
    if profile_document["executionBudget"]["spec"] != {
        **profile["executionBudget"], "enforcement": "REQUIRED", "overflowDisposition": "BLOCK"
    }:
        raise ValueError("execution budget enforcement differs")
    bom = json.loads(first["bom.json"])
    entries = bom["spec"]["entries"]
    expected_resources = set(profile["expectedSelectedModuleIds"]) | set(profile["expectedSelectedProviderIds"])
    if bom["spec"]["state"] != "PLANNED" or {item["resourceId"] for item in entries} != expected_resources:
        raise ValueError("BOM contains an unselected or missing resource")
    for entry in entries:
        expected_kind = "MODULE" if entry["resourceId"] in profile["expectedSelectedModuleIds"] else "PROVIDER"
        if entry["resourceKind"] != expected_kind or not entry["installUnits"]:
            raise ValueError("BOM resource kind or install-unit inventory differs")
        for unit in entry["installUnits"]:
            if unit["digestStatus"] != "MISSING_PLANNED" or unit["digest"] is not None:
                raise ValueError("BOM fabricates an artifact digest")
    install = json.loads(first["install-plan.json"])
    wave_resources = [resource_id for wave in install["spec"]["waves"] for resource_id in wave["resourceIds"]]
    if install["spec"]["state"] != "PLANNED" or len(wave_resources) != len(set(wave_resources)) or set(wave_resources) != expected_resources:
        raise ValueError("install plan contains an unselected, missing, or duplicate resource")
    evidence = json.loads(first["evidence-plan.json"])
    evidence_harnesses = [item["harnessId"] for item in evidence["spec"]["harnessRequirements"]]
    if (
        evidence["spec"]["state"] != "PLANNED"
        or evidence["spec"]["evidenceState"] != "MISSING_PLANNED"
        or evidence["spec"]["tenantAcceptanceIncluded"] is not False
        or evidence_harnesses != profile["expectedSelectedHarnessIds"]
    ):
        raise ValueError("evidence plan escalates or differs from selected harnesses")
    return {name: "sha256:" + _sha256(content) for name, content in first.items()}


def validate_pack_contract(pack: ValidatedPack, common: ValidatedPack) -> None:
    if pack.manifest["metadata"]["version"] != "0.5.0":
        raise ValueError("white-goods pack version differs")
    if pack.manifest["compatibility"]["frameworkVersion"] != "0.1.0":
        raise ValueError("pack format compatibility differs")
    if common.manifest["metadata"]["version"] != "1.0.0" or pack.manifest["extends"]["packDigest"] != common.digest:
        raise ValueError("common foundation binding differs")
    if len(pack.files) != 72 or len(pack.resource_ids) != 69:
        raise ValueError("white-goods file or resource inventory differs")
    for path, digest in NEW_FILE_SHA256.items():
        if _sha256(pack.files[path]) != digest:
            raise ValueError(f"IND-WG-004 data bytes changed: {path}")


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["white-goods"]:
        raise SystemExit("IND-WG-004 accepts only PACK=white-goods")
    if framework_version != "0.1.1":
        raise SystemExit(f"framework version differs: {framework_version}")
    pack = load_pack(PACK_ROOT, common_root=COMMON_ROOT)
    common = load_pack(COMMON_ROOT)
    validate_pack_contract(pack, common)
    binding = _json(pack, BINDING_PATH)
    validate_contract_binding(binding)
    profiles = validate_profile_catalog(_json(pack, PROFILE_PATH))
    demand_digests: dict[str, str] = {}
    golden_digests: dict[str, dict[str, str]] = {}
    for slug, profile in sorted(profiles.items()):
        demand_fixture = _json(pack, profile["demandPath"])
        demand = compile_request_from_fixture(slug, demand_fixture)
        validate_demand(slug, profile, demand)
        demand_digests[slug] = _sha256(canonical_json_bytes(demand_fixture))
        envelope = _json(pack, profile["expectedOutputEnvelopePath"])
        golden_digests[slug] = validate_golden(slug, profile, envelope)
    first_index, second_index = build_index(PACK_ROOT), build_index(PACK_ROOT)
    first_archive, second_archive = archive_bytes(PACK_ROOT), archive_bytes(PACK_ROOT)
    if canonical_json_bytes(first_index) != canonical_json_bytes(second_index) or first_archive != second_archive:
        raise SystemExit("white-goods index or archive is not byte reproducible")
    if first_index["evidence"] != {"published": False, "runtimeEvidence": False, "assuranceEvidence": False, "tenantAcceptance": False}:
        raise SystemExit("pack index asserted unavailable evidence")
    print(
        canonical_json_bytes(
            {
                "archiveSha256": _sha256(first_archive[1]),
                "bindingSha256": _sha256(canonical_json_bytes(binding)),
                "demandDigests": demand_digests,
                "evidence": EVIDENCE_BOUNDARY,
                "frameworkVersion": framework_version,
                "goldenDigests": golden_digests,
                "indexSha256": _sha256(canonical_json_bytes(first_index)),
                "packDigest": pack.digest,
                "packVersion": pack.manifest["metadata"]["version"],
                "predecessorBinding": PREDECESSOR_BINDING,
                "profileCount": len(profiles),
                "retainedArtifacts": False,
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
