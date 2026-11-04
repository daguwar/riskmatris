"""Shared pytest fixtures for the riskmatris test suite (REFACTORING.md fas 6).

Centralizes the test client and the session factories that used to be
duplicated as _add_session()/_make_session()/_client() helpers in test_app.py.
"""

import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app, create_new_risk, manager


@pytest.fixture
def test_client():
    """A FastAPI TestClient bound to the app."""
    return TestClient(app)


@pytest.fixture
def make_session():
    """Factory that builds a session dict matching the backend schema."""

    def _make_session(threshold=4, votes=None, sid="TEST01", title="Test"):
        risk = create_new_risk(1, "")
        if votes:
            risk["votes"] = {
                f"c{i}": {"probability": p, "consequence": c, "updated_at": 0} for i, (p, c) in enumerate(votes)
            }
        return {
            "session_id": sid,
            "admin_token": "x",
            "title": title,
            "threshold": threshold,
            "created_at": 0.0,
            "updated_at": 0.0,
            "active_risk_number": 1,
            "risks": [risk],
        }

    return _make_session


@pytest.fixture
def add_session(make_session):
    """Registers a session in the app state and removes it after the test."""

    created = []

    def _add_session(sid, admin_token="x", **kwargs):
        session = make_session(sid=sid, **kwargs)
        session["admin_token"] = admin_token
        app_module.SESSIONS[sid] = session
        created.append(sid)
        return session

    yield _add_session

    for sid in created:
        app_module.SESSIONS.pop(sid, None)
        manager.connections.pop(sid, None)


@pytest.fixture
def isolated_client(monkeypatch, tmp_path):
    """TestClient with an isolated SQLite DB and cleared in-memory state."""
    monkeypatch.setattr(app_module, "DB_PATH", str(tmp_path / "test.db"))
    app_module.init_db()
    monkeypatch.setattr(app_module, "SESSIONS", {})
    monkeypatch.setattr(app_module, "SESSION_CREATE_LOG", {})
    monkeypatch.setattr(app_module, "SESSION_READ_LOG", {})
    return TestClient(app_module.app)
