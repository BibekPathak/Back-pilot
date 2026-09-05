"""Tests for the workflow state machine and engine."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.run import RunState
from app.workflows.state_machine import InvalidTransition, StateMachine


# ------------------------------------------------------------------
# State machine
# ------------------------------------------------------------------
def test_initial_state():
    sm = StateMachine()
    assert sm.state == RunState.CREATED
    assert sm.history == [RunState.CREATED]
    assert sm.is_terminal is False


def test_valid_transitions():
    sm = StateMachine()
    sm.transition(RunState.PLANNING)
    sm.transition(RunState.NAVIGATING)
    sm.transition(RunState.FILLING_FORM)
    sm.transition(RunState.UPLOADING)
    sm.transition(RunState.VALIDATING)
    sm.transition(RunState.SUBMITTING)
    sm.transition(RunState.SUCCESS)
    assert sm.is_terminal is True
    assert sm.history == [
        RunState.CREATED, RunState.PLANNING, RunState.NAVIGATING,
        RunState.FILLING_FORM, RunState.UPLOADING, RunState.VALIDATING,
        RunState.SUBMITTING, RunState.SUCCESS,
    ]


def test_invalid_transition_raises():
    sm = StateMachine()
    with pytest.raises(InvalidTransition) as exc_info:
        sm.transition(RunState.SUCCESS)
    assert exc_info.value.current == RunState.CREATED
    assert exc_info.value.target == RunState.SUCCESS


def test_failure_path():
    sm = StateMachine()
    sm.transition(RunState.PLANNING)
    sm.transition(RunState.NAVIGATING)
    sm.transition(RunState.ACTION_FAILED)
    sm.transition(RunState.RECOVERING)
    sm.transition(RunState.FILLING_FORM)
    sm.transition(RunState.SUBMITTING)
    sm.transition(RunState.SUCCESS)
    assert sm.is_terminal is True


def test_human_intervention_path():
    sm = StateMachine()
    sm.transition(RunState.PLANNING)
    sm.transition(RunState.NAVIGATING)
    sm.transition(RunState.HUMAN_INTERVENTION)
    sm.transition(RunState.FILLING_FORM)
    sm.transition(RunState.SUBMITTING)
    sm.transition(RunState.SUCCESS)


def test_force_transition():
    sm = StateMachine()
    sm.force(RunState.SUCCESS)
    assert sm.state == RunState.SUCCESS
    assert sm.is_terminal is True


def test_terminal_blocks_further_transitions():
    sm = StateMachine()
    sm.force(RunState.SUCCESS)
    with pytest.raises(InvalidTransition):
        sm.transition(RunState.FILLING_FORM)


def test_filling_form_self_transition():
    """FILLING_FORM can transition to itself (fill another field)."""
    sm = StateMachine()
    sm.transition(RunState.PLANNING)
    sm.transition(RunState.FILLING_FORM)
    sm.transition(RunState.FILLING_FORM)
    assert sm.state == RunState.FILLING_FORM
    # history: CREATED, PLANNING, FILLING_FORM, FILLING_FORM = 4
    assert len(sm.history) == 4


def test_failed_is_terminal():
    sm = StateMachine()
    sm.force(RunState.FAILED)
    assert sm.is_terminal is True


# ------------------------------------------------------------------
# Workflow engine (unit tests without real browser)
# ------------------------------------------------------------------
def test_event_record_to_dict():
    from app.workflows.engine import EventRecord
    from datetime import datetime, timezone
    ev = EventRecord(
        seq=1,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        state=RunState.CREATED,
        kind="action",
        action="goto",
        result="success",
        duration_ms=123,
    )
    d = ev.to_dict()
    assert d["seq"] == 1
    assert d["action"] == "goto"
    assert d["duration_ms"] == 123
