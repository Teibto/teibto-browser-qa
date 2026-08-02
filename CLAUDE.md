# CLAUDE.md

Orientation for an agent or developer working **on this repo** (not for a consumer of the skill —
that audience reads `SKILL.md`). Read this first, then `CONTRIBUTING.md` for the change loop.

## What this repo is

A Claude Code **skill**: a playbook, doc templates, and a few scripts wrapped around the external
`cdp.py` (driver กลางของทีมที่ขับ Chrome
over CDP). It is not an application — nothing here runs a server. The deliverable is the guidance in
`SKILL.md` + `references/`, verified by `self-test/`, and shipped as a `.skill` bundle on a Release.

Mental model the skill teaches: **Claude = the brain** (reads code, derives tests, judges pass/fail,
writes docs); **`cdp.py` = the hands & eyes** (drives the browser, captures evidence, decides
nothing). One walk of the happy path yields two outputs: a QA verdict and documentation material.

## The four layers and how they relate

```
SKILL.md          entry point — loaded into context on EVERY skill trigger. Keep it lean.
  │  points to
references/*.md    working notes (Thai), loaded ON DEMAND only. Detail lives here, not in SKILL.md.
  │  claims verified by
self-test/         mechanical checks of the syntax/recipe/reproducible claims (drift detector).
  │  ledgered in
docs/CLAIMS-AUDIT  which claim is verified / measured / inferred / version-pinned, with provenance.
```

Two consequences to keep in mind when editing:
- **`SKILL.md` costs tokens on every trigger; `references/` do not.** Push detail down to a reference
  and point to it. Don't duplicate a reference's content in `SKILL.md`.
- **A causal or behavioral claim ships with a reproducible check, not an anecdote.** New/changed
  claims get a `self-test/` check where possible and a row in `docs/CLAIMS-AUDIT.md` with honest
  provenance (measured / verified-by-A/B / inferred / version-pinned). This is the discipline the
  whole repo is built around — see `docs/CLAIMS-AUDIT.md`'s own "GPU class" story.

## File map

| Path | What it is |
|---|---|
| `SKILL.md` | The skill itself: golden rules, workflow, targets. Loaded every trigger. |
| `references/` | Thai working notes: `gotchas`, `commands`, `test-design`, `flow-spec`, `pdf-reports`, `coverage-model`, `reliability-policy`, `a11y-layer`, `perf-layer`, `visual-regression`, `test-data`. On-demand. |
| `docs/` | `ARCHITECTURE.md` (mermaid per flow), `TEAM-PROCESS.md` (lifecycle, release gate, RACI), `CLAIMS-AUDIT.md` (claim ledger). |
| `assets/` | PDF templates (`guide-`, `bug-report-template.html`) + `highlight.js` / `pointer.js`. Edit only the `data[]` block — see `references/pdf-reports.md`. |
| `self-test/` | `smoke-test.sh` (claim checks กับ Chrome จริงผ่าน cdp.py) + `pdf/pdf-test.sh` (pagination A/B). |
| `scripts/` | `build-skill.py` (bundle), `coverage-check.py` (release gate → exit code), `release-summary.py` (roll-up). |
| `examples/` | `saucedemo.yaml` — a runnable flow. `qa/_template/coverage.yaml` — a manifest starter. |

## Conventions

- **Docs language:** `README.md` and `SKILL.md` are English; `references/` are Thai working notes (by
  design). Match the file you are editing.
- **Verify, don't guess.** Measure with a tool (this repo counts tokens with tiktoken, pages with
  pymupdf) rather than estimating. Label a claim's provenance in `CLAIMS-AUDIT.md`.
- **GitHub flow:** this repo has a GitHub remote, so changes go through an issue → branch → PR →
  squash-merge (issue-first). Conventional Commits (`docs:`, `feat:`, `fix:`, `test:`, `chore:`).
- **Releases:** SemVer tags; the `.skill` bundle is a build artifact (git-ignored), rebuilt and
  attached to each GitHub Release. See `CONTRIBUTING.md`.

The full development loop (change a claim → add a check → update the ledger → run self-test → build →
PR) is in [`CONTRIBUTING.md`](CONTRIBUTING.md).
