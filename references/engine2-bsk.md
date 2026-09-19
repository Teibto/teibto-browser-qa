# Engine ที่สอง — BrowserSkill (`bsk`): วิธีใช้จริง ตัวเลข และกับดัก

ไฟล์นี้เป็นของ `bsk` เท่านั้น. เงื่อนไขว่า **ใช้ได้เมื่อใด** อยู่ที่ `docs/BROWSER-AGENT-STANDARD.md` §4;
กับดักใน [`gotchas.md`](gotchas.md) เป็นของ direct CDP และไม่ได้ย้ายตามมาเอง. ทุกตัวเลขข้างล่างวัดกับ
`bsk` 0.3.0 + Chrome 152 บน Windows และมีแถวใน `docs/CLAIMS-AUDIT.md` — ขยับรุ่นแล้วต้องวัดใหม่.

## 1. ตั้งเครื่อง (ครั้งเดียว)

1. ติดตั้ง CLI แบบ pin รุ่น: รัน `install.ps1` ของ upstream โดยตั้ง `BSK_VERSION=0.3.0` (รุ่นที่ runner pin)
2. เจ้าของ browser ลง extension เองแล้วเปิดสวิตช์ connection ใน popup; agent ไม่ลง extension ให้
3. ให้ host เป็นคน start daemon (`bsk daemon start --foreground` ใน terminal ที่เปิดค้าง)
4. ทุกคำสั่งจาก agent/สคริปต์: `BSK_AUTO_START=0` + `timeout` + เขียน output ลงไฟล์ **ห้าม pipe** —
   `bsk doctor | tail` ที่ auto-start daemon เคยค้างไม่จบเพราะ daemon ถือ pipe ของ shell ไว้ (เห็นครั้งเดียว · `inferred`)
5. เชื่อมหลาย browser ได้ แต่ต้องเลือกเองเสมอ: `--bsk-browser <instance_id>` / `ENGINE2_BROWSER` — ดู id จาก
   `bsk browsers --json`. แยก **profile ทดสอบ** (ไว้รัน fixture ที่เปิด dialog จริง) ออกจาก **browser ที่คนใช้ทำงาน**

## 2. สองทางในการรัน

| ทาง | ใช้เมื่อ | ข้อจำกัด |
|---|---|---|
| `flow-runner.py --engine bsk` | QA แบบ read-only ที่ต้องได้ `run-log.jsonl` / `qa-report.md` / `shots/` | step ต้องประกาศ `risk: read`; verdict สูงสุด `PASS(inferred)` + exit 1; CSS selector เท่านั้น |
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
   runner รายงานกรณีนี้เป็น `BSK_SESSION_LOST`
5. ยืนยันผลจากช่องทางที่ไม่ใช่ DOM เดิม (NetSuite: `fetch('<record>.nl?id=N&xml=T')`)

## 4. กับดักที่เจอจริง

| อาการ | สาเหตุ | ทำอย่างไร |
|---|---|---|
| `cdp_failed: Detached while handling command`, หรือ `session not registered or already stopped` กลาง run | **คนปิด Agent Window** — daemon log เขียนว่า `session removed: user closed Agent Window`. เกิด 2 ครั้งใน 12 รอบบน browser ที่เจ้าของใช้งานอยู่ ครั้งหนึ่งเกิด **หลัง** กด Save: record ถูกบันทึกจริงแต่ run รายงานว่าล้ม | อ่าน `bsk logs` ก่อนสรุปว่าเป็นบั๊ก · บอกเจ้าของ browser ก่อนรัน · งานที่ไม่มีคนเฝ้าให้ใช้ profile เฉพาะงาน + user ของ automation ไม่ใช่ browser ของคน · ทำตามด่าน 4 ของ §3 |
| login ฝั่งหนึ่งแล้วอีกฝั่งหลุด | user เดียวกัน login NetSuite สอง browser (browser ของคน กับ profile ของ `cdp.py`) เตะ session กัน เมื่อ account ไม่เปิด multiple sessions (`inferred`: เห็นทั้งสองทิศทาง ยังไม่ได้ A/B) | ทำงานฝั่ง `cdp.py` ให้จบก่อน แล้วค่อยให้คน login ฝั่ง `bsk` ครั้งเดียว · ทางแก้ถาวรคือ user แยกสำหรับ automation |
| ตั้ง customer บนฟอร์ม NetSuite แล้ว subsidiary ไม่ source | ฟอร์มยัง init ไม่จบ: `NS.form.isInited()` เป็น `true` หลัง `load` อีก ~7–10 วินาทีบนฟอร์ม Sales Order | รอ `NS.form.isInited()` ก่อนแตะฟอร์ม แล้วตั้งค่า **ครั้งเดียว** — ดีกว่าวน re-fire (§5) |
| ใส่ `&entity=<id>` ใน URL ของฟอร์มเพื่อให้ server source ให้ แล้ว item line พังด้วย `Cannot read properties of undefined (reading 'checkvalid')` | เส้นทาง prefill ทำให้ `NS.form.isInited()` เป็นจริงก่อน item machine พร้อม (ล้ม 1 ใน 2 รอบ) | **ไม่ใช้** — ประหยัดได้ ~3 วินาทีแต่แลกกับความไม่เสถียร |
| `console` ของ run แดงเพราะ favicon 404 | entry ชนิด `log` เป็นของ browser ไม่ใช่ของหน้า | adapter นับเฉพาะ `console.error` และ exception; resource ที่โหลดไม่ได้เป็นงานของ `lens netlog` ซึ่ง engine นี้ไม่มี |

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

## 6. สถานะความพร้อมใช้งาน

| ใช้ได้แล้ว | ยังไม่พร้อม |
|---|---|
| QA read-only ผ่าน `--engine bsk` บน browser ที่คน login ไว้ (verdict `PASS(inferred)`) | ใช้ตัดสิน release — ชั้นหลักฐานยังเป็น `inferred` (BAS §4.3) |
| งานเปลี่ยนข้อมูลบน **sandbox** ด้วยสคริปต์ที่มีด่าน §3 ครบ | งานเปลี่ยนข้อมูลผ่าน runner — ยังห้าม (`ENGINE_RISK_NOT_ALLOWED`) |
| รันมีคนเฝ้า บน browser ของคนนั้นเอง | รันไม่มีคนเฝ้า / หลายเครื่อง — ต้องมี profile เฉพาะงาน + user ของ automation + CI gate ของ `bsk` |
| | Production ทุกกรณี |
