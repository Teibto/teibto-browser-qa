# Visual regression — baseline ที่ review ได้

`cdp.py diff` เปรียบเทียบภาพขนาดเท่ากันและคืน `SAME`, `DIFFERENT` หรือ `SIZE-MISMATCH` พร้อมจำนวน
pixel ที่ต่าง. ใช้ layer นี้เมื่อ layout/style เป็น Acceptance Criterion; อย่าใช้แทน functional
assertion.

## จับภาพให้ deterministic

1. ใช้ viewport, device scale, theme, locale และ test data เดียวกับ baseline.
2. รอ page-specific observable state; `load` อย่างเดียวไม่ยืนยันว่า async UI พร้อม.
3. ใช้ `steady` หยุด animation/transition ก่อนถ่าย. ถ้าต้องคง viewport/timezone ข้ามหลายคำสั่ง ให้
   ทำใน `run` เดียว.
4. ถ่ายภาพด้วย path และ selector เดิม แล้วตรวจว่าไฟล์ถูกสร้างจริง.

```bash
AB steady
AB shot current.png "#main" --vw=1280 --vh=900 --dsf=1
AB diff baseline.png current.png diff.png --threshold=30
```

`--threshold` คือผลรวมความต่าง RGB ต่อ pixel ที่ driver ยอมให้เป็น rendering noise ไม่ใช่เปอร์เซ็นต์
ของ pixel ทั้งภาพ. ถ้ามี pixel เกิน threshold แม้หนึ่งจุด คำสั่งคืน `DIFFERENT` และ exit 1.

## Dynamic content

`mask_regions` และ `diff_threshold` ยังไม่ใช่ executable `flow.yaml` fields. อย่าใส่ลง flow เพราะ
schema จะปฏิเสธ. ถ้าวันที่, session id หรือข้อความ dynamic ไม่ใช่สิ่งที่ต้องตรวจ ให้ทำ test data ให้
คงที่ก่อน. เมื่อทำไม่ได้ ให้ mask DOM แบบ explicit และเหมือนกันทั้ง baseline/current ก่อน `shot`,
พร้อมบันทึก selector ที่ mask ในรายงาน:

```bash
AB eval "(function(){for(const s of ['.timestamp','[data-test=session-id]']){
  for(const e of document.querySelectorAll(s)){e.style.visibility='hidden';}}
  return 'masked';})()"
AB shot current.png "#main" --vw=1280 --vh=900 --dsf=1
```

ห้ามเพิ่ม color threshold เพื่อกลบ region ที่เปลี่ยนเอง เพราะจะลด sensitivity ทั้งภาพ.

## Baseline approval

Baseline คือ UI ที่อนุมัติแล้วและต้อง version กับ feature:

- เปลี่ยนเมื่อ UI เปลี่ยนโดยตั้งใจและมี ticket/เหตุผลที่ review ได้เท่านั้น;
- ห้าม update เพื่อทำให้ regression เขียว;
- reviewer ต้องดู `diff.png`, ภาพก่อน/หลัง และรายการ masked selectors;
- `SIZE-MISMATCH` คือ setup/viewport mismatch จนกว่าจะพิสูจน์ว่าเป็น layout regression;
- ถ้า environment/font/Chrome ต่างจาก baseline ให้สร้าง baseline ชุดใหม่หรือคืน `UNVERIFIED`.

เมื่อ diff เป็นสีแดง ให้จำแนกเป็น dynamic region ที่ mask ไม่ครบ, intentional change ที่มี ticket,
หรือ regression ที่ต้องเปิด bug. การตัดสินนี้อยู่นอก runner และต้องบันทึกใน `qa-report.md`.
