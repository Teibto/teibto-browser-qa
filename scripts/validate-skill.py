#!/usr/bin/env python3
"""Fail closed on skill identity, flow structure, and stale operational names."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "teibto-browser-qa"
ALLOWED_ACTIONS = {
    "open",
    "fill",
    "click",
    "select",
    "press",
    "scrollintoview",
    "eval",
    "wait",
}
ACTIVE_TEXT_FILES = [
    ROOT / "SKILL.md",
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "docs" / "TEAM-PROCESS.md",
    ROOT / "scripts" / "build-skill.py",
    ROOT / ".github" / "workflows" / "release.yml",
]


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
    if not isinstance(data, dict):
        raise ValidationError(f"{path}: root must be an object")
    if not str(data.get("story") or "").strip():
        raise ValidationError(f"{path}: story is required")
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValidationError(f"{path}: scenarios must be a non-empty list")
    seen: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValidationError(f"{path}: each scenario must be an object")
        scenario_id = str(scenario.get("id") or "").strip()
        if not scenario_id or scenario_id in seen:
            raise ValidationError(f"{path}: scenario ids must be present and unique")
        seen.add(scenario_id)
        steps = scenario.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValidationError(f"{path}: {scenario_id} needs at least one step")
        for index, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                raise ValidationError(f"{path}: {scenario_id} step {index} must be an object")
            action = step.get("action")
            if action not in ALLOWED_ACTIONS:
                raise ValidationError(
                    f"{path}: {scenario_id} step {index} has unsupported action {action!r}"
                )


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


def main() -> int:
    try:
        validate_skill()
        for path in sorted((ROOT / "examples").glob("*.yaml")):
            validate_flow(path)
        validate_active_names()
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: skill identity, active names, and example flows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
