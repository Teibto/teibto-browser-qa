# BrowserSkill 0.3.3 candidate qualification

This candidate is **not qualified for installation or merge**. The allowlist change enables
qualification of exactly daemon/extension 0.3.3/0.3.3 with protocol 1.3 and boolean skew=false.
It does not certify other pairs or relax protocol checks.

The native dialog harness passed 100/100 checks (20 rounds), keeping the daemon PID unchanged.
The runner read/guarded-confirm flows and the first three-worker round passed. In the second
round, worker B returned `BSK_EFFECT_UNKNOWN`: the failure screenshot showed `act-clicked`,
so the action occurred despite cleanup not being confirmed. Workers A and C reported navigation
RPC/dispatch timeouts. No input was repeated on that tab. The run cleaned up its owned tabs.

A single follow-up attempt uses fresh fixture tabs after the prior processes ended and the
lease was released. Both attempts are retained in `qualification.json`, with raw-log hashes.
The installed skill remains unchanged. No daemon restart, new profile, or CDP fallback was used.

Reproduction (run sequentially with the existing shared session):

```text
python self-test/engine2/shared-pair-dialogs.py --session <id> --out <new-output>
python self-test/engine2/shared-pair-runner.py --session <id> --out <new-output>
```

Before merge: resolve the observed input/transport failure, obtain complete shared-session
qualification, then update the compatibility documentation and install the complete bundle.
