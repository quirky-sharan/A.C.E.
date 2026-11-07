"""Which app did Sharan mean? (S08 task 2, §8.1 stage 2): rapidfuzz over the app index plus a few
built-in aliases; launch counts and open windows break near-ties; close matches become a
clarification instead of a guess."""

from __future__ import annotations

import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Final

from rapidfuzz import fuzz, utils

from ace_core.os.base import AppKind
from ace_core.skills.app_index import IndexedApp, normalize_name

MIN_SCORE: Final = 70.0  # below this, nothing matches
CLOSE_MARGIN: Final = 6.0  # a runner-up this close to the best one makes it ambiguous
MAX_CHOICES: Final = 4
WORD_MATCH: Final = 80.0  # how close a spoken word must be to a word of the app's name

# Spoken / short names -> the Start menu name (normalized). Memory aliases arrive in S31.
ALIASES: Final[dict[str, str]] = {
    "vs code": "visual studio code",
    "vscode": "visual studio code",
    "code": "visual studio code",
    "chrome": "google chrome",
    "edge": "microsoft edge",
    "explorer": "file explorer",
    "files": "file explorer",
    "file manager": "file explorer",
    "calc": "calculator",
    "cmd": "command prompt",
    "task manager": "task manager",
    "control panel": "control panel",
}


@dataclass(frozen=True, slots=True)
class Candidate:
    app: IndexedApp
    score: float


@dataclass(frozen=True, slots=True)
class Resolution:
    candidates: list[Candidate]  # best first, at most MAX_CHOICES, all >= MIN_SCORE

    @property
    def best(self) -> IndexedApp | None:
        return self.candidates[0].app if self.candidates else None

    @property
    def ambiguous(self) -> bool:
        if len(self.candidates) < 2:
            return False
        first, second = self.candidates[0], self.candidates[1]
        return first.score - second.score < CLOSE_MARGIN


def _words_match(query: str, name: str) -> bool:
    """Every word Sharan said matches a word of the name (a prefix, or a near-typo), so a shared
    word such as "manager" alone cannot match ("task manager" is not "Python install manager")."""
    words = utils.default_process(name).split()
    return all(
        any(word.startswith(said) or fuzz.ratio(said, word) >= WORD_MATCH for word in words)
        for said in utils.default_process(query).split()
    )


def _score(query: str, app: IndexedApp, running: bool) -> float:
    name = app.normalized_name
    alias = ALIASES.get(query)
    if query == name or alias == name:
        score = 100.0
    elif not _words_match(query, name):
        return 0.0
    else:
        score = fuzz.WRatio(query, name, processor=utils.default_process)
        if name.startswith(query):
            score = max(score, 92.0)
        elif any(word.startswith(query) for word in name.split()):
            score = max(score, 85.0)
    if app.kind is AppKind.OTHER:
        score -= 10.0  # documents and links in Start lose to real apps
    score += min(6.0, 2.0 * math.log2(1 + app.launch_count))
    if running:
        score += 5.0
    return score


def resolve(query: str, apps: Sequence[IndexedApp], *, running: Collection[str] = ()) -> Resolution:
    """``running``: targets of apps that have windows open (preferred for focus / close)."""
    wanted = normalize_name(query)
    if not wanted:
        return Resolution([])
    scored = sorted(
        (Candidate(app, _score(wanted, app, app.target in running)) for app in apps),
        key=lambda candidate: (-candidate.score, candidate.app.name),
    )
    return Resolution([c for c in scored if c.score >= MIN_SCORE][:MAX_CHOICES])
