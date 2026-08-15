# Claims Audit — agent-browser-qa (+ netsuite-qa-browser cross-ref)

Audited: 2026-07-14 · by: Claude Code · env: Win11, agent-browser 0.27.0, Chrome 150
**Round 5 (2026-08-02):** transport ย้ายเป็น CDP ตรง (`cdp.py`) — claim ที่ผูกกับ **daemon**
ถูกถอนทั้งหมด (10060 ทุกสายพันธุ์, session file, batch shape, record/ffmpeg, dashboard) ·
claim ที่ผูกกับ **Chrome/หน้าเว็บ** ยังอยู่และถูก re-verify ด้วย `self-test/smoke-test.sh`
รอบใหม่ (30 เคส) · claim ใหม่ที่เพิ่ม: console collector ผูกกับหน้า · `viewport` ข้าม invocation
ไม่มีผล · element-scoped `shot` ตก top-layer popup

**Round 6 (2026-08-16):** วัดใหม่บน **Chrome 151** พร้อมคำสั่งชุด `run`/`lens`/`steady`/`netlog`/`stub`
(`Teibto/teibto-dev-standards` #188/#190/#192 · `tests/test-cdp.sh` 88 เคสกับ Chrome จริง)

| claim | สถานะ | Risk | Smoke |
|---|---|---|---|
| **"`viewport` ข้าม invocation ไม่มีผล" (Round 5) — หยาบเกินไป** | **แก้แล้ว** วัดจริงพบว่ามันแยกร่าง: **ขนาดหน้าต่างค้าง** ข้าม invocation (Chrome resize หน้าต่างจริง) ส่วน **dsf/mobile ไม่ค้าง** · เป็นเหตุผลที่เทส T11e กับ T18e ในชุดเดียวกันดูขัดกันเองแต่ผ่านทั้งคู่มาตลอด | MED (version-pinned: Chrome 151) | T19a/T19b |
| `clearDeviceMetricsOverride` ไม่คืนขนาดหน้าต่าง — คืนตอน websocket ปิดเท่านั้น | measured | MED (version-pinned) | T20g/T20t |
| หน้าที่ไม่มี `<meta name=viewport>` ได้ layout 980px ใต้ mobile emulation | measured (พฤติกรรมมาตรฐานของ mobile browser ไม่ใช่ของ Chrome เวอร์ชันนี้อย่างเดียว) | LOW | T20h |
| `:focus-visible` ต้องมาจาก Tab จริง — `el.focus()` ไม่ติด | measured (ยืนยันซ้ำจาก gotchas §16) | LOW | T20l/T20n |
| `console` ของหน้าไม่เห็น HTTP 4xx/5xx ที่แอป `catch` เอง — `lens netlog` เห็น | measured (เคสคู่ในเทสเดียวกัน) | LOW | T21b/T21c |
| `Fetch.fulfillRequest` เปลี่ยนหน้าจอเข้าสถานะ empty/error ได้จริง | measured บน HTTP server จริงในเทส | LOW | T21f/T21h |

**หนี้ที่ยังเหลือ:** `self-test/smoke-test.sh` ของ repo นี้ (30 เคส) ยังไม่ครอบคำสั่งชุดใหม่ —
เคสทั้งหมดข้างบนอยู่ใน `tests/test-cdp.sh` ของ `teibto-dev-standards` ซึ่งเป็นเจ้าของ `cdp.py`
· ตราบใดที่ยังไม่ตัดสินใจว่าจะ mirror เคสมาที่นี่หรืออ้างข้ามรีโป ให้ถือว่าคอลัมน์ Smoke ข้างบน
หมายถึง "มีเทสที่ต้นทาง" ไม่ใช่ "มีเทสในรีโปนี้"

> **Round 4 (2026-07-17):** baseline re-verified on **agent-browser 0.32.1**. Two claims drifted —
> below-fold `click` now auto-scrolls (rows #13, abq #1) and `batch --json` shape changed (row #10).
> Rows below are the original 0.27.0 audit; the drift is captured in **Round 4** at the bottom.

**Goal:** find claims that might be "written wrong" before they bite — especially **causal claims
with no A/B** (the class the black-window="GPU" bug belonged to).

**Scoring:**
- Type: `causal` (symptom→cause→fix) · `syntax` · `recipe` · `principle` · `efficiency`
- Provenance: does the line carry "verified/observed <date/version>"?
- Risk: **HIGH** = causal + no A/B/provenance · **MED** = inferred/intermittent or version-pinned · **LOW** = has A/B, or syntax the smoke harness checks
- Smoke: covered by `self-test/smoke-test.sh`?

---

## Executive summary

1. **The skill authors already have good provenance discipline** — most high-risk claims carry an
   inline "verified <date>" / "verified v0.27.0". **The black-window="GPU" claim was the outlier**
   (a causal claim stated as fact with no A/B). Fixed → gotchas #9 is now a 3-mechanism model.
2. **Remaining risk classes:**
   - **Intermittent-infra** (os 10060 causes) — causal but hard to reproduce → *inference*, not A/B → label "inferred".
   - **Version-pinned** (Chrome 150 / CfT / 0.27.0 / specific NetSuite accounts) — drift risk on upgrade.
   - **Syntax/recipe** — machine-checkable → let `self-test/smoke-test.sh` verify them.
3. **No remaining "GPU-2" causal claim** in the audited surface (gotchas #1–9, netsuite §0–1 tables, commands.md).

---

## Claim risk table (by risk)

| # | Claim | Location | Type | Provenance | Risk | Smoke |
|---|-------|----------|------|-----------|------|-------|
| 1 | occlusion (`CalculateNativeWinOcclusion`) = primary black-window cause | ns §0 / abq #9 | causal | launcher (primary) but **not synthetically reproduced on Chrome 150** | MED | hard |
| 2 | GPU-compositing → black, fix `--disable-gpu` | ns §1 / abq #9 | causal | no A/B; scoped as conditional | MED | hard |
| 3 | long-poll `wait` → os 10060 (Windows) | abq #3 | causal | "observed 2026-07-05", intermittent, inferred | MED | hard |
| 4 | stale session file → 10060 on every command until killed | abq #3 / ns §1 | causal | "observed 2026-07-05" | MED | partial |
| 5 | `record` needs ffmpeg + PATH not refreshed in old daemon | abq #8 | causal | detailed, verified | MED | partial |
| 6 | `get attr <sel> <name>` — selector before name | commands / #4 | syntax | confirmed | LOW | ✅ |
| 7 | `find <locator> <val> <action>` — action first, name as flag | commands / #4 | syntax | confirmed | LOW | ✅ |
| 8 | PowerShell eats `@eN` (splatting) → must quote | abq #4 | syntax | observed | LOW | (pwsh) |
| 9 | `eval` shares global scope → bare `let x` collides | abq #4 / ns §4 | syntax | "observed 2×" | LOW | ✅ |
| 10 | `batch --json` → array of `{command,result,error,success}` | commands | recipe | v0.27 verified; **shape drifted on 0.32.1 → Round 4** | LOW | ⚠️ |
| 11 | `press Alt+ArrowDown` opens native dropdown + screenshot captures it | commands | recipe | "verified headed+headless CfT150" | LOW | manual |
| 12 | element-scoped `screenshot <sel>` drops top-layer popup | commands | recipe | stated | LOW | manual |
| 13 | click does NOT auto-scroll → below-fold = silent no-op; scrollintoview fixes | abq #1 | causal | in-file minimal repro (≤0.27); **FIXED on 0.32.1 → Round 4** | LOW | ⚠️ |
| 14 | `✓ Done` ≠ success → assert state | abq #2 | principle | — | LOW | n/a |
| 15 | JS click (`eval …click()`) fires handler reliably | abq #7 | recipe | confirmed | LOW | ✅ |
| 16 | headless CfT has no Thai font → boxes | abq #5 | causal | stated | LOW | (render) |
| 17 | about:blank = black but benign; verify get url → retry open | abq #9 | causal | **A/B verified 2026-07-14** | LOW | ✅ |
| 18 | CDP screenshot immune to occlusion | abq #9 / ns §0 | causal | **verified 2026-07-14** (cover 8s) | LOW | (cover) |

**abq** = agent-browser-qa · **ns** = netsuite-qa-browser

Rows #6, #7, #9, #10, #13, #17 are exercised by `self-test/smoke-test.sh` (all green on 2026-07-14 on
0.27.0; re-verified on 0.32.1 — see Round 4; batch was measured ~5× fewer round-trips than sequential).

---

## Actions

**A. Complete provenance labels** — #3, #4 (10060 causes) are *inferred*; add "inferred, intermittent"
so a reader doesn't mistake them for an A/B result.

**B. Smoke harness covers the reproducible rows** — re-run `self-test/smoke-test.sh` on every
Chrome / `cdp.py` bump; it is the automatic drift detector.

**C. Claims the harness can't cover (#1–#5, intermittent/conditional)** — rely on the provenance date
and re-verify on a tool bump; do not promote to "fact" without an A/B.

**D. Round-2 audited (2026-07-14):** `reliability-policy.md`, `perf-layer.md`, `a11y-layer.md`,
`visual-regression.md`, `flow-spec.md`, `pdf-reports.md`, `test-design.md` — see below.

---

## Round 2 — reference / layer files (2026-07-14)

~65 falsifiable claims across 7 files (3 parallel audits, verbatim claim + provenance extraction).

**Headline: these files carry almost NO inline provenance markers** — unlike `gotchas.md` /
`netsuite-qa-browser` which are well-marked "verified <date>". Only markers found: axe-core `4.10.0`,
printToPDF paper `Letter (~196×259mm)`, and `test-design.md`'s race recipe cites "PWOC #39 — repro +
verify fix 100%".

**But low overall alarm**, because the claim MIX here differs from gotchas:
- **Spec/schema** (flow YAML fields, defaults, `retry_on` enum) — definitional, self-consistent → low risk.
- **Tool-pinned recipes** (axe rule ids, `axe.run` shape, `vitals` fields, paged.js counters) — drift
  class; correctness = "does the tool still behave this way" → caught by **re-running**, not by reading.
  These silently break on an axe/Chrome bump. A dedicated layer smoke test would help.
- **Genuine unverified causal claims** — the "GPU class" — consolidated below.

### Consolidated HIGH-risk (unverified causal stated as fact)

| claim | file | adjudication |
|---|---|---|
| `@page` margin-box `counter(page)` doesn't work in Chrome `printToPDF` (justifies paged.js) | pdf-reports L32 | **REFUTED on Chrome 150 (2026-07-14)** — `@bottom-center{content:counter(page)}` DID render in `AB pdf` (footer on all 3 test pages). Version-drift: broke on old Chrome, works now. pdf-reports.md updated + paged.js kept (still needed for TOC `target-counter`). |
| paged.js + printToPDF **double-pagination** (blank even pages, page# ×2) | pdf-reports L41 | **CONFIRMED (2026-07-14)** — no fixes → 3 logical pages became **6** PDF pages, even pages footer-only; fixes → clean 3. Matches the wording exactly. `verified` added + `self-test/pdf/` shipped. |
| headless has no Thai font → boxes | pdf-reports L67 | duplicate of gotchas #5; widely-known → low real risk |
| wait-before-assert fixes timing-flaky assert | reliability §2 | restates golden rule #2 (verified); testable but timing-flaky to automate |
| don't `mark_end` at click's `✓ Done` = bogus number | perf §2 | corollary of golden rule #2 (verified) |
| ~~delete `~/.agent-browser/<session>.*` fixes stuck 10060~~ | reliability §1 | **ถอนแล้ว (2026-08-02)** — ไม่มี daemon ไม่มี session file อีกต่อไป |

→ Both PDF candidates now **resolved by an A/B** (`self-test/pdf/pdf-test.sh`): one was a stale claim
(Chrome caught up), one was real (verified + regression-tested). **No open "GPU-2" candidate remains**
in the audited surface. The lesson recurred: an unverified causal claim was 50/50 — one wrong, one right.

### Remaining (optional)

- **Layer-recipe drift test** (not built): inject axe-core, assert `axe.run` returns the documented
  `{violations}` shape + a known rule id fires; run `vitals --json` and assert LCP/CLS/TTFB/INP fields
  exist. Catches tool-version drift on the a11y/perf recipes.
- The spec/schema claims (flow YAML) are validated by the flow runner + `examples/saucedemo.yaml` —
  running that example end-to-end is their regression check.
- **Layer-recipe drift test** (optional): inject axe-core, assert `axe.run` returns the documented
  `{violations}` shape + a known rule id fires; run `vitals --json` and assert the LCP/CLS/TTFB/INP
  fields exist. Catches tool-version drift on the a11y/perf recipes.
- The spec/schema claims (flow YAML) are validated by the flow runner itself + `examples/saucedemo.yaml`
  — running that example end-to-end is their regression check.

---

## Round 3 — post-refactor claims (2026-07-17)

Five doc PRs merged (NetSuite scope-out + networkidle caveat #2, PDF template scoped-read #4, trim
black-window rule #4 #8, batch rationale #9, README networkidle #10). Two of them add a claim the
ledger must carry; one shifted line refs (fixed in the Round-2 table above: L23→L32, L30→L41, L54→L67).

| # | Claim | Location | Type | Provenance | Risk | Smoke |
|---|-------|----------|------|-----------|------|-------|
| 19 | `wait --load networkidle` never settles on NetSuite → use `wait --fn "jQuery.active===0"` | SKILL §3/§4 · commands.md · README · pdf boundary | causal | **cross-ref to netsuite-qa-browser; NOT A/B'd in this repo** | MED | no (harness has no NetSuite) |
| 20 | scoped Read of the template `<script>` block saves ~half the tokens vs the whole file | pdf-reports step 2 | efficiency | **measured 2026-07-17** — tiktoken o200k_base: guide 4,029→1,890 tok (53%), bug-report 54%; byte proxy 49%/52% | LOW | ✅ (drift gate ≥40%) |

**On #19 (the one to watch):** this is a causal claim of the exact class the audit exists to flag —
stated as fact, no A/B here. It is **inherited** from `netsuite-qa-browser` (where NetSuite lives), not
proven in this repo. Do not promote it to "verified" in this skill; if a NetSuite target is ever added
to the harness, A/B it (networkidle vs `jQuery.active===0`) then relabel. Trimming rule #4 (#8) removed
a *duplicate* of gotchas #9, not a claim — no ledger change beyond the line-ref fix.

`self-test/smoke-test.sh` now gates #20 with a pure-file check (`<script>` block ≥40% smaller than the
full template) — runs without a browser, so it stays green even where the browser harness can't.

---

## Round 4 — 0.32.1 upgrade drift (2026-07-17)

Upgraded the local install 0.27.0 → **0.32.1** and re-ran `self-test/smoke-test.sh` (the drift
detector). 14/15 passed; the one failure plus a follow-up A/B surfaced **two** real behavior changes.
Both were reproduced deterministically, not inferred.

| # | Claim (as of 0.27) | 0.32.1 result | adjudication |
|---|---|---|---|
| 13 | below-fold `click` = silent no-op; must `scrollintoview` first | **FIXED** — `click` auto-scrolls the element into view and fires. A/B: button `top=1629`, `innerH=569`, `inView=false`, `scrollY 0→1089` after click, handler ran. | Behavior changed. Docs version-noted (SKILL rule #1, gotchas #1, README table): 0.3x auto-scrolls; ≤0.27 no-op; `scrollintoview` is now a safe habit. Fixing version not in release notes / not bisected — confirmed present in 0.32.1. |
| 10 | `batch --json` item = `{command:"get url", result:<value>, error, success}` | **SHAPE CHANGED** — `command` is an **array** `["get","url"]`; `result` is an **object** `{lifecycle, <named value>}` (e.g. `result.url`). Four keys unchanged. | commands.md updated: read the value at `result.<field>`. The smoke-test #10 checks only key presence, so it passed despite the shape change — a harness gap (see below). |

**Not drifted (re-verified on 0.32.1):** `wait --load networkidle` → `✓ Done`; `get attr` order;
`find` order; `eval` global scope; `about:blank` benign; the pure-file scoped-read gate.

**Harness lesson:** smoke-test #10 asserts key *presence*, not *shape* — it stayed green while
`command`/`result` restructured. #10 now also asserts `command` is an array; #13 now asserts the
auto-scroll behavior. A presence check is not a shape check — a version bump can restructure a value
while keeping its keys.

**Upstream context (0.28–0.32 release notes):** no headline "click auto-scroll" fix; 0.32.0 did land
"completed-page waits resolve immediately when already ready" (touches `wait --load`) and security
hardening that "rejects unsafe startup arguments" — the latter is **not** re-verified here against the
black-window launch flags (`--disable-gpu`, `--disable-features=CalculateNativeWinOcclusion`) because
that launcher lives in another repo. Flag for manual check before relying on those flags on 0.3x.
