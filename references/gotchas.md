# กับดักที่เจอจริง + วิธีแก้ (transport = CDP ตรง)

ค่าเริ่มต้นคือ BrowserSkill (`bsk`); กับดักของ bsk อยู่ใน [`engine2-bsk.md`](engine2-bsk.md).
ใช้ไฟล์นี้เมื่อเลือก `--engine cdp` โดยชัดแจ้งเท่านั้น.

รวมข้อจำกัดและความเข้าใจผิดที่ทำให้ direct-CDP automation ผ่านหรือ fail แบบหลอกบน Windows.
พฤติกรรมที่ขึ้นกับ Chrome/driver ระบุ provenance ใน `docs/CLAIMS-AUDIT.md`; รัน self-test ใหม่เมื่อ
เวอร์ชันเปลี่ยน.

## TOC

1. อย่าเชื่อว่า "คำสั่งผ่าน" = "งานสำเร็จ" — assert state เสมอ
2. `console` ว่าง ≠ ไม่มี error — แยก "ไม่มีข้อผิดพลาด" ออกจาก "ไม่ได้เฝ้าอยู่"
3. dialog ถูกตอบอัตโนมัติ — สะดวกแต่เปลี่ยนข้อมูลจริงได้
4. `viewport` ที่สั่งแยกคำสั่งไม่มีผล — Emulation ตายพร้อม websocket
5. element-scoped `shot` ตก popup ที่เป็น top-layer
6. Syntax ที่พลาดบ่อย
7. headless ไม่มีฟอนต์ไทย
8. Chrome PDF viewer สคริปต์ไม่ได้
9. headed window จอดำ — แยก 3 กลไก อย่าเหมารวมว่า "GPU"
10. หลาย terminal ขับพร้อมกัน — แยก port + profile
11. ใช้ event-bound navigation; positional `<n>` เป็น legacy fixed drain ไม่ใช่เงื่อนไข JS
12. Chrome บังคับหน้าต่างกว้างขั้นต่ำ ~500px — วัด layout ที่ 320/390 ตรง ๆ ไม่ได้
13. อ่าน state ทันทีหลังสั่ง scroll = อ่านก่อน handler ที่ deferred ด้วย rAF ทำงาน
14. เปลี่ยน CSS custom property แล้ววัดในสคริปต์เดียวกัน = ได้ค่า `var()` ค้าง (fail ปลอม)
15. `innerWidth` ใต้ device-metrics override รวม scrollbar — ด่าน overflow จึงแดงทุกความกว้าง (fail ปลอม)
16. `el.focus()` ไม่ทำให้ `:focus-visible` ทำงาน — ด่าน focus ring รายงานว่า "ทุกปุ่มไม่มี ring"
17. Chrome cache หน้าเดิม — แก้ไฟล์แล้ว QA ยังวัดโค้ดเก่า ผลที่ได้จึงเป็นของรุ่นก่อนแก้
18. แท็บ/หน้าต่างไม่อยู่หน้าสุด — `requestAnimationFrame` ไม่รัน และ trusted `click` อาจหายเงียบ
19. `document.fonts.check()` ตอบ `true` ให้ฟอนต์ที่ไม่มี — วัด presence ด้วยความกว้างเทียบ baseline คนละตระกูล
20. `wait` หลัง `click` ไปหน้าที่โหลดเกิน ~10 วิ ล้มด้วย `WS_TIMEOUT` ทั้งที่ click สำเร็จ
21. `fill` จบด้วยการกด Tab — โฟกัสไปอยู่ที่ `BODY` แล้ว `key Enter` ต่อจากนั้นจึงไม่ส่งฟอร์ม/แชต

---

## 1. อย่าเชื่อว่า "คำสั่งผ่าน" = "งานสำเร็จ" [HIGH]

คำสั่งที่ exit 0 แปลว่า "สั่งไปแล้ว" ไม่ใช่ "เกิดผลลัพธ์ตามตั้งใจ" · หลัง action ที่เปลี่ยน state
ต้องพิสูจน์ด้วยคำสั่งสั้น:

- หลัง click ที่นำทาง → `AB url` (เช็ค url เปลี่ยน)
- หลัง add-to-cart → `AB wait "!!document.querySelector('[data-test=remove]')"` หรือ `AB get text ".badge"`
- หลังกรอกฟอร์ม → `AB get value "#field"` ยืนยันค่าเข้าจริง

อ่าน state ทันทีหลัง click บางครั้ง race (ยังไม่ render) → ใช้ `wait <เงื่อนไขของผลลัพธ์>`
แทนการอ่านดิบ · การ "อ่านเร็วเกิน" ทำให้เข้าใจผิดว่า click ไม่ติดทั้งที่ติด

`cdp.py click` ยิง **Input event จริง** พร้อม `scrollIntoView` ให้แล้ว แต่กฎ assert ยังอยู่ เพราะ
handler ของแอปอาจไม่ทำงานด้วยเหตุอื่น เช่น overlay, handler ที่ยังไม่ bind หรือปุ่ม disabled.

---

## 2. `console` ว่าง ≠ ไม่มี error [HIGH — false pass ตรง ๆ]

`cdp.py console` อ่านจาก collector ที่ **inject ลงหน้า** (`window.onerror` + `unhandledrejection`
+ patch `console.error/warn`) ซึ่งถูกติดตั้งอัตโนมัติทุกครั้งที่ `nav`

**ที่ต้องระวัง:**

- **หน้าที่ไม่ได้เปิดด้วย `nav` จะไม่มี collector** (เช่นหน้าที่แอป redirect ไปเอง หรือแท็บที่คนอื่น
  เปิดไว้) → `console` จะ **error ไม่ใช่คืน `[]`** โดยเจตนา เพราะ "ไม่มี error" กับ "ไม่ได้เฝ้าอยู่"
  คนละเรื่อง · เจอ error นี้ให้ `nav` ซ้ำ หรือ inject collector เอง
- **collector ตายพร้อมหน้า** — navigate แล้ว log เริ่มใหม่ · **นี่คือพฤติกรรมที่ต้องการ**:
  buffer สะสมข้ามหน้าจะทำให้ error ของหน้าก่อนถูกนับเป็นของหน้าปัจจุบัน.
- `cdp.py` protocol v3 register collector ด้วย `Page.addScriptToEvaluateOnNewDocument` ก่อน `nav`
  ใน connection เดียวกัน จึงจับ load-time error ได้; post-nav eval ใช้ verify/fallback
- **หน้าที่เปิด/เปลี่ยนไปก่อน connection ปัจจุบัน register collector ยังจับย้อนหลังไม่ได้** — เช่น
  คนเปิดแท็บไว้ก่อน หรือ one-shot `nav` จบแล้วแอป navigate เองภายหลัง · `console` จะ error ไม่ใช่ `[]`
- เก็บสูงสุด **200 รายการต่อหน้า** — หน้าที่ spam error จะถูกตัดท้าย

---

## 3. dialog ถูกตอบอัตโนมัติ — สะดวกแต่เปลี่ยนข้อมูลจริงได้ [HIGH]

`cdp.py` เปิด `Page.enable` ตั้งแต่ต่อ session แล้วตอบทุก `alert`/`confirm`/`prompt`/**`beforeunload`**
ตาม `DIALOG` policy.

**แต่ "ตอบได้" ไม่ได้แปลว่า "ควรตอบ":**

- กด OK บน `confirm` ของแอป = **ยืนยันบันทึก/ลบจริง**
- กด OK บน `beforeunload` = **ทิ้งงานที่ยังไม่ save จริง ๆ**

ทุก dialog ที่ถูกตอบจะถูกพิมพ์ลง **stderr** เป็น `[dialog] <ชนิด>: <ข้อความ> -> accept` —
**อ่านบรรทัดนั้นทุกครั้ง** · ต้องการปฏิเสธไว้ก่อนใช้ `DIALOG=dismiss AB ...` แล้วดูว่า url
ยังเป็นหน้าเดิมไหม

---

## 4. `viewport` ที่สั่งแยกคำสั่งไม่มีผล [MEDIUM — เงียบสนิท]

`Emulation.setDeviceMetricsOverride` **ผูกกับ session ของ CDP** และถูกยกเลิกทันทีที่ปิด websocket ·
`cdp.py` เปิด WebSocket ใหม่ทุก invocation → `AB viewport 1920 1200 2` แล้วค่อย `AB shot`
**ได้ภาพ 1x เสมอ** ทั้งที่ตั้ง dsf ไว้แล้ว และไม่มีอะไรฟ้อง

```bash
AB shot out.png "#card" --dsf=2 --vw=1920 --vh=1200     # ✓ metric ในคำสั่งเดียวกับที่ถ่าย
AB viewport 1920 1200 2 && AB shot out.png              # ✗ ได้ 1x — override ตายไปแล้ว
```

(teibto-dev-standards#119 · เทส `T11e` ล็อกข้อนี้ไว้แล้ว) · เหตุผลเดียวกับที่ `evalmedia` ต้องตั้ง
media แล้ว eval **ในคำสั่งเดียว**

**ขนาดหน้าต่างไม่ตายตามไปด้วย** — สิ่งที่หายไปพร้อม websocket คือชั้น emulation (`devicePixelRatio`
กลับเป็นค่าเดิม) แต่หน้าต่างถูก resize จริงและ **ค้างขนาดนั้นข้าม invocation** · วัดจริง 2026-09-14
Chrome 152 ทั้ง headless และ headed: `AB shot m.png --vw=390 --vh=700` แล้วคำสั่งถัดไปอ่าน `innerWidth`
ได้ 390 จนกว่าจะมีคำสั่งตั้งขนาดใหม่ → ก่อนกลับไปวัดจอ PC ให้ `AB shot x.png --vw=1440 --vh=900` คืนก่อน
แล้ว assert `innerWidth` · และอย่าใช้ `innerWidth` พิสูจน์ว่า override ยังอยู่ ใช้ `devicePixelRatio` (`ux-lens.md` §4)

**harness ที่ห่อ `viewport` เป็นคำสั่งเดี่ยว = ด่านที่ไม่รู้ว่าวัดที่กี่พิกเซล:** e2e sweep ที่เขียน
`def viewport(w, h): cdp('viewport', w, h)` แล้วค่อย nav/probe ในคำสั่งถัดไป จะวัดที่ขนาดที่หน้าต่างค้างอยู่
ตอนนั้น ไม่ใช่ขนาดที่ตั้งใจ · อาการที่หลอกที่สุดคือเฟสหนึ่งเขียวยกแผง อีกเฟสแดงยกแผงรวมหน้าที่ไม่ได้แก้
ซึ่งอ่านเหมือน regression ของโค้ด (เจอจริง 2026-08-24 · TBTKB #853) → ทุก probe ต้องอยู่ใน invocation
เดียวกับที่ตั้ง metrics (`run <script>` / `lens responsive`) และเฟสต้อง assert `innerWidth` ตรงกับที่ตั้ง
**ก่อน** วัดหน้าแรก แล้วหยุดทั้งเฟสถ้าไม่ตรง

---

## 5. element-scoped `shot` ตก popup ที่เป็น top-layer [MEDIUM]

`AB shot out.png "#card"` crop เฉพาะกล่องของ element — **native `<select>` popup, `<dialog>`
ที่เป็น top-layer, tooltip ที่ portal ออกไปนอก element จะไม่ติดมาด้วย** เพราะอยู่คนละ layer

ภาพที่ต้องมี popup → ถ่าย **full viewport** แล้ว crop ทีหลัง · หรือใช้ท่า DOM (กาง `<select>`
ด้วย `size=N`) ซึ่งอยู่ใน DOM จึงจับติดเสมอ → `commands.md` §จับภาพ native `<select>`

ป๊อปอัป native ที่อยู่นอก DOM จริง ๆ (`alert`/`confirm`, file dialog) **screenshot ไม่ติดทุกกรณี**

---

## 6. Syntax ที่พลาดบ่อย [LOW — แต่เสียเวลา debug]

- **`get attr <selector> <name>`** — selector มาก่อน! `get attr "#a" href` ✓
- **`get` คืน `<no element>` เมื่อหา element ไม่เจอ** — อย่าอ่านเป็น "ค่าว่าง" มันคนละเรื่อง
  (selector ผิด/หน้ายังไม่ render ≠ field ว่าง)
- **ref จาก `a11y` (`@42`) ใช้ข้าม invocation ได้** เพราะเป็น `backendNodeId` ที่คงที่ตลอดอายุ node —
  แต่ stale เมื่อ navigate หรือหน้า re-render node นั้นทิ้ง
- **PowerShell กลืน `@42`** (`@` = splatting token) → ต้อง quote เสมอ: `AB click '@42'`
- **`eval` ทุกครั้งรันใน global scope เดียวกันของหน้า** — top-level `let x` ใน eval แรกทำให้
  eval ถัดไปที่ประกาศ `let x` ซ้ำพัง `SyntaxError: Identifier 'x' has already been declared`
  (เจอจริง 2 ครั้งใน session เดียว) · ครอบ IIFE เสมอ:
  `(function(){ ...; return JSON.stringify(out); })()` และเก็บค่าข้าม eval ที่ `window.__x`
- **`IFRAME` ไม่มี state ค้าง** — ต่างจาก `frame "#sel"` เดิมที่ต้องจำ `frame main` กลับ ·
  ที่นี่ตั้งเฉพาะคำสั่งที่ต้องการ: `IFRAME="#fr" AB get text "#inner"`

---

## 7. headless Chrome ไม่มีฟอนต์ไทย [LOW]

ข้อความไทยที่ **render/วาดใน headless** (เช่น label ที่ inject เองด้วย `font: ... sans-serif`)
กลายเป็นกล่อง □□□ · แต่ HTML ที่เปิดในเบราว์เซอร์ผู้ใช้ render ไทยปกติ

**แก้:** อย่า bake ข้อความไทยลง screenshot ใน headless — ใส่แค่กรอบ/ไฮไลต์เปล่า ๆ
(ดู `assets/highlight.js`) แล้วเขียนข้อความไทยใน HTML/เอกสาร · หรือกำหนด font stack ที่มี glyph ไทย

---

## 8. Chrome PDF viewer สคริปต์ไม่ได้ [LOW]

หน้า PDF ใน Chrome อยู่ใน `<embed>`/shadow DOM — `elementFromPoint` คืน BODY, `PageDown` /
`#page=N` / คลิก thumbnail **ไม่ทำงานผ่าน CDP** · ถ้าต้องอ่าน PDF อ้างอิงให้ screenshot ทีละหน้า
(แต่ก็เลื่อนหน้าไม่ได้ง่าย ๆ) — ทางที่ดีกว่าคือแปลง PDF→ข้อความ/ภาพด้วยเครื่องมืออื่น

---

## 9. headed window จอดำ — แยก 3 กลไก อย่าเหมารวมว่า "GPU" [MEDIUM]

เริ่มจากหลักฐาน ไม่เดาสาเหตุจากสีของหน้าต่าง:

1. `AB url` เป็น `about:blank` → browser ยังไม่อยู่หน้าเป้าหมาย; ใช้ event-bound `nav`.
2. URL ถูกแต่ `AB shot evidence.png` ได้หน้าปกติ → ปัญหาอยู่ที่ native window/occlusion ไม่ใช่ DOM;
   ใช้ screenshot เป็นหลักฐานและทำ headed-window diagnosis แยก.
3. URL ถูกและ screenshot ผิดด้วย → เก็บ URL, screenshot, console และเปิด driver/app bug; ห้ามเติม
   GPU flags แบบเดาแล้วประกาศว่าแก้แล้ว.

`AB shot` จับจาก renderer จึงเป็นหลักฐานที่น่าเชื่อกว่าการมองหน้าต่างที่อาจถูกบัง. GPU/occlusion
สาเหตุเฉพาะเครื่องยังเป็น version-pinned inference ใน claims ledger ไม่ใช่ default diagnosis.

---

## 10. หลาย terminal ขับพร้อมกัน — แยก port + profile [HIGH — เมื่อรันขนาน]

สิ่งที่ชนกันคือ **Chrome instance**, CDP port และ **cookie jar ของ profile**.

```bash
# terminal ที่ 1
export CDP_PORT=9400; chrome --user-data-dir=<...>/.qa-profiles/run-a --remote-debugging-port=9400 &
# terminal ที่ 2 — คนละ port คนละ profile
export CDP_PORT=9401; chrome --user-data-dir=<...>/.qa-profiles/run-b --remote-debugging-port=9401 &
```

- **หนึ่ง `--user-data-dir` = Chrome ได้แค่ 1 process** (profile lock ของ Windows) → สอง terminal
  ใช้ profile เดียวกันไม่ได้แม้ port ต่างกัน
- **ใช้ profile เดียวกันที่ login ไว้แล้ว ⇒ cookie rotate ใส่กัน** — เจอจริง (TBTKB #354, บันทึกใน
  skill `apex-page-as-code`): สอง terminal login แอปเดียวกัน ทุก ~10 วิ cookie ถูกทับ ผลคือ
  login "สำเร็จ" ฝั่ง server ทุกครั้งแต่หน้า render เป็น anonymous · สะสมหนักจนเซิร์ฟเวอร์ตอบ
  400 ทั้ง origin เพราะ cookie บวม · **ไล่ฝั่งแอปกี่ชั่วโมงก็ไม่เจอเพราะมันไม่ได้พังจริง**
- ต้องใช้ login เดิมจริง ๆ → **seed สำเนา profile ต่อ terminal** ไม่ใช่แชร์ตัวเดียวกัน

**เก็บกวาด:** ปิดแท็บของงานเราด้วย `AB close "<marker ของงาน>"` · **ห้ามลบ `.qa-profiles/`**
ถ้ามี login อยู่ (จะต้อง 2FA ใหม่) · Chrome ที่เราเปิดเองปิดได้ตามปกติ
— แต่ **ห้าม `taskkill chrome` มั่ว** เพราะ Chrome ส่วนตัวของผู้ใช้ปนอยู่ ให้กรองด้วย
`--user-data-dir` ของ QA เท่านั้น:

```powershell
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
  ? { $_.CommandLine -like '*\.qa-profiles\*' } |
  % { Stop-Process -Id $_.ProcessId -Force }
```

**profile เก่าโตเงียบจนกินดิสก์เป็นสิบ GB:** profile ที่ตั้งชื่อใหม่ต่อ issue/agent ไม่มีใครลบ · baseline
~240 MB ต่อ profile และบางอันโหลด `OptGuideOnDeviceModel` (on-device model ของ Chrome) เพิ่มอีก ~4 GB ·
ตรวจจริง 2026-08-28: `D:\Claude\TEIBTO` มี 67 profile รวม 23.7 GB (repo TBTKB อย่างเดียว 53 profile / 20 GB)

- วัดขนาดบน Windows ด้วย `robocopy <dir> D:\__nul__ /L /S /NJH /NFL /NDL /BYTES` แล้วอ่านบรรทัด `Bytes :` ·
  `du -sm` ผ่าน Git Bash ช้าจน timeout บน tree ที่มีไฟล์เยอะ
- ก่อนลบต้องเช็คว่าไม่มี Chrome ใช้ profile นั้นอยู่ (ดึง `--user-data-dir=` จาก CommandLine แบบคำสั่งข้างบน)
  — session อื่นอาจเปิด profile เก่ากลับมาระหว่างกวาด (เจอจริง: `Remove-Item` ล้มที่ `BrowserMetrics\*.pma`)
  · ห้าม kill browser ของ session อื่นเพื่อให้ลบผ่าน
- เกณฑ์กวาดที่ใช้ได้จริง: เก็บ profile ที่แตะภายใน 3 วัน และ profile ที่ login ไว้ (ค่า re-login/2FA แพงกว่าพื้นที่)
  ที่เหลือลบได้
- artifact dir ของงาน (`.runtime-*/`) มักฝัง chrome profile ไว้ข้างใน — ตัด `chrome-*profile*` ออกก่อน archive

### กวาดด้วยสคริปต์ (ไม่ต้องรื้อคำสั่งมือ)

`scripts/profile-sweep.py` ทำตามเกณฑ์ข้างบนให้อัตโนมัติ — **dry-run เป็นค่าเริ่มต้น** และ
**ไม่แตะ profile ที่ Chrome กำลังใช้** (ดึง `--user-data-dir=` จาก CommandLine เอง ไม่ต้อง
`taskkill`):

```bash
python scripts/profile-sweep.py --profiles-dir .qa-profiles                      # รายงานก่อน ไม่ลบ
python scripts/profile-sweep.py --profiles-dir .qa-profiles --apply              # กวาดจริง (เก่ากว่า 3 วัน)
python scripts/profile-sweep.py --profiles-dir .qa-profiles --only run-x --apply --force  # post-run hook
```

- `--keep-days N` เก็บ profile ที่แตะภายใน N วัน (default 3) · `--protect 'sb2*'` กันชื่อที่ต้องเก็บ
- วางไฟล์ `.keep` ใน profile ที่ login ไว้ (`.qa-profiles/<customer>/.keep`) ให้รอดทุกโหมด รวม `--force`
- `--strict-probe` = ถ้าดึงรายการ process ไม่ได้ให้ล้มทันที แทนที่จะถือว่า "ไม่มีใครใช้"

**ลดการโตตั้งแต่ต้น** — flags ตอนเปิด Chrome ของงาน (inferred: ยังไม่ได้ A/B ในรีโปนี้):

```bash
chrome --user-data-dir=... --disable-features=OptimizationGuideModelDownloading \
       --disable-component-update --disable-background-networking about:blank
```

`OptGuideOnDeviceModel` (~4 GB) และ component crx cache (~37 MB/component) คือก้อนที่โตโดยไม่เกี่ยวกับ
งาน QA; ปิดสองอย่างนี้ตัดการโตได้ — แต่รัน `self-test/smoke-test.sh` ยืนยันก่อนเลื่อนเป็นค่าเริ่มต้น

---

## 11. ใช้ event-bound navigation; positional `<n>` เป็น legacy fixed drain [HIGH]

```bash
AB nav "<url>" --until=load --timeout=30             # preferred: ผูกกับ document ใหม่
AB wait "document.querySelector('#ready')!==null" 15 0.05
```

`nav <url> <n>` ยังรองรับเพื่อ compatibility แต่ `<n>` คือจำนวนวินาที fixed drain ไม่ใช่เงื่อนไข
JavaScript. **ห้าม optimize ด้วย `nav <url> 0` แล้ว wait `readyState` อย่างเดียว**: document เก่าอาจ
เป็น `complete` อยู่แล้ว ทำให้ assertion อ่านหน้าเก่าเป็น false PASS.

**ผลข้างเคียงที่แพงกว่าตัว error:** `nav` เป็นคำสั่งที่ติดตั้ง console collector ให้ · `nav` ล้ม =
ไม่มี collector → `AB console` คำสั่งถัดไปตอบว่า "collector ยังไม่ถูกติดตั้ง" ซึ่ง**ถูก** แต่ถ้าอ่านผ่าน ๆ
แล้วเข้าใจว่า "ไม่มี error" ก็คือ false pass ตาม gotcha #2 เต็มรูปแบบ

---

## 12. Chrome บังคับหน้าต่างกว้างขั้นต่ำ ~500px [MEDIUM — เงียบ · ทำให้เทส mobile เป็น false pass]

`--window-size=320,900` **ไม่ได้ viewport 320** — Chrome (รวม `--headless=new`) ปัดขึ้นเป็น ~500px
`window.innerWidth` จึงคืน 500 ทั้งที่สั่ง 320/390/480 → **เทส breakpoint ของมือถือผ่านโดยไม่ได้ทดสอบ
ความกว้างจริงเลย** และไม่มีอะไรฟ้อง (เจอจริง 2026-08-14 · nav ล้นแนวนอนที่ 390px รอดด่านมาได้
เพราะทุก probe วัดที่ 500)

```bash
for W in 320 390 480; do ... --window-size=$W,900 ...; done   # ทั้งสามได้ innerWidth=500
```

**ทางที่ใช้ได้จริง**

| ต้องการ | ใช้ |
|---|---|
| ภาพที่ layout จริงของ 320/390 | `AB shot out.png --vw=390 --vh=844` (device metrics มีผลในคำสั่งนั้น ดู #4) |
| assert layout ที่ <500 | `AB lens responsive 320,390,480` ซึ่งตั้งและวัด device metrics ใน invocation เดียว |
| ตรวจว่าล้นแนวนอนไหม | assert `document.documentElement.scrollWidth === window.innerWidth` **และ**
ไม่มี element ที่ `getBoundingClientRect().right > innerWidth` ที่ทุกความกว้างที่วัดได้ (500–1920) |

**ห้ามใช้ `overflow-x:hidden` แก้อาการล้น** — มันทำให้ทั้งด่านนี้ผ่านฟรีตลอดไป (`scrollWidth`
เท่ากับ `innerWidth` เสมอ) ทั้งที่ของยังล้นอยู่จริงและผู้ใช้เห็นของถูกตัด

---

## 13. อ่าน state ทันทีหลังสั่ง scroll = อ่านก่อน handler ที่ deferred ทำงาน [MEDIUM — false FAIL]

หน้าเว็บที่ผูก `scroll` handler แล้ว defer งานด้วย `requestAnimationFrame` (แพตเทิร์นปกติของ
scroll-spy / reveal / sticky state) **จะยังไม่ได้อัปเดต DOM ตอนที่สคริปต์ก้อนเดียวกันอ่านผล** —
rAF callback รันหลัง script ปัจจุบันจบ

```js
// ❌ อ่านได้ NONE ทุกครั้ง ทั้งที่หน้าไม่ได้พัง
document.getElementById('scale').scrollIntoView({behavior:'instant'});
return document.querySelectorAll('a[aria-current]').length;
```

```bash
# ✅ เปลี่ยน state แล้วรอ observable outcome แบบ bounded ก่อนอ่าน
AB eval "document.getElementById('scale').scrollIntoView({behavior:'instant'}); 'x'"
AB wait "document.querySelectorAll('a[aria-current]').length>0" 5 0.05
AB eval "[...document.querySelectorAll('a[aria-current]')].map(a=>a.getAttribute('href')).join('|')||'NONE'"
```

เจอจริง 2026-08-14: สรุปผิดว่า scroll-spy ไม่ทำงานเลย แล้วเกือบไปแก้โค้ดที่ถูกอยู่แล้ว ·
**อาการเดียวกันกับ `behavior:'smooth'`** — ที่นั่นแย่กว่าเพราะ scroll ยังวิ่งอยู่ ตำแหน่งที่วัดได้
เป็นของกลางทาง (ค่าติดลบแปลก ๆ) ใช้ `behavior:'instant'` เสมอเมื่อวัดตำแหน่ง

---

## 14. เปลี่ยน custom property แล้ววัดในสคริปต์เดียวกัน = ได้ค่าค้าง [HIGH — false FAIL ที่ดูน่าเชื่อ]

สลับธีมด้วย `setAttribute('data-theme', ...)` (หรือแก้ `--token` ตรง ๆ) แล้วอ่าน
`getComputedStyle` ของ element อื่นในสคริปต์ก้อนเดียวกัน จะได้ค่าที่ยัง resolve จากธีมก่อนหน้า
Chrome resolve `var()` แบบ lazy ต่อ element — element ที่ถูกอ่านก่อน (เช่น `body`) recalc ให้
แต่ element ที่อ่านทีหลังยังไม่ recalc

```js
// ❌ วัด contrast ได้ 1.06 (ตัวหนังสือหายไปกับพื้น) ทั้งที่ของจริง 17:1
document.documentElement.setAttribute('data-theme','light');
const s = getComputedStyle(document.querySelector('.btn-solid'));   // ยังเป็นสีของธีม dark
```

```bash
# ✅ สลับใน round trip หนึ่ง วัดใน round trip ถัดไป
AB eval "document.documentElement.setAttribute('data-theme','light');'set'"
AB evalf contrast.js
```

**อาการที่ทำให้เสียเวลา:** ค่าที่ได้ "สมเหตุสมผล" พอที่จะเชื่อ — `body` อ่านได้สีใหม่ถูกต้อง
แต่ปุ่มอ่านได้สีเก่า ทำให้สรุปว่า "ธีม light พังเฉพาะปุ่ม" แล้วไปไล่ specificity ของ CSS ที่ถูกอยู่แล้ว
วิธียืนยันเร็วที่สุดคืออ่านค่าโทเคนกับค่าที่ element ใช้จริงมาเทียบกัน
(`getComputedStyle(document.documentElement).getPropertyValue('--ink')` vs
`getComputedStyle(el).backgroundColor`) ถ้าสองอันไม่ตรงกันคือเจอกับดักนี้ ไม่ใช่บั๊กของหน้า

ญาติของ #13 — กฎเดียวกันคือ **หนึ่ง round trip เปลี่ยน หนึ่ง round trip วัด**

**แก้เพิ่ม 2026-08-15: แยก round trip อย่างเดียว "ไม่พอ" เสมอไป** เจอเคสที่สลับธีมด้วย
`setAttribute` ใน eval หนึ่ง แล้ว sleep 0.5 วินาที แล้ววัดใน eval ถัดไป **ยังได้สีของธีมเก่า**
(ปุ่มอ่านได้ `#f2f2f0` ทั้งที่ `--ink` ของ `:root` อ่านได้ `#15171d` ถูกต้องแล้ว)
สิ่งที่ได้ผลคือ **กดปุ่มสลับธีมด้วย `AB click`** แล้วรอ state ของหน้า ก่อนค่อยวัด เพราะ handler ของ
แอปทำงานผ่านทางเดียวกับผู้ใช้ · กฎที่ปลอดภัยที่สุดคือ **เปลี่ยน state ผ่าน trusted action อย่าตั้ง
attribute เองแล้ววัด** และยืนยันด้วย screenshot อย่างน้อยหนึ่งครั้งก่อนเชื่อว่าหน้าพัง

---

## 15. `innerWidth` ใต้ device-metrics override รวมความกว้าง scrollbar [HIGH — false FAIL ทุกความกว้าง]

ด่าน "ไม่มีอะไรล้นแนวนอน" ที่เขียนว่า `documentElement.scrollWidth === innerWidth` **แดงทุกความกว้าง**
เมื่อขับผ่าน `Emulation.setDeviceMetricsOverride` เพราะ `innerWidth` = ความกว้างที่สั่ง
แต่ `scrollWidth`/`clientWidth` = ความกว้างหลังหัก scrollbar (~15px บน Windows)

```js
// ❌ 1265 !== 1280 ทุกครั้ง ทั้งที่ไม่มี element ไหนล้นเลย
d.scrollWidth === innerWidth
// ✅ เทียบกับ clientWidth และวัด element ทั้งสองข้าง
d.scrollWidth <= d.clientWidth &&
  ![...document.querySelectorAll('body *')].some(e => {
    const b = e.getBoundingClientRect();
    return b.right > d.clientWidth + 1 || b.left < -1;   // ล้นซ้ายไม่เพิ่ม scrollWidth
  })
```

อาการที่หลอก: ความกว้างเล็ก ๆ ที่หน้าไม่มี scrollbar (เนื้อหาสั้น) จะผ่าน ส่วนความกว้างใหญ่แดงหมด
ทำให้ดูเหมือน "layout พังเฉพาะจอใหญ่" ซึ่งเป็นข้อสรุปที่ผิด

---

## 16. `el.focus()` ไม่ทำให้ `:focus-visible` ทำงาน [HIGH — false FAIL ยกแผง]

focus ring สมัยใหม่เขียนด้วย `*:focus-visible` ซึ่ง **ผูกกับ heuristic ว่าผู้ใช้ใช้คีย์บอร์ดอยู่**
การเรียก `el.focus()` จากสคริปต์ไม่เข้าเงื่อนไขนั้น `getComputedStyle(el).outlineWidth` จึงเป็น `0px`
ทุกตัว และด่านจะรายงานว่า "ทุกปุ่มไม่มี focus ring" ทั้งที่กด Tab เองแล้วเห็นชัด

```bash
# ✅ กด Tab จริงแล้ววัด document.activeElement ทีละ stop
AB key Tab
AB eval "(()=>{const e=document.activeElement,s=getComputedStyle(e);
  return e.tagName+'|'+s.outlineWidth+'|'+s.outlineStyle;})()"
```

**และอย่าวัดแค่ความหนา** — `outlineWidth != 0` ผ่านได้ด้วย outline โปร่งใสหรือสีกลืนพื้น
ต้องเช็ค `outlineStyle !== 'none'` · alpha ของ `outlineColor` · และ contrast กับพื้นหลัง ≥ 3:1

---

## 17. Chrome cache หน้าเดิมไว้ — QA วัดโค้ดที่ยังไม่ได้แก้ [HIGH — สรุปผิดว่า "แก้แล้วไม่หาย"]

รอบ QA ที่แก้ไฟล์ใน working tree แล้ว `nav` ไป URL เดิม (`http://127.0.0.1:PORT/`)
Chrome เสิร์ฟจาก memory cache ผลที่ได้จึงเป็นของรุ่นก่อนแก้ **อาการคือแก้บั๊กแล้วด่านยังแดงเหมือนเดิม
เป๊ะทุกบรรทัด** ซึ่งชวนให้ไปรื้อโค้ดที่แก้ถูกแล้ว

```python
c.nav(URL + "?qa=" + str(int(time.time())))   # cache-bust ทุกรอบ
```

ตัวชี้ขาดว่าเจอกับดักนี้: เปิด URL พร้อม query ใหม่แล้วผลเปลี่ยนทันที · เจอจริง 2026-08-15
(#117 ของ ERP-AI-First) เสียเวลาไปหนึ่งรอบเต็มกับการยืนยันว่า fix ที่ถูกอยู่แล้ว "ไม่ทำงาน"

**cache ฝั่ง server หลอกแบบเดียวกัน:** static file ของ APEX workspace เสิร์ฟ
`Cache-Control: max-age=315360000, immutable` ตาม URL ที่มี `v<FILES_VERSION>` — ตรวจว่าเสิร์ฟรุ่นไหนด้วยการ
`curl` URL จริงแล้ว grep marker ของรุ่นใหม่ ไม่ใช่เชื่อผลตรวจฝั่ง DB อย่างเดียว (TBTKB #983)

---

## 18. แท็บ/หน้าต่างไม่อยู่หน้าสุด — `requestAnimationFrame` ไม่รัน และ trusted `click` อาจหายเงียบ [HIGH — เมื่อรันขนานหรือแชร์ Chrome]

เกิดได้ทั้งตอนเปิด QA Chrome หลายตัวพร้อมกัน (#10) และใน shared session ที่หลาย agent ถือคนละแท็บใน Chrome
ใบเดียว (skill `netsuite-qa-browser`) — อีก agent ยกแท็บของตัวเองขึ้นหน้า แท็บของเรากลายเป็น background

**`requestAnimationFrame` ไม่รันในแท็บ background** — วัดจริง 2026-09-14 Chrome 152 ทั้ง headless และ headed:
`document.hidden === true` แล้ว callback ไม่รันเลย พอยกแท็บกลับมาหน้าก็รันทันที (`self-test/smoke-test.sh` ล็อกไว้)
อาการในแอป: element ที่วางตำแหน่งใน rAF ค้างที่ตำแหน่งตั้งต้น (inline `left/top/max-width` ว่าง) ขณะที่ส่วนที่ตั้ง
แบบ synchronous ถูกต้อง — e2e ผ่านบ้างไม่ผ่านบ้างตามว่าแท็บไหนอยู่หน้า (TBTKB #983) · ต่างจาก #13 ที่ rAF
รันแน่แต่อ่านเร็วเกิน

- พิสูจน์ก่อนโทษ cache/deploy: ให้ probe คืน `el.style.cssText` ด้วย — ว่างทั้งที่ไฟล์ที่เสิร์ฟเป็นรุ่นใหม่ (#17)
  = callback ไม่เคยรัน
- โค้ด layout ที่ต้องถูกเสมอให้ทำแบบ synchronous (อ่าน `offsetWidth` บังคับ layout ได้อยู่แล้ว) — ผู้ใช้จริง
  ที่สลับแท็บก็โดนแบบเดียวกัน

**trusted `click` ตอบ `clicked <sel> @ x,y` แต่ไม่เกิดอะไร** — เจอจริง 2026-08-23 (6 Chrome ขนานบน TBTKB)
และ 2026-09-08 (shared session: คลิก rail item เดิมที่เพิ่งใช้ได้ แล้วเงียบสามรอบติด) · **ยังไม่มีข้อสรุปว่าเป็นเพราะ
background:** ใน session เดียวกันนั้นคลิกอย่างอื่น (ปุ่มในตาราง · modal · toast) สำเร็จทั้งที่ `document.hidden === true`
ข้อนี้จึงเป็น `inferred` ใน `docs/CLAIMS-AUDIT.md` (ติดตามที่ #74) · ท่าที่แยกได้จริงคือ synthetic เทียบ trusted:

```js
document.hidden                    // สัญญาณ ไม่ใช่คำอธิบาย
document.elementFromPoint(x, y)    // จุดกึ่งกลางที่ cdp.py จะคลิก ตกบน element ไหน
el.click()                         // synthetic — ข้าม hit-test ทั้งหมด
```

- synthetic ผ่าน + trusted ไม่ผ่าน = handler ผูกครบ ปัญหาอยู่ที่ชั้น input/hit-test
- trusted ล้มเฉพาะบาง element แต่ตัวอื่นบนหน้าเดียวกันผ่าน → สงสัย hit-test ของจุดนั้นก่อน (กึ่งกลางอาจตกบนลูก
  ที่ไม่ใช่เป้า เช่น `<svg>` ในปุ่ม) ไม่ใช่สงสัยทั้งแท็บ
- flow ที่ต้องเป็น user input จริงห้ามเปลี่ยนไปใช้ synthetic เพื่อให้ผ่าน · synthetic ใช้เปิด state เพื่อวัด geometry
  อย่างเดียวได้

**แก้:** สั่ง `AB shot x.png` ก่อนชุดคลิกหรือก่อนวัดสิ่งที่พึ่ง rAF — `shot` เรียก `Page.bringToFront` ให้ ·
และ assert ผลหลังคลิกเสมอ (#1)

---

## 19. `document.fonts.check()` ตอบ `true` ให้ฟอนต์ที่ไม่มีในเครื่อง [HIGH — ทำให้ ship regression]

`document.fonts.check('12px "JetBrains Mono"')` คืน `true` บนเครื่องที่ไม่มี JetBrains Mono เพราะมันตอบว่า
"มี web font ที่ยังต้องรอโหลดไหม" ไม่ใช่ "เครื่องมี family นี้ไหม" · วัดจริง Chrome 152 / Windows 11: ตอบ `true`
ให้ JetBrains Mono, Fira Code, Cascadia Mono ที่ไม่มีสักตัว (2026-09-08) และให้ชื่อที่ไม่มีอยู่จริง
(2026-09-14 ทั้ง headless/headed · `self-test/smoke-test.sh` ล็อกไว้)

**ท่าที่ตอบถูก — เทียบความกว้างกับ baseline:**

```js
const w = (fam, txt) => {
  const s = document.createElement('span');
  s.style.cssText = 'position:absolute;visibility:hidden;font-size:40px;white-space:pre;font-family:' + fam;
  s.textContent = txt; document.body.appendChild(s);
  const r = s.getBoundingClientRect().width; s.remove(); return Math.round(r * 100) / 100;
};
const present = (n, t) => w(`"${n}", serif`, t) !== w('"__no_such_face__", serif', t);
```

**baseline ต้องเป็น generic คนละตระกูลกับ family ที่ตรวจ** — generic `monospace` ของ Chrome บน Windows คือ
Consolas เทียบกับมันแล้วได้คำตอบว่า "Consolas ไม่ได้ติดตั้ง" ซึ่งผิดและดูน่าเชื่อมาก (วัดซ้ำ 2026-09-14:
เทียบ `serif` = มี · เทียบ `monospace` = ไม่มี)

**อีกด้านที่สำคัญกว่า:** อย่าสรุปพฤติกรรมฟอนต์จากไฟล์ใน repo ฟอนต์ที่ผู้ใช้ลงเองมีอยู่จริงและมีผลจริง — stack
ที่ "ไม่มีตัวไหนถูก serve" ยังเลือก family ที่เครื่องมีได้ · การถอดชื่อออกเพราะคิดว่าไม่มีผลทำให้ตัวอักษรไทยทั้งหน้า
เปลี่ยนฟอนต์และ merge ไปแล้วก่อนจะจับได้ (TEIBTO-Bank-Reconcile #105) · **วัดในเบราว์เซอร์ก่อนแตะ font stack
เสมอ** — เป็นคำถามที่ repo ตอบไม่ได้โดยหลักการ

## 20. `wait` หลัง `click` ไปหน้าที่โหลดเกิน ~10 วิ ล้มด้วย `WS_TIMEOUT` [HIGH — false FAIL บน NetSuite]

step `click` ที่ทำให้เกิด navigation ไปหน้าโหลดช้า แล้วตามด้วย `wait` แบบ expression, selector หรือ
`networkidle` ล้มด้วย `WS_TIMEOUT` หลัง ~10 วินาที **ไม่ใช่** ที่ deadline 20–30 วินาทีของ `wait` เอง —
ทั้งที่ click สำเร็จและหน้าปลายทางโหลดครบในอีกไม่กี่วินาที. รายงานจึงออกมาเป็น FAIL ที่ step คลิก
โดย `failing_phase` คือ `wait` ไม่ใช่ `action`.

วัดจริงบน NetSuite SB2 (2026-09-19, flow read-only: Sales Order list → คลิก View):
`wait.driver_ms = 10012` แล้ว `WS_TIMEOUT` · หน้า Sales Order view เดียวกันวัดด้วย `nav --until=load` ได้
**13,812 ms** · เปลี่ยน wait เป็นพักแบบกำหนดเวลาแล้ว flow เดิมผ่าน 4/4. สาเหตุที่ evaluate ไม่ตอบ
(renderer ไม่ว่าง หรือ execution context ถูกทำลายระหว่าง navigation) **ยังไม่ได้แยก** — ติดตามที่
`Teibto/teibto-dev-standards#396`.

**อ่านอาการให้ถูกก่อนไล่บั๊ก:** `WS_TIMEOUT` + `failing_phase: wait` + `driver_ms ≈ 10000` หลัง click ที่เปลี่ยนหน้า
= กับดักนี้ ไม่ใช่ปุ่มกดไม่ติด. เปิด failure screenshot ดู — ถ้าเห็นหน้าปลายทางกำลังขึ้น แปลว่า click ลงแล้ว.

**ท่าเลี่ยงจนกว่า driver จะแก้:**

```yaml
- action: click
  target: "tr.uir-list-row-tr a.viewitem"
  risk: read
  wait: 17000            # พักแบบกำหนดเวลา: runner sleep เอง ไม่ส่งคำสั่งเข้า driver ระหว่างหน้าโหลด
  assert: { url_contains: "/salesord.nl?id=" }
- action: wait           # step ถัดไปพิสูจน์ outcome จริงเมื่อ renderer ว่างแล้ว
  target: "fn:!!document.querySelector('h1.uir-record-type')"
  assert: { target: "h1.uir-record-type", contains: "Sales Order" }
```

- ตั้งเวลาพักจากเวลาโหลดที่ **วัดได้** ของหน้านั้น (`nav --until=load` แล้วจับเวลา) บวกส่วนเผื่อ ไม่ใช่เดา
- นี่คือ fixed sleep ซึ่งขัดกับแนวทาง "รอ observable outcome": ใช้เฉพาะ step ที่เข้าอาการข้างบน,
  ใส่ comment อ้างข้อนี้ และห้ามใส่ `perf_budget_ms` ใน step นั้นเพราะตัวเลขจะเป็นเวลาพัก ไม่ใช่เวลาของแอป
- ถ้าไม่ได้ต้องการพิสูจน์ว่า "ลิงก์กดได้" ให้ใช้ `open` ไป URL ปลายทางแทน — `open` รอ navigation แบบ
  event-bound และไม่เข้ากับดักนี้
