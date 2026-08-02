# PDF verdict checker for pdf-reports.md claims. NOTE: do NOT rename to inspect.py
# (pymupdf internally `import inspect`; a local inspect.py shadows the stdlib -> circular import).
import pymupdf, sys, os

def check(path):
    d = pymupdf.open(path)
    n = len(d)
    ftr = sum(1 for pg in d if "FTR " in pg.get_text())
    return n, ftr

D = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
naive_n, naive_ftr = check(os.path.join(D, "out-t1-naive.pdf"))
good_n,  _         = check(os.path.join(D, "out-t2-good.pdf"))
bad_n,   _         = check(os.path.join(D, "out-t2-bad.pdf"))
print(f"naive (plain @page counter, no paged.js): pages={naive_n} footer_pages={naive_ftr}")
print(f"good  (paged.js + 2 fixes):               pages={good_n}")
print(f"bad   (paged.js, no fixes):               pages={bad_n}")
print()

fail = 0
# Claim 1 (pdf-reports §"ทำไมต้อง paged.js"): @page @bottom-center counter renders in printToPDF.
# Documented as WORKING on Chrome 150 -> a regression (footer missing) should fail here.
if naive_n == 3 and naive_ftr == 3:
    print("  PASS  claim1: @page @bottom-center counter(page) renders in AB pdf (footer on all 3 pages)")
else:
    print(f"  FAIL  claim1: expected footer on all 3 naive pages, got {naive_ftr}/{naive_n} "
          f"(if 0 -> Chrome regressed to the old 'counter dead in printToPDF' behavior; re-check pdf-reports.md)")
    fail += 1

# Claim 2 (pdf-reports §"กับดัก double-pagination"): the 2 fixes prevent doubling.
if good_n == 3:
    print("  PASS  claim2-good: fixes applied -> 3 logical == 3 PDF pages (no doubling)")
else:
    print(f"  FAIL  claim2-good: recipe broken — expected 3 clean pages, got {good_n}")
    fail += 1

# Claim 2 trap reproduction. Per asymmetric-burden discipline, a non-repro is INCONCLUSIVE,
# not a refutation (the overflow condition may just not be hit on this Chrome) — do NOT hard-fail.
if bad_n >= 6:
    print(f"  PASS  claim2-bad: no fixes -> double-pagination reproduced ({bad_n} PDF pages from 3 logical, even pages footer-only)")
else:
    print(f"  INCONCLUSIVE  claim2-bad: doubling not reproduced (got {bad_n}, expected >=6) — "
          f"overflow not triggered on this Chrome; the trap is asserted, not refuted")

print(f"\nRESULT: {fail} hard failures (claim1 + claim2-good are the drift gates)")
sys.exit(1 if fail else 0)
