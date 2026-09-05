"""Agent-level schemas for planner I/O.

These wrap the browser observation/action schemas into the structured format
the LLM planner receives and produces.  The planner never sees raw DOM or
raw Playwright — it reasons over :class:`PlannerInput` and emits
:class:`PlannerOutput`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.browser.actions import AgentAction, Target
from app.browser.observation import PageObservation


# ------------------------------------------------------------------
# History entry: one past action+result for the planner's context
# ------------------------------------------------------------------
class ActionHistoryEntry(BaseModel):
    """A single past action and its outcome, shown to the planner."""

    step: int
    action: str
    target_label: str = ""
    result: str  # "success" | "failure" | "skipped"
    failure_reason: str = ""
    duration_ms: int = 0
    timestamp: str = ""


# ------------------------------------------------------------------
# Planner input: what the LLM sees each turn
# ------------------------------------------------------------------
class PlannerInput(BaseModel):
    """The structured prompt sent to the planner each decision step.

    The planner must look at the current observation, the task goal, and the
    action history, then emit exactly one :class:`PlannerOutput`.
    """

    task: str = Field(..., description="Natural language task description")
    state: str = Field(..., description="Current workflow state (e.g. FILLING_FORM)")
    step: int = Field(..., ge=1, description="Current step number (1-indexed)")
    max_steps: int = Field(100, description="Hard cap on steps")
    observation: PageObservation = Field(..., description="Current page snapshot")
    history: list[ActionHistoryEntry] = Field(
        default_factory=list,
        description="Recent action history for context",
    )
    failure_context: Optional[str] = Field(
        None,
        description="If the last action failed, a description of what went wrong",
    )
    captcha_detected: bool = Field(
        False, description="True if a CAPTCHA was detected on the page"
    )
    modal_detected: bool = Field(
        False, description="True if an unexpected modal was detected"
    )
    session_expired: bool = Field(
        False, description="True if the session has expired"
    )

    def to_prompt_context(self) -> str:
        """Render a compact text summary suitable for LLM prompting."""
        lines = [
            f"Task: {self.task}",
            f"State: {self.state}  Step: {self.step}/{self.max_steps}",
            f"URL: {self.observation.url}",
            f"Title: {self.observation.title}",
        ]
        if self.captcha_detected:
            lines.append("⚠ CAPTCHA detected — cannot automate, request human")
        if self.modal_detected:
            lines.append("⚠ Unexpected modal detected — dismiss it")
        if self.session_expired:
            lines.append("⚠ Session expired — re-authenticate")
        if self.failure_context:
            lines.append(f"Last failure: {self.failure_context}")
        if self.observation.interactive_elements:
            lines.append("Visible elements:")
            for el in self.observation.interactive_elements:
                val = f" (current: {el.value!r})" if el.value else ""
                lines.append(f"  [{el.id}] {el.role}: {el.label}{val}")
        if self.history:
            lines.append("Recent actions:")
            for h in self.history[-5:]:
                lines.append(
                    f"  step {h.step}: {h.action}({h.target_label}) → {h.result}"
                )
        return "\n".join(lines)


# ------------------------------------------------------------------
# Planner output: what the LLM emits each turn
# ------------------------------------------------------------------
class PlannerOutput(BaseModel):
    """The planner's decision for one step.

    Contains exactly one action and an optional reasoning field explaining
    why this action was chosen.
    """

    reasoning: str = Field(
        "", description="Brief explanation of why this action was chosen"
    )
    action: AgentAction = Field(..., description="The action to execute")


# ------------------------------------------------------------------
# Agent state: full run state carried across steps
# ------------------------------------------------------------------
class AgentState(BaseModel):
    """Mutable state carried across planner steps.

    The engine updates this after each action; the planner reads it to
    build the next :class:`PlannerInput`.
    """

    task: str = ""
    state: str = "CREATED"
    step: int = 0
    max_steps: int = 100
    history: list[ActionHistoryEntry] = Field(default_factory=list)
    last_failure: Optional[str] = None
    captcha_detected: bool = False
    modal_detected: bool = False
    session_expired: bool = False
    started_at: Optional[str] = None

    def record_action(
        self,
        action: str,
        target_label: str,
        result: str,
        failure_reason: str = "",
        duration_ms: int = 0,
    ) -> None:
        self.step += 1
        self.history.append(
            ActionHistoryEntry(
                step=self.step,
                action=action,
                target_label=target_label,
                result=result,
                failure_reason=failure_reason,
                duration_ms=duration_ms,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
        if result == "failure":
            self.last_failure = failure_reason or "unknown"
        else:
            self.last_failure = None

    def to_planner_input(self, observation: PageObservation) -> PlannerInput:
        """Build a PlannerInput from the current state + a fresh observation."""
        return PlannerInput(
            task=self.task,
            state=self.state,
            step=self.step + 1,
            max_steps=self.max_steps,
            observation=observation,
            history=list(self.history[-10:]),
            failure_context=self.last_failure,
            captcha_detected=self.captcha_detected or observation.captcha_present,
            modal_detected=self.modal_detected or observation.modal_present,
            session_expired=self.session_expired or observation.session_expired,
        )

    @property
    def is_terminal(self) -> bool:
        return self.state in ("SUCCESS", "FAILED")
