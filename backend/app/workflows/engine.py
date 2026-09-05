"""Workflow engine: orchestrates a run, records events, manages the state machine.

The engine is deterministic.  A run is a sequence of *steps*, each of which
is an action performed on the browser executor.  The engine records every
observation, action, result, failure, recovery attempt, and state transition
as an :class:`EventRecord`.

For M3 the engine is driven by a hard-coded script (no LLM).  Later
milestones inject the planner in the loop.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.browser.actions import AgentAction
from app.browser.executor import BrowserExecutor, BrowserError, ElementNotFound
from app.browser.observation import PageObservation
from app.models.run import RunState
from app.workflows.state_machine import StateMachine


@dataclass
class EventRecord:
    """A single event in the execution timeline."""

    seq: int
    timestamp: datetime
    state: str
    kind: str  # observation | action | result | recovery | state_change | error | screenshot
    action: str = ""
    target: str = ""
    result: str = ""
    failure_reason: str = ""
    detail: str = ""
    duration_ms: int = 0
    screenshot_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "timestamp": self.timestamp.isoformat(),
            "state": self.state,
            "kind": self.kind,
            "action": self.action,
            "target": self.target,
            "result": self.result,
            "failure_reason": self.failure_reason,
            "detail": self.detail,
            "duration_ms": self.duration_ms,
            "screenshot_path": self.screenshot_path,
        }


@dataclass
class RunResult:
    """Outcome of a completed run."""

    state: str
    events: list[EventRecord]
    duration_ms: int = 0
    error: str = ""

    @property
    def success(self) -> bool:
        return self.state == RunState.SUCCESS


class WorkflowEngine:
    """Drives a single run through the state machine and records events."""

    def __init__(
        self,
        executor: BrowserExecutor,
        *,
        max_steps: int = 100,
        max_retries: int = 3,
        max_recovery_attempts: int = 2,
    ):
        self.executor = executor
        self.sm = StateMachine()
        self.max_steps = max_steps
        self.max_retries = max_retries
        self.max_recovery_attempts = max_recovery_attempts
        self._events: list[EventRecord] = []
        self._seq = 0
        self._step = 0
        self._recovery_count = 0
        self._last_observation: Optional[PageObservation] = None

    # ------------------------------------------------------------------ events
    def _record(self, kind: str, **kwargs) -> EventRecord:
        self._seq += 1
        ev = EventRecord(
            seq=self._seq,
            timestamp=datetime.now(timezone.utc),
            state=self.sm.state,
            kind=kind,
            **kwargs,
        )
        self._events.append(ev)
        return ev

    def _record_state_change(self, old: str, new: str) -> None:
        self._record("state_change", detail=f"{old} → {new}")

    # ------------------------------------------------------------------ state
    def transition(self, target: str) -> None:
        old = self.sm.state
        self.sm.transition(target)
        self._record_state_change(old, target)

    def force_transition(self, target: str) -> None:
        old = self.sm.state
        self.sm.force(target)
        self._record_state_change(old, target)

    # ------------------------------------------------------------------ actions
    async def execute_action(self, action: AgentAction) -> PageObservation:
        """Execute a single action and return the resulting observation.

        Retries on transient failures up to ``self.max_retries``.
        """
        retries = 0
        last_error: Exception | None = None

        while retries <= self.max_retries:
            t0 = time.monotonic()
            try:
                obs = await self._perform(action)
                dt = int((time.monotonic() - t0) * 1000)
                self._record(
                    "action",
                    action=action.action,
                    target=str(getattr(action, "target", None) and getattr(action.target, "label", None)) or action.description,
                    result="success",
                    duration_ms=dt,
                )
                self._last_observation = obs
                return obs
            except ElementNotFound as exc:
                last_error = exc
                dt = int((time.monotonic() - t0) * 1000)
                self._record(
                    "action",
                    action=action.action,
                    target=str(getattr(action, "target", None) or action.description),
                    result="failure",
                    failure_reason=exc.failure_reason,
                    detail=str(exc),
                    duration_ms=dt,
                )
                retries += 1
                if retries <= self.max_retries:
                    self._record("recovery", detail=f"retry {retries}/{self.max_retries}")
                    await self.executor.wait(300)
            except BrowserError as exc:
                last_error = exc
                dt = int((time.monotonic() - t0) * 1000)
                self._record(
                    "action",
                    action=action.action,
                    target=str(getattr(action, "target", None) or action.description),
                    result="failure",
                    failure_reason=exc.failure_reason,
                    detail=str(exc),
                    duration_ms=dt,
                )
                retries += 1
                if retries <= self.max_retries:
                    self._record("recovery", detail=f"retry {retries}/{self.max_retries}")
                    await self.executor.wait(300)
            except Exception as exc:
                last_error = exc
                dt = int((time.monotonic() - t0) * 1000)
                self._record(
                    "error",
                    action=action.action,
                    detail=str(exc),
                    duration_ms=dt,
                )
                break

        if last_error:
            self._record("error", detail=f"exhausted retries: {last_error}")
        return self._last_observation or PageObservation(url="", title="")

    async def _perform(self, action: AgentAction) -> PageObservation:
        """Dispatch a single action to the executor."""
        name = action.action
        if name == "goto":
            return await self.executor.goto(action.url)
        elif name == "click":
            return await self.executor.click(action.target) or self._last_observation
        elif name == "type":
            await self.executor.type_text(action.target, action.text)
            return await self.executor.observe(screenshot=False)
        elif name == "select":
            await self.executor.select(action.target, action.value)
            return await self.executor.observe(screenshot=False)
        elif name == "upload":
            await self.executor.upload(action.target, action.filepath)
            return await self.executor.observe(screenshot=False)
        elif name == "wait":
            await self.executor.wait(action.ms)
            return await self.executor.observe(screenshot=False)
        elif name == "back":
            return await self.executor.back()
        elif name == "extract":
            text = await self.executor.extract(action.target)
            self._record("observation", detail=text[:500])
            return await self.executor.observe(screenshot=False)
        elif name == "finish":
            return await self.executor.observe()
        else:
            raise BrowserError(f"Unknown action: {name}", failure_reason="unknown_action")

    # ------------------------------------------------------------------ run
    async def run(self, steps: list[AgentAction]) -> RunResult:
        """Execute a fixed sequence of actions through the state machine.

        This is the M3 happy-path driver.  Later milestones inject the planner
        between observation and action selection.
        """
        t0 = time.monotonic()
        self.transition(RunState.PLANNING)

        for i, action in enumerate(steps):
            self._step = i + 1
            if self._step > self.max_steps:
                self._record("error", detail="max steps exceeded")
                self.force_transition(RunState.FAILED)
                break

            if self.sm.is_terminal:
                break

            # Route action → state transition.
            self._transition_for(action.action)

            result_obs = await self.execute_action(action)

            if action.action == "finish":
                self.transition(RunState.SUCCESS)
                break

        dt = int((time.monotonic() - t0) * 1000)
        return RunResult(
            state=self.sm.state,
            events=list(self._events),
            duration_ms=dt,
        )

    def _transition_for(self, action_name: str) -> None:
        """Map an action name to the appropriate state transition."""
        current = self.sm.state
        if action_name == "goto":
            if current in (RunState.PLANNING, RunState.CREATED):
                self.transition(RunState.NAVIGATING)
            elif current == RunState.RECOVERING:
                self.transition(RunState.NAVIGATING)
        elif action_name in ("click", "type", "select"):
            if current in (RunState.PLANNING, RunState.NAVIGATING, RunState.CREATED):
                self.transition(RunState.FILLING_FORM)
        elif action_name == "upload":
            if current in (RunState.FILLING_FORM, RunState.NAVIGATING):
                self.transition(RunState.UPLOADING)
        elif action_name == "finish":
            if current not in (RunState.SUCCESS, RunState.FAILED):
                self.transition(RunState.SUBMITTING)

    # ------------------------------------------------------------------ state
    @property
    def observation(self) -> Optional[PageObservation]:
        return self._last_observation

    @property
    def events(self) -> list[EventRecord]:
        return list(self._events)

    @property
    def current_state(self) -> str:
        return self.sm.state
