# Changelog

รูปแบบตาม [Keep a Changelog](https://keepachangelog.com/) · วันที่ `YYYY-MM-DD` · เวอร์ชัน SemVer ต่อ repo

> **ที่มาของไฟล์นี้:** repo นี้เขียน release note ด้วยมือมาตลอด (v1.0.0–v1.5.0) · ไฟล์นี้เพิ่มเข้ามา
> ตอน 2026-08-04 เพื่อให้ CI ออก GitHub Release เองตอน push tag ตาม Playbook R7 ของทีม ·
> **เนื้อเต็มของ v1.0.0–v1.4.0 อยู่ที่ [หน้า Releases](https://github.com/wichtking/agent-browser-qa/releases)**
> ไม่ได้ copy มาซ้ำที่นี่ เพราะจะกลายเป็นสองแหล่งที่ drift จากกันได้ · ตั้งแต่ v1.6.0 เป็นต้นไป
> ไฟล์นี้คือต้นฉบับ และ Release body ถูก generate จากมัน

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
[เนื้อเต็ม](https://github.com/wichtking/agent-browser-qa/releases/tag/v1.4.0)

## [1.3.0] - 2026-07-17

**token optimization, parallel-terminal safety, release badge** —
[เนื้อเต็ม](https://github.com/wichtking/agent-browser-qa/releases/tag/v1.3.0)

## [1.2.0] - 2026-07-09

**enforceable QA gate + test-data + a11y/perf/visual layers** —
[เนื้อเต็ม](https://github.com/wichtking/agent-browser-qa/releases/tag/v1.2.0)

## [1.1.0] - 2026-07-07

**test design, flow specs, English docs** —
[เนื้อเต็ม](https://github.com/wichtking/agent-browser-qa/releases/tag/v1.1.0)

## [1.0.0] - 2026-06-25

**agent-browser-qa — release แรก** —
[เนื้อเต็ม](https://github.com/wichtking/agent-browser-qa/releases/tag/v1.0.0)
