"""Tests for M5: agent planner and agent loop."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.loop import AgentLoop
from app.agents.planner import MockPlanner, OpenAIPlanner, create_planner
from app.agents.schemas import AgentState, PlannerInput, PlannerOutput
from app.browser.actions import (
    Click,
    Finish,
    Goto,
    RequestHuman,
    Target,
    Type,
)
from app.browser.executor import BrowserError, ElementNotFound
from app.browser.observation import InteractiveElement, PageObservation
from app.browser.validator import ActionValidationError, ActionValidator


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------
def _obs(**kwargs) -> PageObservation:
    defaults = {
        "url": "http://localhost:8081/invoices",
        "title": "Invoice Processing",
        "visible_text": "Invoice Number: INV-29381",
        "interactive_elements": [
            InteractiveElement(id="e1", role="textbox", label="Invoice Number:"),
            InteractiveElement(id="e2", role="textbox", label="Vendor:"),
            InteractiveElement(id="e3", role="button", label="SAVE & CONTINUE"),
        ],
    }
    defaults.update(kwargs)
    return PageObservation(**defaults)


def _login_obs() -> PageObservation:
    return _obs(
        url="http://localhost:8081/login",
        title="Login - ACME ERP",
        visible_text="Username: Password: Login",
        interactive_elements=[
            InteractiveElement(id="e1", role="textbox", label="Username:"),
            InteractiveElement(id="e2", role="textbox", label="Password:"),
            InteractiveElement(id="e3", role="button", label="Login"),
        ],
    )


def _captcha_obs() -> PageObservation:
    return _obs(
        url="http://localhost:8081/captcha",
        title="CAPTCHA Verification",
        captcha_present=True,
    )


def _mock_executor(obs: PageObservation | None = None) -> MagicMock:
    """Create a mock BrowserExecutor that returns observations."""
    executor = AsyncMock()
    executor.observe = AsyncMock(return_value=obs or _obs())
    executor.goto = AsyncMock(return_value=obs or _obs())
    executor.click = AsyncMock(return_value=None)
    executor.type_text = AsyncMock(return_value=None)
    executor.select = AsyncMock(return_value=None)
    executor.upload = AsyncMock(return_value=None)
    executor.back = AsyncMock(return_value=obs or _obs())
    executor.wait = AsyncMock(return_value=None)
    executor.extract = AsyncMock(return_value="extracted text")
    return executor


# ------------------------------------------------------------------
# MockPlanner tests
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_planner_captcha():
    planner = MockPlanner()
    pi = PlannerInput(
        task="test",
        state="NAVIGATING",
        step=1,
        observation=_captcha_obs(),
        captcha_detected=True,
    )
    out = await planner.decide(pi)
    assert out.action.action == "request_human"
    assert "CAPTCHA" in out.reasoning


@pytest.mark.asyncio
async def test_mock_planner_login_page():
    planner = MockPlanner()
    pi = PlannerInput(
        task="test",
        state="NAVIGATING",
        step=1,
        observation=_login_obs(),
    )
    out = await planner.decide(pi)
    assert out.action.action == "goto"
    assert "invoices" in out.action.url


@pytest.mark.asyncio
async def test_mock_planner_empty_url():
    planner = MockPlanner()
    obs = _obs(url="")
    pi = PlannerInput(task="test", state="NAVIGATING", step=1, observation=obs)
    out = await planner.decide(pi)
    assert out.action.action == "goto"


@pytest.mark.asyncio
async def test_mock_planner_finish_on_high_step():
    planner = MockPlanner()
    pi = PlannerInput(
        task="test",
        state="NAVIGATING",
        step=20,
        observation=_obs(),
    )
    out = await planner.decide(pi)
    assert out.action.action == "finish"


@pytest.mark.asyncio
async def test_mock_planner_success_state():
    planner = MockPlanner()
    pi = PlannerInput(
        task="test",
        state="SUCCESS",
        step=5,
        observation=_obs(),
    )
    out = await planner.decide(pi)
    assert out.action.action == "finish"


# ------------------------------------------------------------------
# OpenAIPlanner tests (mocked API)
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_openai_planner_parses_goto():
    planner = OpenAIPlanner(api_key="test-key")
    pi = PlannerInput(
        task="go to login",
        state="PLANNING",
        step=1,
        observation=_obs(url=""),
    )
    with patch("app.agents.planner.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"reasoning":"navigate to login","action":"goto",'
            '"url":"http://localhost:8081/login"}'
        )
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        out = await planner.decide(pi)
    assert out.action.action == "goto"
    assert out.action.url == "http://localhost:8081/login"
    assert "navigate" in out.reasoning.lower()


@pytest.mark.asyncio
async def test_openai_planner_parses_click():
    planner = OpenAIPlanner(api_key="test-key")
    pi = PlannerInput(
        task="click submit",
        state="FILLING_FORM",
        step=3,
        observation=_obs(),
    )
    with patch("app.agents.planner.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"reasoning":"click submit","action":"click",'
            '"target":{"label":"SAVE & CONTINUE"}}'
        )
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        out = await planner.decide(pi)
    assert out.action.action == "click"
    assert out.action.target.label == "SAVE & CONTINUE"


@pytest.mark.asyncio
async def test_openai_planner_parses_finish():
    planner = OpenAIPlanner(api_key="test-key")
    pi = PlannerInput(
        task="done",
        state="SUBMITTING",
        step=10,
        observation=_obs(),
    )
    with patch("app.agents.planner.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"reasoning":"all done","action":"finish","description":"completed"}'
        )
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        out = await planner.decide(pi)
    assert out.action.action == "finish"
    assert out.action.description == "completed"


@pytest.mark.asyncio
async def test_openai_planner_api_error_falls_back():
    planner = OpenAIPlanner(api_key="test-key")
    pi = PlannerInput(
        task="test",
        state="PLANNING",
        step=1,
        observation=_obs(),
    )
    with patch("app.agents.planner.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API error")
        )
        out = await planner.decide(pi)
    assert out.action.action == "finish"
    assert "error" in out.reasoning.lower()


@pytest.mark.asyncio
async def test_openai_planner_strips_markdown_fences():
    planner = OpenAIPlanner(api_key="test-key")
    pi = PlannerInput(
        task="test",
        state="PLANNING",
        step=1,
        observation=_obs(),
    )
    with patch("app.agents.planner.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '```json\n{"reasoning":"done","action":"finish","description":"ok"}\n```'
        )
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        out = await planner.decide(pi)
    assert out.action.action == "finish"


# ------------------------------------------------------------------
# create_planner factory
# ------------------------------------------------------------------
def test_create_planner_with_key():
    with patch("app.agents.planner.settings") as mock_settings:
        mock_settings.openai_api_key = "sk-test"
        mock_settings.openai_model = "gpt-4o"
        mock_settings.openai_base_url = "https://api.openai.com/v1"
        planner = create_planner()
    assert isinstance(planner, OpenAIPlanner)


def test_create_planner_without_key():
    with patch("app.agents.planner.settings") as mock_settings:
        mock_settings.openai_api_key = ""
        planner = create_planner()
    assert isinstance(planner, MockPlanner)


# ------------------------------------------------------------------
# AgentLoop tests
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_agent_loop_finishes_on_finish_action():
    """Planner returns finish immediately → run completes in SUCCESS."""
    executor = _mock_executor()
    planner = MockPlanner()

    loop = AgentLoop(executor=executor, planner=planner, task="test task")
    # Override planner to return finish immediately.
    class FinishPlanner:
        async def decide(self, pi):
            return PlannerOutput(reasoning="done", action=Finish(description="ok"))
    loop.planner = FinishPlanner()

    result = await loop.run()
    assert result.state == "SUCCESS"
    assert result.duration_ms >= 0
    assert len(result.events) > 0


@pytest.mark.asyncio
async def test_agent_loop_request_human():
    """Planner returns request_human → run enters HUMAN_INTERVENTION."""
    executor = _mock_executor()
    planner = MockPlanner()

    class HumanPlanner:
        async def decide(self, pi):
            return PlannerOutput(reasoning="captcha", action=RequestHuman(reason="CAPTCHA"))
    loop = AgentLoop(executor=executor, planner=planner, task="test")
    loop.planner = HumanPlanner()

    result = await loop.run()
    assert result.state == "HUMAN_INTERVENTION"
    assert any(e.kind == "planner_decision" for e in result.events)


@pytest.mark.asyncio
async def test_agent_loop_validates_action_rejection():
    """Action fails validation → planner gets failure context next turn."""
    executor = _mock_executor()
    planner = MockPlanner()

    call_count = 0

    class RejectOncePlanner:
        async def decide(self, pi):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: try to click a nonexistent element.
                return PlannerOutput(
                    reasoning="click bad",
                    action=Click(target=Target(label="Nonexistent")),
                )
            # Second call: finish.
            return PlannerOutput(reasoning="done", action=Finish(description="ok"))

    loop = AgentLoop(executor=executor, planner=RejectOncePlanner(), task="test")
    result = await loop.run()
    assert result.state == "SUCCESS"
    assert any(e.result == "rejected" for e in result.events)


@pytest.mark.asyncio
async def test_agent_loop_retries_on_failure():
    """Executor raises ElementNotFound → loop retries."""
    executor = _mock_executor()
    call_count = 0

    async def _click_fail_then_succeed(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise ElementNotFound("button")

    executor.click = _click_fail_then_succeed
    executor.observe = AsyncMock(return_value=_obs())

    class ClickThenFinish:
        def __init__(self):
            self._calls = 0
        async def decide(self, pi):
            self._calls += 1
            if self._calls <= 2:
                return PlannerOutput(
                    reasoning="try click",
                    action=Click(target=Target(label="SAVE & CONTINUE")),
                )
            return PlannerOutput(reasoning="done", action=Finish(description="ok"))

    loop = AgentLoop(executor=executor, planner=ClickThenFinish(), task="test")
    result = await loop.run()
    assert result.state == "SUCCESS"
    assert call_count == 2


@pytest.mark.asyncio
async def test_agent_loop_max_steps_exceeded():
    """Loop terminates after max_steps."""
    executor = _mock_executor()

    class AlwaysClick:
        async def decide(self, pi):
            return PlannerOutput(
                reasoning="keep going",
                action=Click(target=Target(label="SAVE & CONTINUE")),
            )

    loop = AgentLoop(
        executor=executor,
        planner=AlwaysClick(),
        task="infinite",
        max_steps=3,
    )
    result = await loop.run()
    assert result.state == "FAILED"
    assert any("max steps" in (e.detail or "") for e in result.events)


@pytest.mark.asyncio
async def test_agent_loop_goto_transitions_to_navigating():
    """Goto action transitions state to NAVIGATING."""
    executor = _mock_executor()

    class GotoThenFinish:
        def __init__(self):
            self._calls = 0
        async def decide(self, pi):
            self._calls += 1
            if self._calls == 1:
                return PlannerOutput(
                    reasoning="navigate",
                    action=Goto(url="http://localhost:8081/login"),
                )
            return PlannerOutput(reasoning="done", action=Finish(description="ok"))

    loop = AgentLoop(executor=executor, planner=GotoThenFinish(), task="test")
    result = await loop.run()
    assert result.state == "SUCCESS"
    state_changes = [e for e in result.events if e.kind == "state_change"]
    assert any("NAVIGATING" in e.detail for e in state_changes)


@pytest.mark.asyncio
async def test_agent_loop_type_transitions_to_filling_form():
    """Type action transitions state to FILLING_FORM."""
    executor = _mock_executor()

    class TypeThenFinish:
        def __init__(self):
            self._calls = 0
        async def decide(self, pi):
            self._calls += 1
            if self._calls == 1:
                return PlannerOutput(
                    reasoning="fill field",
                    action=Type(target=Target(label="Invoice Number:"), text="INV-123"),
                )
            return PlannerOutput(reasoning="done", action=Finish(description="ok"))

    loop = AgentLoop(executor=executor, planner=TypeThenFinish(), task="test")
    result = await loop.run()
    assert result.state == "SUCCESS"
    state_changes = [e for e in result.events if e.kind == "state_change"]
    assert any("FILLING_FORM" in e.detail for e in state_changes)


@pytest.mark.asyncio
async def test_agent_loop_records_all_events():
    """Run records planner_decision, action, state_change, observation events."""
    executor = _mock_executor()

    class SimplePlanner:
        async def decide(self, pi):
            return PlannerOutput(reasoning="finish", action=Finish(description="done"))

    loop = AgentLoop(executor=executor, planner=SimplePlanner(), task="test")
    result = await loop.run()

    kinds = [e.kind for e in result.events]
    assert "observation" in kinds
    assert "planner_decision" in kinds
    assert "action" in kinds
    assert "state_change" in kinds
