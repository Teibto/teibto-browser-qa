#!/usr/bin/env python3
"""Make one NetSuite account usable in the shared `bsk` browser with as little human help as possible.

    python scripts/bsk-login.py ensure --session "$SID" --company 4089685_SB2

Order of preference, each step only when the one before cannot finish the job:
  1. the browser already holds a session for this account  -> use it (via=existing)
  2. the project `.env` holds credentials for THIS account  -> log in once, TOTP included (via=env)
  3. otherwise                                              -> bring the tab forward and wait for a
                                                              person to log in there (via=user)
Every path ends in the same identity gate: company and environment read from `nlapiGetContext()` on
a classic page. A session for another account or environment is reported, never "fixed" by switching.

Credentials come from --env-file, TEIBTO_LOGIN_ENV or `.env` in the working directory (never a parent
directory): NS_ACCOUNT_ID, NS_EMAIL, NS_PASSWORD, optional NS_TOTP_SECRET. They are used only when
NS_ACCOUNT_ID equals --company, only on an https `*.netsuite.com` page, only once per run (a rejected
password is never retried: that is how accounts get locked), and a production account additionally
needs NS_AUTO_LOGIN_PRODUCTION=1 in that same file. Values are never printed.

stdout is one JSON object. Exit 0 = ready · 2 = usage/config · 3 = nobody logged in before the wait
ran out · 4 = logged in, but as another account/environment · 5 = bsk failed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # scripts/ is importable when run by path
from bsk_lease import SessionLease  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

READY, LOGIN, OTP, ROLE, FOREIGN, OTHER = "ready", "login", "otp", "role", "foreign", "other"
EXIT = {"CONFIG": 2, "BLOCKED": 3, "IDENTITY_MISMATCH": 4, "BSK_FAILED": 5}
TOTP_MIN_VALIDITY = 12      # a code with 1-2 s left is accepted, then the role leg times out
SUBMIT_SETTLE_SECONDS = 45

# One cheap read of where the tab is. Shadow roots are walked only on small pages: NetSuite's 2FA
# page is a web component, while a record form can be 2.7 MB and a full walk takes ~17 s.
PROBE_JS = r"""(function(){
var c=null;try{c=window.nlapiGetContext&&nlapiGetContext();}catch(e){}
function vis(e){return !!(e&&e.offsetParent!==null);}
var light=[].slice.call(document.querySelectorAll('input[type=tel],input[autocomplete="one-time-code"]')).filter(vis);
var deep=0;if(!c&&!light.length&&document.querySelectorAll('*').length<3000){(function w(r){r.querySelectorAll('*').forEach(function(e){if(e.shadowRoot){deep+=e.shadowRoot.querySelectorAll('input[type=tel],input[autocomplete="one-time-code"]').length;w(e.shadowRoot);}});})(document);}
return JSON.stringify({ready:document.readyState,href:location.href,protocol:location.protocol,host:location.hostname,
path:location.pathname,title:document.title,company:c?c.getCompany():null,env:c?c.getEnvironment():null,
role:c?c.getRoleId():null,login:vis(document.getElementById('email'))&&vis(document.getElementById('password')),
otp:light.length>0,otp_hidden:deep>0,mark:!!window.__teibtoLoginMark});})()"""

MARK_JS = "(function(){window.__teibtoLoginMark=1;return 'ok';})()"

# Tag the 2FA controls in the light DOM so trusted fill/click can address them by selector.
TAG_OTP_JS = r"""(function(){
function vis(e){return !!(e&&e.offsetParent!==null);}
function txt(e){return ((e.innerText||e.value||'')+' '+(e.getAttribute('aria-label')||'')).replace(/\s+/g,' ').trim();}
var o=[].slice.call(document.querySelectorAll('input[type=tel],input[autocomplete="one-time-code"]')).filter(vis)[0];
if(o)o.setAttribute('data-teibto-otp','1');
var t=[].slice.call(document.querySelectorAll('[role=checkbox],input[type=checkbox]')).filter(function(e){
 var box=e.closest('label')||e.parentElement||e;return /trust/i.test(txt(e)+' '+txt(box));})[0];
if(t)t.setAttribute('data-teibto-trust','1');
var s=[].slice.call(document.querySelectorAll('button,[role=button],input[type=submit]')).filter(function(e){
 return vis(e)&&/^(submit|verify)$/i.test(txt(e));})[0];
if(s)s.setAttribute('data-teibto-submit','1');
return JSON.stringify({otp:!!o,trust:!!t,trust_checked:!!t&&(t.getAttribute('aria-checked')==='true'||t.checked===true),submit:!!s});})()"""

TRUST_CHECKED_JS = ("(function(){var t=document.querySelector('[data-teibto-trust]');"
                    "return String(!!t&&(t.getAttribute('aria-checked')==='true'||t.checked===true));})()")


class LoginError(RuntimeError):
    def __init__(self, code: str, message: str, **detail):
        super().__init__(message)
        self.code, self.detail = code, detail


# --- configuration --------------------------------------------------------------------------------
def norm_company(value: str | None) -> str:
    return str(value or "").strip().upper().replace("-", "_")


def is_production(company: str) -> bool:
    """Sandboxes carry an `_SB<n>` suffix; everything else (prod, release preview) counts as production."""
    return not re.search(r"_SB\d*$", norm_company(company))


def account_host(company: str) -> str:
    return norm_company(company).lower().replace("_", "-") + ".app.netsuite.com"


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


def resolve_env_file(explicit: str | None) -> Path | None:
    candidate = explicit or os.environ.get("TEIBTO_LOGIN_ENV")
    path = Path(candidate) if candidate else Path.cwd() / ".env"
    return path if path.is_file() else None


def load_credentials(company: str, env_file: Path | None) -> tuple[dict | None, str]:
    """Credentials usable for THIS account, or (None, why not). The reason never carries a value."""
    if env_file is None:
        return None, "ไม่พบไฟล์ .env (ระบุ --env-file หรือ TEIBTO_LOGIN_ENV หรือรันจาก root ของโปรเจกต์)"
    values = parse_env_file(env_file)
    missing = [k for k in ("NS_ACCOUNT_ID", "NS_EMAIL", "NS_PASSWORD") if not values.get(k)]
    if missing:
        return None, f"{env_file} ขาด {', '.join(missing)}"
    if norm_company(values["NS_ACCOUNT_ID"]) != norm_company(company):
        return None, (f"{env_file} เป็นของ account {norm_company(values['NS_ACCOUNT_ID'])} "
                      f"ไม่ใช่ {norm_company(company)} — ไม่ใช้ credential ข้าม account")
    if is_production(company) and values.get("NS_AUTO_LOGIN_PRODUCTION") != "1":
        return None, (f"{norm_company(company)} เป็น production: login อัตโนมัติต้องตั้ง "
                      f"NS_AUTO_LOGIN_PRODUCTION=1 ใน {env_file}")
    return {"email": values["NS_EMAIL"], "password": values["NS_PASSWORD"],
            "totp": values.get("NS_TOTP_SECRET") or None, "source": str(env_file)}, ""


def totp(secret: str, at: float, digits: int = 6, step: int = 30) -> str:
    """RFC 6238 (SHA-1), so the gate needs no third-party package."""
    key = base64.b32decode(secret.replace(" ", "").upper() + "=" * (-len(secret.replace(" ", "")) % 8))
    digest = hmac.new(key, struct.pack(">Q", int(at // step)), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


# --- page state -----------------------------------------------------------------------------------
def classify(page: dict | None) -> str:
    if not page:
        return OTHER
    host = str(page.get("host") or "").lower()
    if page.get("protocol") != "https:" or not (host == "netsuite.com" or host.endswith(".netsuite.com")):
        return FOREIGN                 # an IdP / SSO page, about:blank, or somewhere we never type into
    if page.get("company"):
        return READY
    if page.get("login"):
        return LOGIN
    path = str(page.get("path") or "").lower()
    if page.get("otp") or page.get("otp_hidden") or "loginchallenge" in path:
        return OTP
    if "chooserole" in path:
        return ROLE                    # authenticaterole.nl is only the hop after a 2FA code: not a choice
    return OTHER


def in_login_flow(page: dict | None) -> bool:
    """A page a person may be typing into right now; navigating away would throw their work away."""
    path = str((page or {}).get("path") or "").lower()
    return not path.startswith("/app/") or any(k in path for k in ("login", "challenge", "role"))


class Gate:
    def __init__(self, driver, company: str, *, env_file: Path | None, wait_seconds: float,
                 poll_seconds: float = 5.0, log=None, sleep=time.sleep, now=time.time):
        self.d, self.company = driver, norm_company(company)
        self.env_file, self.wait_seconds, self.poll = env_file, wait_seconds, poll_seconds
        self.log = log or (lambda msg: print(msg, file=sys.stderr, flush=True))
        self.sleep, self.now = sleep, now
        self.home = f"https://{account_host(self.company)}/app/center/card.nl?sc=-29"
        self.login_url = f"https://system.netsuite.com/pages/customerlogin.jsp?c={self.company}"
        self.secrets: list[str] = []

    # -- helpers ---------------------------------------------------------------------------------
    def redact(self, text: str) -> str:
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, "***")
        return text

    def probe(self) -> dict | None:
        try:
            return json.loads(self.d.evaluate(PROBE_JS))
        except (RuntimeError, ValueError, TypeError):
            return None                # mid-navigation: the next poll answers

    def settle(self, limit: float = 30.0) -> dict | None:
        deadline = self.now() + limit
        page = self.probe()
        while (page is None or page.get("ready") != "complete") and self.now() < deadline:
            self.sleep(0.5)
            page = self.probe()
        return page

    def open(self, url: str) -> dict | None:
        try:
            self.d.navigate(url)
        except RuntimeError:
            pass                       # a redirect chain can outlive the wait; the probe decides
        return self.settle()

    def identity(self, page: dict, via: str) -> dict:
        result = {"state": "READY", "via": via, "company": page.get("company"),
                  "environment": page.get("env"), "role": page.get("role")}
        expected_env = "PRODUCTION" if is_production(self.company) else "SANDBOX"
        if norm_company(page.get("company")) != self.company or page.get("env") != expected_env:
            raise LoginError("IDENTITY_MISMATCH",
                             f"browser login อยู่ที่ {page.get('company')}/{page.get('env')} ไม่ใช่ "
                             f"{self.company}/{expected_env} — ไม่สลับ account/role ให้เอง", **result)
        return result

    def to_classic(self, page: dict | None) -> dict | None:
        """After a login NetSuite returns to whatever was asked first; the gate needs a classic page."""
        return page if classify(page) == READY else self.open(self.home)

    # -- the three ways in -----------------------------------------------------------------------
    def run(self) -> dict:
        page = self.open(self.home)
        if classify(page) == READY:
            return self.identity(page, "existing")
        creds, why = load_credentials(self.company, self.env_file)
        if creds is None:
            return self.wait_for_person(why)
        self.secrets = [creds["password"], creds["email"]] + ([creds["totp"]] if creds["totp"] else [])
        if classify(page) != LOGIN:
            page = self.open(self.login_url)     # native login page: SSO and stale redirects bypassed
        if classify(page) != LOGIN:
            return self.wait_for_person(f"ไม่พบหน้า Login ของ NetSuite ({classify(page)}: {(page or {}).get('host')})")
        outcome, page = self.auto_login(page, creds)
        if outcome == READY:
            return self.identity(page, "env")
        return self.wait_for_person(outcome)

    def submit_and_wait(self, click, *, retry_swallowed: bool) -> dict | None:
        """Click once; on the login form click again only if the page never even left (the form was
        still binding). The 2FA page is a SPA that rejects a code in place, so it never clicks twice."""
        self.d.evaluate(MARK_JS)
        click()
        deadline, clicked_again, started = self.now() + SUBMIT_SETTLE_SECONDS, False, self.now()
        while self.now() < deadline:
            self.sleep(1.0)
            page = self.probe()
            if page is None:
                continue
            state = classify(page)
            if page.get("mark") and state in (LOGIN, OTP):
                if retry_swallowed and not clicked_again and self.now() - started >= 6:
                    clicked_again = True       # no request was sent: the first click was swallowed
                    click()
                continue
            if page.get("ready") == "complete" and "authenticaterole" not in str(page.get("path")).lower():
                return page
        return self.probe()

    def auto_login(self, page: dict, creds: dict) -> tuple[str, dict | None]:
        if classify(page) != LOGIN:      # re-checked right before typing: https + *.netsuite.com
            return "หน้าเปลี่ยนก่อนกรอก — ไม่กรอก credential", page
        self.log(f"login อัตโนมัติ {self.company} ด้วย credential จาก {creds['source']}")
        try:
            self.d.fill("#email", creds["email"])
            self.d.fill("#password", creds["password"])
            page = self.submit_and_wait(lambda: self.d.click("#login-submit"), retry_swallowed=True)
        except RuntimeError as exc:
            return self.redact(f"กรอกหน้า Login ไม่สำเร็จ: {exc}"), self.probe()
        state = classify(page)
        if state == LOGIN:
            return "NetSuite ปฏิเสธ email/password ใน .env — ไม่ลองซ้ำ (กันบัญชีถูกล็อก)", page
        if state == OTP:
            if not creds["totp"]:
                return "หน้า 2FA ต้องใช้รหัส และ .env ไม่มี NS_TOTP_SECRET", page
            outcome, page = self.answer_otp(creds["totp"])
            if outcome != READY:
                return outcome, page
            state = classify(page)
        if state == ROLE:
            return "NetSuite ให้เลือก role — ไม่เลือกให้เอง", page
        page = self.to_classic(page)
        return (READY, page) if classify(page) == READY else (f"login แล้วไม่ถึงหน้า classic ({classify(page)})", page)

    def answer_otp(self, secret: str) -> tuple[str, dict | None]:
        found = json.loads(self.d.evaluate(TAG_OTP_JS))
        if not found.get("otp"):
            return "หาช่องรหัส 2FA ใน light DOM ไม่เจอ", self.probe()
        try:
            if found.get("trust") and not found.get("trust_checked"):
                self.d.click("[data-teibto-trust]")   # trusted click: el.click() does not toggle it
                if self.d.evaluate(TRUST_CHECKED_JS) != "true":
                    self.log("เตือน: ติ๊ก Trust this device ไม่สำเร็จ — รอบหน้าจะถาม 2FA อีก")
            remaining = 30 - int(self.now()) % 30
            if remaining < TOTP_MIN_VALIDITY:
                self.sleep(remaining + 0.5)
            self.d.fill("[data-teibto-otp]", totp(secret, self.now()))
            if found.get("submit"):
                page = self.submit_and_wait(lambda: self.d.click("[data-teibto-submit]"), retry_swallowed=False)
            else:
                page = self.submit_and_wait(lambda: self.d.press("Enter", "[data-teibto-otp]"), retry_swallowed=False)
        except RuntimeError as exc:
            return self.redact(f"ตอบ 2FA ไม่สำเร็จ: {exc}"), self.probe()
        state = classify(page)
        if state == OTP:
            return "NetSuite ไม่รับรหัส 2FA — ไม่ลองซ้ำ", page
        if state == LOGIN:
            return "session หมดระหว่าง 2FA (รหัสใกล้หมดอายุ)", page
        return READY, page

    def wait_for_person(self, why: str) -> dict:
        try:
            self.d.bring_to_front()
        except RuntimeError:
            pass
        page = self.probe()
        if classify(page) == FOREIGN:
            page = self.open(self.login_url)         # give the person a login form, not about:blank
        self.log(f"ACTION REQUIRED: กรุณา login NetSuite {self.company} ใน tab ที่เปิดอยู่ "
                 f"({(page or {}).get('href', self.login_url)}) — เหตุผล: {why} · รอ {int(self.wait_seconds)} วินาที")
        started = self.now()
        deadline = started + self.wait_seconds
        while self.now() < deadline:
            self.sleep(self.poll)
            page = self.probe()
            state = classify(page)
            if state == READY:
                result = self.identity(page, "user")
                result["waited_s"] = round(self.now() - started)
                return result
            if state == OTHER and page and page.get("ready") == "complete" and not in_login_flow(page):
                page = self.to_classic(page)         # landed on a Suitelet/React page after logging in
                if classify(page) == READY:
                    result = self.identity(page, "user")
                    result["waited_s"] = round(self.now() - started)
                    return result
        raise LoginError("BLOCKED", f"ยังไม่มีใคร login {self.company} ภายใน {int(self.wait_seconds)} วินาที — {why}",
                         reason=why)


# --- bsk transport --------------------------------------------------------------------------------
class BskDriver:
    """One pinned tab in a shared session; every command takes the session lease."""

    def __init__(self, bsk: list[str], session: str, tab_id: str | None):
        self.bsk, self.session, self.tab_id, self.owns_tab = bsk, session, tab_id, tab_id is None
        if self.owns_tab:
            created = self._cli(["tab", "create", "--no-active", "--url", "about:blank"], tab=False)
            self.tab_id = str(created.get("tab_id") or created.get("id") or "")
            if not self.tab_id:
                raise LoginError("BSK_FAILED", "bsk tab create ไม่คืน tab_id")

    def _cli(self, args: list[str], *, tab: bool = True, timeout: float = 90.0) -> dict:
        command = [*self.bsk, *args, "--json", "--session", self.session]
        if tab:
            command += ["--tab-id", self.tab_id]
        env = {**os.environ, "BSK_AUTO_START": "0"}
        with SessionLease(self.session):
            done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", env=env, timeout=timeout)
        if done.returncode != 0:
            raise RuntimeError(f"bsk {args[0]}: {(done.stderr or done.stdout).strip()[-300:]}")
        try:
            return json.loads(done.stdout) if done.stdout.strip() else {}
        except ValueError as exc:
            raise RuntimeError(f"bsk {args[0]} คืนค่าที่ไม่ใช่ JSON") from exc

    def navigate(self, url: str) -> None:
        self._cli(["navigate", url, "--wait-until", "load", "--timeout", "60s"])

    def evaluate(self, js: str) -> str:
        result = self._cli(["evaluate", js, "--timeout", "30s"])
        if result.get("ok") is not True:
            raise RuntimeError("evaluate failed")
        value = result.get("value")
        return value if isinstance(value, str) else json.dumps(value)

    def fill(self, selector: str, value: str) -> None:
        self._cli(["fill", "--selector", selector, "--value", value])

    def click(self, selector: str) -> None:
        self._cli(["click", "--selector", selector])

    def press(self, key: str, selector: str) -> None:
        self._cli(["press", key, "--selector", selector])

    def bring_to_front(self) -> None:
        self._cli(["tab", "select", self.tab_id], tab=False)

    def close(self) -> None:
        if self.owns_tab and self.tab_id:
            try:
                self._cli(["tab", "close", self.tab_id], tab=False, timeout=20)
            except RuntimeError:
                pass


def bsk_command(explicit: str | None) -> list[str]:
    candidate = explicit or os.environ.get("TEIBTO_BSK") or shutil.which("bsk")
    if not candidate or not (Path(candidate).is_file() or shutil.which(candidate)):
        raise LoginError("CONFIG", "ไม่พบ bsk: ระบุ --bsk หรือ TEIBTO_BSK หรือเพิ่มใน PATH")
    return [sys.executable, candidate] if str(candidate).endswith(".py") else [candidate]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("ensure",))
    parser.add_argument("--session", default=os.environ.get("TEIBTO_BSK_SESSION") or os.environ.get("NSBSK_SESSION"),
                        help="shared bsk session (python scripts/bsk-shared.py ensure)")
    parser.add_argument("--company", required=True, help="NetSuite account id, e.g. 4089685_SB2")
    parser.add_argument("--tab-id", help="drive this tab instead of opening (and closing) one of our own")
    parser.add_argument("--env-file", help="credentials file (default: TEIBTO_LOGIN_ENV, then ./.env)")
    parser.add_argument("--wait-seconds", type=float, default=float(os.environ.get("TEIBTO_LOGIN_WAIT", 900)),
                        help="how long to wait for a person when automation cannot log in (default 900)")
    parser.add_argument("--bsk", help="path to the bsk CLI (default: TEIBTO_BSK or PATH)")
    args = parser.parse_args(argv)
    driver = gate = None
    try:
        if not args.session:
            raise LoginError("CONFIG", "ต้องระบุ --session หรือ TEIBTO_BSK_SESSION")
        driver = BskDriver(bsk_command(args.bsk), args.session, args.tab_id)
        gate = Gate(driver, args.company, env_file=resolve_env_file(args.env_file), wait_seconds=args.wait_seconds)
        result = gate.run()
        result["tab_id"] = driver.tab_id
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except LoginError as exc:
        message = gate.redact(str(exc)) if gate else str(exc)
        print(json.dumps({"error": {"code": exc.code, "message": message, **exc.detail}}, ensure_ascii=False))
        return EXIT.get(exc.code, 2)
    except RuntimeError as exc:
        message = gate.redact(str(exc)) if gate else str(exc)
        print(json.dumps({"error": {"code": "BSK_FAILED", "message": message}}, ensure_ascii=False))
        return EXIT["BSK_FAILED"]
    finally:
        if driver is not None:
            driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
