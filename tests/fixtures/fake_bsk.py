#!/usr/bin/env python3
"""Minimal BrowserSkill CLI fake; only for runner contract tests.

One process per command, like the real CLI. Every invocation is appended to FAKE_BSK_LOG so a test
can prove which commands ran (or that none did).
"""
import json
import os
import pathlib
import sys

args = [item for item in sys.argv[1:] if item != "--json"]
log = os.environ.get("FAKE_BSK_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(" ".join(args[:2]) + "\n")
        if "--browser" in args:
            handle.write("browser=" + args[args.index("--browser") + 1] + "\n")
version = os.environ.get("FAKE_BSK_VERSION", "0.3.0")
command = args[0]


def flag(name: str) -> str:
    return args[args.index(name) + 1]


if command == "status":
    out = {"daemon_version": version, "pid": 1}
elif command == "browsers":
    # FAKE_BSK_BROWSERS=<id>,<id> models several connected browsers.
    out = [{"instance_id": item, "browser_name": "chrome", "browser_version": "152.0.0.0",
            "extension_version": version}
           for item in os.environ.get("FAKE_BSK_BROWSERS", "only-one").split(",")]
elif command == "session":
    out = {"session_id": "fake-session"} if args[1] == "start" else {}
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
