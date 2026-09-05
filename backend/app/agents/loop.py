"""Agent loop: drives execution by calling the planner, validating, and executing.

The loop is the core runtime. Each iteration:
1. Build a PlannerInput from the current state + observation.
2. Ask the planner for the next action.
3. Validate the action (schema + policy).
4. Execute the action via the browser executor.
5. Update state and record events.
6. Check termination conditions (finish, max steps, human intervention).

The loop handles retries on transient failures and delegates to the recovery
engine for CAPTCHA/modals/session expiry.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.agents.planner import BasePlanner, create_planner
from app.agents.schemas import AgentState, PlannerOutput
from app.browser.actions import (
    AgentAction,
    Finish,
    RequestHuman,
)
from app.browser.executor import BrowserExecutor, BrowserError
from app.browser.observation import PageObservation
from app.browser.validator import ActionValidationError, ActionValidator
from app.workflows.engine import EventRecord, RunResult
from app.workflows.state_machine import StateMachine

logger = logging.getLogger(__name__)


@dataclass
class AgentLoop:
    """Drives a single agent run to completion.

    Usage::

        loop = AgentLoop(executor, planner=planner, task="process invoice")
        result = await loop.run()
    """

    executor: BrowserExecutor
    planner: Optional[BasePlanner] = None
    task: str = ""
    max_steps: int = 100
    max_retries: int = 3
    validator: Optional[ActionValidator] = None

    def __post_init__(self):
        if self.planner is None:
            self.planner = create_planner()
        if self.validator is None:
            self.validator = ActionValidator()
        self._state = AgentState(task=self.task, max_steps=self.max_steps)
        self._sm = StateMachine()
        self._events: list[EventRecord] = []
        self._seq = 0
        self._retries = 0

    # ------------------------------------------------------------------ events
    def _record(self, kind: str, **kwargs) -> EventRecord:
        self._seq += 1
        ev = EventRecord(
            seq=self._seq,
            timestamp=datetime.now(timezone.utc),
            state=self._sm.state,
            kind=kind,
            **kwargs,
        )
        self._events.append(ev)
        return ev

    # ------------------------------------------------------------------ state
    def _transition(self, target: str) -> None:
        old = self._sm.state
        self._sm.transition(target)
        self._state.state = target
        self._record("state_change", detail=f"{old} → {target}")

    def _force_state(self, target: str) -> None:
        old = self._sm.state
        self._sm.force(target)
        self._state.state = target
        self._record("state_change", detail=f"{old} → {target} (forced)")

    # ------------------------------------------------------------------ main loop
    async def run(self) -> RunResult:
        """Execute the agent loop until termination."""
        t0 = time.monotonic()
        self._state.started_at = datetime.now(timezone.utc).isoformat()
        self._transition("PLANNING")

        # Initial observation.
        observation = await self.executor.observe(screenshot=True)
        self._record(
            "observation",
            detail=f"URL: {observation.url}  Title: {observation.title}",
        )

        while not self._state.is_terminal:
            # Step cap.
            if self._state.step >= self.max_steps:
                self._record("error", detail="max steps exceeded")
                self._force_state("FAILED")
                break

            # Build planner input.
            planner_input = self._state.to_planner_input(observation)

            # Ask planner for action.
            try:
                planner_output = await self.planner.decide(planner_input)
            except Exception as exc:
                logger.error("Planner failed: %s", exc)
                self._record("error", detail=f"planner error: {exc}")
                self._force_state("FAILED")
                break

            action = planner_output.action
            reasoning = planner_output.reasoning

            self._record(
                "planner_decision",
                action=action.action,
                detail=reasoning[:500],
            )

            # Handle terminal actions.
            if isinstance(action, Finish):
                self._record(
                    "action",
                    action="finish",
                    target=action.description,
                    result="success",
                )
                self._transition("SUBMITTING")
                self._transition("SUCCESS")
                break

            if isinstance(action, RequestHuman):
                self._record(
                    "action",
                    action="request_human",
                    target=action.reason,
                    result="human_requested",
                )
                self._force_state("HUMAN_INTERVENTION")
                break

            # Validate action.
            try:
                self.validator.validate(action, observation)
            except ActionValidationError as exc:
                logger.warning("Action validation failed: %s", exc)
                self._record(
                    "action",
                    action=action.action,
                    target=str(getattr(action, "target", "")),
                    result="rejected",
                    failure_reason=str(exc),
                )
                self._state.record_action(
                    action.action,
                    str(getattr(action, "target", "")),
                    "failure",
                    failure_reason=str(exc),
                )
                # Let the planner try again with this failure context.
                if self._state.step >= self.max_steps:
                    self._force_state("FAILED")
                continue

            # Route action → state transition.
            self._transition_for_action(action.action)

            # Execute action.
            t_start = time.monotonic()
            try:
                observation = await self._perform(action)
                dt = int((time.monotonic() - t_start) * 1000)
                self._record(
                    "action",
                    action=action.action,
                    target=str(getattr(action, "target", None)),
                    result="success",
                    duration_ms=dt,
                )
                self._state.record_action(
                    action.action,
                    str(getattr(action, "target", "")),
                    "success",
                    duration_ms=dt,
                )
                self._retries = 0

            except BrowserError as exc:
                dt = int((time.monotonic() - t_start) * 1000)
                self._record(
                    "action",
                    action=action.action,
                    target=str(getattr(action, "target", "")),
                    result="failure",
                    failure_reason=exc.failure_reason,
                    detail=str(exc),
                    duration_ms=dt,
                )
                self._state.record_action(
                    action.action,
                    str(getattr(action, "target", "")),
                    "failure",
                    failure_reason=exc.failure_reason,
                    duration_ms=dt,
                )
                self._retries += 1

                # Check if we should recover or give up.
                if exc.failure_reason == "captcha_detected":
                    self._state.captcha_detected = True
                    self._force_state("HUMAN_INTERVENTION")
                    break
                if exc.failure_reason == "session_expired":
                    self._state.session_expired = True
                if self._retries > self.max_retries:
                    self._record(
                        "recovery", detail="exhausted retries, failing"
                    )
                    self._force_state("FAILED")
                    break
                self._record(
                    "recovery",
                    detail=f"retry {self._retries}/{self.max_retries}",
                )
                await self.executor.wait(300)

            except Exception as exc:
                dt = int((time.monotonic() - t_start) * 1000)
                self._record(
                    "error",
                    action=action.action,
                    detail=str(exc),
                    duration_ms=dt,
                )
                self._force_state("FAILED")
                break

        dt = int((time.monotonic() - t0) * 1000)
        return RunResult(
            state=self._sm.state,
            events=list(self._events),
            duration_ms=dt,
        )

    # ------------------------------------------------------------------ dispatch
    async def _perform(self, action: AgentAction) -> PageObservation:
        """Dispatch a single action to the executor."""
        name = action.action
        if name == "goto":
            return await self.executor.goto(action.url)
        elif name == "click":
            await self.executor.click(action.target)
            return await self.executor.observe(screenshot=False)
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
            await self.executor.extract(action.target)
            return await self.executor.observe(screenshot=False)
        else:
            raise BrowserError(f"Unknown action: {name}", failure_reason="unknown_action")

    def _transition_for_action(self, action_name: str) -> None:
        """Map an action name to the appropriate state transition."""
        current = self._sm.state
        if action_name == "goto":
            if current in ("PLANNING", "CREATED"):
                self._transition("NAVIGATING")
            elif current == "RECOVERING":
                self._transition("NAVIGATING")
        elif action_name in ("click", "type", "select"):
            if current in ("PLANNING", "NAVIGATING", "CREATED"):
                self._transition("FILLING_FORM")
        elif action_name == "upload":
            if current in ("FILLING_FORM", "NAVIGATING"):
                self._transition("UPLOADING")

    # ------------------------------------------------------------------ introspection
    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def events(self) -> list[EventRecord]:
        return list(self._events)
