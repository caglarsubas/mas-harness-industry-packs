# Industry-pack authoring contract

## Start from the common journey

Every tenant setup begins with `common.foundation` version `1.0.0` and its eight stages, in order: business context, domain and outcomes, data readiness, governance and regulation, integration readiness, harness demand, environment and provider fit, and evidence and acceptance. The common pack is immutable and industry-neutral.

A sector pack declares `packKind: SECTOR`, `overlayMode: APPEND_ONLY`, and an `extends` record binding the exact computed common-pack digest. It repeats the exact journey and contract-lock bytes so validation is self-contained. It may add uniquely identified material to an existing stage. It cannot remove, replace, shadow, reorder, weaken, or extend another sector pack.

## Data-only content

Declare every file once in `pack.yaml`. The loader admits regular UTF-8 YAML, JSON, Markdown, text, CSV, JSONL, RDF, Turtle, and OWL only. It rejects links, special files, hidden members, traversal, executable suffixes or modes, duplicate structured-data keys, custom YAML tags, unlisted files, oversize files, remote targets, template markers, credential fields, executable fields, and model/tool invocation fields.

Rule expressions use only `all`, `any`, `not`, `eq`, `in`, `exists`, `gte`, and `lte`. Rule actions use only `ASK_QUESTION`, `REQUIRE_EVIDENCE`, `RECOMMEND_HARNESS`, and `BLOCK_READINESS`. Rule fields are answer references; rules are declarative data, never expressions evaluated as source code.

## Deterministic outputs

`harness-pack validate PACK_ROOT` emits sorted canonical JSON and never writes. `compile-index PACK_ROOT --output FILE` creates a new canonical index only when the destination is absent. `package PACK_ROOT --output DIR` creates a new directory containing one fixed-epoch, sorted, mode-0644 tar.gz. Neither command overwrites, publishes, signs, deploys, contacts a registry, or reports runtime/assurance/tenant acceptance.

Pack authors should keep generated output outside the pack root because every input member must be declared and the generated index is deliberately excluded from its own digest subject.

## Evidence boundaries

Schema validation and deterministic packaging prove only source and offline artifact properties. The generated evidence flags remain false for publication, runtime, assurance, and tenant acceptance. Those states require separate downstream authorities and cannot be inferred from this repository's CI.

## Dependencies and licensing

IND-001 uses only exact open-source dependencies `jsonschema==4.24.0`, `PyYAML==6.0.2`, and development-only `pytest==8.4.2`. RDFLib and pySHACL are intentionally absent; ontology conformance is not claimed until a later packet admits and locks that toolchain. Pack metadata accepts Apache-2.0, MIT, BSD-2-Clause, or BSD-3-Clause content only.

