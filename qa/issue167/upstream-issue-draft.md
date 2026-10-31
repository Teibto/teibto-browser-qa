# Draft for Tencent/BrowserSkill (not filed)

Filing upstream contacts people outside the team, so the repository owner decides whether to post it.

**Title:** 0.4.0: agent's own trusted click revoked as "User activity" (event timestamp ~0.4 ms before expected window)

**Environment:** bsk CLI/daemon 0.4.0, extension 0.4.0, protocol 1.7, Chrome 156.0.0.0, Windows 11.
Shared session, background task tab (`tab create --no-active`), loopback fixture page.

**Steps:**

1. `bsk cooperate sync --settle --session S --tab-id T` → `context_id`
2. `bsk click --selector '#btn' --session S --tab-id T --context <id>`
3. Repeat 30 times, with no human input. `GetLastInputInfo` idle was 45–113 s during the failures.

**Observed:** 5 of 30 clicks (other runs: 2/15 and 6/20) return
`permission_denied` / `User activity revoked this action` / `effect_state: unknown`.
`bsk cooperate status` right after shows one activity:

```json
{"type": "pointerdown", "label": "alert", "attribution": {
  "event_time": 1793434231124.7, "event_timestamp": 338070.2000000179,
  "expected_event_time": {"earliest": 338070.59999999404, "latest": 338074.59999999404},
  "expected_time": 1793434231105, "expected_type": "pointerdown"}}
```

The page-side counters (capturing pointerdown/pointerup/click listeners) show that every revoked click
was delivered exactly once, the same as a successful click.

**Expected:** the agent's own input, which matches `expected_type` and is 0.4 ms from the expected
window, is attributed to the agent and the action returns success.

**Also seen:** after accepting a `beforeunload` dialog, `bsk dialog accept` sometimes answers
`Browser did not confirm dialog closure` although the page navigated and `operation await` returns `completed`.
