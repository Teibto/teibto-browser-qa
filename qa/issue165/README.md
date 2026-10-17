# BrowserSkill 0.3.3 qualification

**PASS (version-pinned)** for daemon/extension 0.3.3/0.3.3, CLI 0.3.3, both protocols 1.3,
boolean skew=false, Chrome 155.0.0.0 on Windows. Only the explicit pair is admitted;
unknown versions, missing/mismatched protocols and non-boolean skew fail before tab creation.

Evidence in `qualification.json`:

- Native dialogs: 20 rounds, 100/100 checks, unchanged daemon PID.
- Runner after native dialogs: read, guarded confirm and three workers twice, 8/8 flows.
- Runner before native dialogs: the same 8/8 flows, providing a second complete run.
- Screenshot ownership: 24/24 images match the owning worker across both suites.
- Regression tests cover admission, protocol rejection, dialog guard/backstop and no input replay.

## Earlier failures and recovery boundary

`previous-attempts.json` preserves the original failed qualification and single retry. Worker B
returned `BSK_EFFECT_UNKNOWN`; its failure screenshot showed `act-clicked`, so input occurred
without confirmed cleanup. Other workers and the fresh-tab retry timed out navigating.
Those results remain FAIL and were not counted toward the passing qualification.

Before the follow-up, daemon status showed no sessions and its log recorded `idle session stopped`
for the former session. The shared coordinator then ensured the current session. The daemon PID
remained 26016; no restart, profile change, extension change, CDP fallback or manual session stop
was performed. A background/selected-tab A/B probe passed both paths. Complete suites above then
passed, including the original native-dialog-then-runner ordering.

The internal cause of the former session timeouts is not established. This change fixes the
version-admission blocker and qualifies the exercised paths; it does not claim an upstream
transport fix. Unknown input still fails without replay. Do not replace a live shared session
to hide a failure; inspect outcomes and use the coordinator after actual session expiry.

## Reproduce

Run sequentially with the existing shared session and a new evidence directory:

```text
python self-test/engine2/shared-pair-dialogs.py --session <id> --out <new-output>
python self-test/engine2/shared-pair-runner.py --session <id> --out <new-output>
```

Both harnesses use owned tabs and the shared lease and preserve the session. This is the same
shared-session qualification boundary used in #163, not the original destructive ten-case
contention matrix (session loss, registry corruption and killed-holder cases are excluded).
Raw logs and screenshots remain in the local evidence directory; the summary records their
hashes and the exact runner/harness source hashes.
