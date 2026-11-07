"""The skill registry, its JSON Schema export and the S07 skills (§10.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import JsonValue

from ace_core.app.modes import MODE_SETTING, VerificationMode
from ace_core.brain.records import Origin
from ace_core.db.stores import Actor
from ace_core.security.tiers import Tier
from ace_core.skills import export_schema
from ace_core.skills.apps import (
    AppParams,
    AppsCloseSkill,
    AppsFocusSkill,
    AppsOpenSkill,
    CloseParams,
)
from ace_core.skills.base import NoParams, SkillContext, SkillError, StepResult
from ace_core.skills.catalog import build_registry
from ace_core.skills.demo import DemoDangerousSkill, DemoForbiddenSkill
from ace_core.skills.registry import SkillRegistry
from ace_core.skills.system import (
    EchoParams,
    EchoSkill,
    HelpSkill,
    SetModeParams,
    SetModeSkill,
)

CTX = SkillContext(task_id="t", step_id="s", origin=Origin.TEXT, utterance="test")


class MemorySettings:
    def __init__(self) -> None:
        self.values: dict[str, JsonValue] = {}

    async def get(self, key: str, default: JsonValue = None) -> JsonValue:
        return self.values.get(key, default)

    async def set(self, key: str, value: JsonValue, *, actor: Actor = "system") -> None:
        self.values[key] = value


def test_the_catalog_has_every_skill() -> None:
    ids = [skill.id for skill in build_registry(settings=MemorySettings(), dev=False)]
    assert ids == [
        "apps.close",
        "apps.focus",
        "apps.open",
        "system.echo",
        "system.help",
        "system.set_mode",
        "windows.arrange",
        "windows.list",
    ]
    dev_ids = {skill.id for skill in build_registry(settings=MemorySettings(), dev=True)}
    assert {"demo.dangerous", "demo.forbidden"} <= dev_ids


@pytest.mark.parametrize("bad_id", ["echo", "System.echo", "system.", "system..echo", "a" * 70])
def test_skill_ids_are_checked(bad_id: str) -> None:
    skill = EchoSkill()
    skill.id = bad_id
    with pytest.raises(ValueError, match="invalid skill id"):
        SkillRegistry().register(skill)


def test_duplicates_and_incomplete_skills_are_rejected() -> None:
    registry = SkillRegistry()
    registry.register(EchoSkill())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(EchoSkill())
    nameless = DemoDangerousSkill()
    nameless.description = " "
    with pytest.raises(ValueError, match="description"):
        registry.register(nameless)
    stuck = DemoForbiddenSkill()
    stuck.timeout_s = 0
    with pytest.raises(ValueError, match="timeout"):
        registry.register(stuck)
    assert len(registry) == 1
    assert "system.echo" in registry
    assert registry.get("nope.skill") is None


def test_the_json_schema_export_lists_tools(tmp_path: Path) -> None:
    schema = build_registry(settings=MemorySettings(), dev=True).json_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    tools = {tool["name"]: tool for tool in schema["skills"]}
    echo = tools["system.echo"]
    assert echo["parameters"]["properties"]["text"]["maxLength"] == 500
    assert echo["parameters"]["required"] == ["text"]
    assert echo["parameters"]["additionalProperties"] is False
    assert tools["system.set_mode"]["parameters"]["$defs"]["VerificationMode"]["enum"] == [
        "fast",
        "balanced",
        "paranoid",
    ]
    assert tools["apps.open"]["examples"] == ["open spotify", "spotify khol do"]
    out = tmp_path / "skills.json"
    assert export_schema.main(["--dev", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == schema
    assert "demo.dangerous" not in export_schema.render(dev=False)


async def test_echo_repeats_and_verifies() -> None:
    skill, params = EchoSkill(), EchoParams(text="Hello")
    assert skill.tier_for(params) is Tier.T0
    assert skill.describe(params) == 'Echo "Hello"'
    result = await skill.execute(CTX, params)
    assert result.spoken == "Hello"
    assert (await skill.verify(CTX, params, result)).ok
    wrong = StepResult(spoken="Bye", data={"text": "Bye"})
    assert not (await skill.verify(CTX, params, wrong)).ok
    assert await skill.undo(CTX, params, result) is None
    assert await skill.preconditions(CTX, params) == []


async def test_help_lists_every_skill_and_the_control_words() -> None:
    registry = build_registry(settings=MemorySettings(), dev=False)
    help_skill = registry.get("system.help")
    assert isinstance(help_skill, HelpSkill)
    result = await help_skill.execute(CTX, NoParams())
    assert result.detail is not None
    assert '"open spotify"' in result.detail
    assert '"echo hello"' in result.detail
    assert "help" not in result.detail.split("e.g.")[0]  # help does not list itself first
    assert '"stop"' in result.detail
    assert '"yes" or "no"' in result.detail
    assert (await help_skill.verify(CTX, NoParams(), result)).ok


async def test_set_mode_stores_and_reads_back() -> None:
    settings = MemorySettings()
    skill = SetModeSkill(settings)
    params = SetModeParams(mode=VerificationMode.PARANOID)
    assert skill.tier_for(params) is Tier.T1
    result = await skill.execute(CTX, params)
    assert settings.values[MODE_SETTING] == "paranoid"
    assert result.spoken == "Paranoid mode on."
    assert (await skill.verify(CTX, params, result)).ok
    settings.values[MODE_SETTING] = "fast"
    assert not (await skill.verify(CTX, params, result)).ok


@pytest.mark.parametrize("skill", [AppsOpenSkill(None), AppsCloseSkill(None), AppsFocusSkill(None)])
async def test_app_skills_without_windows_say_so(
    skill: AppsOpenSkill | AppsCloseSkill | AppsFocusSkill,
) -> None:
    params = CloseParams(name="Spotify")
    with pytest.raises(SkillError, match="not available") as caught:
        await skill.execute(CTX, params)
    assert caught.value.code == "E_SKILL_NOT_READY"


def test_app_tiers_and_labels() -> None:
    assert AppsOpenSkill(None).tier_for(AppParams(name="x")) is Tier.T1
    assert AppsFocusSkill(None).tier_for(AppParams(name="x")) is Tier.T0
    close = AppsCloseSkill(None)
    assert close.tier_for(CloseParams(name="Notepad")) is Tier.T1
    assert close.tier_for(CloseParams(name="Notepad", force=True)) is Tier.T2
    assert close.describe(CloseParams(name="Notepad", force=True)).startswith("Force close Notepad")


async def test_demo_skills() -> None:
    dangerous, forbidden = DemoDangerousSkill(), DemoForbiddenSkill()
    assert dangerous.tier_for(NoParams()) is Tier.T2
    assert forbidden.tier_for(NoParams()) is Tier.T3
    result = await dangerous.execute(CTX, NoParams())
    assert (await dangerous.verify(CTX, NoParams(), result)).ok
    with pytest.raises(SkillError):
        await forbidden.execute(CTX, NoParams())
    assert not (await forbidden.verify(CTX, NoParams(), result)).ok


def test_params_reject_unknown_fields() -> None:
    with pytest.raises(ValueError, match="Extra inputs"):
        EchoParams.model_validate({"text": "hi", "extra": 1})
