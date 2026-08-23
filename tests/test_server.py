from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import textwrap
import time
import unittest
import urllib.error
import urllib.request
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FAKE_CDP = ROOT / "tests" / "fixtures" / "fake_cdp.py"
EXAMPLES = ROOT / "examples"


@unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
class LocalServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        env = os.environ.copy()
        env["QA_PORT"] = str(cls.port)
        env["TEIBTO_CDP_SCRIPT"] = str(FAKE_CDP)
        env.pop("TGT_ID", None)
        cls.process = subprocess.Popen(
            ["node", str(ROOT / "app" / "server.js")], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            if cls.process.poll() is not None:
                out, err = cls.process.communicate()
                raise RuntimeError(f"server exited early: {out}\n{err}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/api/health", timeout=0.5):
                    return
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        raise RuntimeError("server did not become ready")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.process.terminate()
        try:
            cls.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=5)

    def get_json(self, path: str):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as response:
            return response.status, json.load(response)

    def test_health_identifies_cdp_jsonl_without_recording(self) -> None:
        status, body = self.get_json("/api/health")
        self.assertEqual(200, status)
        self.assertEqual("cdp-jsonl", body["runner"])
        self.assertFalse(body["record"])

    def test_story_metadata_comes_from_strict_runner(self) -> None:
        try:
            status, body = self.get_json("/api/stories")
        except urllib.error.HTTPError as error:
            body = json.loads(error.read())
            if error.code == 500 and "spawn EPERM" in body.get("error", ""):
                self.skipTest("managed Windows sandbox blocks Node child_process.spawn")
            raise
        self.assertEqual(200, status)
        self.assertTrue(any(item["id"] == "saucedemo" for item in body))

    def test_run_requires_a_pinned_target(self) -> None:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/run",
            data=json.dumps({"flow": "saucedemo", "vars": {}}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(400, caught.exception.code)
        body = json.loads(caught.exception.read())
        self.assertIn("target_id", body["error"])

    def test_one_broken_flow_does_not_blank_the_story_list(self) -> None:
        broken = EXAMPLES / "zz-server-test-broken.yaml"
        broken.write_text("story: zz-server-test-broken", encoding="utf-8")
        self.addCleanup(broken.unlink, missing_ok=True)
        try:
            status, body = self.get_json("/api/stories")
        except urllib.error.HTTPError as error:
            detail = json.loads(error.read())
            if error.code == 500 and "spawn EPERM" in detail.get("error", ""):
                self.skipTest("managed Windows sandbox blocks Node child_process.spawn")
            self.fail(f"{error.code}: {detail}")
        self.assertEqual(200, status)
        by_id = {item["id"]: item for item in body}
        self.assertIn("saucedemo", by_id)
        self.assertNotIn("error", by_id["saucedemo"])
        self.assertIn("schema", by_id["zz-server-test-broken"]["error"])
        self.assertEqual("zz-server-test-broken.yaml", by_id["zz-server-test-broken"]["file"])

    def test_yml_flow_that_lists_also_runs(self) -> None:
        flow = EXAMPLES / "zz-server-test-yml.yml"
        flow.write_text(textwrap.dedent("""
            story: zz-server-test-yml
            title: YML flow
            scenarios:
              - id: smoke
                steps:
                  - {action: open, target: "https://example.test", capture: false}
            """), encoding="utf-8")
        self.addCleanup(flow.unlink, missing_ok=True)
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/run",
            data=json.dumps({"flow": "zz-server-test-yml", "target_id": "target-123"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                self.assertEqual(202, response.status)
                self.assertIn("run_id", json.load(response))
        except urllib.error.HTTPError as error:
            body = json.loads(error.read())
            if error.code == 500 and "spawn EPERM" in body.get("error", ""):
                self.skipTest("managed Windows sandbox blocks Node child_process.spawn")
            self.fail(f"{error.code}: {body}")

    def test_path_traversal_is_not_served(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/runs/x/../../README.md", timeout=5)
        self.assertEqual(404, caught.exception.code)

    def test_embedded_ui_javascript_parses(self) -> None:
        html = (ROOT / "app" / "public" / "index.html").read_text(encoding="utf-8")
        match = re.search(r"<script>([\s\S]*)</script>", html)
        self.assertIsNotNone(match)
        result = subprocess.run(
            ["node", "-e", "new Function(require('fs').readFileSync(0,'utf8'))"],
            input=match.group(1), capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
