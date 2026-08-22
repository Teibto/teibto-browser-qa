// pointer.js — inject วงแหวน "pointer" เรืองแสง บอกตำแหน่งจุดที่กำลัง focus/คลิก
// ชี้จุดโฟกัส/จุดคลิกในภาพนิ่ง — CDP ไม่มี cursor จริง จึง inject DOM overlay แทน
//   → ไม่มี OS cursor ให้ screencast จับ → ดูไม่ออกว่าทำงานตรงไหน.
//   overlay เป็น DOM จึง "ถูก render = ถูกอัดติด".
// ใช้กับ cdp.py:  AB eval "<เนื้อ IIFE ด้านล่าง>('SEL')"
//
// กฎใช้งาน (สำคัญ): เรียก point(sel) "ก่อน" ทุก action ด้วย selector เดียวกับที่จะ act
//   → wait ~500-650ms (ให้วงแหวนเลื่อน+pulse เห็นใน video) → ค่อย fill/click.
// ทำไม robust:
//   - idempotent: สร้าง ring ถ้ายังไม่มี → "pointer หายตอน navigate" หายเอง (call แรกหลัง nav สร้างใหม่)
//   - วางตำแหน่งด้วย getBoundingClientRect (ไม่พึ่ง clientX/Y ของ JS click ที่เป็น 0,0)
//   - pointer-events:none (ไม่บัง click), position:fixed + z-index สูงสุด (ตรงกับพิกัด viewport ของ rect)
// iframe (NetSuite): overlay inject ในเอกสารที่รัน → ต้อง `frame "#sel"` เข้า context ก่อน eval.
// verify 1 เฟรมก่อนอัดจริง: eval point(sel) → screenshot → เช็ควงแหวนลงกลาง target (กัน bug quoting).

// --- เวอร์ชันเต็ม (อ่านง่าย) ---
function point(selector) {
  let p = document.getElementById('__ptr');
  if (!p) {
    p = document.createElement('div');
    p.id = '__ptr';
    p.style.cssText = 'position:fixed;z-index:2147483647;width:26px;height:26px;'
      + 'margin:-13px 0 0 -13px;border:3px solid #ff2d55;border-radius:50%;'
      + 'background:rgba(255,45,85,.2);box-shadow:0 0 0 5px rgba(255,45,85,.22),0 0 16px #ff2d55;'
      + 'pointer-events:none;transition:left .45s ease,top .45s ease;left:50%;top:50%';
    document.body.appendChild(p);
  }
  const e = document.querySelector(selector);
  if (!e) return 'noel:' + selector;
  e.scrollIntoView({ block: 'center' });           // กัน element ใต้ fold + ให้ rect ถูกต้อง same-tick
  const r = e.getBoundingClientRect();
  p.style.left = (r.left + r.width / 2) + 'px';
  p.style.top = (r.top + r.height / 2) + 'px';
  p.animate([{ transform: 'scale(1.8)' }, { transform: 'scale(1)' }], { duration: 450 }); // pulse
  return 'ok';
}

// --- one-liner สำหรับวางใน AB eval "..." (แทน SEL ด้วย selector) ---
// (function(s){var p=document.getElementById('__ptr');if(!p){p=document.createElement('div');p.id='__ptr';p.style.cssText='position:fixed;z-index:2147483647;width:26px;height:26px;margin:-13px 0 0 -13px;border:3px solid #ff2d55;border-radius:50%;background:rgba(255,45,85,.2);box-shadow:0 0 0 5px rgba(255,45,85,.22),0 0 16px #ff2d55;pointer-events:none;transition:left .45s ease,top .45s ease;left:50%;top:50%';document.body.appendChild(p);}var e=document.querySelector(s);if(!e)return 'noel:'+s;e.scrollIntoView({block:'center'});var r=e.getBoundingClientRect();p.style.left=(r.left+r.width/2)+'px';p.style.top=(r.top+r.height/2)+'px';p.animate([{transform:'scale(1.8)'},{transform:'scale(1)'}],{duration:450});return 'ok';})('SEL')

// ตัวอย่าง headed inspection ที่มี pointer — point ก่อน → รอ animation แบบ cosmetic → act:
//   PT="(function(s){...})"                              # เก็บ snippet ไว้ในตัวแปร
//   ใช้กับ headed inspection หรือภาพนิ่ง; video/live-view orchestration อยู่นอก scope ของ repo นี้
//   ใช้ชี้จุดก่อน shot แต่ละ step แทน:
//   AB eval "$PT('#user-name')" && sleep 0.65 && AB fill '#user-name' 'standard_user'
//   AB eval "$PT('#login-button')" && sleep 0.65 && AB click '#login-button'
//   AB wait "location.pathname === '/inventory.html'" 20 0.05
//   ...
//   AB shot guide/step-03.png                            # ภาพนิ่งที่มีวงชี้จุดคลิก
