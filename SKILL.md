---
name: agent-browser-qa
description: >-
  Drive a real browser (agent-browser, CDP) through a web flow and produce QA results +
  documentation from the live run. Trigger for: smoke-test/QA a web app flow (login,
  checkout, wizard, form, grid), click-through with screenshots per step, visual
  check/regression diff, verify a form/row actually saved, test Suitelet/APEX/any page,
  or turn a run into a user-guide/bug-report PDF. English or Thai, headless or headed,
  even when "agent-browser" isn't named. NOT for writing Playwright/Cypress code or CI
  pipelines; NetSuite record-form QA / user guides → skill netsuite-ui-qa-testing (this
  skill keeps generic apps + non-record NetSuite pages). Read references/gotchas.md
  before driving the browser.
---

# agent-browser QA & Docs

`agent-browser` = Rust CLI ([vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser))
that drives Chrome over CDP and outputs an accessibility tree + element refs (`@e1`) that an LLM
reads easily. **The CLI itself costs no tokens — tokens are only spent when you feed its output
back into context.**

**Roles:** Claude = the brain (read code → derive tests → judge pass/fail → write docs).
agent-browser = the hands & eyes (drive the browser + capture evidence; it decides nothing).

**Principle — one pass, two outputs:** walk the happy path once → get both (1) a smoke verdict and
(2) raw material for a user guide / bug report.

**What to test (beyond the happy path):** test *design* is a brain activity (read code → decide
which cases to fire) — cheap, never touches the browser. **All adversarial coverage lives there**,
so it doesn't conflict with token discipline: execution still uses the same short commands. The
happy-path pass yields guide + smoke; adversarial checks are *separate* passes that return **only
bug findings**. **Read `references/test-design.md`** when scope goes beyond smoke (Phase 0 system
map → coverage matrix → edge cases → the split of what runs in-browser vs. what must be derived
from code).

---

## 1. Install (first time)

```bash
npm install -g agent-browser     # or brew / cargo install agent-browser
agent-browser install            # download Chrome for Testing (~186MB, once)
agent-browser --version          # confirm
```

Version-matched built-in guide (better than guessing from --help): `agent-browser skills get core --full`

---

## 2. Golden rules — read before driving the browser (most important)

These traps make automation **fail silently, with no error** — full detail + evidence in
`references/gotchas.md`, but keep these five in mind at all times:

0. **Set a per-terminal session BEFORE the first command** so parallel terminals don't share one
   browser (else two runs click over each other + leak zombie daemons). bash:
   `export AGENT_BROWSER_SESSION="cc-${CLAUDE_CODE_SESSION_ID:0:8}"` at the head of the `&&` chain
   (harness shells are -NoProfile/non-interactive, so re-set it inline in every bash call, or pass
   `--session "cc-<sid8>"`). Parallel NetSuite (shared login) also needs a per-terminal `--profile`
   dir — Windows locks one profile to one Chrome. Detail + cleanup recipe: #10 in `references/gotchas.md`.

1. **`click` auto-scrolls on 0.3x — but still assert.** On agent-browser **≤0.27** a below-fold
   `click` returned `✓ Done` and did nothing (silent no-op); **0.32.1 auto-scrolls the element into
   view and fires the handler** (verified 2026-07-17: below-fold button, `scrollY` 0→1089). So
   `scrollintoview <sel>` before `click` is now a *safe habit*, not a hard requirement — keep it for
   below-fold buttons on old/mixed versions. Either way, prove the effect with rule #2.
2. **Don't trust `✓ Done`** — always assert the resulting state (`wait` element / `get url` /
   `get text .badge`). After a click, prove the effect happened; a successful command return is not proof.
3. **Avoid long-poll `wait --text` / `wait <selector>`** on Windows (intermittent `os error 10060`)
   → use `wait --load networkidle` + check state with short commands instead.
   (ห้ามใช้ networkidle บน NetSuite — โพลไม่จบ; ใช้ `wait --fn "window.jQuery && jQuery.active === 0"`
   ดู skill netsuite-qa-browser)
4. **A black headed window = 3 causes, not just "GPU" — check `get url` first.**
   `about:blank` → page never navigated (benign) → `open` again; a real page but covered/backgrounded
   → relaunch with the `qa-browser.ps1` stability flags. CDP `screenshot` stays valid either way.
   Mechanisms + the flag set: #9 in `references/gotchas.md`.

Extra: if native `click` / `find ... click` is still flaky, drive with a **JS click**
`eval "document.querySelector('SEL').click()"` (always reliable — QA the app's real clickability separately).

---

## 3. Token discipline (prevent context overflow)

- For assertions use only **short-output commands**: `wait`, `is visible/enabled`, `get value/text`,
  `get count`, `errors --json`, `console --json`.
- **Never** feed a whole-page `snapshot` or raw `get html` back into context. If you must snapshot,
  filter it: `snapshot -i` (interactive-only) or scope it `-s "#sel"`.
- **screenshot = always a file** (`--json` returns just the path) — the path may enter context, the
  image may not (unless truly necessary).
- Cap output: `--max-output 50000`.

Full command reference + commonly-missed syntax → `references/commands.md`

**Verify the command/syntax claims machine-side:** `self-test/smoke-test.sh` (checks against a real
agent-browser — re-run on any agent-browser/Chrome version bump = drift detector). Which claims are
verified vs inferred vs version-pinned: `docs/CLAIMS-AUDIT.md`.

---

## 4. Standard workflow (one pass, two outputs)

```
1. open <url> → wait --load networkidle   (NetSuite: ห้าม networkidle — ใช้ wait --fn jQuery.active===0)
2. before each action: screenshot (file) as evidence / guide material
3. action: scrollintoview → click/fill (or JS click) with ref @eN or a semantic locator
4. assert the result with a short command (golden rule #2)
5. errors --json → if non-empty = FAIL, record the error (no silent fallback)
6. end of flow: write 2 files — qa-report.md (verdict) + user guide / bug report
```

QA layers: (1) Smoke = happy path completes + errors empty · (2) Functional = assert state ·
(3) Visual = `diff screenshot --baseline` · (4) Error surfacing = `errors`/`console` after every key step ·
(5) a11y = inject axe-core, return count + top N (`references/a11y-layer.md`) ·
(6) Perf = save/load timing vs budget (`references/perf-layer.md`). Layers 5–6 are opt-in per scenario
(`a11y`, `perf_budget` in flow.yaml) and return only short numbers — never a full node/timing dump.

**Store test cases as repeatable files** (regression/repro) → write them as flow YAML:
`references/flow-spec.md`. **Fewer process spawns + fewer `os 10060` stalls:** `batch` several
commands into one invocation (`@eN` refs persist across them) instead of one CLI call each; run a
pre-flight health-check before a long flow → `references/commands.md`.

Suggested artifact layout:
```
qa/<feature>/
  qa-report.md          # verdict + step table + errors
  shots/                # screenshot per step (artifact, not context)
  guide/                # generated docs (HTML/PDF) + shots
```

---

## 5. Produce PDF docs (user guide / bug report)

Produce ship-ready docs (cover + logo, table of contents + page numbers, FAQ, glossary) from a real
run — ready-made templates + a page-number-correct PDF recipe are included. **Read
`references/pdf-reports.md` before making a PDF** (there are paged.js + Chrome printToPDF traps that
cause alternating blank pages).

**Pipeline boundary:** this skill owns the GENERIC guide/bug-report PDF pipeline (paged.js +
`assets/guide-template.html`). NetSuite record-form guides use netsuite-ui-qa-testing's own pipeline
(agent-browser pdf + PyMuPDF `add-pdf-outline.py` + `toc_tools.py` two-pass + DOCX) — do not mix them.

- `assets/guide-template.html` — document-style user guide (cover, breadcrumb, highlighted
  screenshot, field table, what/why/effect-on-system, FAQ, glossary). Edit only the data array.
- `assets/bug-report-template.html` — bug report (cover, TOC + severity, Steps/Expected/Actual/
  Evidence/Workaround/Impact). Edit only the bug array.
- `assets/highlight.js` — snippet to inject a click-target highlight ring into a screenshot (ring-only, no text).
- `assets/pointer.js` — snippet `point(sel)` that places a pointer ring marking the focus/click spot (for video/live, see §6).

**Do not bake Thai text into screenshots** (headless has no Thai font). Full PDF recipe (paged.js,
the double-pagination fix, page-number verification) → `references/pdf-reports.md`.

---

## 6. Record video / watch live

Record a flow as video (`record start/stop`, **needs ffmpeg** — restart the daemon after installing)
or watch it live without ffmpeg (`dashboard start` → `http://localhost:4848`, or `stream enable`).
Because CDP has no real cursor, inject a rendered pointer ring (`assets/pointer.js`) before each
action so the screencast shows where it happens. Full recipe + traps → `references/video-and-live.md`.

---

## Specific targets (NetSuite / APEX)

- **NetSuite:** log in via an already-logged-in Chrome profile (`--profile "<your-profile>"` to
  avoid repeat 2FA); elements inside an iframe → `frame "#sel"` before snapshot, then `frame main`;
  async loads → `wait --fn "window.jQuery && jQuery.active === 0"`.
- **Oracle APEX:** use an isolated `--session <name>`; dynamic Interactive Grid cells/buttons →
  semantic locators `find label "..." fill "..."` / `find role button click --name "..."`; test Thai
  input; `vitals --json` (if present in that version — check first).
