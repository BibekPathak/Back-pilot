"""Tests for M6: human-takeover API and dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.db.session import Base, engine, SessionLocal

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test, drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _create_run(task: str = "test task", state: str = "CREATED") -> dict:
    resp = client.post("/api/runs", json={"task": task, "scenario": "test"})
    assert resp.status_code == 201
    run = resp.json()
    # Manually set state for tests that need non-default state.
    if state != "CREATED":
        db = SessionLocal()
        from app.models.run import Run
        r = db.get(Run, run["id"])
        r.state = state
        db.commit()
        db.close()
        run["state"] = state
    return run


# ------------------------------------------------------------------
# Request intervention
# ------------------------------------------------------------------
def test_request_intervention():
    run = _create_run()
    resp = client.post(
        f"/api/runs/{run['id']}/intervention",
        json={"reason": "CAPTCHA on page"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["reason"] == "CAPTCHA on page"
    assert data["status"] == "pending"
    assert data["run_id"] == run["id"]


def test_request_intervention_run_not_found():
    resp = client.post(
        "/api/runs/nonexistent/intervention",
        json={"reason": "test"},
    )
    assert resp.status_code == 404


def test_request_intervention_updates_run_state():
    run = _create_run(state="FILLING_FORM")
    client.post(
        f"/api/runs/{run['id']}/intervention",
        json={"reason": "CAPTCHA"},
    )
    resp = client.get(f"/api/runs/{run['id']}")
    assert resp.json()["state"] == "HUMAN_INTERVENTION"


def test_request_intervention_with_assignment():
    run = _create_run()
    resp = client.post(
        f"/api/runs/{run['id']}/intervention",
        json={"reason": "ambiguous", "assigned_to": "alice"},
    )
    assert resp.json()["assigned_to"] == "alice"


# ------------------------------------------------------------------
# List interventions
# ------------------------------------------------------------------
def test_list_interventions():
    run = _create_run()
    client.post(f"/api/runs/{run['id']}/intervention", json={"reason": "a"})
    client.post(f"/api/runs/{run['id']}/intervention", json={"reason": "b"})
    resp = client.get(f"/api/runs/{run['id']}/interventions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["reason"] == "b"  # Most recent first


def test_list_interventions_run_not_found():
    resp = client.get("/api/runs/nonexistent/interventions")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Resolve intervention
# ------------------------------------------------------------------
def test_resolve_intervention():
    run = _create_run()
    iv_resp = client.post(
        f"/api/runs/{run['id']}/intervention", json={"reason": "captcha"}
    )
    iv_id = iv_resp.json()["id"]
    resp = client.put(
        f"/api/runs/{run['id']}/intervention/{iv_id}",
        json={"resolution_note": "I solved the captcha", "status": "resolved"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"
    assert resp.json()["resolution_note"] == "I solved the captcha"
    assert resp.json()["resolved_at"] is not None


def test_resolve_intervention_not_found():
    resp = client.put(
        "/api/runs/run_abc/intervention/999",
        json={"resolution_note": "test", "status": "resolved"},
    )
    assert resp.status_code == 404


def test_resolve_intervention_wrong_run():
    run1 = _create_run(task="run1")
    run2 = _create_run(task="run2")
    iv_resp = client.post(
        f"/api/runs/{run1['id']}/intervention", json={"reason": "captcha"}
    )
    iv_id = iv_resp.json()["id"]
    resp = client.put(
        f"/api/runs/{run2['id']}/intervention/{iv_id}",
        json={"resolution_note": "wrong run", "status": "resolved"},
    )
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Resume run
# ------------------------------------------------------------------
def test_resume_run_continue():
    run = _create_run(state="HUMAN_INTERVENTION")
    client.post(f"/api/runs/{run['id']}/intervention", json={"reason": "captcha"})
    resp = client.post(
        f"/api/runs/{run['id']}/resume",
        json={"action": "continue", "note": "captcha solved"},
    )
    assert resp.status_code == 200
    # Run should now be in RECOVERING state.
    run_resp = client.get(f"/api/runs/{run['id']}")
    assert run_resp.json()["state"] == "RECOVERING"


def test_resume_run_abort():
    run = _create_run(state="HUMAN_INTERVENTION")
    client.post(f"/api/runs/{run['id']}/intervention", json={"reason": "captcha"})
    resp = client.post(
        f"/api/runs/{run['id']}/resume",
        json={"action": "abort", "note": "too hard"},
    )
    assert resp.status_code == 200
    run_resp = client.get(f"/api/runs/{run['id']}")
    assert run_resp.json()["state"] == "FAILED"
    assert run_resp.json()["result"] == "aborted_by_human"


def test_resume_run_wrong_state():
    run = _create_run(state="FILLING_FORM")
    resp = client.post(
        f"/api/runs/{run['id']}/resume",
        json={"action": "continue"},
    )
    assert resp.status_code == 400
    assert "HUMAN_INTERVENTION" in resp.json()["detail"]


def test_resume_run_not_found():
    resp = client.post(
        "/api/runs/nonexistent/resume",
        json={"action": "continue"},
    )
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------
def test_dashboard_stats():
    _create_run(task="a")
    _create_run(task="b")
    # Mark one as SUCCESS.
    db = SessionLocal()
    from app.models.run import Run
    runs = db.query(Run).all()
    if runs:
        runs[0].state = "SUCCESS"
        db.commit()
    db.close()
    resp = client.get("/api/dashboard/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_runs"] == 2
    assert data["success"] == 1


def test_dashboard_active_runs():
    _create_run(task="running", state="FILLING_FORM")
    _create_run(task="done", state="SUCCESS")
    resp = client.get("/api/dashboard/runs/active")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["runs"]) == 1
    assert data["runs"][0]["state"] == "FILLING_FORM"
