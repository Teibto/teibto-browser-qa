# teibto-browser-qa

[![Release](https://img.shields.io/github/v/release/Teibto/teibto-browser-qa?logo=github&label=release&color=5A3FD6)](https://github.com/Teibto/teibto-browser-qa/releases/latest)
[![CI](https://github.com/Teibto/teibto-browser-qa/actions/workflows/ci.yml/badge.svg)](https://github.com/Teibto/teibto-browser-qa/actions/workflows/ci.yml)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-skill-5A3FD6?logo=anthropic)](https://docs.anthropic.com/claude/docs/skills)
[![driver](https://img.shields.io/badge/driver-CDP%20direct%20(cdp.py)-orange?logo=googlechrome)](https://github.com/Teibto/teibto-dev-standards)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

<p align="center">
  <img src="docs/banner.png" alt="teibto-browser-qa: browser QA and docs from one real browser run" width="100%">
</p>

A Claude Code skill for browser QA and documentation. Drive a real browser through a flow once and get two things back: a QA verdict, and a polished user guide or bug report.

> **Transport note (2026-08-02):** this skill used to drive Chrome through the `agent-browser` CLI and its background daemon. It now talks **straight to Chrome over CDP** via `cdp.py` — the team's shared driver in [`Teibto/teibto-dev-standards`](https://github.com/Teibto/teibto-dev-standards). The daemon was dropped because it hung without saying why (`os error 10060` loops, silently dead Chrome) and could not answer JavaScript dialogs at all — `beforeunload` wedged it permanently. Command-by-command mapping: [`references/commands.md`](references/commands.md).

> **Renamed 2026-08-21:** `agent-browser-qa` moved to `Teibto/teibto-browser-qa`. GitHub redirects the old repository URL, but installed skill folders are not redirected. Install only `teibto-browser-qa`; remove the old junction after updating callers so the same capability is not discovered twice.

The reference files under [`references/`](references) are working notes kept in Thai. This README and [`SKILL.md`](SKILL.md) are in English.

**New here?** Read in order: this README → [`SKILL.md`](SKILL.md) (golden rules + workflow) → [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (diagrams) → [`references/gotchas.md`](references/gotchas.md) (the silent-failure traps). Working *on* the skill? Start with [`CLAUDE.md`](CLAUDE.md) then [`CONTRIBUTING.md`](CONTRIBUTING.md).

## How it works

Claude reads the code, derives the tests, and judges pass or fail. `cdp.py` does the driving and captures the evidence — no daemon in between. Its output never enters the model's context on its own, so a full pass stays cheap; favor short-output commands to keep it that way.

```mermaid
flowchart LR
    claude["Claude Code<br/>brain: read code, derive tests,<br/>judge pass/fail, write docs"] -->|"commands"| ab["cdp.py<br/>(hands & eyes)"]
    ab -->|"CDP (no daemon)"| chrome["Chrome<br/>(headless/headed)"]
    chrome --> targets["targets<br/>Web app · NetSuite Suitelet · APEX"]
    ab -.->|"a11y / console<br/>(short output, token-safe)"| claude
    ab -.->|"screenshot (file)"| shots["shots/<br/>(artifact, not context)"]
    claude --> out1["QA verdict<br/>qa-report.md"]
    claude --> out2["Docs PDF<br/>user-guide / bug-report"]
```

Full diagrams for every flow are in [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md).

## Flows

| Flow | Steps | Output |
|---|---|---|
| Smoke QA | `nav` → `wait "<page-specific condition>"` → walk happy path → `console` empty | pass / fail |
| Functional QA | action → `click` / `fill` → assert state with `get` / `is` / `wait` | verdict per step |
| Visual regression | `steady` → `shot` → `diff <baseline> <current>` | `diff.png` |
| Error surfacing | `console` after every key step, `lens netlog` for the network layer | errors surface, not silent |
| UX/UI review | `lens layout` · `responsive` · `theme` · `focus` | findings only, `[]` means clean |
| Empty / error screens | `run` a script with `stub <url> <status>` | the state you cannot reach with real data |
| User-guide PDF | walk flow, highlight, screenshot → `guide-template.html` → `pdf` | guide PDF (cover, TOC, page numbers) |
| Bug-report PDF | repro, evidence, severity → `bug-report-template.html` → `pdf` | bug PDF (Steps/Expected/Actual) |

Golden rule: a command that exits 0 only means it was *sent* — always assert the resulting state, and never read `UNVERIFIED` as a pass. Details in [`references/gotchas.md`](references/gotchas.md).

## Features

- **One pass, two outputs.** A single run gives you the QA verdict and the docs together, so nothing needs a second walkthrough.
- **Real pages, not mocks.** It drives actual Chrome over CDP against any web app, including NetSuite Suitelets and Oracle APEX, headless or headed.
- **Deliberate test design.** A Phase 0–3 method turns code and acceptance criteria into a coverage matrix, and states up front which cases a browser can verify and which must come from a code review.
- **Seven QA layers.** Smoke, functional, visual regression, error surfacing, a11y, perf, and a UX/UI lens that catches horizontal overflow, tap targets under 24×24, unreadable dark mode, and broken Tab order.
- **Guards against silent failures.** The traps that let automation pass when it shouldn't (below-fold clicks, a fake `✓ Done`, `os 10060`) are written up with reproductions and fixes.
- **Token-aware.** Assertions are short commands and screenshots are saved to files, so testing a large app doesn't fill the context window.
- **Reproducible specs.** Test cases live as YAML with `requirement` and `acceptance` fields, so a requirement, its test, and its guide share one id.
- **Documents that ship.** User guides and bug reports export to PDF with a cover, table of contents, page numbers, and highlighted screenshots.
- **Evidence per step.** Capture screenshots and structured results that can be reviewed without a daemon, dashboard, or video dependency.
- **One process per batch run.** `flow-runner.py` validates the flow, pins one target, and keeps one
  bounded `cdp.py session --jsonl` process/WebSocket for every step.
- **Fits a team.** A lifecycle playbook, a release gate, and a RACI table live in [`docs/TEAM-PROCESS.md`](docs/TEAM-PROCESS.md).

## Gotchas it protects against

| Trap | Symptom | Fix |
|---|---|---|
| `click` below the fold (≤0.27) | `✓ Done` but no-op — **fixed on 0.3x, which auto-scrolls** | `scrollintoview <sel>` before `click` — now a safe habit, still needed on old/mixed versions |
| Don't trust `✓ Done` | command succeeds but has no effect | assert state after every action (`wait` / `get url` / `get text`) |
| `os error 10060` | `wait --text` / `wait <selector>` flakes on Windows | use `wait --load networkidle` + short state checks (NetSuite: `wait --fn "jQuery.active===0"` — networkidle never settles there) |
| headless has no Thai font | injected Thai labels render as boxes | put Thai text in the HTML, bake only the ring into the image |
| `pdf` double-pagination | paged.js PDF gets alternating blank pages | fit `@page size` + `.pagedjs_page` margin on screen only |

Full detail with evidence: [`references/gotchas.md`](references/gotchas.md).

## Install

Option A, one file: download `teibto-browser-qa.skill` from the [Releases](https://github.com/Teibto/teibto-browser-qa/releases) page and install it through the Claude Code skill installer.

Option B, clone into your skills directory:
```bash
git clone https://github.com/Teibto/teibto-browser-qa.git ~/.claude/skills/teibto-browser-qa
```

Then install the driver's dependencies:
```bash
py -m pip install -r requirements.txt             # flow runner + repo scripts
py -m pip install websocket-client pillow numpy   # CDP driver; pillow/numpy only for visual diff
```

`cdp.py` ships with the team skills (`~/.claude/skills/netsuite-qa-browser/references/cdp.py`); point `NS_CDP` elsewhere if you vendor it into a project. Requirements: Chrome, Python 3.10+, and `git` only if you build the `.skill` bundle. Full setup and every command: [`references/commands.md`](references/commands.md).

When upgrading from the old name, update callers first and then remove
`~/.claude/skills/agent-browser-qa`; do not keep both skill directories installed.

Maintainers: the `.skill` bundle is a build artifact and is not committed. Rebuild it with `python scripts/build-skill.py` and attach the output to a GitHub Release.

## Quick start

Confirm your setup with a short smoke run: open a page, assert, check for errors, screenshot.

```bash
NS_CDP="$HOME/.claude/skills/netsuite-qa-browser/references/cdp.py"
export CDP_PORT=9400
AB(){ py "$NS_CDP" "$@"; }

chrome --user-data-dir=/tmp/qa-profile --remote-debugging-port=$CDP_PORT --no-first-run about:blank &
until curl -sf "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null; do sleep 1; done

AB nav https://example.com 2
AB get text title          # -> Example Domain
AB console                 # -> []   (empty = no page errors so far)
AB shot hello.png          # evidence file: the image, not context
```

Expect the title to contain `Example Domain` and `console` to print `[]`. If `console` **errors** instead of printing `[]`, the page was not opened with `nav`, so nothing is watching — that distinction is deliberate (see [`references/gotchas.md`](references/gotchas.md) #2).

Keep the Chrome you launched and reuse it — the profile directory holds the login, so a persistent one costs you the sign-in exactly once. If a command reports that the CDP port is not answering, Chrome died: check with `curl http://127.0.0.1:$CDP_PORT/json/version` and relaunch. There is no daemon and no session file to clear.

For a real multi-step flow, see [`examples/saucedemo.yaml`](examples/saucedemo.yaml) and [`references/flow-spec.md`](references/flow-spec.md).

### Batch a flow through one CDP session

Pin the page target first; shared mode deliberately refuses to guess a tab:

```powershell
$env:TGT_ID = '<page target id>'
$env:TEIBTO_CDP_SCRIPT = 'D:\path\to\teibto-dev-standards\scripts\cdp.py'
'{"username":"standard_user","password":"..."}' |
  py scripts/flow-runner.py --flow examples/saucedemo.yaml --out runs/manual --vars-json -
```

The runner writes `run-log.jsonl`, `qa-report.md`, and `shots/`. Secrets travel over stdin and are
redacted from events/reports. It stops on command, wait, assertion, screenshot, console, or transport
failure; an unasserted state-changing action is `UNVERIFIED`, never `PASS`.

Optional local UI: set `TGT_ID` (or enter it in the page), then run `node app/server.js` and open
`http://127.0.0.1:4173`. The server binds locally, uses the same runner, and has no browser daemon,
dashboard, video, or ffmpeg dependency.

## Project structure

```
teibto-browser-qa/
├── README.md                      this file
├── SKILL.md                       overview, golden rules, workflow
├── CLAUDE.md                      orientation for an agent/dev working on the repo
├── CONTRIBUTING.md                the development loop + how to cut a release
├── docs/
│   ├── ARCHITECTURE.md            workflow diagrams (mermaid) for every flow
│   └── TEAM-PROCESS.md            team playbook: lifecycle, release gate, RACI
├── references/                    working notes (Thai)
│   ├── gotchas.md                 silent-failure traps and fixes
│   ├── test-design.md             what to test (adversarial coverage, Phase 0-3)
│   ├── commands.md                command reference, token discipline, batch
│   ├── ux-lens.md                 layer 7: the lenses, and how each one can lie
│   ├── cdp-limits.md              what CDP cannot check at all, and what to do instead
│   ├── configure.md               changing real settings through the screen (not QA)
│   ├── flow-spec.md               test cases as repeatable flow YAML
│   └── pdf-reports.md             paged.js recipe (TOC, page numbers, fixes)
├── assets/
│   ├── guide-template.html        user-guide PDF (edit the data array)
│   ├── bug-report-template.html   bug-report PDF (edit the bugs array)
│   ├── highlight.js               inject a highlight ring before screenshot
│   └── pointer.js                 place a pointer ring on still evidence
├── examples/
│   └── saucedemo.yaml             runnable flow (happy path + adversarial)
├── schemas/
│   └── flow.schema.json           authoritative, fail-closed executable-flow schema
├── app/
│   ├── server.js                  local-only UI/API (SSE + cancellation)
│   └── public/index.html          flow editor and run monitor
├── qa/
│   └── _template/coverage.yaml    coverage manifest starter (release gate)
├── self-test/                     mechanical claim checks (drift detector)
│   ├── smoke-test.sh              syntax/recipe/reproducible claims + efficiency gates
│   └── pdf/pdf-test.sh            PDF pagination A/B
└── scripts/
    ├── flow-runner.py             one flow → one pinned bounded CDP JSONL session
    ├── build-skill.py             build the installable .skill bundle
    ├── validate-skill.py          fail-closed identity + flow validation
    ├── coverage-check.py          release gate as an exit code
    └── release-summary.py         roll every coverage.yaml into one sign-off table
```

## Scripts

Python tooling (`pip install -r requirements.txt`, PyYAML):

| Script | What it does | Usage |
|---|---|---|
| `scripts/flow-runner.py` | Validate and execute a YAML flow through one pinned `cdp.py session --jsonl`; emit JSONL events, report, and screenshots. | `python scripts/flow-runner.py --flow <flow.yaml> --out <dir> --target-id <id>` |
| `scripts/build-skill.py` | Bundle the skill into `teibto-browser-qa.skill` (a git-ignored build artifact attached to Releases). | `python scripts/build-skill.py` |
| `scripts/coverage-check.py` | Release gate → exit code: reads a `qa/<feature>/coverage.yaml`, returns 0 pass / 1 fail / 2 malformed. | `python scripts/coverage-check.py qa/<feature>/coverage.yaml` |
| `scripts/release-summary.py` | Roll every `qa/*/coverage.yaml` into one QA-Lead sign-off table. | `python scripts/release-summary.py [qa_dir]` |

Mechanical checks live in [`self-test/`](self-test) — run `bash self-test/smoke-test.sh` after any Chrome or `cdp.py` version bump; it prints its own pass/fail count against a real browser. It checks the claims *this skill* makes; the driver's own suite (`tests/test-cdp.sh` in [`Teibto/teibto-dev-standards`](https://github.com/Teibto/teibto-dev-standards)) covers `cdp.py` itself, and the two are deliberately not mirrored. Details in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Glossary

| Term | Meaning |
|---|---|
| **One pass, two outputs** | A single walk of the happy path yields both a QA verdict and documentation material. |
| **QA layers (1–7)** | Smoke · Functional · Visual regression · Error surfacing · a11y · Perf · UX/UI lens — each opt-in per scenario. See [`references/ux-lens.md`](references/ux-lens.md) for layer 7. |
| **`PASS` / `FAIL` / `UNVERIFIED`** | Every lens returns one of three verdicts. `UNVERIFIED` means the check could not run — it is never reported as a pass. What CDP cannot check at all is listed in [`references/cdp-limits.md`](references/cdp-limits.md). |
| **Flow YAML** | A test case stored as a repeatable file (`requirement` + `acceptance` + scenarios). See [`references/flow-spec.md`](references/flow-spec.md). |
| **Coverage manifest / gate** | `qa/<feature>/coverage.yaml` maps each Acceptance Criterion to the scenario that proves it; `coverage-check.py` turns it into a pass/fail exit code. |
| **Claims audit** | The ledger in [`docs/CLAIMS-AUDIT.md`](docs/CLAIMS-AUDIT.md) recording which claim is measured / verified / inferred / version-pinned. |
| **Golden rules** | The four silent-failure guards in `SKILL.md` §2 (scroll before click, don't trust `✓ Done`, avoid long-poll `wait`, black window ≠ GPU). |

## More docs

- [`CLAUDE.md`](./CLAUDE.md) — orientation for an agent/dev working on the repo (mental model, file map)
- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — the development loop, self-test, and how to cut a release
- [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — architecture and workflow diagrams for every flow
- [`docs/TEAM-PROCESS.md`](./docs/TEAM-PROCESS.md) — team playbook: lifecycle, release gate, RACI, artifacts
- [`references/gotchas.md`](./references/gotchas.md) — traps and fixes
- [`references/test-design.md`](./references/test-design.md) — what to test (adversarial coverage)
- [`references/commands.md`](./references/commands.md) — command reference and batch
- [`references/flow-spec.md`](./references/flow-spec.md) — test cases as repeatable flow YAML
- [`references/pdf-reports.md`](./references/pdf-reports.md) — how to make PDFs (paged.js)

## Credits

This skill is a playbook around an upstream tool; it does not reproduce or replace the CLI.

- [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser) — the Rust CLI this skill was originally built on. It is no longer a dependency; credit and license for the original CLI belong to the upstream authors.
- [`Teibto/teibto-dev-standards`](https://github.com/Teibto/teibto-dev-standards) — home of `cdp.py`, the shared CDP driver this skill now drives Chrome with.
- [saucedemo.com](https://www.saucedemo.com) — the Sauce Labs demo app used for examples and evidence runs.
- [Paged.js](https://pagedjs.org/) — PDF pagination.

## License

[MIT](LICENSE) © 2026 Wichit Wongta.
