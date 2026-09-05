"""Clean abstraction over Playwright.

Raw Playwright is never scattered through the agent. Everything the agent and
recovery engine need routes through :class:`BrowserExecutor`, which:

* exposes high-level operations (goto/click/type/select/upload/extract/screen
  shot/back/wait),
* produces structured :class:`PageObservation` snapshots instead of raw DOM,
* gates navigation to the configured domain allowlist (demo mode),
* persists screenshots into a per-run directory for the dashboard/replay.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from playwright.async_api import Page, TimeoutError as PWTimeoutError

from app.browser.observation import InteractiveElement, PageObservation
from app.config import settings

_SELECTOR_SAFE = re.compile(r"[^a-zA-Z0-9_-]")


class BrowserError(Exception):
    """Base error raised by the executor on an unrecoverable browser failure."""

    def __init__(self, message: str, *, expected: str | None = None,
                 actual: str | None = None, failure_reason: str = "unknown"):
        super().__init__(message)
        self.expected = expected
        self.actual = actual
        self.failure_reason = failure_reason


class ElementNotFound(BrowserError):
    def __init__(self, expected: str):
        super().__init__(
            f"Element not found: {expected}",
            expected=expected,
            actual="no matching element",
            failure_reason="element_not_found",
        )


class NavigationDenied(BrowserError):
    def __init__(self, url: str):
        super().__init__(
            f"Navigation to disallowed domain denied: {url}",
            expected=url,
            failure_reason="navigation_denied",
        )


# Detects the unexpected "system message" modal overlay.
_MODAL_TEXT_MARKERS = ("unexpected system message", "system error")


class BrowserExecutor:
    """A per-run browser session exposing high-level, validated operations."""

    def __init__(self, page: Page, *, screenshot_dir: str | Path = "screenshots",
                 allowed_domains: Optional[list[str]] = None):
        self._page = page
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._shot_seq = 0
        self.allowed_domains = [d.strip().lower() for d in (allowed_domains or [])]
        if not self.allowed_domains:
            self.allowed_domains = [
                d.strip().lower() for d in settings.allowed_domains.split(",") if d.strip()
            ]

    @property
    def page(self) -> Page:
        return self._page

    # ------------------------------------------------------------------ page
    async def _guard_url(self, url: str) -> str:
        import urllib.parse

        host = (urllib.parse.urlparse(url).hostname or "").lower()
        if self.allowed_domains and host and not any(
            host == d or host.endswith("." + d) for d in self.allowed_domains
        ):
            raise NavigationDenied(url)
        return url

    async def goto(self, url: str, *, timeout_ms: Optional[int] = None) -> PageObservation:
        url = await self._guard_url(url)
        try:
            await self._page.goto(
                url, wait_until="domcontentloaded",
                timeout=timeout_ms or settings.http_timeout_ms,
            )
        except PWTimeoutError as exc:
            raise BrowserError("goto timed out", expected=url,
                               failure_reason="navigation_timeout") from exc
        return await self.observe()

    # ------------------------------------------------------------- targeting
    @staticmethod
    def _target_attr(target, attr: str, default=None):
        if isinstance(target, dict):
            return target.get(attr, default)
        return getattr(target, attr, default)

    async def resolve_locator(self, target):
        """Resolve a semantic target to a Playwright locator (or None).

        Accepts either a ``Target`` model or a plain ``dict`` with keys
        ``selector``, ``element_id``, ``role``, ``label``.
        """
        if target is None:
            return None

        selector = self._target_attr(target, "selector")
        element_id = self._target_attr(target, "element_id")
        role = self._target_attr(target, "role")
        label = self._target_attr(target, "label")

        if selector:
            return self._page.locator(selector).first
        if element_id:
            lc = self._page.locator(f"[data-obs-id='{element_id}']").first
            if await lc.count():
                return lc
        if label:
            lc = await self._locator_by_label(role, label)
            if lc is not None:
                return lc
        if role:
            lc = await self._locator_by_role(role)
            if lc is not None:
                return lc
        return None

    async def _locator_by_label(self, role: Optional[str], label: str) -> Optional[object]:
        page = self._page
        label_q = label.replace("'", "\\'")
        candidates: list[str] = []

        if not role or role in ("button", "submit"):
            candidates += [
                f"button:has-text('{label_q}')",
                f"input[type='submit'][value='{label_q}']",
                f"input[type='button'][value='{label_q}']",
                f"a:has-text('{label_q}')",
            ]

        if not role or role in ("textbox", "select", "file", "checkbox", "radio"):
            # Use Playwright's built-in get_by_label which handles for= associations.
            try:
                lc = page.get_by_label(label, exact=False).first
                if await lc.count():
                    return lc
            except Exception:
                pass
            # Fallback CSS selectors for direct label→input nesting.
            candidates.append(f"input[placeholder='{label_q}']")
            candidates.append(f"textarea[placeholder='{label_q}']")
            # label[for="X"] paired with input#X via JS.
            candidates.append(f"label:has-text('{label_q}') input")
            candidates.append(f"label:has-text('{label_q}') textarea")
            candidates.append(f"label:has-text('{label_q}') select")

        for sel in candidates:
            try:
                lc = page.locator(sel).first
                if await lc.count():
                    return lc
            except Exception:
                continue
        return None

    async def _locator_by_role(self, role: str) -> Optional[object]:
        page = self._page
        if role == "textbox":
            sel = "input:not([type='submit']):not([type='button']),textarea"
        elif role == "button":
            sel = "button, input[type='submit'], input[type='button']"
        elif role == "link":
            sel = "a"
        elif role == "select":
            sel = "select"
        elif role == "file":
            sel = "input[type='file']"
        else:
            sel = None
        if not sel:
            return None
        lc = page.locator(sel).first
        return lc if await lc.count() else None

    async def require_locator(self, target, expected_desc: str):
        if target is None:
            raise ElementNotFound(expected_desc)
        lc = await self.resolve_locator(target)
        if lc is None or await lc.count() == 0:
            raise ElementNotFound(expected_desc)
        return lc

    # ------------------------------------------------------------- operations
    async def click(self, target, *, timeout_ms: Optional[int] = None) -> None:
        lc = await self.require_locator(target, self._target_attr(target, "label", str(target)))
        try:
            await lc.click(timeout=timeout_ms or settings.http_timeout_ms)
        except PWTimeoutError as exc:
            raise BrowserError("click timed out", expected="clickable element",
                               failure_reason="action_timeout") from exc

    async def type_text(self, target, text: str) -> None:
        lc = await self.require_locator(target, self._target_attr(target, "label", str(target)))
        await lc.fill(text)

    async def select(self, target, value: str) -> None:
        lc = await self.require_locator(target, self._target_attr(target, "label", str(target)))
        await lc.select_option(value)

    async def upload(self, target, filepath: str) -> None:
        lc = await self.require_locator(target, self._target_attr(target, "label", str(target)))
        await lc.set_input_files(filepath)

    async def back(self) -> PageObservation:
        await self._page.go_back()
        return await self.observe()

    async def wait(self, ms: int = 500) -> None:
        await self._page.wait_for_timeout(ms)

    async def extract(self, target=None) -> str:
        if target is not None:
            lc = await self.require_locator(target, self._target_attr(target, "label", str(target)))
            return (await lc.inner_text() or "").strip()
        if await self._page.locator("body").count():
            return (await self._page.inner_text("body") or "").strip()
        return ""

    # ------------------------------------------------------------- observation
    async def screenshot(self, name: Optional[str] = None) -> str:
        self._shot_seq += 1
        fname = name or f"shot_{self._shot_seq:04d}.png"
        path = self.screenshot_dir / fname
        await self._page.screenshot(path=str(path))
        return str(path)

    async def observe(self, *, screenshot: bool = True) -> PageObservation:
        url = self._page.url or ""
        title = await self._page.title()
        visible_text = ""
        if await self._page.locator("body").count():
            visible_text = (await self._page.inner_text("body") or "").strip()

        raw_els = await self._page.evaluate(_EXTRACT_ELEMENTS_JS)
        elements = [InteractiveElement(**e) for e in (raw_els or [])]

        page_lower = visible_text.lower()
        observed = PageObservation(
            url=url, title=title, visible_text=visible_text,
            interactive_elements=elements,
        )
        observed.modal_present = any(m in page_lower for m in _MODAL_TEXT_MARKERS)
        observed.captcha_present = (
            "captcha" in url.lower()
            or bool(await self._page.locator("input[name='captcha_answer']").count())
        )
        observed.session_expired = (
            "session expired" in page_lower or url.rstrip("/").endswith("/login")
        )

        if screenshot:
            try:
                observed.screenshot_path = await self.screenshot()
            except Exception:
                observed.screenshot_path = None
        return observed


# JS that returns a compact interactive-element snapshot with semantic labels.
_EXTRACT_ELEMENTS_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  let counter = 0;
  const labelFor = (el) => {
    if (el.labels && el.labels.length) return el.labels[0].innerText.trim();
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (el.getAttribute('placeholder')) return el.getAttribute('placeholder');
    const id = el.getAttribute('id');
    if (id) {
      const lab = document.querySelector(`label[for="${id}"]`);
      if (lab) return lab.innerText.trim();
    }
    return el.innerText.trim() || el.getAttribute('value') || '';
  };
  const mk = (el, role) => {
    if (seen.has(el)) return;
    seen.add(el);
    const label = labelFor(el) || role;
    const id = `e${++counter}`;
    el.setAttribute('data-obs-id', id);
    out.push({
      id,
      role,
      label,
      value: el.value ?? null,
      placeholder: el.getAttribute('placeholder') ?? null,
    });
  };
  document.querySelectorAll('input,textarea,select,button,a')
    .forEach(el => {
      const t = (el.tagName || '').toLowerCase();
      if (t === 'input') {
        const ty = (el.getAttribute('type')||'text').toLowerCase();
        if (ty === 'submit' || ty === 'button') mk(el, 'button');
        else if (ty === 'file') mk(el, 'file');
        else if (ty === 'checkbox') mk(el, 'checkbox');
        else if (ty === 'radio') mk(el, 'radio');
        else mk(el, 'textbox');
      } else if (t === 'textarea') mk(el, 'textbox');
      else if (t === 'select') mk(el, 'select');
      else if (t === 'button') mk(el, 'button');
      else if (t === 'a') mk(el, 'link');
    });
  return out;
}
"""
