from __future__ import annotations

import importlib.util
import io
import os
import sys
import time
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEST_TMP = ROOT / "tests" / ".tmp"
TEST_TMP.mkdir(exist_ok=True)

DAY = 86400.0


def load_sweep():
    path = ROOT / "scripts" / "profile-sweep.py"
    spec = importlib.util.spec_from_file_location("profile_sweep", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    # dataclasses look the module up in sys.modules while the class body is processed, so a
    # spec-loaded module has to be registered before exec_module or @dataclass raises.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sweep_module = load_sweep()


class ProfileSweepTests(unittest.TestCase):
    """#132: sweeping stale .qa-profiles must never delete a profile Chrome is using, a profile
    touched recently, or one explicitly marked to keep."""

    def setUp(self) -> None:
        self.root = TEST_TMP / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.profiles = self.root / ".qa-profiles"
        self.profiles.mkdir()

    def make_profile(self, name: str, *, age_days: float = 0.0, size: int = 1024,
                     keep: bool = False) -> Path:
        path = self.profiles / name
        path.mkdir(parents=True)
        payload = path / "data.bin"
        payload.write_bytes(b"x" * size)
        if keep:
            (path / ".keep").write_text("", encoding="utf-8")
        if age_days:
            stamp = time.time() - age_days * DAY
            os.utime(payload, (stamp, stamp))
            os.utime(path, (stamp, stamp))
        return path

    def chrome_using(self, path: Path, pid: int = 4242):
        return [sweep_module.Process(
            pid=pid,
            cmdline=f'chrome.exe --user-data-dir="{path}" --remote-debugging-port=9400')]

    def run_sweep(self, **kwargs):
        options = dict(processes=[], keep_days=3, protect=[], only=[], force=False, apply=False)
        options.update(kwargs)
        return sweep_module.sweep(self.profiles, **options)

    # -- parsing -----------------------------------------------------------------------------
    def test_parse_user_data_dirs_reads_quoted_and_bare_forms(self):
        processes = [
            sweep_module.Process(1, 'chrome --user-data-dir="C:\\a b\\prof" --x'),
            sweep_module.Process(2, "chrome --user-data-dir=/tmp/prof2"),
            sweep_module.Process(3, "chrome --no-startup-window"),
        ]
        found = sweep_module.parse_user_data_dirs(processes)
        self.assertEqual(2, len(found))
        self.assertEqual(1, found[0][0])
        self.assertEqual(2, found[1][0])

    def test_strict_probe_fails_when_the_probe_returns_nothing(self):
        original = sweep_module.list_processes
        sweep_module.list_processes = lambda: []
        self.addCleanup(setattr, sweep_module, "list_processes", original)
        code = sweep_module.main(["--profiles-dir", str(self.profiles), "--strict-probe"])
        self.assertEqual(2, code)

    # -- the guards --------------------------------------------------------------------------
    def test_a_profile_in_use_is_never_swept_even_with_force(self):
        path = self.make_profile("live", age_days=99)
        profiles = self.run_sweep(processes=self.chrome_using(path), force=True, apply=True)
        self.assertTrue(path.is_dir(), "swept a profile Chrome was using")
        self.assertEqual("keep", profiles[0].decision)
        self.assertIn("in use by pid 4242", " ".join(profiles[0].reasons))

    def test_a_recently_touched_profile_is_kept_unless_forced(self):
        self.make_profile("recent", age_days=1)
        self.assertEqual("keep", self.run_sweep()[0].decision)
        self.assertEqual("sweep", self.run_sweep(force=True)[0].decision)

    def test_a_keep_marker_survives_force(self):
        path = self.make_profile("pinned", age_days=99, keep=True)
        self.run_sweep(force=True, apply=True)
        self.assertTrue(path.is_dir(), "deleted a profile carrying a .keep marker")

    def test_a_protect_glob_survives_force(self):
        path = self.make_profile("sb2-prod", age_days=99)
        self.run_sweep(protect=["sb2*"], force=True, apply=True)
        self.assertTrue(path.is_dir(), "deleted a profile named by --protect")

    # -- deletion behaviour ------------------------------------------------------------------
    def test_dry_run_reports_the_sweep_without_deleting(self):
        path = self.make_profile("stale", age_days=10)
        profiles = self.run_sweep()
        self.assertEqual("sweep", profiles[0].decision)
        self.assertTrue(path.is_dir(), "dry-run deleted a file")

    def test_apply_deletes_only_stale_profiles(self):
        stale = self.make_profile("stale", age_days=10)
        fresh = self.make_profile("fresh", age_days=1)
        self.run_sweep(apply=True)
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.is_dir())

    def test_only_restricts_the_sweep_to_named_profiles(self):
        wanted = self.make_profile("run-x", age_days=10)
        other = self.make_profile("run-y", age_days=10)
        self.run_sweep(only=["run-x"], apply=True)
        self.assertFalse(wanted.exists())
        self.assertTrue(other.is_dir())

    def test_sizes_are_measured_in_mib(self):
        self.make_profile("big", age_days=0, size=2 * 1024 * 1024)
        profiles = self.run_sweep()
        self.assertEqual(2.0, profiles[0].mib)

    # -- discovery and CLI -------------------------------------------------------------------
    def test_discover_finds_the_profiles_dir_under_a_root(self):
        found = sweep_module.discover([self.root], [], max_depth=3)
        self.assertEqual([self.profiles.resolve()], [p.resolve() for p in found])

    def test_cli_defaults_to_dry_run_then_applies(self):
        original = sweep_module.list_processes
        sweep_module.list_processes = lambda: []
        self.addCleanup(setattr, sweep_module, "list_processes", original)
        profile = self.make_profile("stale", age_days=10)

        with redirect_stdout(io.StringIO()):
            self.assertEqual(0, sweep_module.main(["--profiles-dir", str(self.profiles)]))
        self.assertTrue(profile.is_dir(), "default run was not a dry-run")

        with redirect_stdout(io.StringIO()):
            self.assertEqual(0, sweep_module.main(
                ["--profiles-dir", str(self.profiles), "--apply"]))
        self.assertFalse(profile.exists())


if __name__ == "__main__":
    unittest.main()
