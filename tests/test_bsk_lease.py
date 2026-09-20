from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import textwrap
import time
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEST_TMP = ROOT / "tests" / ".tmp"
TEST_TMP.mkdir(exist_ok=True)


def load_lease():
    path = ROOT / "scripts" / "bsk_lease.py"
    spec = importlib.util.spec_from_file_location("bsk_lease", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


lease_module = load_lease()


class LeaseTests(unittest.TestCase):
    """#112: processes that share one bsk session must take turns without stealing from each other."""

    def setUp(self) -> None:
        self.root = TEST_TMP / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.session = "s-" + uuid.uuid4().hex[:6]

    def lease(self, **kwargs):
        return lease_module.SessionLease(self.session, root=self.root, **kwargs)

    def owner_payload(self, **overrides) -> dict:
        payload = {"pid": os.getpid(), "token": "someone-else", "host": socket.gethostname(),
                   "session": self.session, "since": time.time()}
        payload.update(overrides)
        return payload

    def plant_lease(self, *, age: float = 0.0, **overrides) -> Path:
        """A lease held by somebody else, whose last heartbeat was `age` seconds ago."""
        path = self.root / f"{self.session}.lease"
        path.mkdir(parents=True)
        (path / "owner.json").write_text(json.dumps(self.owner_payload(**overrides)), encoding="utf-8")
        if age:
            os.utime(path, (time.time() - age, time.time() - age))
        return path

    # -- mutual exclusion --------------------------------------------------------------------
    def test_separate_processes_never_hold_the_lease_at_the_same_time(self):
        marks = self.root / "marks.txt"
        worker = self.root / "worker.py"
        worker.write_text(textwrap.dedent(f"""
            import importlib.util, os, sys, time
            spec = importlib.util.spec_from_file_location("bsk_lease", {str(ROOT / "scripts" / "bsk_lease.py")!r})
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            with mod.SessionLease({self.session!r}, root={str(self.root)!r}, wait=60):
                with open({str(marks)!r}, "a", encoding="utf-8") as fh:
                    fh.write("in %s\\n" % os.getpid())
                time.sleep(0.25)
                with open({str(marks)!r}, "a", encoding="utf-8") as fh:
                    fh.write("out %s\\n" % os.getpid())
        """), encoding="utf-8")
        workers = [subprocess.Popen([sys.executable, str(worker)]) for _ in range(4)]
        for process in workers:
            self.assertEqual(0, process.wait(timeout=120))
        lines = marks.read_text(encoding="utf-8").split()
        events = [lines[index] for index in range(0, len(lines), 2)]
        self.assertEqual(8, len(events))
        # Strict alternation is the whole contract: any "in in" means two processes were inside.
        self.assertEqual(["in", "out"] * 4, events)

    def test_a_second_lease_in_this_process_waits_for_the_first(self):
        held = self.lease()
        held.acquire()
        try:
            with self.assertRaises(lease_module.LeaseTimeout):
                self.lease(wait=0.3).acquire()
        finally:
            held.release()
        after = self.lease(wait=0.3).acquire()   # released, so the next taker gets it immediately
        self.assertLess(after.waited_ms, 300)
        after.release()

    # -- who may break a lease ---------------------------------------------------------------
    def test_a_live_owner_is_never_evicted_even_with_a_frozen_heartbeat(self):
        self.plant_lease(age=3600)        # this test process is named as the owner, and is alive
        with self.assertRaises(lease_module.LeaseTimeout):
            self.lease(wait=0.3, stale_after=0.1).acquire()

    def test_a_dead_owner_with_a_stale_heartbeat_is_evicted(self):
        corpse = subprocess.Popen([sys.executable, "-c", "pass"])
        corpse.wait(timeout=30)
        self.plant_lease(age=3600, pid=corpse.pid)
        taken = self.lease(wait=5, stale_after=0.1).acquire()
        try:
            self.assertTrue(taken.broke_stale_lease)
        finally:
            taken.release()

    def test_an_owner_on_another_host_is_not_evicted_on_a_pid_check(self):
        self.plant_lease(age=3600, host="some-other-machine", pid=999_999)
        with self.assertRaises(lease_module.LeaseTimeout):
            self.lease(wait=0.3, stale_after=0.1).acquire()

    def test_a_lease_directory_with_no_owner_file_is_only_broken_once_it_is_old(self):
        path = self.root / f"{self.session}.lease"
        path.mkdir(parents=True)
        with self.assertRaises(lease_module.LeaseTimeout):
            self.lease(wait=0.3, stale_after=60).acquire()
        os.utime(path, (time.time() - 3600, time.time() - 3600))
        taken = self.lease(wait=5, stale_after=60).acquire()
        taken.release()

    # -- release -----------------------------------------------------------------------------
    def test_release_does_not_remove_a_lease_somebody_else_now_owns(self):
        mine = self.lease().acquire()
        owner_file = mine.path / "owner.json"
        owner_file.write_text(json.dumps(self.owner_payload(token="taken-over")), encoding="utf-8")
        mine.release()
        self.assertTrue(mine.path.is_dir(), "released a lease that had been re-taken by another process")
        self.assertEqual("taken-over", json.loads(owner_file.read_text(encoding="utf-8"))["token"])

    def test_release_is_idempotent_and_frees_the_session(self):
        mine = self.lease().acquire()
        mine.release()
        mine.release()
        self.assertFalse(mine.path.exists())

    def test_the_holder_refreshes_its_heartbeat_while_it_works(self):
        mine = self.lease(heartbeat=0.05).acquire()
        try:
            os.utime(mine.path, (time.time() - 3600, time.time() - 3600))
            time.sleep(0.4)
            self.assertLess(mine._age(), 60, "a working holder looked stale to every waiter")
        finally:
            mine.release()

    # -- liveness probe ----------------------------------------------------------------------
    def test_the_liveness_probe_does_not_kill_the_process_it_checks(self):
        """os.kill(pid, 0) terminates the target on Windows; the probe must never do that."""
        victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(victim.kill)
        try:
            self.assertTrue(lease_module._pid_alive(victim.pid))
            time.sleep(0.2)
            self.assertIsNone(victim.poll(), "the liveness probe killed the process it probed")
        finally:
            victim.kill()
            victim.wait(timeout=30)
        self.assertFalse(lease_module._pid_alive(victim.pid))


if __name__ == "__main__":
    unittest.main()
