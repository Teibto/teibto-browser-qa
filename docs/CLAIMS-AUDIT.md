# Claims Audit — teibto-browser-qa

Current ledger for operational claims that can change a QA verdict. Historical transport/version
rounds were removed from the active documentation in issue #54; their full provenance remains in Git
history and `CHANGELOG.md`.

## Evidence boundary

- Browser QA release under review: `v2.2.0` (`1434cb6`).
- Canonical released driver: `teibto-dev-standards v0.83.0` (`3868281`).
- Foreground-ready driver candidate: `teibto-dev-standards@56b4e788ab80807c3f62b43b88a151a52a96df8e`
  (PR #277), `scripts/cdp.py` blob `6d9dcc7ea5a8a9a36a7138945dbece8a86a9177f`.
- Performance runs: Windows host, Chrome `151.0.7922.140`, 2026-08-22.
- Issue #69 revalidation: Windows host, Chrome `151.0.7922.174`, 2026-08-30; local driver file
  blob `21bf0cb72adaee04633c21a1c5758cbbf7a4da96` from worktree commit `b745196`.
- Issue #74 revalidation: same Windows host, Chrome `151.0.7922.174`, 2026-08-30; foreground-ready
  candidate commit/blob above. The candidate is not a released dependency until its upstream review,
  CI, and release gates pass.
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
| Runner requires protocol v3+, verifies `input-settle=none`, and requires foreground-ready fields | verified, version-pinned | missing/hidden unit cases plus 20-run two-tab live consumer gate against candidate `56b4e788` |
| The exact pinned target is visible before any flow step while the competing tab becomes hidden | verified, version-pinned | canonical two-tab gate plus browser live test that re-hides the target before every run |
| Structured per-command dialogs are attributed once to the causing step | verified, version-pinned | unit structured-payload/malformed-payload cases plus v0.83.0 and candidate live alert fixtures |
| Event-bound navigation waits for the new main-frame commit/load and fails on cancel/timeout | verified | canonical `tests/test-cdp.sh` T16c–T16j; runner live test |
| Collector is installed before next-document scripts and resets per page | verified | canonical T15/T16d; `self-test/smoke-test.sh` console checks |
| Fast input settle is scoped to direct runner input; `pick`/`lens` retain normal settle | verified | canonical session probe T19u/v |
| Async fill/click outcomes remain bounded and observable | verified | delayed 150 ms input normalization and 300 ms trusted-click fixture in `tests/test-flow-runner-live.sh` |
| Runner telemetry separates driver duration, runner wall time, attempts, and failing phase | verified | unit event assertions plus live `run-log.jsonl` parsing |
| `--stdout summary` keeps the complete artifact but emits terminal output only | verified, measured | unit stream/artifact comparison; issue #69 o200k_base measurement below |
| Step `perf_budget_ms` measures action through observable wait/assert and excludes capture/startup | verified | pass/exceedance unit tests with a delayed capture |
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
| issue #74 foreground-ready candidate | 20 fresh child sessions; target hidden before every session | 653.229 ms | 20/20 pass; p95 739.154 ms |

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

The final issue #74 live set used one temporary Chrome instance with a competing tab. Before each of
20 sessions the harness activated the competing tab and proved the pinned target hidden; after runner
startup it proved the pinned target visible and competitor hidden. Median/p95 milliseconds were:
startup 294.828/414.997, open 41.049/67.821, fill 192.673/226.710, click 432.772/467.162,
step flow 653.229/739.154, and total run 972.063/1,198.926. A preceding 20-run set also passed 20/20
(median step flow 675.275 ms), so the final set was not a lone successful sample.

The motivating anonymized NetSuite Suitelet/MRP evidence is recorded in canonical issue #276: the
same-result foreground/background pairs were 34.784/389.246 seconds (about 11.2x) and
31.094/160.035 seconds (about 5.1x). These are historical sandbox observations, not a controlled
driver A/B and not a fresh authenticated NetSuite rerun. The mechanism is supported separately by
the hidden/visible target proof and the client loop's `setTimeout(0)` behavior; no customer identifier
is needed or retained here.

Canonical PR #277 measured readiness overhead with 30 alternating same-host pairs: baseline/candidate
median wall time 220.358/233.825 ms, +13.467 ms (about 6.1%) per session. Its synthetic headless
fixture did not reproduce the background timer clamp, so this repository makes no synthetic speedup
claim. The large speed-risk finding comes from the NetSuite observations above; the fixture gates the
foreground invariant and bounds its startup cost.

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
