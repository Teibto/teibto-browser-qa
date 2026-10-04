from __future__ import annotations

import importlib.util
import json
import shutil
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("bsk_login", ROOT / "scripts" / "bsk-login.py")
login = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(login)
TEST_TMP = ROOT / "tests" / ".tmp"
TEST_TMP.mkdir(exist_ok=True)

PASSWORD = "S3cret-pw!"
SEED = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


class Clock:
    def __init__(self, start: float = 1_000_000.0):
        self.t = start

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


class FakeNetSuite:
    """Just enough of NetSuite's login pages to drive every branch of the gate."""

    def __init__(self, clock: Clock, *, logged_in_as=None, otp=False, person_after=None,
                 person_as=("4089685_SB2", "SANDBOX"), login_host="system.netsuite.com"):
        self.clock, self.session, self.otp_required = clock, logged_in_as, otp
        self.person_after, self.person_as, self.login_host = person_after, person_as, login_host
        self.page = {"protocol": "about:", "host": "", "path": "blank"}
        self.fields: dict[str, str] = {}
        self.filled_at: dict[str, float] = {}
        self.fills: list[str] = []
        self.clicks: list[str] = []
        self.submits = 0
        self.fronted = 0
        self.waiting_probes = 0

    # page builders
    def _set(self, host, path, **extra):
        self.page = {"protocol": "https:", "host": host, "path": path, "href": f"https://{host}{path}",
                     "ready": "complete", "title": "", "company": None, "env": None, "role": None,
                     "login": False, "otp": False, "otp_hidden": False, "mark": False, **extra}

    def _card(self):
        company, env = self.session
        self._set(company.lower().replace("_", "-") + ".app.netsuite.com", "/app/center/card.nl",
                  company=company, env=env, role=3)

    def _login(self):
        self._set(self.login_host, "/pages/customerlogin.jsp", login=True)

    # driver API
    def navigate(self, url: str) -> None:
        if "customerlogin" in url or not self.session:
            self._login()
        else:
            self._card()

    def evaluate(self, js: str) -> str:
        if js == login.PROBE_JS:
            if self.person_after is not None and self.fronted:
                self.waiting_probes += 1
                if self.waiting_probes >= self.person_after:
                    self.session = self.person_as
                    self._card()
            return json.dumps(self.page)
        if js == login.MARK_JS:
            self.page["mark"] = True
            return "ok"
        if js == login.TAG_OTP_JS:
            return json.dumps({"otp": True, "trust": True, "trust_checked": False, "submit": True})
        if js == login.TRUST_CHECKED_JS:
            return "true"
        raise AssertionError("unexpected script")

    def fill(self, selector: str, value: str) -> None:
        self.fills.append(selector)
        self.fields[selector] = value
        self.filled_at[selector] = self.clock.now()

    def click(self, selector: str) -> None:
        self.clicks.append(selector)
        if selector == "#login-submit":
            self.submits += 1
            if self.fields.get("#email") == "qa@example.com" and self.fields.get("#password") == PASSWORD:
                if self.otp_required:
                    self._set(self.login_host, "/app/login/secure/loginchallenge/entry.nl", otp=True)
                else:
                    self.session = ("4089685_SB2", "SANDBOX")
                    self._card()
            else:
                self._login()                       # a rejected POST reloads the form: the mark is gone
        elif selector == "[data-teibto-submit]":
            if self.fields.get("[data-teibto-otp]") == login.totp(SEED, self.clock.now()):
                self.session = ("4089685_SB2", "SANDBOX")
                self._set("4089685-sb2.app.netsuite.com", "/app/login/secure/authenticaterole.nl")
            # a wrong code is rejected in place: the SPA keeps the page and the mark

    def press(self, key: str, selector: str) -> None:
        raise AssertionError("submit button was available")

    def bring_to_front(self) -> None:
        self.fronted += 1


class LoginGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = TEST_TMP / uuid.uuid4().hex
        self.dir.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.clock = Clock()
        self.messages: list[str] = []

    def env(self, account="4089685_SB2", **extra) -> Path:
        path = self.dir / ".env"
        lines = [f"NS_ACCOUNT_ID={account}", "NS_EMAIL=qa@example.com", f'NS_PASSWORD="{PASSWORD}"']
        lines += [f"{k}={v}" for k, v in extra.items()]
        path.write_text("# test\n" + "\n".join(lines) + "\n", encoding="utf-8")
        return path

    def gate(self, ns, company="4089685_SB2", env_file=None, wait=60):
        return login.Gate(ns, company, env_file=env_file, wait_seconds=wait, log=self.messages.append,
                          sleep=self.clock.sleep, now=self.clock.now)

    def assertNoSecret(self, *texts):
        for text in texts:
            self.assertNotIn(PASSWORD, text)
            self.assertNotIn(SEED, text)

    def test_existing_session_is_used_without_touching_credentials(self):
        ns = FakeNetSuite(self.clock, logged_in_as=("4089685_SB2", "SANDBOX"))
        result = self.gate(ns, env_file=self.env()).run()
        self.assertEqual(("READY", "existing"), (result["state"], result["via"]))
        self.assertEqual([], ns.fills)

    def test_env_credentials_log_in_once(self):
        ns = FakeNetSuite(self.clock)
        result = self.gate(ns, env_file=self.env()).run()
        self.assertEqual("env", result["via"])
        self.assertEqual("4089685_SB2", result["company"])
        self.assertEqual(["#email", "#password"], ns.fills)
        self.assertEqual(1, ns.submits)
        self.assertNoSecret(json.dumps(result), *self.messages)

    def test_totp_is_answered_and_device_trusted(self):
        ns = FakeNetSuite(self.clock, otp=True)
        result = self.gate(ns, env_file=self.env(NS_TOTP_SECRET=SEED)).run()
        self.assertEqual("env", result["via"])
        self.assertIn("[data-teibto-trust]", ns.clicks)

    def test_totp_waits_out_a_nearly_expired_window(self):
        ns = FakeNetSuite(self.clock, otp=True)
        self.clock.t = 1_000_020.0 - 5          # a window edge is near when the code would be typed
        self.gate(ns, env_file=self.env(NS_TOTP_SECRET=SEED)).run()
        typed_at = ns.filled_at["[data-teibto-otp]"]
        self.assertGreaterEqual(30 - int(typed_at) % 30, login.TOTP_MIN_VALIDITY)

    def test_rejected_password_is_never_retried(self):
        path = self.env()
        path.write_text(path.read_text(encoding="utf-8").replace(PASSWORD, "wrong"), encoding="utf-8")
        ns = FakeNetSuite(self.clock)
        with self.assertRaises(login.LoginError) as raised:
            self.gate(ns, env_file=path, wait=30).run()
        self.assertEqual("BLOCKED", raised.exception.code)
        self.assertEqual(1, ns.submits)
        self.assertIn("ไม่ลองซ้ำ", str(raised.exception))
        self.assertTrue(any(m.startswith("ACTION REQUIRED") for m in self.messages))

    def test_rejected_password_then_person_logs_in(self):
        path = self.env()
        path.write_text(path.read_text(encoding="utf-8").replace(PASSWORD, "wrong"), encoding="utf-8")
        ns = FakeNetSuite(self.clock, person_after=3)
        result = self.gate(ns, env_file=path).run()
        self.assertEqual("user", result["via"])
        self.assertEqual(1, ns.submits)

    def test_env_for_another_account_is_not_used(self):
        ns = FakeNetSuite(self.clock, person_after=2)
        result = self.gate(ns, env_file=self.env(account="8158655_SB1")).run()
        self.assertEqual("user", result["via"])
        self.assertEqual([], ns.fills)
        self.assertTrue(any("ข้าม account" in m for m in self.messages))

    def test_missing_env_waits_for_a_person(self):
        ns = FakeNetSuite(self.clock, person_after=2)
        result = self.gate(ns, env_file=None).run()
        self.assertEqual("user", result["via"])
        self.assertEqual(1, ns.fronted)

    def test_production_needs_an_explicit_opt_in(self):
        ns = FakeNetSuite(self.clock, person_after=2, person_as=("4089685", "PRODUCTION"))
        result = self.gate(ns, company="4089685", env_file=self.env(account="4089685")).run()
        self.assertEqual("user", result["via"])
        self.assertEqual([], ns.fills)

    def test_production_opt_in_allows_auto_login(self):
        creds, why = login.load_credentials("4089685", self.env(account="4089685", NS_AUTO_LOGIN_PRODUCTION=1))
        self.assertEqual("", why)
        self.assertEqual(PASSWORD, creds["password"])

    def test_session_for_another_account_is_reported_not_switched(self):
        ns = FakeNetSuite(self.clock, logged_in_as=("4089685_SB1", "SANDBOX"))
        with self.assertRaises(login.LoginError) as raised:
            self.gate(ns, env_file=self.env()).run()
        self.assertEqual("IDENTITY_MISMATCH", raised.exception.code)
        self.assertEqual([], ns.fills)

    def test_credentials_are_never_typed_off_netsuite(self):
        ns = FakeNetSuite(self.clock, login_host="login.example-idp.com", person_after=2)
        result = self.gate(ns, env_file=self.env()).run()
        self.assertEqual("user", result["via"])
        self.assertEqual([], ns.fills)

    def test_errors_from_bsk_are_redacted(self):
        gate = self.gate(FakeNetSuite(self.clock), env_file=self.env())
        gate.secrets = [PASSWORD]
        self.assertEqual("bsk fill: value *** rejected", gate.redact(f"bsk fill: value {PASSWORD} rejected"))

    def test_totp_matches_rfc6238_vector(self):
        self.assertEqual("287082", login.totp(SEED, 59))   # RFC 6238 SHA-1 vector 94287082, 6 digits

    def test_classify_and_host_rules(self):
        self.assertEqual("4089685-sb2.app.netsuite.com", login.account_host("4089685_sb2"))
        self.assertFalse(login.is_production("8158655_SB1"))
        self.assertTrue(login.is_production("8158655"))
        self.assertEqual(login.FOREIGN, login.classify({"protocol": "https:", "host": "netsuite.com.evil.io"}))
        self.assertEqual(login.FOREIGN, login.classify({"protocol": "http:", "host": "system.netsuite.com"}))

    def test_cli_requires_a_session(self):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = login.main(["ensure", "--company", "4089685_SB2", "--session", "",
                               "--bsk", str(ROOT / "tests" / "fixtures" / "fake_bsk.py")])
        self.assertEqual(2, code)
        self.assertEqual("CONFIG", json.loads(out.getvalue())["error"]["code"])


if __name__ == "__main__":
    unittest.main()
