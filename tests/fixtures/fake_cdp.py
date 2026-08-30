#!/usr/bin/env python3
"""Minimal cdp.py JSONL protocol fake; only for runner contract tests."""
import json
import os
import pathlib
import sys
import time

target = next((arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("--target-id=")), "")
input_settle = next((arg.split("=", 1)[1] for arg in sys.argv
                     if arg.startswith("--input-settle=")), "fixed")
counter = os.environ.get("FAKE_CDP_COUNTER")
if counter:
    with open(counter, "a", encoding="utf-8") as handle:
        handle.write("start\n")
if os.environ.get("FAKE_CDP_REJECT_INPUT_SETTLE") and input_settle != "fixed":
    print(json.dumps({"type": "error", "ok": False,
                      "error": {"code": "INVALID_ARGS",
                                "message": f"session: flag ไม่รู้จัก: --input-settle={input_settle}",
                                "transient": False}}), flush=True)
    raise SystemExit(2)
print(json.dumps({"type": "ready", "ok": True, "protocol": "teibto-cdp-jsonl",
                  "version": int(os.environ.get("FAKE_CDP_VERSION", "2")),
                  "input_settle": input_settle, "target_id": target, "port": 9222}), flush=True)
values = {}
url = "about:blank"
# FAKE_CDP_DIALOG=<kind>:<message> makes every click raise that dialog; the answer follows the
# DIALOG policy the way cdp.py does (safe = dismiss anything that is not an alert). Like the
# real driver the ledger is printed to stderr at close; FAKE_CDP_DIALOG_WHEN=click prints it
# live instead (a future driver behaviour the runner attributes per step).
dialog_spec = os.environ.get("FAKE_CDP_DIALOG")
dialog_policy = os.environ.get("DIALOG", "safe")
dialog_when = os.environ.get("FAKE_CDP_DIALOG_WHEN", "close")
dialog_ledger = []


def report_dialogs():
    for line in dialog_ledger:
        sys.stderr.write(line)
    sys.stderr.flush()
    dialog_ledger.clear()
for line in sys.stdin:
    request = json.loads(line)
    if request.get("type") == "close":
        print(json.dumps({"type": "closed", "id": request.get("id"), "ok": True,
                          "reason": "requested", "target_id": target}), flush=True)
        report_dialogs()
        break
    command, args = request["command"], request.get("args", [])
    if command == "click" and dialog_spec:
        kind, message = dialog_spec.split(":", 1)
        if dialog_policy == "safe":
            answer = "accept" if kind == "alert" else "dismiss"
        else:
            answer = dialog_policy
        dialog_ledger.append(f"[dialog] {kind}: {message} -> {answer}\n")
        if dialog_when == "click":
            report_dialogs()
    if command == "nav":
        url = args[0]
        data = url
    elif command == "fill":
        values[args[0]] = args[1]
        data = f"filled {args[0]}"
    elif command == "get" and args[0] == "value":
        data = values.get(args[1])
    elif command == "get" and args[0] == "text":
        data = "saved successfully"
    elif command == "url":
        data = url
    elif command == "eval":
        data = ({"href": url, "timeOrigin": 1}
                if "performance.timeOrigin" in args[0] else True)
    elif command == "wait":
        data = True
    elif command == "console":
        data = []
    elif command == "shot":
        time.sleep(float(os.environ.get("FAKE_CDP_SHOT_DELAY_MS", "0")) / 1000)
        pathlib.Path(args[0]).write_bytes(b"PNG")
        data = args[0]
    else:
        data = True
    print(json.dumps({"type": "result", "id": request["id"], "ok": True,
                      "command": command, "target_id": target, "duration_ms": 0.1,
                      "attempts": 1, "data": data}), flush=True)
