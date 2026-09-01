# White-goods data-readiness slice

IND-WG-002 extends the white-goods sector pack from 0.1.0 to 0.2.0 without
changing `common.foundation`, the contracts lock, the eight-stage journey, the
business/domain ontology, framework format 0.1.0, or framework distribution
0.1.1. This slice is guidance and deterministic fixture evidence. It does not
connect to a source, process tenant data, publish an artifact, deploy a service,
or assert runtime, assurance, or tenant acceptance.

## Contract authority

The data-only binding record pins public contracts commit
`2146278a95344cd2a8e22596b2f315b46edffc88`. The authoritative
`DataReadinessAssessment` path is
`schemas/v1alpha1/readiness/data-readiness-assessment.schema.json`, SHA-256
`ffe003a1a7ec0773f49d8f394ac3dd6281114bd4335ff05c87d223412faf92a5`.
The common guidance schema is pinned at SHA-256
`4d77297073d4c2e559f1131fbada566b499197f87113f7e28b136f0b4ae5f429`.

The inherited lock contains the same readiness-schema content digest under a
historical `guidance/` path. Because sector packs must retain that lock byte for
byte, this slice records the authoritative path separately and marks the
observation `DOCUMENTED_NOT_CORRECTED`. No schema bytes are copied into the pack.

## Guided questions and source inventory

The setup journey asks for source classes, accountable data owner and custodian
roles, approved classification scope, local evidence identifiers, fixed-scope
counts, observation timing, the deterministic evaluator result, and tenant
approval of the policy used. The questionnaire never asks for data values,
credentials, connection strings, source locations, or production identities.

The bundled source inventory is synthetic and closed to four representative
classes:

| Class | Example format | Accountable owner | Custodian |
|---|---|---|---|
| API | local JSON observations | quality owner | data steward |
| events | local JSONL observations | quality owner | data steward |
| files | local Markdown inspection note | quality owner | data steward |
| PostgreSQL | local CSV-shaped observations | quality owner | data steward |

Each source has classification `internal-synthetic` and one stable local
evidence identifier. `dataset.lock.json` binds the four representative data
members by path, media type, record count, byte size, and SHA-256. A byte, count,
path, type, owner, classification, or evidence-id change fails acceptance.

## Illustrative policy

These thresholds exist only to make the pack and failure vectors deterministic.
They are not production advice and every tenant must replace them with an
approved, evidence-bound policy.

| Metric | PASS | WARN | FAIL |
|---|---:|---:|---:|
| completeness | at least 0.98 | 0.95 through below 0.98 | below 0.95 |
| freshness age | at most 15 minutes | above 15 through 60 | above 60 |
| duplicate rate | at most 0.01 | above 0.01 through 0.02 | above 0.02 |
| classification coverage | 1.00 | 0.98 through below 1.00 | below 0.98 |
| provenance coverage | 1.00 | 0.98 through below 1.00 | below 0.98 |

Zero observed records always produce only `MISSING_DATA`. Derived completeness,
freshness, provenance, and classification findings become `NOT_APPLICABLE` in
that vector, avoiding false conclusions from absent observations. FAIL dominates
WARN, and WARN never advances readiness.

## Assessment and evidence states

Each of the seven vectors contains a nested public
`DataReadinessAssessment`: PASS, WARN freshness, missing, stale, duplicate,
unclassified, and unprovenanced. Each assessment has exactly ten gates, in the
public contract order. Evidence ids, reason codes, and missing-gate ids are
stable; missing-gate ids are sorted and agree with every `NEEDS_INPUT` or
`BLOCKED` gate.

PASS alone sets `overallStatus: READY`. WARN uses `NEEDS_INPUT` and
`overallStatus: BLOCKED`; FAIL uses `BLOCKED`. Integration and autonomy remain
`NOT_APPLICABLE` because this packet does not authorize either. Publication,
deployment, runtime, assurance, and tenant-acceptance evidence remain false.

## Offline acceptance

The packet registers the unique `data-readiness` Make target. The handler checks
the contract pins, questionnaire and policy closure, source inventory, dataset
digests/counts, every fixture decision, every ten-gate assessment, and two-build
index/archive identity in memory. It retains no artifact and performs no network
or warm-source access.
