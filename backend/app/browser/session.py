"""Browser session factory: launch a Playwright browser bound to a run."""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import BrowserContext, Playwright, async_playwright

from app.browser.executor import BrowserExecutor


class BrowserSession:
    """Owns a Playwright instance + context and hands out one executor."""

    def __init__(self, playwright: Playwright, context: BrowserContext,
                 executor: BrowserExecutor):
        self.playwright = playwright
        self.context = context
        self.executor = executor

    async def close(self) -> None:
        await self.context.close()
        await self.playwright.stop()


async def launch_session(*, screenshot_dir: str | Path = "screenshots",
                         headless: bool = True,
                         allowed_domains: list[str] | None = None,
                         **context_kwargs) -> BrowserSession:
    """Launch a headless chromium session and wrap it in a BrowserExecutor."""
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=headless)
    context = await browser.new_context(**context_kwargs)
    page = await context.new_page()
    executor = BrowserExecutor(
        page, screenshot_dir=screenshot_dir, allowed_domains=allowed_domains
    )
    # Keep the browser handle on the executor for direct access if needed.
    executor.browser = browser  # type: ignore[attr-defined]
    return BrowserSession(pw, context, executor)
