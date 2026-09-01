# White-goods provider profiles

IND-WG-004 adds five deterministic, recommendation-only environment profiles
to white-goods pack 0.4.0. They help a tenant translate submitted questionnaire
answers into explicit provider selectors; they do not provision a cluster,
install an artifact, rank a provider into a profile, or assert that capacity or
compliance exists.

## Selection boundary

Every active provider group has two distinct states:

1. Compatible catalog members are shown as `PROPOSED_SELECTOR_ONLY`.
2. Compilation proceeds only after the submitted tenant demand contains exactly
   one accepted selector for the infrastructure group and one for the local
   model-backend group.

There is no default, fallback, or automatic acceptance. A missing, incompatible,
surplus, or ambiguous selector fails closed. Every selected catalog record is
still `PLANNED`; install-unit digests remain `MISSING_PLANNED`.

## Profile map

| Profile | Environment | Accepted selectors | Planning envelope |
| --- | --- | --- | --- |
| Minimal ARM64 | self-managed ARM64 Linux/K3s | K3s, llama.cpp | 2 CPU cores, 4 GiB memory, 8 GiB ephemeral and model storage |
| Minimal AMD64 | self-managed AMD64 Linux/upstream Kubernetes | upstream Kubernetes, llama.cpp | 4 CPU cores, 8 GiB memory, 16 GiB ephemeral and model storage |
| Regulated OpenShift | self-managed AMD64 Linux/OpenShift | OpenShift, llama.cpp | 8 CPU cores, 16 GiB memory, 32 GiB ephemeral and model storage |
| Silo | self-managed AMD64 Linux/upstream Kubernetes | upstream Kubernetes, llama.cpp | 8 CPU cores, 16 GiB memory, 32 GiB ephemeral and model storage |
| Air gap | air-gapped AMD64 Linux/K3s | K3s, llama.cpp | 4 CPU cores, 8 GiB memory, 32 GiB ephemeral and model storage |

These are planning minima, not discovered capacity. The tenant must replace
them with a signed capacity attestation before any deployment admission.
Regulated OpenShift is a governance posture and does not claim legal or
regulatory compliance.

The released compiler currently requires `connectivity.connected` for every
non-air-gap request. The silo fixture therefore carries both that admission fact
and the narrower signed `connectivity.silo` fact. Air-gap carries only
`connectivity.airgap`, denies all outbound traffic, disables runtime downloads
and external telemetry, and requires a tenant-supplied digest-pinned local OCI
layout or registry.

## Files and deterministic evidence

- `provider-preferences/contract-binding.json` pins the exact public contracts
  commit, compiler, schemas, catalog lock, and catalog entry digests without
  copying upstream bytes.
- `provider-preferences/profiles.json` contains the five recommendation records,
  resource envelopes, isolation requirements, accepted selections, and
  expected harness/module/provider closures.
- `fixtures/demands/*.json` are synthetic full `CompileRequest` documents with
  submitted answers, ten passing readiness gates, explicit prerequisites,
  environment facts, and bounded execution budgets.
- `fixtures/expected/*.json` are closed envelopes for the exact six public
  compiler outputs and their SHA-256 values.

The profile handler reconstructs every golden output twice in memory using
`SORTED_UTF8_JSON_V1`, compares exact bytes and digests, binds
`profile.sha256`, and ensures BOM and install waves contain only selected
modules and providers. It does not import or run the upstream compiler during
product acceptance. This evidence is a pack-local source-contract lock, not
cross-repository conformance, an artifact release, publication, deployment,
runtime behavior, assurance, or tenant acceptance.

## No-bill and air-gap rules

The profiles require no cloud provisioning, paid provider, API key, credential,
external telemetry, remote font or asset, runtime download, hosted runner, or
mutable artifact. Infrastructure is tenant-supplied and model backends are
self-hosted open-source/non-metered. All verification runs through the pinned
credential-free self-hosted offline launcher with OS-enforced deny-all outbound.
