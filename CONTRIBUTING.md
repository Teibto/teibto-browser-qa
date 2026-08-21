# Contributing

How to change this skill without breaking the discipline it is built on. New here? Read
[`CLAUDE.md`](CLAUDE.md) first for the mental model, then this file for the loop.

## Prerequisites

- Chrome + `py -m pip install websocket-client pillow numpy` — needed to run `self-test/smoke-test.sh`.
  driver อยู่ที่ `~/.claude/skills/netsuite-qa-browser/references/cdp.py` (override ด้วย `NS_CDP`).
- Python 3.10+ with PyYAML/jsonschema: `pip install -r requirements.txt` — for the `scripts/`.
- Node.js 20+ only when changing the optional local UI.
- Optional: `pymupdf` (for `self-test/pdf/pdf-test.sh`).

## The change loop

Most edits change or add a **claim** — a statement about how the browser/driver behaves, a gotcha, a
recipe, a token/efficiency number. The loop keeps a claim honest:

```
1. edit the source        references/<file>.md (detail) and/or SKILL.md (if it's a golden rule)
2. add/adjust a check      self-test/ — a claim ships with a reproducible check, not an anecdote
3. record provenance       docs/CLAIMS-AUDIT.md — a row: measured / verified-by-A/B / inferred / version-pinned
4. run self-test           bash self-test/smoke-test.sh  (+ pdf/pdf-test.sh if PDF-related)
5. ship                    issue-first → branch → PR → squash-merge (see "Git flow")
```

Not every edit is a claim (fixing a typo, tightening wording). But anything that asserts a behavior
or a number goes through steps 2–3 — that is what separates this repo from a pile of tips.

### Editing SKILL.md vs a reference

`SKILL.md` is loaded into context on **every** skill trigger; `references/*.md` load **on demand**.
So keep `SKILL.md` lean: a golden rule + a pointer, with the full detail in the reference. Do not
copy a reference's content up into `SKILL.md`. When in doubt, measure — this repo counts tokens with
`tiktoken` rather than estimating.

### Adding a self-test check

Two kinds live in `self-test/smoke-test.sh`:
- **Browser checks** drive a real Chrome (via `cdp.py`) against `self-test/smoke-page.html` (e.g. "`click`
  does not auto-scroll"). Use `chk "name" "expected-substr" "actual"`.
- **Pure-file checks** need no browser (e.g. the PDF-template scoped-read gate). Prefer these for
  anything measurable from files — they stay green even where the browser harness can't run.

Verify a new check actually runs (`bash -n` for syntax, then run it) before shipping it. Document it
in `self-test/README.md`.

### Updating the claims ledger

`docs/CLAIMS-AUDIT.md` is the ledger of what is proven vs assumed. When you add or change a claim,
add or update its row with honest provenance:
- **measured** — a number you produced with a tool (cite it, e.g. "tiktoken o200k_base").
- **verified (A/B)** — reproduced with a controlled before/after.
- **inferred** — a causal claim you believe but did not A/B; say so, don't promote it to fact.
- **version-pinned** — true for a specific Chrome / `cdp.py` version; re-verify on a bump.

## Running the checks

```bash
python -m unittest discover -s tests -v
node --check app/server.js
bash tests/test-flow-runner-live.sh  # real Chrome + shared cdp.py; skips if either is unavailable
bash self-test/smoke-test.sh      # syntax/recipe/reproducible claims + efficiency gates
bash self-test/pdf/pdf-test.sh    # PDF pagination A/B (needs pymupdf + network for paged.js CDN)
```

Re-run after any Chrome or `cdp.py` version bump — this is the drift detector.

## Scripts

| Script | What it does | Usage |
|---|---|---|
| `scripts/flow-runner.py` | Strict flow executor using one pinned, bounded `cdp.py` JSONL session per run. | `python scripts/flow-runner.py --help` |
| `scripts/build-skill.py` | Zips `SKILL.md` + `assets/` + `references/` + `examples/` + runtime scripts into `teibto-browser-qa.skill` (a git-ignored build artifact). | `python scripts/build-skill.py` |
| `scripts/coverage-check.py` | Release gate as an exit code: reads a `qa/<feature>/coverage.yaml` and returns 0 (pass) / 1 (fail) / 2 (malformed). | `python scripts/coverage-check.py qa/<feature>/coverage.yaml` |
| `scripts/release-summary.py` | Rolls every `qa/*/coverage.yaml` into one sign-off table, reusing the gate logic. | `python scripts/release-summary.py [qa_dir]` |

## Cutting a release

1. Land all changes on `main` via PRs.
2. Add a `## [X.Y.Z] - YYYY-MM-DD` section to `CHANGELOG.md`, leading with a **bold one-line
   summary** (it becomes the first line of the release body).
3. Tag and push — that's it (SemVer; docs/optimization = minor, fixes = patch):
   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z — <summary>" && git push origin vX.Y.Z
   ```
   `.github/workflows/release.yml` then builds `teibto-browser-qa.skill`, creates the GitHub
   Release with the body taken from that CHANGELOG section, and attaches the bundle.

**No CHANGELOG entry = the workflow fails on purpose** — a release with an empty body is worse
than no release.

The release title is plain `vX.Y.Z` (team standard, `Teibto/teibto-dev-standards` Playbook R7);
the descriptive summary now lives in the first line of the body instead of the title.
The README's release badge is dynamic and updates itself once the release is the latest.

## Git flow

- This repo has a GitHub remote, so every change is **issue-first**: open an issue, branch
  (`docs/<n>-slug`, `feat/<n>-slug`, `fix/<n>-slug`), PR with `Closes #<n>`, squash-merge.
- [Conventional Commits](https://www.conventionalcommits.org/): `docs:`, `feat:`, `fix:`, `test:`,
  `chore:`, `refactor:`.
- Keep changes surgical — every changed line should trace to the issue.
