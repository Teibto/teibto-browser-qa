#!/usr/bin/env python3
"""Fail closed on skill identity, flow structure, and stale operational names."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "teibto-browser-qa"
FLOW_SCHEMA = json.loads((ROOT / "schemas" / "flow.schema.json").read_text(encoding="utf-8"))
ACTIVE_TEXT_FILES = [
    ROOT / "SKILL.md",
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "docs" / "TEAM-PROCESS.md",
    ROOT / "scripts" / "build-skill.py",
    ROOT / ".github" / "workflows" / "release.yml",
]
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+['\"][^)]*['\"])?\)")


class ValidationError(ValueError):
    pass


def skill_frontmatter() -> dict:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValidationError("SKILL.md must start with YAML frontmatter")
    try:
        frontmatter = text.split("---\n", 2)[1]
    except IndexError as exc:
        raise ValidationError("SKILL.md frontmatter is not closed") from exc
    data = yaml.safe_load(frontmatter)
    if not isinstance(data, dict):
        raise ValidationError("SKILL.md frontmatter must be an object")
    return data


def validate_skill() -> None:
    data = skill_frontmatter()
    if data.get("name") != SKILL_NAME:
        raise ValidationError(f"skill name must be {SKILL_NAME!r}")
    if not str(data.get("description") or "").strip():
        raise ValidationError("skill description is required")


def validate_flow(path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(FLOW_SCHEMA).iter_errors(data), key=lambda e: list(e.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise ValidationError(f"{path}: {location}: {error.message}")
    scenarios = data["scenarios"]
    seen: set[str] = set()
    for scenario in scenarios:
        scenario_id = scenario["id"]
        if scenario_id in seen:
            raise ValidationError(f"{path}: scenario ids must be unique")
        seen.add(scenario_id)


def validate_active_names() -> None:
    stale_patterns = (
        "wichtking/agent-browser-qa",
        "agent-browser-qa.skill",
        "name: agent-browser-qa",
    )
    hits = []
    for path in ACTIVE_TEXT_FILES:
        text = path.read_text(encoding="utf-8")
        if any(pattern in text for pattern in stale_patterns):
            hits.append(str(path.relative_to(ROOT)))
    if hits:
        raise ValidationError(f"stale operational identity in: {', '.join(hits)}")


def validate_doc_links() -> None:
    """Fail on repository-local Markdown links whose target no longer exists."""
    root = ROOT.resolve()
    broken = []
    for path in sorted(ROOT.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK_RE.finditer(text):
            target = match.group(1).strip("<>")
            if target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            relative = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not relative:
                continue
            candidate = (path.parent / relative).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                broken.append(f"{path.relative_to(ROOT)} -> {target} (outside repo)")
                continue
            if not candidate.exists():
                broken.append(f"{path.relative_to(ROOT)} -> {target}")
    if broken:
        raise ValidationError("broken local Markdown links: " + "; ".join(broken))


def main() -> int:
    try:
        validate_skill()
        for path in sorted((ROOT / "examples").glob("*.yaml")):
            validate_flow(path)
        validate_active_names()
        validate_doc_links()
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: skill identity, active names, example flows, and local Markdown links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
