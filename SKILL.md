---
name: teibto-browser-qa
description: >-
  Drive a real browser (CDP ตรง ผ่าน cdp.py) through a web flow and produce QA results +
  documentation from the live run. Trigger for: smoke-test/QA a web app flow (login,
  checkout, wizard, form, grid), click-through with screenshots per step, visual
  check/regression diff, verify a form/row actually saved, test Suitelet/APEX/any page,
  or turn a run into a user-guide/bug-report PDF. English or Thai, headless or headed,
  even when the driver isn't named. NOT for writing Playwright/Cypress code or CI
  pipelines; NetSuite record-form QA / user guides → skill netsuite-ui-qa-testing (this
  skill keeps generic apps + non-record NetSuite pages). Read references/gotchas.md
  before driving the browser.
---

# Browser QA & Docs

`cdp.py` = driver กลางของทีม ([`Teibto/teibto-dev-standards`](https://github.com/Teibto/teibto-dev-standards)
`scripts/cdp.py`) ที่ขับ Chrome ผ่าน **CDP ตรง ไม่มี daemon คั่น** และคืน accessibility tree
พร้อม ref (`@42`) ที่ LLM อ่านง่าย · **ตัวขับเองไม่กิน token — token หมดไปกับผลลัพธ์ที่เราป้อนกลับ
เข้า context เท่านั้น**

> ทีมเลิกใช้ `agent-browser` daemon แล้ว (teibto-dev-standards#111) เพราะมันค้างแบบไม่บอกเหตุ
> (`os error 10060` วนซ้ำ, Chrome ตายเงียบ) และตอบ JS dialog ไม่ได้เลย โดยเฉพาะ `beforeunload`
> ที่ทำให้ daemon wedge ถาวร · ตารางแปลงคำสั่งทั้งหมด → `references/commands.md`

**Roles:** Claude = the brain (read code → derive tests → judge pass/fail → write docs).
`cdp.py` = the hands & eyes (drive the browser + capture evidence; it decides nothing).

**Principle — one pass, two outputs:** walk the happy path once → get both (1) a smoke verdict and
(2) raw material for a user guide / bug report.

**What to test (beyond the happy path):** test *design* is a brain activity (read code → decide
which cases to fire) — cheap, never touches the browser. **All adversarial coverage lives there**,
so it doesn't conflict with token discipline: execution still uses the same short commands. The
happy-path pass yields guide + smoke; adversarial checks are *separate* passes that return **only
bug findings**. **Read `references/test-design.md`** when scope goes beyond smoke (Phase 0 system
map → coverage matrix → edge cases → the split of what runs in-browser vs. what must be derived
from code).

---

## 1. Install (first time)

```bash
py -m pip install websocket-client pillow numpy    # pillow/numpy เฉพาะตอนใช้ diff
```

ตัว `cdp.py` มาพร้อม skill ของทีม (`~/.claude/skills/netsuite-qa-browser/references/cdp.py`)
หรือ vendor เข้า repo งานก็ได้ · setup ครบชุด + ทุกคำสั่ง → `references/commands.md`

---

## 2. Golden rules — read before driving the browser (most important)

These traps make automation **fail silently, with no error** — full detail + evidence in
`references/gotchas.md`, but keep these six in mind at all times:

0. **หนึ่งงาน = หนึ่ง `CDP_PORT` = หนึ่ง `--user-data-dir`** ตั้งก่อนคำสั่งแรกเสมอ · สอง terminal
   ที่ใช้ profile เดียวกัน **login จะ rotate cookie ใส่กัน** → หน้า render เป็น anonymous ทั้งที่
   server บอกว่า login สำเร็จ ไล่ฝั่งแอปกี่ชั่วโมงก็ไม่เจอ (#10 ใน `references/gotchas.md`)
1. **ทำงานในแท็บของตัวเองที่มี marker เฉพาะ แล้วปักหมุด** —
   `export TGT_ID=$(AB newtab "<url>?job=<งาน>")` · ไม่ปักหมุดแล้วคำสั่งอาจไปตกแท็บของ session อื่น
2. **อย่าเชื่อว่า "คำสั่งผ่าน" = "งานสำเร็จ"** — assert ผลลัพธ์ทุกครั้งด้วยคำสั่งสั้น
   (`wait <เงื่อนไข>` / `url` / `get text`) · คำสั่งที่ exit 0 แปลว่า "สั่งไปแล้ว" เท่านั้น
3. **`console` ว่าง ≠ ไม่มี error** — collector ผูกกับหน้า ถ้าหน้านั้นไม่ได้เปิดด้วย `nav`
   คำสั่งจะ error (โดยเจตนา) ไม่ใช่คืน `[]` · "ไม่มี error" กับ "ไม่ได้เฝ้าอยู่" คนละเรื่อง
4. **dialog ถูกตอบให้อัตโนมัติ — อ่าน `[dialog]` ใน stderr ทุกครั้ง** · กด OK บน `confirm` ของแอป
   = ยืนยันบันทึก/ลบจริง · `DIALOG=dismiss` เมื่อต้องการปฏิเสธไว้ก่อน
5. **จอดำใน headed = 3 กลไก ไม่ใช่แค่ "GPU" — เช็ค `AB url` ก่อน** · `about:blank` = หน้ายังไม่ navigate
   (benign) → `nav` ซ้ำ · url จริงแต่หน้าต่างถูกบัง → relaunch พร้อม stability flags ·
   `AB shot` ใช้ได้เสมอไม่ว่ากรณีไหน (#9 ใน `references/gotchas.md`)
6. **`UNVERIFIED` ไม่ใช่ `PASS`** — `lens` คืนสามค่าเสมอ · "ตรวจไม่ได้" ที่ถูกเขียนลงรายงานว่า
   "ผ่าน" คือการโกหกที่ไม่มีใครตั้งใจ · สิ่งที่ CDP แตะไม่ได้เลยมีรายการอยู่ที่
   `references/cdp-limits.md` — ห้ามรายงานว่าตรวจแล้ว

Extra: `AB click` ยิง Input event จริงพร้อม scrollIntoView ให้แล้ว · ถ้ายังไม่ติดจริง ๆ ใช้
**JS click** `eval "document.querySelector('SEL').click()"` เดิน flow ต่อ แล้วแยกไปรายงานเรื่อง
"ความคลิกได้จริง" เป็น finding ต่างหาก

---

## 3. Token discipline (prevent context overflow)

- For assertions use only **short-output commands**: `wait`, `is visible/enabled/checked`,
  `get value/text/count`, `console`.
- **Never** feed a whole-page `a11y` dump or raw `get html` back into context — กรอง `a11y` ด้วย
  คำค้นเสมอ (`AB a11y "Submit"`)
- **screenshot = always a file** — path เข้า context ได้ ภาพไม่ควรเข้า (เว้นจำเป็นจริง ๆ)
- งานยาวรวมเป็น JS ก้อนเดียวแล้ว `evalf` คืน JSON ก้อนเดียว → `references/commands.md`

Full command reference + commonly-missed syntax → `references/commands.md`

**Verify the command/syntax claims machine-side:** `self-test/smoke-test.sh` (รันกับ Chrome จริง —
re-run ทุกครั้งที่ Chrome หรือ `cdp.py` เปลี่ยนเวอร์ชัน = drift detector) · claim ไหน verified
vs inferred: `docs/CLAIMS-AUDIT.md`.

---

## 4. Standard workflow (one pass, two outputs)

```
1. AB nav <url> → AB wait "<เงื่อนไขที่เจาะจงกับหน้านี้>"   (ติดตั้ง console collector ให้อัตโนมัติ)
2. ก่อนทุก action: AB shot <file> เก็บเป็นหลักฐาน / วัตถุดิบของ guide
3. action: AB click/fill ด้วย ref @<id> จาก a11y หรือ selector
4. assert ผลลัพธ์ด้วยคำสั่งสั้น (golden rule #2)
5. AB console → ไม่ว่าง = FAIL บันทึก error ไว้ (ห้าม fallback เงียบ)
6. จบ flow: เขียน 2 ไฟล์ — qa-report.md (verdict) + user guide / bug report
```

QA layers: (1) Smoke = happy path completes + `console` ว่าง · (2) Functional = assert state ·
(3) Visual = `AB diff <baseline> <current>` · (4) Error surfacing = `console` after every key step ·
(5) a11y = inject axe-core, return count + top N (`references/a11y-layer.md`) ·
(6) Perf = save/load timing vs budget (`references/perf-layer.md`) ·
(7) **UX/UI = `AB lens layout|responsive|theme|focus|netlog`** — ล้นแนวนอน · tap target เล็กเกิน ·
dark mode อ่านไม่ออก · Tab เดินไม่ครบ · error ฝั่ง network ที่ `console` มองไม่เห็น
(`references/ux-lens.md`). Layers 5–7 are opt-in per scenario and return only findings — never a dump.

**ตั้งค่าระบบผ่านหน้าจอ (ไม่ใช่ QA)** → `references/configure.md` · คนละสัญญากับงาน QA โดยสิ้นเชิง:
QA ผิด = รายงานผิด แต่ config ผิด = ระบบจริงเปลี่ยน · ห้ามปนสองอย่างนี้ใน run เดียวกัน

**Store test cases as repeatable files** (regression/repro) → write them as flow YAML:
`references/flow-spec.md`. **ลด process spawn:** รวมงานหลายขั้นเป็น JS ก้อนเดียวแล้ว `evalf`
(แต่ action ที่เปลี่ยน state ยังควรแยกเพื่อ assert ทีละขั้น) · pre-flight เหลือแค่
`curl /json/version` → `references/commands.md`.

Suggested artifact layout:
```
qa/<feature>/
  qa-report.md          # verdict + step table + errors
  shots/                # screenshot per step (artifact, not context)
  guide/                # generated docs (HTML/PDF) + shots
```

---

## 5. Produce PDF docs (user guide / bug report)

Produce ship-ready docs (cover + logo, table of contents + page numbers, FAQ, glossary) from a real
run — ready-made templates + a page-number-correct PDF recipe are included. **Read
`references/pdf-reports.md` before making a PDF** (there are paged.js + Chrome printToPDF traps that
cause alternating blank pages).

**Pipeline boundary:** this skill owns the GENERIC guide/bug-report PDF pipeline (paged.js +
`assets/guide-template.html`). NetSuite record-form guides use netsuite-ui-qa-testing's own pipeline
(`cdp.py pdf` + PyMuPDF `add-pdf-outline.py` + `toc_tools.py` two-pass + DOCX) — do not mix them.

- `assets/guide-template.html` — document-style user guide (cover, breadcrumb, highlighted
  screenshot, field table, what/why/effect-on-system, FAQ, glossary). Edit only the data array.
- `assets/bug-report-template.html` — bug report (cover, TOC + severity, Steps/Expected/Actual/
  Evidence/Workaround/Impact). Edit only the bug array.
- `assets/highlight.js` — snippet to inject a click-target highlight ring into a screenshot (ring-only, no text).
- `assets/pointer.js` — snippet `point(sel)` that places a pointer ring marking the focus/click spot (for video/live, see §6).

**Do not bake Thai text into screenshots** (headless has no Thai font). Full PDF recipe (paged.js,
the double-pagination fix, page-number verification) → `references/pdf-reports.md`.

---

## 6. วิดีโอ / ดูสด — **ตัดออกแล้ว**

`record` / `stream` / `dashboard` เป็นฟีเจอร์ของ daemon ที่ถูกทิ้งไปพร้อมกัน · เหตุผลและสิ่งที่
เสียไปจริง → `docs/ARCHITECTURE.md` §ที่ตัดออกและทำไม

ใช้ **`AB shot` ต่อ step** เป็นหลักฐานแทน ซึ่งเป็น artifact ที่ดีกว่าสำหรับ guide/bug report อยู่แล้ว
(อ้างอิงหน้าได้ · `AB diff` ได้ · ไม่ต้องเปิดดูทั้งคลิป) · `assets/pointer.js` ยังใช้ได้สำหรับ
ชี้จุดโฟกัสในภาพนิ่ง

---

## Specific targets (NetSuite / APEX)

- **NetSuite:** ใช้ Chrome profile ที่ login ค้างไว้ (`--user-data-dir` ตัวเดิม) เลี่ยง 2FA ซ้ำ ·
  element ใน iframe → `IFRAME="#sel" AB get ...` (ไม่มี state ค้างให้ลืมออก) ·
  async loads → `AB wait "window.jQuery ? jQuery.active===0 : true"` ·
  **งาน record-form / user guide ของ NetSuite ใช้ skill `netsuite-ui-qa-testing` ไม่ใช่ตัวนี้**
- **Oracle APEX:** แยก `CDP_PORT` + profile ต่องาน · dynamic Interactive Grid cells/buttons →
  `AB a11y "<ชื่อที่เห็นบนจอ>"` แล้วใช้ ref · ทดสอบ input ภาษาไทยด้วย · skill `apex-page-as-code`
  มีสูตรเฉพาะของ APEX
