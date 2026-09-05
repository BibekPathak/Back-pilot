"""Tests for M6: recovery engine."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.browser.observation import InteractiveElement, PageObservation
from app.recovery.engine import RecoveryEngine, RecoveryResult, RecoveryStrategy


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------
def _obs(**kwargs) -> PageObservation:
    defaults = {
        "url": "http://localhost:8081/invoices",
        "title": "Invoices",
        "interactive_elements": [
            InteractiveElement(id="e1", role="button", label="SAVE"),
        ],
    }
    defaults.update(kwargs)
    return PageObservation(**defaults)


def _mock_executor(obs: PageObservation | None = None) -> MagicMock:
    executor = AsyncMock()
    default_obs = obs or _obs()
    executor.observe = AsyncMock(return_value=default_obs)
    executor.goto = AsyncMock(return_value=default_obs)
    executor.back = AsyncMock(return_value=default_obs)
    executor.page = MagicMock()
    executor.page.reload = AsyncMock(return_value=default_obs)
    executor.page.keyboard = AsyncMock()
    executor.page.keyboard.press = AsyncMock()
    return executor


# ------------------------------------------------------------------
# Strategy selection
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_captcha_escalates():
    obs = _obs(captcha_present=True)
    executor = _mock_executor(obs)
    engine = RecoveryEngine(executor)
    result = await engine.recover(obs, failure_reason="captcha_detected")
    assert result.strategy == RecoveryStrategy.ESCALATE
    assert result.success is False
    assert "CAPTCHA" in result.message


@pytest.mark.asyncio
async def test_session_expired_triggers_reauth():
    obs = _obs(session_expired=True)
    executor = _mock_executor(obs)
    engine = RecoveryEngine(executor)
    result = await engine.recover(obs, failure_reason="session_expired")
    assert result.strategy == RecoveryStrategy.RE_AUTHENTICATE
    assert result.success is True
    assert "login" in result.message.lower()


@pytest.mark.asyncio
async def test_modal_dismiss():
    obs = _obs(modal_present=True)
    executor = _mock_executor(obs)
    # Mock the page to find a close button.
    executor.page.locator = MagicMock()
    close_btn = AsyncMock()
    close_btn.count = AsyncMock(return_value=1)
    close_btn.click = AsyncMock()
    executor.page.locator.return_value.first = close_btn
    engine = RecoveryEngine(executor)
    result = await engine.recover(obs, failure_reason="modal_detected")
    assert result.strategy == RecoveryStrategy.DISMISS_MODAL
    assert result.success is True


@pytest.mark.asyncio
async def test_element_not_found_refreshes():
    obs = _obs()
    executor = _mock_executor(obs)
    engine = RecoveryEngine(executor)
    result = await engine.recover(obs, failure_reason="element_not_found")
    assert result.strategy == RecoveryStrategy.REFRESH
    assert result.success is True


@pytest.mark.asyncio
async def test_navigation_timeout_refreshes():
    obs = _obs()
    executor = _mock_executor(obs)
    engine = RecoveryEngine(executor)
    result = await engine.recover(obs, failure_reason="navigation_timeout")
    assert result.strategy == RecoveryStrategy.REFRESH
    assert result.success is True


@pytest.mark.asyncio
async def test_action_timeout_navigates_back():
    obs = _obs()
    executor = _mock_executor(obs)
    engine = RecoveryEngine(executor)
    result = await engine.recover(obs, failure_reason="action_timeout")
    assert result.strategy == RecoveryStrategy.NAVIGATE_BACK
    assert result.success is True


@pytest.mark.asyncio
async def test_unknown_failure_escalates():
    obs = _obs()
    executor = _mock_executor(obs)
    engine = RecoveryEngine(executor)
    result = await engine.recover(obs, failure_reason="something_weird")
    assert result.strategy == RecoveryStrategy.ESCALATE
    assert result.success is False


# ------------------------------------------------------------------
# Attempt limits
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_refresh_exhausted_escalates():
    obs = _obs()
    executor = _mock_executor(obs)
    engine = RecoveryEngine(executor, max_refresh_attempts=1)
    # First attempt succeeds.
    r1 = await engine.recover(obs, failure_reason="element_not_found")
    assert r1.success is True
    # Second attempt escalates.
    r2 = await engine.recover(obs, failure_reason="element_not_found")
    assert r2.strategy == RecoveryStrategy.ESCALATE
    assert "exhausted" in r2.message


@pytest.mark.asyncio
async def test_reauth_exhausted_escalates():
    obs = _obs()
    executor = _mock_executor(obs)
    engine = RecoveryEngine(executor, max_reauth_attempts=1)
    r1 = await engine.recover(obs, failure_reason="session_expired")
    assert r1.success is True
    r2 = await engine.recover(obs, failure_reason="session_expired")
    assert r2.strategy == RecoveryStrategy.ESCALATE


@pytest.mark.asyncio
async def test_modal_dismiss_exhausted_escalates():
    obs = _obs(modal_present=True)
    executor = _mock_executor(obs)
    # No close button found → Escape key always works, so we mock a failure.
    executor.page.locator = MagicMock()
    close_btn = AsyncMock()
    close_btn.count = AsyncMock(return_value=0)
    executor.page.locator.return_value.first = close_btn
    executor.page.keyboard.press = AsyncMock(side_effect=Exception("no keyboard"))
    engine = RecoveryEngine(executor, max_modal_dismiss_attempts=1)
    r1 = await engine.recover(obs, failure_reason="modal_detected")
    assert r1.success is False  # Escape failed
    r2 = await engine.recover(obs, failure_reason="modal_detected")
    assert r2.strategy == RecoveryStrategy.ESCALATE


@pytest.mark.asyncio
async def test_back_exhausted_escalates():
    obs = _obs()
    executor = _mock_executor(obs)
    engine = RecoveryEngine(executor, max_back_attempts=1)
    r1 = await engine.recover(obs, failure_reason="action_timeout")
    assert r1.success is True
    r2 = await engine.recover(obs, failure_reason="action_timeout")
    assert r2.strategy == RecoveryStrategy.ESCALATE


# ------------------------------------------------------------------
# Reset
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reset_counters():
    obs = _obs()
    executor = _mock_executor(obs)
    engine = RecoveryEngine(executor, max_refresh_attempts=1)
    await engine.recover(obs, failure_reason="element_not_found")
    engine.reset()
    # After reset, can recover again.
    r = await engine.recover(obs, failure_reason="element_not_found")
    assert r.success is True


# ------------------------------------------------------------------
# RecoveryResult
# ------------------------------------------------------------------
def test_recovery_result_fields():
    r = RecoveryResult(
        strategy=RecoveryStrategy.REFRESH,
        success=True,
        message="ok",
    )
    assert r.strategy == RecoveryStrategy.REFRESH
    assert r.success is True
    assert r.observation is None
