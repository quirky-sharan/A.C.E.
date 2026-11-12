"""The router (ACE_MASTER_PLAN.md §8.1). S07 has stages 1-2 only: normalize, then the fast-path
grammar. Commands it does not understand get an honest "not yet"; the local LLM classifier (S14)
and the cloud planner (S15-S16) join later behind the same ``route`` call."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from pydantic import ValidationError
from rapidfuzz import fuzz, utils

from ace_core.brain.grammar import (
    CONTROL_NO,
    CONTROL_STOP,
    CONTROL_YES,
    DEFAULT_RULES,
    GrammarRule,
    Utterance,
    normalize,
)
from ace_core.brain.records import ConfirmationAnswer
from ace_core.skills.base import SkillParams
from ace_core.skills.registry import SkillRegistry

UNKNOWN_INTENT: Final = "unknown"
CHOOSE_INTENT: Final = "control.choose"

_ORDINALS: Final[tuple[frozenset[str], ...]] = (
    frozenset({"1", "one", "first", "pehla", "pehle", "pehla wala", "pehle wala"}),
    frozenset({"2", "two", "second", "dusra", "doosra", "dusra wala", "doosra wala"}),
    frozenset({"3", "three", "third", "teesra", "teesra wala"}),
    frozenset({"4", "four", "fourth", "chautha", "chautha wala"}),
)
_LAST: Final = frozenset({"last", "aakhri", "last wala", "aakhri wala"})
_YES: Final = frozenset(
    {"yes", "yeah", "yep", "haan", "haa", "han", "haan ji", "ji haan", "ji", "sahi"}
)
_NO: Final = frozenset({"no", "nope", "nah", "nahi", "nahin", "na", "galat"})


def pick_option(text: str, options: tuple[tuple[str, str], ...]) -> str | None:
    """The option a typed answer means: a number / ordinal (English or Hinglish) or a clear
    name match. None when it is not an answer."""
    wanted = normalize(text).lower.removeprefix("the ").removesuffix(" one").strip()
    for index, words in enumerate(_ORDINALS):
        if wanted in words and index < len(options):
            return options[index][0]
    if wanted in _LAST and options:
        return options[-1][0]
    ids = {option_id for option_id, _ in options}
    if wanted in _YES and "yes" in ids:  # yes / no questions ("Did you say ...?")
        return "yes"
    if wanted in _NO and "no" in ids:
        return "no"
    scored = sorted(
        (
            (fuzz.WRatio(wanted, label, processor=utils.default_process), option_id)
            for option_id, label in options
        ),
        reverse=True,
    )
    if scored and scored[0][0] >= 85 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 10):
        return scored[0][1]
    return None


class RouteKind(StrEnum):
    SKILL = "skill"  # a one-step task for one skill
    STOP = "stop"  # cancel what is running / waiting
    CONFIRM = "confirm"  # a yes / no answer for a pending confirmation
    NO_MATCH = "no_match"


@dataclass(frozen=True, slots=True)
class Route:
    kind: RouteKind
    utterance: Utterance
    intent: str
    skill_id: str | None = None
    params: SkillParams | None = None
    answer: ConfirmationAnswer | None = None


class Router:
    def __init__(
        self, registry: SkillRegistry, rules: Sequence[GrammarRule] = DEFAULT_RULES
    ) -> None:
        self._registry = registry
        self._rules = tuple(rules)

    def route(self, text: str) -> Route:
        utterance = normalize(text)
        if utterance.text:
            for rule in self._rules:
                match = rule.match(utterance.text)
                if match is None:
                    continue
                if rule.intent == CONTROL_STOP:
                    return Route(RouteKind.STOP, utterance, rule.intent)
                if rule.intent in (CONTROL_YES, CONTROL_NO):
                    answer = (
                        ConfirmationAnswer.YES
                        if rule.intent == CONTROL_YES
                        else ConfirmationAnswer.NO
                    )
                    return Route(RouteKind.CONFIRM, utterance, rule.intent, answer=answer)
                skill = self._registry.get(rule.intent)
                if skill is None:  # e.g. the demo skills outside dev mode
                    continue
                try:
                    params = skill.params_model.model_validate(rule.params(match))
                except ValidationError:
                    continue
                return Route(RouteKind.SKILL, utterance, skill.id, skill_id=skill.id, params=params)
        return Route(RouteKind.NO_MATCH, utterance, UNKNOWN_INTENT)
