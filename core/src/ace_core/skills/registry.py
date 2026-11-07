"""The skill registry and its JSON Schema export (ACE_MASTER_PLAN.md §10.1, S07 task 2).

The export is the tool list the language models get from S15 on: one entry per skill with its
id, description and params schema.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, Final

from ace_core.skills.base import SKILL_ID_PATTERN, AnySkill

_SKILL_ID = re.compile(SKILL_ID_PATTERN)
SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, AnySkill] = {}

    def register(self, skill: AnySkill) -> None:
        if not _SKILL_ID.fullmatch(skill.id) or len(skill.id) > 64:
            raise ValueError(f"invalid skill id: {skill.id!r}")
        if skill.id in self._skills:
            raise ValueError(f"skill already registered: {skill.id}")
        if not skill.description.strip():
            raise ValueError(f"skill {skill.id} needs a description")
        if skill.timeout_s <= 0:
            raise ValueError(f"skill {skill.id} needs a positive timeout")
        self._skills[skill.id] = skill

    def get(self, skill_id: str) -> AnySkill | None:
        return self._skills.get(skill_id)

    def __contains__(self, skill_id: object) -> bool:
        return skill_id in self._skills

    def __iter__(self) -> Iterator[AnySkill]:
        return iter(sorted(self._skills.values(), key=lambda skill: skill.id))

    def __len__(self) -> int:
        return len(self._skills)

    def tool_schemas(self) -> list[dict[str, Any]]:
        """One entry per skill: name, description, params JSON Schema and a few facts."""
        return [
            {
                "name": skill.id,
                "description": skill.description,
                "parameters": skill.params_model.model_json_schema(),
                "background_capable": skill.background_capable,
                "timeout_s": skill.timeout_s,
                "examples": list(skill.examples),
            }
            for skill in self
        ]

    def json_schema(self) -> dict[str, Any]:
        """The whole registry as one JSON document (``python -m ace_core.skills.export_schema``)."""
        return {
            "$schema": SCHEMA_DIALECT,
            "title": "AceSkills",
            "description": "ACE skills and their params. Generated from the skill registry.",
            "skills": self.tool_schemas(),
        }
