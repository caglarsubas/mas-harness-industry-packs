# Banking data readiness

## Scope and evidence boundary

`banking.financial-services` 0.2.0 adds a deterministic, data-only data-readiness slice to the banking business-domain foundation (0.1.0, see `docs/banking/business-domain.md`). It is the banking successor of the historical white-goods data-readiness slice for release scope and replaces the sector inputs of the knowledge packets that consumed that slice. Pack-format compatibility stays `0.1.0`, the framework distribution stays `0.1.1`, and the common pack, contract lock, journey, ontology, business questions and business answer vectors are unchanged.

Everything in this slice is synthetic and illustrative. It holds no tenant, customer, account, employee or transaction record, no institution document, no credential, secret, connection string or endpoint, no production threshold and no regulatory conclusion.

## Data questionnaires

Two questionnaires in the `data-readiness` stage use closed response types only (string, boolean, number, choice):

- `banking.data.sources`: the source classes in scope (`api`, `postgresql`, `events`, `files`), the accountable data owner and the source custodian (each one of the six banking ontology role ids), the approved classification labels, source evidence identifiers, and a confirmation that every bundled example is synthetic.
- `banking.data.readiness-evidence`: the expected observation count, the counts of observations with every required field, of duplicates, of classified observations and of provenanced observations, the latest observation time, measurement evidence identifiers, the cross-source reconciliation confirmation, the readiness-policy evidence identifiers, the deterministic evaluator state, and the tenant's approval of the readiness policy.

The `files` option means:

Synthetic product terms and policy text written for this pack; not an institution document. Each tenant replaces it with its own approved sources.

The pack rule `banking.data.block-unready` blocks readiness while the evaluator state is `warn` or `fail` or the tenant policy is not approved.

## Sources and synthetic data

| Source | Class | Members | Classification |
| --- | --- | --- | --- |
| `banking.source.api` | api | `data/api/product-catalogue.json`: illustrative rates keyed by banking product-family ids | internal-synthetic |
| `banking.source.postgresql` | postgresql | `data/postgresql/parties.csv` (opaque `party-NNNN`, segment, natural-person role or legal entity) and `data/postgresql/accounts.csv` (opaque `acct-NNNN`, holder party, product family, status, opened date) | restricted-synthetic |
| `banking.source.events` | events | `data/events/transactions.jsonl`: opaque `txn-NNNN` and `acct-NNNN` ids, small amounts, currency codes, booking and value times | restricted-synthetic |
| `banking.source.files` | files | `data/files/product-terms.md`: synthetic product terms and policy text | internal-synthetic |

Every source names the domain owner as accountable owner and the data steward as custodian, and carries a stable evidence id. The customer source is the party record only: no member holds a name, address, birth date, national id, phone, e-mail, real account or card number, and no member holds a decimal digit run of thirteen or more digits after removing single spaces and hyphens. Identifiers have four digits, amounts at most seven digits, and times use ISO 8601 with `T` and `:` separators.

`data/dataset.lock.json` binds the five data members by relative path, media type, record count, byte size and SHA-256. Every account holder is a party id and every event's account is an account id; the handler checks that both unresolved counts are zero.

## Illustrative readiness policy

`data/readiness-policy.json` (version 0.2.0, `illustrative: true`, `tenantReplacementRequired: true`) applies FAIL before WARN before PASS and reports `MISSING_DATA` for zero observations. The bands are examples, never production claims; every tenant binds its own approved policy and evidence.

| Class | Label | Completeness min (PASS / WARN) | Freshness max, minutes | Duplicate rate max | Classification min | Provenance min |
| --- | --- | --- | --- | --- | --- | --- |
| events (transactions) | illustrative, tenant-overridable | 0.99 / 0.97 | 5 / 15 | 0.000 / 0.005 | 1.00 / 0.99 | 1.00 / 0.99 |
| postgresql (parties, accounts) | illustrative, tenant-overridable | 1.00 / 0.99 | 1440 / 2880 | 0.000 / 0.001 | 1.00 / 0.99 | 1.00 / 0.99 |
| api (product catalogue) | illustrative, tenant-overridable | 0.98 / 0.95 | 60 / 240 | 0.01 / 0.02 | 1.00 / 0.98 | 1.00 / 0.98 |
| files (product terms) | illustrative, tenant-overridable | 0.95 / 0.90 | 10080 / 43200 | 0.02 / 0.05 | 1.00 / 0.98 | 1.00 / 0.99 |

## Readiness vectors

Each vector names its source class, a fixed evaluation time and measurement counts, and wraps exactly one DataReadinessAssessment with the ten contract gates in order: `business.owner`, `business.outcome`, `data.owner`, `data.quality`, `data.completeness`, `data.freshness`, `data.provenance`, `data.classification`, `integration.readiness`, `autonomy.boundary`. Integration and autonomy are always `NOT_APPLICABLE`. PASS yields READY; WARN yields BLOCKED with `NEEDS_INPUT`; FAIL yields BLOCKED with `BLOCKED`.

| Vector | Class | Decision | Reason codes | missingGateIds |
| --- | --- | --- | --- | --- |
| `pass.json` | events | PASS | none | none |
| `warn-freshness.json` | events | WARN | `FRESHNESS_NEEDS_INPUT` | `data.freshness`, `data.quality` |
| `fail-missing.json` | postgresql | FAIL | `MISSING_DATA` | `data.quality` |
| `fail-stale.json` | events | FAIL | `STALE_DATA` | `data.freshness`, `data.quality` |
| `fail-duplicate.json` | events | FAIL | `DUPLICATE_DATA` | `data.quality` |
| `fail-unclassified.json` | postgresql | FAIL | `UNCLASSIFIED_DATA` | `data.classification`, `data.quality` |
| `fail-unprovenanced.json` | files | FAIL | `UNPROVENANCED_DATA` | `data.provenance`, `data.quality` |
| `fail-reconciliation.json` | postgresql | FAIL | `DATA_RECONCILIATION_MISMATCH` | `data.quality` |
| `fail-disallowed-data.json` | api | FAIL | `PERSONAL_DATA_FORBIDDEN` | `data.classification`, `data.quality` |

Evaluation uses decimal arithmetic and sorted reason codes. With zero observations `MISSING_DATA` is the only reason code, banking codes are not raised and the four metric gates are `NOT_APPLICABLE`. `DATA_RECONCILIATION_MISMATCH` is reported under `data.quality`; `PERSONAL_DATA_FORBIDDEN` sets `data.classification` to `BLOCKED` while keeping the evidence ids of its metric. The disallowed-data vector declares only an in-memory mutation (target member, field and builder name): the handler and the test build the Luhn-valid value from arithmetic at run time, inject it into a copy, and never commit it.

## Contract binding

`data/contract-binding.json` names the public contracts repository by name only (`mas-harness-contracts`, equal to the repository suffix of the byte-copied contract lock), the contracts commit `2146278a95344cd2a8e22596b2f315b46edffc88`, and the paths and SHA-256 values of the DataReadinessAssessment v1alpha1 schema and its guidance schema. The byte-copied contract lock records a historical guidance path for DataReadinessAssessment whose content digest is correct; the binding records this as `DOCUMENTED_NOT_CORRECTED`. No schema bytes are copied.

## Business-answer rule stays in the predecessor

The data-readiness evaluator does not reuse the business-domain answer evaluator. The deferral and role-id rule for business answers stays in the IND-BANK-001 handler's `main()`; IND-BANK-003 and R07's KN-BANK-001 must rely on it there, not on this slice. The data-readiness handler reuses only the predecessor's strict scanner, its Luhn check and its raw-only scan function, loaded by file location under a fixed module name.

## Deferred tenant choices

Source selection, owner and custodian assignment, classification labels, readiness bands, evaluation windows, evidence binding and policy approval are tenant choices. Every bundled value is an example the tenant replaces with its own approved sources, evidence and policy.

## Non-claims

No real tenant, customer, account or transaction data; no production threshold; no regulatory applicability or conclusion; no connection, endpoint or credential; no publication, deployment, runtime, assurance or tenant evidence. Every threshold is illustrative and tenant-replaceable, and every institution-specific choice stays deferred. Source, candidate, CI, merge, artifact, publication, deployment, runtime, assurance and tenant acceptance remain separate evidence states.
