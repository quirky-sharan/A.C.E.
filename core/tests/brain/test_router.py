"""Router stages 1-2: normalization, the fast-path grammar and the golden command set (§16.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from brain_fakes import MemorySettings

from ace_core.brain.grammar import normalize
from ace_core.brain.records import ConfirmationAnswer
from ace_core.brain.router import UNKNOWN_INTENT, RouteKind, Router
from ace_core.skills.catalog import build_registry

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "commands.yaml"


def load_golden() -> list[dict[str, Any]]:
    cases = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))
    assert isinstance(cases, list)
    return cases


@pytest.fixture(scope="module")
def router() -> Router:
    return Router(build_registry(settings=MemorySettings(), dev=True))


def test_the_golden_set_is_well_formed() -> None:
    cases = load_golden()
    assert len(cases) >= 40
    for case in cases:
        assert isinstance(case["utterance"], str), case  # an unquoted yes / no becomes a bool
        assert sum(key in case for key in ("skill", "control", "no_match")) == 1, case
        if "control" in case:
            assert case["control"] in ("stop", "yes", "no"), case
    utterances = [case["utterance"] for case in cases]
    assert len(utterances) == len(set(utterances))


@pytest.mark.parametrize("case", load_golden(), ids=lambda case: str(case["utterance"]))
def test_golden_command(router: Router, case: dict[str, Any]) -> None:
    route = router.route(case["utterance"])
    if case.get("no_match"):
        assert route.kind is RouteKind.NO_MATCH
        assert route.intent == UNKNOWN_INTENT
    elif case.get("control") == "stop":
        assert route.kind is RouteKind.STOP
    elif "control" in case:
        assert route.kind is RouteKind.CONFIRM
        assert route.answer is ConfirmationAnswer(case["control"])
    else:
        assert route.kind is RouteKind.SKILL
        assert route.skill_id == case["skill"] == route.intent
        assert route.params is not None
        assert route.params.model_dump(mode="json", exclude_defaults=True) == case["params"]


def test_every_skill_example_routes_to_its_skill(router: Router) -> None:
    for skill in build_registry(settings=MemorySettings(), dev=True):
        for example in skill.examples:
            assert router.route(example).skill_id == skill.id, example


@pytest.mark.parametrize(
    ("raw", "text"),
    [
        ("  Open   Spotify  ", "Open Spotify"),
        ("please open spotify please", "open spotify"),
        ("hey ace, open spotify!", "open spotify"),
        ("zara spotify kholo na", "spotify kholo"),
        ("Can you, please, echo hi?", "echo hi"),
        ("ace", "ace"),
        ("please", "please"),
        ("na", "na"),
        ("acer laptop", "acer laptop"),
        ("", ""),
    ],
)
def test_normalize(raw: str, text: str) -> None:
    utterance = normalize(raw)
    assert utterance.text == text
    assert utterance.lower == text.casefold()
    assert utterance.raw == raw.strip()


def test_entities_keep_their_case(router: Router) -> None:
    route = router.route("echo Hello WORLD")
    assert route.params is not None
    assert route.params.model_dump(exclude_defaults=True) == {"text": "Hello WORLD"}


def test_demo_skills_exist_only_in_dev_mode() -> None:
    router = Router(build_registry(settings=MemorySettings(), dev=False))
    assert router.route("demo dangerous").kind is RouteKind.NO_MATCH
    assert router.route("demo forbidden").kind is RouteKind.NO_MATCH
    assert router.route("echo hi").kind is RouteKind.SKILL


def test_params_that_fail_validation_fall_through(router: Router) -> None:
    assert router.route("echo " + "x" * 600).kind is RouteKind.NO_MATCH  # max 500 characters
    assert router.route("open " + "y" * 150).kind is RouteKind.NO_MATCH  # app names: max 100


def test_mode_words_win_over_switching_apps(router: Router) -> None:
    route = router.route("switch to balanced mode")
    assert route.skill_id == "system.set_mode"
    assert router.route("switch to spotify").skill_id == "apps.focus"
