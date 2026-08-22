# กับดักที่เจอจริง + วิธีแก้ (transport = CDP ตรง)

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
- `cdp.py` protocol v2 register collector ด้วย `Page.addScriptToEvaluateOnNewDocument` ก่อน `nav`
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

