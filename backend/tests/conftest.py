"""Shared test fixtures for BackPilot test suite."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db.session import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


# ------------------------------------------------------------------
# Database fixtures (SQLite in-memory for tests)
# ------------------------------------------------------------------
@pytest.fixture()
def db_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """Create a database session for testing."""
    TestSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture()
def api_client(db_engine) -> Generator[TestClient, None, None]:
    """Create a FastAPI TestClient with an overridden database."""
    TestSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ------------------------------------------------------------------
# Portal subprocess fixture
# ------------------------------------------------------------------
@pytest.fixture(scope="module")
def portal_url() -> Generator[str, None, None]:
    """Start the legacy portal on a free port and return its URL.

    The portal is started once per module and shared across all tests.
    """
    port = 18082  # Use a high port to avoid conflicts.
    env = {
        "PORT": str(port),
        "PORTAL_FAILURE_MODE": "NORMAL",
    }
    proc = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "legacy-portal" / "portal.py")],
        env={**dict(__import__("os").environ), **env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for the portal to be ready.
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError(f"Portal failed to start on port {port}")

    yield f"http://localhost:{port}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def portal_url_with_modal() -> Generator[str, None, None]:
    """Start the portal with UNEXPECTED_MODAL failure mode."""
    port = 18083
    env = {
        "PORT": str(port),
        "PORTAL_FAILURE_MODE": "UNEXPECTED_MODAL",
    }
    proc = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "legacy-portal" / "portal.py")],
        env={**dict(__import__("os").environ), **env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError(f"Portal failed to start on port {port}")

    yield f"http://localhost:{port}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def portal_url_with_captcha() -> Generator[str, None, None]:
    """Start the portal with CAPTCHA failure mode."""
    port = 18084
    env = {
        "PORT": str(port),
        "PORTAL_FAILURE_MODE": "CAPTCHA",
    }
    proc = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "legacy-portal" / "portal.py")],
        env={**dict(__import__("os").environ), **env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError(f"Portal failed to start on port {port}")

    yield f"http://localhost:{port}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
