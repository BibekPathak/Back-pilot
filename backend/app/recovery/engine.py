"""Recovery engine: structured recovery strategies for browser failures.

When the agent encounters a failure (element not found, session expired,
modal overlay, CAPTCHA), the recovery engine decides what to do next:

1. **refresh** — Reload the current page and retry.
2. **re_authenticate** — Navigate to login, re-enter credentials, return.
3. **dismiss_modal** — Close the modal overlay and retry.
4. **navigate_back** — Go back in history and retry.
5. **escalate** — Give up and request human intervention.

Each strategy returns a :class:`RecoveryResult` indicating whether recovery
succeeded and what action the agent should take next.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.browser.executor import BrowserExecutor
from app.browser.observation import PageObservation

logger = logging.getLogger(__name__)


class RecoveryStrategy(str, Enum):
    REFRESH = "refresh"
    RE_AUTHENTICATE = "re_authenticate"
    DISMISS_MODAL = "dismiss_modal"
    NAVIGATE_BACK = "navigate_back"
    ESCALATE = "escalate"


@dataclass
class RecoveryResult:
    """Outcome of a recovery attempt."""

    strategy: RecoveryStrategy
    success: bool
    message: str = ""
    observation: Optional[PageObservation] = None


@dataclass
class RecoveryEngine:
    """Drives structured recovery based on failure type.

    Usage::

        engine = RecoveryEngine(executor)
        result = await engine.recover(observation, failure_reason="element_not_found")
    """

    executor: BrowserExecutor
    max_refresh_attempts: int = 2
    max_reauth_attempts: int = 1
    max_modal_dismiss_attempts: int = 2
    max_back_attempts: int = 1
    _refresh_count: int = field(default=0, init=False)
    _reauth_count: int = field(default=0, init=False)
    _modal_count: int = field(default=0, init=False)
    _back_count: int = field(default=0, init=False)

    async def recover(
        self,
        observation: PageObservation,
        failure_reason: str = "",
    ) -> RecoveryResult:
        """Select and execute the best recovery strategy for the failure."""

        # CAPTCHA → always escalate.
        if observation.captcha_present or failure_reason == "captcha_detected":
            return await self._escalate("CAPTCHA detected — human required")

        # Session expired → re-authenticate.
        if observation.session_expired or failure_reason == "session_expired":
            return await self._re_authenticate()

        # Modal overlay → dismiss it.
        if observation.modal_present or failure_reason == "modal_detected":
            return await self._dismiss_modal()

        # Element not found → refresh and retry.
        if failure_reason == "element_not_found":
            return await self._refresh()

        # Navigation timeout → refresh.
        if failure_reason == "navigation_timeout":
            return await self._refresh()

        # Action timeout → navigate back.
        if failure_reason == "action_timeout":
            return await self._navigate_back()

        # Unknown → escalate.
        return await self._escalate(f"Unknown failure: {failure_reason}")

    async def _refresh(self) -> RecoveryResult:
        if self._refresh_count >= self.max_refresh_attempts:
            return await self._escalate("Refresh attempts exhausted")
        self._refresh_count += 1
        logger.info("Recovery: refresh page (attempt %d/%d)", self._refresh_count, self.max_refresh_attempts)
        try:
            obs = await self.executor.page.reload(wait_until="domcontentloaded")
            obs = await self.executor.observe(screenshot=False)
            return RecoveryResult(
                strategy=RecoveryStrategy.REFRESH,
                success=True,
                message=f"Page refreshed ({self._refresh_count}/{self.max_refresh_attempts})",
                observation=obs,
            )
        except Exception as exc:
            return RecoveryResult(
                strategy=RecoveryStrategy.REFRESH,
                success=False,
                message=f"Refresh failed: {exc}",
            )

    async def _re_authenticate(self) -> RecoveryResult:
        if self._reauth_count >= self.max_reauth_attempts:
            return await self._escalate("Re-auth attempts exhausted")
        self._reauth_count += 1
        logger.info("Recovery: re-authenticate (attempt %d/%d)", self._reauth_count, self.max_reauth_attempts)
        try:
            obs = await self.executor.goto("http://localhost:8081/login")
            return RecoveryResult(
                strategy=RecoveryStrategy.RE_AUTHENTICATE,
                success=True,
                message="Navigated to login page",
                observation=obs,
            )
        except Exception as exc:
            return RecoveryResult(
                strategy=RecoveryStrategy.RE_AUTHENTICATE,
                success=False,
                message=f"Re-auth failed: {exc}",
            )

    async def _dismiss_modal(self) -> RecoveryResult:
        if self._modal_count >= self.max_modal_dismiss_attempts:
            return await self._escalate("Modal dismiss attempts exhausted")
        self._modal_count += 1
        logger.info("Recovery: dismiss modal (attempt %d/%d)", self._modal_count, self.max_modal_dismiss_attempts)
        try:
            page = self.executor.page
            # Try clicking common close buttons.
            for selector in [
                "button.close",
                "[aria-label='Close']",
                "[data-dismiss='modal']",
                "button:has-text('OK')",
                "button:has-text('Dismiss')",
                "button:has-text('Continue')",
                "button:has-text('Close')",
            ]:
                loc = page.locator(selector).first
                if await loc.count():
                    await loc.click()
                    obs = await self.executor.observe(screenshot=False)
                    return RecoveryResult(
                        strategy=RecoveryStrategy.DISMISS_MODAL,
                        success=True,
                        message=f"Modal dismissed via {selector}",
                        observation=obs,
                    )
            # No close button found → try pressing Escape.
            await page.keyboard.press("Escape")
            obs = await self.executor.observe(screenshot=False)
            return RecoveryResult(
                strategy=RecoveryStrategy.DISMISS_MODAL,
                success=True,
                message="Modal dismissed via Escape key",
                observation=obs,
            )
        except Exception as exc:
            return RecoveryResult(
                strategy=RecoveryStrategy.DISMISS_MODAL,
                success=False,
                message=f"Modal dismiss failed: {exc}",
            )

    async def _navigate_back(self) -> RecoveryResult:
        if self._back_count >= self.max_back_attempts:
            return await self._escalate("Navigate-back attempts exhausted")
        self._back_count += 1
        logger.info("Recovery: navigate back (attempt %d/%d)", self._back_count, self.max_back_attempts)
        try:
            obs = await self.executor.back()
            return RecoveryResult(
                strategy=RecoveryStrategy.NAVIGATE_BACK,
                success=True,
                message="Navigated back",
                observation=obs,
            )
        except Exception as exc:
            return RecoveryResult(
                strategy=RecoveryStrategy.NAVIGATE_BACK,
                success=False,
                message=f"Navigate back failed: {exc}",
            )

    async def _escalate(self, reason: str) -> RecoveryResult:
        logger.warning("Recovery: escalate — %s", reason)
        return RecoveryResult(
            strategy=RecoveryStrategy.ESCALATE,
            success=False,
            message=reason,
        )

    def reset(self) -> None:
        """Reset all attempt counters."""
        self._refresh_count = 0
        self._reauth_count = 0
        self._modal_count = 0
        self._back_count = 0
