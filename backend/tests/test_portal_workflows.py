"""Browser-independent portal workflow tests (via HTTP).

They verify the portal's deterministic behavior end-to-end at the HTTP layer,
covering every injection mode plus the happy path. (Playwright browser tests
come in M13.)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PORTAL_DIR = Path(__file__).resolve().parents[2] / "legacy-portal"
sys.path.insert(0, str(PORTAL_DIR))

from portal import app  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(app)


def _login(client, scenario: str | None = None) -> str:
    url = "/login" + (f"?scenario={scenario}" if scenario else "")
    r = client.post(url, data={"username": "admin", "password": "admin"}, follow_redirects=False)
    assert r.status_code == 302
    return r.headers["set-cookie"].split(";")[0]


def _submit_invoice(client, scenario: str | None = None, **overrides) -> str:
    cookie = _login(client, scenario)
    fields = {
        "invoice_number": "INV-29381",
        "vendor": "Acme Corp",
        "amount": "4291.20",
        "invoice_date": "2026-09-05",
        "captcha_answer": "7",
    }
    fields.update(overrides)
    return client.post(
        "/invoices",
        data=fields,
        files={"document": ("invoice.pdf", b"%PDF-1.4 mock", "application/pdf")}
        if overrides.get("upload", True)
        else None,
        cookies={"bp_session": cookie.split("=")[1]},
        follow_redirects=False,
    )


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------
def test_happy_path_submits(client):
    cookie = _login(client)
    r = client.get(
        "/invoices",
        cookies={"bp_session": cookie.split("=")[1]},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "Invoice Number" in r.text
    assert "id=\"submit\"" in r.text

    res = client.post(
        "/invoices",
        data={
            "invoice_number": "INV-29381", "vendor": "Acme Corp",
            "amount": "4291.20", "invoice_date": "2026-09-05",
        },
        files={"document": ("invoice.pdf", b"%PDF mock", "application/pdf")},
        cookies={"bp_session": cookie.split("=")[1]},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert res.headers["location"].endswith("/success")


def test_redirects_when_unauthenticated(client):
    r = client.get("/invoices", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/login")


def test_invalid_login_shows_error(client):
    r = client.post("/login", data={"username": "x", "password": "y"})
    assert r.status_code == 200
    assert "Invalid credentials" in r.text


# --------------------------------------------------------------------------
# Failure modes (each deterministic via ?scenario=)
# --------------------------------------------------------------------------
def test_selector_change_renames_fields(client):
    _login(client, "SELECTOR_CHANGE")
    r = client.get("/invoices?scenario=SELECTOR_CHANGE")
    assert "Document ID" in r.text
    assert "Supplier Name" in r.text
    assert "Invoice Number" not in r.text


def test_missing_element_removes_submit(client):
    _login(client, "MISSING_ELEMENT")
    r = client.get("/invoices?scenario=MISSING_ELEMENT")
    assert "id=\"submit\"" not in r.text


def test_unexpected_modal_rendered(client):
    _login(client, "UNEXPECTED_MODAL")
    r = client.get("/invoices?scenario=UNEXPECTED_MODAL")
    assert "UNEXPECTED SYSTEM MESSAGE" in r.text
    assert "id=\"modal\"" in r.text


def test_captcha_requires_answer(client):
    _login(client, "CAPTCHA")
    r = client.get("/invoices?scenario=CAPTCHA")
    assert "captcha_answer" in r.text

    bad = _submit_invoice(client, "CAPTCHA", captcha_answer="99")
    assert "Captcha verification failed" in bad.text

    ok = _submit_invoice(client, "CAPTCHA", captcha_answer="7")
    assert ok.status_code == 302
    assert ok.headers["location"].endswith("/success")


def test_session_expired_forces_relogin(client):
    _login(client, "SESSION_EXPIRED")
    r = client.get("/invoices?scenario=SESSION_EXPIRED", follow_redirects=False)
    # first visit triggers expiry and redirects to login
    assert r.status_code == 302
    assert r.headers["location"].startswith("/login")


def test_upload_failure_errors(client):
    res = _submit_invoice(client, "UPLOAD_FAILURE")
    assert "Upload service unavailable" in res.text


def test_slow_network_delays(client):
    import time
    start = time.time()
    _login(client, "SLOW_NETWORK")
    elapsed = time.time() - start
    assert elapsed >= 2.5


def test_sequence_multi_failure(client):
    # UNEXPECTED_MODAL at invoice page, then CAPTCHA at fill step.
    cookie = _login(client, "UNEXPECTED_MODAL")
    sc = "UNEXPECTED_MODAL"
    r = client.get(f"/invoices?scenario={sc}", cookies={"bp_session": cookie.split("=")[1]})
    assert "UNEXPECTED SYSTEM MESSAGE" in r.text
