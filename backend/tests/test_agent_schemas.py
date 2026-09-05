"""Tests for M4: agent observation/action schemas and action validation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.schemas import (
    ActionHistoryEntry,
    AgentState,
    PlannerInput,
    PlannerOutput,
)
from app.browser.actions import (
    AgentAction,
    Click,
    Finish,
    Goto,
    RequestHuman,
    Target,
    Type,
    Upload,
    Wait,
)
from app.browser.observation import InteractiveElement, PageObservation
from app.browser.validator import ActionValidationError, ActionValidator


# ------------------------------------------------------------------
# PlannerInput
# ------------------------------------------------------------------
def _obs(**kwargs) -> PageObservation:
    defaults = {
        "url": "http://localhost:8081/invoices",
        "title": "Invoice Processing",
        "visible_text": "Invoice Number:",
        "interactive_elements": [
            InteractiveElement(id="e1", role="textbox", label="Invoice Number:"),
            InteractiveElement(id="e2", role="textbox", label="Vendor:"),
            InteractiveElement(id="e3", role="button", label="SAVE & CONTINUE"),
        ],
    }
    defaults.update(kwargs)
    return PageObservation(**defaults)


def test_planner_input_basic():
    pi = PlannerInput(
        task="process invoice",
        state="FILLING_FORM",
        step=3,
        observation=_obs(),
    )
    assert pi.task == "process invoice"
    assert pi.state == "FILLING_FORM"
    assert pi.step == 3
    assert len(pi.observation.interactive_elements) == 3


def test_planner_input_to_prompt_context():
    pi = PlannerInput(
        task="process invoice INV-29381",
        state="FILLING_FORM",
        step=5,
        observation=_obs(),
        history=[
            ActionHistoryEntry(step=1, action="goto", result="success"),
            ActionHistoryEntry(step=2, action="type", target_label="Username:", result="success"),
        ],
    )
    ctx = pi.to_prompt_context()
    assert "process invoice INV-29381" in ctx
    assert "FILLING_FORM" in ctx
    assert "e1" in ctx
    assert "goto" in ctx
    assert "type" in ctx


def test_planner_input_captcha_flag():
    pi = PlannerInput(
        task="solve captcha",
        state="NAVIGATING",
        step=1,
        observation=_obs(captcha_present=True),
        captcha_detected=True,
    )
    ctx = pi.to_prompt_context()
    assert "CAPTCHA" in ctx


def test_planner_input_modal_flag():
    pi = PlannerInput(
        task="dismiss modal",
        state="NAVIGATING",
        step=1,
        observation=_obs(),
        modal_detected=True,
    )
    ctx = pi.to_prompt_context()
    assert "modal" in ctx.lower()


def test_planner_input_failure_context():
    pi = PlannerInput(
        task="retry",
        state="RECOVERING",
        step=2,
        observation=_obs(),
        failure_context="element_not_found",
    )
    ctx = pi.to_prompt_context()
    assert "element_not_found" in ctx


# ------------------------------------------------------------------
# PlannerOutput
# ------------------------------------------------------------------
def test_planner_output_goto():
    po = PlannerOutput(
        reasoning="navigate to portal",
        action=Goto(url="http://localhost:8081/login"),
    )
    assert po.action.action == "goto"
    assert po.reasoning == "navigate to portal"


def test_planner_output_click():
    po = PlannerOutput(
        reasoning="click submit",
        action=Click(target=Target(label="SAVE & CONTINUE")),
    )
    assert po.action.action == "click"


def test_planner_output_finish():
    po = PlannerOutput(
        reasoning="task complete",
        action=Finish(description="done"),
    )
    assert po.action.action == "finish"


def test_planner_output_request_human():
    po = PlannerOutput(
        reasoning="captcha detected",
        action=RequestHuman(reason="CAPTCHA on page"),
    )
    assert po.action.action == "request_human"


def test_planner_output_roundtrip():
    """PlannerOutput serializes and deserializes correctly."""
    original = PlannerOutput(
        reasoning="fill invoice number",
        action=Type(target=Target(label="Invoice Number:"), text="INV-29381"),
    )
    data = original.model_dump()
    restored = PlannerOutput.model_validate(data)
    assert restored.reasoning == original.reasoning
    assert restored.action.action == "type"
    assert restored.action.text == "INV-29381"


# ------------------------------------------------------------------
# AgentState
# ------------------------------------------------------------------
def test_agent_state_initial():
    s = AgentState(task="process invoice")
    assert s.state == "CREATED"
    assert s.step == 0
    assert s.history == []
    assert s.is_terminal is False


def test_agent_state_record_action():
    s = AgentState(task="test")
    s.record_action("goto", "http://login", "success", duration_ms=100)
    assert s.step == 1
    assert len(s.history) == 1
    assert s.history[0].action == "goto"
    assert s.last_failure is None


def test_agent_state_record_failure():
    s = AgentState(task="test")
    s.record_action("click", "Login", "failure", failure_reason="element_not_found")
    assert s.last_failure == "element_not_found"


def test_agent_state_to_planner_input():
    s = AgentState(task="process invoice", state="FILLING_FORM", step=3)
    s.record_action("type", "Invoice Number:", "success")
    obs = _obs()
    pi = s.to_planner_input(obs)
    assert pi.task == "process invoice"
    assert pi.state == "FILLING_FORM"
    assert pi.step == 5  # record_action bumped step to 4, to_planner_input adds 1
    assert len(pi.history) == 1
    assert pi.observation.url == obs.url


def test_agent_state_terminal():
    s = AgentState(state="SUCCESS")
    assert s.is_terminal is True
    s2 = AgentState(state="FAILED")
    assert s2.is_terminal is True
    s3 = AgentState(state="FILLING_FORM")
    assert s3.is_terminal is False


def test_agent_state_captcha_detection():
    s = AgentState()
    obs = _obs(captcha_present=True)
    pi = s.to_planner_input(obs)
    assert pi.captcha_detected is True


# ------------------------------------------------------------------
# ActionValidator
# ------------------------------------------------------------------
def test_validator_parse_valid():
    v = ActionValidator()
    action = v.parse({"action": "goto", "url": "http://localhost:8081/login"})
    assert isinstance(action, Goto)
    assert action.url == "http://localhost:8081/login"


def test_validator_parse_invalid_action():
    v = ActionValidator()
    with pytest.raises(ActionValidationError, match="Invalid action"):
        v.parse({"action": "hacked"})


def test_validator_parse_missing_action_infers_type():
    v = ActionValidator()
    # Pydantic infers Goto from the url field even without explicit "action"
    action = v.parse({"url": "http://localhost"})
    assert isinstance(action, Goto)


def test_validator_parse_click_no_target():
    v = ActionValidator()
    with pytest.raises(ActionValidationError, match="Invalid action"):
        v.parse({"action": "click"})


def test_validator_domain_allowed():
    v = ActionValidator(allowed_domains=["localhost", "127.0.0.1"])
    action = Goto(url="http://localhost:8081/login")
    v.validate(action)  # should not raise


def test_validator_domain_denied():
    v = ActionValidator(allowed_domains=["localhost"])
    action = Goto(url="http://evil.com/steal")
    with pytest.raises(ActionValidationError, match="disallowed domain"):
        v.validate(action)


def test_validator_target_found_in_observation():
    v = ActionValidator()
    obs = _obs()
    action = Click(target=Target(label="SAVE & CONTINUE"))
    v.validate(action, observation=obs)  # should not raise


def test_validator_target_not_found_in_observation():
    v = ActionValidator()
    obs = _obs()
    action = Click(target=Target(label="Nonexistent Button"))
    with pytest.raises(ActionValidationError, match="Nonexistent Button"):
        v.validate(action, observation=obs)


def test_validator_element_id_found():
    v = ActionValidator()
    obs = _obs()
    action = Click(target=Target(element_id="e1"))
    v.validate(action, observation=obs)


def test_validator_element_id_not_found():
    v = ActionValidator()
    obs = _obs()
    action = Click(target=Target(element_id="e999"))
    with pytest.raises(ActionValidationError, match="e999.*not found"):
        v.validate(action, observation=obs)


def test_validator_upload_path_allowed():
    v = ActionValidator(allowed_upload_dirs=["/tmp", str(Path.cwd())])
    action = Upload(target=Target(label="Document:"), filepath="/tmp/test.pdf")
    v.validate(action)


def test_validator_upload_path_denied():
    v = ActionValidator(allowed_upload_dirs=["/tmp"])
    action = Upload(target=Target(label="Document:"), filepath="/etc/passwd")
    with pytest.raises(ActionValidationError, match="not in allowed"):
        v.validate(action)


def test_validator_no_observation_skips_target_check():
    v = ActionValidator()
    action = Click(target=Target(label="Anything"))
    v.validate(action, observation=None)  # should not raise


def test_validator_request_human_always_allowed():
    v = ActionValidator()
    action = RequestHuman(reason="captcha")
    v.validate(action)  # should not raise


def test_validator_finish_always_allowed():
    v = ActionValidator()
    action = Finish(description="done")
    v.validate(action)  # should not raise
