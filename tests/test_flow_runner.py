from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "scripts" / "flow-runner.py"
FAKE_CDP = ROOT / "tests" / "fixtures" / "fake_cdp.py"
TEST_TMP = ROOT / "tests" / ".tmp"
TEST_TMP.mkdir(exist_ok=True)


def load_runner():
    spec = importlib.util.spec_from_file_location("flow_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RunnerHarness:
    """Shared fixture plumbing; mixed into a TestCase so suites do not re-run each other."""

    def workspace(self) -> Path:
        root = TEST_TMP / uuid.uuid4().hex
        root.mkdir()
        self.addCleanup(shutil.rmtree, root, True)
        return root

    def run_flow(self, yaml_text: str, variables: dict | None = None,
                 env_overrides: dict[str, str] | None = None,
                 extra_args: list[str] | None = None):
        root = self.workspace()
        flow = root / "flow.yaml"
        flow.write_text(textwrap.dedent(yaml_text), encoding="utf-8")
        out = root / "out"
        counter = root / "starts.txt"
        env = os.environ.copy()
        env["FAKE_CDP_COUNTER"] = str(counter)
        env.update(env_overrides or {})
        process = subprocess.run(
            [sys.executable, str(RUNNER), "--flow", str(flow), "--out", str(out),
             "--vars-json", "-", "--target-id", "target-123", "--cdp-script", str(FAKE_CDP),
             "--engine", "cdp", *(extra_args or [])],
            input=json.dumps(variables or {}), capture_output=True, text=True, encoding="utf-8", env=env,
        )
        return process, out, counter


class FlowRunnerTests(RunnerHarness, unittest.TestCase):
    def test_pass_uses_one_session_and_redacts_secret(self):
        process, out, counter = self.run_flow("""
            story: login
            title: Login
            vars:
              - {name: password, secret: true}
            scenarios:
              - id: happy
                steps:
                  - {action: open, target: "https://example.test/done", capture: false}
                  - {action: fill, target: "#password", value: "{{password}}", capture: false}
                  - action: click
                    target: "#save"
                    assert: {target: "#notice", contains: "saved"}
                    capture: false
        """, {"password": "do-not-leak"})
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        self.assertEqual(["start"], counter.read_text(encoding="utf-8").splitlines())
        events = (out / "run-log.jsonl").read_text(encoding="utf-8")
        report = (out / "qa-report.md").read_text(encoding="utf-8")
        self.assertNotIn("do-not-leak", process.stdout + events + report)
        self.assertIn('"verdict":"PASS"', events)
        payloads = [json.loads(line) for line in events.splitlines()]
        ready = next(item for item in payloads if item["type"] == "session_ready")
        self.assertEqual(3, ready["version"])
        self.assertEqual("none", ready["input_settle"])
        self.assertIs(True, ready["foreground"])
        self.assertEqual("visible", ready["visibility_state"])
        self.assertEqual(str(FAKE_CDP), ready["cdp_script"])
        self.assertGreaterEqual(ready["duration_ms"], 0)
        steps = [item for item in payloads if item["type"] == "step_done"]
        self.assertTrue(all("timings" in item for item in steps))
        self.assertIn("action", steps[1]["timings"]["phases"])
        self.assertIn("wait", steps[1]["timings"]["phases"])
        self.assertIn("assert", steps[2]["timings"]["phases"])
        self.assertIn("timing", next(item for item in payloads if item["type"] == "errors"))

    def test_summary_stdout_preserves_complete_run_log(self):
        process, out, _ = self.run_flow("""
            story: token-safe
            title: Token-safe stdout
            scenarios:
              - id: smoke
                steps:
                  - {action: open, target: "https://example.test", capture: false}
        """, extra_args=["--stdout", "summary"])
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        stdout_events = [json.loads(line) for line in process.stdout.splitlines()]
        artifact_events = [json.loads(line) for line in
                           (out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(["run_done"], [item["type"] for item in stdout_events])
        self.assertGreater(len(artifact_events), len(stdout_events))
        self.assertEqual("run_start", artifact_events[0]["type"])
        self.assertEqual("run_done", artifact_events[-1]["type"])

    def test_summary_stdout_keeps_fatal_error_visible(self):
        process, _, _ = self.run_flow("""
            story: token-safe-fatal
            title: Token-safe fatal output
            scenarios:
              - id: smoke
                steps:
                  - {action: open, target: "https://example.test", capture: false}
        """, env_overrides={"FAKE_CDP_VERSION": "1"}, extra_args=["--stdout", "summary"])
        self.assertEqual(1, process.returncode)
        stdout_events = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(["fatal", "run_done"], [item["type"] for item in stdout_events])
        self.assertEqual("DRIVER_INCOMPATIBLE", stdout_events[0]["error"]["code"])

    def test_perf_budget_excludes_capture_and_reports_pass(self):
        process, out, _ = self.run_flow("""
            story: perf-pass
            title: Performance pass
            scenarios:
              - id: load
                doc: true
                steps:
                  - action: open
                    target: "https://example.test"
                    wait: 30
                    perf_budget_ms: 500
        """, env_overrides={"FAKE_CDP_SHOT_DELAY_MS": "800"})
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        payloads = [json.loads(line) for line in
                    (out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]
        step = next(item for item in payloads if item["type"] == "step_done")
        self.assertEqual("PASS", step["performance"]["verdict"])
        self.assertLessEqual(step["performance"]["outcome_ms"], 500)
        self.assertGreaterEqual(step["duration_ms"] - step["performance"]["outcome_ms"], 700)
        done = next(item for item in payloads if item["type"] == "run_done")
        self.assertEqual({"passed": 1, "evaluated": 1, "total": 1},
                         done["performance_budgets"])
        report = (out / "qa-report.md").read_text(encoding="utf-8")
        self.assertIn("**Performance budgets:** 1/1 passed (1 evaluated)", report)
        self.assertIn("budget 500ms → PASS", report)

    def test_perf_budget_exceedance_fails_closed_with_evidence(self):
        process, out, _ = self.run_flow("""
            story: perf-fail
            title: Performance failure
            scenarios:
              - id: save
                steps:
                  - action: open
                    target: "https://example.test"
                    wait: 50
                    perf_budget_ms: 5
        """)
        self.assertEqual(1, process.returncode)
        payloads = [json.loads(line) for line in
                    (out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]
        step = next(item for item in payloads if item["type"] == "step_done")
        self.assertEqual("PERF_BUDGET_EXCEEDED", step["error"]["code"])
        self.assertEqual("FAIL", step["performance"]["verdict"])
        self.assertGreater(step["performance"]["outcome_ms"], 5)
        self.assertEqual("perf_budget", step["timings"]["failing_phase"])
        self.assertTrue(Path(step["shot"]).is_file())
        done = next(item for item in payloads if item["type"] == "run_done")
        self.assertEqual({"passed": 0, "evaluated": 1, "total": 1},
                         done["performance_budgets"])
        report = (out / "qa-report.md").read_text(encoding="utf-8")
        self.assertIn("PERF_BUDGET_EXCEEDED", report)
        self.assertIn("budget 5ms → FAIL", report)

    def test_unasserted_click_is_unverified(self):
        process, out, _ = self.run_flow("""
            story: unverified
            title: Unverified
            scenarios:
              - id: smoke
                steps:
                  - {action: open, target: "https://example.test", capture: false}
                  - {action: click, target: "#save", capture: false}
        """)
        self.assertEqual(1, process.returncode)
        self.assertIn('"verdict":"UNVERIFIED"', (out / "run-log.jsonl").read_text(encoding="utf-8"))

    def test_schema_rejects_unknown_step_field(self):
        runner = load_runner()
        path = self.workspace() / "bad.yaml"
        path.write_text(textwrap.dedent("""
            story: bad
            title: Bad
            scenarios:
              - id: smoke
                steps:
                  - {action: click, target: "#x", silentFallback: true}
        """), encoding="utf-8")
        with self.assertRaises(runner.RunnerError) as caught:
            runner.load_flow(path)
        self.assertEqual("INVALID_FLOW", caught.exception.code)

    def test_schema_rejects_nonpositive_perf_budget(self):
        runner = load_runner()
        path = self.workspace() / "bad-perf.yaml"
        path.write_text(textwrap.dedent("""
            story: bad-perf
            title: Bad performance budget
            scenarios:
              - id: smoke
                steps:
                  - {action: open, target: "https://example.test", perf_budget_ms: 0}
        """), encoding="utf-8")
        with self.assertRaises(runner.RunnerError) as caught:
            runner.load_flow(path)
        self.assertEqual("INVALID_FLOW", caught.exception.code)

    def test_duplicate_variable_names_fail_closed(self):
        runner = load_runner()
        path = self.workspace() / "duplicates.yaml"
        path.write_text(textwrap.dedent("""
            story: duplicates
            title: Duplicates
            vars:
              - {name: user, default: first}
              - {name: user, default: second}
            scenarios:
              - id: smoke
                steps:
                  - {action: open, target: "https://example.test"}
        """), encoding="utf-8")
        with self.assertRaises(runner.RunnerError) as caught:
            runner.load_flow(path)
        self.assertEqual("INVALID_FLOW", caught.exception.code)

    def test_requires_pinned_target_before_starting_session(self):
        process = subprocess.run(
            [sys.executable, str(RUNNER), "--flow", str(ROOT / "examples" / "saucedemo.yaml"),
             "--out", str(TEST_TMP / "never-created-runner-test"),
             "--cdp-script", str(FAKE_CDP), "--engine", "cdp"],
            capture_output=True, text=True, encoding="utf-8", env={k: v for k, v in os.environ.items() if k != "TGT_ID"},
        )
        self.assertEqual(2, process.returncode)
        self.assertIn("UNPINNED_TARGET", process.stdout)

    def test_secret_value_in_argv_is_rejected(self):
        process = subprocess.run(
            [sys.executable, str(RUNNER), "--flow", str(ROOT / "tests" / "fixtures" / "live-flow.yaml"),
             "--out", str(TEST_TMP / "never-created-secret-argv"), "--target-id", "target-123",
             "--cdp-script", str(FAKE_CDP), "--engine", "cdp", "--vars-json", '{"tester":"unsafe"}'],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(2, process.returncode)
        self.assertIn("SECRET_IN_ARGV", process.stdout)

    def test_old_driver_is_rejected_with_actionable_error(self):
        process, out, _ = self.run_flow("""
            story: old-driver
            title: Old driver
            scenarios:
              - id: smoke
                steps:
                  - {action: open, target: "https://example.test", capture: false}
        """, env_overrides={"FAKE_CDP_VERSION": "2"})
        self.assertEqual(1, process.returncode)
        events = (out / "run-log.jsonl").read_text(encoding="utf-8")
        self.assertIn("DRIVER_INCOMPATIBLE", events)
        self.assertIn("v3+", events)
        fatal = next(json.loads(line) for line in events.splitlines()
                     if '"type":"fatal"' in line)
        self.assertIn(str(FAKE_CDP), fatal["error"]["message"])

    def test_driver_rejecting_fast_policy_is_mapped_to_incompatible(self):
        process, out, _ = self.run_flow("""
            story: rejected-policy
            title: Rejected policy
            scenarios:
              - id: smoke
                steps:
                  - {action: open, target: "https://example.test", capture: false}
        """, env_overrides={"FAKE_CDP_REJECT_INPUT_SETTLE": "1"})
        self.assertEqual(1, process.returncode)
        self.assertIn("DRIVER_INCOMPATIBLE",
                      (out / "run-log.jsonl").read_text(encoding="utf-8"))

    def test_driver_without_foreground_evidence_is_rejected_as_incompatible(self):
        process, out, _ = self.run_flow("""
            story: missing-foreground
            title: Missing foreground evidence
            scenarios:
              - id: smoke
                steps:
                  - {action: open, target: "https://example.test", capture: false}
        """, env_overrides={"FAKE_CDP_OMIT_FOREGROUND": "1"})
        self.assertEqual(1, process.returncode)
        payloads = [json.loads(line) for line in
                    (out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]
        fatal = next(item for item in payloads if item["type"] == "fatal")
        self.assertEqual("DRIVER_INCOMPATIBLE", fatal["error"]["code"])
        self.assertIn("foreground-ready evidence", fatal["error"]["message"])
        self.assertIn(str(FAKE_CDP), fatal["error"]["message"])

    def test_hidden_target_fails_closed_before_any_flow_step(self):
        process, out, _ = self.run_flow("""
            story: hidden-target
            title: Hidden target
            scenarios:
              - id: smoke
                steps:
                  - {action: open, target: "https://example.test", capture: false}
        """, env_overrides={"FAKE_CDP_FOREGROUND": "false",
                             "FAKE_CDP_VISIBILITY": "hidden"})
        self.assertEqual(1, process.returncode)
        payloads = [json.loads(line) for line in
                    (out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]
        fatal = next(item for item in payloads if item["type"] == "fatal")
        self.assertEqual("TARGET_BACKGROUND", fatal["error"]["code"])
        self.assertFalse(any(item["type"] == "step" for item in payloads))
        self.assertIn("performance baseline", fatal["error"]["message"])

    def test_auto_answered_dialogs_are_evidence_and_policy_is_pinned(self):
        flow = """
            story: dialogs
            title: Dialogs
            scenarios:
              - id: delete
                steps:
                  - {action: open, target: "https://example.test", capture: false}
                  - action: click
                    target: "#delete"
                    assert: {target: "#notice", contains: "saved"}
                    capture: false
        """
        # A stale DIALOG=accept in the shell must not leak into the QA session. Protocol v3
        # attaches structured dialogs to the command result; stderr must not duplicate them.
        process, out, _ = self.run_flow(flow, env_overrides={
            "FAKE_CDP_DIALOG": "confirm:Delete this record?", "DIALOG": "accept"})
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        payloads = [json.loads(line) for line in
                    (out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]
        start = next(item for item in payloads if item["type"] == "run_start")
        self.assertEqual("safe", start["driver_policy"]["dialog"])
        self.assertEqual("structured-per-command", start["driver_policy"]["dialog_evidence"])
        dialog_events = [item for item in payloads if item["type"] == "dialog"]
        self.assertEqual(1, len(dialog_events))
        dialog = dialog_events[0]
        self.assertEqual({"scenario": "delete", "index": 2, "global_index": 2,
                          "kind": "confirm",
                          "message": "Delete this record?", "answer": "dismiss"},
                         {key: dialog[key] for key in
                          ("scenario", "index", "global_index", "kind", "message", "answer")})
        done = next(item for item in payloads if item["type"] == "run_done")
        self.assertEqual(1, done["dialogs"])
        report = (out / "qa-report.md").read_text(encoding="utf-8")
        self.assertIn('dialog confirm: "Delete this record?" -> dismiss', report)
        self.assertIn("**Auto-answered dialogs:** 1 (policy: safe)", report)
        self.assertNotIn("reported by the driver at session close", report)

        # The policy changes only through the explicit runner flag.
        process, out, _ = self.run_flow(flow, env_overrides={
            "FAKE_CDP_DIALOG": "confirm:Delete this record?"}, extra_args=["--dialog", "accept"])
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        events = (out / "run-log.jsonl").read_text(encoding="utf-8")
        self.assertIn('"answer":"accept"', events)
        self.assertIn('"dialog":"accept"', events)

    def test_malformed_protocol_v3_dialogs_fail_closed(self):
        process, out, _ = self.run_flow("""
            story: bad-dialogs
            title: Bad protocol-v3 dialogs
            scenarios:
              - id: save
                steps:
                  - action: click
                    target: "#save"
                    assert: {target: "#notice", contains: "saved"}
                    capture: false
        """, env_overrides={"FAKE_CDP_BAD_DIALOGS": "1"})
        self.assertEqual(1, process.returncode)
        payloads = [json.loads(line) for line in
                    (out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]
        step = next(item for item in payloads if item["type"] == "step_done")
        self.assertEqual("INVALID_SESSION_OUTPUT", step["error"]["code"])
        self.assertEqual("action", step["timings"]["failing_phase"])

    def test_capture_defaults_follow_doc_mode_and_failure_evidence(self):
        passed, passed_out, _ = self.run_flow("""
            story: capture-policy
            title: Capture policy
            scenarios:
              - id: adversarial-pass
                doc: false
                steps:
                  - action: click
                    target: "#save"
                    assert: {target: "#notice", contains: "saved"}
              - id: guide-pass
                doc: true
                steps:
                  - {action: open, target: "https://example.test"}
        """)
        self.assertEqual(0, passed.returncode, passed.stdout + passed.stderr)
        shots = sorted(path.name for path in (passed_out / "shots").glob("*.png"))
        self.assertEqual(["guide-pass-01.png"], shots)

        failed, failed_out, _ = self.run_flow("""
            story: failure-evidence
            title: Failure evidence
            scenarios:
              - id: adversarial-fail
                doc: false
                steps:
                  - action: click
                    target: "#save"
                    assert: {target: "#notice", contains: "missing"}
        """)
        self.assertEqual(1, failed.returncode)
        self.assertTrue((failed_out / "shots" / "adversarial-fail-01-failure.png").is_file())
        payloads = [json.loads(line) for line in
                    (failed_out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]
        step = next(item for item in payloads if item["type"] == "step_done")
        self.assertEqual("assert", step["timings"]["failing_phase"])
        self.assertIn("capture", step["timings"]["phases"])


class OriginAndRiskPolicyTests(RunnerHarness, unittest.TestCase):
    """BAS-4: a run declares where it is allowed to go, and fails closed when it leaves."""

    ALLOWED = "https://sb1.example.test"

    def payloads(self, out: Path) -> list[dict]:
        return [json.loads(line) for line in
                (out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_flow_without_allowed_origins_keeps_previous_behaviour(self):
        process, out, counter = self.run_flow("""
            story: no-policy
            title: No declared origins
            scenarios:
              - id: smoke
                steps:
                  - {action: open, target: "https://anywhere.test/page", capture: false}
        """)
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        self.assertEqual(["start"], counter.read_text(encoding="utf-8").splitlines())
        start = next(item for item in self.payloads(out) if item["type"] == "run_start")
        self.assertEqual("not-declared", start["run_policy"]["origin_gate"])
        done = next(item for item in self.payloads(out) if item["type"] == "run_done")
        self.assertFalse(done["origin_gate"]["enforced"])
        self.assertIn("none declared", (out / "qa-report.md").read_text(encoding="utf-8"))

    def test_declared_target_outside_allowed_origins_fails_before_the_browser(self):
        process, out, counter = self.run_flow(f"""
            story: wrong-origin
            title: Declared target escapes
            allowed_origins: ["{self.ALLOWED}"]
            scenarios:
              - id: smoke
                steps:
                  - {{action: open, target: "https://prod.example.test/app", capture: false}}
        """)
        self.assertEqual(1, process.returncode)
        self.assertFalse(counter.exists(), "the session must not start once the flow is rejected")
        fatal = next(item for item in self.payloads(out) if item["type"] == "fatal")
        self.assertEqual("ORIGIN_NOT_ALLOWED", fatal["error"]["code"])
        self.assertIn("prod.example.test", fatal["error"]["message"])

    def test_redirect_outside_allowed_origins_fails(self):
        """The declared target is fine; the live URL is not. Only a post-navigation check sees it."""
        process, out, _ = self.run_flow(f"""
            story: redirected
            title: Redirect escapes
            allowed_origins: ["{self.ALLOWED}"]
            scenarios:
              - id: smoke
                steps:
                  - {{action: open, target: "{self.ALLOWED}/login", capture: false}}
        """, env_overrides={"FAKE_CDP_REDIRECT_TO": "https://prod.example.test/app"})
        self.assertEqual(1, process.returncode)
        step = next(item for item in self.payloads(out) if item["type"] == "step_done")
        self.assertEqual("ORIGIN_NOT_ALLOWED", step["error"]["code"])
        self.assertEqual("origin", step["timings"]["failing_phase"])

    def test_lookalike_host_is_rejected_where_a_prefix_match_would_pass(self):
        lookalike = f"{self.ALLOWED}.attacker.test/app"
        self.assertTrue(lookalike.startswith(self.ALLOWED), "fixture must fool a prefix match")
        process, out, _ = self.run_flow(f"""
            story: lookalike
            title: Lookalike host
            allowed_origins: ["{self.ALLOWED}"]
            scenarios:
              - id: smoke
                steps:
                  - {{action: open, target: "{self.ALLOWED}/login", capture: false}}
        """, env_overrides={"FAKE_CDP_REDIRECT_TO": lookalike})
        self.assertEqual(1, process.returncode)
        step = next(item for item in self.payloads(out) if item["type"] == "step_done")
        self.assertEqual("ORIGIN_NOT_ALLOWED", step["error"]["code"])

    def test_non_http_scheme_is_rejected(self):
        process, out, counter = self.run_flow(f"""
            story: bad-scheme
            title: Non-http scheme
            allowed_origins: ["{self.ALLOWED}"]
            scenarios:
              - id: smoke
                steps:
                  - {{action: open, target: "javascript:alert(1)", capture: false}}
        """)
        self.assertEqual(1, process.returncode)
        self.assertFalse(counter.exists())
        fatal = next(item for item in self.payloads(out) if item["type"] == "fatal")
        self.assertEqual("ORIGIN_NOT_ALLOWED", fatal["error"]["code"])
        self.assertIn("scheme is not http/https", fatal["error"]["message"])

    def test_destructive_step_is_blocked_without_the_run_level_opt_in(self):
        process, out, counter = self.run_flow("""
            story: destructive
            title: Destructive step
            scenarios:
              - id: cleanup
                steps:
                  - action: click
                    target: "#delete-everything"
                    risk: destructive
                    assert: {target: "#notice", contains: "saved"}
                    capture: false
        """)
        self.assertEqual(1, process.returncode)
        self.assertFalse(counter.exists())
        fatal = next(item for item in self.payloads(out) if item["type"] == "fatal")
        self.assertEqual("DESTRUCTIVE_NOT_ALLOWED", fatal["error"]["code"])
        self.assertIn("cleanup#1", fatal["error"]["message"])

    def test_destructive_step_runs_with_the_opt_in(self):
        process, out, counter = self.run_flow("""
            story: destructive-ok
            title: Destructive step allowed
            scenarios:
              - id: cleanup
                steps:
                  - action: click
                    target: "#delete-everything"
                    risk: destructive
                    assert: {target: "#notice", contains: "saved"}
                    capture: false
        """, extra_args=["--allow-destructive"])
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        self.assertEqual(["start"], counter.read_text(encoding="utf-8").splitlines())
        start = next(item for item in self.payloads(out) if item["type"] == "run_start")
        self.assertTrue(start["run_policy"]["destructive_allowed"])
        self.assertEqual(1, start["run_policy"]["risk_counts"]["destructive"])
        self.assertIn("destructive allowed", (out / "qa-report.md").read_text(encoding="utf-8"))

    def test_origin_check_is_not_charged_to_the_performance_budget(self):
        """perf_budget_ms measures the application's observable outcome, not our policy check."""
        process, out, _ = self.run_flow(f"""
            story: budget
            title: Budget with the gate on
            allowed_origins: ["{self.ALLOWED}"]
            scenarios:
              - id: smoke
                steps:
                  - action: open
                    target: "{self.ALLOWED}/page"
                    perf_budget_ms: 600000
                    capture: false
        """)
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        step = next(item for item in self.payloads(out) if item["type"] == "step_done")
        self.assertIn("origin", step["timings"]["phases"])
        self.assertLess(step["performance"]["outcome_ms"], step["timings"]["total_ms"])
        done = next(item for item in self.payloads(out) if item["type"] == "run_done")
        self.assertEqual(1, done["origin_gate"]["checks"])


class WaitTimeoutAndConsoleExpectationTests(RunnerHarness, unittest.TestCase):
    """#101: a step may declare its own wait ceiling, a scenario may declare the errors it expects."""

    NEVER = "fn:window.__never===true"

    def payloads(self, out: Path) -> list[dict]:
        return [json.loads(line) for line in
                (out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_wait_action_fails_at_the_declared_timeout_not_the_default(self):
        process, out, _ = self.run_flow(f"""
            story: short-wait
            title: Declared wait timeout
            scenarios:
              - id: slow
                steps:
                  - {{action: wait, target: "{self.NEVER}", wait_timeout_ms: 500, capture: false}}
        """)
        self.assertEqual(1, process.returncode)
        step = next(item for item in self.payloads(out) if item["type"] == "step_done")
        self.assertEqual("WAIT_TIMEOUT", step["error"]["code"])
        self.assertIn("0.5s", step["error"]["message"])
        # The default would have cost 20 s; anything in this range proves the declared value won.
        self.assertLess(step["duration_ms"], 5_000)
        self.assertEqual("wait", step["timings"]["failing_phase"])

    def test_wait_after_an_action_uses_the_declared_timeout(self):
        process, out, _ = self.run_flow(f"""
            story: short-wait-after-action
            title: Declared wait timeout after an action
            scenarios:
              - id: slow
                steps:
                  - action: open
                    target: "https://example.test"
                    wait: "{self.NEVER}"
                    wait_timeout_ms: 700
                    capture: false
        """)
        self.assertEqual(1, process.returncode)
        step = next(item for item in self.payloads(out) if item["type"] == "step_done")
        self.assertEqual("WAIT_TIMEOUT", step["error"]["code"])
        self.assertIn("0.7s", step["error"]["message"])
        self.assertLess(step["duration_ms"], 5_000)

    def test_schema_rejects_a_wait_timeout_outside_the_ceiling(self):
        runner = load_runner()
        for value in (120_001, 499, 0):
            with self.subTest(value=value):
                path = self.workspace() / "bad-timeout.yaml"
                path.write_text(textwrap.dedent(f"""
                    story: bad-timeout
                    title: Out of range wait timeout
                    scenarios:
                      - id: smoke
                        steps:
                          - {{action: wait, target: "#x", wait_timeout_ms: {value}}}
                """), encoding="utf-8")
                with self.assertRaises(runner.RunnerError) as caught:
                    runner.load_flow(path)
                self.assertEqual("INVALID_FLOW", caught.exception.code)
                self.assertIn("wait_timeout_ms", str(caught.exception))

    def test_expected_console_error_does_not_fail_the_scenario(self):
        process, out, _ = self.run_flow("""
            story: negative-case
            title: Expected console error
            scenarios:
              - id: missing-record
                expected_console_errors: ["Cannot read properties of undefined"]
                steps:
                  - {action: open, target: "https://example.test/notice", capture: false}
        """, env_overrides={"FAKE_CDP_CONSOLE":
                            "TypeError: Cannot read properties of undefined (reading 'appendChild')"})
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        errors = next(item for item in self.payloads(out) if item["type"] == "errors")
        self.assertEqual(["Cannot read properties of undefined"], errors["expected"])
        self.assertEqual([], errors["unexpected"])
        self.assertEqual([], errors["missing"])
        self.assertEqual(["TypeError: Cannot read properties of undefined (reading 'appendChild')"],
                         errors["matched"]["Cannot read properties of undefined"])
        report = (out / "qa-report.md").read_text(encoding="utf-8")
        self.assertIn('expected error "Cannot read properties of undefined" matched 1 message(s)',
                      report)
        self.assertIn("**Verdict:** PASS", report)

    def test_an_undeclared_console_error_still_fails_the_scenario(self):
        process, out, _ = self.run_flow("""
            story: negative-case
            title: One expected error, one surprise
            scenarios:
              - id: missing-record
                expected_console_errors: ["Cannot read properties of undefined"]
                steps:
                  - {action: open, target: "https://example.test/notice", capture: false}
        """, env_overrides={"FAKE_CDP_CONSOLE":
                            "TypeError: Cannot read properties of undefined (reading 'appendChild')"
                            "|Uncaught ReferenceError: nlapiLoadRecord is not defined"})
        self.assertEqual(1, process.returncode)
        errors = next(item for item in self.payloads(out) if item["type"] == "errors")
        self.assertEqual(["Uncaught ReferenceError: nlapiLoadRecord is not defined"],
                         errors["unexpected"])
        self.assertEqual([], errors["missing"])
        done = next(item for item in self.payloads(out) if item["type"] == "run_done")
        self.assertEqual("FAIL", done["verdict"])
        self.assertIn("nlapiLoadRecord", (out / "qa-report.md").read_text(encoding="utf-8"))

    def test_a_declared_error_that_never_appears_fails_the_scenario(self):
        """Otherwise the declaration is a gate that passes whatever the page does."""
        process, out, _ = self.run_flow("""
            story: negative-case
            title: Declared but absent
            scenarios:
              - id: missing-record
                expected_console_errors: ["Cannot read properties of undefined"]
                steps:
                  - {action: open, target: "https://example.test/notice", capture: false}
        """)
        self.assertEqual(1, process.returncode)
        errors = next(item for item in self.payloads(out) if item["type"] == "errors")
        self.assertTrue(errors["empty"])
        self.assertEqual(["Cannot read properties of undefined"], errors["missing"])
        self.assertEqual({}, errors["matched"])
        self.assertIn('expected error "Cannot read properties of undefined" never appeared',
                      (out / "qa-report.md").read_text(encoding="utf-8"))

    def test_a_scenario_that_declares_nothing_keeps_failing_on_console_errors(self):
        process, out, _ = self.run_flow("""
            story: undeclared
            title: No expectation declared
            scenarios:
              - id: smoke
                steps:
                  - {action: open, target: "https://example.test", capture: false}
        """, env_overrides={"FAKE_CDP_CONSOLE": "TypeError: boom"})
        self.assertEqual(1, process.returncode)
        errors = next(item for item in self.payloads(out) if item["type"] == "errors")
        self.assertFalse(errors["empty"])
        self.assertNotIn("expected", errors)
        self.assertIn("- ❌ Browser console: ['TypeError: boom']",
                      (out / "qa-report.md").read_text(encoding="utf-8"))


class EvalDeclarationTests(RunnerHarness, unittest.TestCase):
    """BAS-7/D4: an `action: eval` step declares itself or the run never opens a browser."""

    DECLARED = """
        story: declared-eval
        title: Declared eval
        scenarios:
          - id: probe
            steps:
              - {action: open, target: "https://example.test", capture: false}
              - action: eval
                target: "window.__feature = 'on'"
                risk: write
                eval_reason: "seed the feature flag the UI cannot set yet"
                assert: {target: "#notice", contains: "saved"}
                capture: false
    """

    def payloads(self, out: Path) -> list[dict]:
        return [json.loads(line) for line in
                (out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_eval_without_a_reason_is_rejected_before_the_browser_opens(self):
        process, out, counter = self.run_flow("""
            story: silent-eval
            title: Undeclared eval
            scenarios:
              - id: probe
                steps:
                  - {action: open, target: "https://example.test", capture: false}
                  - {action: eval, target: "window.__feature = 'on'", risk: write, capture: false}
        """)
        self.assertEqual(1, process.returncode)
        self.assertFalse(counter.exists(), "the session must not start once the flow is rejected")
        fatal = next(item for item in self.payloads(out) if item["type"] == "fatal")
        self.assertEqual("EVAL_NOT_DECLARED", fatal["error"]["code"])
        self.assertIn("probe#2 (ขาด: eval_reason)", fatal["error"]["message"])

    def test_eval_that_inherits_the_default_risk_is_rejected(self):
        """`risk` defaults to read, which is exactly the silent state change this gate is for."""
        process, out, counter = self.run_flow("""
            story: default-risk-eval
            title: Eval without its own risk class
            scenarios:
              - id: probe
                steps:
                  - action: eval
                    target: "document.querySelector('#save').click()"
                    eval_reason: "shortcut the save button"
                    capture: false
        """)
        self.assertEqual(1, process.returncode)
        self.assertFalse(counter.exists())
        fatal = next(item for item in self.payloads(out) if item["type"] == "fatal")
        self.assertEqual("EVAL_NOT_DECLARED", fatal["error"]["code"])
        self.assertIn("probe#1 (ขาด: risk)", fatal["error"]["message"])

    def test_a_declared_eval_is_evidence_in_the_run_log_and_the_report(self):
        process, out, _ = self.run_flow(self.DECLARED)
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        payloads = self.payloads(out)
        declaration = next(item for item in payloads if item["type"] == "eval")
        self.assertEqual({"scenario": "probe", "index": 2, "global_index": 2, "risk": "write",
                          "reason": "seed the feature flag the UI cannot set yet",
                          "evidence": "state set by eval, not trusted input"},
                         {key: declaration[key] for key in
                          ("scenario", "index", "global_index", "risk", "reason", "evidence")})
        start = next(item for item in payloads if item["type"] == "run_start")
        self.assertEqual("declared", start["run_policy"]["eval_gate"])
        done = next(item for item in payloads if item["type"] == "run_done")
        self.assertEqual({"declared": 1, "executed": 1,
                          "evidence": "state set by eval, not trusted input"},
                         done["eval_steps"])
        report = (out / "qa-report.md").read_text(encoding="utf-8")
        self.assertIn("**Eval steps:** 1/1 executed — state set by eval, not trusted input", report)
        self.assertIn("- 🧪 eval (risk: write) — state set by eval, not trusted input: "
                      "seed the feature flag the UI cannot set yet", report)

    def test_a_flow_without_eval_keeps_the_previous_report_and_events(self):
        process, out, _ = self.run_flow("""
            story: no-eval
            title: No eval anywhere
            scenarios:
              - id: smoke
                steps:
                  - {action: open, target: "https://example.test", capture: false}
        """)
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        payloads = self.payloads(out)
        self.assertEqual([], [item for item in payloads if item["type"] == "eval"])
        done = next(item for item in payloads if item["type"] == "run_done")
        self.assertEqual({"declared": 0, "executed": 0,
                          "evidence": "state set by eval, not trusted input"}, done["eval_steps"])
        report = (out / "qa-report.md").read_text(encoding="utf-8")
        self.assertNotIn("Eval steps", report)
        self.assertNotIn("state set by eval", report)

    def test_schema_rejects_an_empty_eval_reason(self):
        runner = load_runner()
        path = self.workspace() / "empty-reason.yaml"
        path.write_text(textwrap.dedent("""
            story: empty-reason
            title: Empty reason
            scenarios:
              - id: probe
                steps:
                  - {action: eval, target: "1", risk: read, eval_reason: ""}
        """), encoding="utf-8")
        with self.assertRaises(runner.RunnerError) as caught:
            runner.load_flow(path)
        self.assertEqual("INVALID_FLOW", caught.exception.code)
        self.assertIn("eval_reason", str(caught.exception))


class IdentityGuardAndReceiptTests(RunnerHarness, unittest.TestCase):
    """BAS-2/BAS-3 on the `--engine cdp` lane: aim on purpose, and keep the driver's receipt."""

    def payloads(self, out: Path) -> list[dict]:
        return [json.loads(line) for line in
                (out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]

    def run_with_actions(self, yaml_text: str, **kwargs):
        """Same as run_flow, but the fake driver also logs every action it actually performed."""
        root = self.workspace()
        actions = root / "actions.txt"
        overrides = dict(kwargs.pop("env_overrides", None) or {})
        overrides["FAKE_CDP_ACTIONS"] = str(actions)
        process, out, counter = self.run_flow(yaml_text, env_overrides=overrides, **kwargs)
        return process, out, actions

    def test_expect_mismatch_fails_the_step_and_sends_no_input(self):
        process, out, actions = self.run_with_actions("""
            story: wrong-button
            title: Intent does not match the element
            scenarios:
              - id: save
                steps:
                  - {action: open, target: "https://example.test", capture: false}
                  - action: click
                    target: ".btn-primary"
                    expect: "Submit"
                    capture: false
        """, env_overrides={"FAKE_CDP_AX_NAME": "Delete everything"})
        self.assertEqual(1, process.returncode)
        step = [item for item in self.payloads(out) if item["type"] == "step_done"][-1]
        self.assertEqual("EXPECT_MISMATCH", step["error"]["code"])
        self.assertIn("Delete everything", step["error"]["message"])
        self.assertFalse(actions.exists(), "a refused click must never reach the page")
        self.assertIn("EXPECT_MISMATCH", (out / "qa-report.md").read_text(encoding="utf-8"))

    def test_expect_count_mismatch_fails_before_the_input(self):
        process, out, actions = self.run_with_actions("""
            story: ambiguous
            title: Selector matches more than one element
            scenarios:
              - id: save
                steps:
                  - action: click
                    target: ".btn-primary"
                    expect_count: 1
                    capture: false
        """, env_overrides={"FAKE_CDP_MATCH_COUNT": "2"})
        self.assertEqual(1, process.returncode)
        step = [item for item in self.payloads(out) if item["type"] == "step_done"][-1]
        self.assertEqual("EXPECT_COUNT_MISMATCH", step["error"]["code"])
        self.assertFalse(actions.exists())

    def test_a_matching_expect_lets_the_step_through_and_is_reported(self):
        process, out, actions = self.run_with_actions("""
            story: right-button
            title: Intent matches the element
            scenarios:
              - id: save
                steps:
                  - action: click
                    target: "#save"
                    expect: "Save"
                    expect_count: 1
                    assert: {target: "#notice", contains: "saved"}
                    capture: false
        """)
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        self.assertEqual(["click #save"], actions.read_text(encoding="utf-8").splitlines())
        start = next(item for item in self.payloads(out) if item["type"] == "run_start")
        self.assertEqual("expect-when-declared", start["driver_policy"]["identity_guard"])
        self.assertEqual([{"step": "save#1", "action": "click", "expect": "Save",
                           "expect_count": 1}], start["run_policy"]["identity_steps"])
        done = next(item for item in self.payloads(out) if item["type"] == "run_done")
        self.assertEqual({"declared": 1, "engine_supported": True}, done["identity_guard"])

    def test_every_state_changing_action_carries_a_receipt(self):
        process, out, _ = self.run_with_actions("""
            story: receipts
            title: One action, one receipt
            scenarios:
              - id: save
                steps:
                  - {action: open, target: "https://example.test/app", capture: false}
                  - {action: fill, target: "#name", value: "Ada", capture: false}
                  - action: click
                    target: "#save"
                    assert: {target: "#notice", contains: "saved"}
                    capture: false
        """)
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        steps = [item for item in self.payloads(out) if item["type"] == "step_done"]
        self.assertNotIn("receipt", steps[0], "open is a navigation, not an observed action")
        for step in steps[1:]:
            self.assertEqual("https://example.test/app", step["receipt"]["url"])
            self.assertEqual("unwatched", step["receipt"]["net_errors"])
        done = next(item for item in self.payloads(out) if item["type"] == "run_done")
        self.assertEqual({"requested": 2, "received": 2, "engine_supported": True},
                         done["action_receipts"])
        report = (out / "qa-report.md").read_text(encoding="utf-8")
        self.assertIn("**Action receipts:** 2/2 received", report)
        self.assertIn("🧾 receipt: url=https://example.test/app", report)

    def test_a_driver_without_receipts_reports_unverified_instead_of_pass(self):
        """BAS-3: an observed action that came back without a receipt is not a PASS."""
        process, out, _ = self.run_with_actions("""
            story: no-receipt
            title: Driver returns no receipt
            scenarios:
              - id: save
                steps:
                  - action: click
                    target: "#save"
                    assert: {target: "#notice", contains: "saved"}
                    capture: false
        """, env_overrides={"FAKE_CDP_NO_RECEIPT": "1"})
        self.assertEqual(1, process.returncode)
        payloads = self.payloads(out)
        step = [item for item in payloads if item["type"] == "step_done"][-1]
        self.assertEqual("unverified", step["status"])
        self.assertIsNone(step["receipt"])
        self.assertIn("no page-state receipt", step["detail"])
        done = next(item for item in payloads if item["type"] == "run_done")
        self.assertEqual("UNVERIFIED", done["verdict"])
        self.assertEqual({"requested": 1, "received": 0, "engine_supported": True},
                         done["action_receipts"])

    def test_expect_on_an_action_the_driver_cannot_guard_is_rejected(self):
        process, out, counter = self.run_flow("""
            story: wrong-action
            title: expect on an action without an identity check
            scenarios:
              - id: probe
                steps:
                  - {action: select, target: "#country", value: "TH", expect: "Country"}
        """)
        self.assertEqual(1, process.returncode)
        self.assertFalse(counter.exists())
        fatal = next(item for item in self.payloads(out) if item["type"] == "fatal")
        self.assertEqual("EXPECT_NOT_SUPPORTED", fatal["error"]["code"])
        self.assertIn("probe#1 (action: select)", fatal["error"]["message"])

    def test_a_flow_without_expect_keeps_its_previous_behaviour(self):
        process, out, _ = self.run_flow("""
            story: plain
            title: No identity guard declared
            scenarios:
              - id: save
                steps:
                  - action: click
                    target: "#save"
                    assert: {target: "#notice", contains: "saved"}
                    capture: false
        """)
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        start = next(item for item in self.payloads(out) if item["type"] == "run_start")
        self.assertEqual([], start["run_policy"]["identity_steps"])
        done = next(item for item in self.payloads(out) if item["type"] == "run_done")
        self.assertEqual({"declared": 0, "engine_supported": True}, done["identity_guard"])
        self.assertEqual("PASS", done["verdict"])

    def test_schema_rejects_a_zero_expect_count(self):
        runner = load_runner()
        path = self.workspace() / "zero-count.yaml"
        path.write_text(textwrap.dedent("""
            story: zero-count
            title: Zero expect_count
            scenarios:
              - id: save
                steps:
                  - {action: click, target: "#save", expect_count: 0}
        """), encoding="utf-8")
        with self.assertRaises(runner.RunnerError) as caught:
            runner.load_flow(path)
        self.assertEqual("INVALID_FLOW", caught.exception.code)
        self.assertIn("expect_count", str(caught.exception))


class IdentityGuardHelperTests(unittest.TestCase):
    """Pure helpers: which flags each lane gets, and what counts as a receipt."""

    def setUp(self) -> None:
        self.runner = load_runner()

    def test_the_bsk_lane_is_given_no_identity_or_receipt_flags(self):
        step = {"action": "click", "target": "#save", "expect": "Save"}
        self.assertEqual([], self.runner.driver_flags(step, {}, "bsk"))

    def test_the_cdp_lane_substitutes_variables_into_expect(self):
        step = {"action": "fill", "target": "#name", "expect": "{{label}}", "expect_count": 2}
        self.assertEqual(["--expect=Full name", "--expect-count=2", "--observe"],
                         self.runner.driver_flags(step, {"label": "Full name"}, "cdp"))

    def test_navigation_and_eval_are_not_observed_actions(self):
        for action in ("open", "eval", "wait", "scrollintoview"):
            with self.subTest(action=action):
                self.assertEqual([], self.runner.driver_flags({"action": action}, {}, "cdp"))

    def test_a_partial_payload_is_not_a_receipt(self):
        full = {key: None for key in self.runner.RECEIPT_KEYS}
        self.assertEqual(full, self.runner.action_receipt({"data": full}))
        self.assertIsNone(self.runner.action_receipt({"data": "clicked #save @ 1,2"}))
        self.assertIsNone(self.runner.action_receipt({"data": {"url": "x", "title": "y"}}))
        self.assertIsNone(self.runner.action_receipt({}))


class WaitTimeoutAndConsoleGateHelperTests(unittest.TestCase):
    """Pure helpers, so the defaults and the matching rules are pinned without starting a run."""

    def setUp(self) -> None:
        self.runner = load_runner()

    def test_an_undeclared_timeout_keeps_the_previous_hard_coded_values(self):
        self.assertEqual("20", self.runner.wait_timeout({"action": "wait"},
                                                        self.runner.DEFAULT_WAIT_TIMEOUT_MS))
        self.assertEqual("30", self.runner.wait_timeout({"wait": "networkidle"},
                                                        self.runner.NAVIGATION_WAIT_TIMEOUT_MS))

    def test_a_declared_timeout_is_converted_to_seconds_for_both_engines(self):
        step = {"action": "wait", "wait_timeout_ms": 500}
        self.assertEqual("0.5", self.runner.wait_timeout(step, self.runner.DEFAULT_WAIT_TIMEOUT_MS))
        self.assertEqual("0.5", self.runner.wait_timeout(step,
                                                         self.runner.NAVIGATION_WAIT_TIMEOUT_MS))
        self.assertEqual("120", self.runner.wait_timeout({"wait_timeout_ms": 120_000},
                                                         self.runner.DEFAULT_WAIT_TIMEOUT_MS))

    def test_console_gate_without_expectations_treats_every_error_as_unexpected(self):
        matched, unexpected, missing = self.runner.console_gate(["TypeError: boom"], [])
        self.assertEqual(({}, ["TypeError: boom"], []), (matched, unexpected, missing))
        self.assertEqual(({}, [], []), self.runner.console_gate([], []))

    def test_console_gate_matches_by_substring_and_reports_both_directions(self):
        matched, unexpected, missing = self.runner.console_gate(
            ["TypeError: appendChild of undefined", "boom"], ["appendChild", "never-happens"])
        self.assertEqual({"appendChild": ["TypeError: appendChild of undefined"]}, matched)
        self.assertEqual(["boom"], unexpected)
        self.assertEqual(["never-happens"], missing)


class OriginHelperTests(unittest.TestCase):
    """Pure helpers, so the parsing rules are pinned without starting a run."""

    def setUp(self) -> None:
        self.runner = load_runner()

    def test_origin_of_normalises_case_and_keeps_the_port(self):
        self.assertEqual("https://sb1.example.test:8443",
                         self.runner.origin_of("HTTPS://SB1.Example.Test:8443/path?q=1#x"))

    def test_origin_of_rejects_other_schemes(self):
        for url in ("javascript:alert(1)", "file:///c:/tmp/x.html", "data:text/html,hi", "", "/rel"):
            with self.subTest(url=url):
                self.assertIsNone(self.runner.origin_of(url))

    def test_origin_violation_distinguishes_host_suffixes(self):
        allowed = ["https://sb1.example.test"]
        self.assertIsNone(self.runner.origin_violation("https://sb1.example.test/a/b", allowed))
        self.assertIsNotNone(
            self.runner.origin_violation("https://sb1.example.test.attacker.test/", allowed))
        self.assertIsNotNone(self.runner.origin_violation("http://sb1.example.test/", allowed))

    def test_flow_policy_defaults_missing_risk_to_read(self):
        policy = self.runner.flow_policy({
            "scenarios": [{"id": "s", "steps": [{"action": "click"},
                                                {"action": "click", "risk": "write"},
                                                {"action": "click", "risk": "destructive"}]}]
        })
        self.assertEqual({"read": 1, "write": 1, "destructive": 1}, policy["risk_counts"])
        self.assertEqual(["s#3"], policy["destructive_steps"])


if __name__ == "__main__":
    unittest.main()
