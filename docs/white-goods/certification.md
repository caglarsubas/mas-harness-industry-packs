# White-goods source-certification fixtures

IND-WG-005 closes the pack-local source contract for five synthetic environment
profiles. It does not run a conformance campaign or certify a tenant runtime.

## Scenario matrix

| Scenario | Business | Data | Governance | Provider fixtures |
| --- | --- | --- | --- | --- |
| `minimal-arm64` | accepted pilot | PASS | ready read-only | matching demand and golden envelope |
| `minimal-amd64` | accepted pilot | PASS | ready read-only | matching demand and golden envelope |
| `regulated-openshift` | accepted pilot | PASS | ready reversible write | matching demand and golden envelope |
| `silo` | accepted pilot | PASS | ready read-only | matching demand and golden envelope |
| `air-gap` | accepted pilot | PASS | ready read-only | matching demand and golden envelope |

Each scenario binds every input by repository-relative path and raw SHA-256.
`SOURCE_CONTRACT_READY` means only that the declared synthetic records are
present, internally consistent, and deterministic. Source readiness cannot be
promoted to candidate, CI, merge, artifact, publication, deployment, runtime,
assurance, cross-repository conformance, or tenant acceptance.

## Non-recursive payload lock

`pack.lock.json` lists the seventy final pack files other than itself and
`manifest.json`. Records are sorted by path and bind media type, byte size, raw
SHA-256, and Apache-2.0 disposition. `payloadDigest` is the SHA-256 of canonical
JSON containing only the algorithm, canonicalization identifier, exclusions,
and exact entry list.

The lock intentionally does not store the final pack, index, archive, lock-file,
or manifest-file digest. Those values would create a recursive build subject.
The packet handler computes pack, index, and archive digests as ephemeral
acceptance output and retains no artifact.

## Unsigned source manifest

`manifest.json` binds the exact raw lock bytes, payload digest, entry count,
clean-room packet lineage, and pack license. Its artifact state is
`NOT_RETAINED`. Its signing state is `MISSING_PLANNED`; signature and signer are
null and signing is required before any future publication.

This document is ready to be used as an offline signing subject only after the
source change is merged and independently admitted by a future release process.
IND-WG-005 does not generate a key, create or verify a signature, publish an
artifact, or claim release admission.

## Tamper checks

Acceptance changes only in-memory copies and proves stable denial for:

- changed member bytes;
- a missing member;
- an undeclared member;
- a changed payload digest; and
- a changed manifest-to-lock binding.

No mutation is written back to the pack. All checks run without network access,
runtime downloads, credentials, paid services, remote telemetry, or cloud
resources.
