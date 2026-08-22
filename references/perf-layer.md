# Performance layer — วัดเวลาโดยไม่ซ่อน application latency

เก็บเฉพาะตัวเลขที่ตอบ budget ของ scenario. ห้าม dump Navigation/Resource Timing ทั้งก้อน และห้าม
เอา driver duration ไปอ้างเป็นเวลาที่ผู้ใช้รอ.

## Navigation timing

หลัง `nav --until=load` อ่าน Navigation Timing API แบบย่อ:

```bash
AB eval "(function(){var n=performance.getEntriesByType('navigation')[0]||{};
  return JSON.stringify({ttfb_ms:Math.round(n.responseStart||0),
    dom_ms:Math.round(n.domContentLoadedEventEnd||0),
    load_ms:Math.round(n.loadEventEnd||0)});})()"
```

`load_ms` เป็น browser lifecycle ไม่ใช่หลักฐานว่าข้อมูลของแอปพร้อม. ถ้าหน้ามี async component ให้
รอและวัด observable outcome ที่ Acceptance Criteria ระบุ เช่น status text, row count หรือ enabled
state.

## Action-to-outcome timing

สำหรับ flow YAML ใช้ `run-log.jsonl` เป็นแหล่งหลัก:

- `action.driver_ms` = เวลาที่ driver ใช้ส่ง trusted input;
- `wait.wall_ms` = เวลาที่ application ใช้จน observable condition เป็นจริง;
- `step.total_ms` = runner wall time รวม assertion/capture ที่เปิดใช้;
- `attempts` และ `failing_phase` ใช้แยก transport retry จาก application failure.

Runner protocol v2 ตัดเฉพาะ fixed input settle และย้ายเวลาที่ต้องรอจริงไปอยู่ใน bounded outcome
wait. อย่าสรุปว่า action เร็วขึ้นจาก `driver_ms` อย่างเดียว.

งาน ad-hoc ที่อยู่ใน document เดิมใช้ mark ก่อน trusted action แล้ววัดหลัง bounded wait:

```bash
AB eval "performance.clearMarks('qa_start');performance.mark('qa_start');'marked'"
AB click "#save"
AB wait "document.querySelector('#status')?.textContent==='saved'" 20 0.05
AB eval "performance.mark('qa_end');performance.measure('qa_action','qa_start','qa_end');
  JSON.stringify({action_to_outcome_ms:Math.round(performance.getEntriesByName('qa_action').at(-1).duration)})"
```

ถ้า action navigate ไป document ใหม่ performance mark เดิมจะหาย ให้ใช้ runner phase telemetry หรือ
Navigation Timing ของ document ใหม่แทน.

## Budget และรายงาน

`perf_budget` ยังไม่ใช่ executable `flow.yaml` field. เก็บ budget ใน Acceptance Criteria หรือ
coverage manifest แล้วเปรียบเทียบกับค่าที่วัดได้ในรายงาน เช่น:

```text
checkout confirmation: 842 ms / budget 1,500 ms -> PASS
source: step SC-CHECKOUT-01 wait.wall_ms
```

รายงาน environment, จำนวนรอบ และ median/p95 เมื่อใช้ตัวเลขตัดสิน release. รอบเดียวเหมาะกับ diagnosis
แต่ไม่พอสำหรับ claim เรื่อง performance regression.
