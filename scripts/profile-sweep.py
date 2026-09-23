#!/usr/bin/env python3
"""Sweep stale `.qa-profiles` Chrome profiles — safely, and without touching a live one.

A QA run creates a full Chrome user-data-dir per run/agent and nothing prunes it, so the tree
grows silently: the baseline of a brand-new profile is ~215-235 MB of re-downloaded Chrome
components, and a profile that pulls the on-device model adds ~4 GB on top (`gotchas.md` §10).

The sweep is deliberately conservative, because a profile is not just disk — it may hold a login
that cost an MFA round-trip:

  * dry-run is the default; only `--apply` deletes anything;
  * a profile is **never** swept while a Chrome process is using it (matched from the process's
    own `--user-data-dir=`);
  * a profile touched within `--keep-days` is kept;
  * a profile carrying a `.keep` marker is kept, as is any name in `--protect`.

    python scripts/profile-sweep.py --profiles-dir .qa-profiles                 # report only
    python scripts/profile-sweep.py --profiles-dir .qa-profiles --apply         # sweep old ones
    python scripts/profile-sweep.py --profiles-dir .qa-profiles --only run-x --apply --force
                                                                                # post-run hook
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

PROFILES_DIRNAME = ".qa-profiles"
KEEP_MARKERS = (".keep", "KEEP")
DEFAULT_KEEP_DAYS = 3
USER_DATA_RE = re.compile(r'--user-data-dir=(?:"([^"]+)"|(\S+))')


@dataclass
class Process:
    pid: int
    cmdline: str


@dataclass
class Profile:
    path: Path
    name: str
    bytes: int = 0
    last_touched: float = 0.0
    decision: str = "sweep"          # sweep | keep
    reasons: list[str] = field(default_factory=list)
    in_use_pids: list[int] = field(default_factory=list)

    @property
    def mib(self) -> float:
        return round(self.bytes / (1024 * 1024), 1)


def parse_user_data_dirs(processes: list[Process]) -> list[tuple[int, Path]]:
    """Every `--user-data-dir=` found in a process command line, as (pid, path)."""
    found: list[tuple[int, Path]] = []
    for process in processes:
        for match in USER_DATA_RE.finditer(process.cmdline or ""):
            raw = match.group(1) or match.group(2)
            if raw:
                found.append((process.pid, Path(raw)))
    return found


def list_processes() -> list[Process]:
    """Best-effort process list with command lines. Failure returns an empty list, which makes the
    sweep treat nothing as in-use — so a caller that expects the guard must not ignore a probe
    error silently. `--strict-probe` turns the empty result into a hard failure instead."""
    try:
        if sys.platform == "win32":
            script = (
                "Get-CimInstance Win32_Process | "
                "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"
            )
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=60,
            ).stdout
        else:
            out = subprocess.run(
                ["ps", "-eo", "pid=,args="], capture_output=True, text=True, timeout=60,
            ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    processes: list[Process] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        head, _, rest = line.partition("\t" if "\t" in line else " ")
        try:
            pid = int(head)
        except ValueError:
            continue
        processes.append(Process(pid=pid, cmdline=rest.strip()))
    return processes


def _same_or_inside(child: Path, parent: Path) -> bool:
    try:
        child = child.resolve()
        parent = parent.resolve()
    except OSError:
        return False
    return child == parent or parent in child.parents


def profile_size_and_touch(path: Path) -> tuple[int, float]:
    """Total bytes and the newest mtime under a profile (Chrome keeps touching its files while the
    browser is alive, so the newest mtime is the closest thing to 'last used')."""
    total = 0
    newest = 0.0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        else:
                            stat = entry.stat(follow_symlinks=False)
                            total += stat.st_size
                            newest = max(newest, stat.st_mtime)
                    except OSError:
                        continue
        except OSError:
            continue
    if newest == 0.0:
        try:
            newest = path.stat().st_mtime
        except OSError:
            newest = 0.0
    return total, newest


def classify(profile: Profile, *, in_use: list[tuple[int, Path]], keep_days: float,
             now: float, protect: list[str], force: bool) -> Profile:
    """Decide keep vs sweep, and record every reason so the report never has to guess."""
    profile.bytes, profile.last_touched = profile_size_and_touch(profile.path)

    pids = [pid for pid, used in in_use if _same_or_inside(profile.path, used)
            or _same_or_inside(used, profile.path)]
    if pids:
        profile.in_use_pids = sorted(set(pids))
        profile.decision = "keep"
        profile.reasons.append(f"in use by pid {', '.join(map(str, profile.in_use_pids))}")
        return profile

    if any((profile.path / marker).exists() for marker in KEEP_MARKERS):
        profile.decision = "keep"
        profile.reasons.append("has .keep marker")
        return profile

    for pattern in protect:
        if fnmatch.fnmatch(profile.name, pattern):
            profile.decision = "keep"
            profile.reasons.append(f"matched --protect {pattern!r}")
            return profile

    age_days = (now - profile.last_touched) / 86400.0 if profile.last_touched else None
    if not force and age_days is not None and age_days < keep_days:
        profile.decision = "keep"
        profile.reasons.append(f"touched {age_days:.1f}d ago (< {keep_days:g}d)")
        return profile

    if age_days is None:
        profile.reasons.append("no readable timestamps")
    else:
        profile.reasons.append(f"stale {age_days:.1f}d")
    profile.decision = "sweep"
    return profile


def discover(roots: list[Path], explicit: list[Path], max_depth: int) -> list[Path]:
    """All `.qa-profiles` directories: the explicit ones plus any found under each root."""
    found: list[Path] = [p for p in explicit if p.is_dir()]
    seen = {p.resolve() for p in found}
    for root in roots:
        if not root.is_dir():
            continue
        base_depth = len(root.resolve().parts)
        for current, dirnames, _ in os.walk(root):
            here = Path(current)
            if len(here.resolve().parts) - base_depth > max_depth:
                dirnames[:] = []
                continue
            if here.name == PROFILES_DIRNAME:
                resolved = here.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    found.append(here)
                dirnames[:] = []          # do not descend into a profiles tree
    return found


def sweep(profiles_dir: Path, *, processes: list[Process] | None = None, keep_days: float,
          protect: list[str], only: list[str], force: bool, apply: bool,
          now: float | None = None) -> list[Profile]:
    now = time.time() if now is None else now
    in_use = parse_user_data_dirs(list_processes() if processes is None else processes)

    profiles: list[Profile] = []
    for child in sorted(profiles_dir.iterdir()):
        if not child.is_dir():
            continue
        if only and child.name not in only:
            continue
        profile = Profile(path=child, name=child.name)
        classify(profile, in_use=in_use, keep_days=keep_days, now=now,
                 protect=protect, force=force)
        if profile.decision == "sweep" and apply:
            shutil.rmtree(child, ignore_errors=True)
            if child.exists():
                profile.decision = "keep"
                profile.reasons.append("delete failed (still present, likely locked)")
        profiles.append(profile)
    return profiles


def report(profiles: list[Profile], *, apply: bool, as_json: bool) -> None:
    swept = [p for p in profiles if p.decision == "sweep"]
    freed = sum(p.bytes for p in swept)
    if as_json:
        print(json.dumps({
            "mode": "apply" if apply else "dry-run",
            "sweep": [{"name": p.name, "mib": p.mib, "reasons": p.reasons} for p in swept],
            "keep": [{"name": p.name, "mib": p.mib, "reasons": p.reasons} for p in profiles
                     if p.decision == "keep"],
            "freed_mib": round(freed / (1024 * 1024), 1),
        }, ensure_ascii=False, indent=2))
        return

    verb = "swept" if apply else "would sweep"
    for profile in sorted(profiles, key=lambda p: p.bytes, reverse=True):
        mark = "-" if profile.decision == "sweep" else "="
        print(f"  {mark} {profile.name:<32} {profile.mib:>9.1f} MiB  ({'; '.join(profile.reasons)})")
    print(f"\n{verb} {len(swept)} profile(s), {freed / (1024 * 1024):.1f} MiB "
          f"{'freed' if apply else 'recoverable'}"
          f"{'' if apply else ' (dry-run; pass --apply to delete)'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", action="append", default=[], type=Path,
                        help=f"directory to search for {PROFILES_DIRNAME}/ (repeatable)")
    parser.add_argument("--profiles-dir", action="append", default=[], type=Path,
                        help=f"an explicit {PROFILES_DIRNAME}/ directory (repeatable)")
    parser.add_argument("--max-depth", type=int, default=3,
                        help="how deep to search under each --root (default 3)")
    parser.add_argument("--keep-days", type=float, default=DEFAULT_KEEP_DAYS,
                        help=f"keep profiles touched within this many days (default {DEFAULT_KEEP_DAYS})")
    parser.add_argument("--protect", action="append", default=[],
                        help="glob of profile names to always keep (repeatable)")
    parser.add_argument("--only", action="append", default=[],
                        help="restrict to these profile names (repeatable; for a post-run hook)")
    parser.add_argument("--force", action="store_true",
                        help="ignore --keep-days (still respects in-use, .keep and --protect)")
    parser.add_argument("--apply", action="store_true",
                        help="actually delete; without this the run is a dry-run")
    parser.add_argument("--strict-probe", action="store_true",
                        help="fail instead of assuming nothing is in use when the process probe fails")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    args = parser.parse_args(argv)

    roots = args.root or ([] if args.profiles_dir else [Path.cwd()])
    dirs = discover(roots, args.profiles_dir, args.max_depth)
    if not dirs:
        print(f"no {PROFILES_DIRNAME}/ found under "
              f"{', '.join(str(r) for r in roots) or ', '.join(str(d) for d in args.profiles_dir)}")
        return 0

    processes = list_processes()
    if not processes:
        message = ("process probe returned nothing; cannot tell whether a profile is in use")
        if args.strict_probe:
            print(f"{message} (--strict-probe)", file=sys.stderr)
            return 2
        print(f"warning: {message}; treating nothing as in use", file=sys.stderr)

    for profiles_dir in dirs:
        if not args.json:
            print(f"\n{profiles_dir}")
        profiles = sweep(profiles_dir, processes=processes, keep_days=args.keep_days,
                         protect=args.protect, only=args.only, force=args.force, apply=args.apply)
        report(profiles, apply=args.apply, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
