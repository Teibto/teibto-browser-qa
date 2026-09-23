#!/usr/bin/env python3
"""Give every customer account its own `bsk` daemon, so parallel projects stop sharing one session.

One daemon on the default port is shared by every agent on the machine. With several projects open at
once their sessions pile onto the same daemon and the same browser profile, and a NetSuite login from one
project throws out another's. This script keeps one daemon per account: its own `BSK_HOME` (so its own
named pipe and lock), its own WebSocket port, and its own shared-window registry for `bsk-shared.py`.

    python scripts/bsk-account.py ensure foodstar            # start (or reuse) the account's daemon
    eval "$(python scripts/bsk-account.py env foodstar)"     # bash: point bsk + bsk-shared.py at it
    python scripts/bsk-account.py env foodstar --shell pwsh | Invoke-Expression
    python scripts/bsk-account.py status                     # every account, its port, who is connected

The browser side is manual and cannot be scripted: open a Chrome profile for the account, set the
BrowserSkill extension's "Local port" to the account's port and press Save. The registry holds names,
ports and paths only - never a cookie or a token.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

DEFAULT_PORT = 52800          # the shared daemon every project falls back to; never handed to an account
FIRST_ACCOUNT_PORT = 52810
PORT_STEP = 10
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


class AccountError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def teibto_root() -> Path:
    return Path(os.environ.get("TEIBTO_BSK_ACCOUNT_ROOT") or (Path.home() / ".teibto"))


def registry_path() -> Path:
    return teibto_root() / "bsk-accounts.json"


def load_registry() -> dict:
    try:
        data = json.loads(registry_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_registry(data: dict) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def check_name(name: str) -> str:
    name = (name or "").strip().lower()
    if not NAME_RE.match(name):
        raise AccountError("BAD_ACCOUNT", "ชื่อ account ต้องเป็น a-z 0-9 _ - (ขึ้นต้นด้วยตัวอักษรหรือตัวเลข, ไม่เกิน 40 ตัว)")
    return name


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def allocate(name: str, registry: dict, port: int | None, bsk_home: str | None = None) -> dict:
    """Existing entry wins; otherwise the next unused port from 52810 in steps of 10.

    `bsk_home` adopts a daemon home that already exists (one started by hand before this script), so the
    running daemon is reused instead of a second one being started for the same account.
    """
    if name in registry:
        entry = registry[name]
        if bsk_home and Path(bsk_home) != Path(entry["bsk_home"]):
            raise AccountError("HOME_CONFLICT", f"account {name} ใช้ BSK_HOME {entry['bsk_home']} อยู่แล้ว")
        if port and int(port) != int(entry["port"]):
            raise AccountError("PORT_CONFLICT", f"account {name} ใช้ port {entry['port']} อยู่แล้ว; "
                                                "เปลี่ยน port ต้องแก้ส่วนเสริมใน Chrome ด้วย จึงไม่เปลี่ยนให้เงียบ ๆ")
        return entry
    taken = {int(item["port"]) for item in registry.values()} | {DEFAULT_PORT}
    if port:
        if int(port) in taken:
            raise AccountError("PORT_CONFLICT", f"port {port} ถูกใช้โดย account อื่นหรือเป็น port กลาง {DEFAULT_PORT}")
        chosen = int(port)
    else:
        chosen = FIRST_ACCOUNT_PORT
        while chosen in taken or not port_free(chosen):
            chosen += PORT_STEP
    home = Path(bsk_home) if bsk_home else teibto_root() / "bsk-homes" / name
    entry = {"port": chosen, "bsk_home": str(home),
             "session_root": str(teibto_root() / "bsk-sessions" / name),
             "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    registry[name] = entry
    save_registry(registry)
    return entry


def bsk_command(explicit: str | None) -> list[str]:
    candidate = explicit or os.environ.get("TEIBTO_BSK") or shutil.which("bsk")
    if not candidate or not (Path(candidate).is_file() or shutil.which(candidate)):
        raise AccountError("BSK_MISSING", "ไม่พบ bsk: ระบุ --bsk หรือ TEIBTO_BSK หรือเพิ่มใน PATH")
    return [sys.executable, candidate] if str(candidate).endswith(".py") else [candidate]


def account_env(entry: dict) -> dict[str, str]:
    env = os.environ.copy()
    env["BSK_HOME"] = entry["bsk_home"]
    env["BSK_AUTO_START"] = "0"   # an auto-started daemon inherits our pipes and lands on the default port
    return env


def daemon_status(bsk: list[str], entry: dict) -> dict | None:
    """`bsk status` under the account's BSK_HOME; None when no daemon answers there."""
    done = subprocess.run([*bsk, "status", "--json"], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=account_env(entry), timeout=20)
    try:
        data = json.loads(done.stdout) if done.stdout.strip() else {}
    except ValueError:
        return None
    return data if done.returncode == 0 and data.get("pid") else None


def start_daemon(bsk: list[str], entry: dict, log_path: Path) -> None:
    """Detached `daemon start --foreground`: the process must outlive us and must not hold our pipes."""
    Path(entry["bsk_home"]).mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {"env": account_env(entry), "stdin": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0x8)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200))
    else:
        kwargs["start_new_session"] = True
    with open(log_path, "ab") as log:
        subprocess.Popen([*bsk, "daemon", "start", "--port", str(entry["port"]), "--foreground"],
                         stdout=log, stderr=log, **kwargs)


def summarize(name: str, entry: dict, status: dict | None) -> dict:
    browsers = (status or {}).get("browsers") or []
    out = {"account": name, "port": entry["port"], "bsk_home": entry["bsk_home"],
           "session_root": entry["session_root"], "running": bool(status),
           "pid": (status or {}).get("pid"), "ws_port": (status or {}).get("ws_port"),
           "browsers": [str(item.get("instance_id")) for item in browsers],
           "sessions": len((status or {}).get("sessions") or [])}
    if status and not browsers:
        out["next"] = (f"ยังไม่มี browser ต่อเข้า port {entry['port']}: เปิด Chrome โปรไฟล์ของ account นี้ "
                       f"-> ส่วนเสริม BrowserSkill -> Local port = {entry['port']} -> Save port")
    return out


def ensure(bsk: list[str], name: str, port: int | None, wait: float, bsk_home: str | None = None) -> dict:
    registry = load_registry()
    entry = allocate(name, registry, port, bsk_home)
    status = daemon_status(bsk, entry)
    if status and int(status.get("ws_port") or 0) != int(entry["port"]):
        raise AccountError("PORT_MISMATCH", f"daemon ของ {name} ฟังอยู่ที่ port {status.get('ws_port')} "
                                            f"ไม่ใช่ {entry['port']}: หยุด daemon นั้นก่อน (bsk daemon stop ด้วย BSK_HOME เดียวกัน)")
    started = False
    if not status:
        if not port_free(int(entry["port"])):
            raise AccountError("PORT_BUSY", f"port {entry['port']} มีโปรแกรมอื่นใช้อยู่ แต่ไม่ใช่ daemon ของ {name}")
        start_daemon(bsk, entry, Path(entry["bsk_home"]) / "daemon-console.log")
        started = True
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            status = daemon_status(bsk, entry)
            if status:
                break
            time.sleep(0.5)
        if not status:
            raise AccountError("DAEMON_NOT_READY", f"daemon ของ {name} ไม่ตอบภายใน {wait:.0f}s; "
                                                   f"ดู {Path(entry['bsk_home']) / 'daemon-console.log'}")
    return {**summarize(name, entry, status), "started": started}


def env_lines(entry: dict, shell: str) -> str:
    values = {"BSK_HOME": entry["bsk_home"], "BSK_AUTO_START": "0",
              "TEIBTO_BSK_SESSION_ROOT": entry["session_root"]}
    if shell == "json":
        return json.dumps(values, ensure_ascii=False, indent=2)
    if shell == "pwsh":
        return "\n".join(f"$env:{key} = '{value}'" for key, value in values.items())
    return "\n".join(f"export {key}='{value}'" for key, value in values.items())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("ensure", "env", "status"))
    parser.add_argument("account", nargs="?", help="account name, e.g. foodstar (required for ensure/env)")
    parser.add_argument("--port", type=int, help="port for a NEW account (default: next free from 52810)")
    parser.add_argument("--bsk-home", help="adopt an existing BSK_HOME for a NEW account (reuses its running daemon)")
    parser.add_argument("--shell", choices=("bash", "pwsh", "json"), default="bash", help="env output format")
    parser.add_argument("--wait", type=float, default=20.0, help="seconds to wait for a started daemon")
    parser.add_argument("--bsk", help="path to the bsk CLI (default: TEIBTO_BSK or PATH)")
    args = parser.parse_args(argv)
    try:
        if args.action in ("ensure", "env") and not args.account:
            raise AccountError("BAD_ACCOUNT", f"{args.action} ต้องระบุชื่อ account")
        if args.action == "env":
            name = check_name(args.account)
            entry = load_registry().get(name)
            if not entry:
                raise AccountError("UNKNOWN_ACCOUNT", f"ยังไม่มี account {name}: รัน ensure ก่อน")
            print(env_lines(entry, args.shell))
            return 0
        bsk = bsk_command(args.bsk)
        if args.action == "ensure":
            result = ensure(bsk, check_name(args.account), args.port, args.wait, args.bsk_home)
        else:
            registry = load_registry()
            names = [check_name(args.account)] if args.account else sorted(registry)
            result = [summarize(n, registry[n], daemon_status(bsk, registry[n])) for n in names if n in registry]
    except AccountError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": str(exc)}}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
