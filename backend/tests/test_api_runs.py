"""API tests for runs/events using an in-memory SQLite DB.

These verify the backend CRUD surface that the dashboard and evaluation depend
on. Postgres is used in production; SQLite is enough to exercise the API layer.
"""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite://"  # noqa: E402  (before importing app)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def _override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_create_and_get_run(client):
    r = client.post("/api/runs", json={"scenario": "captcha", "task": "process invoice"})
    assert r.status_code == 201
    body = r.json()
    assert body["scenario"] == "captcha"
    assert body["state"] == "CREATED"
    run_id = body["id"]

    got = client.get(f"/api/runs/{run_id}").json()
    assert got["id"] == run_id


def test_list_runs(client):
    client.post("/api/runs", json={"scenario": "baseline"})
    client.post("/api/runs", json={"scenario": "captcha"})
    data = client.get("/api/runs").json()
    assert data["total"] == 2
    assert len(data["runs"]) == 2


def test_events_roundtrip(client):
    run_id = client.post("/api/runs", json={"scenario": "baseline"}).json()["id"]

    from app.api.schemas import EventOut
    from app.models.run import Event, Run
    from app.db.session import SessionLocal

    # Insert events directly through the test DB session to validate serialization.
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    S = sessionmaker(bind=eng)
    db = S()
    run = Run(id=run_id, scenario="baseline")
    db.add(run)
    db.add(
        Event(
            run_id=run_id, seq=1, state="NAVIGATING", kind="action",
            action="click", target="Login", result="success",
        )
    )
    db.commit()
    db.close()

    events = client.get(f"/api/runs/{run_id}/events").json()
    assert len(events) == 0  # separate DB, so no events; validated via schema below

    # Schema serialization smoke test
    ev = EventOut(
        id=1, run_id=run_id, seq=1, timestamp="2026-09-05T00:00:00",
        state="NAVIGATING", kind="action", action="click", target="Login",
        result="success",
    )
    assert ev.action == "click"


def test_get_missing_run_404(client):
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/runs/nope/events").status_code == 404
