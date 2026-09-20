from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COORDINATOR = ROOT / "scripts" / "bsk-shared.py"
FAKE_BSK = ROOT / "tests" / "fixtures" / "fake_bsk.py"
TEST_TMP = ROOT / "tests" / ".tmp"
TEST_TMP.mkdir(exist_ok=True)


class SharedSessionTests(unittest.TestCase):
    """#116: every agent asks the coordinator which Agent Window to share, instead of opening one."""

    def setUp(self) -> None:
        self.root = TEST_TMP / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.registry = self.root / "registry"
        self.store = self.root / "sessions.txt"
        self.log = self.root / "bsk.log"

    def env(self, **overrides) -> dict[str, str]:
        env = os.environ.copy()
        env.update({"TEIBTO_BSK_SESSION_ROOT": str(self.registry),
                    "TEIBTO_BSK_LEASE_DIR": str(self.root / "leases"),
                    "FAKE_BSK_SESSION_FILE": str(self.store),
                    "FAKE_BSK_LOG": str(self.log)})
        env.pop("TEIBTO_BSK_BROWSER", None)
        env.update(overrides)
        return env

    def run_coordinator(self, *args: str, env: dict[str, str] | None = None,
                        check: bool = True) -> subprocess.CompletedProcess[str]:
        done = subprocess.run([sys.executable, str(COORDINATOR), *args, "--bsk", str(FAKE_BSK)],
                              capture_output=True, text=True, encoding="utf-8",
                              env=env or self.env(), timeout=120)
        if check:
            self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        return done

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def starts(self) -> int:
        return sum(1 for call in self.calls() if call == "session start")

    def test_ensure_opens_one_window_and_prints_its_id(self):
        done = self.run_coordinator("ensure")
        session_id = done.stdout.strip()
        self.assertTrue(session_id)
        self.assertEqual(1, self.starts())
        entry = json.loads((self.registry / "only-one.json").read_text(encoding="utf-8"))
        self.assertEqual(session_id, entry["session_id"])
        self.assertEqual("only-one", entry["browser_instance"])

    def test_ensure_twice_reuses_the_same_window(self):
        first = self.run_coordinator("ensure").stdout.strip()
        second = self.run_coordinator("ensure").stdout.strip()
        self.assertEqual(first, second)
        self.assertEqual(1, self.starts(), "the second ensure opened another Agent Window")

    def test_a_registered_session_that_is_gone_is_replaced(self):
        first = self.run_coordinator("ensure").stdout.strip()
        self.store.write_text("", encoding="utf-8")      # the daemon reaped it (idle session stopped)
        second = self.run_coordinator("ensure").stdout.strip()
        self.assertNotEqual(first, second)
        self.assertEqual(2, self.starts())

    def test_four_agents_at_once_end_up_in_one_window(self):
        env = self.env()
        workers = [subprocess.Popen([sys.executable, str(COORDINATOR), "ensure", "--bsk", str(FAKE_BSK)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
                   for _ in range(4)]
        ids = set()
        for worker in workers:
            out, err = worker.communicate(timeout=180)
            self.assertEqual(0, worker.returncode, out + err)
            ids.add(out.strip())
        self.assertEqual(1, len(ids), f"agents disagreed about the shared window: {ids}")
        self.assertEqual(1, self.starts(), "more than one Agent Window was opened")

    def test_several_browsers_without_a_choice_is_refused_not_guessed(self):
        done = self.run_coordinator("ensure", env=self.env(FAKE_BSK_BROWSERS="work,qa"), check=False)
        self.assertEqual(2, done.returncode)
        self.assertEqual("BSK_BROWSER_AMBIGUOUS", json.loads(done.stdout)["error"]["code"])
        self.assertEqual(0, self.starts())

    def test_a_named_browser_gets_its_own_registry_entry(self):
        env = self.env(FAKE_BSK_BROWSERS="work,qa")
        session_id = self.run_coordinator("ensure", "--browser", "qa", env=env).stdout.strip()
        entry = json.loads((self.registry / "qa.json").read_text(encoding="utf-8"))
        self.assertEqual(session_id, entry["session_id"])
        self.assertFalse((self.registry / "work.json").exists())

    def test_status_reports_what_is_registered_and_whether_it_is_alive(self):
        session_id = self.run_coordinator("ensure").stdout.strip()
        report = json.loads(self.run_coordinator("status").stdout)
        self.assertTrue(report["alive"])
        self.assertEqual(session_id, report["registered"]["session_id"])
        self.store.write_text("", encoding="utf-8")
        self.assertFalse(json.loads(self.run_coordinator("status").stdout)["alive"])

    def test_release_stops_the_window_and_forgets_it(self):
        self.run_coordinator("ensure")
        result = json.loads(self.run_coordinator("release").stdout)
        self.assertTrue(result["stopped"])
        self.assertIn("session stop", self.calls())
        self.assertFalse((self.registry / "only-one.json").exists())
        again = json.loads(self.run_coordinator("release").stdout)
        self.assertFalse(again["stopped"])          # releasing twice is not an error


if __name__ == "__main__":
    unittest.main()
