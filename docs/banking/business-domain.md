# Banking business-domain foundation

## Scope and evidence boundary

`banking.financial-services` 0.1.0 (industry `banking`) is a clean-room, data-only sector overlay on the exact `common.foundation` 1.0.0 pack. It is the banking successor of the historical white-goods business-domain slice for release scope. It guides a tenant through a bounded business and domain definition before any data integration, model, agent, tool, runtime, or production action is selected.

The pack holds three business questionnaires, one ontology with its SHACL shapes, seven synthetic answer vectors, and two synthetic ontology fixtures. Its `rules`, `readiness`, `controls`, and `providerPreferences` lists are empty: data readiness, governance and regulation, integrations, and provider fit belong to later banking packets. The pack carries byte-identical copies of the common contract lock and journey, uses `overlayMode: APPEND_ONLY`, and shadows no common resource.

The pack contains no institution identity, real account, card, customer, employee, or transaction data, no threshold presented as real, no credential, secret, remote endpoint, model prompt, write-capable action, regulatory conclusion, or control mapping, and it names no law, regulation, or supervisory standard.

## Guided business questionnaire

The three questionnaires (`banking.business.roles`, `banking.business.objectives`, `banking.business.acceptance`) bind a tenant declaration to a closed vocabulary. Response types are only string, boolean, number, and choice.

- Accountable roles: business owner, domain owner, first-line risk owner, second-line compliance owner, data steward, and evidence approver, plus a confirmation that authoring, first-line risk ownership, second-line compliance oversight, and evidence approval are held by distinct roles.
- Objectives and scope: one primary measurable objective; product-family, channel, and KPI scopes; a closed pilot decision scope; an unacceptable outcome.
- Evidence and acceptance: a business-domain outcome and local evidence identifiers.
- Deferred institution-specific choices: institution identity, jurisdiction, licence type, risk appetite, observation window, and regulatory applicability. Every synthetic vector keeps all six deferred; an institution-specific claim without tenant verification blocks.

## Ontology and glossary

The ontology uses only `urn:planeon:banking:*` identifiers and the exact RDF, RDFS, XSD, OWL, and SHACL W3C namespace identifiers admitted by framework 0.1.1; these are never dereferenced. There is no SKOS, no ontology import, and no SPARQL or JavaScript constraint.

- Business frame: business objective, accountable role, key performance indicator, acceptance outcome, target direction, pilot decision scope, and institution-specific choice.
- Banking concepts: parties (party, customer, counterparty, legal entity, natural-person role, which is a role and never a person record), products (product family with deposits, payments, cards, consumer lending, and commercial lending; product), accounts (account, account role with holder, signatory, and beneficiary), transactions (transaction, payment instruction, transaction type), channels (branch, online, mobile, contact centre, partner interface), credit (credit facility, credit application, credit decision as a concept only), and risk and compliance (risk type with credit, liquidity, market, operational, conduct, and financial-crime risk; control; compliance obligation, whose instances come later; risk data element).

Every class and named individual is a versioned glossary entry with a stable id, a label, a clean-room definition, term version `1.0.0`, a closed provenance (`AUTHORED_CLEAN_ROOM` or `NAMED_STANDARD_CONCEPT`), and the questionnaire question it serves. Where a public standard names the concept, a plain-text alignment literal records only the standard's name (technical identifier standards and reference-ontology concept names); it is never an address and never copied text.

Six KPI definitions carry formula semantics, dimensions, a target direction, one accountable role, and an evidence class, but no target value:

| KPI | Basis | Direction |
| --- | --- | --- |
| Straight-through processing rate | instructions completed without manual intervention / instructions received | higher is better |
| First-contact resolution rate | enquiries resolved at first contact / enquiries received | higher is better |
| Complaint resolution time | elapsed time from complaint receipt to recorded resolution | lower is better |
| Risk report timeliness | time from reporting-period end to an approved internal risk report | lower is better |
| Risk data exception rate | risk data elements with an open quality exception / risk data elements in scope | lower is better |
| Cited-answer rate | sampled assistant answers with a valid source citation / sampled assistant answers | higher is better |

## SHACL execution contract

The shapes require the glossary members on every class and named individual, exactly one accountable role per objective, KPI, and acceptance outcome, and for each KPI a formula, a numerator and denominator or an observation definition, dimensions, a target direction, and an evidence class. Validation receives only explicit local graphs and runs with `inference=none`, `advanced=false`, `js=false`, and `do_owl_imports=false`. The positive fixture (a synthetic deposit product) conforms; the negative fixture (a deliberately incomplete KPI with an undeclared provenance) fails with minimum-count, closed-value, and alternative-definition constraint results.

## Deterministic answer decisions

The packet handler closes answer keys against the questionnaire and checks response types and choices. An unknown, missing, or mistyped answer key makes a vector invalid: the handler and the test fail, and the vector is never `BLOCKED`. Valid vectors produce sorted stable reason codes:

- `MISSING_ACCOUNTABLE_OWNER`
- `INCOMPLETE_OUTCOME_EVIDENCE`
- `UNVERIFIED_INSTITUTION_SPECIFIC_CHOICE`
- `ROLE_SEPARATION_UNCONFIRMED`
- `DECISION_SCOPE_REQUIRES_GOVERNANCE_STAGE`
- `PERSONAL_DATA_FORBIDDEN`
- `INCOMPLETE_REQUIRED_ANSWER`
- `NON_READY_ACCEPTANCE_OUTCOME`

Only the complete read-only cited-assistant pilot yields `READY`; each of the six negative vectors binds one blocker. The pilot decision scope is a stage-local declaration with three values: information only, human-reviewed recommendation, and automated decision out of pilot scope. The third blocks as a deferral to the later governance packet that owns the autonomy taxonomy; it is not a legal conclusion. Canonical sorted UTF-8 JSON digests freeze all seven vectors.

## Disallowed data

A structural scan looks for IBAN shapes that pass the ISO 13616 mod-97 check and 13-19 digit runs that pass the Luhn check. It covers exactly the answer values, the questionnaire prompts and titles, and the ontology literals. It must find exactly one value in exactly one vector: the pinned synthetic value in `personal-data-in-answer.json`, which uses the unassigned country code `XX` and an all-zero basic account number, so it can never be a real account. Tests build their Luhn and mod-97 values at run time; the repository holds no other card- or account-like literal.

## Offline and zero-bill operation

RDFLib 7.6.0 and pySHACL 0.40.1 are development-only dependencies already in the exact lock; the handler refuses any other installed version. Packet acceptance runs inside a deny-all-outbound process tree, performs no download, cloud provisioning, hosted action, upload, telemetry, or publication, creates only temporary in-process outputs, and retains no artifact.

## Non-claims

This slice makes no pack release, signature, artifact, catalog change, control mapping, provider selection, campaign, deployment, runtime, assurance, or tenant acceptance claim. It draws no regulatory conclusion and holds no personal data. Source, candidate, CI, merge, artifact, publication, deployment, runtime, assurance, and tenant acceptance remain separate evidence states, and every evidence flag stays `false`.
