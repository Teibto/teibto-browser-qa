# CDP ทำอะไรไม่ได้ — และต้องทำอะไรแทน

ทีมตกลงแล้วว่า **transport มีทางเดียวคือ CDP ตรง** (ไม่มี daemon, ไม่มี Playwright/Puppeteer,
ไม่มี driver ตัวที่สอง) · กฎนี้จะกลายเป็นด่านที่ fail open ทันทีถ้าไม่เขียนไว้ว่ามันแตะอะไรไม่ได้ —
เพราะคนจะรายงานว่า "ถ่ายภาพไว้แล้ว" ทั้งที่ภาพนั้นถ่ายไม่ติดโดยธรรมชาติ

> **กฎ:** สิ่งที่อยู่ในตารางนี้ **ห้ามคืน `PASS`** · ถ้าจำเป็นต้องรายงาน ให้เป็น `UNVERIFIED`
> พร้อมบอกว่าต้องไปทำท่าไหนแทน

---

## 1. สิ่งที่ CDP แตะไม่ได้

| ทำไม่ได้ | ทำไม | ต้องทำแทน |
|---|---|---|
| screenshot ของ `alert` / `confirm` / file dialog | เป็น native UI นอก DOM ทั้งหมด | OS-level capture (สูตรใน skill `netsuite-ui-qa-testing`) · ถ้าไม่ได้ทำ **ห้ามอ้างว่ามีภาพ** |
| screenshot ของ native `<select>` popup ที่กางอยู่ | popup เป็น layer นอก DOM บางรุ่นจับติดบางรุ่นไม่ติด | ท่า DOM `size=N` (`commands.md` §จับภาพ native `<select>`) — อยู่ใน DOM จึงจับติดทุกรุ่น |
| element-scoped `shot` ที่ต้องมี top-layer popup ติดมาด้วย | `<dialog>`/tooltip ที่ portal ออกไปอยู่คนละ layer | ถ่ายทั้ง viewport แล้ว crop ทีหลัง (`gotchas.md` §5) |
| สคริปต์หน้า `chrome://*` และ Chrome PDF viewer | สิทธิ์ของ renderer คนละชั้น | ตรวจ PDF **จากไฟล์** ไม่ใช่จากหน้าจอ (`pdf-reports.md`) |
| ตอบ dialog ที่เกิด**ก่อน** เราต่อ CDP | ไม่มีใครฟัง event ตอนนั้น | เปิดแท็บของตัวเองด้วย `newtab` แล้วค่อยทำงาน (golden rule #1) |
| ยืนยันว่า `setfile` แนบไฟล์สำเร็จผ่าน `input.files.length` | `DOM.setFileInputFiles` ใส่สำเร็จแต่ page JS เห็น 0 | ดู **ชื่อไฟล์ที่โผล่ใน UI** เป็นสัญญาณจริง (`cdp.md` ของ `netsuite-qa-browser`) |
| วัด contrast ของสี | lens `theme` เทียบสีแบบตรงตัวเท่านั้น | axe-core ผ่าน `a11y-layer.md` |
| จำลอง input ของ touch/gesture หลายนิ้ว | `Input` domain ครอบเท่าที่ `cdp.py` ใช้อยู่ | ยังไม่รองรับ — อย่ารายงานว่าเทสแล้ว |

## 2. สิ่งที่ CDP ทำได้ แต่ **ไม่ควรใช้ browser ทำ**

"CDP อย่างเดียว" คือกฎเลือก transport ของ **การขับ browser** ไม่ได้แปลว่าทุกอย่างต้องผ่าน browser

| งาน | ใช้อะไรแทน | ทำไม |
|---|---|---|
| อ่าน/เขียนข้อมูล GitHub | `gh` CLI | เร็วกว่า เสถียรกว่า ไม่พังตอน UI เปลี่ยน |
| อ่าน/เขียน record ของ NetSuite | OAuth 2.0 M2M + REST/SuiteQL (skill `netsuite-oauth2-connect`) | verify ผ่าน API เชื่อได้กว่าการอ่านหน้าจอ |
| query ฐานข้อมูล | sqlcl / driver ตรง | หน้าจอเป็นชั้นที่บางที่สุดของความจริง |
| ตั้งค่าที่มี API ให้ตั้ง | **API ชนะเสมอ** | หน้าจอเก็บไว้สำหรับค่าที่ไม่มี API เท่านั้น (`configure.md`) |

## 3. สิ่งที่ต้องอยู่ในโหมด `run` เท่านั้น

ไม่ใช่ "ทำไม่ได้" แต่ **ทำนอก `run` แล้วไม่มีผลจริง** — และทุกตัวจะเตือนลง stderr ให้เอง:

| คำสั่ง | ถ้าสั่งนอก `run` |
|---|---|
| `viewport` | ตั้งแล้วตายทันที = no-op ที่เคยพิมพ์ว่าสำเร็จ (`gotchas.md` §4) |
| `steady --tz` / `--locale` | รายงานใน `skipped` ไม่ถูกนับว่าตั้งแล้ว |
| `netlog on` | ไม่ได้เฝ้าอะไรเลย |
| `stub` | Fetch domain ตายพร้อมคำสั่ง |
| `lens netlog` | `UNVERIFIED` เพราะไม่มีใครเฝ้า |

## 4. เวลาเจอของใหม่ที่ CDP ทำไม่ได้

1. เขียนเพิ่มในตารางข้างบน **พร้อมทางออก** — รายการที่มีแต่ปัญหาไม่มีทางออกจะถูกข้ามในทางปฏิบัติ
2. ถ้าเป็นเรื่องที่ `cdp.py` ควรทำได้แต่ยังไม่ได้ทำ → เปิด issue ที่
   [`Teibto/teibto-dev-standards`](https://github.com/Teibto/teibto-dev-standards) อย่าเขียน
   driver ตัวที่สองในสกิลนี้
3. ถ้ามันทำให้ผลตรวจไม่น่าเชื่อถือ → ต้องมีทางคืนค่า `UNVERIFIED` ในโค้ด ไม่ใช่แค่บันทึกในเอกสาร
