#!/usr/bin/env python3
"""Example harness: drive a NetSuite SANDBOX through BrowserSkill (`bsk`) with the team's gates built in.

Rules and the evidence behind them: references/engine2-bsk.md. Configure through the environment:
    NSBSK_HOST=https://<account>-sb2.app.netsuite.com  NSBSK_COMPANY=<account>_SB2  NSBSK_BROWSER=<instance id>

    from nsbsk import Session, Laps
    with Session(name="o2c") as s:
        s.ns_open("/app/accounting/transactions/salesord.nl?whence=", record_type="salesorder")
        ...

Built-in rules (do not bypass them in scenario code):
  * SANDBOX-only identity gate on every ns_open(): NSBSK_COMPANY + SANDBOX, else SystemExit.
  * Page-level dialog guard: alert/confirm captured into window.__alerts, confirm() answers NO,
    onbeforeunload nulled. Any entry in s.dialogs means a native dialog leaked past the guard.
  * Only idempotent commands are retried on a detached debugger. click/fill/press/select/save never are.
  * A lost session after a mutating action means UNKNOWN effect: never repeat the action, ask the server.
  * BSK_AUTO_START=0, every call has a timeout, nothing is piped.
  * ONE Agent Window for a whole job: start it once with `python nsbsk.py open-shared`, export
    NSBSK_SESSION=<id>, and every Session() — in any script, from any agent — attaches to it and works in
    its OWN background tab instead of opening another window. `python nsbsk.py close-shared <id>` ends it.
    Trusted clicks land in hidden tabs (measured 9/9); timers are throttled there, so waits run slower.
"""
import json
import os
import subprocess
import tempfile
import time

HOST = os.environ.get("NSBSK_HOST", "").rstrip("/")
COMPANY, ENVIRONMENT = os.environ.get("NSBSK_COMPANY", ""), "SANDBOX"
BROWSER = os.environ.get("NSBSK_BROWSER", "")
_ENV = {**os.environ, "BSK_AUTO_START": "0"}   # bsk must be on PATH; the harness never starts the daemon

GUARD_JS = ("(function(){window.__alerts=window.__alerts||[];window.alert=function(m){window.__alerts.push('ALERT:'+m);};"
            "window.confirm=function(m){window.__alerts.push('CONFIRM(no):'+m);return false;};window.onbeforeunload=null;"
            "var c=window.nlapiGetContext&&nlapiGetContext();return JSON.stringify({company:c&&c.getCompany(),"
            "env:c&&c.getEnvironment(),role:c&&c.getRoleId(),type:window.nlapiGetRecordType?nlapiGetRecordType():null,"
            "href:location.href});})()")
INITED_JS = "String(!!(window.NS&&NS.form&&NS.form.isInited&&NS.form.isInited())&&typeof nlapiSetFieldValue==='function')"


class SessionLost(RuntimeError):
    """The Agent Window/session vanished. The last mutating action has an UNKNOWN effect."""


class EffectUnknown(RuntimeError):
    """bsk sent the input but could not confirm it. Observe the page; never re-issue the action."""


class _SharedLock:
    """Cross-process mutex for a shared session: a bsk session rejects a second concurrent command
    with `session_busy`, so every process attached to the same window takes turns."""

    def __init__(self, session_id, stale_after=180.0):
        self.path = os.path.join(tempfile.gettempdir(), f"nsbsk-{session_id}.lock")
        self.stale_after = stale_after

    def __enter__(self):
        deadline = time.monotonic() + 300
        while True:
            try:
                os.mkdir(self.path)          # atomic on every platform
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > self.stale_after:
                        os.rmdir(self.path)  # owner died mid-command
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("shared bsk window stayed busy for 300 s")
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            os.rmdir(self.path)
        except OSError:
            pass


class _NoLock:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


class Laps:
    def __init__(self):
        self.steps, self._mark, self._start = {}, time.perf_counter(), time.perf_counter()

    def lap(self, name):
        now = time.perf_counter()
        self.steps[name] = round((now - self._mark) * 1000)
        self._mark = now

    def total_ms(self):
        return round((time.perf_counter() - self._start) * 1000)


class Session:
    TAB_COMMANDS = {"navigate", "evaluate", "click", "fill", "press", "select", "screenshot", "console",
                    "snapshot", "observe", "reload", "wait-for-navigation"}

    def __init__(self, name="nsbsk", focus=False, attach=None):
        if not (HOST and COMPANY and BROWSER):
            raise SystemExit("set NSBSK_HOST, NSBSK_COMPANY and NSBSK_BROWSER (see `bsk browsers --json`)")
        self.sid, self.calls, self.retries, self.dialogs = None, 0, 0, []
        self.tab_id, self.owns_session = None, True
        attach = attach or os.environ.get("NSBSK_SESSION")
        if attach:
            # Shared-window mode: never start or stop the session here; own exactly one tab.
            self.sid, self.owns_session = attach, False
            # a tab left on chrome://newtab cannot be driven ("Cannot access a chrome:// URL")
            created = self.run(["tab", "create", "--no-active", "--url", "about:blank"], idempotent=False)
            self.tab_id = str(created.get("tab_id") or created.get("id"))
            return
        args = ["session", "start", "--name", name, "--browser", BROWSER] + ([] if focus else ["--no-focus"])
        self.sid = self.run(args, idempotent=True)["session_id"]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def run(self, args, *, idempotent, timeout=120):
        cmd = ["bsk", *args, "--json"] + (["--session", self.sid] if self.sid and args[0] != "session" else [])
        if self.tab_id and args[0] in self.TAB_COMMANDS:
            cmd += ["--tab-id", self.tab_id]
        for attempt in (1, 2, 3):
            self.calls += 1
            with (_SharedLock(self.sid) if (self.sid and not self.owns_session) else _NoLock()):
                done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                      timeout=timeout, env=_ENV)
            if done.returncode == 0:
                result = json.loads(done.stdout) if done.stdout.strip() else {}
                for item in (result.get("dialogs") or []) if isinstance(result, dict) else []:
                    self.dialogs.append({k: item.get(k) for k in ("type", "message", "handled")})
                return result
            text = (done.stderr or done.stdout)[-500:]
            if "session not registered" in text or "no active tab in Agent Window" in text:
                raise SessionLost(f"bsk {args[0]}: session/tab lost — effect of the last mutating action is UNKNOWN")
            if '"effect_state":"unknown"' in text.replace(" ", ""):
                # e.g. click -> input_cleanup_failed: the input was sent, the page may already have navigated
                raise EffectUnknown(f"bsk {args[0]}: {text}")
            if idempotent and "cdp_failed" in text and attempt < 3:
                self.retries += 1
                time.sleep(0.5)
                continue
            raise RuntimeError(f"bsk {args[0]}: {text}")

    # --- transport -------------------------------------------------------------------------------
    def nav(self, url, wait_until="load"):
        return self.run(["navigate", url if url.startswith("http") else HOST + url,
                         "--wait-until", wait_until, "--timeout", "90s"], idempotent=True)

    def ev(self, js, *, idempotent):
        """Evaluate JS. Pass idempotent=False for anything that changes state."""
        result = self.run(["evaluate", js, "--timeout", "90s"], idempotent=idempotent)
        if result.get("ok") is not True:
            raise RuntimeError(f"evaluate failed: {str(result)[:400]}")
        value = result.get("value")
        return value if isinstance(value, str) else json.dumps(value)

    def click(self, selector):           # trusted input through the extension; never retried
        return self.run(["click", "--selector", selector], idempotent=False)

    def fill(self, selector, value):     # real typing into the element; never retried
        return self.run(["fill", "--selector", selector, "--value", str(value)], idempotent=False)

    def press(self, key, selector=None):
        return self.run(["press", key] + (["--selector", selector] if selector else []), idempotent=False)

    def select(self, selector, value):   # native <select> by option value
        return self.run(["select", "--selector", selector, "--value", str(value)], idempotent=False)

    def shot(self, path, full_page=False):
        return self.run(["screenshot", "--out", path] + (["--full-page"] if full_page else []), idempotent=True)

    def snapshot(self, max_tokens=1500):  # aria snapshot with @eN refs; keep it small
        return self.run(["snapshot"], idempotent=True)

    def console_errors(self):
        result = self.run(["console"], idempotent=True)
        return [e.get("text") for e in result.get("entries", [])
                if e.get("kind") == "exception" or (e.get("kind") == "console" and e.get("level") == "error")]

    def wait_true(self, js, limit=40, step=0.2):
        deadline = time.monotonic() + limit
        while self.ev(js, idempotent=True) != "true":
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timeout waiting for: {js[:100]}")
            time.sleep(step)

    # --- NetSuite --------------------------------------------------------------------------------
    def guard(self, record_type=None, classic=True):
        """Install the dialog guard and enforce the SANDBOX identity gate. Call after every page change.

        classic=False is for pages without nlapiGetContext (suitelets, React pages, Notice pages): they
        pass only on the sandbox host AND after a classic page in this same session already proved
        company + SANDBOX. The host alone is never enough for the first gate.
        """
        state = json.loads(self.ev(GUARD_JS, idempotent=True))
        if not classic:
            if not getattr(self, "identity_proven", False) or not str(state.get("href", "")).startswith(HOST + "/"):
                raise SystemExit(f"IDENTITY GATE (non-classic): refusing to continue on {state}")
            return state
        if state.get("company") != COMPANY or state.get("env") != ENVIRONMENT:
            raise SystemExit(f"IDENTITY GATE: refusing to continue on {state}")
        self.identity_proven = True
        if record_type and state.get("type") != record_type:
            raise SystemExit(f"IDENTITY GATE: expected record type {record_type}, got {state}")
        return state

    def ns_open(self, path, record_type=None, form=True):
        self.nav(path)
        if form:
            self.wait_true(INITED_JS, 45)      # touching a form before this silently drops sourcing
        return self.guard(record_type)

    def alerts(self):
        return json.loads(self.ev("JSON.stringify(window.__alerts||[])", idempotent=True))

    def ns_save(self, limit=90, trusted=False):
        """Click Save once; wait until a NEW document replaced this one, or the form rejected in place.

        An `id=` in the URL proves nothing on an edit form (it is already there), so success is
        "the page-scoped marker is gone AND the new URL has an id". Never retried.
        """
        self.ev("(function(){window.__alerts=[];window.onbeforeunload=null;window.__navmark=1;return 1;})()", idempotent=True)
        if trusted:
            self.click("#submitter")
        else:
            self.ev("(function(){document.getElementById('submitter').click();return 1;})()", idempotent=False)
        deadline = time.monotonic() + limit
        probe = ("(function(){var m=location.href.match(/[?&]id=(\\d+)/);var b=document.querySelector('.uir-alert-box');"
                 "return JSON.stringify({id:(m&&!window.__navmark)?m[1]:null,swapped:!window.__navmark,title:document.title,alerts:window.__alerts||[],"
                 "banner:b?(b.textContent||'').replace(/\\s+/g,' ').slice(0,200):null});})()")
        while True:
            try:
                state = json.loads(self.ev(probe, idempotent=True))
            except RuntimeError:
                state = {"id": None, "alerts": [], "title": ""}          # mid-navigation
            if state.get("id") or state.get("alerts") or state.get("title") == "Error":
                return state
            if time.monotonic() >= deadline:
                # Do NOT call save_record() to diagnose: it is a second real submit. Report and stop.
                state["timeout"] = True
                return state
            time.sleep(0.25)

    def record_xml(self, path, record_id, fields, line_machine=None, line_fields=()):
        """Server-side truth for a record, independent of the rendered DOM."""
        js = ("(async function(){var r=await fetch(%s+'?id='+%s+'&xml=T',{credentials:'same-origin'});"
              "var d=new DOMParser().parseFromString(await r.text(),'text/xml');var o={http:r.status,"
              "recordType:(d.querySelector('record')||{getAttribute:function(){}}).getAttribute('recordType')};"
              "%s.forEach(function(n){var x=d.querySelector('record > '+n);o[n]=x?x.textContent:null;});"
              "var m=%s;if(m){var ls=d.querySelectorAll('machine[name='+m+'] line');o.lines=[];"
              "for(var i=0;i<ls.length;i++){var l={};%s.forEach(function(n){var x=ls[i].querySelector(n);l[n]=x?x.textContent:null;});o.lines.push(l);}}"
              "return JSON.stringify(o);})()") % (json.dumps(path), json.dumps(str(record_id)), json.dumps(list(fields)),
                                                  json.dumps(line_machine), json.dumps(list(line_fields)))
        return json.loads(self.ev(js, idempotent=True))

    def close(self):
        if self.sid and not self.owns_session:
            if self.tab_id:          # shared window: close only our own tab, leave the session to its owner
                subprocess.run(["bsk", "tab", "close", self.tab_id, "--session", self.sid, "--quiet"],
                               env=_ENV, capture_output=True, timeout=30)
            self.sid = self.tab_id = None
            return
        if self.sid:
            subprocess.run(["bsk", "session", "stop", self.sid, "--quiet"], env=_ENV, capture_output=True, timeout=30)
            self.sid = None


def _main(argv):
    """open-shared [name] -> prints the session id to export as NSBSK_SESSION; close-shared <id>."""
    if len(argv) >= 1 and argv[0] == "open-shared":
        args = ["bsk", "session", "start", "--json", "--no-focus", "--browser", BROWSER,
                "--name", argv[1] if len(argv) > 1 else "nsbsk-shared"]
        done = subprocess.run(args, env=_ENV, capture_output=True, text=True, encoding="utf-8", timeout=60)
        if done.returncode != 0:
            raise SystemExit((done.stderr or done.stdout)[-400:])
        print(json.loads(done.stdout)["session_id"])
    elif len(argv) == 2 and argv[0] == "close-shared":
        subprocess.run(["bsk", "session", "stop", argv[1], "--quiet"], env=_ENV, capture_output=True, timeout=30)
        print("closed", argv[1])
    else:
        raise SystemExit("usage: nsbsk.py open-shared [name] | close-shared <session-id>")


if __name__ == "__main__":
    import sys
    _main(sys.argv[1:])
