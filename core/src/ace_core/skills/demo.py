"""Test skills for the confirmation and refusal rules (S07 task 6). Registered in dev mode only."""

from __future__ import annotations

from ace_core.security.tiers import Tier
from ace_core.skills.base import (
    NoParams,
    RuleCheckResult,
    Skill,
    SkillContext,
    SkillError,
    StepResult,
)


class DemoDangerousSkill(Skill[NoParams]):
    id = "demo.dangerous"
    description = "A harmless test of the confirmation rule (T2)"
    params_model = NoParams
    timeout_s = 2.0
    examples = ("demo dangerous",)

    def tier_for(self, params: NoParams) -> Tier:
        return Tier.T2

    def describe(self, params: NoParams) -> str:
        return "Run the demo dangerous action (a harmless test; nothing real happens)"

    async def execute(self, ctx: SkillContext, params: NoParams) -> StepResult:
        return StepResult(
            spoken="Done. The demo dangerous action ran; nothing real happened.",
            detail="demo.dangerous ran after your yes. It changes nothing on the PC.",
            data={"ran": True},
        )

    async def verify(
        self, ctx: SkillContext, params: NoParams, result: StepResult
    ) -> RuleCheckResult:
        ok = result.data.get("ran") is True
        return RuleCheckResult(ok, None if ok else "the demo action did not report a run")


class DemoForbiddenSkill(Skill[NoParams]):
    id = "demo.forbidden"
    description = "A harmless test of the refusal rule (T3)"
    params_model = NoParams
    timeout_s = 2.0
    examples = ("demo forbidden",)

    def tier_for(self, params: NoParams) -> Tier:
        return Tier.T3

    def describe(self, params: NoParams) -> str:
        return "Run the demo forbidden action"

    async def execute(self, ctx: SkillContext, params: NoParams) -> StepResult:
        raise SkillError("E_SKILL_FORBIDDEN", "This must never run.")  # the Supervisor refuses T3

    async def verify(
        self, ctx: SkillContext, params: NoParams, result: StepResult
    ) -> RuleCheckResult:
        return RuleCheckResult(False, "forbidden skills never run")
