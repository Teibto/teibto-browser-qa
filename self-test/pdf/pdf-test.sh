#!/usr/bin/env bash
# PDF-pagination self-test — verifies the pdf-reports.md causal claims mechanically.
#   bash self-test/pdf/pdf-test.sh
# Needs: Chrome (เปิดค้างไว้ที่ CDP_PORT), websocket-client, pymupdf, network (paged.js CDN).
# Verified: Chrome 150 (2026-07-14) · transport ย้ายเป็น cdp.py 2026-08-02
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
D="$(cygpath -m "$HERE" 2>/dev/null || echo "$HERE")"
CDP="${NS_CDP:-$HOME/.claude/skills/netsuite-qa-browser/references/cdp.py}"
PY=""; for c in py python3 python; do "$c" -c 'import websocket' >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || { echo "SKIP: ไม่มี python ที่ import websocket ได้"; exit 0; }
curl -sf "http://127.0.0.1:${CDP_PORT:-9333}/json/version" >/dev/null 2>&1   || { echo "SKIP: ไม่มี Chrome ตอบที่ CDP_PORT=${CDP_PORT:-9333}"; exit 0; }
ab(){ "$PY" "$CDP" "$@" 2>&1; }

render(){ # render <name> <paged:yes|no>
  local name="$1" paged="$2"
  ab nav "file:///${D}/${name}.html" 2 >/dev/null
  if [ "$paged" = yes ]; then
    local c=0 tries=0
    while [ "$tries" -lt 40 ]; do
      c=$(ab get count ".pagedjs_page" 2>/dev/null | grep -oE '[0-9]+' | head -1)
      [ -n "${c:-}" ] && [ "$c" -gt 0 ] 2>/dev/null && break
      sleep 0.5; tries=$((tries+1))
    done
    echo "  ${name}: .pagedjs_page=${c:-0}"
  else
    ab wait "document.readyState==='complete'" 15 >/dev/null 2>&1 || true
  fi
  ab pdf "${D}/out-${name}.pdf" >/dev/null
}

echo "=== render ==="
render t1-naive no
render t2-good  yes
render t2-bad   yes

echo "=== verdict (pymupdf) ==="
python "${HERE}/pdf_inspect.py" "${HERE}"
rc=$?
# tidy generated PDFs (keep the html + scripts under version control, drop artifacts)
rm -f "${HERE}"/out-*.pdf "${HERE}"/out-*.png
exit $rc
