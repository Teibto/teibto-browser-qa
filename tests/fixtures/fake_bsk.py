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
        # Which tab a command was pinned to — `unpinned` is the failure the runner must never show.
        if args[0] not in ("status", "browsers", "session", "tab", "window"):
            handle.write("tab=" + (args[args.index("--tab-id") + 1] if "--tab-id" in args
                                   else "unpinned") + "\n")
version = os.environ.get("FAKE_BSK_VERSION", "0.3.0")


def fail(code: str, message: str) -> None:
    print(json.dumps({"code": code, "message": message, "exit_code": 3}))
    raise SystemExit(3)


# FAKE_BSK_DETACH_ONCE=<command>: the first call of that command fails like a detached debugger.
once = os.environ.get("FAKE_BSK_DETACH_ONCE")
if once == args[0] and log:
    seen = pathlib.Path(log).read_text(encoding="utf-8").splitlines().count(args[0] + " " + (args[1] if len(args) > 1 else ""))
    if seen == 1:
        fail("cdp_failed", "Detached while handling command.")
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


def flag(name: str) -> str:
    return args[args.index(name) + 1]


# FAKE_BSK_SESSION_FILE=<path> makes the double remember the sessions it started, so a test can
# watch several processes agree on one shared window.
store = pathlib.Path(os.environ["FAKE_BSK_SESSION_FILE"]) if os.environ.get("FAKE_BSK_SESSION_FILE") else None


def stored() -> list[str]:
    if store is None or not store.exists():
        return []
    return [line for line in store.read_text(encoding="utf-8").splitlines() if line.strip()]


if command == "status":
    # FAKE_BSK_SESSIONS=<session-id>:<instance-id>,... models sessions another agent already started.
    items = [item for item in os.environ.get("FAKE_BSK_SESSIONS", "").split(",") if item] + stored()
    sessions = [dict(zip(("session_id", "browser_instance_id"), item.split(":")))
                for item in items]
    out = {"daemon_version": version, "pid": 1, "sessions": sessions}
elif command == "browsers":
    # FAKE_BSK_BROWSERS=<id>,<id> models several connected browsers.
    out = [{"instance_id": item, "browser_name": "chrome", "browser_version": "152.0.0.0",
            "extension_version": version}
           for item in os.environ.get("FAKE_BSK_BROWSERS", "only-one").split(",")]
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
    else:
        value = "https://example.test/done" if expression == "location.href" else "saved successfully"
        out = {"ok": True, "value": value}
elif command == "screenshot":
    pathlib.Path(flag("--out")).write_bytes(b"png")
    out = {}
elif command == "console":
    out = {"entries": [{"kind": "log", "level": "error", "text": "favicon 404"}], "next_since": 1}
else:
    out = {}
print(json.dumps(out))
