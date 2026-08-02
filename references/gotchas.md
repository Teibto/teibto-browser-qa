# กับดักที่เจอจริง + วิธีแก้ (transport = CDP ตรง)

รวมบั๊ก/ข้อจำกัด/ความเข้าใจผิดที่เสียเวลาไปจริง (Chrome for Testing / Chrome 150 · Windows 11).
เรียงตามความสำคัญ. **อ่านก่อนเริ่มขับ browser** เพราะหลายอันทำให้ automation "ผ่านแบบหลอก"
(false pass) ตรวจจับยาก.

> **ที่หายไปพร้อม agent-browser daemon** (Teibto/teibto-dev-standards#111): `os error 10060`
> ทุกสายพันธุ์ · session file ค้างชี้ daemon ตาย · "daemon version mismatch, restarting" ·
> `connect` ค้าง 2 นาที · zombie daemon บน port สุ่ม · daemon/Chrome ค้างสะสมข้ามคืน ·
> `record` ที่ต้อง restart daemon หลังติดตั้ง ffmpeg — **ไม่ต้องไล่หาอีกแล้ว**
> ถ้ายังเจอ แปลว่ามีสคริปต์เก่าที่ยังเรียก daemon ค้างอยู่

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

---

## 1. อย่าเชื่อว่า "คำสั่งผ่าน" = "งานสำเร็จ" [HIGH]

คำสั่งที่ exit 0 แปลว่า "สั่งไปแล้ว" ไม่ใช่ "เกิดผลลัพธ์ตามตั้งใจ" · หลัง action ที่เปลี่ยน state
ต้องพิสูจน์ด้วยคำสั่งสั้น:

- หลัง click ที่นำทาง → `AB url` (เช็ค url เปลี่ยน)
- หลัง add-to-cart → `AB wait "!!document.querySelector('[data-test=remove]')"` หรือ `AB get text ".badge"`
- หลังกรอกฟอร์ม → `AB get value "#field"` ยืนยันค่าเข้าจริง

อ่าน state ทันทีหลัง click บางครั้ง race (ยังไม่ render) → ใช้ `wait <เงื่อนไขของผลลัพธ์>`
แทนการอ่านดิบ · การ "อ่านเร็วเกิน" ทำให้เข้าใจผิดว่า click ไม่ติดทั้งที่ติด

`cdp.py click` ยิง **Input event จริง** พร้อม `scrollIntoView` ให้แล้ว — ปัญหา "คลิกใต้ fold แล้ว
เป็น no-op เงียบ ๆ" ของตัวขับรุ่นเก่าจึงไม่เกิด **แต่กฎ assert ยังอยู่** เพราะ handler ของแอป
อาจไม่ทำงานด้วยเหตุอื่น (element ถูก overlay ทับ, handler ยังไม่ bind, ปุ่ม disabled)

---

## 2. `console` ว่าง ≠ ไม่มี error [HIGH — false pass ตรง ๆ]

`cdp.py console` อ่านจาก collector ที่ **inject ลงหน้า** (`window.onerror` + `unhandledrejection`
+ patch `console.error/warn`) ซึ่งถูกติดตั้งอัตโนมัติทุกครั้งที่ `nav`

**ที่ต้องระวัง:**

- **หน้าที่ไม่ได้เปิดด้วย `nav` จะไม่มี collector** (เช่นหน้าที่แอป redirect ไปเอง หรือแท็บที่คนอื่น
  เปิดไว้) → `console` จะ **error ไม่ใช่คืน `[]`** โดยเจตนา เพราะ "ไม่มี error" กับ "ไม่ได้เฝ้าอยู่"
  คนละเรื่อง · เจอ error นี้ให้ `nav` ซ้ำ หรือ inject collector เอง
- **collector ตายพร้อมหน้า** — navigate แล้ว log เริ่มใหม่ · **นี่คือพฤติกรรมที่ต้องการ**:
  buffer สะสมข้ามหน้า (แบบที่ `agent-browser errors` ทำ) ทำให้ error ของหน้าก่อนถูกนับเป็นของ
  หน้านี้ ซึ่งเป็น false PASS ที่จับยากมาก
- **error ที่เกิด "ก่อน" collector ถูกติดตั้ง จับไม่ได้** — script ที่ throw ตอน parse ของหน้า
  อยู่ก่อนเราเสมอ · ต้องจับ error ตอน load จริง ๆ ให้เปิดหน้าเปล่าก่อน inject แล้วค่อย
  `location.href = <target>`
- เก็บสูงสุด **200 รายการต่อหน้า** — หน้าที่ spam error จะถูกตัดท้าย

---

## 3. dialog ถูกตอบอัตโนมัติ — สะดวกแต่เปลี่ยนข้อมูลจริงได้ [HIGH]

`cdp.py` เปิด `Page.enable` ตั้งแต่ต่อ session แล้วตอบทุก `alert`/`confirm`/`prompt`/**`beforeunload`**
ให้อัตโนมัติ (default = accept) — นี่คือเหตุผลหลักที่ทิ้ง daemon เพราะมันทำข้อนี้ไม่ได้เลย

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

ถาม 2 คำถามก่อนเสมอ — (1) `AB url` เป็น `about:blank` ไหม? (2) หน้าต่างถูก **บัง/background**
อยู่ไหม (terminal ทับ, QA window อยู่หลัง)?

**กลไก A — `about:blank` cosmetic (benign, เจอบ่อยสุด).** `about:blank` พื้น dark theme ว่างเปล่า
= ดำ เป็นเรื่องปกติ ไม่ใช่ paint พัง · ทดสอบจับภาพหน้าต่างจริงตรงพิกัด: ดำ ⟺ `url == about:blank`
เท่านั้น; พอ navigate หน้าจริง render ปกติทันที **ทั้งมีและไม่มี `--disable-gpu`**
แปลว่า browser **ยังไม่ได้ navigate ไปเป้าหมาย** → เช็ค `AB url` แล้ว `nav` ซ้ำ

**กลไก B — GPU-compositing black rectangle.** automation Chrome บน Windows headed บางเงื่อนไข
paint content เป็นสี่เหลี่ยมดำทั้งที่ url เป็นหน้าจริง · แก้: `--disable-gpu --disable-software-rasterizer`

**กลไก C — occluded/background window หยุด paint ("the real repeat offender").** Chrome บน Windows
มี feature `CalculateNativeWinOcclusion`: หน้าต่างที่ถูกบัง/background ถูกมองว่า hidden แล้ว
**หยุด render** → จอดำ · QA window ถูก background ตลอดเวลาที่ agent ขับ → โดนเต็ม ๆ · แก้:
`--disable-features=CalculateNativeWinOcclusion --disable-backgrounding-occluded-windows
--disable-renderer-backgrounding`

**สิ่งที่วัดได้เอง (bound):** ทดสอบบนเครื่องนี้ (Chrome 150, จับภาพหน้าต่างจริง + cover window 9 วิ)
บน example.com **และหน้า NetSuite Login จริง** มี/ไม่มี flag → **reproduce B และ C ไม่ได้เลย**
reproduce ได้แค่ A · สรุป: B/C เป็น **conditional จริง** (background นานเป็นนาที / GPU driver เฉพาะ /
Chrome รุ่นเก่า) ที่ cover สังเคราะห์สั้น ๆ trigger ไม่ติด — flag set มาจาก session จริงยาว ๆ
จึงยังเชื่อถือได้ แค่ trigger ไม่ง่ายบน Chrome 150

**ที่ยืนยันแน่:** **CDP screenshot ภูมิคุ้มกัน occlusion** (capture จาก renderer compositor ไม่ใช่
native window) → ถูกบังอยู่ก็ยังได้ภาพหน้าจริง → **artifact ของ guide/report ไม่พังแม้จอจะดำ**

**Decision rule:** `AB url` ก่อน → `about:blank` = กลไก A (nav ซ้ำ, benign) · url เป็นหน้าจริง +
หน้าต่างถูกบัง = B/C → relaunch พร้อม flag set · `AB shot` ใช้ได้เสมอไม่ว่ากรณีไหน

---

## 10. หลาย terminal ขับพร้อมกัน — แยก port + profile [HIGH — เมื่อรันขนาน]

**กลไกเปลี่ยนไปจากยุค daemon:** ไม่มี "session name" ให้ชนกันแล้ว · สิ่งที่ชนกันคือ **Chrome
instance** และ **cookie jar ของ profile**

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

**เก็บกวาด:** ไม่มี daemon ให้ล้าง · ปิดแท็บของงานเราด้วย `AB close "<marker ของงาน>"` แล้วจบ ·
**ห้ามลบ `.qa-profiles/`** ถ้ามี login อยู่ (จะต้อง 2FA ใหม่) · Chrome ที่เราเปิดเองปิดได้ตามปกติ
— แต่ **ห้าม `taskkill chrome` มั่ว** เพราะ Chrome ส่วนตัวของผู้ใช้ปนอยู่ ให้กรองด้วย
`--user-data-dir` ของ QA เท่านั้น:

```powershell
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
  ? { $_.CommandLine -like '*\.qa-profiles\*' } |
  % { Stop-Process -Id $_.ProcessId -Force }
```
