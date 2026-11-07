"""Builds the registry with every skill that exists at this stage."""

from __future__ import annotations

from ace_core.skills.apps import AppsCloseSkill, AppsFocusSkill, AppsOpenSkill, AppsPorts
from ace_core.skills.base import SettingsAccess
from ace_core.skills.demo import DemoDangerousSkill, DemoForbiddenSkill
from ace_core.skills.registry import SkillRegistry
from ace_core.skills.system import EchoSkill, HelpSkill, SetModeSkill
from ace_core.skills.windows import WindowsArrangeSkill, WindowsListSkill


def build_registry(
    *, settings: SettingsAccess, dev: bool, apps: AppsPorts | None = None
) -> SkillRegistry:
    """All skills; the demo skills only in dev mode (``--dev``). ``apps`` is None where app
    control is not available (not Windows)."""
    registry = SkillRegistry()
    for skill in (
        EchoSkill(),
        HelpSkill(registry),
        SetModeSkill(settings),
        AppsOpenSkill(apps),
        AppsCloseSkill(apps),
        AppsFocusSkill(apps),
        WindowsArrangeSkill(apps),
        WindowsListSkill(apps),
    ):
        registry.register(skill)
    if dev:
        registry.register(DemoDangerousSkill())
        registry.register(DemoForbiddenSkill())
    return registry
