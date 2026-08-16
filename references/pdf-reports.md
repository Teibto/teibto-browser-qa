# ทำเอกสาร PDF คุณภาพส่งจริง (user guide / bug report)

เป้าหมาย: PDF ที่มี **ปก+โลโก้ · สารบัญ+เลขหน้าตรงจริง · footer เลขหน้า · screenshot ไฮไลต์ ·
ตารางข้อมูล** จากการรันจริง. มี template พร้อมใช้ใน `assets/` — แก้แค่ data array.

> **ขอบเขต pipeline:** สูตร paged.js + `assets/guide-template.html` ในไฟล์นี้คือ pipeline
> เอกสาร GENERIC (web app ทั่วไป / หน้า NetSuite ที่ไม่ใช่ record form). คู่มือ NetSuite record form
> ใช้ pipeline ของ skill netsuite-ui-qa-testing (AB pdf + `add-pdf-outline.py` +
> `toc_tools.py` two-pass + DOCX) — อย่าเอามาปนกัน.

## ขั้นตอน (recipe)

```
1. ก๊อป template:  cp assets/guide-template.html  qa/<feat>/guide/guide.html
   (หรือ bug-report-template.html)
2. แก้ data array ในแท็ก <script> ให้ตรงเนื้อหา (scenario/step/field หรือ bug).
   **token discipline:** Edit บังคับ Read ก่อน → อย่าอ่านทั้งไฟล์ (CSS ครึ่งไฟล์ไม่ต้องแตะ).
   อ่านเฉพาะบล็อก `<script>` — `Read offset:57` (guide) / `offset:42` (bug-report); anchor คือ
   บรรทัด `<script>` เผื่อเลขบรรทัดขยับ. วัดจริง (tiktoken): เต็มไฟล์ 4,029 tok → block 1,890 tok
   = ประหยัด ~2,000 tok/เอกสาร (53%).
3. วาง screenshot ไว้ใน guide/shots/ (ถ่ายจาก run จริง — ดูหัวข้อ "ถ่ายภาพไฮไลต์")
4. สร้าง PDF:
     AB nav "file:///ABS/PATH/guide.html"
     AB wait 6000          # รอ paged.js จัดหน้า (เช็ค .pagedjs_page count)
     AB pdf "ชื่อเอกสาร.pdf"
5. verify: เปิด PDF กลับมา screenshot ดูจำนวนหน้า (ต้องไม่มีหน้าว่างสลับ) + สารบัญมีเลขหน้า
```

## เนื้อหาที่มี `<` `>` `&` — escape ให้แล้ว แต่มีข้อยกเว้นหนึ่งข้อ

**ค่าทุกตัวใน `data[]` / `bugs[]` / `META` ถูก HTML-escape ให้อัตโนมัติ** (ที่ขอบของข้อมูล
ก่อนประกอบ HTML) → กรอก payload ที่ทดสอบลงไปได้ตรง ๆ เช่น `assert failed: expected count < 5`
หรือ `<script>alert(1)</script>` มันจะแสดงเป็นตัวอักษรตามที่พิมพ์ ไม่ถูกตีความเป็น markup
และไม่ execute (เทสใน `self-test/smoke-test.sh` ล็อกไว้แล้ว)

⚠️ **ข้อยกเว้นเดียว: ห้ามพิมพ์ `</script>` ตรง ๆ ในไฟล์เทมเพลต** — HTML parser ตัดบล็อก
`<script>` ของเอกสารทิ้งทันทีที่เห็น `</script>` แม้จะอยู่ในสตริง JS ก็ตาม **ตั้งแต่ก่อน JS
ได้ทำงาน** ผลคือ**ทั้งหน้าว่างเปล่า** ไม่มี error ให้เห็น · ไม่มี escape ตอน runtime ตัวไหน
แก้ข้อนี้ได้เพราะไฟล์พังตั้งแต่ชั้น parser แล้ว

```js
evidence:"... got <script>alert(1)<\/script>",   // ✅ ใส่ backslash หน้า /
evidence:"... got <script>alert(1)</script>",    // ❌ เอกสารว่างทั้งหน้า
```

กับดักนี้ยังทำให้ **เทสผ่านฟรี**ได้ด้วย: ถ้าเช็คแค่ "payload ไม่ถูก execute" มันจะผ่านเพราะ
ไม่มีอะไร render เลย — เทสจึงต้องยืนยันก่อนว่าเอกสาร render จริง (`svg.logo` มีอยู่)
แล้วค่อยเช็คเรื่อง escape

## ทำไมต้อง paged.js (และกับดักของมัน)

`AB pdf` รับแค่ path — **ไม่มี option ตั้ง margin / paper / preferCSSPageSize /
header-footer**. `@page` margin-box counter แบบง่าย (`@bottom-center{content:counter(page)}`)
**ทำงานแล้วบน Chrome 150** — verified 2026-07-14: footer เลขหน้าโผล่ครบทุกหน้าใน printToPDF
(เคยพังบน Chrome รุ่นเก่า จึงต้อง re-verify ต่อ version; เดิมเอกสารนี้เขียนว่า "ไม่ทำงาน").
แต่ **ยังต้องใช้ paged.js อยู่ดี** เพราะ **สารบัญเลขหน้า** ต้องพึ่ง `target-counter(attr(href),page)`
ที่ printToPDF เปล่า ๆ ไม่ให้ + คุม page-break/หน้าปกได้แน่กว่า. โหลด CDN ท้าย body **หลัง** script ที่สร้าง DOM:
```html
<script src="https://unpkg.com/pagedjs/dist/paged.polyfill.js"></script>
```

**กับดัก double-pagination (หน้าคู่ว่าง เลขหน้าเป็น 2 เท่า) — ต้องแก้ 2 จุด**
(verified 2026-07-14: paged.js 3 หน้า → PDF **6** หน้าถ้าไม่แก้ หน้าคู่เหลือแค่ footer; แก้แล้วได้ 3 หน้าตรง.
repro harness: `self-test/pdf/`)**:**
1. printToPDF ของ Chrome (`AB pdf`) ใช้ paper **Letter** (พื้นที่พิมพ์ ~196×259mm) + margin default.
   ถ้า `@page size` ใหญ่กว่านี้จะล้นเป็นหน้าถัดไป → ตั้ง **เล็กกว่า**:
   `@page{ size:182mm 250mm; margin:13mm }`
2. อย่าใส่ `margin` บน `.pagedjs_page` ตอนพิมพ์ (มันบวกความสูง) → จำกัดเฉพาะจอ:
   ```css
   @media screen{ .pagedjs_page{ box-shadow:...; margin:10mm auto } }
   @media print { .pagedjs_page{ margin:0 !important; box-shadow:none !important } }
   ```

**สารบัญเลขหน้า:** `leader('.')` อาจไม่ทำงาน → ใช้ flex แทน:
```css
.toc a{ display:flex; justify-content:space-between; border-bottom:1px dotted #ccc }
.toc a::after{ content: target-counter(attr(href), page) }
```

**verify อย่างไร:** generated content (counter/target-counter) **ไม่อยู่** ใน textContent/
getComputedStyle → ตรวจด้วย **screenshot เท่านั้น** (เปิด PDF กลับมาถ่าย). เช็ค: จำนวนหน้าตรงกับ
`.pagedjs_page` count (ไม่เป็น 2 เท่า), สารบัญมีเลข, footer "หน้า X / Y" โผล่.

## ถ่ายภาพไฮไลต์ชี้จุดคลิก (ดู assets/highlight.js)

ก่อน screenshot แต่ละ step: `eval` inject กรอบเรืองแสงบน element เป้าหมาย (ดู snippet ใน
`assets/highlight.js`) — 🔴 แดง = จุดคลิก, 🟢 เขียว = จุดสังเกตผล. ฝังลงรูป → ตรงปุ่มเป๊ะทุกครั้ง.
**อย่าใส่ข้อความไทยในป้ายที่ inject** (headless ไม่มีฟอนต์ไทย เพี้ยนเป็นกล่อง) — ใส่แค่กรอบ,
ข้อความไทยไปอยู่ใน HTML. ขับ flow ด้วย JS click ถ้า native click flaky (ดู gotchas ข้อ 7).

## สไตล์เนื้อหาที่เข้าใจง่าย (อ้างอิง help-center มืออาชีพ)

ต่อ section/scenario ใส่: **คืออะไร · ทำเพื่ออะไร · เมื่อไรใช้**. ต่อ step ใส่: **วิธีทำ · ผลที่เห็น ·
ทำงานอย่างไร/ผลต่อระบบ** + กล่อง note/warning. ปิดท้ายด้วย **ผลต่อระบบหลังทำรายการ**, **FAQ**,
**glossary**. ถ้าระบบจริงไม่มีข้อมูล (เช่น demo ไม่มีสต็อก) ให้แยกชัด "สังเกตจริง" vs "เทียบเคียง"
— อย่าเดามั่ว. ทุก step/หลักฐานต้องมาจาก run จริง ไม่ใช่เขียนจากเดา.
