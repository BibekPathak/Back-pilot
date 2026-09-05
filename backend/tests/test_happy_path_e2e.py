"""End-to-end happy-path workflow test.

Proves the full pipeline: extract → navigate → login → fill → upload →
submit → verify, against the live legacy portal.
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

PORTAL_DIR = Path(__file__).resolve().parents[2] / "legacy-portal"
BACKEND_DIR = Path(__file__).resolve().parents[1]
PORTAL_PORT = 8084
PORTAL_URL = f"http://127.0.0.1:{PORTAL_PORT}"


@pytest.fixture(scope="module")
def portal():
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "portal:app",
         "--host", "127.0.0.1", "--port", str(PORTAL_PORT)],
        cwd=str(PORTAL_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
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
async def session(tmp_path):
    sys.path.insert(0, str(BACKEND_DIR))
    from app.browser.session import launch_session
    s = await launch_session(
        screenshot_dir=str(tmp_path / "shots"),
        allowed_domains=["127.0.0.1", "localhost"],
    )
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_happy_path_e2e(portal, session):
    from app.models.run import RunState
    from app.workflows.happy_path import run_happy_path

    result = await run_happy_path(
        session.executor,
        portal_url=portal,
        invoice_data={
            "invoice_number": "INV-29381",
            "vendor": "Acme Corp",
            "amount": 4291.20,
            "invoice_date": "2026-09-05",
            "filename": str(Path(__file__).resolve().parents[2] / "fixtures" / "invoice.pdf"),
        },
    )

    assert result.state == RunState.SUCCESS, f"Expected SUCCESS, got {result.state}"
    assert result.success is True
    assert result.duration_ms > 0
    assert len(result.events) > 0

    # Verify key events exist.
    actions = [e for e in result.events if e.kind == "action"]
    action_names = [e.action for e in actions]
    assert "goto" in action_names, f"Expected goto action, got: {action_names}"
    assert "type" in action_names, f"Expected type action, got: {action_names}"
    assert "click" in action_names, f"Expected click action, got: {action_names}"
    assert "upload" in action_names, f"Expected upload action, got: {action_names}"

    # Verify state transitions were recorded.
    transitions = [e for e in result.events if e.kind == "state_change"]
    assert len(transitions) >= 3, f"Expected >=3 transitions, got {len(transitions)}"

    # Verify the final page shows success.
    # The engine stores the last observation; get it from the events.
    final_events = [e for e in result.events if e.kind == "action"]
    assert len(final_events) > 0
    # The last action should be "finish" with success.
    last_action = final_events[-1]
    assert last_action.action == "finish"
    assert last_action.result == "success"


@pytest.mark.asyncio
async def test_happy_path_events_timeline(portal, session):
    from app.workflows.happy_path import run_happy_path

    result = await run_happy_path(
        session.executor,
        portal_url=portal,
        invoice_data={
            "invoice_number": "INV-E2E-001",
            "vendor": "E2E Test Corp",
            "amount": 100.00,
            "invoice_date": "2026-06-15",
            "filename": str(Path(__file__).resolve().parents[2] / "fixtures" / "invoice.pdf"),
        },
    )

    # Build a human-readable timeline.
    timeline = []
    for ev in result.events:
        if ev.kind == "state_change":
            timeline.append(f"[STATE] {ev.detail}")
        elif ev.kind == "action":
            timeline.append(f"[{ev.result}] {ev.action} ({ev.duration_ms}ms)")
        elif ev.kind == "recovery":
            timeline.append(f"[RETRY] {ev.detail}")

    # Verify timeline has expected structure.
    assert any("PLANNING" in t for t in timeline), "Missing PLANNING transition"
    assert any("NAVIGATING" in t for t in timeline), "Missing NAVIGATING transition"
    assert any("SUCCESS" in t for t in timeline), "Missing SUCCESS transition"
    assert any("goto" in t for t in timeline), "Missing goto action"
    assert any("type" in t for t in timeline), "Missing type action"
    assert any("upload" in t for t in timeline), "Missing upload action"
