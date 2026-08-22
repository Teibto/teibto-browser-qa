# a11y layer — จับ bug ที่ functional test มองไม่เห็น (token-safe)

accessibility เป็น bug ประเภทที่ happy-path smoke ไม่มีทางเจอ: contrast ต่ำ, label ไม่ผูก input,
focus order พัง, ARIA ผิด. ทั้งหมดนี้ **✅ browser-verifiable** — ยิงผ่าน browser ได้จริง
(ต่างจาก race/governance ที่ ⚠️ code-only). กติกาเดียวที่ต้องระวัง: **ห้าม dump node เต็ม**
กลับ context — axe คืนผลยาวมาก ต้อง reduce ให้เหลือตัวเลข + top N ก่อนเข้า context.

---

## 1. Inject axe-core แล้วรัน (ผ่าน eval)

axe-core เป็น JS ตัวเดียว inject ได้ผ่าน `eval`. bundle local (ไฟล์ในเครื่อง) หรือ CDN ก็ได้ —
ถ้าเครื่อง/หน้ามี CSP บล็อก CDN ให้อ่านไฟล์ local มา inject เป็น string.

```
# 1) โหลด axe เข้าไปในหน้า (ถ้ายังไม่มี window.axe)
AB eval "if(!window.axe){var s=document.createElement('script');
  s.src='https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.0/axe.min.js';
  document.head.appendChild(s);} 'loading'"
AB wait "window.axe && typeof axe.run==='function'" 20 0.05
```

## 2. รัน axe แล้ว reduce ให้ token-safe (สำคัญสุด)

`axe.run()` คืน object ใหญ่ (violations แต่ละตัวมี nodes[] + html + DOM). **ห้ามคืนทั้งก้อน** —
reduce ในหน้าเว็บก่อน return ให้เหลือแค่ **count + top N by impact**:

```
AB eval "axe.run(document,{resultTypes:['violations']}).then(function(r){
  var order={critical:0,serious:1,moderate:2,minor:3};
  var top=r.violations.slice().sort(function(a,b){return order[a.impact]-order[b.impact];})
    .slice(0,8).map(function(v){return {id:v.id, impact:v.impact, count:v.nodes.length};});
  return JSON.stringify({total:r.violations.length,
    by_impact:{critical:0,serious:0,moderate:0,minor:0,
      ...r.violations.reduce(function(a,v){a[v.impact]=(a[v.impact]||0)+1;return a;},{})},
    top:top});
})"
```

output ที่ได้ (สั้น, เข้า context ได้):
```json
{"total":5,"by_impact":{"critical":1,"serious":2,"moderate":2,"minor":0},
 "top":[{"id":"color-contrast","impact":"serious","count":7},
        {"id":"label","impact":"critical","count":1}]}
```

**ห้ามทำ:** คืน `r.violations` ทั้งก้อน, คืน `nodes[].html`, คืน `nodes[].target` ทั้งหมด.
ต้องการรายละเอียด node ของ 1 issue ค่อย query เจาะจงทีหลัง (`...filter(v=>v.id==='label')...target`)
แล้วคืนแค่ selector สั้นๆ ไม่ใช่ html.

---

## 3. สิ่งที่ a11y layer ครอบ

- **ARIA** — role/attribute ผิด, required attr หาย (`aria-required-attr`, `aria-roles`)
- **Contrast** — ตัวอักษร/พื้นหลัง contrast ต่ำกว่า WCAG (`color-contrast`)
- **Label ↔ input binding** — input ไม่มี label ที่ผูก (`label`, `form-field-multiple-labels`)
- **Keyboard / focus order** — focus ตกหล่น, tabindex ผิด, focus trap (`tabindex`, `focus-order-semantics`)

focus order ที่ axe จับไม่หมด ตรวจเสริมด้วยการไล่ `press Tab` แล้วอ่าน `eval
"document.activeElement.outerHTML.slice(0,80)"` ทีละครั้ง — คืนแค่ selector/tag สั้นๆ.

---

## 4. ต่อเข้ากับ flow ปัจจุบัน

`a11y` ยังไม่ใช่ field ของ executable flow. ให้ runner เดินถึง state เป้าหมายก่อน แล้วรัน §1–2 เป็น
ขั้นตรวจแยกบน `TGT_ID` เดิมและแนบ JSON ย่อเข้า `qa-report.md`. ถ้าทีมกำหนด policy ว่า
`critical`/`serious` block release ให้บันทึกเกณฑ์นั้นใน Acceptance Criteria หรือ coverage manifest;
อย่าฝัง field ที่ schema จะปฏิเสธลง `flow.yaml`.
