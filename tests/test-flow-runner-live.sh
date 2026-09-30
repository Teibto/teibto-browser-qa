#!/usr/bin/env bash
# Real Chrome compatibility check for flow-runner.py + the shared cdp.py session protocol.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CDP="${TEIBTO_CDP_SCRIPT:-${ROOT}/../teibto-dev-standards/scripts/cdp.py}"
[ -f "${CDP}" ] || { echo "SKIP: set TEIBTO_CDP_SCRIPT to teibto-dev-standards/scripts/cdp.py"; exit 0; }

CHROME=""
for candidate in \
  "/c/Program Files/Google/Chrome/Application/chrome.exe" \
  "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
  "$(command -v google-chrome || true)" \
  "$(command -v chromium || true)"; do
  [ -x "${candidate}" ] && { CHROME="${candidate}"; break; }
done
[ -n "${CHROME}" ] || { echo "SKIP: Chrome not found"; exit 0; }

PY=""
for candidate in py python3 python; do
  if "${candidate}" -c 'import jsonschema,websocket,yaml' >/dev/null 2>&1; then PY="${candidate}"; break; fi
done
[ -n "${PY}" ] || { echo "FAIL: Python needs PyYAML, jsonschema, websocket-client"; exit 1; }

export CDP_PORT="${CDP_PORT:-9411}"
HTTP_PORT=$((CDP_PORT + 100))
WORK="$(mktemp -d)"
PROFILE="${WORK}/chrome-profile"
CHROME_PID=""; HTTP_PID=""
cleanup() {
  [ -n "${HTTP_PID}" ] && kill "${HTTP_PID}" 2>/dev/null || true
  if [ -n "${CHROME_PID}" ]; then
    kill "${CHROME_PID}" 2>/dev/null || true
    wait "${CHROME_PID}" 2>/dev/null || true
  fi
  # Chrome helper processes may release profile files a moment after the parent exits on Windows.
  for _ in $(seq 1 10); do
    rm -rf "${WORK}" 2>/dev/null && break
    sleep 0.3
  done
}
trap cleanup EXIT

"${PY}" -m http.server "${HTTP_PORT}" --bind 127.0.0.1 --directory "${ROOT}/tests/fixtures" \
  >"${WORK}/http.log" 2>&1 &
HTTP_PID=$!
"${CHROME}" --user-data-dir="$(cygpath -w "${PROFILE}" 2>/dev/null || echo "${PROFILE}")" \
  --remote-debugging-port="${CDP_PORT}" --headless=new --no-first-run \
  --no-default-browser-check about:blank >"${WORK}/chrome.log" 2>&1 &
CHROME_PID=$!

for _ in $(seq 1 40); do
  curl -sf "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1 && break
  sleep 0.25
done
curl -sf "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null
for _ in $(seq 1 20); do
  curl -sf "http://127.0.0.1:${HTTP_PORT}/live-page.html" >/dev/null 2>&1 && break
  sleep 0.1
done

TARGET_ID="$("${PY}" "${CDP}" newtab "http://127.0.0.1:${HTTP_PORT}/live-page.html?job=runner-live")"
COMPETING_ID="$(TGT_ID="${TARGET_ID}" "${PY}" "${CDP}" newtab "about:blank#runner-competing")"
VARS="$(printf '{"base_url":"http://127.0.0.1:%s/live-page.html","tester":"s3cret-Ada"}' "${HTTP_PORT}")"
LIVE_RUNS="${LIVE_RUNS:-1}"
[[ "${LIVE_RUNS}" =~ ^[0-9]+$ ]] && [ "${LIVE_RUNS}" -ge 1 ] && [ "${LIVE_RUNS}" -le 50 ] \
  || { echo "FAIL: LIVE_RUNS must be an integer in 1..50"; exit 2; }
for run in $(seq 1 "${LIVE_RUNS}"); do
  # Make the owned target hidden before every run. Session readiness must foreground the exact
  # pinned target; otherwise Chrome background-timer throttling invalidates performance evidence.
  curl -sf "http://127.0.0.1:${CDP_PORT}/json/activate/${COMPETING_ID}" >/dev/null
  TARGET_BEFORE="$(TGT_ID="${TARGET_ID}" "${PY}" "${CDP}" eval "document.visibilityState")"
  COMPETING_BEFORE="$(TGT_ID="${COMPETING_ID}" "${PY}" "${CDP}" eval "document.visibilityState")"
  [ "${TARGET_BEFORE}" = "hidden" ] && [ "${COMPETING_BEFORE}" = "visible" ] || {
    echo "FAIL: foreground precondition target=${TARGET_BEFORE} competing=${COMPETING_BEFORE}"
    exit 1
  }
  # Print terminal output and the full artifact on failure: cleanup removes ${WORK}, so a silent
  # exit would hide the cause (for example DRIVER_INCOMPATIBLE from a stale cdp.py).
  printf '%s' "${VARS}" | "${PY}" "${ROOT}/scripts/flow-runner.py" \
    --engine cdp \
    --flow "${ROOT}/tests/fixtures/live-flow.yaml" --out "${WORK}/out-${run}" --vars-json - \
    --target-id "${TARGET_ID}" --cdp-script "${CDP}" --stdout summary \
    >"${WORK}/runner-${run}.jsonl" || {
    code=$?
    echo "FAIL: runner exit ${code} on run ${run} (driver: ${CDP})"
    cat "${WORK}/runner-${run}.jsonl"
    [ ! -f "${WORK}/out-${run}/run-log.jsonl" ] || cat "${WORK}/out-${run}/run-log.jsonl"
    exit 1
  }
  TARGET_AFTER="$(TGT_ID="${TARGET_ID}" "${PY}" "${CDP}" eval "document.visibilityState")"
  COMPETING_AFTER="$(TGT_ID="${COMPETING_ID}" "${PY}" "${CDP}" eval "document.visibilityState")"
  [ "${TARGET_AFTER}" = "visible" ] && [ "${COMPETING_AFTER}" = "hidden" ] || {
    echo "FAIL: runner did not foreground pinned target target=${TARGET_AFTER} competing=${COMPETING_AFTER}"
    exit 1
  }
done

# BAS-2 against the real driver: a declared identity that does not match the element must fail the
# step, and the page must be exactly as it was — the refusal happens before any input is dispatched.
MISMATCH_VARS="$(printf '{"base_url":"http://127.0.0.1:%s/live-page.html"}' "${HTTP_PORT}")"
if printf '%s' "${MISMATCH_VARS}" | "${PY}" "${ROOT}/scripts/flow-runner.py" \
    --engine cdp --flow "${ROOT}/tests/fixtures/live-expect-mismatch.yaml" \
    --out "${WORK}/out-mismatch" --vars-json - --target-id "${TARGET_ID}" \
    --cdp-script "${CDP}" --stdout summary >"${WORK}/runner-mismatch.jsonl"; then
  echo "FAIL: a click whose --expect does not match the element must not pass"
  cat "${WORK}/runner-mismatch.jsonl"
  exit 1
fi
grep -q '"code":"EXPECT_MISMATCH"' "${WORK}/out-mismatch/run-log.jsonl" || {
  echo "FAIL: the mismatch run did not fail as EXPECT_MISMATCH"
  cat "${WORK}/out-mismatch/run-log.jsonl"
  exit 1
}
STATUS_AFTER="$(TGT_ID="${TARGET_ID}" "${PY}" "${CDP}" eval \
  "document.querySelector('#status').textContent")"
[ "${STATUS_AFTER}" = "not saved" ] || {
  echo "FAIL: the refused click still reached the page (#status = ${STATUS_AFTER})"
  exit 1
}

grep -q 'event.isTrusted' "${ROOT}/tests/fixtures/live-page.html"
[ -s "${WORK}/out-1/shots/native-click-03.png" ]
"${PY}" - "${WORK}" "${LIVE_RUNS}" <<'PY'
import json
import math
import statistics
import sys
from pathlib import Path

work, count = Path(sys.argv[1]), int(sys.argv[2])
rows = []


def p95(values):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


for run in range(1, count + 1):
    events = [json.loads(line) for line in
              (work / f"out-{run}" / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]
    ready = next(item for item in events if item["type"] == "session_ready")
    assert ready["version"] >= 3 and ready["input_settle"] == "none", ready
    assert ready["foreground"] is True and ready["visibility_state"] == "visible", ready
    steps = [item for item in events if item["type"] == "step_done"]
    assert len(steps) == 3 and all(item["status"] != "fail" for item in steps), steps
    fill = steps[1]["timings"]["phases"]
    click = steps[2]["timings"]["phases"]
    # The browser event may begin its timer before the action command returns, so the
    # portable contract is action + wait wall time—not a particular phase split.
    assert fill["action"]["wall_ms"] + fill["wait"]["wall_ms"] >= 140, fill
    assert click["action"]["wall_ms"] + click["wait"]["wall_ms"] >= 280, click
    assert "assert" in click and "capture" in click, click
    # BAS-3: every state-changing step carries the driver's own page-state receipt, and an
    # unwatched channel reads as "unwatched" rather than as a zero that looks like "all clear".
    for step in steps[1:]:
        receipt = step["receipt"]
        assert receipt["url"].endswith("live-page.html"), receipt
        assert receipt["net_errors"] == "unwatched", receipt
        assert receipt["downloads"] == "unwatched", receipt
        assert receipt["ref_invalidated"] is False, receipt
    assert [item["type"] for item in steps[2]["receipt"]["dialogs"]] == ["alert"], steps[2]
    assert steps[2]["performance"]["verdict"] == "PASS", steps[2]
    assert 280 <= steps[2]["performance"]["outcome_ms"] <= 10000, steps[2]
    assert next(item for item in events if item["type"] == "errors").get("timing"), events
    dialogs = [item for item in events if item["type"] == "dialog"]
    assert len(dialogs) == 1, dialogs
    assert {key: dialogs[0][key] for key in
            ("scenario", "index", "global_index", "kind", "message", "answer")} == {
                "scenario": "native-click", "index": 3, "global_index": 3,
                "kind": "alert", "message": "Live save started", "answer": "accept",
            }, dialogs[0]
    done = next(item for item in events if item["type"] == "run_done")
    assert done["verdict"] == "PASS", done
    assert done["dialogs"] == 1, done
    assert done["performance_budgets"] == {"passed": 1, "evaluated": 1, "total": 1}, done
    assert done["action_receipts"] == {"requested": 2, "received": 2,
                                       "engine_supported": True}, done
    assert done["identity_guard"] == {"declared": 2, "engine_supported": True}, done
    terminal = [json.loads(line) for line in
                (work / f"runner-{run}.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [item["type"] for item in terminal] == ["run_done"], terminal
    rows.append({"startup_ms": done["startup_ms"], "open_ms": steps[0]["duration_ms"],
                 "fill_ms": steps[1]["duration_ms"], "click_ms": steps[2]["duration_ms"],
                 "step_total_ms": sum(item["duration_ms"] for item in steps),
                 "run_total_ms": done["duration_ms"]})
print(json.dumps({"runs": count, "failures": 0,
                  "median_ms": {key: round(statistics.median(row[key] for row in rows), 3)
                                for key in rows[0]},
                  "p95_ms": {key: round(p95([row[key] for row in rows]), 3)
                             for key in rows[0]}}, separators=(",", ":")))
PY
if grep -R -q 's3cret-Ada' "${WORK}"/out-*/run-log.jsonl; then exit 1; fi
if grep -R -q 's3cret-Ada' "${WORK}"/out-*/qa-report.md; then exit 1; fi
echo "PASS: ${LIVE_RUNS} real-Chrome run(s) foregrounded the exact pinned target and used protocol v3, per-step dialogs, event-bound nav, fast native input, async waits, performance budgets, declared identity guards with per-action receipts (plus a refused mismatch that never reached the page), summary stdout, redaction, telemetry, and artifacts"
