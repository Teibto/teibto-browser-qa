# Reliability policy — retry ยังไงไม่ให้ทำลาย adversarial mindset

หลักของ skill นี้คือ **หา bug ไม่ใช่ mark Pass** (test-design.md). "retry จนเขียว" คือศัตรูตัวฉกาจ:
มันซ่อน bug จริงไว้ใต้ความ flaky. ไฟล์นี้แยกให้ชัดว่า **อะไร retry ได้ (infra) vs ห้าม retry เด็ดขาด
(assertion)** และจัดการ scenario ที่ flaky จน block คนอื่นด้วย **quarantine** โดยไม่ทำ gate เขียวหลอก.

---

## 1. Retry ได้เฉพาะ infra error (ไม่ใช่ผล assertion)

infra error = ปัญหา "ต่อ browser/daemon ไม่ติด" ไม่เกี่ยวกับ correctness ของแอป. retry ได้
**max 2 ครั้ง + backoff** (เช่น 2s, 5s). enumerate ให้ชัด — retry เฉพาะรายการนี้:

| Infra error | อาการ | อ้างอิง |
|---|---|---|
| `os error 10060` | connection attempt failed บน long-poll wait / หลัง kill daemon | gotchas.md §3 |
| daemon stall / session ค้าง | ทุกคำสั่ง timeout, `.pid`/`.port` ชี้ daemon ตาย | gotchas.md §3 |
| cold-start timeout | `open` ค้างแม้หน้าโหลดแล้ว (Windows) | gotchas.md, runner cold-start |
| CDP disconnect | browser หลุด CDP กลาง flow | — |

**ก่อน retry ต้อง reset สาเหตุ** ไม่ใช่ยิงซ้ำเฉยๆ: เช่น 10060 ที่ค้าง → ลบ session file
แล้วค่อยสั่งใหม่. retry ที่ไม่ reset สาเหตุ = วน fail เปล่า.

---

## 2. Assertion fail → ห้าม retry เด็ดขาด

`assert` ที่ fail (url ไม่ตรง, badge ไม่ขึ้น, error ไม่ surface, text ไม่ตรง) = **ผลจริงของแอป**
ไม่ใช่ infra. retry assertion = **ซ่อน bug** = ผิดกฎ no-silent-fallback โดยตรง.

- assertion fail → บันทึกเป็น **FAIL ทันที** พร้อม repro (test-design.md Phase 3).
- ถ้าสงสัยว่า fail เพราะ timing (อ่านเร็วเกิน ยังไม่ render) → นั่นคือ **การ wait ที่ผิด** ไม่ใช่เหตุ
  retry: แก้ด้วย `wait <selector ผลลัพธ์>` / `wait --load networkidle` ก่อน assert (gotchas.md §2)
  แล้ว assert **ครั้งเดียว**. อย่าเปลี่ยน "รอให้ถูก" เป็น "ยิงซ้ำจนบังเอิญผ่าน".

เส้นแบ่ง: **ต่อ browser ไม่ติด = retry ได้. แอปให้ผลผิด = FAIL.** ถ้าแยกไม่ออก ให้ถือเป็น FAIL.

---

## 3. Quarantine — กัน flaky ตัวเดียว block ทั้งทีม โดยไม่โกง gate

scenario ที่ flaky จริง (ไม่ใช่ bug แต่ยังหาเหตุไม่จบ) และ block คนอื่น → ตั้ง `quarantine: true`:

- scenario **ยังรันอยู่** (ไม่ลบทิ้ง — จะได้เห็นว่ามันกลับมาเขียวเองไหม) แต่ **ไม่นับเข้า release gate**.
- log ทุกครั้งที่ `qa/<feature>/quarantine-log.md`:
  ```
  | scenario | เหตุผล flaky | วันที่ (YYYY-MM-DD) | เจ้าของ | ticket |
  |---|---|---|---|---|
  | SC-014 | 10060 สุ่มขึ้นช่วง checkout ~1/5 รอบ | 2026-07-09 | wichit | PROJ-88 |
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

## 4. Schema ใน flow.yaml (retry_on / quarantine)

optional มี default (backward-compatible):
```yaml
scenarios:
  - id: SC-001
    retry_on: [infra]        # default: [] — [] = ไม่ retry อะไรเลย. ใส่ได้เฉพาะ infra
    quarantine: false        # default: false
```
`retry_on` รับได้แค่ `infra` (จาก §1). **`assertion` ไม่เคยเป็นค่าที่ใส่ได้** — โดยตั้งใจ (§2).

---

## Cross-links
- อาการ infra จริง + วิธี reset: [`gotchas.md`](gotchas.md) §3 (os 10060 / session ค้าง), §8 (record/daemon PATH).
- เส้นแบ่ง Pass/Fail + mindset: [`test-design.md`](test-design.md).
- gate + quarantine ในตัวเลข: [`coverage-model.md`](coverage-model.md).
