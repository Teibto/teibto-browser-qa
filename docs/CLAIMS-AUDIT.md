# Claims Audit — teibto-browser-qa

Current ledger for operational claims that can change a QA verdict. Historical transport/version
rounds were removed from the active documentation in issue #54; their full provenance remains in Git
history and `CHANGELOG.md`.

## Evidence boundary

- Browser QA release under review: `v2.2.0` (`1434cb6`).
- Canonical driver: `teibto-dev-standards v0.83.0` (`3868281`).
- Performance runs: Windows host, Chrome `151.0.7922.140`, 2026-08-22.
- Issue #69 revalidation: Windows host, Chrome `151.0.7922.174`, 2026-08-30; local driver file
  blob `21bf0cb72adaee04633c21a1c5758cbbf7a4da96` from worktree commit `b745196`.
- The pinned `scripts/cdp.py` blob is `28ca9e4a6475639f102d24a1cb2aab2dc736a3c9`, identical to
  the blob at canonical tag `v0.83.0`.
- Driver internals are owned by canonical `tests/test-cdp.sh`; this repository keeps thin consumer
  checks in `self-test/smoke-test.sh` plus runner unit/live tests.

Status terms:

- **verified** — reproduced by a deterministic test;
- **measured** — observed number with method/environment recorded;
- **version-pinned** — true for the recorded Chrome/driver and must be rechecked on a bump;
- **inferred** — plausible but not reproduced; never use alone for a `PASS`/`FAIL` verdict;
- **principle** — a reporting/safety rule rather than a browser behavior.

## Current driver and runner claims

| Claim | Status | Evidence |
|---|---|---|
| Runner requires `teibto-cdp-jsonl` protocol v3+ and verifies `input-settle=none` | verified, version-pinned | unit incompatibility cases plus live consumer gate against v0.83.0 |
| Structured per-command dialogs are attributed once to the causing step | verified, version-pinned | unit structured-payload/malformed-payload cases plus v0.83.0 live alert fixture |
| Event-bound navigation waits for the new main-frame commit/load and fails on cancel/timeout | verified | canonical `tests/test-cdp.sh` T16c–T16j; runner live test |
| Collector is installed before next-document scripts and resets per page | verified | canonical T15/T16d; `self-test/smoke-test.sh` console checks |
| Fast input settle is scoped to direct runner input; `pick`/`lens` retain normal settle | verified | canonical session probe T19u/v |
| Async fill/click outcomes remain bounded and observable | verified | delayed 150 ms input normalization and 300 ms trusted-click fixture in `tests/test-flow-runner-live.sh` |
| Runner telemetry separates driver duration, runner wall time, attempts, and failing phase | verified | unit event assertions plus live `run-log.jsonl` parsing |
| `--stdout summary` keeps the complete artifact but emits terminal output only | verified, measured | unit stream/artifact comparison; issue #69 o200k_base measurement below |
| Step `perf_budget_ms` measures action through observable wait/assert and excludes capture/startup | verified | pass/exceedance unit tests with a delayed capture |
| `allowed_origins` is enforced against the live URL after every step, not only against declared targets | verified | redirect and lookalike-host cases in `tests/test_flow_runner.py` |
| Origin comparison parses the URL, so a host that merely starts with an allowed origin is rejected | verified | `OriginHelperTests` suffix case plus the lookalike run |
| A step marked `risk: destructive` cannot run without `--allow-destructive`, and the session never starts | verified | blocked/allowed unit pair asserting the session counter |
| The origin check is excluded from `perf_budget_ms` | verified | budget run asserting `outcome_ms` below step `total_ms` with an `origin` phase present |
| A flow that declares no `allowed_origins` keeps its previous behaviour and pays no extra round trip | verified | no-policy run asserting `origin_gate: not-declared` |
| Missing/old driver fails as `DRIVER_INCOMPATIBLE` rather than using a silent fallback | verified | `tests/test_flow_runner.py` |
| Success/failure screenshots follow scenario/step capture policy | verified | runner unit tests and live fixture |

## Performance evidence

The comparison measures summed live step time, excluding Chrome startup:

| Sample | Runs | Median step flow | Result |
|---|---:|---:|---|
| main baseline (`teibto-browser-qa@3ecafee`, driver `6656b9c`) | 5 isolated runs | 4,373.865 ms | fixed navigation/input settling |
| protocol-v2 candidate | 20 fresh child sessions on one temporary Chrome target | 622.523 ms | 20/20 pass |
| issue #54 revalidation | 20 fresh child sessions on one temporary Chrome target | 972.687 ms | 20/20 pass |
| issue #69 current-host revalidation | 20 fresh child sessions on one temporary Chrome target | 618.904 ms | 20/20 pass |
| issue #68 exact v0.83.0 pin | 20 fresh child sessions on one temporary Chrome target | 743.579 ms | 20/20 pass; per-step alert dialog |

Measured improvement: **85.8%**. Candidate medians were startup 181.014 ms, open 30.552 ms, fill
171.488 ms, click 396.767 ms, and total run 823.390 ms. The fixture intentionally waits 150/300 ms
for application outcomes; those delays remain visible across action/wait timing rather than being erased.

The issue #54 revalidation medians were startup 208.707 ms, open 41.492 ms, fill 206.611 ms, click
739.543 ms, and total run 1,299.784 ms. The run verifies compatibility and records host variance; it
does not replace the controlled release comparison or create a cross-machine latency gate.

The issue #69 medians were startup 174.502 ms, open 24.486 ms, fill 215.526 ms, click 385.726 ms,
and total run 826.889 ms. The 618.904 ms step flow is 85.8% below the 4,373.865 ms historical baseline;
450 ms remains intentional fixture latency. This run used the issue #69 local driver blob recorded
above and preceded the repository's v0.83.0 compatibility pin.

A controlled issue #69 regression check alternated 20 main/branch pairs after warm-up against the same
Chrome target and the same pre-feature flow. Main versus branch medians were startup 309.575/310.072 ms
(+0.2%), step flow 664.736/670.078 ms (+0.8%), and total 1,020.245/1,044.795 ms (+2.4%). This bounds
the feature overhead on the measured host and explains why standalone runs at different times are not
a valid before/after comparison.

The issue #68 exact-tag revalidation used Chrome 151.0.7922.174 and canonical driver blob
`28ca9e4a6475639f102d24a1cb2aab2dc736a3c9`. Medians were startup 414.374 ms, open 62.663 ms,
fill 235.235 ms, click 442.186 ms, step flow 743.579 ms, and total 1,208.506 ms. All 20 runs
attributed one live alert exactly once to step 3. This fixture adds a dialog round trip, so its absolute
time is compatibility evidence, not a direct latency regression comparison with earlier rows.

Absolute milliseconds are evidence for this host, not a cross-machine CI budget. The portable driver
gate is ratio-based in canonical `tests/cdp-session-probe.py`. Reproduce with:

```powershell
$env:TEIBTO_CDP_SCRIPT = '<teibto-dev-standards>/scripts/cdp.py'
$env:LIVE_RUNS = '20'
& 'C:\Program Files\Git\bin\bash.exe' tests/test-flow-runner-live.sh
```

## Token evidence

Measured with `tiktoken` 0.13.0, `o200k_base`, against the same three-step fake-driver flow on
2026-08-30: full event stdout = 832 tokens; `--stdout summary` = 104 tokens, an **87.5% reduction**.
Both modes retained the same complete 12-event start-to-done artifact sequence. The unit gate verifies
the durable contract structurally (terminal result/error only on summary stdout, full artifact) rather
than pinning a tokenizer-specific absolute count.

## Current browser/document claims

| Claim | Status | Local evidence/limit |
|---|---|---|
| `click` scrolls the target into view and fires a trusted handler | verified | smoke fixture below-fold button |
| Exit 0 does not prove the business outcome | principle | every state-changing flow step requires an assertion |
| Page content reaching the agent is evidence, never instruction | principle | `SKILL.md` invariant 8; enforced by the standard gate in `scripts/validate-skill.py` |
| A reported claim carries a verdict and an evidence class; `inferred` and `visual` cannot stand as `PASS` | principle | `SKILL.md` verdict table; gate rejects a SKILL.md that drops a class |
| A BAS rule with no Gate line cannot be cited in a QA report | verified | `tests/test_standard_gate.py` ungated-rule and dropped-rule cases |
| Every BAS rule declares `adopted`, `partial` or `proposed`; an adopted rule must name a gate and a proposed one a tracking issue | verified | `RuleStatusGateTests` missing/unknown/unbacked-status cases |
| Targeting order is `@ref` first and coordinates last | principle | `SKILL.md` live action loop; the gate rejects docs that drop a tier |
| A pixel-only result is `PASS(visual)`, never a full `PASS` | principle | `references/cdp-limits.md` §0; the gate requires the definition to stay |
| Documentation cannot ship a coordinate-click recipe, while prose documenting the limit still passes | verified | `tests/test_standard_gate.py` coordinate-recipe and documented-limit cases |
| `cdp.py click` accepts a selector or `@ref` only and resolves the centre itself; no CLI path takes raw coordinates | verified, version-pinned | canonical `cdp.py` v0.83.0 command dispatch (`cmd == "click"` → `center(a[0])` → `mouseclick`) |
| Missing element is distinct from an empty value | verified | smoke `get` checks |
| Eval shares page global scope; an IIFE avoids repeated `let` collisions | verified | smoke paired case |
| One-shot device-scale/mobile override does not survive its WebSocket | verified, version-pinned | smoke paired `viewport`/`shot`; canonical driver tests own deeper behavior |
| `lens netlog` without `netlog on` is `UNVERIFIED`, never `PASS` | verified | smoke paired lens case |
| CDP console cannot prove absence of caught HTTP failures | verified | canonical console vs netlog paired test |
| PDF template data is HTML-escaped and script payloads do not execute | verified | smoke template payload case |
| paged.js fixes prevent the controlled double-pagination fixture | verified, version-pinned | `self-test/pdf/pdf-test.sh` with PyMuPDF |
| `about:blank` can explain an apparently black headed window | verified | smoke URL case |
| GPU/occlusion is the cause of a black headed window | inferred | not reproducible on the recorded host; diagnose URL and CDP screenshot first |
| Headless Thai font availability and native popup capture vary by host/Chrome | version-pinned | require a current render/manual evidence check |
| `document.fonts.check()` returns `true` for a family that is not installed, so it cannot prove presence | verified, version-pinned | smoke fonts case; Chrome 152.0.7977.84 headless and headed, 2026-09-14 (#85) |
| Width comparison against a generic of a different family (`serif`) detects an installed family; a `monospace` baseline on Windows is Consolas and misreports Consolas as absent | measured, version-pinned | #85 probe on Windows 11, Chrome 152: Consolas present vs `serif`, absent vs `monospace`; smoke covers the no-false-positive side |
| `requestAnimationFrame` callbacks do not run in a background tab (`document.hidden === true`) and run again once the tab is in front | verified, version-pinned | smoke background-tab rAF case; Chrome 152 headless and headed (#85) |
| A trusted CDP click can report success yet have no effect while its tab/window is not in front | inferred | observed 2026-08-23 and 2026-09-08 on TBTKB; other clicks succeeded with `document.hidden === true` in the same session; not reproduced; tracked in #74 |
| `shot --vw/--vh` leaves the window at the emulated size for later invocations while `devicePixelRatio` resets | measured, version-pinned | #85 probe, Chrome 152 headless and headed, canonical driver `fb1adc1` (shot metrics path unchanged since v0.83.0) |
| `eval`/`evalf` await a returned promise | verified, version-pinned | #85 probe; canonical `Runtime.evaluate` uses `awaitPromise=True` at v0.83.0 |
| lens `theme`/`focus` read the light DOM and the custom-element host, so shadow-DOM components can yield `text-invisible`/`no-focus-ring` false positives | measured, version-pinned | TBT-DS 1.46.1 page, 2026-09-08; confirm with `shot <sel>` and a `shadowRoot` probe before reporting |
| `el.focus()` on some custom-element hosts leaves `activeElement` on `BODY`; only keyboard Tab focuses the host | measured, version-pinned | `tbt-button`, TBT-DS 1.46.1, 2026-09-08 |
| `lens focus` reports `focus-stuck`/`unreachable-controls` on `<input type=date>` because Tab walks its date fields | measured, version-pinned | observed 2026-09-08; verify by pressing Tab 4–5 more times |

## NetSuite live-run findings

| Claim | Status | Evidence/limit |
|---|---|---|
| After a `click` that navigates to a page loading longer than ~10 s, an expression/`networkidle` `wait` fails with `WS_TIMEOUT` at ~10 s instead of at its own deadline | measured | SB2 `4089685_SB2`, 2026-09-19, driver `71b477a`: `wait.driver_ms=10012`; same page `nav --until=load` = 13,812 ms; fixed-sleep variant of the same flow passed 4/4. Reproduced once, no fixture yet — `gotchas.md` §20, driver issue `Teibto/teibto-dev-standards#396` |
| The evaluate stalls because the renderer is busy or its execution context is torn down mid-navigation | inferred | not separated; do not cite as cause |

## Second-engine live-run findings

| Claim | Status | Evidence/limit |
|---|---|---|
| A tuned customer + Sales Order create loop through `bsk` takes a median 47.7 s per pair (min 43.7, max 51.0), 20–28 CLI calls, no retries and no dialogs | measured | NetSuite SB2, bsk 0.3.0 + Chrome 152, 2026-09-19, n=6, 6/6 verified against the server-side record XML; harness lives under git-ignored `qa/` |
| The untuned script took 68.1 s through `bsk` and 64.6 s through one-process-per-command `cdp.py` (53 calls each); the gain came from waiting for `NS.form.isInited()` instead of re-firing the customer, not from the engine | measured | same day, n=1 per engine — direction only, not a benchmark of the engines; the runner's JSONL session was not part of the comparison |
| Per-command transport cost is about 33–58 ms for `bsk` and about 205 ms for one-process-per-command `cdp.py` | measured | ten trivial evaluates, three `bsk` samples and one `cdp.py` sample |
| A focused Agent Window is not faster than `--no-focus` for this loop | measured | 47.2 s vs 48.1 s mean, n=3 each |
| A person closing the Agent Window ends the session mid-run, and a save already clicked can still have landed | verified | daemon log `session removed: user closed Agent Window` twice in 12 runs; one orphaned Sales Order confirmed by server-side lookup. Runner maps it to `BSK_SESSION_LOST` |
| `--engine bsk` retries a detached-debugger failure only for commands that cannot act twice; `click`/`fill`/`pick`/`key`/`eval` are never retried | verified | `tests/test_bsk_engine.py` navigate-retried, click-not-retried and session-lost cases; removing the idempotent condition turns the click case red |
| Pre-filling the customer through the Sales Order URL saves about 3 s but breaks the item line | measured — rejected | 1 of 2 runs failed with `checkvalid` undefined although `NS.form.isInited()` was true |

## Engine policy

| Claim | Status | Evidence/limit |
|---|---|---|
| `cdp.py` is the primary engine; BrowserSkill (`bsk`) is admitted as a second engine only for sessions `cdp.py` cannot attach to | principle | owner decision 2026-09-19, issue #87; conditions in `docs/BROWSER-AGENT-STANDARD.md` §4 |
| Results obtained through the second engine are `inferred` until it has a version pin, a live compatibility gate, a run-log adapter, and negative dialog/`beforeunload` tests | principle | `docs/BROWSER-AGENT-STANDARD.md` §4.3; adapter and dialog gate exist (#89, #91), the pin is enforced by the runner, no CI job runs the live tests |
| `--engine bsk` refuses any step that is not explicitly read-only before the browser is touched, and fails a step when a `confirm`/`prompt`/`beforeunload` was auto-accepted | verified | `tests/test_bsk_engine.py` (fake CLI proves no `session start` happened); both gates removed one at a time turn the suite red; `self-test/engine2/runner-test.sh` against bsk 0.3.0 |
| A fully passing `--engine bsk` run reports `PASS(inferred)` and a non-zero exit, and rejects an unpinned daemon/extension | verified | `tests/test_bsk_engine.py`; live `runner-test.sh` |
| With several browsers connected, `--engine bsk` refuses to pick one: no choice is `BSK_BROWSER_AMBIGUOUS`, the chosen instance is passed to `session start --browser` and recorded in `session_ready` | verified | `tests/test_bsk_engine.py` ambiguous/chosen/unknown/single cases |
| `--engine bsk` emits the same run-log event types as the primary engine | verified | `tests/test_bsk_engine.py::test_same_event_types_as_primary_engine` |
| BrowserSkill is a CLI + daemon + MV3 extension that drives tabs over CDP and offers `observe` refs, `tab borrow`/`tab return`, `request-help`, read-only `console`/`network`, remote pairing, operation audit, and Windows x64 builds | version-pinned, inferred | read from the upstream docs and changelog at `Tencent/BrowserSkill` `fa953dc` (v0.3.0, 2026-09-16); **not executed here** — recheck on every pin bump |
| BrowserSkill auto-accepts every native dialog in an agent-controlled tab: `alert`, `confirm`, `prompt` (with its default text), and `beforeunload`; no setting changes this | verified, version-pinned | `self-test/engine2/dialog-test.sh`, 20 rounds, bsk 0.3.0 + extension 0.3.0 + Chrome 152, Windows, 2026-09-19; matches `chromium-cdp.ts:750` at `fa953dc`. Violates the `safe` dialog policy, hence the write/destructive ban in BAS §4.2 |
| The `handled` value BrowserSkill reports per dialog matches the outcome observed in the DOM | verified, version-pinned | same run: 80/80 dialog reports agreed with the fixture; negative case (fixture forced to disagree) fails the gate |
| BrowserSkill does not reproduce the `beforeunload` wedge or daemon death that retired the previous daemon (#34) | verified, version-pinned | same run: first command after `beforeunload` answered within 10 s in 20/20 rounds and the daemon pid was unchanged; negative case (impossible budget) fails the gate. Loopback fixture only — not exercised against NetSuite or a long session |
| `bsk` auto-starting its daemon from a shell whose output is piped leaves that shell hanging | inferred | observed once: `bsk doctor \| tail` never returned on Git Bash while the daemon it started kept running; not A/B tested. The self-test sets `BSK_AUTO_START=0`, writes to files, and never starts the daemon |

## Executable-flow authority

`schemas/flow.schema.json` is authoritative and rejects unknown fields. `fixtures`, `teardown`,
`retry_on`, `quarantine`, `a11y`, `perf_budget`, `mask_regions`, `diff_threshold`, and `ci_candidate`
are **not executable fields** in v2.1.0. Their recipes/state live outside the flow until schema,
execution behavior, reporting, and failure tests ship together.

Issue #69 adds the executable integer field `perf_budget_ms` at step level. The older proposed
scenario/object field `perf_budget` remains rejected; the two names are intentionally not aliases.

This rule closed contradictory documentation found in `test-data.md`, `a11y-layer.md`,
`perf-layer.md`, `visual-regression.md`, and `TEAM-PROCESS.md` during issue #54.

## Withdrawn claims

- "Transport is direct CDP only, with no second driver" was an unconditional team rule until issue #87.
  It is replaced by the engine policy above; the ban on *writing* a second driver in this skill stands.
- Operational instructions for the retired transport, session files, daemon recovery, recording, and
  old command shapes are historical and must not appear in current runbooks.
- Old-version claims that below-fold click does not auto-scroll were superseded by the canonical
  trusted-click behavior and current smoke test.
- A generic NetSuite `networkidle`/jQuery prescription was never A/B verified here and was replaced by
  page-specific observable waits.
- Proposed flow fields listed above were documentation proposals, not implemented behavior. Examples
  that presented them as accepted schema were removed.

## Revalidation rule

After any Chrome or canonical `cdp.py` bump, run unit tests, the live runner test, and
`self-test/smoke-test.sh`; run the PDF test when Chrome/PDF assets change. Update this ledger only from
the resulting evidence. Do not promote an inferred or unrun condition to `PASS`.
