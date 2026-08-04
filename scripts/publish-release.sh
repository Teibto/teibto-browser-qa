#!/usr/bin/env bash
# publish-release.sh — สร้าง GitHub Release ของ tag หนึ่งตัว โดยดึงเนื้อจาก CHANGELOG.md (#113)
#
# ทำไมต้องมี: `git push origin <tag>` สร้าง **tag** เท่านั้น · หน้า Releases แสดงเฉพาะ
# **Release object** ซึ่งต้องสร้างแยก — เป็นงานมือที่ไม่มีอะไรสั่งให้ทำ จึงหลุดเงียบข้าม release
# มาแล้ว 20 tag (หน้า Releases ค้างที่ v0.33.0 ทั้งที่ tag ไปถึง v0.39.0)
#
# ใช้:
#   bash scripts/publish-release.sh v0.39.0            # สร้างจริง (ข้ามถ้ามีอยู่แล้ว)
#   bash scripts/publish-release.sh v0.39.0 --dry-run  # พิมพ์ body ที่จะใช้ ไม่แตะ GitHub
#
# ★ idempotent โดยเจตนา — CI เรียกทุกครั้งที่ push tag และ backfill ก็ใช้สคริปต์ตัวเดียวกัน
#   รันซ้ำต้องไม่พังและต้องไม่เขียนทับของเดิม
# ★ ต้องมี gh ที่ auth แล้ว (local) หรือ GH_TOKEN ใน env (CI)
# @author Wichit Wongta @since 2026-08-02
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHANGELOG="${ROOT}/CHANGELOG.md"

TAG=""
DRY=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    v*) TAG="$a" ;;
    *) echo "FATAL: unknown arg '$a' (ใช้: <vX.Y.Z> [--dry-run])" >&2; exit 2 ;;
  esac
done
[ -n "${TAG}" ] || { echo "FATAL: ต้องระบุ tag เช่น v0.39.0" >&2; exit 2; }
[ -f "${CHANGELOG}" ] || { echo "FATAL: ไม่พบ ${CHANGELOG}" >&2; exit 1; }

# เลือก interpreter จากการ **รันจริง** — Windows วาง App Execution Alias `python3` ที่มีอยู่ใน PATH
# แต่รันแล้วเด้ง Microsoft Store + exit 49 · `command -v` จึงหลอกได้ (บทเรียน #107)
PY=""
for cand in python3 python py; do
  if "$cand" -c 'import sys' >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "${PY}" ] || { echo "FATAL: ต้องมี python3 (หรือ python) ที่รันได้จริงใน PATH" >&2; exit 1; }
export PYTHONIOENCODING=utf-8

# ---- ดึงเนื้อของเวอร์ชันนี้จาก CHANGELOG ----
# ตัดตั้งแต่บรรทัด `## [X.Y.Z]` จนถึงก่อน `## [` ตัวถัดไป — **ต้องหยุดที่หัวข้อถัดไป**
# ไม่งั้นจะกิน release เก่าทั้งไฟล์มาเป็น body (เทส T2 กันข้อนี้)
BODY="$(VERSION="${TAG#v}" "${PY}" - "${CHANGELOG}" <<'PYEOF'
import io, os, re, sys
ver = os.environ["VERSION"]
text = io.open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"^## \[%s\][^\n]*\n(.*?)(?=^## \[|\Z)" % re.escape(ver), text, re.S | re.M)
sys.stdout.write(m.group(1).strip() if m else "")
PYEOF
)"

if [ -z "${BODY}" ]; then
  echo "FATAL: ไม่พบหัวข้อ '## [${TAG#v}]' ใน CHANGELOG.md — เพิ่ม entry ก่อนแล้วค่อย tag" >&2
  exit 1
fi

# ---- badge Latest ต้องอยู่กับเลขเวอร์ชันสูงสุด ไม่ใช่ตัวที่สร้างล่าสุด ----
# `gh release create` default เป็น make_latest=legacy ซึ่ง GitHub ตีความว่า "Release ที่สร้าง
# ล่าสุดตามเวลา" → backfill tag เก่าไปแย่ง badge จากเวอร์ชันปัจจุบัน (เจอจริงตอน backfill #113:
# v0.39.0 แย่ง Latest จาก v0.40.0) · จึงระบุให้ชัดเจนทุกครั้ง ไม่ปล่อยให้ลำดับการรันตัดสิน
# ★ `git -C "${ROOT}"` ไม่ใช่ git เฉย ๆ — สคริปต์อ่าน CHANGELOG จาก ROOT อยู่แล้ว tag ก็ต้องมาจาก
#   repo เดียวกัน ไม่ใช่จาก cwd ที่บังเอิญเรียก (ไม่งั้นเรียกข้าม repo แล้วได้ผลมั่ว)
HIGHEST="$(git -C "${ROOT}" tag --list 'v*' --sort=v:refname | tail -1)"
LATEST_FLAG="--latest=false"
[ "${TAG}" = "${HIGHEST}" ] && LATEST_FLAG="--latest"

if [ "${DRY}" -eq 1 ]; then
  printf '=== %s (%s · สูงสุดใน repo = %s) ===\n%s\n' \
    "${TAG}" "${LATEST_FLAG}" "${HIGHEST:-<ไม่มี tag>}" "${BODY}"
  exit 0
fi

# ---- สร้างจริง ----
command -v gh >/dev/null 2>&1 || { echo "FATAL: ต้องมี gh CLI" >&2; exit 1; }

if gh release view "${TAG}" >/dev/null 2>&1; then
  echo "SKIP: Release ${TAG} มีอยู่แล้ว — ไม่เขียนทับ"
  exit 0
fi
if ! git -C "${ROOT}" rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
  echo "FATAL: ยังไม่มี tag ${TAG} ใน repo — tag ก่อนแล้วค่อยสั่ง" >&2
  exit 1
fi

printf '%s\n' "${BODY}" | gh release create "${TAG}" --title "${TAG}" "${LATEST_FLAG}" --notes-file -
echo "CREATED: Release ${TAG} (${LATEST_FLAG})"
