#!/usr/bin/env python3
"""Minimal BrowserSkill CLI fake; only for runner contract tests.

One process per command, like the real CLI. Every invocation is appended to FAKE_BSK_LOG so a test
can prove which commands ran (or that none did).
"""
import json
import os
import pathlib
import uuid
import sys

args = [item for item in sys.argv[1:] if item != "--json"]
log = os.environ.get("FAKE_BSK_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(" ".join(args[:2]) + "\n")
        if "--browser" in args:
            handle.write("browser=" + args[args.index("--browser") + 1] + "\n")
        if args[0] == "tab" and len(args) > 2 and not args[2].startswith("--"):
            handle.write("tab-target=" + args[2] + "\n")   # `tab select 42` / `tab close 42`
        # Which tab a command was pinned to — `unpinned` is the failure the runner must never show.
        if args[0] not in ("status", "browsers", "session", "tab", "window"):
            handle.write("tab=" + (args[args.index("--tab-id") + 1] if "--tab-id" in args
                                   else "unpinned") + "\n")
version = os.environ.get("FAKE_BSK_VERSION", "0.3.0")


def fail(code: str, message: str) -> None:
    print(json.dumps({"code": code, "message": message, "exit_code": 3}))
    raise SystemExit(3)


# FAKE_BSK_COOPERATE=1 models bsk 0.4 shared control: a page action without `--context` from
# `cooperate sync` is refused before dispatch. FAKE_BSK_COOP_REJECT=<command>:<n> refuses the
# first n context-carrying calls of that command as if the page changed after the sync.
PASSIVE = {"status", "browsers", "daemon", "session", "window", "cooperate", "snapshot",
           "screenshot", "console", "dialog", "operation"}
if os.environ.get("FAKE_BSK_COOPERATE") == "1":
    if args[0] == "cooperate":
        reply = {"ready": True}
        if args[1] == "sync":
            reply["context_id"] = "ctx-" + uuid.uuid4().hex[:6]
        elif args[1] == "status" and os.environ.get("FAKE_BSK_SELF_REVOKE"):
            skew = float(os.environ.get("FAKE_BSK_SELF_REVOKE_SKEW", "0.4"))
            reply["activity"] = [{"type": "pointerdown", "label": "tab", "attribution": {
                "expected_type": "pointerdown", "event_timestamp": 1000.0 - skew,
                "expected_event_time": {"earliest": 1000.0, "latest": 1004.0}}}]
        print(json.dumps(reply))
        raise SystemExit(0)
    # FAKE_BSK_COOP_REJECT_TAB_CREATE=1: the first `tab create` is refused before dispatch because
    # the session's task tab frame is not responding (seen live on 0.4.0).
    if (os.environ.get("FAKE_BSK_COOP_REJECT_TAB_CREATE") == "1" and args[:2] == ["tab", "create"] and log
            and pathlib.Path(log).read_text(encoding="utf-8").splitlines().count("tab create") == 1):
        print(json.dumps({"code": "permission_denied", "exit_code": 1, "message": "A page frame is not responding",
                          "data": {"effect_state": "none", "reason": "cooperation_sync_required"}}))
        raise SystemExit(1)
    acts = (args[0] == "tab" and args[1] == "close") or (args[0] not in PASSIVE and args[0] != "tab")
    if acts:
        if log:
            with open(log, "a", encoding="utf-8") as handle:
                handle.write("context=" + ("yes" if "--context" in args else "none") + "\n")
        reject = os.environ.get("FAKE_BSK_COOP_REJECT", "")
        reject_command, _, reject_count = reject.partition(":")
        refused = "--context" not in args
        if not refused and reject_command == args[0] and log:
            sent = pathlib.Path(log).read_text(encoding="utf-8").splitlines().count(
                args[0] + " " + (args[1] if len(args) > 1 else ""))
            refused = sent <= int(reject_count or "1")
        if refused:
            print(json.dumps({"code": "permission_denied", "exit_code": 1,
                              "message": "This action requires the context returned by the latest cooperate sync",
                              "data": {"effect_state": "none", "reason": "cooperation_sync_required"}}))
            raise SystemExit(1)


# FAKE_BSK_DETACH_ONCE=<command>: the first call of that command fails like a detached debugger.
once = os.environ.get("FAKE_BSK_DETACH_ONCE")
if once == args[0] and log:
    seen = pathlib.Path(log).read_text(encoding="utf-8").splitlines().count(args[0] + " " + (args[1] if len(args) > 1 else ""))
    if seen == 1:
        fail("cdp_failed", "Detached while handling command.")
# FAKE_BSK_RPC_TIMEOUT=<command>: the daemon answers a timeout, which is also what a closed
# Agent Window looks like from the CLI.
rpc_timeout = os.environ.get("FAKE_BSK_RPC_TIMEOUT", "")
rpc_command, _, rpc_mode = rpc_timeout.partition(":")
if rpc_command == args[0]:
    seen = 0
    if log and rpc_mode == "once":
        seen = pathlib.Path(log).read_text(encoding="utf-8").splitlines().count(
            args[0] + " " + (args[1] if len(args) > 1 else ""))
    if rpc_mode != "once" or seen == 1:
        print(json.dumps({"code": "timeout", "message": "tool RPC timed out after 30s", "exit_code": 1}))
        raise SystemExit(1)
# FAKE_BSK_STOPPING=<command>: the daemon is tearing the session down under us.
if os.environ.get("FAKE_BSK_STOPPING") == args[0]:
    print(json.dumps({"code": "timeout", "message": "session is stopping", "exit_code": 4}))
    raise SystemExit(4)
# FAKE_BSK_TAB_GONE=<command>: somebody closed the tab this run owns.
if os.environ.get("FAKE_BSK_TAB_GONE") == args[0]:
    print(json.dumps({"code": "not_found", "message": "No tab with id: 4242.", "exit_code": 1}))
    raise SystemExit(1)
if os.environ.get("FAKE_BSK_SESSION_LOST") == args[0]:
    fail("not_found", "session not registered or already stopped")
if os.environ.get("FAKE_BSK_NO_TAB") == args[0]:
    fail("not_found", "no active tab in Agent Window 1122955421")
# FAKE_BSK_BUSY_ONCE=<command>: the first call of that command is refused like a peer holding the
# session. The daemon rejects such a command before dispatch, so the runner may re-send it.
busy_once = os.environ.get("FAKE_BSK_BUSY_ONCE")
if busy_once == args[0] and log:
    seen = pathlib.Path(log).read_text(encoding="utf-8").splitlines().count(
        args[0] + " " + (args[1] if len(args) > 1 else ""))
    if seen == 1:
        print(json.dumps({"code": "timeout", "message": "session already has an unfinished command",
                          "exit_code": 4, "data": {"reason": "session_busy"}}))
        raise SystemExit(4)
if os.environ.get("FAKE_BSK_EFFECT_UNKNOWN") == args[0]:
    print(json.dumps({"code": "cdp_failed", "message": "Input completed but temporary focus emulation could not be disabled",
                      "data": {"effect_state": "unknown", "reason": "input_cleanup_failed"}, "exit_code": 3}))
    raise SystemExit(3)
command = args[0]
# FAKE_BSK_DIALOG_PENDING=<kind>:<message> models bsk >= protocol 1.5: a click that opens a native
# dialog is suspended (exit 6) until `dialog accept|dismiss`; `operation await` returns its result.
# FAKE_BSK_AWAIT=coverage makes the await fail like 0.4.0 "Page interaction coverage changed".
pending = os.environ.get("FAKE_BSK_DIALOG_PENDING")
if pending and command == "click":
    kind, message = pending.split(":", 1)
    print(json.dumps({"code": "dialog_pending", "exit_code": 6,
                      "message": "Original operation is suspended for a dialog decision; do not repeat it",
                      "data": {"dialog": {"id": "dlg-1", "type": kind, "message": message, "sequence": 1},
                               "dispatched": True, "operation_id": "op-1", "reason": "dialog_pending"}}))
    raise SystemExit(6)
if pending and command == "dialog" and os.environ.get("FAKE_BSK_DECIDE_UNCONFIRMED") == "1":
    print(json.dumps({"code": "cdp_failed", "exit_code": 3, "message": "Browser did not confirm dialog closure"}))
    raise SystemExit(3)
if pending and command == "dialog":
    print(json.dumps({"dialog": {"handled": "accepted" if args[1] == "accept" else "dismissed"}}))
    raise SystemExit(0)
if pending and command == "operation":
    if os.environ.get("FAKE_BSK_AWAIT") == "coverage":
        print(json.dumps({"state": "failed", "operation_id": "op-1", "error": {
            "code": "permission_denied", "message": "Page interaction coverage changed; wait and synchronize",
            "data": {"effect_state": "unknown", "reason": "cooperation_sync_required"}}}))
    else:
        print(json.dumps({"state": "completed", "operation_id": "op-1",
                          "result": {"used_selector": "#tab"}}))
    raise SystemExit(0)
# FAKE_BSK_SELF_REVOKE=<command> models the 0.4.0 mis-attribution: the action lands but is reported
# as revoked by user activity; `cooperate status` then shows bsk's own expected-input attribution.
# FAKE_BSK_SELF_REVOKE_SKEW=<ms> moves the event that far before the expected window.
if os.environ.get("FAKE_BSK_SELF_REVOKE") == command:
    print(json.dumps({"code": "permission_denied", "exit_code": 1, "message": "User activity revoked this action",
                      "data": {"effect_state": "unknown", "reason": "cooperation_sync_required"}}))
    raise SystemExit(1)


def flag(name: str) -> str:
    return args[args.index(name) + 1]


# FAKE_BSK_SESSION_FILE=<path> makes the double remember the sessions it started, so a test can
# watch several processes agree on one shared window.
store = pathlib.Path(os.environ["FAKE_BSK_SESSION_FILE"]) if os.environ.get("FAKE_BSK_SESSION_FILE") else None


def stored() -> list[str]:
    if store is None or not store.exists():
        return []
    return [line for line in store.read_text(encoding="utf-8").splitlines() if line.strip()]


# FAKE_BSK_DAEMONS=1 models one daemon per BSK_HOME (scripts/bsk-account.py): `daemon start` records the
# port in <BSK_HOME>/fake-daemon.json, `status` answers only when that file exists, like a real daemon
# that is or is not listening on the account's named pipe. FAKE_BSK_DAEMON_BROWSERS lists who is connected.
if os.environ.get("FAKE_BSK_DAEMONS") == "1" and command in ("daemon", "status"):
    home = pathlib.Path(os.environ.get("BSK_HOME") or (pathlib.Path.home() / ".bsk"))
    state = home / "fake-daemon.json"
    if command == "daemon":
        home.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"pid": 4000 + len(str(home)), "ws_port": int(flag("--port"))}), encoding="utf-8")
        raise SystemExit(0)
    if not state.exists():
        print(json.dumps({"code": None, "message": "ensure daemon is running: automatic daemon startup is disabled",
                          "exit_code": 2}))
        raise SystemExit(2)
    daemon = json.loads(state.read_text(encoding="utf-8"))
    browsers = [{"instance_id": item} for item in os.environ.get("FAKE_BSK_DAEMON_BROWSERS", "").split(",") if item]
    print(json.dumps({"daemon_version": version, "pid": daemon["pid"], "ws_port": daemon["ws_port"],
                      "browsers": browsers, "sessions": []}))
    raise SystemExit(0)

if command == "status":
    # FAKE_BSK_SESSIONS=<session-id>:<instance-id>,... models sessions another agent already started.
    items = [item for item in os.environ.get("FAKE_BSK_SESSIONS", "").split(",") if item] + stored()
    sessions = [dict(zip(("session_id", "browser_instance_id"), item.split(":")))
                for item in items]
    out = {"daemon_version": version, "pid": 1, "sessions": sessions}
    if "FAKE_BSK_PROTOCOL" in os.environ:
        out["protocol_version"] = os.environ["FAKE_BSK_PROTOCOL"]
elif command == "browsers":
    # FAKE_BSK_BROWSERS=<id>,<id> models several connected browsers.
    out = [{"instance_id": item, "browser_name": "chrome", "browser_version": "152.0.0.0",
            "extension_version": os.environ.get("FAKE_BSK_EXTENSION_VERSION", version)}
           for item in os.environ.get("FAKE_BSK_BROWSERS", "only-one").split(",")]
    for browser in out:
        if "FAKE_BSK_EXTENSION_PROTOCOL" in os.environ:
            browser["extension_protocol_version"] = os.environ["FAKE_BSK_EXTENSION_PROTOCOL"]
        if "FAKE_BSK_VERSION_SKEW" in os.environ:
            browser["version_skew"] = json.loads(os.environ["FAKE_BSK_VERSION_SKEW"])
elif command == "session":
    if args[1] == "start":
        session_id = os.environ.get("FAKE_BSK_SESSION_ID", "fake-session")
        if store is not None:
            # A fresh id per start, so a test can tell a reused window from a replaced one.
            session_id = session_id + "-" + uuid.uuid4().hex[:4]
            instance = args[args.index("--browser") + 1] if "--browser" in args else "only-one"
            with open(store, "a", encoding="utf-8") as handle:
                handle.write(session_id + ":" + instance + "\n")
        out = {"session_id": session_id}
    else:
        if store is not None and len(args) > 2:
            keep = [line for line in stored() if not line.startswith(args[2] + ":")]
            store.write_text("".join(line + "\n" for line in keep), encoding="utf-8")
        out = {}
elif command == "tab":
    out = {"tab_id": os.environ.get("FAKE_BSK_TAB_ID", "4242")} if args[1] == "create" else {}
elif command == "navigate":
    out = {"final_url": args[1], "reached": "load"}
elif command == "click":
    out = {"used_selector": flag("--selector")}
    spec = os.environ.get("FAKE_BSK_DIALOG")   # <kind>:<message>; the real engine always accepts
    if spec:
        kind, message = spec.split(":", 1)
        out["dialogs"] = [{"type": kind, "message": message, "handled": "accepted", "sequence": 1}]
elif command == "evaluate":
    expression = args[1]
    if "__tbqaGuard" in expression:
        out = {"ok": True, "value": "installed"}
    elif "__tbqaDialogs=[]" in expression:   # the in-page drain
        spec = os.environ.get("FAKE_BSK_PAGE_DIALOG")   # <kind>:<message>:<answer>
        if spec:
            kind, message, answer = spec.split(":", 2)
            items = [{"type": kind, "message": message, "answer": answer}]
        else:
            items = []
        out = {"ok": True, "value": json.dumps(items)}
    elif "__never" in expression:
        out = {"ok": True, "value": False}   # a wait condition that never becomes true
    else:
        value = "https://example.test/done" if expression == "location.href" else "saved successfully"
        out = {"ok": True, "value": value}
elif command == "screenshot":
    # FAKE_BSK_STEAL_FOCUS=once|always models a peer that activates its own tab between our
    # `tab select` and our capture, which the real engine answers with `not active`.
    steal = os.environ.get("FAKE_BSK_STEAL_FOCUS")
    if steal and log:
        taken = pathlib.Path(log).read_text(encoding="utf-8").splitlines().count("screenshot --out")
        if steal == "always" or taken == 1:
            print(json.dumps({"code": "invalid_params", "exit_code": 1,
                              "message": "tab is not active; screenshot can only capture the visible tab"}))
            raise SystemExit(1)
    # The real engine captures the visible tab only: a pinned background tab is refused until the
    # caller selects it. Keeping that rule here is what makes #118 a red test instead of an empty
    # shots/ directory nobody notices.
    if log and "--tab-id" in args:
        lines = pathlib.Path(log).read_text(encoding="utf-8").splitlines()
        selected = None
        for index, line in enumerate(lines):
            if line == "tab select" and index + 1 < len(lines) and lines[index + 1].startswith("tab-target="):
                selected = lines[index + 1].split("=", 1)[1]
        if selected != args[args.index("--tab-id") + 1]:
            print(json.dumps({"code": "invalid_params", "exit_code": 1,
                              "message": f"tab {args[args.index('--tab-id') + 1]} is not active; "
                                         "screenshot can only capture the visible tab"}))
            raise SystemExit(1)
    pathlib.Path(flag("--out")).write_bytes(b"png")
    out = {}
elif command == "console":
    # FAKE_BSK_CONSOLE=<msg>|<msg> models real console errors next to the browser-generated log entry.
    out = {"entries": [{"kind": "log", "level": "error", "text": "favicon 404"}]
           + [{"kind": "console", "level": "error", "text": item}
              for item in os.environ.get("FAKE_BSK_CONSOLE", "").split("|") if item],
           "next_since": 1}
else:
    out = {}
print(json.dumps(out))
