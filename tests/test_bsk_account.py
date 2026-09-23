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
ACCOUNTS = ROOT / "scripts" / "bsk-account.py"
FAKE_BSK = ROOT / "tests" / "fixtures" / "fake_bsk.py"
TEST_TMP = ROOT / "tests" / ".tmp"
TEST_TMP.mkdir(exist_ok=True)
FREE_PORT = 58990   # explicit port for tests that must not depend on what else listens on 528xx


class AccountDaemonTests(unittest.TestCase):
    """One daemon per customer account: own BSK_HOME, own port, own shared-window registry."""

    def setUp(self) -> None:
        self.root = TEST_TMP / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.log = self.root / "bsk.log"

    def env(self, **overrides) -> dict[str, str]:
        env = os.environ.copy()
        env.update({"TEIBTO_BSK_ACCOUNT_ROOT": str(self.root / "teibto"),
                    "FAKE_BSK_DAEMONS": "1", "FAKE_BSK_LOG": str(self.log)})
        env.pop("BSK_HOME", None)
        env.update(overrides)
        return env

    def run_accounts(self, *args: str, env: dict[str, str] | None = None,
                     check: bool = True) -> subprocess.CompletedProcess[str]:
        done = subprocess.run([sys.executable, str(ACCOUNTS), *args, "--bsk", str(FAKE_BSK)],
                              capture_output=True, text=True, encoding="utf-8",
                              env=env or self.env(), timeout=120)
        if check:
            self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        return done

    def daemon_starts(self) -> int:
        return sum(1 for line in (self.log.read_text(encoding="utf-8").splitlines()
                                  if self.log.exists() else []) if line == "daemon start")

    def error_code(self, done: subprocess.CompletedProcess[str]) -> str:
        self.assertEqual(2, done.returncode, done.stdout + done.stderr)
        return json.loads(done.stdout)["error"]["code"]

    def test_ensure_starts_a_daemon_on_the_accounts_own_home_and_port(self):
        result = json.loads(self.run_accounts("ensure", "foodstar", "--port", str(FREE_PORT)).stdout)
        self.assertTrue(result["started"])
        self.assertTrue(result["running"])
        self.assertEqual(FREE_PORT, result["ws_port"])
        self.assertTrue(result["bsk_home"].endswith(str(Path("bsk-homes") / "foodstar")))
        self.assertTrue(result["session_root"].endswith(str(Path("bsk-sessions") / "foodstar")))
        self.assertEqual(1, self.daemon_starts())

    def test_ensure_twice_reuses_the_running_daemon(self):
        self.run_accounts("ensure", "foodstar", "--port", str(FREE_PORT))
        again = json.loads(self.run_accounts("ensure", "foodstar").stdout)
        self.assertFalse(again["started"])
        self.assertEqual(FREE_PORT, again["port"])
        self.assertEqual(1, self.daemon_starts(), "a second daemon was started for the same account")

    def test_new_accounts_never_get_the_shared_port_or_each_others(self):
        first = json.loads(self.run_accounts("ensure", "alpha").stdout)
        second = json.loads(self.run_accounts("ensure", "beta").stdout)
        self.assertNotIn(52800, (first["port"], second["port"]))
        self.assertNotEqual(first["port"], second["port"])
        self.assertNotEqual(first["bsk_home"], second["bsk_home"])
        self.assertGreaterEqual(min(first["port"], second["port"]), 52810)

    def test_asking_for_a_taken_port_is_refused(self):
        self.run_accounts("ensure", "alpha", "--port", str(FREE_PORT))
        self.assertEqual("PORT_CONFLICT", self.error_code(
            self.run_accounts("ensure", "beta", "--port", str(FREE_PORT), check=False)))
        self.assertEqual("PORT_CONFLICT", self.error_code(
            self.run_accounts("ensure", "gamma", "--port", "52800", check=False)))

    def test_an_existing_account_is_not_silently_moved_to_another_port(self):
        self.run_accounts("ensure", "foodstar", "--port", str(FREE_PORT))
        self.assertEqual("PORT_CONFLICT", self.error_code(
            self.run_accounts("ensure", "foodstar", "--port", str(FREE_PORT + 1), check=False)))

    def test_a_daemon_on_the_wrong_port_is_reported_not_reused(self):
        self.run_accounts("ensure", "foodstar", "--port", str(FREE_PORT))
        home = Path(json.loads(self.run_accounts("env", "foodstar", "--shell", "json").stdout)["BSK_HOME"])
        state = home / "fake-daemon.json"
        state.write_text(json.dumps({"pid": 1, "ws_port": 52800}), encoding="utf-8")
        self.assertEqual("PORT_MISMATCH", self.error_code(self.run_accounts("ensure", "foodstar", check=False)))

    def test_env_prints_the_three_variables_for_each_shell(self):
        self.run_accounts("ensure", "foodstar", "--port", str(FREE_PORT))
        values = json.loads(self.run_accounts("env", "foodstar", "--shell", "json").stdout)
        self.assertEqual({"BSK_HOME", "BSK_AUTO_START", "TEIBTO_BSK_SESSION_ROOT"}, set(values))
        self.assertEqual("0", values["BSK_AUTO_START"])
        bash = self.run_accounts("env", "foodstar").stdout
        self.assertIn("export BSK_HOME='" + values["BSK_HOME"] + "'", bash)
        pwsh = self.run_accounts("env", "foodstar", "--shell", "pwsh").stdout
        self.assertIn("$env:TEIBTO_BSK_SESSION_ROOT = '" + values["TEIBTO_BSK_SESSION_ROOT"] + "'", pwsh)

    def test_env_for_an_unknown_account_is_an_error(self):
        self.assertEqual("UNKNOWN_ACCOUNT", self.error_code(self.run_accounts("env", "nobody", check=False)))

    def test_a_bad_account_name_is_refused(self):
        self.assertEqual("BAD_ACCOUNT", self.error_code(self.run_accounts("ensure", "../etc", check=False)))
        self.assertEqual(0, self.daemon_starts())

    def test_status_says_what_to_do_when_no_browser_is_connected(self):
        self.run_accounts("ensure", "foodstar", "--port", str(FREE_PORT))
        report = json.loads(self.run_accounts("status").stdout)
        self.assertEqual(["foodstar"], [item["account"] for item in report])
        self.assertEqual([], report[0]["browsers"])
        self.assertIn(str(FREE_PORT), report[0]["next"])
        connected = json.loads(self.run_accounts(
            "status", "foodstar", env=self.env(FAKE_BSK_DAEMON_BROWSERS="3e08257e")).stdout)
        self.assertEqual(["3e08257e"], connected[0]["browsers"])
        self.assertNotIn("next", connected[0])

    def test_an_existing_home_is_adopted_and_its_running_daemon_reused(self):
        home = self.root / "hand-started"
        home.mkdir()
        (home / "fake-daemon.json").write_text(json.dumps({"pid": 7, "ws_port": FREE_PORT}), encoding="utf-8")
        result = json.loads(self.run_accounts("ensure", "foodstar", "--port", str(FREE_PORT),
                                              "--bsk-home", str(home)).stdout)
        self.assertFalse(result["started"])
        self.assertEqual(str(home), result["bsk_home"])
        self.assertEqual(0, self.daemon_starts(), "a second daemon was started beside the adopted one")
        self.assertEqual("HOME_CONFLICT", self.error_code(self.run_accounts(
            "ensure", "foodstar", "--bsk-home", str(self.root / "elsewhere"), check=False)))

    def test_the_registry_holds_no_secret(self):
        self.run_accounts("ensure", "foodstar", "--port", str(FREE_PORT))
        text = (self.root / "teibto" / "bsk-accounts.json").read_text(encoding="utf-8").lower()
        for word in ("cookie", "token", "password", "secret"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
