# Command Reference — `cdp.py` (CDP ตรง)

transport ของ skill นี้คือ **`cdp.py`** ซึ่งเป็น asset กลางของ `Teibto/teibto-dev-standards`
(`scripts/cdp.py`) — ทีมเลิกใช้ `agent-browser` daemon แล้ว เหตุผลและตารางแปลงอยู่ท้ายไฟล์นี้

## เตรียม (ครั้งเดียวต่อเครื่อง)

```bash
py -m pip install websocket-client pillow numpy    # pillow/numpy เฉพาะตอนใช้ diff
```

## เริ่มทุก session

```bash
NS_CDP="$HOME/.claude/skills/netsuite-qa-browser/references/cdp.py"   # หรือ copy ที่ vendor เข้า repo
export CDP_PORT=9400                       # หนึ่งงาน = หนึ่ง port = หนึ่ง profile
AB(){ py "$NS_CDP" "$@"; }

# Chrome ของงานนี้ (profile ถาวร = เก็บ login ไว้ ไม่ต้อง 2FA ซ้ำ)
"/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --user-data-dir="$(cygpath -w "$PWD/.qa-profiles/run")" --remote-debugging-port=$CDP_PORT \
  --no-sandbox --no-first-run --no-default-browser-check about:blank &
until curl -sf "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null; do sleep 1; done

# แท็บของงานเราพร้อม marker เฉพาะ แล้วปักหมุด — ห้ามทำงานบนแท็บที่คนอื่นเปิดไว้
export TGT_ID=$(AB newtab "<url>?job=<ชื่องาน>")
```

**pre-flight ทั้งหมดเหลือแค่ `curl /json/version`** — ไม่มี daemon ให้ warm, ไม่มี session file
ให้ล้าง, ไม่มี cold-start loop ที่ค้างเป็นนาที

## Navigate / Interact

| คำสั่ง | ใช้ทำ |
|---|---|
| `nav <url> [wait]` | เปิดหน้า แล้วรอ (ยังตอบ JS dialog ระหว่างรอ) · ติดตั้ง console collector ให้อัตโนมัติ |
| `click <sel\|@ref>` | คลิก **จริง** ด้วย Input event · `scrollIntoView` ให้ในตัว |
| `fill <sel\|@ref> <text>` | โฟกัสจริง → ล้าง → พิมพ์จริง → Tab |
| `type <text>` | พิมพ์ลง element ที่โฟกัสอยู่ |
| `key <Enter\|Tab\|Escape\|Arrow*\|Backspace\|Delete>` | ส่งปุ่มจริง |
| `pick <sel\|@ref> <text>` | dropdown: คลิก → type-ahead → Enter |
| `setfile <sel> <path>` | แนบไฟล์เข้า `<input type=file>` (พิมพ์ path ตรง ๆ ไม่ได้ browser กัน) |
| `newtab [url]` · `close <substring>` | จัดการแท็บของงานเรา |

`eval <js>` = ทางหนีที่ชัวร์เสมอ — element ที่ locator ไหนก็จับไม่ติด ใช้
`eval "document.querySelector('SEL').click()"` (แล้ว QA เรื่อง clickability จริงแยกต่างหาก)

## อ่านข้อมูล (ผลลัพธ์สั้น — ปลอดภัยต่อ token)

| คำสั่ง | หมายเหตุ |
|---|---|
| `a11y [คำค้น]` | accessibility tree เฉพาะที่มีความหมาย + ref `@<id>` ใช้กับ `click`/`fill` ได้ตรง ๆ |
| `get text\|value\|attr\|count\|html <sel> [name]` | **ไม่มี element = `<no element>`** ไม่ใช่ค่าว่าง |
| `is visible\|enabled\|checked <sel>` | คืน `true`/`false` |
| `url` · `tabs` | สั้น ปลอดภัย |
| `console [--clear]` | error/warn ที่ collector จับไว้ — **หลังทุก step สำคัญ** |
| `cookies` | รวม HttpOnly ที่ `document.cookie` มองไม่เห็น |
| `eval <js>` · `evalf <file.js>` | assert ลึก · ไฟล์ = เลี่ยงนรก quote ของ shell |

**`get` แยก "ไม่มี element" ออกจาก "มีแต่ค่าว่าง"** — สองอย่างนี้คนละเรื่อง แต่ถ้าพิมพ์เหมือนกัน
จะสรุปผิดว่า field ว่างทั้งที่จริง ๆ หา element ไม่เจอ (คือ selector ผิด/หน้ายังไม่ render)

## หา element แบบ semantic (ทน dynamic UI)

`a11y` คือตัวแทนของ `find role/label/text` — มันคืน role + ชื่อ + ref มาให้เลย:

```bash
AB a11y "Submit"          # → [{"ref":"@42","role":"button","name":"Submit","value":""}]
AB click "@42"            # ใช้ ref ได้ตรง ๆ ทั้ง click/fill
```

ref เป็น `backendNodeId` ซึ่ง **คงที่ตลอดอายุของ node** — ไม่หมดอายุทุกครั้งที่ snapshot ใหม่
แบบ ref เดิม · แต่ยังหมดอายุเมื่อ navigate หรือหน้า re-render node นั้นทิ้ง

## รอแบบฉลาด (อย่ารอ fixed ms กับหน้า async)

```bash
AB wait "document.readyState==='complete'" 20
AB wait "!!document.querySelector('#done')" 15
AB wait "window.jQuery ? jQuery.active===0 : true" 20     # หน้า async ที่ใช้ jQuery (NetSuite)
```

`wait` **exit 1 เมื่อหมดเวลา** → ใช้กับ `&&` / `set -e` ได้ตรง ๆ ให้ flow หยุดตรงจุดที่พังจริง

> ไม่มี `--load networkidle` ให้ใช้ · เขียนเงื่อนไขที่**เจาะจงกับหน้าที่กำลังทดสอบ** แทน
> ซึ่งดีกว่าอยู่แล้ว — networkidle เดาไม่ถูกว่า "นิ่ง" ของแอปนี้แปลว่าอะไร และบนบางหน้า
> (NetSuite) มันโพลไม่จบเลย

## หลักฐาน / เอกสาร

| คำสั่ง | หมายเหตุ |
|---|---|
| `shot <path>` | ทั้ง viewport |
| `shot <path> <sel>` | crop เฉพาะกล่อง element — ตัดขอบว่างทิ้ง เอกสารกินหน้าน้อยลง |
| `shot <path> [sel] --dsf=2 --vw=1920 --vh=1200` | ตั้ง device metrics **ในการถ่ายครั้งนี้** |
| `diff <baseline.png> <current.png> [out.png] [--threshold=N]` | visual regression · **exit 1 เมื่อต่าง** |
| `pdf <path>` | Chrome printToPDF (traps → `pdf-reports.md`) |

⚠️ **path ของ `shot`/`pdf` ต้องเป็น Windows-style (`cygpath -w`)** — ส่ง path แบบ Git-Bash
(`/d/...`) ไฟล์**ไม่ถูกเขียนและคำสั่ง exit 0 ไม่ฟ้องอะไรเลย** (Windows Python ตีความ `/d/x`
เป็น `<ไดรฟ์ปัจจุบัน>:\d\x`) · หลัง `shot` ให้ `ls` ยืนยันว่าไฟล์มีจริงก่อนอ้างเป็นหลักฐานเสมอ
— เจอจริง 2026-08-10 (QA ar_aging บน SB2: รายงานเกือบอ้างภาพที่ไม่มีอยู่จริง)

⚠️ **`--dsf` ต้องส่งที่ `shot` ไม่ใช่สั่ง `viewport` แยกก่อน** — `Emulation.setDeviceMetricsOverride`
ผูกกับ session ของ CDP และถูกยกเลิกทันทีที่ปิด websocket · `cdp.py` เปิด WebSocket ใหม่ทุกคำสั่ง
แปลว่า `viewport 1920 1200 2` แล้วค่อย `shot` **ได้ภาพ 1x เสมอโดยไม่มีอะไรฟ้อง**
(teibto-dev-standards#119 — เทส T11e ล็อกข้อนี้ไว้แล้ว)

⚠️ **element-scoped `shot` จะ "ตก" native dropdown / top-layer popup** เพราะมันเป็น layer แยก
ไม่ได้อยู่ในกล่องของ element → ภาพที่ต้องมี popup ให้ถ่าย full viewport แล้ว crop ทีหลัง

### `diff` — ตัวเลขที่เชื่อได้

```bash
AB diff base.png now.png diff.png --threshold=30
# {"verdict": "DIFFERENT", "differing_pixels": 1842, "total_pixels": 540000, "pct": 0.341, ...}
```

- ภาพ diff ทาแดงตรงจุดที่ต่าง — ดูด้วยตาได้ว่าต่างตรงไหน ไม่ใช่แค่รู้ว่า "ต่าง"
- **ขนาดไม่เท่ากันคืน `SIZE-MISMATCH`** ไม่ย่อภาพให้เท่ากันแล้วเทียบ (จะได้ % ที่ไม่มีความหมาย)
- `--threshold` = ผลรวมส่วนต่าง RGB ต่อ pixel ที่ยอมให้ผ่าน (default 30) กัน noise ของการ render

## จับภาพ native `<select>` ที่เปิดอยู่ (สำหรับ user guide)

**ใช้ท่า DOM เป็นหลัก** — กาง `<select>` เป็น list inline ชั่วคราวด้วย `size`:

```bash
AB eval "(function(){var s=document.querySelector('SEL');window.__sz=s.size;s.size=6;
          s.selectedIndex=2;return 'ok';})()"
AB shot guide/step.png "SEL"
AB eval "(function(){document.querySelector('SEL').size=window.__sz;return 'ok';})()"
```

**ทำไมไม่ใช้ `Alt+ArrowDown` เปิด popup จริง:** popup ของ native `<select>` เป็น layer นอก DOM —
บาง Chrome จับติด บางรุ่นไม่ติด และ `cdp.py key` ยังไม่รองรับปุ่มพร้อม modifier · ท่า `size`
**อยู่ใน DOM จึงจับติดเสมอทุกรุ่น** และควบคุมได้ว่าจะให้ไฮไลต์ตัวไหน

ป๊อปอัป native ที่อยู่นอก DOM จริง ๆ (`alert`/`confirm`, file dialog) **screenshot ไม่ติดทุกกรณี** —
ถ้าต้องเก็บภาพต้องใช้ OS-level capture (skill `netsuite-ui-qa-testing` มีสูตร)

## `run` — หลายคำสั่งบน connection เดียว

ทุก invocation เปิด WebSocket ใหม่ → **CDP override ตายก่อนคำสั่งถัดไปจะเริ่ม** · งานที่ต้องข้าม
คำสั่ง (จอมือถือ, ธีม, timezone, ปลอมคำตอบ, เฝ้า network) จึงต้องอยู่ในโหมดนี้

```bash
cat > steps.txt <<'EOF'
# หนึ่งคำสั่งต่อบรรทัด · '#' = คอมเมนต์
netlog on
steady --tz=Asia/Bangkok
stub /api/orders 200 --bodyfile=D:\qa\empty.json
nav https://app.example.com/orders 3
lens layout
lens netlog
EOF
AB run steps.txt
```

| กฎ | รายละเอียด |
|---|---|
| แยก argument แบบ shell | แต่ **backslash เป็นตัวอักษรธรรมดา** — path Windows ไม่ถูกกลืน |
| ล้มบรรทัดไหน = หยุดทั้งสคริปต์ | บอกเลขบรรทัด + คำสั่ง ครอบทั้ง `SystemExit` และ exception อื่น |
| **หนึ่ง `run` = หนึ่งแท็บ** | `tabs`/`newtab`/`close`/`diff` ถูกปฏิเสธ — แท็บถูกเลือกตอนต่อครั้งเดียว |
| JSON ใน `--body=` | double quote โดน shlex กิน → ใช้ `--bodyfile=` หรือครอบ single quote |

**ไม่ใช่ daemon:** lifetime ของ session = lifetime ของ process — จบสคริปต์คือจบ ไม่มี state ค้าง
ไม่มี TTL ไม่มี orphan (เหตุผลที่ทีมทิ้ง `agent-browser` ยังใช้ได้อยู่)

## `lens` / `steady` / `netlog` / `stub` — ชั้น UX/UI

| คำสั่ง | คืนอะไร | ต้องอยู่ใน `run` |
|---|---|---|
| `lens layout` | ล้นแนวนอน · tap target < 24x24 · ข้อความถูกตัดหาย | ไม่ |
| `lens responsive <w1,w2,..>` | วน `layout` ทุกความกว้าง + `no-viewport-meta` | ไม่ |
| `lens theme` | ตัวหนังสือสีเดียวกับพื้น + `dark_mode: supported\|not-supported` | ไม่ |
| `lens focus [n]` | ลำดับ Tab จริง · trap · ไม่มีเส้นบอกโฟกัส | ไม่ |
| `lens netlog` | HTTP >= 400 · request ที่ล้ม · CSP/mixed content | **ใช่** |
| `steady [--tz=] [--locale=]` | หยุด animation/transition/smooth scroll · `--tz`/`--locale` ต้องอยู่ใน `run` | บางส่วน |
| `netlog on\|off` | เปิดเฝ้า `Network` + `Log` domain | **ใช่** |
| `stub <urlที่ตรง> <status>` | ปลอมคำตอบเพื่อบังคับสถานะ empty/error | **ใช่** |

```bash
AB lens layout
# {"lens":"layout","verdict":"FAIL","count":1,"findings":[
#   {"kind":"tap-target-small","sel":"nav > a.menu","detail":"18x18 < 24x24 (WCAG 2.2 AA)"}]}
```

⚠️ **`verdict` มีสามค่า ไม่ใช่สอง** — `PASS` / `FAIL` / **`UNVERIFIED`** · `lens netlog` ที่ไม่ได้สั่ง
`netlog on` มาก่อนคืน `UNVERIFIED` เพราะ "ไม่ได้เฝ้า" ไม่ใช่ "ไม่มีปัญหา" · คำสั่งที่ตั้ง override
นอกโหมด `run` จะเตือนลง stderr เสมอว่าไม่มีผลจริง

รายละเอียดการใช้งาน + ตารางว่าแต่ละ lens โกหกได้ยังไง → `ux-lens.md` ·
สิ่งที่ CDP แตะไม่ได้เลย → `cdp-limits.md`

## ลด round-trip ในงานยาว

ทุกคำสั่ง `cdp.py` = หนึ่ง process + หนึ่ง WebSocket handshake · flow ยาว ๆ ให้รวมงานเป็น
**JS ก้อนเดียวแล้วยิงด้วย `evalf`**:

```bash
cat > /tmp/step.js <<'JS'
(function(){
  var out = {};
  document.querySelector('#user').value = 'demo';
  document.querySelector('#login').click();
  out.url = location.href;
  out.errors = (window.__cdpLog || []).length;
  return JSON.stringify(out);
})()
JS
AB evalf /tmp/step.js
```

- คืน **JSON ก้อนเดียว** = อ่านง่าย token น้อย และเป็น run-log ในตัว
- **อย่ายัด assertion ที่ output ยาว** (`get html` ทั้งหน้า) ลงไป — ผลกลับเข้า context ทั้งก้อน
- แต่ **action ที่เปลี่ยน state ควรแยกคำสั่ง** เพื่อ assert ทีละขั้น — รวมทุกอย่างเป็นก้อนเดียว
  แล้วพังกลางทางจะไม่รู้ว่าพังขั้นไหน · และ synthetic `.click()` ใน `eval` ไม่ใช่ trusted click
  (dropdown/component หลายตัวไม่รับ) — ปุ่มสำคัญยังต้อง `AB click`

## Session / iframe / แท็บ

| ต้องการ | ทำยังไง |
|---|---|
| แยก session ต่อ terminal | `CDP_PORT` + `--user-data-dir` คนละอันต่อ terminal — **cookie jar แยกขาด** |
| ใช้ login เดิมไม่ต้อง 2FA ซ้ำ | `--user-data-dir` ชี้ profile ถาวรตัวเดิม (ห้ามลบตอนเก็บกวาด) |
| element ใน iframe | `IFRAME="#frameSel" AB get text "#inner"` — มีผลกับ `eval`/`is`/`get`/`click`/`fill` (same-origin) |
| ปักหมุดแท็บของงานเรา | `export TGT_ID=$(AB newtab "<url>?job=x")` — ไม่ match = error พร้อมรายชื่อแท็บ ไม่ fallback เงียบ |

## ตารางแปลงจาก `agent-browser` เดิม

| agent-browser | `cdp.py` |
|---|---|
| `open <url>` | `nav <url> [wait]` |
| `get url` / `get title` | `url` / `get text "title"` |
| `get text/value/attr/count <sel>` | เหมือนกัน |
| `is visible/enabled/checked <sel>` | เหมือนกัน |
| `click` · `fill` · `type` · `press` | `click` · `fill` · `type` · `key` |
| `scrollintoview <sel>` + `click` | `click` (scrollIntoView ให้ในตัว) |
| `snapshot -i` + ref `@eN` | `a11y [คำค้น]` + ref `@<backendNodeId>` |
| `find role button click --name "X"` | `a11y "X"` แล้ว `click "@<ref>"` |
| `errors --json` / `console --json` | `console` — **collector ผูกกับหน้า ไม่ใช่ buffer สะสม** |
| `wait --fn "<js>"` · `wait <sel>` · `wait --load networkidle` | `wait "<js>" [timeout]` |
| `screenshot <path>` · `screenshot <sel> <path>` | `shot <path>` · `shot <path> <sel>` |
| `diff screenshot --baseline <a> -o <b>` | `diff <a> <b> [out]` |
| `pdf <path>` | `pdf <path>` |
| `set viewport <w> <h> <dsf>` | `shot ... --vw= --vh= --dsf=` (ดูคำเตือนข้างบน) |
| `upload <sel> <path>` | `setfile <sel> <path>` |
| `frame "#sel"` … `frame main` | `IFRAME=#sel` เฉพาะคำสั่งที่ต้องการ (ไม่มี state ค้างให้ลืมออก) |
| `tab new` · `tab close` | `newtab` · `close <marker>` |
| `batch "<cmd>" ...` | รวมเป็น JS ก้อนเดียวแล้ว `evalf` |
| `--session` · `--profile` | `CDP_PORT` + `--user-data-dir` ของ Chrome |
| `connect` · `close --all` · `-Reset` · daemon recovery | **ไม่มีแล้ว** — ไม่มี daemon ให้ recover |
| `record start/stop` · `stream` · `dashboard` | **ตัดทิ้ง** — ดู `docs/ARCHITECTURE.md` §ที่ตัดออกและทำไม |
| `state save/load` · `auth save/login` | ใช้ profile ถาวรแทน (cookie export ข้าม profile ใช้ไม่ได้ตั้งแต่ Chrome 149) |
| `mcp` | ไม่มี |
