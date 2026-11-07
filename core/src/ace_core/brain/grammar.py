"""Router stages 1-2 (ACE_MASTER_PLAN.md §8.1): normalization and the deterministic fast-path
grammar. English + Hinglish; no models, works offline.

Rules are tried in order and the first full match wins, so specific rules (stop, yes / no, modes)
come before the general ones (switch to / open / close <app>).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from pydantic import JsonValue

_SPACES = re.compile(r"\s+")
_EDGE_CHARS: Final = " \t,.!?;:\"'"

# Fillers that add nothing to a command (§8.1), removed only at the start / end of the text.
LEADING_FILLERS: Final = (
    "hey ace",
    "hi ace",
    "ok ace",
    "okay ace",
    "ace",
    "please",
    "pls",
    "plz",
    "kindly",
    "can you",
    "could you",
    "would you",
    "will you",
    "zara",
    "jara",
    "yaar",
)
TRAILING_FILLERS: Final = ("please", "pls", "plz", "na", "yaar", "zara", "for me")

CONTROL_STOP: Final = "control.stop"
CONTROL_YES: Final = "control.yes"
CONTROL_NO: Final = "control.no"

# §15.3: accepted yes / haan / send it / confirm / do it; rejected no / nahi / cancel / stop.
# Casual words such as "ok" or "sure" do not confirm an irreversible action.
YES_WORDS: Final = (
    "yes|yeah|yep|haan|haa|han|haan ji|ji haan|confirm|confirmed|send it|do it|yes,? do it"
    "|haan,? karo|kar do"
)
NO_WORDS: Final = (
    "no|nope|nah|nahi|nahin|na|mat karo|mat kar|dont|don't|do not|(?:no,? )?don'?t do it"
)
STOP_WORDS: Final = (
    "stop|stop it|stop that|stop everything|cancel|cancel it|cancel that|abort|never ?mind"
    "|forget it|ruko|ruk|ruk jao|bas|bas karo|bas kar|rehne do|chhodo|chodo|band karo|band kar do"
)
_MODE = r"(?P<mode>fast|balanced|paranoid)"


@dataclass(frozen=True, slots=True)
class Utterance:
    raw: str  # as received, trimmed
    text: str  # fillers and edge punctuation removed, spaces collapsed; case kept for entities
    lower: str  # text, case-folded


def _strip_once(text: str) -> str:
    for filler in LEADING_FILLERS:
        match = re.match(rf"{re.escape(filler)}\b[\s,]*", text, re.IGNORECASE)
        if match and match.end() < len(text):
            return text[match.end() :]
    for filler in TRAILING_FILLERS:
        match = re.search(rf"[\s,]+{re.escape(filler)}$", text, re.IGNORECASE)
        if match and match.start() > 0:
            return text[: match.start()]
    return text


def normalize(raw: str) -> Utterance:
    """Collapse spaces, strip edge punctuation and fillers; never strips the text to nothing."""
    text = _SPACES.sub(" ", raw).strip().strip(_EDGE_CHARS)
    while True:
        stripped = _strip_once(text).strip(_EDGE_CHARS)
        if stripped == text or not stripped:
            break
        text = stripped
    return Utterance(raw=raw.strip(), text=text, lower=text.casefold())


ParamsBuilder = Callable[[re.Match[str]], dict[str, JsonValue]]


def _no_params(_: re.Match[str]) -> dict[str, JsonValue]:
    return {}


def _group(name: str, *, lower: bool = False) -> ParamsBuilder:
    def build(match: re.Match[str]) -> dict[str, JsonValue]:
        value = match.group(name).strip(_EDGE_CHARS)
        return {name: value.lower() if lower else value}

    return build


def _app_name(match: re.Match[str]) -> dict[str, JsonValue]:
    return {"name": match.group("name").strip(_EDGE_CHARS)}


def _force_close(match: re.Match[str]) -> dict[str, JsonValue]:
    return {"name": match.group("name").strip(_EDGE_CHARS), "force": True}


_THIS: Final = frozenset({"this", "it", "window", "this window", "the window", "current window"})
_STATE_WORDS: Final[dict[str, str]] = {
    "maximize": "maximize",
    "maximise": "maximize",
    "bada": "maximize",
    "minimize": "minimize",
    "minimise": "minimize",
    "chhota": "minimize",
    "restore": "restore",
}


def _arrange(match: re.Match[str]) -> dict[str, JsonValue]:
    groups = match.groupdict()
    side, state = groups.get("side"), groups.get("state")
    action = f"snap_{side.lower()}" if side else _STATE_WORDS[(state or "").lower()]
    name = (groups.get("name") or "").strip(_EDGE_CHARS)
    return {"action": action, "name": None if not name or name.lower() in _THIS else name}


@dataclass(frozen=True, slots=True)
class GrammarRule:
    intent: str  # a skill id, or control.stop / control.yes / control.no
    patterns: tuple[re.Pattern[str], ...]
    params: ParamsBuilder = _no_params

    @property
    def is_control(self) -> bool:
        return self.intent.startswith("control.")

    def match(self, text: str) -> re.Match[str] | None:
        for pattern in self.patterns:
            found = pattern.fullmatch(text)
            if found is not None:
                return found
        return None


def rule(intent: str, *patterns: str, params: ParamsBuilder = _no_params) -> GrammarRule:
    compiled = tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)
    return GrammarRule(intent, compiled, params)


_APP_SUFFIX = r"(?: app| window)?"

DEFAULT_RULES: Final[tuple[GrammarRule, ...]] = (
    rule(CONTROL_STOP, rf"(?:{STOP_WORDS})"),
    rule(CONTROL_YES, rf"(?:{YES_WORDS})"),
    rule(CONTROL_NO, rf"(?:{NO_WORDS})"),
    rule(
        "system.help",
        r"help(?: me)?|what (?:all )?can you do|what do you do|(?:show |list )?commands",
        r"(?:tum )?kya(?: kya)? kar sakte ho",
    ),
    rule(
        "system.set_mode",
        rf"(?:switch|change|set|go|put)(?: me)?(?: (?:to|into|in))?(?: the)? {_MODE}(?: mode)?",
        rf"(?:switch|change|set)(?: the)?(?: verification)? mode(?: to)? {_MODE}",
        rf"{_MODE} mode(?: (?:on|karo|kar do|chalu karo|lagao))?",
        rf"(?:use|enable|turn on|activate) {_MODE}(?: mode)?",
        rf"mode {_MODE}",
        params=_group("mode", lower=True),
    ),
    rule("system.echo", r"echo (?P<text>.+)", params=_group("text")),
    rule(
        "windows.list",
        r"what(?:'s| is) open|which (?:apps|windows) are open|(?:list|show)(?: me)?(?: all| my)?"
        r" (?:open )?windows|open windows",
        r"kya(?: kya)? khula hai|kaun(?: kaun)? se (?:apps|windows) khule hain",
    ),
    rule(
        "windows.arrange",
        r"snap (?:the )?(?P<name>.+?) (?:to (?:the )?)?(?P<side>left|right)(?: side| half)?",
        r"snap(?: (?:it|this|this window))?(?: to(?: the)?)? (?P<side>left|right)(?: side| half)?",
        r"(?P<name>.+?) ko (?P<side>left|right)(?: (?:mein|me|side))?(?: snap)? karo",
        r"(?P<state>maximi[sz]e|minimi[sz]e|restore)(?: (?:the )?(?P<name>.+?))?(?: window)?",
        r"(?P<name>.+?) (?:ko )?(?P<state>bada|chhota) karo",
        params=_arrange,
    ),
    rule("demo.dangerous", r"(?:run )?(?:the )?demo dangerous|dangerous demo"),
    rule("demo.forbidden", r"(?:run )?(?:the )?demo forbidden|forbidden demo"),
    rule(
        "apps.focus",
        rf"(?:switch|go|jump|move)(?: over)? to (?:the )?(?P<name>.+?){_APP_SUFFIX}",
        rf"focus(?: on)? (?:the )?(?P<name>.+?){_APP_SUFFIX}",
        r"(?P<name>.+?) (?:pe|par) (?:jao|chalo|le chalo|switch karo|switch kar do)",
        params=_app_name,
    ),
    rule(
        "apps.close",
        rf"(?:force (?:close|quit|kill)|kill) (?:the )?(?P<name>.+?){_APP_SUFFIX}",
        r"(?P<name>.+?) (?:ko )?force (?:close|band) karo",
        params=_force_close,
    ),
    rule(
        "apps.close",
        rf"(?:close|quit|exit) (?:the )?(?P<name>.+?){_APP_SUFFIX}",
        r"(?P<name>.+?) (?:band karo|band kar do|band kar|bandh karo|close karo|close kar do)",
        params=_app_name,
    ),
    rule(
        "apps.open",
        rf"(?:open|launch)(?: up)? (?:the )?(?P<name>.+?){_APP_SUFFIX}",
        r"(?P<name>.+?) (?:kholo|khol do|khol|open karo|open kar do|chalu karo|launch karo)",
        params=_app_name,
    ),
)
