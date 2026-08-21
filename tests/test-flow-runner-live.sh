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
VARS="$(printf '{"base_url":"http://127.0.0.1:%s/live-page.html","tester":"s3cret-Ada"}' "${HTTP_PORT}")"
printf '%s' "${VARS}" | "${PY}" "${ROOT}/scripts/flow-runner.py" \
  --flow "${ROOT}/tests/fixtures/live-flow.yaml" --out "${WORK}/out" --vars-json - \
  --target-id "${TARGET_ID}" --cdp-script "${CDP}"

grep -q '"verdict":"PASS"' "${WORK}/out/run-log.jsonl"
grep -q 'event.isTrusted' "${ROOT}/tests/fixtures/live-page.html"
[ -s "${WORK}/out/shots/native-click-03.png" ]
if grep -q 's3cret-Ada' "${WORK}/out/run-log.jsonl"; then exit 1; fi
if grep -q 's3cret-Ada' "${WORK}/out/qa-report.md"; then exit 1; fi
echo "PASS: real Chrome flow used native click, one pinned JSONL session, redacted secret, and artifacts"
