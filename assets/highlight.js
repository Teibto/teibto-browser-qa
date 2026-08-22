// highlight.js — inject กรอบเรืองแสงชี้จุดคลิกลงบนหน้า ก่อน screenshot
// ใช้กับ cdp.py:  AB eval "<เนื้อ IIFE ด้านล่าง>('SEL','#ff2d55')"
// 🔴 #ff2d55 = จุดที่ต้องคลิก   🟢 #16a34a = จุดสังเกตผลลัพธ์
// หมายเหตุ: ห้ามใส่ข้อความไทยในป้ายที่ inject (headless ไม่มีฟอนต์ไทย → เพี้ยนเป็นกล่อง)
//          ใส่แค่กรอบ; ข้อความไทยไว้ใน HTML/เอกสารแทน.

// --- เวอร์ชันเต็ม (อ่านง่าย) ---
function highlight(selector, color) {
  const el = document.querySelector(selector);
  if (!el) return 'NOEL';
  el.scrollIntoView({ block: 'center' });          // กัน element ใต้ fold (สำคัญ!)
  el.style.outline = '4px solid ' + color;
  el.style.outlineOffset = '3px';
  el.style.boxShadow = '0 0 0 6px ' + color + '55, 0 0 22px ' + color;  // เรืองแสง
  el.style.borderRadius = '8px';
  return 'HL_OK';
}

// --- one-liner สำหรับวางใน AB eval "..." ---
// (function(s,c){var e=document.querySelector(s);if(!e)return'NOEL';e.scrollIntoView({block:'center'});e.style.outline='4px solid '+c;e.style.outlineOffset='3px';e.style.boxShadow='0 0 0 6px '+c+'55, 0 0 22px '+c;e.style.borderRadius='8px';return'HL_OK';})('SEL','#ff2d55')

// ตัวอย่าง flow เก็บภาพไฮไลต์ แล้วใช้ trusted click:
//   HL="(function(s,c){...})"                       # เก็บ snippet ไว้ในตัวแปร bash
//   AB eval "$HL('[data-test=login-button]','#ff2d55')"
//   AB shot shots/01-login.png
//   AB click "[data-test=login-button]"
//   AB wait "location.pathname==='/home'" 20 0.05   # assert observable outcome
