#!/usr/bin/env bash
# Smoke self-test ของ claim ที่ skill นี้เขียนไว้ — พิสูจน์กับ Chrome จริงแบบ mechanical
# Re-run หลัง Chrome หรือ cdp.py เปลี่ยนเวอร์ชัน = drift detector อัตโนมัติ
#
#   bash self-test/smoke-test.sh
#
# ต้องมี: Chrome + `py -m pip install websocket-client` (pillow/numpy ถ้าจะเทส diff)
# ไม่มี Chrome = SKIP (exit 0) ไม่ใช่ FAIL
# transport: cdp.py (CDP ตรง) — ทีมเลิกใช้ agent-browser daemon แล้ว (teibto-dev-standards#111)
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERE_WIN="$(cygpath -m "$HERE" 2>/dev/null || pwd -W 2>/dev/null || echo "$HERE")"
PAGE="file:///${HERE_WIN}/smoke-page.html"

CDP="${NS_CDP:-$HOME/.claude/skills/netsuite-qa-browser/references/cdp.py}"
[ -f "$CDP" ] || { echo "SKIP: ไม่พบ cdp.py ที่ $CDP (ตั้ง NS_CDP ให้ชี้ถูก)"; exit 0; }

CHROME=""
for p in \
  "/c/Program Files/Google/Chrome/Application/chrome.exe" \
  "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
  "$(command -v google-chrome || true)" \
  "$(command -v chromium || true)"; do
  [ -x "$p" ] && { CHROME="$p"; break; }
done
[ -n "$CHROME" ] || { echo "SKIP: ไม่พบ Chrome — เทสนี้ต้องมี browser จริง"; exit 0; }

PY=""
for c in py python3 python; do
  if "$c" -c 'import websocket' >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "SKIP: ไม่มี python ที่ import websocket ได้ — <python> -m pip install websocket-client"; exit 0; }
export PYTHONIOENCODING=utf-8

export CDP_PORT=9395                 # คนละพอร์ตกับงานจริงและกับเทสของ cdp.py เอง
WORK="$(mktemp -d)"
CHROME_PID=""
cleanup() {
  if [ -n "$CHROME_PID" ]; then kill "$CHROME_PID" 2>/dev/null || true; sleep 1; fi
  rm -rf "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

"$CHROME" --user-data-dir="$(cygpath -w "$WORK/profile" 2>/dev/null || echo "$WORK/profile")" \
  --remote-debugging-port="$CDP_PORT" --headless=new \
  --no-first-run --no-default-browser-check about:blank >/dev/null 2>&1 &
CHROME_PID=$!
for _ in $(seq 40); do
  curl -sf "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -sf "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1 \
  || { echo "FAIL: Chrome ไม่ตอบที่ port ${CDP_PORT}"; exit 1; }

AB(){ "$PY" "$CDP" "$@" 2>&1; }
png_size(){ "$PY" -c "import struct,sys;b=open(sys.argv[1],'rb').read();print('%dx%d'%(struct.unpack('>I',b[16:20])[0],struct.unpack('>I',b[20:24])[0]))" "$1"; }

pass=0; fail=0
chk(){ # chk "name" "expected-substr" "actual"
  if [[ "$3" == *"$2"* ]]; then echo "  PASS  $1"; pass=$((pass+1));
  else echo "  FAIL  $1 | want '$2' | got: ${3//$'\n'/ }" | head -c 240; echo; fail=$((fail+1)); fi; }

echo "=== setup ==="
AB nav "$PAGE" 2 >/dev/null; echo "url: $(AB url)"

echo "=== get: selector ก่อน name · แยก 'ไม่มี element' ออกจาก 'ค่าว่าง' ==="
chk "get attr <sel> <name> (ลำดับถูก)"      "example.org/target" "$(AB get attr '#lnk' href)"
chk "element ที่ไม่มีจริง -> <no element>"   "<no element>"       "$(AB get text '#ไม่มีจริง')"
chk "input ว่าง -> ค่าว่าง ไม่ใช่ <no element>" ""                 "$(AB get value '#txt')"
chk "get count นับได้"                       "2"                  "$(AB get count '.row')"

echo "=== is: visible/enabled/checked (ห้ามวัดด้วย offsetParent) ==="
chk "is visible ของที่แสดงอยู่"               "true"  "$(AB is visible '#act')"
chk "is visible ของที่ display:none"          "false" "$(AB is visible '#gone')"
chk "is visible ไม่พลาด position:fixed"       "true"  "$(AB is visible '#fixedbar')"
chk "is enabled รู้ว่าปุ่ม disabled"           "false" "$(AB is enabled '#off')"

echo "=== a11y: คืน ref แล้วใช้ ref คลิกได้จริง (แทน find role/label) ==="
AB nav "$PAGE" 2 >/dev/null
REF="$(AB a11y "Act" | "$PY" -c "import json,sys;d=json.load(sys.stdin);print(d[0]['ref'] if d else '')")"
chk "a11y หา button ตามชื่อเจอ"               "@"           "$REF"
AB click "$REF" >/dev/null
chk "คลิกด้วย ref จาก a11y แล้ว handler ทำงาน" "act-clicked" "$(AB get text '#out')"

echo "=== eval แชร์ global scope (bare let ชนกัน) ==="
AB eval "let smk=1; smk" >/dev/null
chk "let smk ซ้ำรอบสอง -> SyntaxError"       "already been declared" "$(AB eval 'let smk=2; smk')"
chk "ห่อ IIFE แล้วไม่ชน"                      "ok3"                   "$(AB eval "(function(){var smk=3; return 'ok'+smk;})()")"

echo "=== click ใต้ fold: scrollIntoView อยู่ในตัว ==="
AB nav "$PAGE" 2 >/dev/null
AB click '#btm' >/dev/null
chk "click ใต้ fold เลื่อนให้เอง + ยิง handler" "btm-clicked" "$(AB get text '#bout')"

echo "=== console collector: ผูกกับหน้า ไม่ใช่ buffer สะสม ==="
AB nav "$PAGE" 2 >/dev/null
chk "หน้าใหม่เริ่มด้วย log ว่าง"               "[]"           "$(AB console)"
AB eval "window.boom()" >/dev/null; sleep 0.6
CON="$(AB console)"
chk "จับ console.error ได้"                   "smoke-error"  "$CON"
chk "จับ uncaught error ได้ด้วย"              "error"        "$CON"
AB nav "$PAGE" 2 >/dev/null
chk "navigate แล้วล้างเอง ไม่ยกของหน้าก่อนมา"  "[]"           "$(AB console)"

echo "=== wait: exit 1 เมื่อหมดเวลา (ให้ flow หยุดตรงจุดที่พังจริง) ==="
chk "เงื่อนไขที่จริงอยู่แล้ว ผ่านทันที" "true" "$(AB wait "document.readyState==='complete'" 5)"
rc=0; AB wait "window.__never===1" 2 >/dev/null 2>&1 || rc=$?
chk "หมดเวลาแล้ว exit ไม่เป็น 0" "rc=1" "rc=$rc"

echo "=== IFRAME: ไม่มี state ค้าง ตั้งเฉพาะคำสั่งที่ต้องการ ==="
chk "ไม่ตั้ง IFRAME มองไม่เห็นของข้างใน" "<no element>"   "$(AB get text '#inner')"
chk "ตั้ง IFRAME แล้วเห็น"                "inside iframe"  "$(IFRAME='#fr' AB get text '#inner')"

echo "=== shot: element-scoped + --dsf ต้องอยู่ในคำสั่งเดียวกัน ==="
AB nav "$PAGE" 2 >/dev/null
AB shot "$WORK/card.png" '#card' --dsf=2 >/dev/null
chk "shot <sel> --dsf=2 ได้ขนาด element x2" "300x120" "$(png_size "$WORK/card.png")"
# ★ พิสูจน์ gotcha #4: viewport ที่สั่งแยก invocation ไม่มีผล
AB viewport 900 600 2 >/dev/null
AB shot "$WORK/card1x.png" '#card' >/dev/null
chk "viewport แยกคำสั่งไม่มีผล (จึงต้องใช้ --dsf)" "150x60" "$(png_size "$WORK/card1x.png")"
rc=0; AB shot "$WORK/nope.png" '#ไม่มีจริง' >/dev/null 2>&1 || rc=$?
chk "selector ไม่มีจริง -> error ไม่ใช่ถ่ายทั้งหน้า" "rc=1" "rc=$rc"

echo "=== diff: visual regression ==="
if "$PY" -c "import PIL, numpy" >/dev/null 2>&1; then
  AB shot "$WORK/a.png" >/dev/null; AB shot "$WORK/b.png" >/dev/null
  chk "ภาพเดียวกัน = SAME" '"verdict": "SAME"' "$(AB diff "$WORK/a.png" "$WORK/b.png")"
  AB eval "document.body.style.background='#000';1" >/dev/null
  AB shot "$WORK/c.png" >/dev/null
  rc=0; OUT="$(AB diff "$WORK/a.png" "$WORK/c.png" "$WORK/d.png")" || rc=$?
  chk "ภาพต่างกัน = DIFFERENT" '"verdict": "DIFFERENT"' "$OUT"
  chk "และ exit 1 ให้ CI จับได้"  "rc=1"                  "rc=$rc"
else
  echo "  SKIP  diff (ไม่มี pillow/numpy)"
fi

echo "=== about:blank เป็นเรื่องปกติ ไม่ใช่ paint พัง ==="
chk "nav about:blank -> url == about:blank" "about:blank" "$(AB nav about:blank 1)"

echo "=== EFFICIENCY: หลายคำสั่ง vs รวมเป็น evalf ก้อนเดียว ==="
AB nav "$PAGE" 2 >/dev/null
t0=$(date +%s.%N)
for c in "url" "get text title" "get count body" "is visible #act" "console"; do AB "$c" >/dev/null 2>&1; done
t1=$(date +%s.%N)
cat > "$WORK/all.js" <<'JS'
(function(){return JSON.stringify({url:location.href,title:document.title,
  body:document.querySelectorAll('body').length,act:!!document.querySelector('#act'),
  errors:(window.__cdpLog||[]).length});})()
JS
t2=$(date +%s.%N); AB evalf "$WORK/all.js" >/dev/null; t3=$(date +%s.%N)
echo "  แยกคำสั่ง: 5 calls, $(awk "BEGIN{printf \"%.2f\", $t1-$t0}")s | evalf ก้อนเดียว: 1 call, $(awk "BEGIN{printf \"%.2f\", $t3-$t2}")s"

echo "=== EFFICIENCY: PDF template scoped-read drift gate (pure file, no browser) ==="
# pdf-reports.md บอกให้ Read เฉพาะบล็อก <script> ตอนแก้ data[] · ถ้า refactor ทำให้ CSS เล็กลง
# การประหยัดจะอ่อนลง -> gate นี้จับได้ · assert ว่ายังประหยัด >=40%
ROOT="$(dirname "$HERE")"
for f in guide-template bug-report-template; do
  file="$ROOT/assets/$f.html"
  sline=$(grep -nE '^<script>$' "$file" | head -1 | cut -d: -f1)
  full=$(wc -c < "$file"); block=$(tail -n +"$sline" "$file" | wc -c); saved=$(( (full-block)*100/full ))
  echo "  $f: full=${full}c block(<script>@L$sline)=${block}c -> scoped read saves ${saved}%"
  chk "$f scoped-read saves >=40%" "yes" "$([ "$saved" -ge 40 ] && echo yes || echo no)"
done

echo ""
echo "======== RESULT: $pass passed, $fail failed ========"
[ "$fail" -eq 0 ]
