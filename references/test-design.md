# Test Design — จะทดสอบอะไร

`commands.md` และ `gotchas.md` บอกวิธีขับ browser; ไฟล์นี้ใช้เปลี่ยน Acceptance Criteria กับ code
ที่เกี่ยวข้องให้เป็น case ที่พิสูจน์ได้ เป้าหมายคือหา defect ไม่ใช่ทำให้รายงานเป็นสีเขียว.

## แยก design ออกจาก execution

- **Design:** อ่าน requirement/code, หา branch, invariant, side effect และ failure mode โดยยังไม่เปิด
  browser.
- **Happy path:** เดินหนึ่งรอบเพื่อได้ smoke verdict และหลักฐานสำหรับเอกสาร.
- **Adversarial case:** รันแยกทีละ case, คืนเฉพาะ finding และถ่ายภาพเมื่อ fail หรือเมื่อหลักฐานจำเป็น.

ทุกผลต้องเป็น `PASS`, `FAIL` หรือ `UNVERIFIED`. ถ้าไม่ได้รันหรือ browser พิสูจน์ไม่ได้ ห้ามใช้
`PASS`.

## สิ่งที่ browser พิสูจน์ได้

รันและ assert ผ่าน browser ได้เมื่อผลปรากฏใน UI, URL, DOM, console หรือ network observation เช่น:

- valid/invalid/boundary input, ช่องว่าง, format, Unicode/ไทย/emoji;
- validation, navigation, role/permission state ที่ account ทดสอบเข้าถึงได้;
- double-submit และลำดับ action ที่ผู้ใช้ทำได้จริง;
- error/empty/loading states ที่บังคับได้อย่างปลอดภัย;
- visual, keyboard, accessibility และ observable performance behavior.

สิ่งต่อไปนี้ต้องใช้ code review, API/backend test หรือหลาย session เพิ่มเติม เว้นแต่มี harness เฉพาะที่
พิสูจน์ได้จริง:

- concurrency/locking ข้ามผู้ใช้;
- transaction rollback, orphan state และ database integrity;
- platform governance/usage limits และ backend timeout;
- query semantics, cross-tenant authorization และ server-side logging.

บันทึกสิ่งเหล่านี้ว่า `derived from code, unverified in browser` พร้อมชื่อหลักฐานที่ยังขาด.

## Phase 0 — ทำ system map

1. อ่าน entry point, data flow, dependency และ side effect ที่อยู่ใน scope.
2. แตก Acceptance Criteria เป็น observable outcomes.
3. ระบุ business invariant เช่น uniqueness, total, permission และ state transition.
4. จด assumption ที่ยังยืนยันไม่ได้; ถ้าคำตอบเปลี่ยน expected result ให้ถามก่อนรัน.

## Phase 1 — ครอบ supported paths

ทำ coverage matrix จาก behavior จริง:

- ทุก entry point และ mode ที่ผู้ใช้เข้าถึง;
- ทุก branch/guard ที่ส่งผลต่อ UI;
- role/permission และ state ที่ต่างกัน;
- valid input combinations ที่เปลี่ยนผลธุรกิจ.

แต่ละแถวต้องมี scenario, expected observable result และ assertion ที่สั้นพอจะ review ได้.

## Phase 2 — ยิง adversarial cases

เลือกเฉพาะหมวดที่เกี่ยวข้องกับ feature:

- **Boundary:** 0, 1, -1, min/max, precision, overflow.
- **Empty/type/format:** null-equivalent, empty, whitespace, wrong type, timezone, special characters.
- **Uniqueness/state:** duplicate, repeat, interrupt, invalid sequence, session expiry.
- **Auth:** missing permission, expired session, URL/object outside the allowed scope.
- **Error handling:** error must surface; no silent fallback or swallowed rejection.
- **Volume/performance:** realistic large data and a stated, measured budget.

Security payloads must use disposable test data and an authorized environment. Assert that input is
escaped/rejected rather than executed and that secrets/PII do not appear in `console`, visible errors,
reports, or screenshots. Server-side behavior remains a code/backend check.

## Stateful test isolation

Setup and teardown are external orchestration, not executable `flow.yaml` fields. For a run that
creates or changes data:

1. use a unique, narrow marker for this run;
2. record the original state before mutation;
3. identify and log exact cleanup targets before deleting or reverting;
4. stop when the target count or environment differs from expectation;
5. mutate only the confirmed IDs/objects, never a broad criterion;
6. surface teardown failure and mark the environment dirty; do not call the next run clean.

Prefer API/database fixtures when available and authorized. Browser setup is appropriate only when
the UI behavior itself is under test. Production mutation always requires its own explicit approval.

## Phase 3 — รายงาน

| # | Case | Input/state | Expected | Actual | Verdict | Severity | Evidence/repro |
|---|---|---|---|---|---|---|---|

- One bug gets one deterministic repro.
- Cite the requirement and the observable assertion that failed.
- Separate browser evidence from code/backend evidence.
- Record untested or blocked cases explicitly; absence of a finding is not proof of coverage.
- Feed confirmed findings into `assets/bug-report-template.html`; use happy-path evidence for the
  user guide.
