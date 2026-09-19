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

## 7. สถานะความพร้อมใช้งาน

| ใช้ได้แล้ว | ยังไม่พร้อม |
|---|---|
| QA read-only ผ่าน `--engine bsk` บน browser ที่คน login ไว้ (verdict `PASS(inferred)`) | ใช้ตัดสิน release — ชั้นหลักฐานยังเป็น `inferred` (BAS §4.3) |
| งานเปลี่ยนข้อมูลบน **sandbox** ด้วยสคริปต์ที่มีด่าน §3 ครบ | งานเปลี่ยนข้อมูลผ่าน runner — ยังห้าม (`ENGINE_RISK_NOT_ALLOWED`) |
| รันมีคนเฝ้า บน browser ของคนนั้นเอง — agent 4 ตัวพร้อมกันใน session เดียวทำงานได้ | รันไม่มีคนเฝ้า / หลายเครื่อง — ต้องมี profile เฉพาะงาน + user ของ automation + CI gate ของ `bsk` |
| | O2C ต่อจาก Sales Order บน SB2 — อนุมัติผ่าน suitelet ของ bundle APC ยังไม่ได้ขับ; item ทดสอบมี Available 0 |
| | Production ทุกกรณี |
