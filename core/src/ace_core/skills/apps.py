"""Apps & windows (§10.2). Until S08 these are stubs: the router already understands the commands,
and the skill says when it will work."""

from __future__ import annotations

from pydantic import Field

from ace_core.security.tiers import Tier
from ace_core.skills.base import (
    RuleCheckResult,
    Skill,
    SkillContext,
    SkillError,
    SkillParams,
    StepResult,
)

NOT_READY = "E_SKILL_NOT_READY"


class AppParams(SkillParams):
    name: str = Field(min_length=1, max_length=100)


class _AppStub(Skill[AppParams]):
    params_model = AppParams
    timeout_s = 5.0
    not_ready: str

    async def execute(self, ctx: SkillContext, params: AppParams) -> StepResult:
        raise SkillError(NOT_READY, self.not_ready)

    async def verify(
        self, ctx: SkillContext, params: AppParams, result: StepResult
    ) -> RuleCheckResult:
        return RuleCheckResult(False, "app control arrives in stage S08")


class AppsOpenSkill(_AppStub):
    id = "apps.open"
    description = "Open an app (works from stage S08)"
    examples = ("open spotify", "spotify khol do")
    not_ready = "Opening apps arrives in stage S08."

    def tier_for(self, params: AppParams) -> Tier:
        return Tier.T1

    def describe(self, params: AppParams) -> str:
        return f"Open {params.name}"


class AppsCloseSkill(_AppStub):
    id = "apps.close"
    description = "Close an app (works from stage S08)"
    examples = ("close chrome", "chrome band karo")
    not_ready = "Closing apps arrives in stage S08."

    def tier_for(self, params: AppParams) -> Tier:
        return Tier.T1

    def describe(self, params: AppParams) -> str:
        return f"Close {params.name}"


class AppsFocusSkill(_AppStub):
    id = "apps.focus"
    description = "Switch to an app (works from stage S08)"
    examples = ("switch to whatsapp", "whatsapp pe jao")
    not_ready = "Switching between apps arrives in stage S08."

    def tier_for(self, params: AppParams) -> Tier:
        return Tier.T0

    def describe(self, params: AppParams) -> str:
        return f"Switch to {params.name}"
