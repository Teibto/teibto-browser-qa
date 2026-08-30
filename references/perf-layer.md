# Performance layer — วัด action ถึง observable outcome จริง

Performance budget ที่ใช้ตัดสิน QA ต้องครอบเวลาที่ผู้ใช้รอผลธุรกิจ ไม่ใช่แค่เวลาที่ driver ส่ง click.
คืนเฉพาะ milliseconds + budget verdict; ห้าม dump Navigation/Resource Timing ทั้งก้อน.

## Executable budget ใน flow

ใส่ `perf_budget_ms` ที่ step ซึ่งมี observable wait/assert ครบ:

```yaml
- intent: Save and wait for confirmation
  action: click
  target: "#btn_save"
  wait: "fn:document.querySelector('#status')?.textContent==='saved'"
  assert: {target: "#status", contains: "saved"}
  perf_budget_ms: 3000
```

Clock เริ่มก่อน action และหยุดหลัง explicit wait + assertion:

```text
included: action + automatic fill verification + explicit wait + assertion
excluded: session startup + screenshot capture + scenario console check
```

การแยกนี้สำคัญ: screenshot อาจช้าตามขนาดหน้า/เครื่อง แต่ไม่ใช่เวลาที่ผู้ใช้รอ Save. ถ้าเกิน budget
runner คืน `PERF_BUDGET_EXCEEDED`, verdict `FAIL`, และเก็บ failure screenshot ตาม capture policy.

หลักฐานอยู่สามที่:

- `step_done.performance` = `outcome_ms`, `budget_ms`, `verdict`;
- `run_done.performance_budgets` = `passed`, `evaluated`, `total`;
- `qa-report.md` = บรรทัด `outcome: 842.123ms / budget 1500ms → PASS`.

`step_done.duration_ms` ยังรวม capture จึงอาจมากกว่า `performance.outcome_ms`; อย่าใช้สองค่านี้แทนกัน.

## Navigation timing สำหรับ diagnosis

หลัง `nav --until=load` อ่าน Navigation Timing API แบบย่อได้:

```bash
AB eval "(function(){var n=performance.getEntriesByType('navigation')[0]||{};
  return JSON.stringify({ttfb_ms:Math.round(n.responseStart||0),
    dom_ms:Math.round(n.domContentLoadedEventEnd||0),
    load_ms:Math.round(n.loadEventEnd||0)});})()"
```

`load_ms` เป็น browser lifecycle ไม่ใช่หลักฐานว่าข้อมูล async พร้อม. Budget ใน flow จึงควรผูกกับ
status text, row count, URL, enabled state หรือสัญญาณธุรกิจที่ Acceptance Criteria ระบุ.

งาน ad-hoc ที่ไม่ navigate ใช้ performance mark ได้ แต่ mark จะหายเมื่อเปลี่ยน document:

```bash
AB eval "performance.clearMarks('qa_start');performance.mark('qa_start');'marked'"
AB click "#save"
AB wait "document.querySelector('#status')?.textContent==='saved'" 20 0.05
AB eval "performance.mark('qa_end');performance.measure('qa_action','qa_start','qa_end');
  JSON.stringify({outcome_ms:Math.round(performance.getEntriesByName('qa_action').at(-1).duration)})"
```

ถ้า action navigate ให้ใช้ `perf_budget_ms` ของ runner; clock ฝั่ง runner ไม่ตายพร้อม document.

## Fast path สำหรับ NetSuite

สำหรับ Suitelet/non-record page ให้ลด overhead โดยยังเก็บหลักฐานที่เชื่อได้:

1. ใช้ runner/driver ที่ ready เฉพาะหลัง target ที่ pin เป็น foreground และ
   `document.visibilityState=visible`; ห้ามใช้การถ่าย screenshot เป็น activation side effect และห้าม
   รับ run ที่ hidden เป็น baseline เพราะ Chrome throttle timer ของ NetSuite ได้.
2. ใช้ persistent `--user-data-dir` เพื่อเก็บ login/trusted-device token แต่แยกหนึ่ง profile + port
   ต่อ job; ห้ามรันขนานด้วย profile เดียวเพราะ cookie/session ชนกัน.
3. รวม scenarios ที่เกี่ยวข้องไว้ใน flow เดียว เพื่อ reuse `cdp.py session --jsonl` process/WebSocket
   เดียว; อย่าเรียก driver process ใหม่ทุก step.
4. ใช้ page-specific observable `wait: "fn:..."`; หลีกเลี่ยง fixed sleep และชื่อ compatibility
   `networkidle` เมื่อผลที่ต้องการเป็น AJAX/Oracle JET state.
5. ใช้ `doc: false` ใน performance/adversarial pass และไม่ต้องใส่ `capture:false`: step ที่ผ่านจะไม่ถ่าย
   แต่ failure ยังได้ screenshot อัตโนมัติ.
6. รัน agent ด้วย `--stdout summary`; JSONL เต็มยังอยู่ใน artifact โดยไม่ไหลเข้า context.
7. ใช้ selector/get/count แบบแคบ; ห้าม whole-page HTML หรือ a11y dump.

ตัวอย่าง:

```powershell
'{"base_url":"https://..."}' |
  py scripts/flow-runner.py --flow qa/suitelet/flow.yaml --out runs/suitelet-perf `
    --vars-json - --target-id $env:TGT_ID --stdout summary
```

NetSuite record-form QA ยังเป็นขอบเขตของ `netsuite-ui-qa-testing`; ใช้หลัก profile isolation,
observable outcome และ token-safe output เดียวกัน แต่ใช้ pipeline ของ skill นั้น.

## ตีความตัวเลข

- รอบเดียวเหมาะกับ diagnosis และ budget ต่อ run; claim regression ควรรันซ้ำแล้วรายงาน median/p95.
- รายงาน Chrome, driver revision, จำนวนรอบ และ fixture/application delay ที่ตั้งใจไว้.
- เปรียบเทียบ host เดียวกันเมื่อใช้ absolute milliseconds; CI ข้ามเครื่องควรใช้ budget ที่เผื่อ variance.
- ห้ามอ้าง `driver_ms` อย่างเดียวว่า Save เร็ว เพราะ application latency อยู่ใน wait wall time.
