#!/usr/bin/env bash
# flow-runner --engine bsk กับ BrowserSkill จริง — คู่กับ dialog-test.sh (BAS §4.3 ข้อ 2)
#
#   bash self-test/engine2/runner-test.sh
#
# พิสูจน์: flow read-only ได้ PASS(inferred) + exit 1, และ confirm ที่ bsk ตอบ accept ทำให้ step ล้มด้วย
# ENGINE_DIALOG_ACCEPTED. ไม่มี bsk / daemon / extension = SKIP (exit 0) ไม่ใช่ PASS
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PORT=8931
export BSK_AUTO_START=0 PYTHONIOENCODING=utf-8
command -v bsk >/dev/null 2>&1 || { echo "SKIP: ไม่พบ bsk ใน PATH"; exit 0; }
PY=""; for c in python py python3; do "$c" -c 'import yaml, jsonschema' >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || { echo "SKIP: ไม่พบ python ที่มี PyYAML + jsonschema"; exit 0; }
WORK="$(mktemp -d)"; SRV_PID=""
cleanup() { [ -n "$SRV_PID" ] && kill "$SRV_PID" 2>/dev/null; rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT
timeout 15 bsk status --json >"$WORK/status.json" 2>/dev/null || { echo "SKIP: bsk daemon ไม่ตอบ"; exit 0; }
timeout 15 bsk browsers --json >"$WORK/browsers.json" 2>/dev/null
[ "$("$PY" -c "import json,sys;print(len(json.load(open(sys.argv[1]))))" "$WORK/browsers.json" 2>/dev/null)" = "1" ] \
  || { echo "SKIP: ต้องมี browser ที่เชื่อม extension หนึ่งตัวพอดี"; exit 0; }

(cd "$HERE" && exec "$PY" -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1) &
SRV_PID=$!
for _ in $(seq 20); do curl -sf -o /dev/null "http://127.0.0.1:${PORT}/dialog-page.html" && break; sleep 0.5; done

pass=0; fail=0
# run <flow> <expected-verdict> <expected-exit> <substring that must be in run-log>
run() {
  "$PY" "$ROOT/scripts/flow-runner.py" --engine bsk --flow "$HERE/$1" --out "$WORK/out-$1" --stdout summary >"$WORK/$1.json" 2>&1
  local rc=$? verdict
  verdict="$("$PY" -c "import json,sys;print(json.loads(open(sys.argv[1],encoding='utf-8').read().strip().splitlines()[-1]).get('verdict'))" "$WORK/$1.json" 2>/dev/null)"
  if [ "$verdict" = "$2" ] && [ "$rc" = "$3" ] && grep -q "$4" "$WORK/out-$1/run-log.jsonl"; then
    pass=$((pass+1)); echo "  ok   $1: $verdict (exit $rc)"
  else
    fail=$((fail+1)); echo "  FAIL $1: verdict=$verdict exit=$rc expected=$2/$3 marker=$4"; tail -c 400 "$WORK/$1.json"
  fi
}
run flow-read.yaml    "PASS(inferred)" 1 '"engine":"bsk"'
run flow-confirm.yaml "FAIL"           1 'ENGINE_DIALOG_ACCEPTED'
echo "pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
