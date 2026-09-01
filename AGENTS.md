# Sol-High Product Execution Rules

1. Implement exactly one task packet from the public `harness-onion` meta repository per branch and PR.
2. Touch only the packet's `allowedPaths`; read every predecessor contract and lock first.
3. Never mount, open, or copy a warm-start checkout. `sourceReuse` is provenance only unless a future packet carries explicit path-level copy authorization and a matching `PORTING.yaml` entry.
4. Use `codex/<packet-id>-<slug>`, the signed hash-pinned offline launcher, ephemeral credential-free self-hosted CI, and merge only when every required check is green.
5. No cloud provisioning, hosted runners, billable APIs, API keys, runtime downloads, mutable artifact references, remote telemetry, or publication from CI.
6. Preserve source, candidate, CI, merge, artifact, publication, deployment, runtime, assurance, and tenant acceptance as separate evidence states.
7. Stop when an unresolved decision changes a public contract, tenant isolation, destructive-data behavior, licensing, or billing boundary.
8. Only the bootstrap packet owns `Makefile`, `ci/run_make_target.py`, and the inert `PORTING.yaml` seed. Later packets add only their packet-owned target descriptor unless explicitly authorized otherwise.

