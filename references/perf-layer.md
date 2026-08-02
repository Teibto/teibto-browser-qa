# perf layer — วัดเวลา save/load จริง เทียบ budget (token-safe)

เพิ่มเลเยอร์ที่ผูกกับงาน optimize ที่มีอยู่ (เช่น "save ควร < 3s"). แนวคิด: วัดเวลาจริงผ่าน
browser timing API แล้ว **คืนแค่ตัวเลข ms + pass/fail เทียบ budget** — สั้น token-safe
ไม่ dump timing entry ทั้งก้อน.

---

## 1. Navigation / load timing (หน้าโหลด)

ใช้ Navigation Timing API — คืนแค่ตัวเลขที่ต้องการ:
```
AB eval "(function(){var n=performance.getEntriesByType('navigation')[0]||{};
  return JSON.stringify({ttfb:Math.round(n.responseStart),
    dom:Math.round(n.domContentLoadedEventEnd),
    load:Math.round(n.loadEventEnd)});})()" --json
# -> {"ttfb":210,"dom":880,"load":1450}
```
ไม่มีคำสั่ง `vitals` สำเร็จรูป — อ่านค่าเองจาก `performance` API ผ่าน `eval` (ตัวอย่างข้างล่าง)
(framework-agnostic, ใช้กับ APEX ได้). ทั้งคู่คืนตัวเลขสั้น ไม่ต้อง reduce มาก.

---

## 2. Save-time pattern (NetSuite form) — สำคัญ

save duration ของ NetSuite form วัดจาก **mark ก่อน submit → measure หลัง confirmation/redirect**.
ใช้ `performance.mark` + `performance.measure` (custom mark) เพราะ Navigation Timing วัดแค่ page load
ไม่ครอบ round-trip ของ save:

```
# 1) ก่อนกด Save: ตั้ง mark
AB eval "performance.mark('save_start'); 'marked'"

# 2) กด Save (ปุ่มมักอยู่ท้ายฟอร์ม → scrollintoview ก่อน, gotchas §1)
AB click  # (scrollIntoView อยู่ในตัวแล้ว) "#btn_save" && AB eval "document.querySelector('#btn_save').click()"

# 3) รอ "save เสร็จจริง" — ไม่ใช่ ✓Done: รอ confirmation/redirect (gotchas §2)
AB wait --fn "window.jQuery ? jQuery.active===0 : true"   # NetSuite async settle
#   (หรือรอ url เปลี่ยนเข้า record view / รอ banner 'saved')

# 4) measure ช่วง save แล้วคืนแค่ ms
AB eval "performance.mark('save_end');
  performance.measure('save','save_start','save_end');
  var m=performance.getEntriesByName('save')[0];
  JSON.stringify({save_ms:Math.round(m.duration)});" --json
# -> {"save_ms":2360}
```

**จุดวัดต้องเป็น "save เสร็จจริง"** — ผูกกับ signal ที่พิสูจน์ผล (jQuery.active===0 / redirect /
banner) ตาม gotchas §2. อย่า mark_end ตอน `✓Done` ของ click เพราะยังไม่เสร็จ = ตัวเลขหลอก.

---

## 3. เทียบ budget

```yaml
scenarios:
  - id: SC-001
    perf_budget:              # default: null (ไม่วัด)
      save_ms: 3000           # เพดานเวลา save (ms)
```
เกณฑ์: `save_ms` วัดได้ > budget → **FAIL (report, surface)**; ≤ budget → pass. บันทึกใน qa-report
แค่บรรทัดเดียว: `save: 2360ms / budget 3000ms → PASS`. ผูกกลับงาน optimize ได้ตรงๆ.

**Acceptance:** perf layer วัด save duration ได้จริงในตัวอย่าง form (§2); output = ms + pass/fail
(§3, token-safe); optional (flow เดิมไม่มี perf_budget ไม่พัง).
