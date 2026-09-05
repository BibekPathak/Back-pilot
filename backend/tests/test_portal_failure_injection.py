"""Failure-injection tests for the legacy ERP portal.

These exercise the portal failure injection system deterministically:
every mode must be reproducible and behave as specified.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PORTAL_DIR = Path(__file__).resolve().parents[2] / "legacy-portal"
sys.path.insert(0, str(PORTAL_DIR))

from failure import FAILURE_MODES, FailureInjector, WORKFLOW_STEPS  # noqa: E402
from portal import app  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(app)


def _login(client, scenario: str | None = None) -> None:
    url = "/login"
    if scenario:
        url += f"?scenario={scenario}"
    r = client.post(url, data={"username": "admin", "password": "admin"}, follow_redirects=False)
    assert r.status_code == 302
    assert "bp_session" in r.headers["set-cookie"] or "bp_session=" in r.headers["set-cookie"]


# --------------------------------------------------------------------------
# Failure injector unit tests
# --------------------------------------------------------------------------
def test_all_modes_known():
    assert FAILURE_MODES == {
        "NORMAL", "SELECTOR_CHANGE", "SLOW_NETWORK", "MISSING_ELEMENT",
        "UNEXPECTED_MODAL", "SESSION_EXPIRED", "UPLOAD_FAILURE", "CAPTCHA",
    }


def test_default_is_normal():
    inj = FailureInjector()
    for step in WORKFLOW_STEPS:
        assert inj.resolve(step) is None


def test_single_mode_applies_everywhere():
    inj = FailureInjector(mode="CAPTCHA")
    assert inj.applies("FILL_FORM", {"CAPTCHA"})
    assert inj.applies("SUBMIT", {"CAPTCHA"})


def test_sequence_maps_one_mode_per_step():
    inj = FailureInjector(sequence=["UNEXPECTED_MODAL", "CAPTCHA"])
    assert inj.resolve("INVOICE_PAGE") == "UNEXPECTED_MODAL"
    assert inj.resolve("FILL_FORM") == "CAPTCHA"
    # Modes inactive elsewhere
    assert inj.resolve("UPLOAD") is None
    assert inj.resolve("SUBMIT") is None


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        FailureInjector(mode="HACKED")


def test_env_injection():
    inj = FailureInjector.from_env({"PORTAL_FAILURE_MODE": "SESSION_EXPIRED"})
    assert inj.resolve("INVOICE_PAGE") == "SESSION_EXPIRED"
