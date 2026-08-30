# Changelog

รูปแบบตาม [Keep a Changelog](https://keepachangelog.com/) · วันที่ `YYYY-MM-DD` · เวอร์ชัน SemVer ต่อ repo

> **ที่มาของไฟล์นี้:** repo นี้เขียน release note ด้วยมือมาตลอด (v1.0.0–v1.5.0) · ไฟล์นี้เพิ่มเข้ามา
> ตอน 2026-08-04 เพื่อให้ CI ออก GitHub Release เองตอน push tag ตาม Playbook R7 ของทีม ·
> **เนื้อเต็มของ v1.0.0–v1.4.0 อยู่ที่ [หน้า Releases](https://github.com/Teibto/teibto-browser-qa/releases)**
> ไม่ได้ copy มาซ้ำที่นี่ เพราะจะกลายเป็นสองแหล่งที่ drift จากกันได้ · ตั้งแต่ v1.6.0 เป็นต้นไป
> ไฟล์นี้คือต้นฉบับ และ Release body ถูก generate จากมัน

## [Unreleased]

### Added

- Token-safe runner stdout (`--stdout summary`) preserves the complete `run-log.jsonl` while returning
  only terminal output to agent context; step `perf_budget_ms` now fails closed on slow observable
  outcomes and records budget evidence in JSONL/report artifacts (measured 87.5% fewer stdout tokens
  on the three-step fixture, #69).
- CI job `driver-compat` รัน `tests/test-flow-runner-live.sh` กับ canonical `cdp.py` ที่ pin tag
  `TEIBTO_DEV_STANDARDS_REF` (v0.83.0) ใน Chrome จริงทุก PR; ไม่มี secret `DEV_STANDARDS_DEPLOY_KEY` (read-only deploy key) = fail
  (fork PR = skip พร้อม warning) — drift ระหว่าง runner กับ driver ถูกจับก่อน merge (#66)
- `session_ready.cdp_script` และข้อความ `DRIVER_INCOMPATIBLE`/`CDP_NOT_READY`/`TARGET_MISMATCH`
  ระบุ path ของ `cdp.py` ที่ runner resolve ได้ เพื่อชี้สำเนาที่ต้องอัปเดตเมื่อเครื่องมี driver หลายชุด (#58)

### Changed

- Runner และ `driver-compat` ยก minimum contract เป็น canonical `cdp.py` v0.83.0 / JSONL protocol v3;
  structured `result.dialogs` เป็น authority ที่ผูก dialog กับ step โดยตรง, stderr ใช้ diagnosis
  และ malformed payload fail closed แทน run-level ledger/race (#68).

### Fixed

- runner บันทึก dialog ที่ cdp.py ตอบอัตโนมัติทุกรายการเป็น event `dialog` ใน run-log + บรรทัด ⚠️ และสรุป
  `Auto-answered dialogs` ใน qa-report; session ได้ `DIALOG=safe` เสมอ (ไม่ inherit จาก shell) เปลี่ยนได้
  เฉพาะ `--dialog accept|dismiss` และ policy ที่ใช้อยู่ใน `run_start.driver_policy.dialog` (#56)
- local UI: `GET /api/stories` ตอบ 200 เสมอเมื่ออ่าน `examples/` ได้ — flow ที่โหลดไม่ได้คืน item พร้อม `error`
  แทนการทำทั้งรายการเป็น 500 (#60)
- local UI: flow `.yml` ที่ `/api/stories` list ได้ สั่ง `POST /api/run` แล้วไม่ 404 อีก — `startRun` ใช้ resolver
  เดียวกับ `metadata()` (#59)
- `tests/test-flow-runner-live.sh` พิมพ์ run-log ของ runner พร้อม path ของ driver ก่อน exit 1 เมื่อ runner
  ล้ม แทนการออกเงียบ ๆ หลัง cleanup ลบ log ทิ้ง (#57)

## [2.2.0] - 2026-08-22

**Current v2 browser guidance with stale transport history and unsupported flow examples removed.**

### Changed

- Reworked `SKILL.md` into safety invariants plus progressive routing, and replaced the README with a
  current v2.1/v0.82 install, smoke, runner, local-UI, and documentation map (#54).
- Condensed the claims audit to current verified/measured/version-pinned evidence while keeping
  withdrawn history discoverable through this changelog and Git history (#54).
- Updated architecture, team process, contributor, command, gotcha, self-test, a11y, performance,
  visual-regression, and test-design guidance to match the executable runner/schema (#54).

### Removed

- Removed orphaned `references/test-data.md`; its generic state-isolation and destructive guardrails
  now live in `references/test-design.md`, while product-specific NetSuite/APEX cleanup recipes are
  outside this generic skill (#54).
- Removed operational migration tables, retired daemon troubleshooting, pre-current-driver behavior,
  and unsupported video/live-view instructions from active runbooks (#54).

### Fixed

- Removed examples for rejected `fixtures`, `teardown`, `a11y`, `perf_budget`, `mask_regions`,
  `diff_threshold`, and `ci_candidate` flow fields, plus old wait/find/batch command syntax (#54).
- Added fail-closed validation for repository-local Markdown links and aligned the smoke-test guide
  with the checks that the current harness actually runs (#54).
- Removed a flaky live-test comparison between driver latency and application wait duration; the
  harness now verifies the observable async delays without treating host timings as a CI budget (#54).

## [2.1.0] - 2026-08-22

### Added

- **Per-phase runner telemetry** — JSONL แยก startup/action/wait/assert/capture/console/total พร้อม
  authoritative driver duration/attempts และ partial phases เมื่อ fail (#52)
- **Async/live performance coverage** — fixture normalize input 150 ms และ defer trusted click
  300 ms เพื่อพิสูจน์ว่า fast input ยังรอ observable outcome; protocol compatibility และ failure
  evidence มี unit gates (#52)

### Changed

- Runner ต้องใช้ canonical CDP JSONL protocol v2+, ขอ `--input-settle=none`, verify ready policy และ
  ใช้ event-bound navigation; standalone/ad-hoc driver behavior ไม่เปลี่ยน (#52)

### Fixed

- `networkidle` หลัง action ไม่ผ่านจาก `readyState` ของ document เก่า; runner ผูก document identity
  ก่อน action และงาน AJAX ใช้ explicit selector/function outcome wait (#52)
- Capture default ตรงกับ spec: `doc:true` ถ่าย step ที่ผ่าน, `doc:false` ถ่ายเฉพาะ failure และ
  `capture` ระดับ step override ได้ (#52)

## [2.0.0] - 2026-08-21

**Canonical team-owned Browser QA with a direct, bounded CDP runner and one local UI.**

### Changed

- ย้าย canonical ownership จากบัญชีส่วนตัวมา `Teibto/teibto-browser-qa` และเปลี่ยน skill/bundle
  identity เป็น `teibto-browser-qa` โดยคง Git history, issues และ Releases เดิม (#47)
- เพิ่ม PR quality gate และบังคับให้ release-on-tag ผ่าน gate เดียวกันก่อนสร้าง bundle พร้อม checksum
- รวม QA runner เข้า repo canonical: strict JSON Schema, one pinned/bounded `cdp.py session --jsonl`
  ต่อ run, secret ผ่าน stdin, fail-fast typed errors, `PASS`/`FAIL`/`UNVERIFIED`, JSONL log/report/shots
- เพิ่ม local-only UI/API ที่ใช้ runner เดียวกัน พร้อม SSE/cancellation/path guards; ตัด dependency
  `agent-browser` daemon, dashboard, video และ ffmpeg ออกจาก runtime

## [1.6.3] - 2026-08-16

**บทเรียนจากการเอา lens ไปยิงของจริงครั้งแรก**

### Added

- **`ux-lens.md` §4.1 "ก่อนเชื่อ lens ตัวใหม่ — เอาไปยิงของจริงก่อนเสมอ"** — ครั้งแรกที่ยิง lens
  ใส่เอกสาร bug-report ที่ส่งลูกค้าจริง ได้ FAIL 4 ข้อ และ **หน้านั้นไม่ได้ผิดสักข้อ พังที่ lens
  ทั้งหมด** · ทั้งสามข้อแรกผ่านเทสของ driver ครบ 88 เคสมาก่อน เพราะ fixture ที่คนเขียนโค้ด
  ออกแบบเองไม่มีพี่น้องที่หน้าตาเหมือนกัน — **เทสที่เขียนจากจินตนาการของคนเขียนไม่มีวันจับคลาสนี้**
  (แก้ที่ต้นทางแล้วใน `Teibto/teibto-dev-standards` v0.74.2 · #202)

### Changed

- `ux-lens.md` §4 ปรับตามพฤติกรรมใหม่ของ lens: `tap-target-small` ฟ้องเมื่อเล็กทั้งสองด้าน
  (พร้อมข้อจำกัดที่ตามมา: ปุ่มแถบยาวที่เตี้ยผิดปกติจะไม่ถูกจับ) · ล้นแนวนอนรายงาน "ตัวแรกในสาย
  ที่เริ่มล้น" · ทุก finding มีฟิลด์ `text` ให้แยกพี่น้องออก
- เพิ่มกฎการอ่านผล `responsive`: **เช็ค `effective_width` ก่อนอ่าน findings เสมอ** — หน้าที่ตรึง
  ความกว้างของตัวเอง (เอกสาร paged.js, `min-width`) จะได้ `width-not-applied` และผลที่ความกว้าง
  นั้น**ไม่ใช่สิ่งที่มือถือเห็น** · อย่าเอา `responsive` ไปยิงเอกสารสำหรับพิมพ์แล้วรายงานว่าพังบนมือถือ

## [1.6.2] - 2026-08-16

### Fixed

- **PDF template ยัดข้อมูลเข้า `innerHTML` โดยไม่ escape** — เนื้อหาที่มี `<` `>` `&` ถูกเบราว์เซอร์
  ตีความเป็น markup: `expected count < 5` กลายเป็น tag ปลอมแล้วข้อความหายไปเงียบ ๆ และ payload
  อย่าง `<script>` ทำงานจริงในเอกสาร · โดนง่ายเป็นพิเศษเพราะสกิลนี้**จงใจ**ยิง injection payload
  เป็น test case แล้วบันทึกผลลง `evidence`/`actual` (#27)
  - แก้โดย escape **ที่ขอบของข้อมูล** (`escDeep` ครั้งเดียวหลังบล็อกที่ผู้ใช้แก้) ไม่ใช่ไล่ครอบทีละ
    `${...}` — field ที่เพิ่มมาทีหลังจึงปลอดภัยเองโดยไม่ต้องจำ
  - `document.title` และ `<style>` textContent อ่านค่าก่อน escape เพราะเป็นบริบท **ข้อความ**
    ไม่ใช่ HTML — ถ้า escape ทับ ผู้ใช้จะเห็น `&lt;ระบบ&gt;` เป็นชื่อเอกสาร

### Added

- **เทสของ #27 ใน `self-test/smoke-test.sh`** — payload ไม่ execute · `<` ไม่หาย · markup ของ
  เทมเพลตยัง render · `document.title` ไม่ถูก escape ทับ (41 passed, 0 failed)
- **`pdf-reports.md` §เนื้อหาที่มี `<` `>` `&`** — บอกว่า escape ให้อัตโนมัติแล้ว **พร้อมข้อยกเว้น
  ที่ escape แก้ไม่ได้**: `</script>` ที่พิมพ์ตรง ๆ ในไฟล์ทำให้ HTML parser ตัดบล็อก `<script>`
  ของเอกสารทิ้ง → **หน้าว่างทั้งหน้าโดยไม่มี error** · เจอตอนเขียนเทสนี้เอง และมันเกือบทำให้เทส
  "ผ่านฟรี" (เช็ค "payload ไม่ execute" ผ่านเพราะไม่มีอะไร render เลย) → เทสจึงยืนยันก่อนว่า
  เอกสาร render จริงแล้วค่อยเช็ค escape

### Changed

- CLAIMS-AUDIT: ปิด flag ที่ค้างจาก Round 4 (#29) — 0.32 hardening ไม่กระทบ flag แก้จอดำ และ
  หมดเจ้าของไปตั้งแต่ทิ้ง daemon ใน v1.5.0

## [1.6.1] - 2026-08-16

**เก็บงานค้างให้จบ — บทเรียนที่ไม่เคยเข้า repo และเอกสารที่ยังสอนคำสั่งที่ไม่มีอยู่จริง**

### Added

- **บทเรียน 7 ข้อที่เขียนไว้ตั้งแต่ 2026-08-10 แต่ไม่เคย commit** — `gotchas.md` §11–§17
  (`nav` อาร์กิวเมนต์ที่สองเป็นวินาที · Chrome บังคับหน้าต่างกว้างขั้นต่ำ ~500px · อ่าน state ทันที
  หลัง scroll · custom property ค้าง · `innerWidth` รวม scrollbar · `el.focus()` ไม่ปลุก
  `:focus-visible` · Chrome cache หน้าเดิม) และหมายเหตุ path Windows ของ `shot`/`pdf` ใน
  `commands.md` · v1.6.0 อ้าง §14–§17 ทั้งที่ยังไม่มีอยู่บน main — คนที่ clone ไปตามลิงก์เจอความว่าง (#41)
- **`commands.md` §`run` และ §`lens`/`steady`/`netlog`/`stub`** — ตารางว่าตัวไหนต้องอยู่ในโหมด `run`
  + กับดัก quote ของ `--body=` + `verdict` มีสามค่าไม่ใช่สอง
- **`self-test/smoke-test.sh` เพิ่ม claim-check ของคำสั่งใหม่** — `run` ทำให้ override อยู่ข้ามคำสั่ง
  (พร้อม**เคสคู่**ที่พิสูจน์ว่าเทสวัดของจริง) · `lens layout` FAIL บนหน้าที่ผิดและ PASS บนหน้าที่ถูก ·
  **`lens netlog` ที่ไม่ได้ `netlog on` = `UNVERIFIED`** — claim ที่อันตรายที่สุดของทั้งสกิล
  เพราะถ้ามัน regress ผลจะออกมาเป็นสีเขียวโดยไม่มีอะไรฟ้อง

### Fixed

- **`docs/ARCHITECTURE.md` §3 ยังเป็นชั้น QA ยุค daemon** — ตารางสอนคำสั่งที่ไม่มีอยู่จริงแล้ว
  (`open`, `errors`, `diff screenshot --baseline`) และนับ 4 ชั้นขณะที่ README/SKILL.md นับ 7 ·
  เขียนใหม่ทั้งหัวข้อ + diagram ที่แยกชั้นบังคับกับชั้น opt-in (#40)
- **README สอนสิ่งที่ไม่จริงสองจุด** — "`click` does not auto-scroll, so call `scrollintoview` first"
  (ปัจจุบัน `click` ทำ `scrollIntoView` ให้ในตัว) และคำแนะนำให้ล้าง "stale session file" ตอนเจอ
  `os error 10060` (เป็นวิธีของ daemon ที่ไม่มีอยู่แล้ว) · ตารางงานในหน้าแรกก็ยังเป็นคำสั่งยุค daemon ทั้งตาราง
- เลิกเขียนจำนวนเคสของ `smoke-test.sh` เป็นตัวเลขตายตัวใน README — สคริปต์พิมพ์ผลรวมเอง
  ป้ายที่ hardcode จะ drift ทุกครั้งที่เพิ่มเทส
- `CLAUDE.md` / `README.md` รายชื่อไฟล์ใน `references/` ตามทัน `ux-lens` · `cdp-limits` · `configure`

### Changed

- **CLAIMS-AUDIT: ตัดสินใจเรื่องการแบ่งเทสระหว่างสองรีโป** — เทสลึกของ `cdp.py` อยู่ที่
  `tests/test-cdp.sh` ของ `teibto-dev-standards` เท่านั้น **ไม่ mirror มาที่นี่** (สองแหล่งจะ drift
  จากกัน) · repo นี้เก็บเฉพาะ claim-check ของสิ่งที่สกิลนี้สัญญาเอง

## [1.6.0] - 2026-08-16

**ชั้นที่ 7: UX/UI lens — และเส้นแบ่งระหว่างงาน QA กับงานตั้งค่าระบบ**

`cdp.py` มีคำสั่ง `run` (หลายคำสั่งบน connection เดียว) และ `lens` ที่คืนคำวินิจฉัยแล้ว
(`Teibto/teibto-dev-standards` #188/#190/#192) สกิลนี้จึงต้องบอกว่าเมื่อไหร่ใช้อะไร
และผลที่ได้เชื่อได้แค่ไหน

### Added

- **`references/ux-lens.md`** — ชั้น QA ที่ 7: `lens layout|responsive|theme|focus|netlog` +
  `steady` + `stub` · เลือก lens ให้ตรงคำถาม · ท่ารันหลาย lens ในหนึ่ง `run` · **ตารางว่าแต่ละ
  lens "โกหก" ได้ยังไง** (ตรวจเฉพาะสิ่งที่มองเห็นอยู่ตอนนั้น, tap target ที่พ่อขยายพื้นที่กดให้,
  theme เทียบสีตรงตัวจึงไม่จับ contrast ต่ำ, focus ยังไม่ตรวจ arrow-key navigation) และ
  **สิ่งที่ lens จงใจไม่ฟ้อง** เพราะด่านที่ฟ้องทุกอย่างไร้ค่าพอกับด่านที่ไม่เคยฟ้องอะไร
- **`references/cdp-limits.md`** — รายการสิ่งที่ CDP แตะไม่ได้เลย (screenshot ของ `alert`/file
  dialog, native `<select>` popup, `chrome://`, PDF viewer) พร้อม**ทางออกทุกข้อ** · แยกจากสิ่งที่
  "ทำได้แต่ไม่ควรใช้ browser ทำ" (GitHub → `gh`, NetSuite → REST/SuiteQL) และสิ่งที่ต้องอยู่ในโหมด
  `run` เท่านั้น · ทีมตกลงว่า transport มีทางเดียวคือ CDP ตรง — กฎนี้จะกลายเป็นด่านที่ fail open
  ทันทีถ้าไม่มีรายการนี้ เพราะคนจะรายงานว่า "ถ่ายภาพไว้แล้ว" ทั้งที่ภาพนั้นถ่ายไม่ติดโดยธรรมชาติ
- **`references/configure.md`** — ตั้งค่าระบบผ่านหน้าจอ: วงจร READ → DIFF → PLAN → APPLY → VERIFY →
  RECORD, desired-state ที่เขียนเป็น "ค่าที่ต้องการ" ไม่ใช่ "ลำดับการคลิก", guardrail
  (`DIALOG=dismiss` เป็นค่าเริ่มต้นของโหมดนี้ · prod ต้องปลดล็อกด้วย flag · verify ไม่ได้ = หยุด),
  evidence record ที่มี `before` ให้ rollback ได้ · **ข้อแรกสุด: ค่าไหนตั้งผ่าน API ได้ API ชนะเสมอ**

### Changed

- **golden rule ข้อ 6: `UNVERIFIED` ไม่ใช่ `PASS`** — "ตรวจไม่ได้" ที่ถูกเขียนลงรายงานว่า "ผ่าน"
  คือการโกหกที่ไม่มีใครตั้งใจ · คลาสเดียวกับ "`console` ว่าง ≠ ไม่มี error" (rule 3)
- `SKILL.md` §4 เพิ่มชั้นที่ 7 เข้า QA layers + ชี้ทางไป `configure.md` พร้อมเส้นแบ่ง:
  **ห้ามปนงาน config เข้าไปใน QA run** เพราะ QA ต้อง read-only เสมอ
- `README.md` — "Four QA layers" เป็น 7 ชั้น และเพิ่ม `PASS`/`FAIL`/`UNVERIFIED` เข้าอภิธานศัพท์

## [1.5.1] - 2026-08-04

**ออก GitHub Release เองตอน push tag — เลิกทำมือ**

### Added

- **`CHANGELOG.md`** (ไฟล์นี้) + **`.github/workflows/release.yml`** + vendor
  `scripts/publish-release.sh` จาก `Teibto/teibto-dev-standards` — tag ต้องมี Release object
  คู่กันเสมอตาม Playbook R7 · repo นี้ยังไม่มีปัญหา (tag/release ตรงกัน 6/6) แต่ที่ตรงเพราะทำมือ
  ทุกครั้ง งานนี้จึงกันไม่ให้ drift ไม่ใช่แก้ของที่พังอยู่ (#36)
- workflow **build + แนบ `.skill` bundle** ให้ด้วย — flow มือเดิมแนบมาตลอด ถ้า automate แล้ว
  ลืมข้อนี้ bundle จะหายเงียบ ๆ และคนที่ install แบบ one-file จะโหลดไม่ได้

### Changed

- `CONTRIBUTING.md` §Cutting a release — ขั้นตอนเหลือ "เขียน CHANGELOG entry แล้ว tag+push"
  · **ไม่มี entry = workflow ล้มโดยเจตนา** (Release ที่ body ว่างแย่กว่าไม่มี)
- ชื่อ Release เป็น `vX.Y.Z` เฉย ๆ ตามมาตรฐานทีม — คำบรรยายย้ายไปอยู่บรรทัดแรกของ body แทน

## [1.5.0] - 2026-08-02

**Transport ย้ายเป็น CDP ตรง — เลิกใช้ `agent-browser` daemon**

daemon ค้างแบบไม่บอกเหตุ (`os error 10060` วนซ้ำ, Chrome ตายเงียบ) และตอบ JS dialog ไม่ได้เลย
โดยเฉพาะ `beforeunload` ที่ทำให้ wedge ถาวร · ขับ Chrome ผ่าน CDP ตรงด้วย `cdp.py` ซึ่งเป็น
driver กลางของทีมที่ [`Teibto/teibto-dev-standards`](https://github.com/Teibto/teibto-dev-standards)

### Changed

- `references/commands.md` เขียนใหม่ทั้งไฟล์ — คู่มือ `cdp.py` + ตารางแปลงคำสั่งเดิมครบทุกตัว
- `references/gotchas.md` คัดของ daemon ออก (10060 ทุกสายพันธุ์, session file, batch shape,
  record/ffmpeg, dashboard) เก็บของ Chrome/หน้าเว็บไว้ครบ + เพิ่ม 4 ข้อใหม่
- `SKILL.md` golden rules 5 ข้อใหม่ (เดิมครึ่งหนึ่งเป็นเรื่อง daemon ล้วน)
- `docs/ARCHITECTURE.md` เปลี่ยนภาพ transport + เพิ่ม §ที่ตัดออกและทำไม
- `self-test/smoke-test.sh` เขียนใหม่ — launch Chrome เอง, **30 เคสกับ browser จริง (30/30 ผ่าน)**

### Added

- gotcha ใหม่ 4 ข้อจากที่เจอตอนย้ายจริง: `console` ว่าง ≠ ไม่มี error (หน้าที่ไม่ได้เปิดด้วย `nav`
  จะ error ไม่ใช่คืน `[]`) · dialog ถูกตอบอัตโนมัติ = เปลี่ยนข้อมูลจริงได้ · `viewport` ที่สั่งแยก
  invocation ไม่มีผลเพราะ Emulation ตายพร้อม websocket · element-scoped `shot` ตก top-layer popup

### Removed

- `record` / `stream` / `dashboard` (วิดีโอ + ดูสด) — เป็นฟีเจอร์ของ daemon · CDP ตรงทำได้แต่ต้อง
  เขียน `Page.startScreencast` + ต่อเฟรมเป็นวิดีโอเอง ไม่คุ้มกับที่ pipeline ทำเอกสารใช้ screenshot
  ต่อ step อยู่แล้ว · เหตุผลและทางกลับบันทึกไว้ใน `docs/ARCHITECTURE.md`
- `references/video-and-live.md`

## [1.4.0] - 2026-07-17

**agent-browser 0.32.1 baseline + onboarding docs** —
[เนื้อเต็ม](https://github.com/Teibto/teibto-browser-qa/releases/tag/v1.4.0)

## [1.3.0] - 2026-07-17

**token optimization, parallel-terminal safety, release badge** —
[เนื้อเต็ม](https://github.com/Teibto/teibto-browser-qa/releases/tag/v1.3.0)

## [1.2.0] - 2026-07-09

**enforceable QA gate + test-data + a11y/perf/visual layers** —
[เนื้อเต็ม](https://github.com/Teibto/teibto-browser-qa/releases/tag/v1.2.0)

## [1.1.0] - 2026-07-07

**test design, flow specs, English docs** —
[เนื้อเต็ม](https://github.com/Teibto/teibto-browser-qa/releases/tag/v1.1.0)

## [1.0.0] - 2026-06-25

**agent-browser-qa — release แรก** —
[เนื้อเต็ม](https://github.com/Teibto/teibto-browser-qa/releases/tag/v1.0.0)
