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

    def run_flow(self, yaml_text: str, variables: dict | None = None):
        root = self.workspace()
        flow = root / "flow.yaml"
        flow.write_text(textwrap.dedent(yaml_text), encoding="utf-8")
        out = root / "out"
        counter = root / "starts.txt"
        env = os.environ.copy()
        env["FAKE_CDP_COUNTER"] = str(counter)
        process = subprocess.run(
            [sys.executable, str(RUNNER), "--flow", str(flow), "--out", str(out),
             "--vars-json", "-", "--target-id", "target-123", "--cdp-script", str(FAKE_CDP)],
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


if __name__ == "__main__":
    unittest.main()
