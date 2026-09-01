# White-goods business-domain foundation

## Scope and evidence boundary

`white-goods.manufacturing` is a clean-room, data-only sector overlay on the exact `common.foundation` 1.0.0 pack. It guides a tenant through a bounded business and domain definition before any data integration, model, agent, tool, runtime, or production action is selected. The pack contains no plant identity, production value, real threshold, personal or customer record, credential, remote endpoint, model prompt, regulatory conclusion, or write-capable action.

All included answer and RDF fixtures are synthetic. They cannot prove publication, deployment, runtime operation, assurance, or tenant acceptance. Every such evidence flag remains `false`; an accepted business-domain pilot means only that this setup slice is internally complete enough to proceed to the next evidence-gated step.

Historical `sourceReuse` records in IND-WG-001 are provenance and clean-room parity requirements only. No warm-source checkout was observed, mounted, copied, translated, adapted, or supplied to product execution.

## Guided business questionnaire

The three questionnaires bind a tenant declaration to a closed vocabulary:

- accountable business, domain, quality, data-steward, and evidence-approver roles, plus explicit role-separation review;
- one primary measurable objective and explicit product-family, manufacturing-process, CTQ, and KPI scopes;
- a decision boundary, an unacceptable outcome, a business-domain outcome, local evidence identifiers, and any plant-specific claim;
- the exact choices deferred until tenant evidence exists: plant identity, production threshold, observation window, source-system binding, and regulatory applicability.

The initial product families are refrigeration, laundry, dish care, and cooking. The generic process vocabulary is incoming inspection, component preparation, assembly, joining and sealing, final test, and packaging. These are domain identifiers, not a claim that a tenant uses all of them.

## Objectives, CTQs, and KPIs

The ontology defines five candidate objectives: improve first-pass yield, reduce confirmed defect escape, reduce evidence-confirmed warranty return, improve CTQ conformance, and improve resource-performance evidence. Each objective has one accountable role and an acceptance relation.

Six representative CTQs cover sealed-system integrity, temperature stability, water containment, vibration performance, electrical test result, and cosmetic grade. They contain a stable identifier, label, metric code, target direction, accountable role, and evidence class. They deliberately contain no plant threshold.

Five KPI definitions provide formula semantics rather than tenant values:

| KPI | Numerator | Denominator | Direction |
| --- | --- | --- | --- |
| First-pass yield | accepted units without rework | inspected units | higher is better |
| Defect escape rate | confirmed post-release defects | released units | lower is better |
| Warranty return rate | evidence-confirmed returned units | shipped units | lower is better |
| Rework rate | units requiring rework | completed units | lower is better |
| CTQ conformance rate | accepted CTQ observations | total CTQ observations | higher is better |

Each KPI also declares dimensions and exactly one accountable role. Observation windows, thresholds, source-system bindings, and applicability decisions remain deferred to tenant-authorized evidence.

## Ontology and SHACL execution contract

The ontology uses only `urn:planeon:white-goods:*` domain identifiers and the exact RDF, RDFS, XSD, OWL, and SHACL W3C namespace identifiers admitted by framework 0.1.1. These identifiers are never dereferenced. Arbitrary HTTP or FTP IRIs remain invalid.

SHACL validation receives only explicit local graphs and runs with `inference=none`, `advanced=false`, `js=false`, and `do_owl_imports=false`. Ontology imports, SPARQL constraints, JavaScript constraints, remote graphs, and implicit resolution are forbidden. The positive product-model fixture conforms; the deliberately incomplete KPI fixture fails the required formula, numerator, denominator, dimension, direction, and accountability constraints.

## Deterministic answer decisions

The packet handler closes answer keys against the questionnaire, checks response types and choices, requires synthetic fixtures and false evidence flags, binds the deferred-choice field to the corresponding answer, and produces sorted stable reason codes:

- `MISSING_ACCOUNTABLE_OWNER`
- `INCOMPLETE_OUTCOME_EVIDENCE`
- `UNVERIFIED_PLANT_SPECIFIC_CHOICE`
- `ROLE_SEPARATION_UNCONFIRMED`
- `INCOMPLETE_REQUIRED_ANSWER`
- `NON_READY_ACCEPTANCE_OUTCOME`

Only the complete `pilot-scope-approved` vector with no blockers yields `READY`. The supplied negative vectors each bind one expected blocking outcome. Canonical sorted UTF-8 JSON digests freeze all four vectors.

## Offline and zero-bill operation

RDFLib 7.6.0 and pySHACL 0.40.1 are development-only dependencies in the exact lock. Packet acceptance consumes them from a preloaded root-owned toolchain inside a single deny-all-outbound process tree. It performs no runtime download, cloud provisioning, hosted action, artifact upload, remote telemetry, API-key access, or publication. The handler creates only temporary in-process build outputs and retains no artifact.
