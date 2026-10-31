# BrowserSkill 0.4.0 qualification

**PASS (version-pinned)** for daemon/extension 0.4.0/0.4.0, CLI 0.4.0, both protocols 1.7,
boolean skew=false, Chrome 156.0.0.0 on Windows 11, shared session `gsyi`. Only that exact pair is
admitted. Unknown versions, missing or mismatched protocols, and non-boolean skew still fail before
any tab is created.

Evidence is in `qualification.json`:

- **Native dialogs:** 20 rounds, 100/100 checks, daemon PID unchanged. 0.4.0 no longer accepts
  dialogs by itself. All 80 dialogs were suspended with `dialog_pending` and decided by the harness,
  and each original click was collected with `operation await`, never repeated.
- **Runner:** two complete suites (B and C) of 8 flows each: read, guarded confirm, and three
  concurrent workers × 2 rounds: 16/16 flows, screenshot ownership 24/24.
- **Regression tests:** `tests/test_bsk_engine.py::test_040_*` cover admission, protocol rejection,
  per-action context, refusal before dispatch (including `tab create`), persistent refusal,
  self-attribution acceptance and rejection, native dialog policy, unconfirmed beforeunload closure,
  lost coverage after a dialog, and no replay of an unknown input.

## What 0.4.0 changed and how it was handled

`../../references/engine2-bsk.md` (section "bsk 0.4.0") holds the operational rules. The short
version: each page action needs a fresh `cooperate sync` context, native dialogs wait for a decision,
and an upstream bug revokes 17–30% of the agent's own clicks as "User activity". A 30-click probe with
page-side pointerdown/pointerup/click counters showed that every revoked click was delivered exactly
once. The runner accepts such a revocation only when every recorded activity is the event type bsk
expected and lies within 5 ms of bsk's own expected window. These are recorded in
`run_done.session_sharing.self_revocations`. `upstream-issue-draft.md` is the unfiled report for
Tencent/BrowserSkill.

## Failures kept, not counted

- **Suite A** (`failed_attempt_suite_A` in the JSON) ran first on the final code. One worker click
  returned `The action's observed content changed; synchronize and replan` with an unknown effect,
  and the runner failed that step without re-sending.
- **Development runs** before the final code are not summarized here. They exposed, in order: the
  missing context, transient sync refusals (fixed with `--settle`), the self-attribution revocation,
  `tab create` refused before dispatch, and the unconfirmed beforeunload closure. Each one is now a
  regression test.

No daemon restart, profile change, extension change, CDP fallback or session stop was made. The
shared session was re-ensured once through `bsk-shared.py ensure` after the daemon stopped the former
one on idle.

## Reproduce

Run sequentially on the existing shared session with a new evidence directory:

```text
python self-test/engine2/shared-pair-dialogs.py --session <id> --out <new-output>
python self-test/engine2/shared-pair-runner.py --session <id> --out <new-output>
```

As in #163 and #165, this is shared-session qualification, not the destructive ten-case
contention matrix.
