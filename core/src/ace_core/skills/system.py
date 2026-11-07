"""ACE's own skills: echo (a test skill), help and the verification mode (S07)."""

from __future__ import annotations

from typing import Final

from pydantic import Field

from ace_core.app.modes import MODE_SETTING, VerificationMode
from ace_core.security.tiers import Tier
from ace_core.skills.base import (
    NoParams,
    RuleCheckResult,
    SettingsAccess,
    Skill,
    SkillContext,
    SkillParams,
    StepResult,
)
from ace_core.skills.registry import SkillRegistry

CONTROL_LINES: Final = (
    '• "stop" or "cancel" (ruko, bas) — stop what I am doing',
    '• "yes" or "no" (haan, nahi) — answer a confirmation',
)


class EchoParams(SkillParams):
    text: str = Field(min_length=1, max_length=500)


class EchoSkill(Skill[EchoParams]):
    id = "system.echo"
    description = "Repeat back what you typed (a test skill)"
    params_model = EchoParams
    timeout_s = 2.0
    examples = ("echo hello",)

    def tier_for(self, params: EchoParams) -> Tier:
        return Tier.T0

    def describe(self, params: EchoParams) -> str:
        return f'Echo "{params.text}"'

    async def execute(self, ctx: SkillContext, params: EchoParams) -> StepResult:
        return StepResult(
            spoken=params.text, detail=f'Echo: "{params.text}"', data={"text": params.text}
        )

    async def verify(
        self, ctx: SkillContext, params: EchoParams, result: StepResult
    ) -> RuleCheckResult:
        ok = result.spoken == params.text and result.data.get("text") == params.text
        return RuleCheckResult(ok, None if ok else "the reply is not the text that was sent")


class HelpSkill(Skill[NoParams]):
    id = "system.help"
    description = "List what ACE can do right now"
    params_model = NoParams
    timeout_s = 2.0
    examples = ("help", "what can you do", "kya kya kar sakte ho")

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def tier_for(self, params: NoParams) -> Tier:
        return Tier.T0

    def describe(self, params: NoParams) -> str:
        return "List what I can do"

    async def execute(self, ctx: SkillContext, params: NoParams) -> StepResult:
        lines = [
            f'• {skill.description} — e.g. "{skill.examples[0]}"'
            for skill in self._registry
            if skill.examples and skill.id != self.id
        ]
        lines.extend(CONTROL_LINES)
        return StepResult(
            spoken="Here's what I can do right now, boss.",
            detail="\n".join(lines),
            data={"skills": [skill.id for skill in self._registry]},
        )

    async def verify(
        self, ctx: SkillContext, params: NoParams, result: StepResult
    ) -> RuleCheckResult:
        ok = bool(result.detail)
        return RuleCheckResult(ok, None if ok else "the help text is empty")


class SetModeParams(SkillParams):
    mode: VerificationMode


class SetModeSkill(Skill[SetModeParams]):
    id = "system.set_mode"
    description = "Set the verification mode: fast, balanced or paranoid"
    params_model = SetModeParams
    timeout_s = 5.0
    examples = ("paranoid mode", "switch to fast mode", "balanced mode karo")

    def __init__(self, settings: SettingsAccess) -> None:
        self._settings = settings

    def tier_for(self, params: SetModeParams) -> Tier:
        return Tier.T1

    def describe(self, params: SetModeParams) -> str:
        return f"Set the verification mode to {params.mode.value.title()}"

    async def execute(self, ctx: SkillContext, params: SetModeParams) -> StepResult:
        await self._settings.set(MODE_SETTING, params.mode.value, actor="user")
        name = params.mode.value.title()
        return StepResult(
            spoken=f"{name} mode on.",
            detail=(
                f"Verification mode set to {name}. It is stored now; the verification council "
                "that acts on it arrives in stage S18."
            ),
            data={"mode": params.mode.value},
        )

    async def verify(
        self, ctx: SkillContext, params: SetModeParams, result: StepResult
    ) -> RuleCheckResult:
        ok = await self._settings.get(MODE_SETTING) == params.mode.value
        return RuleCheckResult(ok, None if ok else "the stored mode is different")
