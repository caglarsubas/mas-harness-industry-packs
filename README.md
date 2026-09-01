# Planeon Industry Packs

Offline, deterministic, data-only guidance packs for building an enterprise multi-agent harness ecosystem. The framework begins with an immutable, industry-neutral eight-stage journey and admits sector guidance only as append-only overlays.

IND-001 provides:

- closed JSON Schemas for packs, journeys, rules, contract locks, and indexes;
- strict regular-file loading with traversal, link, duplicate-key, executable-content, and unlisted-file rejection;
- deterministic validation, canonical indexing, fixed-epoch packaging, wheel, and sdist builds;
- a credential-free CLI: `harness-pack validate|compile-index|package`;
- self-hosted, deny-all-outbound verification with no remote artifact storage.

The repository holds no tenant answers, executable plug-ins, provider credentials, runtime integrations, or hosted-service dependencies.

## Local verification

Product acceptance must be launched with the trusted, hash-pinned offline runner. The packet commands are:

```text
make prefetch
make pack-framework-test
make build-reproducible
make zero-bill
```

Running these commands directly is useful developer feedback but is not signed candidate, CI, merge, runtime, assurance, or tenant-acceptance evidence.

