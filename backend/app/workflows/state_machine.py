"""Deterministic workflow state machine.

The state machine is the source of truth for workflow progression.  The LLM
(or a hard-coded script) proposes actions; the state machine owns the
transitions.  Invalid transitions are rejected.

States are defined in :mod:`app.models.run`; transitions here are strict.
"""

from __future__ import annotations

from app.models.run import RunState


# Allowed transitions: current_state → {next_states}
_TRANSITIONS: dict[str, set[str]] = {
    RunState.CREATED: {
        RunState.PLANNING,
        RunState.NAVIGATING,
        RunState.ACTION_FAILED,
        RunState.FAILED,
    },
    RunState.PLANNING: {
        RunState.NAVIGATING,
        RunState.FILLING_FORM,
        RunState.UPLOADING,
        RunState.SUBMITTING,
        RunState.ACTION_FAILED,
        RunState.FAILED,
        RunState.HUMAN_INTERVENTION,
    },
    RunState.NAVIGATING: {
        RunState.FILLING_FORM,
        RunState.UPLOADING,
        RunState.VALIDATING,
        RunState.SUBMITTING,
        RunState.SUCCESS,
        RunState.ACTION_FAILED,
        RunState.RECOVERING,
        RunState.FAILED,
        RunState.HUMAN_INTERVENTION,
    },
    RunState.FILLING_FORM: {
        RunState.FILLING_FORM,  # fill another field
        RunState.UPLOADING,
        RunState.VALIDATING,
        RunState.SUBMITTING,
        RunState.SUCCESS,
        RunState.ACTION_FAILED,
        RunState.RECOVERING,
        RunState.FAILED,
        RunState.HUMAN_INTERVENTION,
    },
    RunState.UPLOADING: {
        RunState.VALIDATING,
        RunState.SUBMITTING,
        RunState.ACTION_FAILED,
        RunState.RECOVERING,
        RunState.FAILED,
        RunState.HUMAN_INTERVENTION,
    },
    RunState.VALIDATING: {
        RunState.SUBMITTING,
        RunState.FILLING_FORM,
        RunState.ACTION_FAILED,
        RunState.RECOVERING,
        RunState.FAILED,
        RunState.HUMAN_INTERVENTION,
    },
    RunState.SUBMITTING: {
        RunState.SUCCESS,
        RunState.ACTION_FAILED,
        RunState.RECOVERING,
        RunState.FAILED,
        RunState.HUMAN_INTERVENTION,
    },
    RunState.ACTION_FAILED: {
        RunState.RECOVERING,
        RunState.FAILED,
        RunState.HUMAN_INTERVENTION,
    },
    RunState.RECOVERING: {
        RunState.FILLING_FORM,
        RunState.UPLOADING,
        RunState.SUBMITTING,
        RunState.ACTION_FAILED,
        RunState.FAILED,
        RunState.HUMAN_INTERVENTION,
    },
    RunState.HUMAN_INTERVENTION: {
        RunState.FILLING_FORM,
        RunState.UPLOADING,
        RunState.SUBMITTING,
        RunState.RECOVERING,
        RunState.SUCCESS,
        RunState.FAILED,
    },
    RunState.SUCCESS: set(),
    RunState.FAILED: set(),
}


class InvalidTransition(Exception):
    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(
            f"Invalid transition: {current!r} → {target!r}. "
            f"Allowed: {sorted(_TRANSITIONS.get(current, set()))}"
        )


class StateMachine:
    """Tracks the current state and enforces valid transitions."""

    def __init__(self, initial: str = RunState.CREATED):
        self._state = initial
        self._history: list[str] = [initial]

    @property
    def state(self) -> str:
        return self._state

    @property
    def history(self) -> list[str]:
        return list(self._history)

    @property
    def is_terminal(self) -> bool:
        return self._state in (RunState.SUCCESS, RunState.FAILED)

    def transition(self, target: str) -> None:
        allowed = _TRANSITIONS.get(self._state, set())
        if target not in allowed:
            raise InvalidTransition(self._state, target)
        self._state = target
        self._history.append(target)

    def force(self, target: str) -> None:
        """Force a transition without validation (for recovery / resume)."""
        self._state = target
        self._history.append(target)
