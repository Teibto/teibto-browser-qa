# Team process

This skill is a test-and-userguide engine, not a full SDLC tool. This playbook wires it into a team
flow (Requirement, Design, Dev, Test, Userguide) and sets out the bridges, boundaries, ownership, and
release gate, so results stay consistent and traceable whoever runs them.

✋ The key boundary: this is the acceptance, exploratory, and documentation pass that a person and
agent run before a release. It is not the deterministic CI regression suite. Keep the two separate
(see section 4).

---

## Where the tool fits

```mermaid
flowchart LR
    R["Requirement<br/>ticket / PRD"] --> D["Design<br/>Acceptance Criteria<br/>(Given/When/Then)"]
    D --> V["Dev<br/>build + unit/integration tests"]
    V --> T["Test"]
    T --> G["Userguide"]
    G --> Rel(["Release"])

    D -.->|"AC to coverage matrix"| TD["test-design.md"]
    TD --> FS["flow.yaml<br/>(requirement + acceptance)"]
    FS --> T
    T -.->|"one pass, two outputs"| QA["qa-report.md"]
    T -.->|"same run"| G

    classDef tool fill:#1f2937,stroke:#38bdf8,color:#e5e7eb;
    class TD,FS,QA tool
    classDef owned fill:#111827,stroke:#a855f7,color:#e5e7eb;
    class T,G owned
```

The solid path is the team's flow. The dotted path is where this skill plugs in: it consumes
Acceptance Criteria and produces both a QA verdict and the user guide from the same run.

---

## Stage by stage

### 1. Requirement to Acceptance Criteria (the Design bridge)
- Every requirement or ticket becomes one or more Acceptance Criteria in Given/When/Then form.
- Acceptance Criteria are the objective source of what must be true. They catch missing-feature bugs
  that code-based test design cannot, since you can't derive a test for code that was never written.
- Record the ticket id. It flows all the way to the guide.

### 2. Design (test design)
- Feed both the Acceptance Criteria and the code into
  [`../references/test-design.md`](../references/test-design.md): the AC drive the happy and
  functional coverage; the code drives the branch, edge, and adversarial coverage the AC don't spell out.
- Use its ✅ in-browser vs. ⚠️ code-only split as a contract with Dev (see section 3).

### 3. Dev (what belongs where)
| Concern | Owner | Where it's tested |
|---|---|---|
| ✅ Rendered UI: forms, navigation, visual, error surfacing | QA (this skill) | `flow.yaml` scenarios |
| ⚠️ Logic boundaries, race/concurrency, governance, SQL, rollback | Dev | unit / integration tests |

The ⚠️ code-only rows in `test-design.md` are not covered by the browser. Dev must cover them, and the
QA report should cite them as verified by dev tests or unverified in browser, never marked Pass.

### 4. Test (two distinct roles, kept separate)
| | teibto-browser-qa | CI regression suite (Playwright/Cypress) |
|---|---|---|
| Trigger | before a release, person + agent | every commit, headless, deterministic |
| Goal | acceptance, exploratory, and docs | fast pass/fail gate, no flakiness tolerated |
| Environment | dev machine (Windows cold-start / 10060 realities) | clean CI runner |
| Output | qa-report.md, user guide, bug reports | red/green |

Do not turn `flow.yaml` runs into the CI suite. The gotchas (ffmpeg, session stalls, os 10060) are
single-machine realities that make it flaky in CI. A stable subset of flows can be ported to
Playwright for CI, but that is a separate, deterministic artifact.

**Graduating a flow to Playwright CI.** Mark a scenario `ci_candidate: true` (flow.yaml) only when
it has earned it, then port it. Criteria:
- It is a happy or functional path (not an exploratory/adversarial hunt).
- It has run green for 3+ consecutive releases with no quarantine in that window.
- It depends on no single-machine gotcha (no ffmpeg/video, no `--profile` session reuse, no manual
  2FA) and its data is seeded idempotently (Phase 2) so a clean CI runner can set it up.
- Its assertions are deterministic (no reliance on wall-clock time or a running number's value).

The ported Playwright test is the CI artifact; the `flow.yaml` scenario stays as the acceptance/repro
source. `ci_candidate` only signals readiness — it does not turn the flow.yaml run into CI.

### 5. Userguide (regenerate every release)
The guide comes from a real run, so it is only correct for the UI at run time. A UI change silently
invalidates it. Put "regenerate the guide" on the release checklist rather than treating it as a
one-time task.

---

## Release gate

The gate is an exit code, not a judgement call. Maintain a coverage manifest per feature
(`qa/<feature>/coverage.yaml`, one row per Acceptance Criterion) and run:

```
python scripts/coverage-check.py qa/<feature>/coverage.yaml   # release blocked unless exit 0
```

Exit 0 requires that every AC maps to a scenario that ran and passed, with no Critical/High bug
open and nothing quarantined. Exit 1 means at least one AC is not_tested, blocked, quarantined, or a
Critical/High fail. Exit 2 means the manifest itself is broken (surfaced, never a silent pass). Full
model and status rules: [`../references/coverage-model.md`](../references/coverage-model.md).

Two checks the script cannot make, so keep them on the checklist:
1. The adversarial pass ran, not just smoke, for the changed areas.
2. The user guide was regenerated if any covered UI changed.

Severity guide: Critical is data loss, wrong money, or security. High is a core AC broken with no
workaround. Medium is an AC that works but only with a workaround. Low is cosmetic. Medium and Low
fails do not block the exit code but must ship with a tracked ticket.

---

## Ownership (RACI)

| Activity | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Write Acceptance Criteria | BA / PO | PO | Dev, QA | Team |
| Dev unit/integration (code-only rows) | Dev | Tech Lead | QA | - |
| Author `flow.yaml` and run QA | QA (+ agent) | QA Lead | Dev | PO |
| Review `qa-report.md` | Tech Lead | QA Lead | Dev | PO |
| Release gate sign-off | QA Lead | PO | Tech Lead | Team |
| Regenerate user guide | QA (+ agent) | QA Lead | - | Support / PO |

---

## Artifacts and where they live

Version QA artifacts with the feature, in the app repo, not on one person's machine:
```
<app-repo>/qa/<feature>/
  flow.yaml            # scenarios with requirement + acceptance
  run-log.json         # batch --json output (audit trail)
  baseline/            # visual-regression baselines (versioned)
  shots/               # per-step screenshots
  qa-report.md         # verdict + severity, cites ticket ids
  guide/               # generated user guide (regenerated per release)
```
This keeps coverage auditable, since the requirement, scenario, report, and guide all carry the same
ticket id, and it lets anyone re-run or diff a flow.
