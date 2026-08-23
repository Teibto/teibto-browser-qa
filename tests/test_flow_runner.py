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


class FlowRunnerTests(unittest.TestCase):
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
             *(extra_args or [])],
            input=json.dumps(variables or {}), capture_output=True, text=True, encoding="utf-8", env=env,
        )
        return process, out, counter

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
        self.assertEqual(2, ready["version"])
        self.assertEqual("none", ready["input_settle"])
        self.assertEqual(str(FAKE_CDP), ready["cdp_script"])
        self.assertGreaterEqual(ready["duration_ms"], 0)
        steps = [item for item in payloads if item["type"] == "step_done"]
        self.assertTrue(all("timings" in item for item in steps))
        self.assertIn("action", steps[1]["timings"]["phases"])
        self.assertIn("wait", steps[1]["timings"]["phases"])
        self.assertIn("assert", steps[2]["timings"]["phases"])
        self.assertIn("timing", next(item for item in payloads if item["type"] == "errors"))

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
             "--cdp-script", str(FAKE_CDP)],
            capture_output=True, text=True, encoding="utf-8", env={k: v for k, v in os.environ.items() if k != "TGT_ID"},
        )
        self.assertEqual(2, process.returncode)
        self.assertIn("UNPINNED_TARGET", process.stdout)

    def test_secret_value_in_argv_is_rejected(self):
        process = subprocess.run(
            [sys.executable, str(RUNNER), "--flow", str(ROOT / "tests" / "fixtures" / "live-flow.yaml"),
             "--out", str(TEST_TMP / "never-created-secret-argv"), "--target-id", "target-123",
             "--cdp-script", str(FAKE_CDP), "--vars-json", '{"tester":"unsafe"}'],
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
        """, env_overrides={"FAKE_CDP_VERSION": "1"})
        self.assertEqual(1, process.returncode)
        events = (out / "run-log.jsonl").read_text(encoding="utf-8")
        self.assertIn("DRIVER_INCOMPATIBLE", events)
        self.assertIn("v2+", events)
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
        # A stale DIALOG=accept in the shell must not leak into the QA session. The current
        # driver prints its dialog ledger at session close, so the evidence is run-level.
        process, out, _ = self.run_flow(flow, env_overrides={
            "FAKE_CDP_DIALOG": "confirm:Delete this record?", "DIALOG": "accept"})
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        payloads = [json.loads(line) for line in
                    (out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]
        start = next(item for item in payloads if item["type"] == "run_start")
        self.assertEqual("safe", start["driver_policy"]["dialog"])
        dialog = next(item for item in payloads if item["type"] == "dialog")
        self.assertEqual({"scenario": None, "index": None, "kind": "confirm",
                          "message": "Delete this record?", "answer": "dismiss"},
                         {key: dialog[key] for key in
                          ("scenario", "index", "kind", "message", "answer")})
        done = next(item for item in payloads if item["type"] == "run_done")
        self.assertEqual(1, done["dialogs"])
        report = (out / "qa-report.md").read_text(encoding="utf-8")
        self.assertIn('dialog confirm: "Delete this record?" -> dismiss', report)
        self.assertIn("**Auto-answered dialogs:** 1 (policy: safe)", report)

        # A driver that reports dialogs while the step runs gets per-step attribution.
        process, out, _ = self.run_flow(flow, env_overrides={
            "FAKE_CDP_DIALOG": "confirm:Delete this record?", "FAKE_CDP_DIALOG_WHEN": "click"})
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        payloads = [json.loads(line) for line in
                    (out / "run-log.jsonl").read_text(encoding="utf-8").splitlines()]
        dialog = next(item for item in payloads if item["type"] == "dialog")
        self.assertEqual(("delete", 2, 2), (dialog["scenario"], dialog["index"], dialog["global_index"]))
        self.assertEqual(1, next(item for item in payloads if item["type"] == "run_done")["dialogs"])

        # The policy changes only through the explicit runner flag.
        process, out, _ = self.run_flow(flow, env_overrides={
            "FAKE_CDP_DIALOG": "confirm:Delete this record?"}, extra_args=["--dialog", "accept"])
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        events = (out / "run-log.jsonl").read_text(encoding="utf-8")
        self.assertIn('"answer":"accept"', events)
        self.assertIn('"dialog":"accept"', events)

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


if __name__ == "__main__":
    unittest.main()
