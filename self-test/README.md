# Browser claim self-test

`smoke-test.sh` drives a real Chrome through canonical `cdp.py` and fails when an operational claim
used by this skill drifts. It launches a temporary profile on dedicated port `9395` and tests only
local `file://` fixtures.

## Run

```bash
NS_CDP=/path/to/cdp.py bash self-test/smoke-test.sh
```

Requirements: Chrome, Python, and `websocket-client`; visual diff checks additionally need Pillow and
NumPy. Missing Chrome/driver dependencies produce an explicit `SKIP`, while a started harness returns
non-zero on any failed assertion.

## Current checks

- `get` argument order, missing-element sentinel, counts, and visible/enabled semantics;
- filtered `a11y` refs and trusted click through a ref;
- shared eval scope and the IIFE workaround;
- below-fold click auto-scroll plus handler execution;
- page-scoped console collection and reset on navigation;
- bounded wait success/timeout behavior;
- command-scoped iframe selection;
- element screenshots, DSF behavior, and missing-selector failure;
- visual `SAME`/`DIFFERENT` verdicts and exit codes when optional dependencies exist;
- connection-scoped overrides inside `run`;
- UX lens `PASS`/`FAIL` and `UNVERIFIED` behavior;
- PDF-template escaping against stored script payloads;
- `about:blank` diagnosis;
- `document.fonts.check()` reporting missing families as present, and the width-baseline method not
  producing a false positive;
- `requestAnimationFrame` suspended in a background tab and resumed once the tab is in front;
- read-only probe batching and template scoped-read measurements.

The harness is a driver-drift detector, not the runner integration suite. Runner protocol, capture,
redaction, async outcome waits, and telemetry are covered by `tests/test_flow_runner.py` and
`tests/test-flow-runner-live.sh`.

## PDF pagination test

```bash
bash self-test/pdf/pdf-test.sh
```

This renders controlled documents through `cdp.py pdf` and inspects page counts with PyMuPDF. It
checks the paged.js double-pagination fixes and keeps non-reproduction of the known bad fixture
inconclusive rather than turning absence of a reproduction into a false pass.

## Second-engine dialog gate

```bash
bash self-test/engine2/dialog-test.sh
```

Drives `engine2/dialog-page.html` through BrowserSkill (`bsk`) and fails when the `handled` value it
reports for `alert`/`confirm`/`prompt`/`beforeunload` disagrees with the DOM, when the observed policy
differs from the pinned `ENGINE2_EXPECT_*` values, when the first command after `beforeunload` does not
answer within `ENGINE2_LIVENESS_S`, or when the daemon pid changes across `ENGINE2_ROUNDS` (default 20).
It needs `bsk` on `PATH`, a daemon already started by the host (`bsk daemon start --foreground`), and
one connected browser — or `ENGINE2_BROWSER=<instance_id>` when several are connected, so the dialog
fixture never lands in someone's everyday browser by accident; anything missing is an explicit `SKIP`. The script
never starts the daemon itself and never pipes `bsk` output. Re-run it on every `bsk`, extension, or
Chrome bump: a changed dialog policy turns it red on purpose so BAS §4.2 is re-decided, not inherited.

`bash self-test/engine2/runner-test.sh` drives the same fixture through `flow-runner.py --engine bsk`:
`flow-read.yaml` must end `PASS` with exit 0, and `flow-confirm.yaml` must end `PASS` with a `confirm -> dismiss`
dialog event: the in-page guard answered NO and the fixture shows `false`. Same `SKIP` conditions as above, plus PyYAML/jsonschema.

`python self-test/engine2/contention-matrix.py` replays what several agents do to one browser and
fails when sharing stops holding. Ten scenarios drive `flow-runner.py` through `bsk` for real: two and
six runs in one Agent Window, a peer opening a focused tab, a peer re-activating its tab every 150 ms,
a window stopped mid-run, a registry pointing at a reaped session, a corrupt registry, a stale
`TEIBTO_BSK_SESSION`, a lease holder killed mid-command, and the run's own tab closed under it. Each
fixture page is one flat colour, so the harness also checks **which page is in the screenshot** — a run
that quietly photographs a colleague's tab passes every exit-code check and is exactly the defect this
gate exists for (it caught #118, #120, #122 and #124).

It redirects the session registry and the lease directory into a temporary folder, opens only its own
Agent Windows, closes every one of them on the way out, and serves its fixtures on a free loopback
port. Missing `bsk`/daemon/browser is a `SKIP`; several connected browsers need `ENGINE2_BROWSER`.
Faults are injected only once the run's own `run-log.jsonl` proves it is mid-flight, and a fault that the session refuses while the run holds it (`session_busy`) is re-sent until it lands — a scenario that could not interrupt anything reports FAIL instead of a quiet pass. Without Pillow the colour checks report as skipped rather than passing silently. Expect roughly two
minutes and one Agent Window at a time. Re-run it on every `bsk`, extension or Chrome bump, and after
any change to the lease, the tab pinning or the capture path.

Run the browser harness after any Chrome or `cdp.py` bump and before changing `commands.md`,
`gotchas.md`, the PDF templates, or their behavioral claims. Current provenance is maintained in
[`docs/CLAIMS-AUDIT.md`](../docs/CLAIMS-AUDIT.md).
