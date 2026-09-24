# Engine หลัก — BrowserSkill (`bsk`): วิธีใช้จริง ตัวเลข และกับดัก

ไฟล์นี้เป็นของ `bsk` เท่านั้น. เงื่อนไขว่า **ใช้ได้เมื่อใด** อยู่ที่ `docs/BROWSER-AGENT-STANDARD.md` §4;
กับดักใน [`gotchas.md`](gotchas.md) เป็นของ direct CDP และไม่ได้ย้ายตามมาเอง. ทุกตัวเลขข้างล่างวัดกับ
`bsk` 0.3.0 + Chrome 152 บน Windows และมีแถวใน `docs/CLAIMS-AUDIT.md` — ขยับรุ่นแล้วต้องวัดใหม่.

## การเลือก engine และการอัปเดต

BrowserSkill เป็นค่าเริ่มต้นสำหรับ interactive QA รวม NetSuite เมื่อเจ้าของเครื่องเลือกใช้.
คำสั่งเก่าที่บังคับ `cdp.py` ไม่ใช่เหตุผลให้สลับ engine; ใช้ CDP เฉพาะ capability ที่ตาราง
engine ระบุหรือเมื่อผู้ใช้เลือก. สำหรับ NetSuite อ่าน §3 และ §6 ก่อนเปลี่ยนข้อมูล:
ตรวจ account/environment/role, ติดตั้ง dialog guard และยืนยันผล save จากแหล่งอิสระ.
ถ้า browser ยังไม่ login ให้เจ้าของทำ login/MFA ใน browser ที่เลือก ไม่เปิด profile ใหม่หรือ
เรียก CDP login อัตโนมัติ. ห้ามรบกวนงาน CDP ที่ยังรันอยู่ระหว่างย้าย.

อัปเดตแพ็กเกจ `teibto-browser-qa` จาก commit ที่ตรวจสอบแล้วของ `main` เมื่อต้องการ fixes
ที่ใหม่กว่า release. ติดตั้งทั้ง `SKILL.md`, references, scripts, examples และ schemas พร้อมกัน;
การคัดลอกเฉพาะ SKILL.md ทำให้คำสั่งเรียก runtime ที่ยังเก่า. เก็บ SHA ของแหล่งที่ติดตั้ง.
แยกเวอร์ชันแพ็กเกจนี้ออกจาก `bsk` CLI/extension ซึ่ง runner pin ไว้ที่ 0.3.0.

## 1. ตั้งเครื่อง (ครั้งเดียว)

1. ติดตั้ง CLI แบบ pin รุ่น: รัน `install.ps1` ของ upstream โดยตั้ง `BSK_VERSION=0.3.0` (รุ่นที่ runner pin)
2. เจ้าของ browser ลง extension เองแล้วเปิดสวิตช์ connection ใน popup; agent ไม่ลง extension ให้
3. ให้ host เป็นคน start daemon (`bsk daemon start --foreground` ใน terminal ที่เปิดค้าง)
4. ทุกคำสั่งจาก agent/สคริปต์: `BSK_AUTO_START=0` + `timeout` + เขียน output ลงไฟล์ **ห้าม pipe** —
   `bsk doctor | tail` ที่ auto-start daemon เคยค้างไม่จบเพราะ daemon ถือ pipe ของ shell ไว้ (เห็นครั้งเดียว · `inferred`)
5. เชื่อมหลาย browser ได้ แต่ต้องเลือกเองเสมอ: `--bsk-browser <instance_id>` / `ENGINE2_BROWSER` — ดู id จาก
   `bsk browsers --json`. แยก **profile ทดสอบ** (ไว้รัน fixture ที่เปิด dialog จริง) ออกจาก **browser ที่คนใช้ทำงาน**

### 1.1 หนึ่ง Agent Window ต่อหนึ่งงาน — และหนึ่ง tab ต่อหนึ่ง process

ทุก `bsk session start` เปิด Agent Window ใหม่หนึ่งบานบนจอของเจ้าของ browser. สคริปต์ที่ start session ของตัวเอง
คูณด้วยจำนวน agent = หน้าต่างเด้งหลายสิบบาน และเจ้าของ browser จะปิดมัน (ดู §4 — เกิดแล้ว 2 ครั้ง).

```bash
# ขอ Agent Window ที่ใช้ร่วมกันของเครื่องนี้ — มีอยู่แล้วก็ได้ตัวเดิม ไม่มีก็เปิดให้ครั้งเดียว
SID=$(python scripts/bsk-shared.py ensure)            # --browser <instance> เมื่อเชื่อมหลายตัว
python scripts/flow-runner.py --flow f.yaml --out runs/a --bsk-session "$SID"   # หรือ TEIBTO_BSK_SESSION=$SID
export NSBSK_SESSION="$SID"                           # harness ตัวอย่าง examples/nsbsk.py ใช้ตัวแปรนี้

python scripts/bsk-shared.py status                   # registry ชี้ session ไหน ยังอยู่ไหม
python scripts/bsk-shared.py release                  # เจ้าของงานปิดตอนจบ; ผู้ที่ attach ไม่ต้องทำอะไร
```

`ensure` ยึด lease ต่อ browser instance ระหว่างตัดสินใจ สี่ process ที่เรียกพร้อมกันจึงได้ id เดียวกันและ
เปิดหน้าต่างครั้งเดียว. registry อยู่ที่ `~/.teibto/bsk-sessions/<instance>.json` (override ด้วย
`TEIBTO_BSK_SESSION_ROOT`) เก็บแค่ id/เจ้าของ/เวลา ไม่มี cookie หรือ token. daemon เองก็เก็บ session ที่ทิ้งไว้
เฉย ๆ ด้วย (`idle session stopped` — เห็น 6 ครั้งใน 90 นาทีบนเครื่อง dev) `ensure` จึงตรวจกับ `bsk status`
ทุกครั้งก่อนคืน id เดิม

การชนกันของหลาย agent มีสามชั้น และแก้คนละที่ (วัดกับ bsk 0.3.0 + Chrome 152 · #112):

| ข้อเท็จจริงที่วัดได้ | ผลต่อการใช้งาน |
|---|---|
| session ของ `bsk` รับ **ทีละคำสั่ง** — คำสั่งที่สองที่เข้ามาพร้อมกันถูกปฏิเสธใน ~30–180 ms ด้วย `exit_code 4` + `data.reason: "session_busy"` | ทุก process ที่ใช้ session ร่วมกันต้องผลัดกัน: `scripts/bsk_lease.py` เป็น lease ข้าม process ต่อ session id (`%TEMP%/teibto-bsk-lease/<sid>.lease`) ที่ runner และ `nsbsk.py` ใช้ร่วมกัน |
| คำสั่งที่ถูกปฏิเสธด้วย `session_busy` **ยังไม่ถูก dispatch** — `click` ที่โดนปฏิเสธไม่เปลี่ยนหน้าเว็บเลย (idle → idle) ส่วน click เดียวกันตอนว่างเปลี่ยนเป็น `act-clicked` | รอแล้วส่งใหม่ได้ปลอดภัยแม้เป็นคำสั่งที่เปลี่ยน state; runner รอสูงสุด 30 วินาทีก่อนล้มด้วย `BSK_SESSION_BUSY` |
| คนละ session บน browser เดียวกัน **ทำงานขนานกันได้จริง** (คำสั่ง 1.5 s สองตัว เสร็จใน 1.57 s) | การชนเกิดเฉพาะ *ภายใน* session เดียวกัน; lease จึงล็อกต่อ session ไม่ใช่ต่อ browser |
| คำสั่งที่ไม่ส่ง `--tab-id` ยิงไปที่ **active tab ของ session** และ peer เปลี่ยน active tab ได้ด้วย `tab create` (default = focus) หรือ `tab select` | ทุก process ต้องสร้าง tab ของตัวเองแล้ว pin: `tab create --no-active --url about:blank` แล้วส่ง `--tab-id` ทุกคำสั่งที่เป็น tab-scoped. พิสูจน์แล้ว: worker ที่ไม่ pin ถูก peer ลากไปหน้าอื่น (`?w=A-unpinned` → `?w=C-peer-new-tab`) ส่วน worker ที่ pin อยู่ที่หน้าเดิม |
| tab ที่สร้างโดยไม่ระบุ URL อยู่ที่ `chrome://newtab/` และขับไม่ได้ (`Cannot access a chrome:// URL`) | สร้างด้วย `tab create --no-active --url about:blank` |
| `screenshot` ถ่ายได้เฉพาะ tab ที่ **active** — tab พื้นหลังตอบ `invalid_params` (`tab <id> is not active; screenshot can only capture the visible tab`; แบบ `--full-page` ว่า `Select the target tab before capturing a full-page screenshot`) | ก่อนถ่ายต้อง `tab select` tab ของตัวเอง แล้วถ่ายใน **lease เดียวกัน** ไม่งั้น peer ที่ select tab ของมันแทรกกลางได้ — runner ทำให้แล้ว (#118); คำสั่งอื่นบน tab พื้นหลัง (`navigate`/`evaluate`/`click`/`console`) ทำงานปกติ |
| trusted click ลงใน tab ที่ซ่อนอยู่ (`visibilityState: hidden`) ได้ 9/9 แต่ใช้ 0.4–3.5 s | ใช้ tab พื้นหลังได้; timer/`requestAnimationFrame` ใน tab ที่ซ่อนถูก throttle (`gotchas.md` §18) — wait ช้าลง และหน้าที่ render ด้วย rAF อาจไม่ขึ้น |
| `bsk` ไม่มีคำสั่งย้ายหรือย่อหน้าต่าง (มีแค่ `window resize`) | ถ้าไม่ต้องการให้อะไรเด้งบนจอของคนเลย ต้องใช้ profile เฉพาะงาน + user ของ automation (§7) |

ราคาที่จ่าย: throughput รวมลดลงเพราะผลัดกัน — flow-runner สองตัวบน session เดียวกัน (flow 3 step บนหน้า loopback)
ผ่านทั้งคู่ใน 2.6 วินาที โดยตัวที่มาทีหลังรอ lease 985 ms และเจอ `session_busy` 0 ครั้ง. ตัวเลขนี้อยู่ใน
`run_done.session_sharing` ของทุก run: `lease_wait_ms` คือเวลาที่รอคิว, `busy_waits` > 0 แปลว่ามีใครขับ session
เดียวกันโดยไม่ถือ lease.

สคริปต์ที่ **เปิด** session เองต้องปิดเอง (`with Session(...)` / runner ปิดให้อัตโนมัติ): session ที่ค้างคือหน้าต่าง
ที่ค้างบนจอ — ตรวจด้วย `bsk session list --json` ตอนจบงาน. สคริปต์ที่ **attach** ปิดเฉพาะ tab ของตัวเอง.

## 2. สองทางในการรัน

| ทาง | ใช้เมื่อ | ข้อจำกัด |
|---|---|---|
| `flow-runner.py` (ค่าตั้งต้นคือ `bsk`) | QA และงานเปลี่ยนข้อมูลที่ต้องได้ `run-log.jsonl` / `qa-report.md` / `shots/` | นโยบาย `--dialog` ถูกบังคับด้วยด่านในหน้าเว็บ; `destructive` ต้อง `--allow-destructive`; CSS selector เท่านั้น; ไม่มี `lens`/`netlog`/`stub`/`diff` |
| เรียก `bsk` CLI ตรงจากสคริปต์ของงาน | งานที่เจ้าของระบบสั่งให้เปลี่ยนข้อมูลบน **sandbox** | อยู่นอกด่านของ runner ทั้งหมด — สคริปต์ต้องมีด่านของตัวเองครบตาม §3 |

## 3. ด่านขั้นต่ำของสคริปต์ที่เปลี่ยนข้อมูลผ่าน `bsk`

`bsk` ตอบ **accept** ให้ dialog ทุกชนิดและปิดไม่ได้ (`self-test/engine2/dialog-test.sh`). สคริปต์จึงต้อง:

1. **Identity gate ก่อนทุก save** — อ่าน account + environment จากหน้า (NetSuite: `nlapiGetContext().getCompany()` และ
   `.getEnvironment()==='SANDBOX'`) แล้วหยุดถ้าไม่ตรง. ด่านนี้จับกรณี session หลุดได้ด้วย: หน้า Log In ไม่มี `nlapiGetContext`
2. **กัน dialog ที่ระดับหน้าเว็บ** ก่อนตั้งค่าใด ๆ: แทน `window.alert`/`window.confirm` ด้วยตัวเก็บข้อความ โดย
   `confirm` **ตอบ `false`** (นโยบาย safe) และ `window.onbeforeunload=null`. dialog ที่ไม่เคยเปิด = `bsk` ไม่มีอะไรให้ accept.
   ตรวจ `dialogs` ในผลของทุกคำสั่ง — ถ้าไม่ว่างแปลว่าด่านนี้รั่ว
3. **ห้าม retry คำสั่งที่ทำซ้ำแล้วเกิดผลซ้ำ** (save, เพิ่ม line, submit). retry ได้เฉพาะ `navigate`, การอ่านค่า, screenshot
4. **session หายหลังกด save = ผลไม่ทราบ** — ห้ามกด save ซ้ำ ให้ถาม backend ว่า record เกิดหรือยัง แล้วค่อยตัดสิน.
   runner รายงานกรณีนี้เป็น `BSK_SESSION_LOST` — ครอบคลุมทั้ง `session not registered`, `session is stopping`
   และ RPC timeout ที่ตรวจแล้วว่า session หายจาก `bsk status` จริง; ถ้า **tab ของ run เอง** ถูกปิดจะเป็น
   `BSK_TAB_LOST` (ความหมายเดียวกัน: ผลของ action ล่าสุดไม่ทราบ ห้ามสั่งซ้ำ)
5. ยืนยันผลจากช่องทางที่ไม่ใช่ DOM เดิม (NetSuite: `fetch('<record>.nl?id=N&xml=T')`)

## 4. กับดักที่เจอจริง

| อาการ | สาเหตุ | ทำอย่างไร |
|---|---|---|
| `cdp_failed: Detached while handling command`, หรือ `session not registered or already stopped` กลาง run | **คนปิด Agent Window** — daemon log เขียนว่า `session removed: user closed Agent Window`. เกิด 2 ครั้งใน 12 รอบบน browser ที่เจ้าของใช้งานอยู่ ครั้งหนึ่งเกิด **หลัง** กด Save: record ถูกบันทึกจริงแต่ run รายงานว่าล้ม | อ่าน `bsk logs` ก่อนสรุปว่าเป็นบั๊ก · บอกเจ้าของ browser ก่อนรัน · งานที่ไม่มีคนเฝ้าให้ใช้ profile เฉพาะงาน + user ของ automation ไม่ใช่ browser ของคน · ทำตามด่าน 4 ของ §3 |
| login ฝั่งหนึ่งแล้วอีกฝั่งหลุด | user เดียวกัน login NetSuite สอง browser (browser ของคน กับ profile ของ `cdp.py`) เตะ session กัน เมื่อ account ไม่เปิด multiple sessions (`inferred`: เห็นทั้งสองทิศทาง ยังไม่ได้ A/B) | ทำงานฝั่ง `cdp.py` ให้จบก่อน แล้วค่อยให้คน login ฝั่ง `bsk` ครั้งเดียว · ทางแก้ถาวรคือ user แยกสำหรับ automation |
| ตั้ง customer บนฟอร์ม NetSuite แล้ว subsidiary ไม่ source | ฟอร์มยัง init ไม่จบ: `NS.form.isInited()` เป็น `true` หลัง `load` อีก ~7–10 วินาทีบนฟอร์ม Sales Order | รอ `NS.form.isInited()` ก่อนแตะฟอร์ม แล้วตั้งค่า **ครั้งเดียว** — ดีกว่าวน re-fire (§5) |
| ใส่ `&entity=<id>` ใน URL ของฟอร์มเพื่อให้ server source ให้ แล้ว item line พังด้วย `Cannot read properties of undefined (reading 'checkvalid')` | เส้นทาง prefill ทำให้ `NS.form.isInited()` เป็นจริงก่อน item machine พร้อม (ล้ม 1 ใน 2 รอบ) | **ไม่ใช้** — ประหยัดได้ ~3 วินาทีแต่แลกกับความไม่เสถียร |
| `console` ของ run แดงเพราะ favicon 404 | entry ชนิด `log` เป็นของ browser ไม่ใช่ของหน้า | adapter นับเฉพาะ `console.error` และ exception; resource ที่โหลดไม่ได้เป็นงานของ `lens netlog` ซึ่ง engine นี้ไม่มี |
| `bsk fill <sel> --value "- ข้อ 1…"` ตอบ `unexpected argument '- ' found` | ค่าที่ขึ้นต้นด้วย `-` ถูก CLI อ่านเป็น flag (บันทึกแบบ bullet ขึ้นต้นด้วย `-` เสมอ) | ใช้รูป `--value=<ค่า>` ติดกันเสมอ (เห็น 2026-09-24 · `verified`) |
| `bsk fill` ช่อง `<input type=date>` ตอบ `target element is not fillable` | fill ไม่รองรับ input ชนิดวันที่ และคีย์บอร์ดไม่ถึง inner editor ของช่องวันที่ — `click` แล้ว `press` ตัวเลข (ไม่ว่าไม่ระบุ ref, `--selector` หรือ `--ref`) ไม่ทำให้ `.value` เปลี่ยนเลย ขณะที่ input text ปกติรับตัวอักษรเดียวกันได้ | ตั้งด้วย `evaluate` แล้ว dispatch `input`+`change`: `d.value='2026-09-24';d.dispatchEvent(new Event('input',{bubbles:true}));d.dispatchEvent(new Event('change',{bubbles:true}))` แล้วอ่าน `.value` ยืนยัน (bsk 0.3.1 · Chrome 153 · 2026-09-24 · `verified`) |
| `bsk fill` ช่องค้นหาของหน้า React (เช่น product search ของ Tencent Cloud console) ตอบ `fill could not verify the expected value` และ `.value` ยังว่าง | component คุมค่าเองและทิ้งค่าที่ถูกตั้งตรง ๆ | `click` ช่องนั้นแล้ว `press` ทีละตัวอักษร แล้วอ่าน `.value` ยืนยัน — contenteditable ของหน้าเดียวกัน `fill` ได้ปกติ (2026-09-24 · `verified`) |
| selector กว้างอย่าง `textarea` พิมพ์ลงช่องที่ไม่ใช่ช่องแชท แล้วปุ่มส่งเป็น disabled | panel ข้าง (เช่น Agent Builder ของ LibreChat) ถูกจำไว้ใน localStorage และเปิดค้างข้าม tab — `textarea` ตัวแรกคือช่อง Instructions | ใช้ id ของช่องจริง (`#prompt-textarea`) เสมอ (2026-09-24 · `verified`) |
| `bsk fill` ช่องพิมพ์ของ Slack (`.ql-editor` / `[data-qa="texty_input"]`): แบบ default ตอบ `the fill target changed during the action` แล้ว **ข้อความเดิมถูก wipe และค่าใหม่ไม่ลง**; แบบ `--no-clear` ตอบ `fill could not verify the expected value` แต่ค่าลงจริง | composer เป็น Quill contenteditable — รอบ "wipe ก่อนพิมพ์" ของ default ไปเปลี่ยน node/คลาส `ql-blank` ระหว่างทางจนขั้นตรวจค่าไม่ผ่าน; `observe` ไล่ tree ฝั่ง sidebar ไม่ถึง main panel จึงไม่เห็น `textbox "Message to <channel>"` | ใช้ `fill --no-clear` — **ห้ามใช้ default บนช่องที่มี draft** · เอา ref จาก `snapshot` เมื่อ `observe` ไม่เห็นช่อง · อ่านค่าจริงด้วย `evaluate` ก่อนตัดสิน ห้าม retry รัว · ส่งจาก composer ของ **ห้อง** ด้วย `press Enter` (แถวถัดไปอธิบายกรณีที่ส่งไม่ออก) (bsk 0.3.1 · Chrome 153 · 2026-09-24 · `verified`) |
| `fill` ลงช่อง Slack ที่ว่างอยู่แล้ว `press Enter` หรือคลิกปุ่มส่ง **ไม่ทำอะไร** (บางรอบข้อความในช่องหายเงียบ) ทั้งที่ `evaluate` อ่านข้อความกลับได้ | `fill` เขียน DOM แต่ **โมเดล (delta) ของ Quill ยังว่าง** — Enter/ปุ่มส่งอ่านจากโมเดล ไม่ใช่ DOM; อาการนี้ยังพ่วง `fill could not verify the expected value` ด้วยเหตุผลเดียวกัน | ให้ของจริงเข้าโมเดลผ่านทางของ Slack เองก่อน: `fill --no-clear @Teib` → autocomplete ขึ้น → `press Enter` → เช็ค `[data-qa="texty_input"] ts-mention` ≥ 1 → `fill --no-clear '<ข้อความ>'` → อ่าน `textContent` ให้ตรงทั้งก้อนก่อนส่ง · **อย่าตัดสินว่าส่งแล้วจาก exit 0** (bsk 0.3.1 · Chrome 153 · 2026-09-24 · `verified`) |
| เปิดแท็บใหม่เข้า channel แล้ว `fill` `[data-qa="texty_input"]` ตัวแรก ปรากฏว่าไปต่อท้าย **draft เดิมของ thread** (`@Teib` → `@Teib@Teib` แล้ว Enter ส่งออกไปจริง) | Slack sync draft และสถานะ thread panel ต่อผู้ใช้ — แท็บใหม่มาพร้อม panel ที่เปิดค้างและ draft เดิม จึงมี `texty_input` สองตัว (ตัวแรกอาจเป็นของ panel) | scope ให้ชัดทุกครั้ง: ช่องของห้อง = `.p-message_pane_input_inner_main [data-qa="texty_input"]`, ช่องของ thread = `[data-qa="reply_container"] [data-qa="texty_input"]`; อ่านค่าที่มีอยู่ก่อน fill (bsk 0.3.1 · Chrome 153 · 2026-09-24 · `verified`) |
| `press Enter` ใน reply box ของ thread ไม่ส่ง (3 ครั้ง) และ `click [data-qa="texty_send_button"]` (aria-label "Send now") ก็ไม่ส่ง ทั้งที่ข้อความอยู่ในช่องและปุ่มเป็น `aria-disabled="false"` | `inferred` — ยังไม่ได้แยกสาเหตุ (โมเดล/draft) แต่ยืนยันว่าเป็นอาการเฉพาะของช่องใน panel: composer ของห้องใน session เดียวกัน Enter ส่งได้ | อย่าใช้ reply box ของ panel เป็นทางส่ง; ตอบ/ทดสอบผ่าน composer ของห้อง หรือให้เจ้าของเปิด thread แล้วพิมพ์เอง (bsk 0.3.1 · Chrome 153 · 2026-09-24 · `verified`) |
| หลังเคยส่งข้อความในแท็บหนึ่งแล้ว `document.activeElement` ชี้ `[data-qa="texty_input"]` แต่ `press` (Enter/Backspace/ตัวอักษร) ไม่มีผลเลย ทั้งที่ `visibilityState` = `visible` และ `hasFocus()` = `true` | `inferred` — node ของ composer ที่ค้างใน DOM ยังตอบ `activeElement` แต่ไม่ผูกกับ editor ที่ยังทำงาน; `reload` แล้วค่าที่อ่านได้จากช่องก็ยังไม่ตรงกับที่พิมพ์ | ตรวจว่าคีย์ถึงช่องจริงด้วย `press` ตัวอักษรหนึ่งตัวแล้วอ่านค่ากลับ ถ้าไม่ลงให้เปิดแท็บใหม่ (`tab create --no-active --url`) แล้วทำในแท็บใหม่ ไม่วน retry ในแท็บเดิม (bsk 0.3.1 · Chrome 153 · 2026-09-24 · `verified`) |
| ต้องลบข้อความทดสอบที่ส่งผิด แต่ `hover` ที่ข้อความไม่ทำให้ toolbar ของ Slack ขึ้น (`[data-qa="message_actions"]` = 0 ทั้งก่อนและหลัง hover) | Slack เรนเดอร์เมนูของข้อความจาก hover ที่ขับด้วย JS ของตัวเอง — แต่ปุ่ม `More actions` มีอยู่ใน DOM ของ message row แล้วและ trusted click โดน | `click '[data-item-key="<ts>"] [aria-label="More actions"]'` → `click [data-qa="delete_message"]` → `click [data-qa="dialog_go"]` แล้วยืนยันว่า item key นั้นหายจาก DOM (bsk 0.3.1 · Chrome 153 · 2026-09-24 · `verified`) |

## 5. Performance ที่วัดได้ (NetSuite SB2, สร้าง customer + Sales Order หนึ่งคู่)

| รุ่นของสคริปต์ | engine | ต่อคู่ | คำสั่งต่อคู่ |
|---|---|---|---|
| baseline: หนึ่ง evaluate ต่อ field, วน re-fire customer, poll save ทุก 1 วิ | `cdp.py` แบบ process ต่อคำสั่ง | 64.6 s (n=1) | 53 |
| baseline เดียวกัน | `bsk` | 68.1 s (n=1) | 53 |
| tuned: รอ `NS.form.isInited()`, ตั้ง field ทั้งชุดใน evaluate เดียว, poll save ทุก 0.25 วิ | `bsk` | **median 47.7 s** (min 43.7 · max 51.0 · n=6, 6/6 ผ่าน, 0 retry, 0 dialog) | 20–28 |

- ค่าใช้จ่ายของ transport: `bsk` ≈ 33–58 ms ต่อคำสั่ง; `cdp.py` แบบเปิด process ใหม่ทุกคำสั่ง ≈ 205 ms
  (JSONL session ของ runner ไม่ได้อยู่ในการเทียบนี้). หลัง tune transport เหลือ ~2–3% ของเวลาทั้งหมด
- ที่เหลือเป็นเวลาของ NetSuite เอง และ engine ไหนก็ลดไม่ได้: บันทึก Sales Order ~11.9 s · sourcing หลังเลือก customer ~9.6 s ·
  เปิดฟอร์ม Sales Order จนพร้อม ~7.4 s
- Agent Window แบบ `--no-focus` (พื้นหลัง) เทียบกับแบบ focus: 48.1 s กับ 47.2 s (n=3 ต่อฝั่ง) — **ไม่ต่างกัน**;
  ใช้ `--no-focus` เพื่อไม่กวนคนที่ใช้ browser อยู่
- การ tune ที่ได้ผลจริงคือ **ลดจำนวนรอบที่รอผิดจังหวะ** ไม่ใช่เปลี่ยน engine: baseline เสีย ~24 s ไปกับการ re-fire customer
  ก่อนฟอร์มพร้อม

## 6. มาตรฐานการขับ NetSuite ผ่าน `bsk`

สกัดจากการทดสอบ UI จริงบน SB2 สี่รูปแบบพร้อมกัน (2026-09-19): O2C หลัง Sales Order · input จริงเทียบ nlapi ·
flow read-only ผ่าน runner 3 รอบ · edit + validation + dirty form. ทุกข้ออ้างสิ่งที่เห็นจริง; ตัวเลขมีแถวใน
`docs/CLAIMS-AUDIT.md`. harness ตัวอย่างที่ฝังข้อ 6.1–6.4 ไว้แล้ว: `examples/nsbsk.py`.

### 6.1 ความพร้อมของหน้า

| กฎ | หลักฐาน |
|---|---|
| หน้า **ฟอร์ม**: รอ `NS.form.isInited()` ก่อนแตะ field แล้วตั้งค่าครั้งเดียว | ฟอร์ม Sales Order พร้อมหลัง `load` อีก 7–10 s; ตั้งก่อนนั้น sourcing หายเงียบ (baseline เสีย ~24 s) |
| ก่อน **คลิก** ใด ๆ บนหน้า record (tab, ลิงก์ในฟอร์ม): รอ `NS.form.isInited() && NS.form.isValid()` | anchor ของ tab มี `onclick="if (NS.form.isInited() && NS.form.isValid()) ShowTab(...)"` — ถ้า tab ก่อนหน้ายัง lazy-load อยู่ คลิกถูกทิ้งเงียบและ `bsk` รายงานว่าคลิกสำเร็จ: Relationships 1/3 → 3/3 |
| หน้า **view**: `navigate --wait-until domcontentloaded` แล้วรอ element ที่ต้องใช้ (`#edit`) | 4,888 → 4,124 ms (−16%) |
| หลังคลิกที่เปลี่ยนหน้า รอ **ปลายทาง** (`location.href` + heading) ห้ามใช้ `wait` แบบกำหนดเวลา | 17.2 s → 3.7 s (−78%), 3/3 ทั้งสองแบบ |

### 6.2 การคลิกและการกรอก

| กฎ | หลักฐาน |
|---|---|
| งานเตรียมข้อมูลใช้ nlapi (`fire=true, sync=true`); input จริงใช้เมื่อ **พฤติกรรมของ widget** คือสิ่งที่ทดสอบ | field phase เท่ากัน (2.2 s ทั้งคู่) แต่ input จริงใช้คำสั่ง 54 ต่อ 24 และมีกับดักค่าผิดเงียบ |
| ห้าม `bsk fill` ลงช่อง dropdown (`inpt_<field>_N`) และห้าม `bsk select` | `fill` ได้ `{"inpt":"Service","hddn":"","api":""}` — จอถูก ค่าว่าง; ฟอร์ม classic มี `<select>` 0 ตัว |
| dropdown ด้วย UI จริง = trusted click ที่ `input[id^=inpt_<field>_]` → รอ `div.dropdownDiv` → trusted click แถว `#nlN` | วิธีเดียวที่ commit ค่า; ถ้า list ไม่เปิดใน 1 s ให้คลิกซ้ำ (คลิกระหว่าง sourcing หลัง subsidiary ถูกกลืน) |
| หลังทุก field: `nlapiGetFieldValue(field)` ต้อง **เท่ากับ internal id ที่ตั้งใจ** — ไม่ใช่แค่ไม่ว่าง | `press "C"` บน dropdown เลื่อนไปตัวถัดไปและ commit: status 13 → 15 เงียบ ๆ |
| ตรวจ `offsetParent` ของ field และเปิด subtab เจ้าของก่อน | `currency`/`terms` อยู่ใน `financial_div` ที่ซ่อนจนกว่าจะคลิก `#financialtxt` |
| ห้ามกด Enter ใน field; ห้ามใช้ภาพหน้าจอหรือค่าที่เห็นเป็นหลักฐานของค่าที่เก็บ | Enter = submit; `inpt` กับ `hddn` แยกกันได้ (`{"inpt":"CUSTOMER","hddn":"13"}`) |
| หาปุ่ม action ด้วย **classic id** (`#edit`, `#approve`, …) + label เท่ากันพอดี + `offsetParent` ไม่ null | จับ substring "actions" ไปโดน "MFG Transactions" → `element_not_visible` |
| ไม่มีปุ่ม = ถูกบล็อก; ห้ามเลี่ยงด้วย URL `transform=` | SO ที่ยังไม่อนุมัติยังเปิดฟอร์ม Item Fulfillment พร้อม `#submitter` ได้ (HTTP 200) |

### 6.3 Save และการแจ้งปัญหา

| กฎ | หลักฐาน |
|---|---|
| ยืนยัน save ด้วย **marker ในหน้า** ที่ต้องหายไป (`window.__navmark`) ไม่ใช่ `id=` ใน URL | URL ของโหมด edit มี `id=` อยู่แล้ว — probe แบบเดิมรายงานสำเร็จโดยยังไม่ได้ save |
| หลังคลิก Save อ่าน `window.__alerts` คู่กับ marker: marker ยังอยู่ + มี alert = ถูกปฏิเสธในหน้าเดิม | mandatory ว่าง, VAT ยาวเกิน, และ "Another user has updated this record…" มาเป็น `alert` ทั้งหมด; `.uir-alert-box` ไม่ถูกใช้เลยบนฟอร์ม customer |
| ห้ามเรียก `save_record()` เพื่อวินิจฉัย | เป็นการ submit จริงอีกครั้ง |
| `bsk fill` ที่ตอบ `fill_value_mismatch` คือ **ผลของ validation** ห้าม retry | field VAT ตัดเหลือ 13 ตัว + alert ระหว่างพิมพ์ |
| `effect_state: unknown` (`input_cleanup_failed`) = input ถูกส่งแล้ว: สังเกตหน้า ห้ามสั่งซ้ำ | คลิก View ล้มแบบนี้ 1 ใน 4 ทั้งที่ navigation เกิดจริง · runner: `BSK_EFFECT_UNKNOWN` |
| ปิดท้ายทุกขั้นด้วย `fetch('<record>.nl?id=N&xml=T')` | ไม่ได้รับผลจากฟอร์ม stale ที่เปิดค้าง; NetSuite มี optimistic lock (`version` + `lastmodifieddate`) — save ที่ชนถูกปฏิเสธ ไม่ใช่ last-write-wins บน customer |

### 6.4 Dialog, dirty form และหน้าที่ไม่ใช่ classic

| กฎ | หลักฐาน |
|---|---|
| ติดตั้ง guard ระดับหน้าเว็บทุกครั้งที่เปลี่ยนหน้า และ assert `dialogs` ว่างหลังทุก `navigate` | 0 dialog ตลอดทุก loop; เคสควบคุมที่ใส่ handler เองพิสูจน์ว่า `beforeunload` ที่หลุดจะโผล่ใน `dialogs` เป็น `accepted` |
| ไม่ต้องติดตั้ง guard ซ้ำหลังพิมพ์จริง | `onbeforeunload` ยังเป็น `null` หลัง keystroke จริง 2/2; ตรวจด้วย `=== null` เพราะ `typeof null` คือ `"object"` |
| ทิ้งฟอร์ม dirty ด้วย `navigate` ได้เลย | ไม่มี prompt และค่าถูกทิ้ง 3/3 (ยืนยันฝั่ง server) · อย่าใช้ `NS.form.isChanged()` — เป็น `true` ตั้งแต่โหลด |
| หน้าไม่มี `nlapiGetContext` (suitelet/React/Notice): ผ่านด่านได้เมื่ออยู่บน host ของ sandbox **และ** session เดียวกันเคยพิสูจน์ company + SANDBOX บนหน้า classic แล้ว | Batch Approval ของ bundle APC (`scriptlet.nl?script=2024`) เป็น React; host อย่างเดียวไม่พอสำหรับด่านแรก |
| ห้าม `DOMParser` กับหน้าฟอร์มทั้งหน้า; ใช้ regex บน text หรือ `xml=T` | parse หน้า 2.7 MB ทำ session ตาย; scan `querySelectorAll('*')` 16.7 s เทียบ query เจาะจง 24 ms |

### 6.5 Flow read-only ผ่าน `--engine bsk`

- หนึ่ง pattern ต่อหนึ่ง flow และ scenario ยืนยันตัวตนขึ้นก่อน — scenario ที่ล้มหยุดทั้ง run
- พิสูจน์การสลับ tab ด้วยการมองเห็น (`#<tab>_div.offsetParent!==null` และ tab ก่อนหน้า `===null`) — `innerText` ของ div ที่ซ่อนยังคืนข้อความ = false pass
- filter/sort ของ list ใช้ URL parameter แล้ว assert คุณสมบัติของข้อมูล (id เรียงลง, status เดียว) ไม่ใช่แค่ heading
- negative case (record ไม่มี / Page not found) แยก flow: หน้า Notice ของ NetSuite throw `TypeError … appendChild` เอง console gate จึงทำให้ verdict เป็น FAIL ทั้งที่ assert ผ่าน 3/3
- 27/27 identity step ผ่าน, 0 dialog, 3 รอบ

### 6.6 `perf_budget_ms` ที่แนะนำ (ค่าสูงสุดที่เห็น × ~2)

| ชนิดหน้า | median ที่วัดได้ | budget |
|---|---|---|
| home / context | 2.2 s | 10000 |
| list มาตรฐาน (≤500 แถว) | 2.3 s | 10000 |
| transaction list 1000 แถว | 7.7 s | 20000 |
| saved-search list → results | 4.1 s + 1.6 s | 15000 |
| record view ผ่าน `open` (SO 5.5 s · item 3.5 s) | — | 20000 (item 15000) |
| record view ผ่านคลิก + รอปลายทาง | 2.2–3.7 s | 15000 |
| สลับ tab | 0.4 s | 5000 |
| หน้า error / Notice | 2.0 s | 10000 |
| ฟอร์ม edit จนพร้อม | ~18 s (SO) · ~3 s (customer) | วัดต่อฟอร์ม |
| edit → save → verify (customer) | 8.2 s (7.6–10.8) | — |
| สร้าง customer + Sales Order | 47.7 s (43.7–51.0) | — |

### 6.7 หน้า React/suitelet และ workflow ที่ต่อหลาย record

จากรอบที่เดิน Order-to-Cash เต็ม loop (2026-09-19): สร้าง Sales Order ด้วย item ที่มีสต็อกจริงได้ (40.3 s, 0 dialog)
แต่ **หยุดที่ approve** — bundle อนุมัติของ account ไม่ได้สร้าง control record ให้ SO ใบนั้น หน้า Batch Approval จึงไม่มีแถวให้กด.
fulfill และ invoice **ยังไม่ได้ขับ**.

| กฎ | หลักฐาน |
|---|---|
| ก่อนขับ stage ของ workflow แบบ custom ให้พิสูจน์ **control record ของ workflow นั้น** ไม่ใช่สถานะ native | SO เป็น `Pending Approval` แต่ search `customrecord_apc_record_approval_level` ตาม transaction ได้ 0 แถว; SO ที่อยู่ในคิวจริงมี record (`level 1`, approver "Sales Manager") |
| อย่าเชื่อสิ่งที่คิวแสดง — ตรวจ transaction ของแต่ละแถวฝั่ง server | สองแถวที่ขึ้น "รออนุมัติ" ฝั่ง server เป็น `fullyBilled` และ `pendingFulfillment` ไปแล้ว |
| บนหน้า React รอ **text marker จากข้อมูล** (`body.innerText` มี prefix ของเลขเอกสาร) ไม่ใช่ `<table>/<tr>/checkbox` | หน้า Batch Approval มี `<table>` 0, `<tr>` 0, checkbox 0 — wait บน `tr` หมดเวลา 45 s ขณะที่ marker คืนทันทีที่ข้อมูลมา (~9–11 s) |
| ระบุแถวด้วยการหา element ในสุดที่มีเลขเอกสาร แล้วไต่ขึ้นไปหา ancestor ที่ถือปุ่ม action | grid เป็น div ล้วน; selector แบบ `tr,li,[role=row]` ไม่เจออะไร |
| ปุ่ม action ที่ `offsetParent === null` แปลว่า "แถวยังไม่ active" ไม่ใช่ "ไม่มีสิทธิ์" | ปุ่ม อนุมัติ/ปฏิเสธ อยู่ใน DOM ของทุกแถวตั้งแต่ก่อนเลือก |
| ห้ามใช้ substring ใน HTML ของ list หลาย MB เป็นหลักฐานว่า record ผูกกัน — query field | list 2.28 MB `indexOf(เลขเอกสาร)` ได้ `true` ทั้งที่ไม่มี record ไหนอ้างถึง |
| ช่องค้นหาแบบ controlled input ของ React ไม่ตอบ `bsk fill` — กรองด้วย tab/URL แทน | พิมพ์เลขเอกสารแล้ว list ไม่เปลี่ยน |
| `evaluate` ที่ `fetch('/app/...')` บน session ใหม่ล้ม `Failed to parse URL` เพราะ tab ยังเป็น `about:blank` — เปิดหน้า classic ก่อนเสมอ | ได้ทั้ง base URL และด่าน identity ของหน้า non-classic ในคราวเดียว |
| availability ต่อ location ต้องมาจาก search (`locationquantityavailable`) — `item.nl?xml=T` ไม่มี machine `locations` | item 617: non-lot, non-serial, ไม่มี bin, available 1000 ที่ location 30 |
| stage ที่ไม่มีทางเดินที่ชอบธรรม: เก็บ (ก) ปุ่มที่มองเห็นบน record (ข) ข้อความของคิว (ค) approver ใน control record แล้ว **หยุด** | ห้ามใช้ URL `transform=` หรือแก้ field สถานะเพื่อสร้างการเปลี่ยนสถานะเอง |

### 6.8 Order-to-Cash ครบ loop (SB2, 2026-09-20)

`SO-TH-260900019` เดินจาก UI จริงจนจบ: สร้าง SO → Send to Approve → Approve → Item Fulfillment `IFS-TH-260900002`
(Shipped) → Invoice `INT-TH-260900001` (107.00, ภาษี 7.00) → SO เป็น **Billed**. ทุกขั้นยืนยันกับ record XML ฝั่ง server,
0 dialog, ใช้ Agent Window เดียว. ก่อนจะผ่านได้ต้องแก้บั๊กของ bundle อนุมัติ 5 จุด (`Teibto/TEIBTO-Approval-Control#15`) และตั้ง
parameter ที่ขาดของกลไกอนุมัติตัวที่สองหนึ่งตัว.

| ขั้น | ขับด้วย | เวลา |
|---|---|---|
| สร้าง SO (item มีสต็อก) | nlapi + `ns_save()` | ~37–40 s |
| Send to Approve | trusted click `#custpage_btn_sendtoapprove` | ผลฝั่ง server ตามมา ~15 s |
| Approve | trusted click `#custpage_btn_approve` บนหน้า SO | หน้า re-render เอง |
| Fulfill | `#process` → ฟอร์ม Item Fulfillment → `shipstatus=C` → save | 56.6 s (ฟอร์มพร้อม 15.2 s · save 24.5 s) |
| Invoice | `#nextbill` → ฟอร์ม Invoice → save | 109.4 s (ฟอร์มพร้อม 37.6 s · save 55.2 s) |

| กฎ | หลักฐาน |
|---|---|
| ปุ่มของ bundle (`form.addButton`) เป็น **fire-and-forget**: `onclick` แค่โหลด AMD module; ไม่มี confirm/modal/navigation. ถือว่า commit ทันทีที่คลิก แล้ว poll server ≥30 s — ห้ามคลิกซ้ำ | Send to Approve: ผลมาถึงที่ ~15 s; `typeof window.<fn>` เป็น `undefined` เสมอ จึงใช้เป็นสัญญาณพร้อมไม่ได้ |
| หน้า **view** พร้อมเมื่อ `#edit` อยู่ + `NS.form.isValid()` — `NS.form.isInited()` ไม่เคยเป็น true บนหน้า view | รอ `isInited()` บนหน้า view = ค้าง 45 s |
| `input_cleanup_failed` (`EffectUnknown`) เกิดซ้ำได้ **ต่อปุ่ม** ไม่ใช่สุ่ม: จับ exception แล้วรอปลายทาง ห้ามคลิกซ้ำ | `#process` 3/3 และ `#nextbill` 1/1 — navigation เกิดจริงทุกครั้ง |
| save ที่ SuiteScript ปฏิเสธลงที่หน้า **`Notice`** (ไม่ใช่ `Error`, ไม่มี alert): อ่าน `document.body.innerText` ของหน้านั้น และกลับไปหน้า classic ก่อนเรียก `nlapi*` | `SOA_FULFILL_BLOCKED …`; harness คืน `rejected` ทันทีแทนการรอจนหมดเวลา |
| record เดียวอาจมี **กลไกอนุมัติมากกว่าหนึ่งตัว** — ก่อนสรุปว่า "อนุมัติแล้ว" อ่านทุก field ที่ชื่อมี `approval` จาก `xml=T` | APC = 3 (Approved) ขณะที่ `custbody_soa_approval_status = Pending Approval` และ script อีกตัวปฏิเสธ fulfillment |
| สคริปต์ที่เปลี่ยนข้อมูลต้องตรวจ precondition ของตัวเองก่อนคลิก (ปุ่มอยู่ + label ตรง + สถานะฝั่ง server) | รันซ้ำหลังสคริปต์ตายกลางทาง: ด่านปฏิเสธ (`Approve button not clickable`) แทนการอนุมัติซ้ำ; ขั้น invoice ปฏิเสธเมื่อเจอสองปุ่ม (`nextbill`, `billremaining`) จนกว่าจะระบุปุ่ม |
| field สถานะที่เป็น `input[type=hidden]` และถูกเขียนโดย `beforeSubmit` เท่านั้น **ไม่ใช่ affordance** — เก็บหลักฐานแล้วหยุด; ทางแก้คือ config ที่ script เองบอกว่าขาด | `custscript_soa_thb_currency_id` ไม่ถูกตั้ง → SO ทุกใบถูกพัก; ตั้งเป็น id ของ THB แล้ว SO ใหม่ได้ `Approved` ตอนสร้าง |

## 7. สถานะความพร้อมใช้งาน

| ใช้ได้แล้ว | ยังไม่พร้อม |
|---|---|
| QA และงานเปลี่ยนข้อมูลผ่าน `flow-runner.py` (engine ตั้งต้น) บน browser ที่คน login ไว้ — verdict `PASS` ได้ | CI gate ของ `bsk` — drift ตรวจได้เฉพาะบนเครื่อง dev (`self-test/engine2/*.sh`) |
| งานเปลี่ยนข้อมูลบน **sandbox** ด้วยสคริปต์ที่มีด่าน §3 ครบ | งานเปลี่ยนข้อมูลบน **Production** — ต้องได้คำสั่งตรงจากเจ้าของระบบทุกครั้ง |
| รันมีคนเฝ้า บน browser ของคนนั้นเอง — agent 4 ตัวพร้อมกันใน session เดียวทำงานได้ | รันไม่มีคนเฝ้า / หลายเครื่อง — ต้องมี profile เฉพาะงาน + user ของ automation + CI gate ของ `bsk` |
| Order-to-Cash ครบ loop บน **sandbox** ด้วยสคริปต์ที่มีด่าน §3 ครบ (§6.8) | รัน loop แบบเดียวกันบน Production — ห้าม จนกว่าจะมีมติเรื่อง engine ที่สองกับการเขียนข้อมูล |
| | Production ทุกกรณี |
