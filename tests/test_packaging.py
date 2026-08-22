from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "teibto-browser-qa.skill"


def load_validator():
    path = ROOT / "scripts" / "validate-skill.py"
    spec = importlib.util.spec_from_file_location("validate_skill", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class PackagingTests(unittest.TestCase):
    def tearDown(self) -> None:
        BUNDLE.unlink(missing_ok=True)

    def test_skill_frontmatter_uses_canonical_name(self) -> None:
        validator = load_validator()
        self.assertEqual("teibto-browser-qa", validator.skill_frontmatter()["name"])

    def test_example_flows_validate(self) -> None:
        validator = load_validator()
        examples = sorted((ROOT / "examples").glob("*.yaml"))
        self.assertTrue(examples)
        for example in examples:
            validator.validate_flow(example)
        validator.validate_flow(ROOT / "tests" / "fixtures" / "live-flow.yaml")

    def test_local_markdown_links_validate(self) -> None:
        load_validator().validate_doc_links()

    def test_bundle_has_one_canonical_root(self) -> None:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build-skill.py")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        with zipfile.ZipFile(BUNDLE) as archive:
            names = archive.namelist()
        self.assertIn("teibto-browser-qa/SKILL.md", names)
        self.assertIn("teibto-browser-qa/scripts/flow-runner.py", names)
        self.assertIn("teibto-browser-qa/schemas/flow.schema.json", names)
        self.assertIn("teibto-browser-qa/app/server.js", names)
        self.assertIn("teibto-browser-qa/app/public/index.html", names)
        self.assertTrue(all(name.startswith("teibto-browser-qa/") for name in names))
        self.assertFalse(any("agent-browser-qa/" in name for name in names))
        self.assertNotIn("teibto-browser-qa/references/test-data.md", names)


if __name__ == "__main__":
    unittest.main()
