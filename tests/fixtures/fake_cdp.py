#!/usr/bin/env python3
"""Minimal cdp.py JSONL protocol fake; only for runner contract tests."""
import json
import os
import pathlib
import sys

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
for line in sys.stdin:
    request = json.loads(line)
    if request.get("type") == "close":
        print(json.dumps({"type": "closed", "id": request.get("id"), "ok": True,
                          "reason": "requested", "target_id": target}), flush=True)
        break
    command, args = request["command"], request.get("args", [])
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
        pathlib.Path(args[0]).write_bytes(b"PNG")
        data = args[0]
    else:
        data = True
    print(json.dumps({"type": "result", "id": request["id"], "ok": True,
                      "command": command, "target_id": target, "duration_ms": 0.1,
                      "attempts": 1, "data": data}), flush=True)
