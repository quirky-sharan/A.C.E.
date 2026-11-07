"""The Supervisor (ACE_MASTER_PLAN.md §5.3 step 6, §15.3, D-10): decides in code whether a step
may run. T0 runs, T1 runs and is logged, T2 waits for Sharan's yes (30 s, then cancelled), T3 is
refused, and a skill outside the task's capability scope never runs."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final

from ace_core.app.events import EventBus
from ace_core.brain.records import ConfirmationAnswer, ConfirmationRequested, PendingConfirmation
from ace_core.db.history import HistoryStore
from ace_core.db.ids import new_id
from ace_core.db.stores import AuditLog
from ace_core.security.scope import CapabilityScope
from ace_core.security.tiers import Tier, TierPolicy, policy_for
from ace_core.skills.base import AnySkill, SkillParams

DEFAULT_CONFIRM_TIMEOUT_S: Final = 30.0
ERR_FORBIDDEN: Final = "E_SUPERVISOR_FORBIDDEN"
ERR_OUT_OF_SCOPE: Final = "E_SUPERVISOR_OUT_OF_SCOPE"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Decision(StrEnum):
    RUN = "run"
    CONFIRM = "confirm"
    REFUSE = "refuse"


@dataclass(frozen=True, slots=True)
class Verdict:
    decision: Decision
    tier: Tier
    error_code: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ConfirmOutcome:
    answer: ConfirmationAnswer
    channel: str  # click / text / voice / stop / cancel, or system for a timeout


@dataclass(slots=True)
class _Waiting:
    confirmation: PendingConfirmation
    future: asyncio.Future[ConfirmOutcome]
    deadline: float  # event-loop time


class Supervisor:
    def __init__(
        self,
        *,
        history: HistoryStore,
        audit: AuditLog,
        bus: EventBus,
        timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._history = history
        self._audit = audit
        self._bus = bus
        self._timeout_s = timeout_s
        self._clock = clock
        self._waiting: dict[str, _Waiting] = {}

    @property
    def timeout_s(self) -> float:
        return self._timeout_s

    def evaluate(self, skill: AnySkill, params: SkillParams, scope: CapabilityScope) -> Verdict:
        tier = skill.tier_for(params)
        if not scope.allows(skill.id):
            return Verdict(
                Decision.REFUSE, tier, ERR_OUT_OF_SCOPE, f"{skill.id} is not allowed for this task"
            )
        policy = policy_for(tier)
        if policy is TierPolicy.REFUSE:
            return Verdict(
                Decision.REFUSE,
                tier,
                ERR_FORBIDDEN,
                "Forbidden actions (T3) never run; this one is for you to do yourself.",
            )
        if policy is TierPolicy.CONFIRM:
            return Verdict(Decision.CONFIRM, tier)
        return Verdict(Decision.RUN, tier)

    # ---- confirmations (T2) ----

    async def request(self, *, task_id: str, step_id: str, prompt: str) -> PendingConfirmation:
        """Register, store and announce a confirmation; then :meth:`wait` for the answer."""
        now = self._clock()
        confirmation = PendingConfirmation(
            id=new_id(),
            task_id=task_id,
            step_id=step_id,
            prompt=prompt,
            requested_at=now,
            expires_at=now + timedelta(seconds=self._timeout_s),
        )
        loop = asyncio.get_running_loop()
        self._waiting[confirmation.id] = _Waiting(
            confirmation, loop.create_future(), loop.time() + self._timeout_s
        )
        await self._history.add_confirmation(confirmation)
        await self._audit.record(
            actor="ace",
            event_type="confirm.requested",
            summary=f"asked to confirm: {prompt}",
            tier=Tier.T2,
            task_id=task_id,
            step_id=step_id,
            data={"confirmation_id": confirmation.id, "timeout_s": self._timeout_s},
        )
        await self._bus.publish(ConfirmationRequested(confirmation=confirmation))
        return confirmation

    async def wait(self, confirmation_id: str) -> ConfirmOutcome:
        """Sharan's answer, or TIMEOUT when the time runs out. Cancelling this leaves the stored
        confirmation unanswered (the core is stopping)."""
        waiting = self._waiting[confirmation_id]
        remaining = max(0.0, waiting.deadline - asyncio.get_running_loop().time())
        try:
            outcome = await asyncio.wait_for(waiting.future, remaining)
        except TimeoutError:
            outcome = ConfirmOutcome(ConfirmationAnswer.TIMEOUT, "system")
        finally:
            self._waiting.pop(confirmation_id, None)
        confirmation = waiting.confirmation
        await self._history.resolve_confirmation(
            confirmation_id,
            answer=outcome.answer,
            channel=outcome.channel,
            responded_at=self._clock(),
        )
        await self._audit.record(
            actor="system" if outcome.answer is ConfirmationAnswer.TIMEOUT else "user",
            event_type="confirm.answered",
            summary=f"confirmation answered: {outcome.answer.value}",
            tier=Tier.T2,
            task_id=confirmation.task_id,
            step_id=confirmation.step_id,
            data={
                "confirmation_id": confirmation_id,
                "answer": outcome.answer.value,
                "channel": outcome.channel,
            },
        )
        return outcome

    def respond(self, confirmation_id: str, answer: ConfirmationAnswer, channel: str) -> bool:
        """Answer a pending confirmation; False if it is unknown, answered or expired."""
        if answer is ConfirmationAnswer.TIMEOUT:
            raise ValueError("only the Supervisor times a confirmation out")
        waiting = self._waiting.get(confirmation_id)
        if waiting is None or waiting.future.done():
            return False
        waiting.future.set_result(ConfirmOutcome(answer, channel))
        return True

    def pending(self) -> list[PendingConfirmation]:
        """Unanswered confirmations, oldest first."""
        return [w.confirmation for w in self._waiting.values() if not w.future.done()]

    def newest_pending(self) -> PendingConfirmation | None:
        pending = self.pending()
        return pending[-1] if pending else None

    def pending_for_task(self, task_id: str) -> PendingConfirmation | None:
        return next((c for c in self.pending() if c.task_id == task_id), None)
