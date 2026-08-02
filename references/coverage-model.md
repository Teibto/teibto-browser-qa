# Coverage model — release gate ที่ "คำนวณได้" ไม่ใช่ assert ด้วยมือ

`docs/TEAM-PROCESS.md` เขียน release gate ไว้เป็น prose (4 ข้อ) — คนต้องอ่านแล้วตัดสินเอง.
ไฟล์นี้อธิบาย **coverage manifest** (`coverage.yaml`) + สคริปต์ `scripts/coverage-check.py`
ที่แปลง gate นั้นเป็น **exit code** เดียว: 0 = ผ่าน, 1 = ยังไม่ผ่าน, 2 = manifest พัง.

The gate becomes a number, not a judgement call: one manifest per feature, one script, one exit code.

---

## ทำไมต้องมี manifest แยกจาก flow.yaml

- `flow.yaml` ตอบว่า *scenario ทำอะไร* (steps + assert). มัน execution-centric.
- `coverage.yaml` ตอบว่า *requirement ทุกข้อถูกพิสูจน์แล้วหรือยัง* — requirement-centric.
- แยกกันเพราะ 1 AC อาจ map ไป scenario เดียว และ AC ที่ยัง **ไม่มี scenario** ต้องนับเป็น
  `not_tested` ให้เห็น (code-based test design จับ "ฟีเจอร์ที่ควรมีแต่ไม่มี" ไม่ได้ — AC จับได้).

> flow.yaml ยังใช้ `story:` เหมือนเดิม (ไม่เปลี่ยน). `feature:` เป็น key ของ coverage.yaml เท่านั้น
> — คนละไฟล์ ไม่ชนกัน (additive, backward-compatible).

---

## Schema (`qa/_template/coverage.yaml`)

```yaml
feature: <name>                  # ชื่อ feature (label; flow.yaml ยังใช้ story:)
updated: YYYY-MM-DD
acceptance_criteria:
  - id: AC-001
    requirement: <ticket id>      # ticket ต้นทางของ AC (traceability)
    description: <short>
    flow_scenario: SC-001         # scenario ที่พิสูจน์; null => not_tested
    verifiable: browser           # browser | code-only
    result: not_tested            # pass | fail | not_tested | blocked
    severity: null                # critical|high|medium|low — required เมื่อ result=fail
    quarantine: false             # true => flaky, ไม่นับ pass, ติดธง (ดู Phase 3)
    last_run: null                # YYYY-MM-DD
    evidence: null                # path screenshot / anchor ใน qa-report.md
```

**Field เขียนมือ:** `verifiable` ระบุเองต่อ AC (browser = พิสูจน์ผ่าน browser ได้ /
code-only = ต้อง Dev unit/integration test — ดู ✅/⚠️ ใน `test-design.md`). manifest ไม่ auto-derive
จาก flow.yaml เพื่อไม่ให้ต้องแก้ schema flow เดิม.

---

## Gate logic (`coverage-check.py`)

```
python scripts/coverage-check.py qa/<feature>/coverage.yaml
```

พิมพ์ตาราง `AC · Scenario · Verifiable · Result · Severity · Status` แล้วปิดท้าย `GATE: PASS|FAIL`.

**สถานะต่อ AC** (คอลัมน์ Status):

| Status | เงื่อนไข | นับเป็น |
|---|---|---|
| `PASS` | มี flow_scenario + result=pass + ไม่ quarantine | ผ่าน |
| `NOT_TESTED` | result=not_tested **หรือ** ไม่มี flow_scenario (แม้เขียน result=pass ก็ downgrade) | **block** |
| `BLOCKED` | result=blocked | **block** |
| `FAIL(critical\|high)` | result=fail + severity critical/high | **block** |
| `FAIL(medium\|low)` | result=fail + severity medium/low | **warn** (ship ได้ถ้ามี ticket) |
| `QUARANTINE` | quarantine=true | **block** (ไม่นับ pass, เห็นชัด) |

**Exit code:**
- **0** — ไม่มี AC ที่ block เลย → `GATE: PASS`. (warn medium/low ไม่ block แต่ต้องมี tracked ticket
  ตาม TEAM-PROCESS — บังคับด้วยคน ไม่ใช่สคริปต์)
- **1** — มี AC block ≥ 1 (not_tested / blocked / fail critical|high / quarantine / ไม่มี scenario)
  → `GATE: FAIL`
- **2** — manifest พัง: parse ไม่ได้, ไม่มี `acceptance_criteria`, `result`/`severity`/`verifiable`
  ค่าไม่ถูก enum, result=fail แต่ไม่มี severity, **flow_scenario ชี้ id ที่ไม่มีใน flow.yaml**
  (ดู linkage ด้านล่าง), หรือ **PyYAML ไม่ได้ติดตั้ง** → พิมพ์ error ทาง stderr, exit 2
  (no silent fallback — ไม่ default เงียบ).

### Linkage check (structural — Q1 ตอบ (c))
`coverage-check.py` เช็คว่า `flow_scenario` ทุกตัว (ที่ไม่ null) **มีอยู่จริง**ใน `flow.yaml`
ข้างๆ (`qa/<feature>/flow.yaml`, sibling เดียวกัน) — จับ manifest ที่หลุด sync กับ scenario ที่ถูก
rename/ลบ. เป็น structural check เท่านั้น (ยัง**ไม่**อ่านผลการรันจาก run-log — `result` ยังเชื่อคนกรอก):
- flow_scenario ชี้ id ที่ **ไม่มี**ใน flow.yaml → **exit 2** (manifest inconsistent, ต้องแก้).
- **ไม่มี flow.yaml** ข้างๆ (เช่น template) หรือ flow.yaml ใช้ไม่ได้ → **warn ไป stderr แล้วข้าม**
  (linkage เป็น additive, ไม่ทำ manifest เดิมพัง). มี flow.yaml เมื่อไหร่ → บังคับเข้มทันที.

> การ downgrade "ไม่มี flow_scenario → not_tested" คือหัวใจ: กันการ mark pass ทั้งที่ยังไม่มี
> scenario รันจริง (สอดคล้อง test-design.md: ห้าม Pass ถ้าไม่ได้ run).

**ทำไม medium/low ไม่ block:** `docs/TEAM-PROCESS.md` ระบุ "Medium and Low may ship with a tracked
ticket". สคริปต์จึงติดธง warn แต่ไม่ block — การตัดสินใจ ship อยู่ที่คน (QA Lead) พร้อม ticket.

---

## workflow ใช้จริง

1. ตอน Design: ทุก AC (Given/When/Then) → 1 แถวใน `qa/<feature>/coverage.yaml`, ตั้ง `result: not_tested`.
2. เขียน scenario ใน `flow.yaml` → ใส่ id กลับใน `flow_scenario`.
3. หลังรัน: อัปเดต `result` + `severity` (ถ้า fail) + `last_run` + `evidence`.
4. Release gate: `python scripts/coverage-check.py qa/<feature>/coverage.yaml` → exit ต้อง = 0.
   ผูกเข้า checklist/CI ได้เพราะเป็น exit code จริง.
