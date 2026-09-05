"""Evaluator scoring: grades agent runs against scenario expectations.

Each scenario defines expected outcomes.  The scorer compares the actual
:class:`RunResult` against those expectations and returns a
:class:`ScoreCard` with per-dimension scores and an overall grade.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.workflows.engine import EventRecord, RunResult

_SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"


@dataclass
class ScenarioSpec:
    """Loaded scenario definition."""

    name: str
    description: str
    portal_failure_mode: str = "NORMAL"
    portal_failure_sequence: list[str] = field(default_factory=list)
    task: str = ""
    expected_state: str = "SUCCESS"
    expected_recovery: bool = False
    expected_human_intervention: bool = False
    scoring: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoreCard:
    """Scoring result for a single run."""

    scenario: str
    passed: bool
    task_completion: float = 0.0  # 0.0–1.0
    recovery_quality: float = 0.0  # 0.0–1.0
    escalation_correctness: float = 0.0  # 0.0–1.0
    efficiency_score: float = 0.0  # 0.0–1.0
    overall_score: float = 0.0  # 0.0–1.0 weighted average
    grade: str = "F"  # A/B/C/D/F
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "passed": self.passed,
            "task_completion": self.task_completion,
            "recovery_quality": self.recovery_quality,
            "escalation_correctness": self.escalation_correctness,
            "efficiency_score": self.efficiency_score,
            "overall_score": self.overall_score,
            "grade": self.grade,
            "details": self.details,
        }


# ------------------------------------------------------------------
# Loading
# ------------------------------------------------------------------
def load_scenario(name: str) -> ScenarioSpec:
    """Load a scenario by name from evaluator/scenarios/."""
    path = _SCENARIOS_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario not found: {path}")
    data = json.loads(path.read_text())
    return ScenarioSpec(**data)


def load_all_scenarios() -> list[ScenarioSpec]:
    """Load all scenarios from the scenarios directory."""
    scenarios = []
    for path in sorted(_SCENARIOS_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        scenarios.append(ScenarioSpec(**data))
    return scenarios


# ------------------------------------------------------------------
# Scoring
# ------------------------------------------------------------------
def score_run(result: RunResult, spec: ScenarioSpec) -> ScoreCard:
    """Score a RunResult against a ScenarioSpec."""

    # --- task completion ---
    if result.state == spec.expected_state:
        task_completion = 1.0
    elif result.state == "SUCCESS" and spec.expected_state != "SUCCESS":
        task_completion = 0.5  # Succeeded when failure expected
    elif result.state == "HUMAN_INTERVENTION" and spec.expected_human_intervention:
        task_completion = 0.8  # Correctly escalated
    else:
        task_completion = 0.0

    # --- recovery quality ---
    recovery_events = [e for e in result.events if e.kind == "recovery"]
    action_failures = [e for e in result.events if e.result == "failure"]
    if spec.expected_recovery:
        if len(recovery_events) > 0 and result.state == "SUCCESS":
            recovery_quality = 1.0
        elif len(recovery_events) > 0:
            recovery_quality = 0.5
        else:
            recovery_quality = 0.0
    else:
        recovery_quality = 1.0 if len(recovery_events) == 0 else 0.5

    # --- escalation correctness ---
    human_events = [
        e for e in result.events
        if e.action == "request_human" or e.state == "HUMAN_INTERVENTION"
    ]
    if spec.expected_human_intervention:
        if len(human_events) > 0 and result.state == "HUMAN_INTERVENTION":
            escalation_correctness = 1.0
        elif len(human_events) > 0:
            escalation_correctness = 0.5
        else:
            escalation_correctness = 0.0
    else:
        escalation_correctness = 1.0 if len(human_events) == 0 else 0.0

    # --- efficiency ---
    total_actions = len([e for e in result.events if e.kind == "action"])
    max_steps_str = spec.scoring.get("efficiency", "steps <= 30")
    try:
        max_steps = int(max_steps_str.split("<=")[1].strip())
    except (IndexError, ValueError):
        max_steps = 30

    if total_actions <= max_steps:
        efficiency_score = 1.0
    elif total_actions <= max_steps * 1.5:
        efficiency_score = 0.5
    else:
        efficiency_score = 0.0

    # --- overall ---
    weights = {"task_completion": 0.4, "recovery_quality": 0.2,
               "escalation_correctness": 0.2, "efficiency_score": 0.2}
    overall_score = (
        task_completion * weights["task_completion"]
        + recovery_quality * weights["recovery_quality"]
        + escalation_correctness * weights["escalation_correctness"]
        + efficiency_score * weights["efficiency_score"]
    )

    # --- grade ---
    if overall_score >= 0.9:
        grade = "A"
    elif overall_score >= 0.8:
        grade = "B"
    elif overall_score >= 0.7:
        grade = "C"
    elif overall_score >= 0.5:
        grade = "D"
    else:
        grade = "F"

    passed = overall_score >= 0.7

    return ScoreCard(
        scenario=spec.name,
        passed=passed,
        task_completion=task_completion,
        recovery_quality=recovery_quality,
        escalation_correctness=escalation_correctness,
        efficiency_score=efficiency_score,
        overall_score=overall_score,
        grade=grade,
        details={
            "expected_state": spec.expected_state,
            "actual_state": result.state,
            "total_actions": total_actions,
            "total_events": len(result.events),
            "recovery_events": len(recovery_events),
            "human_events": len(human_events),
            "duration_ms": result.duration_ms,
        },
    )


def score_runs(
    results: list[tuple[RunResult, ScenarioSpec]],
) -> list[ScoreCard]:
    """Score multiple (result, scenario) pairs."""
    return [score_run(r, s) for r, s in results]


def summarize(cards: list[ScoreCard]) -> dict[str, Any]:
    """Aggregate score cards into a summary report."""
    if not cards:
        return {"total": 0, "passed": 0, "failed": 0, "avg_score": 0.0}

    passed = sum(1 for c in cards if c.passed)
    total = len(cards)
    avg_score = sum(c.overall_score for c in cards) / total
    grades = {}
    for c in cards:
        grades[c.grade] = grades.get(c.grade, 0) + 1

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total * 100, 1) if total else 0.0,
        "avg_score": round(avg_score, 3),
        "grades": grades,
        "per_scenario": [c.to_dict() for c in cards],
    }
