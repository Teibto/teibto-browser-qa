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

Run the browser harness after any Chrome or `cdp.py` bump and before changing `commands.md`,
`gotchas.md`, the PDF templates, or their behavioral claims. Current provenance is maintained in
[`docs/CLAIMS-AUDIT.md`](../docs/CLAIMS-AUDIT.md).
