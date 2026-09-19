from __future__ import annotations

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
FAKE_BSK = ROOT / "tests" / "fixtures" / "fake_bsk.py"
TEST_TMP = ROOT / "tests" / ".tmp"
TEST_TMP.mkdir(exist_ok=True)

READ_ONLY = """
    story: engine2
    title: Second engine
    scenarios:
      - id: read
        steps:
          - {action: open, target: "https://example.test/done", capture: true}
          - action: click
            target: "#tab"
            risk: read
            assert: {target: "#notice", contains: "saved"}
            capture: false
"""


class BskEngineTests(unittest.TestCase):
    """BAS §4: the second engine is read-only, pinned, and never yields a bare PASS."""

    def run_flow(self, yaml_text: str, env_overrides: dict[str, str] | None = None,
                 extra_args: list[str] | None = None):
        root = TEST_TMP / uuid.uuid4().hex
        root.mkdir()
        self.addCleanup(shutil.rmtree, root, True)
        flow = root / "flow.yaml"
        flow.write_text(textwrap.dedent(yaml_text), encoding="utf-8")
        out, log = root / "out", root / "bsk.log"
        env = os.environ.copy()
        env["FAKE_BSK_LOG"] = str(log)
        env.update(env_overrides or {})
        process = subprocess.run(
            [sys.executable, str(RUNNER), "--flow", str(flow), "--out", str(out),
             "--engine", "bsk", "--bsk", str(FAKE_BSK), *(extra_args or [])],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        events = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return process, out, events, calls

    def test_read_only_flow_is_pass_inferred_and_never_exit_zero(self):
        process, out, events, calls = self.run_flow(READ_ONLY)
        done = events[-1]
        self.assertEqual(done["verdict"], "PASS(inferred)")
        self.assertEqual(process.returncode, 1)
        self.assertEqual(done["failures"], 0)
        self.assertEqual(events[0]["engine"], "bsk")
        self.assertEqual(events[0]["driver_policy"]["dialog"], "bsk-accept-all")
        self.assertTrue((out / "shots" / "read-01.png").is_file())
        report = (out / "qa-report.md").read_text(encoding="utf-8")
        self.assertIn("**Engine:** bsk 0.3.0", report)
        self.assertIn("**Target ID:** `fake-session` (bsk session · browser `only-one`)", report)
        self.assertIn("session stop", calls)

    def test_same_event_types_as_primary_engine(self):
        _, _, events, _ = self.run_flow(READ_ONLY)
        self.assertEqual(
            {event["type"] for event in events},
            {"run_start", "session_ready", "scenario_start", "step", "step_done", "errors",
             "scenario_done", "run_done"},
        )

    def test_browser_generated_log_errors_are_not_console_failures(self):
        _, _, events, _ = self.run_flow(READ_ONLY)
        errors = next(event for event in events if event["type"] == "errors")
        self.assertTrue(errors["empty"])

    def test_write_step_is_refused_before_the_browser_is_touched(self):
        process, _, events, calls = self.run_flow("""
            story: engine2
            title: Second engine
            scenarios:
              - id: save
                steps:
                  - {action: open, target: "https://example.test/form"}
                  - {action: click, target: "#save", risk: write, assert: {url_contains: "/done"}}
        """)
        self.assertEqual(events[-1]["verdict"], "FAIL")
        self.assertEqual(process.returncode, 1)
        fatal = next(event for event in events if event["type"] == "fatal")
        self.assertEqual(fatal["error"]["code"], "ENGINE_RISK_NOT_ALLOWED")
        self.assertIn("save#2(click:write)", fatal["error"]["message"])
        self.assertEqual(calls, [])

    def test_undeclared_click_is_refused_because_default_risk_is_read(self):
        _, _, events, calls = self.run_flow("""
            story: engine2
            title: Second engine
            scenarios:
              - id: sneaky
                steps:
                  - {action: open, target: "https://example.test/form"}
                  - {action: click, target: "#delete", assert: {url_contains: "/done"}}
        """)
        fatal = next(event for event in events if event["type"] == "fatal")
        self.assertEqual(fatal["error"]["code"], "ENGINE_RISK_NOT_ALLOWED")
        self.assertIn("sneaky#2(click:undeclared)", fatal["error"]["message"])
        self.assertEqual(calls, [])

    def test_accepted_confirm_fails_the_step_and_is_still_recorded(self):
        process, out, events, _ = self.run_flow(
            READ_ONLY, {"FAKE_BSK_DIALOG": "confirm:Delete this record?"})
        self.assertEqual(events[-1]["verdict"], "FAIL")
        failed = next(event for event in events
                      if event["type"] == "step_done" and event.get("error"))
        self.assertEqual(failed["error"]["code"], "ENGINE_DIALOG_ACCEPTED")
        dialog = next(event for event in events if event["type"] == "dialog")
        self.assertEqual((dialog["kind"], dialog["answer"]), ("confirm", "accept"))
        self.assertIn("Delete this record?", (out / "qa-report.md").read_text(encoding="utf-8"))

    def test_accepted_alert_is_recorded_but_does_not_fail(self):
        _, _, events, _ = self.run_flow(READ_ONLY, {"FAKE_BSK_DIALOG": "alert:Heads up"})
        self.assertEqual(events[-1]["verdict"], "PASS(inferred)")
        self.assertEqual(events[-1]["dialogs"], 1)

    def test_unpinned_version_is_driver_incompatible(self):
        _, _, events, calls = self.run_flow(READ_ONLY, {"FAKE_BSK_VERSION": "0.4.0"})
        fatal = next(event for event in events if event["type"] == "fatal")
        self.assertEqual(fatal["error"]["code"], "DRIVER_INCOMPATIBLE")
        self.assertNotIn("session start", calls)

    def test_several_browsers_without_a_choice_is_ambiguous_not_guessed(self):
        _, _, events, calls = self.run_flow(READ_ONLY, {"FAKE_BSK_BROWSERS": "work,qa"})
        fatal = next(event for event in events if event["type"] == "fatal")
        self.assertEqual(fatal["error"]["code"], "BSK_BROWSER_AMBIGUOUS")
        self.assertIn("work", fatal["error"]["message"])
        self.assertIn("qa", fatal["error"]["message"])
        self.assertNotIn("session start", calls)

    def test_chosen_browser_is_passed_to_session_start_and_recorded(self):
        _, _, events, calls = self.run_flow(READ_ONLY, {"FAKE_BSK_BROWSERS": "work,qa"},
                                            ["--bsk-browser", "qa"])
        self.assertEqual(events[-1]["verdict"], "PASS(inferred)")
        self.assertIn("browser=qa", calls)
        ready = next(event for event in events if event["type"] == "session_ready")
        self.assertEqual(ready["browser_instance"], "qa")

    def test_unknown_browser_is_not_ready(self):
        _, _, events, calls = self.run_flow(READ_ONLY, {"FAKE_BSK_BROWSERS": "work,qa"},
                                            ["--bsk-browser", "gone"])
        fatal = next(event for event in events if event["type"] == "fatal")
        self.assertEqual(fatal["error"]["code"], "BSK_NOT_READY")
        self.assertNotIn("session start", calls)

    def test_single_browser_needs_no_choice(self):
        _, _, events, calls = self.run_flow(READ_ONLY)
        self.assertEqual(events[-1]["verdict"], "PASS(inferred)")
        self.assertIn("browser=only-one", calls)

    def test_ref_target_is_unsupported_not_silently_a_selector(self):
        _, _, events, _ = self.run_flow("""
            story: engine2
            title: Second engine
            scenarios:
              - id: ref
                steps:
                  - {action: open, target: "https://example.test/done"}
                  - {action: click, target: "@e3", risk: read, assert: {url_contains: "/done"}}
        """)
        failed = next(event for event in events
                      if event["type"] == "step_done" and event.get("error"))
        self.assertEqual(failed["error"]["code"], "ENGINE_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
