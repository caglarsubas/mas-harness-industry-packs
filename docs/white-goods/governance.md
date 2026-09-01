# White-goods governance and integration guidance

White-goods pack 0.3.0 adds a deterministic, data-only setup slice for
regulatory applicability, action autonomy, integration declarations, and
waiver documentation. It does not execute a connector, issue an approval,
determine legal applicability, or authorize production promotion.

## Public and pack-local contracts

The slice binds `mas-harness-contracts` commit
`2146278a95344cd2a8e22596b2f315b46edffc88` and the released
`ApprovalRequest` v1alpha1 lifecycle schema. The binding records exact SHA-256
values for that schema and its two common dependencies without copying schema
bytes into this repository.

`ControlRequirement` and `IntegrationDeclaration` are architecture-planned
kinds but are absent from the pinned public release. This pack therefore marks
both `NOT_AVAILABLE_IN_BOUND_RELEASE`. Its
`IndustryControlRequirementRecordSet` and
`IndustryIntegrationDeclarationRecordSet` are pack-local guidance data, not
implementations of unreleased public schemas.

## Decision boundary

Actions use four closed categories:

- `READ_ONLY`
- `REVERSIBLE_WRITE`
- `IRREVERSIBLE_WRITE`
- `UNKNOWN_SIDE_EFFECT`

Unknown side effects always block. A write requires an exact policy reference,
an unexpired approved `MUTATION` request, distinct approver quorum, a durable
receipt requirement, idempotency, approved scoped access through a credential
reference identifier, and either compensation or independent outcome review.
The bundled integration records are synthetic declarations only and contain no
endpoint, connection, credential value, or executable configuration.

## Regulatory applicability

Candidate themes cover product safety, data protection, cybersecurity, quality
management, and environmental or energy governance. A tenant-authorized role
must determine applicability for the exact jurisdiction and market scope and
bind local evidence. Pack prompts and examples are not legal advice or legal
conclusions.

## Waivers

A waiver must bind the same required control and complete demand scope, an
approved `WAIVER` request, justification evidence, a compensating control, and
a non-renewable future expiry. It only documents an exception. Even a valid,
active waiver yields `WAIVER_DOES_NOT_SATISFY_PROMOTION`; production promotion
remains blocked until every required control has fresh `PASS` evidence.

## Evidence boundary

The fixtures are synthetic decision vectors. Their source, candidate, CI,
merge, artifact, publication, deployment, runtime, assurance, and tenant
acceptance states are all false. Packet acceptance creates only candidate and
CI evidence outside the pack; it retains and publishes no artifact.
