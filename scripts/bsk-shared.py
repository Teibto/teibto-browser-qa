#!/usr/bin/env python3
"""Answer one question for every agent on this machine: which `bsk` Agent Window do we share?

`--bsk-session` lets runs share a window; this decides *which* window, so an agent no longer has to
open one of its own just because it does not know the id. The registry is a small JSON file per
browser instance outside any repo; it holds an id and who registered it, never a cookie or a token.

    SID=$(python scripts/bsk-shared.py ensure)        # reuse the machine's window, or open it once
    python scripts/flow-runner.py --flow f.yaml --out runs/a --bsk-session "$SID"
    python scripts/bsk-shared.py status               # what is registered, and is it still alive
    python scripts/bsk-shared.py release              # the job owner ends it; attachers never do

Creating the window is serialised with the same cross-process lease the commands use, so several
agents calling `ensure` at the same moment end up with one window, not four.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
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

DEFAULT_ROOT = Path.home() / ".teibto" / "bsk-sessions"
SESSION_NAME = "teibto-shared"


class SharedError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def registry_root() -> Path:
    return Path(os.environ.get("TEIBTO_BSK_SESSION_ROOT") or DEFAULT_ROOT)


def bsk_command(explicit: str | None) -> list[str]:
    candidate = explicit or os.environ.get("TEIBTO_BSK") or shutil.which("bsk")
    if not candidate or not (Path(candidate).is_file() or shutil.which(candidate)):
        raise SharedError("BSK_MISSING", "ไม่พบ bsk: ระบุ --bsk หรือ TEIBTO_BSK หรือเพิ่มใน PATH")
    return [sys.executable, candidate] if str(candidate).endswith(".py") else [candidate]


def run_bsk(bsk: list[str], args: list[str], *, timeout: float = 60.0):
    env = os.environ.copy()
    env["BSK_AUTO_START"] = "0"   # an auto-started daemon inherits our pipes and never lets go
    done = subprocess.run([*bsk, *args, "--json"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=timeout)
    if done.returncode != 0:
        raise SharedError("BSK_COMMAND_FAILED",
                          f"bsk {args[0]}: {(done.stderr or done.stdout).strip()[:300]}")
    try:
        return json.loads(done.stdout) if done.stdout.strip() else {}
    except ValueError as exc:
        raise SharedError("INVALID_OUTPUT", f"bsk {args[0]} คืนค่าที่ไม่ใช่ JSON") from exc


def pick_instance(browsers: list, explicit: str | None) -> str:
    """Which browser are we coordinating? `bsk browsers` is the authoritative list."""
    browsers = browsers or []
    known = ", ".join(str(item.get("instance_id")) for item in browsers)
    if not browsers:
        raise SharedError("BSK_NOT_READY", "ไม่มี browser ที่เชื่อม extension อยู่")
    if explicit:
        if explicit not in [str(item.get("instance_id")) for item in browsers]:
            raise SharedError("BSK_NOT_READY", f"ไม่พบ browser {explicit}; ที่เชื่อมอยู่: {known}")
        return explicit
    if len(browsers) > 1:
        # Same rule as the runner: never guess among shared targets.
        raise SharedError("BSK_BROWSER_AMBIGUOUS", f"มี browser เชื่อมอยู่หลายตัว ระบุ --browser: {known}")
    return str(browsers[0].get("instance_id"))


def live_sessions(status: dict) -> set[str]:
    return {str(item.get("session_id")) for item in (status.get("sessions") or [])}


def read_registry(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_registry(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def ensure(bsk: list[str], instance: str | None, *, focus: bool = False) -> dict:
    instance = pick_instance(run_bsk(bsk, ["browsers"]), instance)
    path = registry_root() / f"{instance}.json"
    # Hold the browser-wide lease while deciding, so two agents cannot each open a window.
    with SessionLease(f"shared-{instance}", wait=120):
        status = run_bsk(bsk, ["status"])
        alive = live_sessions(status)
        entry = read_registry(path)
        if entry and str(entry.get("session_id")) in alive:
            return {**entry, "reused": True}
        args = ["session", "start", "--name", SESSION_NAME, "--browser", instance]
        if not focus:
            args.append("--no-focus")
        started = run_bsk(bsk, args, timeout=90)
        entry = {"session_id": str(started["session_id"]), "browser_instance": instance,
                 "name": SESSION_NAME, "host": socket.gethostname(), "opened_by_pid": os.getpid(),
                 "opened_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        write_registry(path, entry)
        return {**entry, "reused": False}


def status_report(bsk: list[str], instance: str | None) -> dict:
    instance = pick_instance(run_bsk(bsk, ["browsers"]), instance)
    status = run_bsk(bsk, ["status"])
    entry = read_registry(registry_root() / f"{instance}.json")
    session_id = str((entry or {}).get("session_id") or "")
    return {"browser_instance": instance, "registered": entry,
            "alive": bool(session_id) and session_id in live_sessions(status),
            "registry": str(registry_root() / f"{instance}.json")}


def release(bsk: list[str], instance: str | None) -> dict:
    instance = pick_instance(run_bsk(bsk, ["browsers"]), instance)
    path = registry_root() / f"{instance}.json"
    with SessionLease(f"shared-{instance}", wait=120):
        entry = read_registry(path)
        session_id = str((entry or {}).get("session_id") or "")
        stopped = False
        if session_id and session_id in live_sessions(run_bsk(bsk, ["status"])):
            run_bsk(bsk, ["session", "stop", session_id, "--quiet"], timeout=40)
            stopped = True
        path.unlink(missing_ok=True)
        return {"browser_instance": instance, "session_id": session_id or None, "stopped": stopped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("ensure", "status", "release"))
    parser.add_argument("--browser", default=os.environ.get("TEIBTO_BSK_BROWSER"),
                        help="bsk browser instance id; required when several are connected")
    parser.add_argument("--bsk", help="path to the bsk CLI (default: TEIBTO_BSK or PATH)")
    parser.add_argument("--focus", action="store_true",
                        help="let the new Agent Window take focus (default: open it in the background)")
    parser.add_argument("--json", action="store_true", help="print the whole record, not just the id")
    args = parser.parse_args(argv)
    try:
        bsk = bsk_command(args.bsk)
        if args.action == "ensure":
            result = ensure(bsk, args.browser, focus=args.focus)
        elif args.action == "status":
            result = status_report(bsk, args.browser)
        else:
            result = release(bsk, args.browser)
    except SharedError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": str(exc)}}, ensure_ascii=False))
        return 2
    if args.json or args.action != "ensure":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["session_id"])   # the one line a shell wants to capture
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
