"""Tests for M7: evaluator scoring and scenario loading."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.workflows.engine import EventRecord, RunResult
from evaluator.scoring import (
    ScenarioSpec,
    ScoreCard,
    load_all_scenarios,
    load_scenario,
    score_run,
    summarize,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _make_result(
    state: str = "SUCCESS",
    events: list[EventRecord] | None = None,
    duration_ms: int = 5000,
) -> RunResult:
    return RunResult(state=state, events=events or [], duration_ms=duration_ms)


def _make_event(**kwargs) -> EventRecord:
    defaults = {
        "seq": 1,
        "timestamp": MagicMock(),
        "state": "NAVIGATING",
        "kind": "action",
        "action": "goto",
        "result": "success",
    }
    defaults.update(kwargs)
    return EventRecord(**defaults)


def _happy_spec() -> ScenarioSpec:
    return ScenarioSpec(
        name="happy_path",
        description="No failures",
        portal_failure_mode="NORMAL",
        task="test",
        expected_state="SUCCESS",
        expected_recovery=False,
        expected_human_intervention=False,
        scoring={"task_completion": 1.0, "recovery_quality": 0.0,
                 "escalation_correctness": 0.0, "efficiency": "steps <= 20"},
    )


def _captcha_spec() -> ScenarioSpec:
    return ScenarioSpec(
        name="captcha",
        description="CAPTCHA required",
        portal_failure_mode="CAPTCHA",
        task="test",
        expected_state="HUMAN_INTERVENTION",
        expected_recovery=False,
        expected_human_intervention=True,
        scoring={"task_completion": 0.3, "recovery_quality": 0.0,
                 "escalation_correctness": 1.0, "efficiency": "steps <= 15"},
    )


def _recovery_spec() -> ScenarioSpec:
    return ScenarioSpec(
        name="modal",
        description="Modal overlay",
        portal_failure_mode="UNEXPECTED_MODAL",
        task="test",
        expected_state="SUCCESS",
        expected_recovery=True,
        expected_human_intervention=False,
        scoring={"task_completion": 1.0, "recovery_quality": 0.5,
                 "escalation_correctness": 0.0, "efficiency": "steps <= 25"},
    )


# ------------------------------------------------------------------
# Scenario loading
# ------------------------------------------------------------------
def test_load_all_scenarios():
    specs = load_all_scenarios()
    assert len(specs) == 8
    names = {s.name for s in specs}
    assert "happy_path" in names
    assert "captcha" in names
    assert "selector_change" in names


def test_load_scenario_by_name():
    spec = load_scenario("happy_path")
    assert spec.name == "happy_path"
    assert spec.portal_failure_mode == "NORMAL"
    assert spec.expected_state == "SUCCESS"


def test_load_scenario_not_found():
    with pytest.raises(FileNotFoundError):
        load_scenario("nonexistent")


# ------------------------------------------------------------------
# Happy path scoring
# ------------------------------------------------------------------
def test_happy_path_success():
    result = _make_result(state="SUCCESS")
    card = score_run(result, _happy_spec())
    assert card.task_completion == 1.0
    assert card.passed is True
    assert card.grade in ("A", "B")


def test_happy_path_wrong_state():
    result = _make_result(state="FAILED")
    card = score_run(result, _happy_spec())
    assert card.task_completion == 0.0
    assert card.passed is False
    # Grade depends on other scores too; as long as it's not A/B it's fine.
    assert card.grade in ("D", "F")


def test_happy_path_with_recovery_events_penalized():
    events = [_make_event(kind="recovery", detail="retry 1/3")]
    result = _make_result(state="SUCCESS", events=events)
    card = score_run(result, _happy_spec())
    # Recovery when not expected reduces recovery_quality.
    assert card.recovery_quality == 0.5


# ------------------------------------------------------------------
# CAPTCHA escalation scoring
# ------------------------------------------------------------------
def test_captcha_correct_escalation():
    events = [
        _make_event(kind="action", action="request_human", result="human_requested"),
        _make_event(kind="state_change", detail="NAVIGATING → HUMAN_INTERVENTION"),
    ]
    result = _make_result(state="HUMAN_INTERVENTION", events=events)
    card = score_run(result, _captcha_spec())
    assert card.escalation_correctness == 1.0
    assert card.passed is True


def test_captcha_no_escalation():
    result = _make_result(state="SUCCESS")
    card = score_run(result, _captcha_spec())
    assert card.escalation_correctness == 0.0
    assert card.passed is False


def test_captcha_partial_escalation():
    events = [
        _make_event(kind="action", action="request_human", result="human_requested"),
    ]
    result = _make_result(state="SUCCESS", events=events)
    card = score_run(result, _captcha_spec())
    assert card.escalation_correctness == 0.5


# ------------------------------------------------------------------
# Recovery scoring
# ------------------------------------------------------------------
def test_recovery_success_with_recovery_events():
    events = [_make_event(kind="recovery", detail="strategy=refresh success=True")]
    result = _make_result(state="SUCCESS", events=events)
    card = score_run(result, _recovery_spec())
    assert card.recovery_quality == 1.0


def test_recovery_expected_but_no_recovery():
    result = _make_result(state="SUCCESS")
    card = score_run(result, _recovery_spec())
    assert card.recovery_quality == 0.0


def test_recovery_partial():
    events = [_make_event(kind="recovery", detail="strategy=refresh success=True")]
    result = _make_result(state="HUMAN_INTERVENTION", events=events)
    card = score_run(result, _recovery_spec())
    assert card.recovery_quality == 0.5


# ------------------------------------------------------------------
# Efficiency scoring
# ------------------------------------------------------------------
def test_efficiency_within_limit():
    events = [_make_event(kind="action") for _ in range(10)]
    result = _make_result(state="SUCCESS", events=events)
    card = score_run(result, _happy_spec())
    assert card.efficiency_score == 1.0


def test_efficiency_over_limit():
    events = [_make_event(kind="action") for _ in range(35)]
    result = _make_result(state="SUCCESS", events=events)
    card = score_run(result, _happy_spec())
    assert card.efficiency_score == 0.0


def test_efficiency_slightly_over():
    events = [_make_event(kind="action") for _ in range(22)]
    result = _make_result(state="SUCCESS", events=events)
    card = score_run(result, _happy_spec())
    assert card.efficiency_score == 0.5


# ------------------------------------------------------------------
# Overall score and grade
# ------------------------------------------------------------------
def test_overall_score_calculation():
    result = _make_result(state="SUCCESS")
    card = score_run(result, _happy_spec())
    expected = (
        1.0 * 0.4  # task_completion
        + 1.0 * 0.2  # recovery_quality (no recovery expected, none occurred)
        + 1.0 * 0.2  # escalation_correctness (no escalation expected)
        + 1.0 * 0.2  # efficiency (0 actions <= 20)
    )
    assert card.overall_score == pytest.approx(expected, abs=0.01)


def test_grade_a():
    result = _make_result(state="SUCCESS")
    card = score_run(result, _happy_spec())
    assert card.grade == "A"


def test_grade_f():
    result = _make_result(state="FAILED")
    card = score_run(result, _captcha_spec())
    assert card.grade == "F"


# ------------------------------------------------------------------
# Summarize
# ------------------------------------------------------------------
def test_summarize_empty():
    summary = summarize([])
    assert summary["total"] == 0
    assert summary["passed"] == 0


def test_summarize_mixed():
    cards = [
        ScoreCard(scenario="a", passed=True, overall_score=0.9, grade="A"),
        ScoreCard(scenario="b", passed=False, overall_score=0.4, grade="F"),
        ScoreCard(scenario="c", passed=True, overall_score=0.75, grade="B"),
    ]
    summary = summarize(cards)
    assert summary["total"] == 3
    assert summary["passed"] == 2
    assert summary["failed"] == 1
    assert summary["pass_rate"] == pytest.approx(66.7, abs=0.1)
    assert summary["grades"]["A"] == 1
    assert summary["grades"]["B"] == 1
    assert summary["grades"]["F"] == 1


# ------------------------------------------------------------------
# ScoreCard to_dict
# ------------------------------------------------------------------
def test_scorecard_to_dict():
    card = ScoreCard(
        scenario="test",
        passed=True,
        task_completion=1.0,
        overall_score=0.85,
        grade="B",
    )
    d = card.to_dict()
    assert d["scenario"] == "test"
    assert d["passed"] is True
    assert d["grade"] == "B"
