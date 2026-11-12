"""The response composer (ACE_MASTER_PLAN.md §5.3 step 8, D-04): every reply is a short line
(spoken once TTS exists, S11) plus optional detail for the sidebar. Persona: a chill friend who
calls Sharan "boss"; replies are in English (D-01)."""

from __future__ import annotations

from dataclasses import dataclass

from ace_core.brain.records import ConfirmationAnswer
from ace_core.skills.base import StepResult


@dataclass(frozen=True, slots=True)
class Reply:
    spoken: str
    detail: str | None = None


def succeeded(result: StepResult) -> Reply:
    return Reply(result.spoken, result.detail)


def failed(message: str, code: str) -> Reply:
    return Reply(f"That didn't work, boss. {message}", f"{message} ({code})")


def refused(label: str, reason: str) -> Reply:
    return Reply(
        "I can't do that one, boss. It's on the forbidden list, so you'll have to do it yourself.",
        f"Refused: {label}. {reason}",
    )


def confirm_prompt(label: str, timeout_s: float) -> Reply:
    return Reply(
        f"{label}. Should I go ahead? Yes or no.",
        f'Say or type "yes" / "haan" to go ahead, "no" / "nahi" to cancel. '
        f"No answer in {timeout_s:g} s cancels it.",
    )


def cancelled(answer: ConfirmationAnswer | None, timeout_s: float) -> Reply:
    if answer is ConfirmationAnswer.TIMEOUT:
        return Reply(
            "No answer, so I cancelled it.", f"No answer came within {timeout_s:g} seconds."
        )
    return Reply("Okay, cancelled.")


def question(text: str, labels: list[str]) -> Reply:
    options = "\n".join(f"{n}. {label}" for n, label in enumerate(labels, start=1))
    return Reply(text, f"{options}\nPick one, or say its number or name.")


def stopped(count: int) -> Reply:
    if count == 0:
        return Reply("Nothing to stop, boss.")
    return Reply("Stopped.", f"Cancelled {count} task{'s' if count != 1 else ''}.")


def nothing_to_confirm() -> Reply:
    return Reply("There's nothing waiting for a yes or no right now.")


def no_match(text: str) -> Reply:
    return Reply(
        'Sorry boss, I don\'t know that one yet. Type "help" to see what I can do.',
        f'No command matched "{text}". Understanding free-form requests arrives with the local '
        "and cloud models (stages S14-S16).",
    )


def internal_error() -> Reply:
    return Reply(
        "Something went wrong on my side, boss.",
        "An internal error stopped this command; the details are in the core log.",
    )
