"""Playwright browser tests for the BrowserExecutor against the legacy portal.

These exercise the executor's core operations end-to-end:
  - goto + observe (structured page snapshot)
  - login flow
  - form filling via semantic labels
  - file upload
  - submission + success page
  - semantic fallback (SELECTOR_CHANGE mode)
  - modal/CAPTCHA detection in observations
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import pytest

PORTAL_DIR = Path(__file__).resolve().parents[2] / "legacy-portal"
BACKEND_DIR = Path(__file__).resolve().parents[1]
PORTAL_PORT = 8082  # use a high free port for tests
PORTAL_URL = f"http://127.0.0.1:{PORTAL_PORT}"


@pytest.fixture(scope="module")
def portal():
    """Start the legacy portal on a random port for the duration of the test module."""
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "portal:app",
            "--host", "127.0.0.1", "--port", str(PORTAL_PORT),
        ],
        cwd=str(PORTAL_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for it to be ready.
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{PORTAL_URL}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.3)
    else:
        proc.kill()
        pytest.fail("Portal failed to start")

    yield PORTAL_URL
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture()
async def executor(tmp_path):
    """Launch a browser session pointing at the portal."""
    sys.path.insert(0, str(BACKEND_DIR))
    from app.browser.session import launch_session
    session = await launch_session(
        screenshot_dir=str(tmp_path / "shots"),
        allowed_domains=["127.0.0.1", "localhost"],
    )
    yield session.executor
    await session.close()


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_goto_login(portal, executor):
    obs = await executor.goto(f"{portal}/login")
    assert "/login" in obs.url
    assert "System Login" in obs.visible_text or "Login" in obs.title
    labels = [e.label for e in obs.interactive_elements]
    assert "Username:" in labels or "username" in " ".join(labels)


@pytest.mark.asyncio
async def test_login(portal, executor):
    await executor.goto(f"{portal}/login")
    await executor.type_text({"role": "textbox", "label": "Username:"}, "admin")
    await executor.type_text({"role": "textbox", "label": "Password:"}, "admin")
    await executor.click({"role": "button", "label": "LOGIN"})
    await executor.wait(300)
    obs = await executor.observe()
    assert "/login" not in obs.url or "admin" in obs.visible_text


@pytest.mark.asyncio
async def test_form_filling(portal, executor):
    await executor.goto(f"{portal}/login")
    await executor.type_text({"role": "textbox", "label": "Username:"}, "admin")
    await executor.type_text({"role": "textbox", "label": "Password:"}, "admin")
    await executor.click({"role": "button", "label": "LOGIN"})
    await executor.wait(300)

    obs = await executor.goto(f"{portal}/invoices")
    assert "/invoices" in obs.url

    await executor.type_text({"label": "Invoice Number:"}, "INV-TEST")
    await executor.type_text({"label": "Vendor:"}, "Test Vendor")
    await executor.type_text({"label": "Amount:"}, "100.50")
    await executor.type_text({"label": "Invoice Date:"}, "2026-01-15")

    # Verify values stuck.
    obs2 = await executor.observe()
    inv_el = next(e for e in obs2.interactive_elements if e.label == "Invoice Number:")
    assert inv_el.value == "INV-TEST"
    vendor_el = next(e for e in obs2.interactive_elements if e.label == "Vendor:")
    assert vendor_el.value == "Test Vendor"


@pytest.mark.asyncio
async def test_upload_and_submit(portal, executor, tmp_path):
    await executor.goto(f"{portal}/login")
    await executor.type_text({"role": "textbox", "label": "Username:"}, "admin")
    await executor.type_text({"role": "textbox", "label": "Password:"}, "admin")
    await executor.click({"role": "button", "label": "LOGIN"})
    await executor.wait(300)

    await executor.goto(f"{portal}/invoices")
    await executor.type_text({"label": "Invoice Number:"}, "INV-100")
    await executor.type_text({"label": "Vendor:"}, "Acme Corp")
    await executor.type_text({"label": "Amount:"}, "250.00")
    await executor.type_text({"label": "Invoice Date:"}, "2026-06-01")
    # Create a temp PDF file for upload validation.
    pdf_path = tmp_path / "test_invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test invoice content")
    await executor.upload({"label": "Document:"}, str(pdf_path))
    await executor.click({"role": "button", "label": "SAVE"})
    await executor.wait(500)

    obs = await executor.observe()
    assert "SUCCESS" in obs.visible_text or "/success" in obs.url


@pytest.mark.asyncio
async def test_selective_change_semantic_fallback(portal, executor):
    """When fields are renamed (SELECTOR_CHANGE), semantic resolution should still find them."""
    await executor.goto(f"{portal}/login?scenario=SELECTOR_CHANGE")
    await executor.type_text({"role": "textbox", "label": "Username:"}, "admin")
    await executor.type_text({"role": "textbox", "label": "Password:"}, "admin")
    await executor.click({"role": "button", "label": "LOGIN"})
    await executor.wait(300)

    obs = await executor.goto(f"{portal}/invoices?scenario=SELECTOR_CHANGE")
    assert "/invoices" in obs.url
    labels = [e.label for e in obs.interactive_elements]
    # With SELECTOR_CHANGE, fields should be renamed.
    assert "Document ID:" in labels or "Supplier Name:" in labels


@pytest.mark.asyncio
async def test_captcha_detection(portal, executor):
    """Observe page should detect CAPTCHA presence."""
    await executor.goto(f"{portal}/login")
    await executor.type_text({"role": "textbox", "label": "Username:"}, "admin")
    await executor.type_text({"role": "textbox", "label": "Password:"}, "admin")
    await executor.click({"role": "button", "label": "LOGIN"})
    await executor.wait(300)

    obs = await executor.goto(f"{portal}/invoices?scenario=CAPTCHA")
    assert obs.captcha_present is True
    # The captcha form fields should be present in the page.
    page_text = obs.visible_text.lower()
    assert "captcha" in page_text or "captcha_answer" in [e.id for e in obs.interactive_elements]


@pytest.mark.asyncio
async def test_modal_detection(portal, executor):
    """Observe page should detect unexpected modal."""
    await executor.goto(f"{portal}/login")
    await executor.type_text({"role": "textbox", "label": "Username:"}, "admin")
    await executor.type_text({"role": "textbox", "label": "Password:"}, "admin")
    await executor.click({"role": "button", "label": "LOGIN"})
    await executor.wait(300)

    obs = await executor.goto(f"{portal}/invoices?scenario=UNEXPECTED_MODAL")
    assert obs.modal_present is True


@pytest.mark.asyncio
async def test_navigation_denied(portal, executor):
    """Navigation to non-allowed domain should be rejected."""
    from app.browser.executor import NavigationDenied
    with pytest.raises(NavigationDenied):
        await executor.goto("http://evil.example.com/steal")


@pytest.mark.asyncio
async def test_screenshot_persisted(portal, executor, tmp_path):
    obs = await executor.goto(f"{portal}/login")
    assert obs.screenshot_path is not None
    assert Path(obs.screenshot_path).exists()
    assert Path(obs.screenshot_path).stat().st_size > 0


@pytest.mark.asyncio
async def test_observe_structured_elements(portal, executor):
    """Observation should return structured elements with id/role/label."""
    obs = await executor.goto(f"{portal}/login")
    assert len(obs.interactive_elements) >= 3  # username, password, submit
    for el in obs.interactive_elements:
        assert el.id.startswith("e")
        assert el.role in ("textbox", "button", "link")
        assert len(el.label) > 0
