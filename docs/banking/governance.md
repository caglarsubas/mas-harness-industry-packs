# Banking governance and integrations

Banking 0.3.0 adds a deterministic, data-only governance-and-integration slice to `banking.financial-services`. It
states who may do what at which autonomy, which control objectives a case must evidence, which outcome state counts as
done, which synthetic integration profiles a tenant may declare, and which regulatory themes a tenant role must rule
on. It executes no connector, issues no approval, decides no legal applicability and authorizes no production
promotion. Every record is pack-local data checked by `ci/handlers/ind_bank_003.py`.

## What the pack adds

| Resource | Path | Stage |
|----------|------|-------|
| Contract binding (ApprovalRequest v1alpha1 and its two common dependencies, by exact sha256) | `controls/contract-binding.json` | governance-and-regulation |
| Control requirements CAP01-13 with a closed control class | `controls/control-requirements.json` | governance-and-regulation |
| Integration declarations IP16, IP17, IP18 | `controls/integration-declarations.json` | integration-readiness |
| Waiver policy | `controls/waiver-policy.json` | governance-and-regulation |
| Autonomy policy (modes, action classes, invariant rows) | `controls/autonomy-policy.json` | governance-and-regulation |
| Outcome states and their negative rules | `controls/outcome-states.json` | governance-and-regulation |
| Deployer-duty evidence map (candidates only) | `controls/ai-act-deployer-map.json` | governance-and-regulation |
| Four questionnaires | `questions/governance/*.yaml`, `questions/integrations/declarations.yaml` | as declared |
| Governance rule `banking.governance.block-unsafe-action` | `rules/governance.json` | governance-and-regulation |
| 29 labelled vectors | `fixtures/governance/*.json` | governance-and-regulation |

`ControlRequirement` and `IntegrationDeclaration` are not available in the bound contracts release, so both stay
`NOT_AVAILABLE_IN_BOUND_RELEASE` and the pack keeps them as pack-local record sets. No schema bytes are copied.

## Autonomy

Each case declares a mode: A1 evidence, A2 prepared action, A3 bounded execution. Every step names an action class,
its executor and its approval.

| Action class | Side-effect category | Agent may execute at | Executor when not the agent | Approval and receipt |
|--------------|----------------------|----------------------|-----------------------------|----------------------|
| read_evidence | READ_ONLY | A1, A2, A3 | - | none; source receipt |
| prepare_action | READ_ONLY | A2, A3 | - | none; the draft has no external effect |
| submit | IRREVERSIBLE_WRITE | never | human role (A2 and A3 cases) | approved MUTATION request, maker and checker distinct; receipt |
| task_update | REVERSIBLE_WRITE | A3 only | - | the write rules; scope is the case's own task |
| approve_payment | IRREVERSIBLE_WRITE | never | human role, any mode | approved MUTATION request, distinct approver quorum |

The derived mode is the least mode whose agent set covers every agent-executed step. It must equal the declared mode,
and it is judged on the declarations before any check result. Every child declares its own mode; a missing child mode
blocks and is never inherited, and a summary mode never broadens a child. Profiles never raise a mode: a profile above
the case and a case above a profile are both refused. Unknown action classes and unknown side effects always block.

The three invariant rows the pack enforces on its own side, quoted from the register:

- INV01: "Installing a pack MUST NOT create data grants, execution rights or business authority." The closed manifest
  schema refuses any unknown manifest field at load; the 003 handler refuses any field outside each record set's closed
  field set, including any grant, entitlement or authority field. The platform's own grant path is outside the pack.
- INV03: "The permitted action, executor, approval and derived mode MUST agree; a summary mode MUST NOT broaden child
  actions."
- INV18: "A failed compatibility, capability or protected-policy check MUST disable affected execution; fallback MUST
  use a separately defined preparation scope." After a failed check the effective mode drops to the case's preparation
  scope (A1 or A2) and every step above it is disabled. The effective mode only goes down.

## Control objectives, profiles, outcomes and waivers

- CAP01-13 each carry a control class: AUTOMATED, MANUAL or TECHNOLOGY_DEPENDENT, an owner role and the evidence kinds
  a tenant must supply.
- IP16 payments (maximum mode A2), IP17 reconciliation (A3) and IP18 reporting (A1) are synthetic declarations. They
  hold no endpoint, connection, credential value or executable configuration, only the
  `accessCredentialReferenceRequired` form; counterparties are synthetic labels.
- Outcome states are accepted, committed and final, each with its required evidence kind and in that order. A
  submission receipt is not acceptance, an upload receipt is not acceptance, and a readiness flag is not disbursement.
- A waiver documents an exception and never satisfies promotion (`WAIVER_DOES_NOT_SATISFY_PROMOTION`); an expired waiver
  or one without a compensating control is refused before that.

## Regulatory applicability (candidates)

The applicability questionnaire lists candidate themes for a tenant-authorized role to rule on per jurisdiction. The
pack asserts none of them, and its prompts are not legal advice.

## Deployer-duty evidence map (HG-D1)

`controls/ai-act-deployer-map.json` maps candidate deployer duties to a pack evidence slot or names the gap the pack
cannot fill. Every entry is marked CANDIDATE, article references are candidates for the tenant to confirm, and no legal
text is quoted. The creditworthiness of natural persons is listed as a candidate high-risk use; whether it applies is
the tenant role's ruling.

| Candidate duty id | Candidate reference | Pack evidence slot | Named gap (tenant-side evidence) |
|-------------------|---------------------|--------------------|----------------------------------|
| deployer-duty.use-per-instructions | Article 26(1), candidate | none | yes |
| deployer-duty.human-oversight | Article 26(2), candidate | `banking.control.cap02-accountable-operator` | yes |
| deployer-duty.input-data-relevance | Article 26(4), candidate | `banking.data.readiness-policy` | none |
| deployer-duty.monitoring-and-notification | Article 26(5), candidate | none | yes |
| deployer-duty.log-retention | Article 26(6), candidate | `banking.control.cap07-durable-receipt` | yes |
| deployer-duty.worker-information | Article 26(7), candidate | none | yes |
| deployer-duty.affected-person-information | Article 26(11), candidate | none | yes |
| deployer-duty.fundamental-rights-impact-assessment | Article 27, candidate | `creditworthiness-use-in-scope` | yes |
| deployer-duty.explanation-of-decisions | Article 86, candidate | none | yes |
| deployer-duty.ai-literacy | Article 4, candidate | none | yes |

The map's own `namedGap` text says what each gap is; the pack fills none of them.

## Readiness evaluator: two entry forms

- Acceptance form: `make readiness-evaluate PACK=banking` runs `ci/handlers/ind_bank_003.py readiness-evaluate banking`
  on the shipped synthetic input `tests/fixtures/banking/evaluator/input` and passes only when the canonical verdict
  equals `tests/fixtures/banking/evaluator/expected.json` byte for byte.
- Tenant form: `harness-pack readiness-evaluate <pack_root> --input <dir>`. The input directory holds a v1alpha1
  `source-inventory.json` and the data members it names. The evaluator measures each source, judges it against the
  pack's DataReadinessPolicy, prints the canonical verdict and exits 0 on READY, otherwise 1. A source whose members
  carry no record timestamps is observed as of the input snapshot (the latest observation in the input). It refuses a
  symbolic link, a non-regular file or a path that escapes the input directory, and it never imports `ci/`.

The evaluator and `ci/handlers/ind_bank_002.py` agree on all nine readiness fixtures.

## Non-claims

No legal applicability, approval, connector execution, endpoint or credential; no promotion; no held-out answers; no
personal data; white goods, the dispatcher, the transport and the framework version are unchanged. Packet acceptance
creates candidate and CI evidence only.
