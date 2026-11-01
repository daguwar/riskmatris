"""Unit tests for AppState and FastAPI dependency injection."""

from fastapi.testclient import TestClient

from riskmatris import app
from riskmatris.session import create_new_risk
from riskmatris.state import AppState, get_app_state


def test_app_state_custom_isolation():
    """AppState can be created with isolated dicts without touching globals."""
    custom_sessions = {
        "CUSTOM": {
            "session_id": "CUSTOM",
            "admin_token": "secret",
            "title": "Isolated Session",
            "threshold": 3,
            "created_at": 0.0,
            "updated_at": 0.0,
            "active_risk_number": 1,
            "risks": [create_new_risk(1, "Risk in isolated state")],
        }
    }
    custom_rate_log = {"127.0.0.1": [100.0]}
    custom_tickets = {}

    state = AppState(
        sessions=custom_sessions,
        session_create_log=custom_rate_log,
        ws_tickets=custom_tickets,
    )

    assert len(state.sessions) == 1
    assert "CUSTOM" in state.sessions
    assert state.sessions["CUSTOM"]["title"] == "Isolated Session"
    assert state.session_create_log == {"127.0.0.1": [100.0]}


def test_dependency_injection_override():
    """FastAPI endpoints use the injected AppState via app.dependency_overrides."""
    mock_sessions = {
        "INJECT": {
            "session_id": "INJECT",
            "admin_token": "admin123",
            "title": "Dependency Injected",
            "threshold": 2,
            "created_at": 0.0,
            "updated_at": 0.0,
            "active_risk_number": 1,
            "risks": [create_new_risk(1, "Injected Risk")],
        }
    }
    mock_state = AppState(sessions=mock_sessions)

    # Override the dependency cleanly
    app.dependency_overrides[get_app_state] = lambda: mock_state

    try:
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_sessions"] == 1

        info_resp = client.get("/api/sessions/INJECT")
        assert info_resp.status_code == 200
        assert info_resp.json()["title"] == "Dependency Injected"
    finally:
        app.dependency_overrides.clear()
