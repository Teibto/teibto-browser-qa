# Flow Spec — เขียน test case เป็นไฟล์ reproducible

test-design.md ตัดสิน *จะทดสอบอะไร*. ไฟล์นี้บอก *เก็บ test case ยังไงให้รันซ้ำได้* —
เขียน flow เป็น YAML declarative แทน ad-hoc command ต่อรอบ. ตัวอย่างรันได้จริง:
`examples/saucedemo.yaml`.

## รันแบบ batch (canonical runner)

```powershell
$env:TGT_ID = '<target id จาก cdp.py newtab หรือ tabs>'
$env:TEIBTO_CDP_SCRIPT = 'D:\path\to\teibto-dev-standards\scripts\cdp.py'
'{"username":"qa-user","password":"..."}' |
  py scripts/flow-runner.py --flow examples/saucedemo.yaml --out runs/manual --vars-json - `
    --stdout summary
```

- flow ทุกไฟล์ผ่าน `schemas/flow.schema.json` และ field ที่ไม่รู้จักทำให้หยุดทันที
- secret ส่งผ่าน stdin (`--vars-json -`), ไม่อยู่ใน process argv/log/report
- หนึ่ง run ใช้ target ที่ pin และ `cdp.py` JSONL protocol v3+ เพียง process/WebSocket เดียว;
  runner ขอ `--input-settle=none` และ verify policy จาก ready handshake แบบ fail closed
- `open` รอ main-frame commit/load event จริง; ไม่ใช้ zero-drain + `readyState` ที่อาจอ่านหน้าเก่า
- `click` ใช้ native input เท่านั้น; ไม่มี JS fallback เงียบ
- action/wait/assert/screenshot/console ล้ม = หยุด scenario และ verdict `FAIL`
- dialog ที่ driver ตอบอัตโนมัติทุกรายการถูกบันทึกเป็น event `dialog` ใน run-log และบรรทัด ⚠️ ใน report;
  policy เป็น `safe` เสมอ (ไม่ inherit `DIALOG` จาก shell) เว้นแต่สั่ง `--dialog accept|dismiss`
- action ที่เปลี่ยน state แต่ไม่มี explicit assertion = verdict `UNVERIFIED`, ไม่ใช่ `PASS`
- artifact อยู่ที่ `<out>/run-log.jsonl`, `<out>/qa-report.md`, `<out>/shots/`
- `--stdout summary` ลด output เข้า agent context แต่ `run-log.jsonl` ยังเก็บ event เต็มเหมือนเดิม
- `perf_budget_ms` ระดับ step วัด action → explicit wait → assertion; ไม่รวม startup/capture

Local UI (ไม่จำเป็นต่อ CI):

```powershell
$env:TGT_ID = '<target id>'       # หรือกรอกในหน้า Run
node app/server.js                # bind 127.0.0.1:4173 เท่านั้นโดย default
```

UI ส่ง secret เข้า runner ผ่าน stdin และมี cancellation endpoint; ไม่มี daemon/dashboard/video/ffmpeg.

**ทำไมต้องเป็นไฟล์:** 1 flow file = 1 repro ถาวร (กติกา "1 bug = 1 repro"), diff ได้, รันซ้ำ
regression ได้, เติม vars ต่างค่าเพื่อยิง edge case ได้โดยไม่แก้ logic.

---

## Schema

ไฟล์ authoritative คือ `schemas/flow.schema.json`; ตัวอย่างด้านล่างเป็น quick reference เท่านั้น

```yaml
story: <slug>                    # id สั้นๆ ของ flow (ใช้ตั้งชื่อโฟลเดอร์ artifact)
title: <ชื่ออ่านเข้าใจ>          # ขึ้นหัว guide/report
ticket: <PROJ-123>               # (team) link กลับ requirement/ticket — ไหลเข้า qa-report + guide

vars:                            # ค่าที่ inject ผ่าน {{name}} — UI render เป็นช่องกรอก
  - { name: base_url, label: URL, default: "https://..." }
  - { name: password, label: Password, default: "x", secret: true }   # secret → input password

scenarios:
  - id: <scenario-id>
    doc: true                    # true = ใช้ scenario นี้ generate user-guide ด้วย
    requirement: <PROJ-123>      # (team) requirement ที่ scenario นี้ยืนยัน (override story.ticket)
    acceptance: >               # (team) Acceptance Criteria — Given/When/Then ที่ steps ต้องพิสูจน์
      Given ผู้ใช้ login แล้ว When กด Checkout Then ไปหน้า step-one
    steps:
      - intent: "<คำอธิบายคน — ขึ้นเป็น step ใน guide>"
        action: open|fill|click|select|press|scrollintoview|eval|wait
        target: "<selector | @eN | {{var}} | url>"
        value: "<ค่า/ข้อความ (สำหรับ fill/select) — รองรับ {{var}}>"
        wait: networkidle | <ms> | "<selector>" | "fn:<js>"  # รอหลัง action
        perf_budget_ms: 3000       # optional; เกินแล้ว PERF_BUDGET_EXCEEDED + FAIL
        capture: true|false        # override screenshot policy ของ scenario นี้
        assert:                  # พิสูจน์ผล (ตาม gotchas: อย่าเชื่อ ✓Done)
          url_contains: "/inventory.html"
          # หรือ: { target: ".shopping_cart_badge", contains: "1" }
```

**assert forms ที่ใช้บ่อย:** `url_contains: "..."` · `{ target: "<sel>", contains: "<text>" }`.
ทุก step ที่เปลี่ยน application state **ต้องมี assert** — runner คืน `UNVERIFIED` ถ้าไม่มี
(การ `fill` ตรวจ value หลังกรอกให้อัตโนมัติ แต่ action ที่ submit/เปลี่ยนข้อมูลยังต้อง assert ผลธุรกิจ).

`networkidle` เป็นชื่อเดิมเพื่อ compatibility แต่ contract จริงคือ **navigation-ready** ไม่ใช่
เครือข่ายนิ่ง: `open` ใช้ event ของ main frame; หลัง action อื่น runner ปัก document identity ก่อนทำ
action แล้วรอ URL/time origin เปลี่ยนพร้อม `readyState=complete`, จึงไม่ผ่านจากหน้าเก่า. งาน AJAX/
Oracle JET ให้ใช้ selector หรือ `fn:<observable outcome>` เช่น
`fn:document.querySelector('#status').textContent==='saved'` แล้ว assert ครั้งเดียว.

Dialog: cdp.py protocol v3 แนบ `dialogs: [{type,message,answer}]` ใน result ของ command ที่ตอบ dialog
และพิมพ์ `[dialog] <kind>: <message> -> accept|dismiss` ลง stderr ทันที. Runner ใช้ structured result
เป็น authority (stderr ใช้ diagnosis เท่านั้น จึงไม่เกิด event ซ้ำ/race) แล้วแปลงเป็น event
`{"type":"dialog","scenario","index","global_index","kind","message","answer","line"}`,
นับรวมใน `run_done.dialogs` และสรุปใน report เป็น
`**Auto-answered dialogs:** <n> (policy: <policy>)`. `run_start.driver_policy.dialog` บอก policy ที่ใช้จริง;
`run_start.driver_policy.dialog_evidence` เป็น `structured-per-command`;
default `safe` (alert = accept, อย่างอื่น = dismiss) และเปลี่ยนได้เฉพาะ `--dialog` ของ runner —
QA run ไม่ inherit `DIALOG` จาก shell ตาม SKILL.md invariant 5. ทุก dialog จึงผูกกับ step/command
ที่ทำให้เกิดได้โดยตรง; payload ที่ shape ผิดทำให้ `INVALID_SESSION_OUTPUT` แทนการทิ้ง evidence เงียบ ๆ.

`run-log.jsonl` เก็บ runner wall-clock และ authoritative driver `duration_ms`/`attempts` แยก
`action`, `wait`, `assert`, `capture`; failure มี partial phases + `failing_phase`, console check มี
timing ของตัวเอง และ `run_done` แยก startup/total. `session_ready.cdp_script` และข้อความ
`DRIVER_INCOMPATIBLE`/`CDP_NOT_READY` ระบุ path ของ `cdp.py` ที่ runner resolve ได้จริง เพื่อให้รู้ว่า
ต้องอัปเดตสำเนาไหนเมื่อเครื่องมี driver หลายชุด.

เมื่อ step มี `perf_budget_ms`, `step_done.performance.outcome_ms` วัดตั้งแต่ก่อน action ถึงหลัง
explicit wait/assert โดยไม่รวม screenshot; `run_done.performance_budgets` สรุป pass/evaluated/total.
เกิน budget = typed failure `PERF_BUDGET_EXCEEDED` และเก็บ failure evidence ตาม capture policy.

**Traceability (สำหรับทีม):** `ticket`/`requirement` + `acceptance` ทำให้ตอบได้ว่า *test นี้ยืนยัน
req ไหน* และ *req นี้ครอบด้วย scenario ไหน*. 1 acceptance criterion → 1 scenario (map 1:1) →
qa-report + user-guide อ้าง req เดียวกัน = ปิด loop req→test→doc. ดู playbook ทีมใน repo:
`docs/TEAM-PROCESS.md`.

---

## สิ่งที่ไม่ใช่ executable flow field

Runner ปัจจุบันไม่รองรับ `fixtures`, `teardown`, `retry_on`, `quarantine`, `a11y`, `perf_budget`,
`mask_regions`, `diff_threshold` หรือ `ci_candidate`; fail-closed schema ปฏิเสธทั้งหมดแทนการรับแล้ว
ignore เงียบ ๆ.

`perf_budget` แบบ object/scenario เดิมยังถูกปฏิเสธ; executable contract คือ integer
`perf_budget_ms` ที่ step เท่านั้น.

- เก็บ release/quarantine/coverage state ใน `qa/<feature>/coverage.yaml`.
- ทำ setup/teardown เป็น orchestration แยก โดยใช้ scoped marker, identify-before-mutate และ dirty-state
  reporting ตาม [`test-design.md`](test-design.md) §Stateful test isolation.
- รัน a11y/perf/visual recipes แยกหลัง flow ถึง state ที่ต้องการ แล้วแนบผลเข้ารายงาน.

การเพิ่ม field ต้องส่ง schema, execution behavior, report behavior และ failure test ใน PR เดียวกัน.

---

## Design → Spec → Run → Report (pipeline เต็ม)

0. **Requirement** — แต่ละ requirement/ticket → เขียน **Acceptance Criteria** (Given/When/Then).
1. **Design** (`test-design.md`) — จาก AC + อ่าน code → coverage matrix → list case (happy + adversarial).
   AC จับ "ฟีเจอร์ที่ควรมีแต่ไม่มี" (code-based test จับไม่ได้); code จับ branch/edge ที่ AC ไม่ครอบ.
2. **Spec** — แปลงแต่ละ case เป็น scenario ใน `qa/<feature>/flow.yaml` (ใส่ `requirement`+`acceptance`).
   - happy path: `doc: true` (ใช้ทำ guide).
   - adversarial: scenario แยก `doc: false` — ยิง edge value ผ่าน `vars` (ไทย/emoji/boundary/
     injection payload) แล้ว assert ว่า error **surface** (ไม่ใช่ Pass เงียบ).
3. **Run** — ขับด้วย `scripts/flow-runner.py` ผ่าน JSONL session เดียว คืน `run-log.jsonl`.
   screenshot ทุก step เฉพาะ scenario `doc:true`; adversarial `doc:false` ไม่ถ่ายตอนผ่านแต่ถ่าย
   failure เป็นหลักฐาน. `capture:true|false` ที่ step override ทั้งสองกรณีได้.
4. **Report** — `qa-report.md` (ตาราง Phase 3) + ป้อน bug เข้า `assets/bug-report-template.html`,
   guide จาก scenario `doc:true` เข้า `assets/guide-template.html`.

โครง artifact:
```
qa/<feature>/
  flow.yaml            # test case ทั้งหมด (happy + adversarial scenarios)
  run-log.jsonl        # event/result ที่ตรวจ correlation และลำดับย้อนหลังได้
  shots/               # screenshot (artifact ไม่เข้า context)
  qa-report.md         # verdict + ตาราง case + severity
  guide/               # user-guide / bug-report ที่ generate
```

ตัวอย่างจริงพร้อมรัน: `examples/saucedemo.yaml` (login→cart→checkout happy path `doc:true` +
adversarial `doc:false`, มี requirement/acceptance + assert ครบ).
