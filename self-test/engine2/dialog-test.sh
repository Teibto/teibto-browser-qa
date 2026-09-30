#!/usr/bin/env bash
# Engine ที่สอง (BrowserSkill / bsk) — ด่าน dialog + beforeunload ตาม BAS §4.3 ข้อ 3
#
#   bash self-test/engine2/dialog-test.sh
#
# พิสูจน์สามเรื่องกับ bsk + extension จริง:
#   1. ค่า `handled` ที่ bsk รายงานต่อ dialog ตรงกับผลจริงใน DOM (รายงานไม่โกหก)
#   2. นโยบายที่สังเกตได้ตรงกับที่ ledger pin ไว้ (EXPECT_*) — upstream เปลี่ยนนโยบาย = แดง = ต้องทบทวน BAS §4
#   3. หลัง beforeunload คำสั่งถัดไปยังตอบใน LIVENESS_S วินาที และ daemon ยังตอบ status หลังครบ ROUNDS รอบ
#      (อาการที่ทำให้ทีมเลิก daemon ตัวก่อน — issue #34)
#
# ต้องมี: bsk ใน PATH, daemon รันอยู่, extension เชื่อมต่อหนึ่ง browser, python
# ขาดอย่างใดอย่างหนึ่ง = SKIP (exit 0) ไม่ใช่ PASS · เทสนี้ไม่ start daemon เอง (ดู gotchas ใน README)
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROUNDS="${ENGINE2_ROUNDS:-20}"
PORT="${ENGINE2_PORT:-8931}"
LIVENESS_S="${ENGINE2_LIVENESS_S:-10}"
EXPECT_ALERT="${ENGINE2_EXPECT_ALERT:-accepted}"
EXPECT_CONFIRM="${ENGINE2_EXPECT_CONFIRM:-accepted}"
EXPECT_PROMPT="${ENGINE2_EXPECT_PROMPT:-accepted}"
EXPECT_LEAVE="${ENGINE2_EXPECT_LEAVE:-accepted}"
PAGE="http://127.0.0.1:${PORT}/dialog-page.html"

export BSK_AUTO_START=0          # auto-start ทำให้ shell ที่ pipe output ค้าง — ให้ host เป็นคน start daemon
command -v bsk >/dev/null 2>&1 || { echo "SKIP: ไม่พบ bsk ใน PATH"; exit 0; }
PY=""; for c in python py python3; do "$c" -c 'import json' >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || { echo "SKIP: ไม่พบ python"; exit 0; }

WORK="$(mktemp -d)"
SID=""; SRV_PID=""
cleanup() {
  [ -n "$SID" ] && timeout 20 bsk session stop "$SID" --quiet >/dev/null 2>&1
  [ -n "$SRV_PID" ] && kill "$SRV_PID" 2>/dev/null
  rm -rf "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

# jget <file> <python-expr over d>  — อ่านค่าจาก JSON โดยไม่พึ่ง jq
jget() { "$PY" -c "import json,sys;d=json.load(open(sys.argv[1],encoding='utf-8'));print($2)" "$1" 2>/dev/null; }

timeout 15 bsk status --json >"$WORK/status.json" 2>/dev/null \
  || { echo "SKIP: bsk daemon ไม่ตอบ — รัน 'bsk daemon start --foreground' ใน terminal ของ host ก่อน"; exit 0; }
timeout 15 bsk browsers --json >"$WORK/browsers.json" 2>/dev/null
# เลือก browser: ENGINE2_BROWSER=<instance_id> หรือมีตัวเดียวพอดี — ห้ามเดา เพราะ fixture นี้เปิด dialog จริง
IDS="$(jget "$WORK/browsers.json" "' '.join(x['instance_id'] for x in d)")"
BROWSER="${ENGINE2_BROWSER:-}"
if [ -z "$BROWSER" ]; then
  [ "$(jget "$WORK/browsers.json" 'len(d)')" = "1" ] \
    || { echo "SKIP: มี browser เชื่อมอยู่ ${IDS:-0 ตัว} — ตั้ง ENGINE2_BROWSER=<instance_id> ของ profile ทดสอบ"; exit 0; }
  BROWSER="$IDS"
fi
case " $IDS " in *" $BROWSER "*) ;; *) echo "SKIP: ไม่พบ browser $BROWSER (ที่เชื่อมอยู่: $IDS)"; exit 0 ;; esac
echo "engine: bsk $(jget "$WORK/status.json" "d['daemon_version']") · browser $BROWSER · extension $(jget "$WORK/browsers.json" "[x for x in d if x['instance_id']=='$BROWSER'][0]['extension_version']")"

(cd "$HERE" && exec "$PY" -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1) &
SRV_PID=$!
for _ in $(seq 20); do curl -sf -o /dev/null "$PAGE" && break; sleep 0.5; done
curl -sf -o /dev/null "$PAGE" || { echo "FAIL: เสิร์ฟ fixture ที่ $PAGE ไม่ได้"; exit 1; }

timeout 40 bsk session start --json --name engine2-dialog-test --no-focus --browser "$BROWSER" >"$WORK/sess.json" 2>"$WORK/err.txt" \
  || { echo "FAIL: session start: $(head -c 300 "$WORK/err.txt")"; exit 1; }
SID="$(jget "$WORK/sess.json" "d['session_id']")"

pass=0; fail=0
chk() { # chk <name> <expected> <actual>
  if [ "$2" = "$3" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "  FAIL $1: expected=$2 actual=$3"; fi
}
# B <outfile> <timeout-s> <bsk args...> — ทุกคำสั่งมี timeout และเขียนลงไฟล์ ไม่ pipe
B() { local out="$1" t="$2"; shift 2; timeout "$t" bsk "$@" --session "$SID" --json >"$out" 2>"$WORK/err.txt"; }
dom() { B "$WORK/dom.json" "$LIVENESS_S" evaluate "document.getElementById('$1').textContent" || { echo "<timeout>"; return; }; jget "$WORK/dom.json" "d['value']"; }
handled() { jget "$1" "','.join(x['type']+'='+x['handled'] for x in d.get('dialogs',[]))"; }
# dom_for <kind> <handled> — ผลใน DOM ที่ต้องเห็นถ้ารายงานเป็นความจริง
dom_for() {
  case "$1:$2" in
    alert:*) echo "returned" ;;
    confirm:accepted) echo "true" ;;   confirm:dismissed) echo "false" ;;
    prompt:accepted) echo '"default-text"' ;; prompt:dismissed) echo "null" ;;
    leave:accepted) echo "left" ;;     leave:dismissed) echo "stayed" ;;
  esac
}

for round in $(seq "$ROUNDS"); do
  B "$WORK/nav.json" 40 navigate "$PAGE" || { echo "FAIL round $round: navigate ไม่ตอบ: $(head -c 200 "$WORK/err.txt")"; fail=$((fail+1)); break; }
  for kind in alert confirm prompt; do
    B "$WORK/$kind.json" 40 click "#btn-$kind" || { echo "  FAIL round $round: click $kind ไม่ตอบ"; fail=$((fail+1)); continue; }
    reported="$(handled "$WORK/$kind.json")"; reported="${reported#*=}"
    eval "expected=\$EXPECT_$(echo "$kind" | tr a-z A-Z)"
    chk "r$round $kind policy" "$expected" "$reported"
    chk "r$round $kind report-vs-DOM" "$(dom_for "$kind" "$reported")" "$(dom "r-$kind")"
  done

  B "$WORK/leave.json" 40 click "#btn-leave" || { echo "  FAIL round $round: click leave ไม่ตอบ"; fail=$((fail+1)); continue; }
  reported="$(handled "$WORK/leave.json")"; reported="${reported#*=}"
  chk "r$round beforeunload policy" "$EXPECT_LEAVE" "$reported"
  t0=$(date +%s%3N); got="idle"
  for _ in $(seq 10); do got="$(dom r-leave)"; [ "$got" != "idle" ] && [ -n "$got" ] && break; sleep 0.5; done
  chk "r$round beforeunload report-vs-DOM" "$(dom_for leave "$reported")" "$got"
  # liveness: คำสั่งแรกหลัง beforeunload ต้องตอบ — wedge คือ timeout ตรงนี้
  if B "$WORK/live.json" "$LIVENESS_S" evaluate "1+1" && [ "$(jget "$WORK/live.json" "d['value']")" = "2" ]; then
    pass=$((pass+1))
  else
    fail=$((fail+1)); echo "  FAIL r$round liveness: ไม่ตอบใน ${LIVENESS_S}s หลัง beforeunload (wedge)"
  fi
  [ "$round" = 1 ] && echo "round 1: $(handled "$WORK/alert.json") · $(handled "$WORK/confirm.json") · $(handled "$WORK/prompt.json") · $(handled "$WORK/leave.json") · post-unload settle $(( $(date +%s%3N)-t0 ))ms"
done

timeout 15 bsk status --json >"$WORK/status2.json" 2>/dev/null && [ "$(jget "$WORK/status2.json" "d['pid']")" = "$(jget "$WORK/status.json" "d['pid']")" ] \
  && pass=$((pass+1)) || { fail=$((fail+1)); echo "  FAIL daemon: ไม่ตอบ status หรือ pid เปลี่ยนหลัง $ROUNDS รอบ"; }

echo "rounds=$ROUNDS pass=$pass fail=$fail"
if [ "$EXPECT_CONFIRM" = "accepted" ] || [ "$EXPECT_LEAVE" = "accepted" ]; then
  echo "POLICY: bsk ตอบ accept ให้ confirm/beforeunload — ขัดกับนโยบาย safe (SKILL.md invariant 5) · ห้ามใช้กับ step ที่ risk: write|destructive (BAS §4.2)"
fi
[ "$fail" -eq 0 ]
