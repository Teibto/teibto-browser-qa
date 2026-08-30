# Reliability policy — retry ยังไงไม่ให้ทำลาย adversarial mindset

หลักของ skill นี้คือ **หา bug ไม่ใช่ mark Pass** (test-design.md). "retry จนเขียว" คือศัตรูตัวฉกาจ:
มันซ่อน bug จริงไว้ใต้ความ flaky. ไฟล์นี้แยกให้ชัดว่า **อะไร retry ได้ (infra) vs ห้าม retry เด็ดขาด
(assertion)** และจัดการ scenario ที่ flaky จน block คนอื่นด้วย **quarantine** โดยไม่ทำ gate เขียวหลอก.

---

## 1. Retry ได้เฉพาะ infra error (ไม่ใช่ผล assertion)

infra error = ปัญหา transport/CDP หลุด ไม่เกี่ยวกับ correctness ของแอป. retry ได้
**max 2 ครั้ง + backoff** (เช่น 2s, 5s). enumerate ให้ชัด — retry เฉพาะรายการนี้:

| Infra error | อาการ | อ้างอิง |
|---|---|---|
| `PORT_UNREACHABLE` | Chrome/CDP port ไม่ตอบก่อนเริ่ม session | `cdp.py doctor` |
| `WS_DISCONNECTED` / `WS_ERROR` | WebSocket หลุดกลาง flow | cdp.py session protocol |
| `CONTEXT_DESTROYED` | navigation ทำให้ execution context เปลี่ยน | retry 1 ครั้งเฉพาะ safe read ใน cdp.py |

`DRIVER_INCOMPATIBLE` และ `TARGET_BACKGROUND` ก่อนเริ่ม flow ไม่ใช่เหตุให้ยิง scenario ซ้ำจนผ่าน:
อัปเดต canonical driver หรือแก้ Chrome/target ownership แล้วเริ่ม run ใหม่. ห้ามลด contract หรือใช้
run ที่ hidden เป็น performance evidence.

`flow-runner.py` ไม่ replay action เอง: transport error ทำให้ run ปัจจุบัน FAIL และปิด bounded child
process. การ retry ทั้ง scenario ต้องเป็นการตัดสินใจของ orchestration ภายนอกหลังตรวจสาเหตุแล้ว
เท่านั้น เพื่อไม่กด action ที่เปลี่ยน state ซ้ำโดยไม่รู้ตัว

---

## 2. Assertion fail → ห้าม retry เด็ดขาด

`assert` ที่ fail (url ไม่ตรง, badge ไม่ขึ้น, error ไม่ surface, text ไม่ตรง) = **ผลจริงของแอป**
ไม่ใช่ infra. retry assertion = **ซ่อน bug** = ผิดกฎ no-silent-fallback โดยตรง.

- assertion fail → บันทึกเป็น **FAIL ทันที** พร้อม repro (test-design.md Phase 3).
- ถ้าสงสัยว่า fail เพราะ timing (อ่านเร็วเกิน ยังไม่ render) → นั่นคือ **การ wait ที่ผิด** ไม่ใช่เหตุ
  retry: แก้ด้วย `wait "<เงื่อนไขผลลัพธ์>"` ก่อน assert (gotchas.md §2)
  แล้ว assert **ครั้งเดียว**. อย่าเปลี่ยน "รอให้ถูก" เป็น "ยิงซ้ำจนบังเอิญผ่าน".

Runner protocol v3 ตัด fixed input settle เฉพาะ `click`/`fill`/`press` ที่ runner ส่งตรง. `fill`
จึง poll ค่า exact แบบ bounded หลัง action; click/press ต้องมี `wait` ของ observable outcome ก่อน
assert. เวลาของแอปยังอยู่ใน action/wait timing ไม่ได้ถูกลบออก. `networkidle` ใช้เฉพาะ navigation-ready;
AJAX/component state ใช้ selector หรือ `fn:<js>` ที่เจาะจง.

เส้นแบ่ง: **ต่อ browser ไม่ติด = retry ได้. แอปให้ผลผิด = FAIL.** ถ้าแยกไม่ออก ให้ถือเป็น FAIL.

---

## 3. Quarantine — กัน flaky ตัวเดียว block ทั้งทีม โดยไม่โกง gate

scenario ที่ flaky จริง (ไม่ใช่ bug แต่ยังหาเหตุไม่จบ) และ block คนอื่น → ตั้ง `quarantine: true`:

- scenario **ยังรันอยู่** (ไม่ลบทิ้ง — จะได้เห็นว่ามันกลับมาเขียวเองไหม) แต่ **ไม่นับเข้า release gate**.
- log ทุกครั้งที่ `qa/<feature>/quarantine-log.md`:
  ```
  | scenario | เหตุผล flaky | วันที่ (YYYY-MM-DD) | เจ้าของ | ticket |
  |---|---|---|---|---|
  | SC-014 | WS_DISCONNECTED ระหว่าง checkout 1/5 รอบ | 2026-08-22 | owner | PROJ-88 |
  ```
- quarantine เป็น **หนี้ที่มองเห็น** ไม่ใช่ที่ซ่อน bug — ต้องมีเจ้าของ + ticket + วันที่ เพื่อทวงคืน.

### coverage-check.py ปฏิบัติต่อ quarantine ยังไง
`scripts/coverage-check.py` (ดู coverage-model.md) treat AC ที่ผูก scenario quarantine ว่า
**"ไม่ pass, มองเห็นได้"**: ตั้ง `quarantine: true` ที่แถว AC ใน coverage.yaml →
- Status = `QUARANTINE`, **นับเป็น blocking** (ไม่ทำ gate เขียว), exit 1.
- แสดงในตารางชัด ไม่ถูกกลืนเป็น pass.

→ quarantine จึง **ไม่มีทางทำให้ gate เขียว** — แค่ปลด scenario ออกจากการ block *การรัน* ของคนอื่น
แต่ release ยังติดจนกว่าจะแก้จริง.

---

## 4. Retry/quarantine ไม่ใช่ field ของ executable flow

Canonical runner ไม่ retry action และ schema ปฏิเสธ `retry_on`/`quarantine` เพื่อไม่ให้ config ที่ดู
เหมือนทำงานถูก ignore เงียบ ๆ. ถ้าต้อง quarantine ให้บันทึกใน coverage manifest ตาม §3; orchestration
ภายนอกที่ retry ทั้ง scenario ต้องแยก transport error จาก assertion และเก็บ retry เป็น run ใหม่เสมอ

---

## Cross-links
- อาการ infra จริง + diagnosis: `py cdp.py doctor`; bounded transport contract ดู
  [`flow-spec.md`](flow-spec.md) และ `Teibto/teibto-dev-standards` `docs/TOOLSTACK.md`.
- เส้นแบ่ง Pass/Fail + mindset: [`test-design.md`](test-design.md).
- gate + quarantine ในตัวเลข: [`coverage-model.md`](coverage-model.md).
