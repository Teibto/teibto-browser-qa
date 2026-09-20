#!/usr/bin/env python3
"""Replay what several agents actually do to one browser, and fail when sharing stops holding.

Unit tests cannot see this class of defect: every one of #118, #120, #122 and #124 was green in
`tests/` while a real run photographed a colleague's page or died on a peer's tab switch. This
harness drives `flow-runner.py` through `bsk` for real and checks the outcome, including **which
page ended up in the screenshot** — a run that quietly captures somebody else's tab is the failure
that matters most, and it is invisible to an exit code.

    python self-test/engine2/contention-matrix.py                 # all scenarios
    python self-test/engine2/contention-matrix.py s01 s04         # a subset
    ENGINE2_BROWSER=<instance_id> python self-test/engine2/contention-matrix.py

It never touches the Agent Window this machine shares: the registry and the lease directory are
redirected into a temporary directory, so every session it uses is its own and is stopped on the way
out. Missing `bsk`, daemon or browser is an explicit SKIP, never a silent pass.
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RUNNER = ROOT / "scripts" / "flow-runner.py"
COORDINATOR = ROOT / "scripts" / "bsk-shared.py"
FLOW, FLOW_SLOW = HERE / "flow-own.yaml", HERE / "flow-slow.yaml"
ENV_BASE = {**os.environ, "BSK_AUTO_START": "0"}
# Each fixture page is one flat colour, so a screenshot says who owns the page it shows.
COLOURS = {"A": (192, 57, 43), "B": (39, 174, 96), "C": (41, 128, 185),
           "D": (142, 68, 173), "E": (211, 84, 0), "F": (22, 160, 133)}
RESULTS: list[tuple[str, str, str]] = []
OPENED: set[str] = set()          # every window this harness opened, so none of them outlives it
BASE_URL = ""
ENV: dict[str, str] = {}


def skip(reason: str) -> None:
    print(f"SKIP: {reason}")
    raise SystemExit(0)


def bsk(args: list[str], timeout: float = 90) -> dict:
    done = subprocess.run(["bsk", *args, "--json"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=ENV, timeout=timeout)
    payload: object = None
    if done.stdout.strip():
        try:
            payload = json.loads(done.stdout)
        except ValueError:
            payload = done.stdout[:300]
    return {"rc": done.returncode, "out": payload}


def coordinator(action: str, *extra: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(COORDINATOR), action, *extra],
                          capture_output=True, text=True, encoding="utf-8",
                          env=env or ENV, timeout=180)


def ensure(env: dict | None = None) -> str:
    done = coordinator("ensure", env=env)
    if done.returncode != 0:
        raise RuntimeError(f"bsk-shared ensure failed: {done.stdout}{done.stderr}")
    session_id = done.stdout.strip()
    OPENED.add(session_id)        # S06/S07 replace the registered window; none may be left behind
    return session_id


def run_flow(worker: str, out: Path, *extra: str, env: dict | None = None,
             flow: Path | None = None, timeout: float = 300):
    shutil.rmtree(out, ignore_errors=True)
    done = subprocess.run(
        [sys.executable, str(RUNNER), "--flow", str(flow or FLOW), "--out", str(out),
         "--vars-json", json.dumps({"worker": worker, "base_url": BASE_URL}),
         "--stdout", "summary", *extra],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env or ENV, timeout=timeout)
    final: dict = {}
    for line in done.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                final = json.loads(line)
            except ValueError:
                pass
    return done, final


def error_codes(out: Path) -> list[str]:
    log = out / "run-log.jsonl"
    if not log.exists():
        return []
    codes = []
    for line in log.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        code = (event.get("error") or {}).get("code")
        if code:
            codes.append(code)
    return codes


def own_tab(out: Path) -> str | None:
    log = out / "run-log.jsonl"
    if not log.exists():
        return None
    for line in log.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("type") == "session_ready" and event.get("tab_id"):
            return str(event["tab_id"])
    return None


def whose_page(path: Path) -> str:
    """Which worker's page is in this screenshot? Unknown without Pillow — say so, never assume."""
    if not path.is_file():
        return "(missing)"
    try:
        from PIL import Image
    except ImportError:
        return "(no pillow)"
    with Image.open(path) as image:
        pixel = image.convert("RGB").resize((1, 1)).getpixel((0, 0))
    best, distance = "(unknown)", 1e9
    for name, colour in COLOURS.items():
        gap = sum((pixel[index] - colour[index]) ** 2 for index in range(3))
        if gap < distance:
            best, distance = name, gap
    return best if distance < 12000 else f"(unknown rgb={pixel})"


def shows_own_page(out: Path, worker: str) -> tuple[bool, str]:
    seen = whose_page(out / "shots" / "own-02.png")
    if seen == "(no pillow)":
        return True, "colour check skipped (no Pillow)"
    return seen == worker, f"shot shows {seen}"


def record(name: str, ok: bool, evidence: str) -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL", evidence))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {evidence}", flush=True)


# --- scenarios ----------------------------------------------------------------------------------
def s01_two_runs_share_one_window(work: Path) -> None:
    """Two agents in one Agent Window: each drives its own tab and photographs its own page."""
    sid = ensure()
    results: dict[str, tuple] = {}
    threads = [threading.Thread(target=lambda w=w: results.__setitem__(
        w, run_flow(w, work / f"s01-{w}", "--bsk-session", sid))) for w in ("A", "B")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    verdicts = {w: results[w][1].get("verdict") for w in ("A", "B")}
    owns = {w: shows_own_page(work / f"s01-{w}", w) for w in ("A", "B")}
    ok = all(v == "PASS" for v in verdicts.values()) and all(item[0] for item in owns.values())
    record("S01 two runs share one window", ok,
           f"verdicts={verdicts} " + " ".join(f"{w}:{owns[w][1]}" for w in owns))


def s02_six_runs_share_one_window(work: Path) -> None:
    """Six at once: the lease has to hold, and nobody may see a raw session_busy."""
    sid = ensure()
    workers = ["A", "B", "C", "D", "E", "F"]
    results: dict[str, tuple] = {}
    started = time.perf_counter()
    threads = [threading.Thread(target=lambda w=w: results.__setitem__(
        w, run_flow(w, work / f"s02-{w}", "--bsk-session", sid))) for w in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = round(time.perf_counter() - started, 1)
    verdicts = {w: results[w][1].get("verdict") for w in workers}
    sharing = [results[w][1].get("session_sharing", {}) for w in workers]
    busy = sum(item.get("busy_waits", 0) for item in sharing)
    waits = sorted(round(item.get("lease_wait_ms", 0)) for item in sharing)
    ok = all(v == "PASS" for v in verdicts.values()) and busy == 0
    record("S02 six runs share one window", ok,
           f"wall={wall}s pass={sum(1 for v in verdicts.values() if v == 'PASS')}/6 "
           f"busy_waits={busy} lease_waits_ms={waits}")


def s03_peer_opens_a_focused_tab(work: Path) -> None:
    """A peer's `tab create` takes focus by default; a pinned run must not follow it."""
    sid = ensure()
    box: dict[str, tuple] = {}
    worker = threading.Thread(
        target=lambda: box.__setitem__("result", run_flow("A", work / "s03-A", "--bsk-session", sid)))
    worker.start()
    time.sleep(1.2)
    peer = bsk(["tab", "create", "--session", sid, "--url", f"{BASE_URL}/page.html?w=B"])
    worker.join()
    _, final = box["result"]
    if isinstance(peer["out"], dict) and peer["out"].get("tab_id"):
        bsk(["tab", "close", str(peer["out"]["tab_id"]), "--session", sid, "--quiet"])
    owns, detail = shows_own_page(work / "s03-A", "A")
    record("S03 peer opens a focused tab mid-run",
           final.get("verdict") == "PASS" and owns, f"verdict={final.get('verdict')} {detail}")


def s04_peer_keeps_taking_focus(work: Path) -> None:
    """A peer that re-activates its tab every 150 ms costs retries, not the run."""
    sid = ensure()
    peer = bsk(["tab", "create", "--session", sid, "--no-active", "--url", f"{BASE_URL}/page.html?w=B"])
    peer_tab = str((peer["out"] or {}).get("tab_id") or "")
    if not peer_tab:
        record("S04 peer keeps taking focus", False, f"could not open the peer tab: {peer}")
        return
    stop = threading.Event()

    def churn() -> None:
        while not stop.is_set():
            bsk(["tab", "select", peer_tab, "--session", sid])
            time.sleep(0.15)

    noisy = threading.Thread(target=churn, daemon=True)
    noisy.start()
    try:
        _, final = run_flow("A", work / "s04-A", "--bsk-session", sid)
    finally:
        stop.set()
        noisy.join(timeout=10)
    bsk(["tab", "close", peer_tab, "--session", sid, "--quiet"])
    owns, detail = shows_own_page(work / "s04-A", "A")
    record("S04 peer keeps taking focus",
           final.get("verdict") == "PASS" and owns, f"verdict={final.get('verdict')} {detail}")


def s05_window_stopped_mid_run(work: Path) -> None:
    """A stopped window must be reported as a lost session, not as a slow browser."""
    sid = ensure()
    box: dict[str, tuple] = {}
    worker = threading.Thread(
        target=lambda: box.__setitem__("result", run_flow(
            "A", work / "s05-A", "--bsk-session", sid, flow=FLOW_SLOW)))
    worker.start()
    time.sleep(4.0)                       # the fixture is only ready after 8 s
    bsk(["session", "stop", sid, "--quiet"])
    worker.join()
    _, final = box["result"]
    codes = error_codes(work / "s05-A")
    record("S05 window stopped mid-run", "BSK_SESSION_LOST" in codes,
           f"verdict={final.get('verdict')} codes={codes}")


def s06_registry_points_at_a_dead_session(work: Path) -> None:
    """The daemon reaps idle windows; `ensure` must notice instead of handing out a corpse."""
    sid = ensure()
    bsk(["session", "stop", sid, "--quiet"])
    again = ensure()
    alive = json.loads(coordinator("status").stdout)["alive"]
    record("S06 registry points at a dead session", again != sid and alive,
           f"old={sid} new={again} alive={alive}")


def s07_corrupt_registry(work: Path) -> None:
    """A half-written registry file must not wedge every agent on the machine."""
    path = Path(json.loads(coordinator("status").stdout)["registry"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"session_id": "trunc', encoding="utf-8")
    sid = ensure()
    alive = json.loads(coordinator("status").stdout)["alive"]
    record("S07 corrupt registry recovers", bool(sid) and alive, f"session={sid} alive={alive}")


def s08_stale_session_in_the_environment(work: Path) -> None:
    """A session id left over from yesterday must fail closed, not attach to a stranger."""
    _, final = run_flow("A", work / "s08-A", env={**ENV, "TEIBTO_BSK_SESSION": "zzzz"})
    codes = error_codes(work / "s08-A")
    record("S08 stale TEIBTO_BSK_SESSION fails closed", "BSK_SESSION_MISSING" in codes,
           f"verdict={final.get('verdict')} codes={codes}")


def s09_lease_holder_killed(work: Path) -> None:
    """A run killed while holding the lease must not wedge the window for the next agent."""
    sid = ensure()
    shutil.rmtree(work / "s09-victim", ignore_errors=True)
    victim = subprocess.Popen(
        [sys.executable, str(RUNNER), "--flow", str(FLOW), "--out", str(work / "s09-victim"),
         "--vars-json", json.dumps({"worker": "B", "base_url": BASE_URL}),
         "--stdout", "summary", "--bsk-session", sid],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=ENV)
    time.sleep(1.6)
    victim.kill()
    victim.wait(timeout=30)
    started = time.perf_counter()
    _, final = run_flow("A", work / "s09-A", "--bsk-session", sid)
    took = round(time.perf_counter() - started, 1)
    record("S09 lease holder killed mid-command", final.get("verdict") == "PASS",
           f"next run verdict={final.get('verdict')} recovered_in={took}s "
           f"lease_wait_ms={final.get('session_sharing', {}).get('lease_wait_ms')}")


def s10_own_tab_closed(work: Path) -> None:
    """If our own tab disappears, say so — never drive whatever tab is left."""
    sid = ensure()
    box: dict[str, tuple] = {}
    worker = threading.Thread(
        target=lambda: box.__setitem__("result", run_flow(
            "A", work / "s10-A", "--bsk-session", sid, flow=FLOW_SLOW)))
    worker.start()
    time.sleep(4.0)
    tab = own_tab(work / "s10-A")
    if tab:
        bsk(["tab", "close", tab, "--session", sid, "--quiet"])
    worker.join()
    _, final = box["result"]
    codes = error_codes(work / "s10-A")
    record("S10 our own tab closed mid-run", bool(tab) and "BSK_TAB_LOST" in codes,
           f"verdict={final.get('verdict')} closed={tab} codes={codes}")


SCENARIOS = {
    "s01": s01_two_runs_share_one_window,
    "s02": s02_six_runs_share_one_window,
    "s03": s03_peer_opens_a_focused_tab,
    "s04": s04_peer_keeps_taking_focus,
    "s05": s05_window_stopped_mid_run,
    "s06": s06_registry_points_at_a_dead_session,
    "s07": s07_corrupt_registry,
    "s08": s08_stale_session_in_the_environment,
    "s09": s09_lease_holder_killed,
    "s10": s10_own_tab_closed,
}


# --- harness ------------------------------------------------------------------------------------
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args: object) -> None:      # the fixture server is not the evidence
        pass


def serve_fixtures() -> tuple[str, socketserver.TCPServer]:
    handler = type("Fixtures", (QuietHandler,),
                   {"__init__": lambda self, *a, **k: QuietHandler.__init__(
                       self, *a, directory=str(HERE), **k)})
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}", server


def preflight() -> None:
    if not shutil.which("bsk"):
        skip("bsk is not on PATH")
    status = bsk(["status"], timeout=30)
    if status["rc"] != 0 or not isinstance(status["out"], dict):
        skip("no bsk daemon is running (the host starts it: bsk daemon start --foreground)")
    browsers = bsk(["browsers"], timeout=30)["out"]
    if not isinstance(browsers, list) or not browsers:
        skip("no browser has the extension connected")
    if len(browsers) > 1 and not os.environ.get("ENGINE2_BROWSER"):
        known = ", ".join(str(item.get("instance_id")) for item in browsers)
        skip(f"several browsers are connected — set ENGINE2_BROWSER to one of: {known}")
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("NOTE: Pillow is missing — 'which page is in the screenshot' cannot be judged "
              "and those checks are reported as skipped, not passed.", flush=True)


def main(argv: list[str]) -> int:
    global BASE_URL, ENV
    wanted = [item.lower() for item in argv if not item.startswith("-")] or list(SCENARIOS)
    unknown = [name for name in wanted if name not in SCENARIOS]
    if unknown:
        print(f"unknown scenario(s): {unknown}; known: {list(SCENARIOS)}")
        return 2
    ENV = dict(ENV_BASE)
    preflight()
    work = Path(tempfile.mkdtemp(prefix="bsk-contention-"))
    # Its own registry and lease directory: the window this machine shares is never touched.
    ENV["TEIBTO_BSK_SESSION_ROOT"] = str(work / "registry")
    ENV["TEIBTO_BSK_LEASE_DIR"] = str(work / "leases")
    if os.environ.get("ENGINE2_BROWSER"):
        ENV["TEIBTO_BSK_BROWSER"] = os.environ["ENGINE2_BROWSER"]
    BASE_URL, server = serve_fixtures()
    print(f"fixtures on {BASE_URL} · work dir {work}", flush=True)
    try:
        for name in wanted:
            try:
                SCENARIOS[name](work)
            except Exception as exc:                   # a crashed scenario is a failing scenario
                record(name, False, f"raised {type(exc).__name__}: {exc}")
    finally:
        try:
            coordinator("release")
            live = {str(item.get("session_id")) for item in (bsk(["status"])["out"] or {}).get("sessions", [])}
            leftovers = sorted(OPENED & live)
            for session_id in leftovers:
                bsk(["session", "stop", session_id, "--quiet"])
            still = {str(item.get("session_id")) for item in (bsk(["status"])["out"] or {}).get("sessions", [])}
            print(f"harness windows opened={len(OPENED)} closed_at_exit={leftovers} "
                  f"left_behind={sorted(OPENED & still)}", flush=True)
        finally:
            server.shutdown()
            if not os.environ.get("ENGINE2_KEEP"):
                shutil.rmtree(work, ignore_errors=True)
    print()
    failed = [name for name, verdict, _ in RESULTS if verdict == "FAIL"]
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} pass"
          + (f" · failed: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
