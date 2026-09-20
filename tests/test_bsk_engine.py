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
    """BAS §4: bsk is the primary engine, pinned, with the shared risk and dialog policy."""

    def run_flow(self, yaml_text: str, env_overrides: dict[str, str] | None = None,
                 extra_args: list[str] | None = None, *, with_engine: bool = True):
        root = TEST_TMP / uuid.uuid4().hex
        root.mkdir()
        self.addCleanup(shutil.rmtree, root, True)
        flow = root / "flow.yaml"
        flow.write_text(textwrap.dedent(yaml_text), encoding="utf-8")
        out, log = root / "out", root / "bsk.log"
        env = os.environ.copy()
        env.pop("TEIBTO_QA_ENGINE", None)
        env.pop("TGT_ID", None)
        env["FAKE_BSK_LOG"] = str(log)
        env.update(env_overrides or {})
        command = [sys.executable, str(RUNNER), "--flow", str(flow), "--out", str(out)]
        if with_engine:
            command += ["--engine", "bsk"]
        command += ["--bsk", str(FAKE_BSK), *(extra_args or [])]
        process = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", env=env,
        )
        events = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return process, out, events, calls

    def test_read_only_flow_passes_with_the_in_page_guard(self):
        process, out, events, calls = self.run_flow(READ_ONLY)
        done = events[-1]
        self.assertEqual(done["verdict"], "PASS")
        self.assertEqual(process.returncode, 0)
        self.assertEqual(done["failures"], 0)
        self.assertEqual(events[0]["engine"], "bsk")
        self.assertEqual(events[0]["driver_policy"]["dialog"], "safe")
        self.assertEqual(events[0]["driver_policy"]["dialog_enforcement"], "in-page-guard")
        self.assertTrue((out / "shots" / "read-01.png").is_file())
        report = (out / "qa-report.md").read_text(encoding="utf-8")
        self.assertIn("**Engine:** bsk 0.3.0", report)
        self.assertIn("**Target ID:** `fake-session` (bsk session · browser `only-one` · "
                      "tab `4242` · own window)", report)
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

    def test_write_step_runs_under_the_shared_risk_policy(self):
        process, _, events, calls = self.run_flow("""
            story: engine2
            title: Second engine
            scenarios:
              - id: save
                steps:
                  - {action: open, target: "https://example.test/form"}
                  - {action: click, target: "#save", risk: write, assert: {url_contains: "/done"}}
        """)
        self.assertFalse(any(event["type"] == "fatal" for event in events))
        self.assertEqual(events[-1]["verdict"], "PASS")
        self.assertEqual(process.returncode, 0)
        self.assertIn("session start", calls)

    def test_undeclared_click_runs_like_the_primary_engine(self):
        process, _, events, calls = self.run_flow("""
            story: engine2
            title: Second engine
            scenarios:
              - id: sneaky
                steps:
                  - {action: open, target: "https://example.test/form"}
                  - {action: click, target: "#delete", assert: {url_contains: "/done"}}
        """)
        self.assertFalse(any(event["type"] == "fatal" for event in events))
        self.assertEqual(events[-1]["verdict"], "PASS")
        self.assertEqual(process.returncode, 0)
        self.assertIn("session start", calls)

    def test_in_page_guard_answered_dialog_is_recorded_and_passes(self):
        process, out, events, _ = self.run_flow(
            READ_ONLY, {"FAKE_BSK_PAGE_DIALOG": "confirm:Delete this record?:dismiss"})
        self.assertEqual(events[-1]["verdict"], "PASS")
        self.assertEqual(process.returncode, 0)
        dialog = next(event for event in events if event["type"] == "dialog")
        self.assertEqual((dialog["kind"], dialog["answer"]), ("confirm", "dismiss"))
        self.assertIn("Delete this record?", (out / "qa-report.md").read_text(encoding="utf-8"))

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

    def test_accepted_confirm_does_not_fail_under_the_accept_policy(self):
        process, _, events, _ = self.run_flow(
            READ_ONLY, {"FAKE_BSK_DIALOG": "confirm:Delete this record?"},
            ["--dialog", "accept"])
        self.assertEqual(events[-1]["verdict"], "PASS")
        self.assertEqual(process.returncode, 0)
        dialog = next(event for event in events if event["type"] == "dialog")
        self.assertEqual((dialog["kind"], dialog["answer"]), ("confirm", "accept"))

    def test_accepted_alert_is_recorded_but_does_not_fail(self):
        _, _, events, _ = self.run_flow(READ_ONLY, {"FAKE_BSK_DIALOG": "alert:Heads up"})
        self.assertEqual(events[-1]["verdict"], "PASS")
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
        self.assertEqual(events[-1]["verdict"], "PASS")
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
        self.assertEqual(events[-1]["verdict"], "PASS")
        self.assertIn("browser=only-one", calls)

    def test_detached_navigate_is_retried_because_it_cannot_act_twice(self):
        _, _, events, calls = self.run_flow(READ_ONLY, {"FAKE_BSK_DETACH_ONCE": "navigate"})
        self.assertEqual(events[-1]["verdict"], "PASS")
        self.assertEqual(sum(1 for call in calls if call.startswith("navigate ")), 2)

    def test_detached_click_is_never_retried(self):
        _, _, events, calls = self.run_flow(READ_ONLY, {"FAKE_BSK_DETACH_ONCE": "click"})
        failed = next(event for event in events
                      if event["type"] == "step_done" and event.get("error"))
        self.assertEqual(failed["error"]["code"], "BSK_COMMAND_FAILED")
        self.assertEqual(sum(1 for call in calls if call.startswith("click ")), 1)

    def test_lost_session_says_the_effect_is_unknown(self):
        _, _, events, _ = self.run_flow(READ_ONLY, {"FAKE_BSK_SESSION_LOST": "click"})
        failed = next(event for event in events
                      if event["type"] == "step_done" and event.get("error"))
        self.assertEqual(failed["error"]["code"], "BSK_SESSION_LOST")
        self.assertIn("backend", failed["error"]["message"])

    def test_unconfirmed_click_is_effect_unknown_and_never_reissued(self):
        _, _, events, calls = self.run_flow(READ_ONLY, {"FAKE_BSK_EFFECT_UNKNOWN": "click"})
        failed = next(event for event in events
                      if event["type"] == "step_done" and event.get("error"))
        self.assertEqual(failed["error"]["code"], "BSK_EFFECT_UNKNOWN")
        self.assertEqual(sum(1 for call in calls if call.startswith("click ")), 1)

    def test_lost_agent_window_tab_is_session_lost(self):
        _, _, events, _ = self.run_flow(READ_ONLY, {"FAKE_BSK_NO_TAB": "click"})
        failed = next(event for event in events
                      if event["type"] == "step_done" and event.get("error"))
        self.assertEqual(failed["error"]["code"], "BSK_SESSION_LOST")

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

    def test_default_engine_is_bsk_when_the_env_is_unset(self):
        _, _, events, _ = self.run_flow(READ_ONLY, with_engine=False)
        self.assertEqual(events[0]["engine"], "bsk")

    def test_env_can_force_cdp_which_then_needs_a_target_id(self):
        process, _, events, _ = self.run_flow(
            READ_ONLY, {"TEIBTO_QA_ENGINE": "cdp"}, with_engine=False)
        self.assertEqual(process.returncode, 2)
        fatal = next(event for event in events if event["type"] == "fatal")
        self.assertEqual(fatal["error"]["code"], "UNPINNED_TARGET")


class BskSessionSharingTests(unittest.TestCase):
    run_flow = BskEngineTests.run_flow

    """#112: several agents on one browser must not drive each other's tab or window."""

    def test_the_run_owns_a_tab_and_pins_every_tab_scoped_command_to_it(self):
        _, _, events, calls = self.run_flow(READ_ONLY)
        ready = next(event for event in events if event["type"] == "session_ready")
        self.assertEqual(ready["tab_id"], "4242")
        self.assertTrue(ready["session_owned"])
        self.assertIn("tab create", calls)
        # Unpinned means "whichever tab is active", which a peer can move at any moment.
        self.assertNotIn("tab=unpinned", calls)
        self.assertIn("tab=4242", calls)

    def test_attaching_to_a_shared_session_never_starts_or_stops_it(self):
        _, out, events, calls = self.run_flow(
            READ_ONLY, {"FAKE_BSK_SESSIONS": "shared-1:only-one"},
            ["--bsk-session", "shared-1"])
        ready = next(event for event in events if event["type"] == "session_ready")
        self.assertEqual(events[-1]["verdict"], "PASS")
        self.assertEqual(ready["target_id"], "shared-1")
        self.assertFalse(ready["session_owned"])
        self.assertNotIn("session start", calls)
        self.assertNotIn("session stop", calls)
        self.assertIn("tab close", calls)     # only our own tab goes away
        self.assertIn("shared window", (out / "qa-report.md").read_text(encoding="utf-8"))

    def test_the_env_can_supply_the_shared_session(self):
        _, _, events, calls = self.run_flow(
            READ_ONLY, {"FAKE_BSK_SESSIONS": "shared-9:only-one", "TEIBTO_BSK_SESSION": "shared-9"})
        ready = next(event for event in events if event["type"] == "session_ready")
        self.assertEqual(ready["target_id"], "shared-9")
        self.assertNotIn("session start", calls)

    def test_attaching_to_a_session_that_is_gone_fails_closed(self):
        process, _, events, calls = self.run_flow(
            READ_ONLY, {"FAKE_BSK_SESSIONS": "shared-1:only-one"},
            ["--bsk-session", "ghost"])
        fatal = next(event for event in events if event["type"] == "fatal")
        self.assertEqual(fatal["error"]["code"], "BSK_SESSION_MISSING")
        self.assertEqual(process.returncode, 1)   # a session that cannot be opened fails the run
        self.assertNotIn("session start", calls)
        self.assertNotIn("tab create", calls)

    def test_attaching_is_rejected_on_the_cdp_engine(self):
        process, _, events, _ = self.run_flow(
            READ_ONLY, {"TEIBTO_QA_ENGINE": "cdp", "TGT_ID": "page-1"},
            ["--bsk-session", "shared-1"], with_engine=False)
        fatal = next(event for event in events if event["type"] == "fatal")
        self.assertEqual(fatal["error"]["code"], "INVALID_ARGS")
        self.assertEqual(process.returncode, 2)

    def test_a_capture_selects_the_runs_own_tab_first(self):
        """#118: bsk captures the visible tab, so a pinned background tab must be brought forward."""
        _, out, events, calls = self.run_flow(READ_ONLY)
        self.assertEqual(events[-1]["verdict"], "PASS")
        self.assertTrue((out / "shots" / "read-01.png").is_file())
        order = [call for call in calls if call in ("tab select", "screenshot --out")]
        self.assertEqual(["tab select", "screenshot --out"], order[:2])
        self.assertIn("tab-target=4242", calls)

    def test_a_peer_that_steals_focus_once_costs_a_retry_not_the_run(self):
        """#120: a capture is read-only, so select+capture may simply be sent again."""
        process, out, events, calls = self.run_flow(READ_ONLY, {"FAKE_BSK_STEAL_FOCUS": "once"})
        self.assertEqual(events[-1]["verdict"], "PASS")
        self.assertEqual(process.returncode, 0)
        self.assertTrue((out / "shots" / "read-01.png").is_file())
        self.assertEqual(2, sum(1 for call in calls if call == "screenshot --out"))
        self.assertEqual(2, sum(1 for call in calls if call == "tab select"))

    def test_a_peer_that_never_yields_fails_with_a_contended_tab_not_a_raw_error(self):
        _, _, events, calls = self.run_flow(READ_ONLY, {"FAKE_BSK_STEAL_FOCUS": "always"})
        failed = next(event for event in events
                      if event["type"] == "step_done" and event.get("error"))
        self.assertEqual(failed["error"]["code"], "CAPTURE_TAB_CONTENDED")
        self.assertIn("--bsk-session", failed["error"]["message"])   # names the way out
        # Three attempts for the step's own capture, three more for the failure evidence shot.
        self.assertEqual(6, sum(1 for call in calls if call == "screenshot --out"))

    def test_an_rpc_timeout_on_a_window_that_is_gone_reads_as_a_lost_session(self):
        """A closed Agent Window reaches the CLI as a timeout; blaming a slow browser hides it."""
        _, _, events, _ = self.run_flow(READ_ONLY, {"FAKE_BSK_RPC_TIMEOUT": "click"})
        failed = next(event for event in events
                      if event["type"] == "step_done" and event.get("error"))
        self.assertEqual(failed["error"]["code"], "BSK_SESSION_LOST")

    def test_an_rpc_timeout_while_the_window_is_alive_stays_a_command_failure(self):
        _, _, events, _ = self.run_flow(
            READ_ONLY, {"FAKE_BSK_RPC_TIMEOUT": "click", "FAKE_BSK_SESSIONS": "fake-session:only-one"})
        failed = next(event for event in events
                      if event["type"] == "step_done" and event.get("error"))
        self.assertEqual(failed["error"]["code"], "BSK_COMMAND_FAILED")

    def test_a_peer_holding_the_session_is_waited_out_not_reported_as_a_failure(self):
        process, _, events, calls = self.run_flow(READ_ONLY, {"FAKE_BSK_BUSY_ONCE": "click"})
        self.assertEqual(events[-1]["verdict"], "PASS")
        self.assertEqual(process.returncode, 0)
        # The rejected command was never dispatched, so the same click is sent again (#112 E7).
        self.assertEqual(2, sum(1 for call in calls if call.startswith("click ")))
        self.assertGreaterEqual(events[-1]["session_sharing"]["busy_waits"], 1)


if __name__ == "__main__":
    unittest.main()
