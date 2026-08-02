# Test Design — จะทดสอบอะไร (adversarial coverage)

`gotchas.md` + `commands.md` บอก **วิธีขับ browser**. ไฟล์นี้บอก **จะทดสอบอะไร** — วิธีคิด
test case เชิงระบบเพื่อ "แตกระบบให้พังก่อน user เจอ" ไม่ใช่แค่ยืนยันว่า happy path เดินจบ.

**Mindset:** adversarial — เป้าหมายคือหา bug ไม่ใช่ mark Pass. ห้าม mark Pass ถ้าไม่ได้ run จริง;
ถ้าไม่ได้ทดสอบให้เขียน "ไม่ได้ทดสอบ".

---

## กฎข้อเดียวที่ทำให้ merge นี้ไม่ขัดกันเอง

skill นี้มีหลัก **"one pass, token น้อย"**. adversarial coverage ดูเหมือนขัด (หลายรอบ + output เยอะ)
แต่ไม่ขัดถ้าแยกให้ชัด:

| ชั้น | เป็นอะไร | ต้นทุน |
|---|---|---|
| **Test design** (Phase 0–2 ล่าง) | **สมองคิดจาก code** — ตัดสินว่าจะยิง case ไหน | ถูก ไม่แตะ browser เลย |
| **Test execution** | ขับ browser ยิง case ที่ design ไว้ | **ยัง token discipline เดิม** — คำสั่งสั้น, screenshot=ไฟล์, ห้าม dump snapshot |

**"one pass, two outputs" นิยามใหม่:**
- **Happy-path pass** = เดินรอบเดียว → ได้ guide material + smoke verdict (หลักเดิม ยังอยู่).
- **Adversarial passes** = pass **แยก** ยิงทีละ case → คืน **เฉพาะ bug finding** (ไม่ผลิต guide,
  ไม่ screenshot ทุก step — ถ่ายเฉพาะตอนเจอ bug เป็นหลักฐาน).

design matrix แค่บอกว่า *จะรัน short-assertion check ตัวไหน* — มันไม่เคยอนุญาตให้ feed snapshot กลับ context.

---

## สิ่งที่รันผ่าน browser ได้จริง vs ไม่ได้ (สำคัญ — กัน false confidence)

prompt ทั่วไปครอบคลุมทุก edge case แต่ **CDP-driven browser เดียวทำได้ไม่หมด**. แยกให้ชัดในรายงาน
ไม่งั้นจะให้ความมั่นใจหลอกๆ (ตรงข้ามกับที่ gotchas สู้มาทั้งไฟล์):

**✅ ยิงผ่าน browser ได้ (execute + assert):**
- Boundary / Empty-Null / Type-Format ที่เป็น **input ในฟอร์ม** (0/-1/max, empty, ผิด type, วันที่ format ผิด)
- **Unicode / ภาษาไทย / emoji** ใน field, injection payload (SQL/`<script>`) ที่ยิงเป็น input
- Double-submit, กด action ผิดลำดับ, ทำซ้ำ (idempotency ที่เห็นผลบน UI)
- Auth / session (logout กลางคัน, session หมด, url ข้าม scope)
- **Error surfacing** — หลังทุก step: `errors --json` + `console --json` ต้องโผล่ ไม่เงียบ

**⚠️ derive จาก code ได้ แต่ browser พิสูจน์ไม่ได้ → mark เป็น "risk / needs code review หรือ backend test":**
- True cross-user concurrency / race / lock (ต้องหลาย session พร้อมกัน + timing จริง)
- Governance / usage-unit limit, script yield, timeout ระดับ platform
- SuiteQL internals (null ใน join, cursor boundary, Oracle syntax edge)
- Transaction rollback / partial save / orphan record (ดูจาก DB ไม่ใช่ UI)
- Cross-subsidiary scope, elimination, running-number sequence gap ระดับ backend

กฎ: อะไรที่ browser พิสูจน์ไม่ได้ → เขียนว่า "derived from code, unverified in browser" อย่า mark Pass.

---

## Phase 0 — เข้าใจระบบก่อน (สมองล้วน ไม่แตะ browser)

ก่อนเขียน test แม้แต่ case เดียว:
1. อ่าน code ที่เกี่ยวข้อง — entry points, modules, data model, dependencies.
2. สร้าง **System Map**: feature/function ทั้งหมด + inputs, outputs, side effects, external calls.
3. ระบุ **business rules & invariants** ที่ต้องรักษาเสมอ (เช่น "ยอดต้องไม่ติดลบ", "running number unique").
4. behavior ไหนไม่ชัด → **ถามก่อน ห้ามเดา**.

**Output:** ตาราง feature/function + สมมติฐานที่ตั้งไว้. (ยังไม่เปิด browser — นี่คือ token ถูกที่สุด)

---

## Phase 1 — Supported cases (ทุก branch ต้องโดน)

**Coverage Matrix** จาก code จริง (ไม่ใช่จาก comment/ชื่อ function):
- ทุก entry point / function / endpoint
- ทุก branch — `if/else`, `switch`, guard clause ครบ
- ทุก mode / state (CREATE / EDIT / VIEW · draft / approved / cancelled)
- ทุก role / permission level
- ทุก combination ของ input ที่ valid

แต่ละแถวของ matrix = 1 flow ที่ต้องขับ + short-assertion ที่พิสูจน์ผล.

---

## Phase 2 — Edge cases & bug hunting

ต่อแต่ละ input/field/operation ยิงทุกหมวด (ทำเครื่องหมาย ✅/⚠️ ตามตารางด้านบน):
- **Boundary** — 0, 1, -1, max, min, overflow, ทศนิยม precision/rounding
- **Empty / Null** — null, undefined, empty string, whitespace-only, empty array/object, field หาย
- **Type & Format** — ผิด type, string ที่ควรเป็น number, วันที่ format ผิด, timezone, special char,
  **Unicode/ไทย**, emoji, injection (SQL/script)
- **Uniqueness / Duplicate** — ค่าซ้ำ, running number ชน, concurrent create ค่าเดียวกัน ⚠️
- **Concurrency / Race** ⚠️ — หลาย user แก้ record เดียวกัน, lock, double-submit (✅ เฉพาะ double-submit)
  - **เทคนิคอัปเกรด mid-flight race เป็น ✅ (deterministic, ไม่ต้องจับจังหวะมือ):** ใช้ `eval`
    monkey-patch ฟังก์ชัน fetch-wrapper ของแอป (เช่น `postToSuitelet`) ในหน้าเว็บ — await ตัวจริงเสร็จ
    แล้ว **inject mutation ตรงรอยต่อระหว่าง backend call** (เช่น แก้ cell ระหว่าง create 2 step)
    ก่อน return; เก็บ log ใน `window.__raceLog` แล้ว assert ผลที่ record ฝั่ง server.
    พิสูจน์จริง: PWOC stale-qty race (#39) — repro + verify fix ได้ 100% ใน browser
- **Volume / Performance** — dataset ใหญ่, pagination boundary, timeout, governance ⚠️
- **State & Sequence** — operation ผิดลำดับ, ทำซ้ำ (idempotency), interrupt กลางคัน, partial failure+rollback ⚠️
- **Auth / Permission** — ไม่มีสิทธิ์, session หมด, ข้าม scope
- **Error handling** — error ต้อง surface ชัด ห้าม silent fallback/swallow; ตรวจว่า log + propagate จริง

### Security checklist (รวมจุดเดียว)

ยิงทุกครั้งที่แตะ input, auth, หรือ logging — 3 หมวดนี้เป็น security ที่ browser ยิงได้บางส่วน (✅) และ
บางส่วน ⚠️ ต้อง code review:

- **Injection (✅ input)** — ยิง SQL / `<script>` / template / command payload เป็นค่าใน field แล้ว
  assert ว่า **ถูก escape/reject** ไม่ execute และไม่สะท้อนกลับดิบ (stored + reflected XSS). ไทย/Unicode
  ใน 4 payload ด้วย.
- **Auth / authz cross-scope (✅ ผ่าน URL/session)** — เข้าถึงโดยไม่มีสิทธิ์, session หมดกลางคัน,
  **แก้ URL ข้าม scope** (record/subsidiary/tenant ของคนอื่น) → ต้องถูกปฏิเสธ ไม่ใช่หลุด. true
  concurrency/lock ยังเป็น ⚠️ (code/backend).
- **Sensitive data in logs (⚠️ code + ✅ console)** — password / token / PII **ต้องไม่โผล่** ใน
  `console --json`, network response ที่เห็นได้, หรือ error message. ตรวจ `console`/`errors` ว่าไม่มี
  ความลับรั่ว; log ฝั่ง server = code review.

กติกาเดิมยังใช้: อะไรที่ browser พิสูจน์ไม่ได้ → "derived from code, unverified in browser" อย่า mark Pass.

---

## Phase 3 — รายงานผล

ทุก case ลงตาราง:

| # | Case | Input | Expected | Actual | Pass/Fail | Severity | Repro |
|---|------|-------|----------|--------|-----------|----------|-------|

จากนั้น:
- แยก **bug จริง** เป็น list เรียงตาม severity (Critical / High / Medium / Low).
- ระบุ **root cause** ถ้าวิเคราะห์ได้ + แนวทางแก้ → ป้อนเข้า `assets/bug-report-template.html`.
- **1 bug = 1 repro ที่ทำซ้ำได้เสมอ.** ห้าม Pass ถ้าไม่ได้ trace/run จริง.

---

## Add-on: NetSuite-specific edge cases

(ผนวกท้าย Phase 2 เมื่อทดสอบ NetSuite — ส่วนใหญ่ ⚠️ derive จาก code, browser พิสูจน์บางส่วน)
- **Governance** ⚠️ — usage units เกิน limit, yield boundary, unmetered vs metered
- **Realtime path** — Ship/Outbound critical path ต้อง realtime: ตรวจ (จาก code) ว่าไม่มี async /
  Map-Reduce / Scheduled Script แทรก
- **Cross-subsidiary** ⚠️ — item/entity ข้าม subsidiary scope, elimination
- **Lot / Serial** — uniqueness, FEFO/FIFO allocation, negative inventory, over-allocation (✅ ถ้าเห็นบน UI)
- **Running number** ⚠️ — concurrent generation ชน, sequence gap, prefix collision
- **Date** — internal `YYYY-MM-DD` vs display, user timezone, cross-midnight (✅ ยิง input ได้)
- **Sublist** — commit/insert/remove order, dynamic vs standard mode, line index shift (✅ ผ่าน UI)
- **SuiteQL** ⚠️ — null ใน join, cursor boundary, Oracle syntax edge, large result set
- **Transaction rollback** ⚠️ — fail กลางคัน state ค้าง, partial save, orphan record

APEX: IG cell/button dynamic → semantic locator (`find label ... fill` / `find role button click --name`);
ทดสอบ Thai input ทุกครั้ง; boundary/format ยิงผ่าน form ได้.
