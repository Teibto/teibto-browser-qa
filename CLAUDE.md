# CLAUDE.md

Orientation for an agent or developer working **on this repository**. Consumers start with
`SKILL.md`; contributors follow this file with [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Repository boundary

This repository packages browser-QA guidance, a strict YAML runner, an optional loopback-only UI,
and documentation templates around the external canonical `cdp.py` driver. It does not vendor or
fork the driver. Driver behavior changes belong in `Teibto/teibto-dev-standards` and must be verified
here through the live compatibility tests.

The shipped `.skill` bundle contains the runtime entrypoint, references, templates, examples, schema,
runner scripts, and local UI. Repository-only architecture, claim provenance, tests, and contribution
guidance are intentionally not bundled.

## Information layers

```text
SKILL.md             always-loaded purpose, safety invariants, and routing
  -> references/     task-specific procedures loaded only when needed
  -> scripts/app     executable runner and optional local interface
self-test/ + tests/  behavior, packaging, and drift gates
docs/CLAIMS-AUDIT.md current claim provenance and withdrawn-claim record
```

- Keep `SKILL.md` compact, but do not demote safety invariants that every live run needs.
- Keep each operational fact in one reference and link to it from the entrypoint or README.
- Do not document a flow field until schema, execution behavior, and a failure test ship together.
- A causal or behavioral claim needs reproducible evidence where practical and a provenance row in
  `docs/CLAIMS-AUDIT.md`.

## File ownership

| Path | Responsibility |
|---|---|
| `SKILL.md` | Skill selection, mandatory invariants, progressive routing |
| `references/` | On-demand commands, safety, layers, flow, reliability, and PDF procedures |
| `scripts/flow-runner.py` | Validated flow execution through a bounded CDP JSONL session |
| `schemas/flow.schema.json` | Authoritative executable-flow fields; fail closed on extras |
| `app/` | Optional loopback UI that delegates to the same runner |
| `assets/` | User-guide/bug-report templates and evidence markers |
| `docs/ARCHITECTURE.md` | Current component and data-flow boundaries |
| `docs/TEAM-PROCESS.md` | Team traceability and release-gate ownership |
| `docs/CLAIMS-AUDIT.md` | Current verified, measured, inferred, and version-pinned claims |
| `self-test/` and `tests/` | Live driver drift checks plus deterministic unit/package checks |

## Conventions

- README and architecture are concise product documentation; operational references may use Thai.
  Match the surrounding file rather than enforcing a language split that the repository does not use.
- Prefer current contracts over migration history. Historical behavior belongs in `CHANGELOG.md` and
  Git history unless a temporary upgrade instruction still changes a user's action.
- Use issue-first GitHub flow, an issue-numbered branch, a conventional commit, and a squash PR.
- Releases are SemVer tags. The `.skill` bundle is rebuilt and attached by the release workflow; do
  not commit it.

The full edit, validation, and release loop is in [`CONTRIBUTING.md`](CONTRIBUTING.md).
