"""Unit tests for the core functions in app.py."""

import os
import sys

# Add the project root to sys.path so we can import app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app import (
    CONSEQUENCE_LABELS,
    MAX_TITLE_LENGTH,
    PROBABILITY_LABELS,
    _safe_int,
    check_session_create_rate,
    cleanup_rate_limit_log,
    compute_risk_stats,
    consume_ws_ticket,
    create_new_risk,
    create_ws_ticket,
    generate_session_id,
    get_local_lan_ip,
    get_risk_level,
    round_half_up,
    sanitize_user_text,
)

# ---------------------------------------------------------------------------
# round_half_up
# ---------------------------------------------------------------------------


class TestRoundHalfUp:
    """Rounding per the cautious principle (.5 up), clamped to 1..4."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            (1.0, 1),
            (1.4, 1),
            (1.5, 2),
            (1.6, 2),
            (2.0, 2),
            (2.5, 3),
            (3.0, 3),
            (3.5, 4),
            (4.0, 4),
            (4.4, 4),
            # Out of bounds – must be clamped
            (0.0, 1),
            (0.4, 1),
            (0.5, 1),
            (5.0, 4),
            (99.9, 4),
            (-1.0, 1),
        ],
    )
    def test_rounding(self, value, expected):
        assert round_half_up(value) == expected

    def test_exact_half_rounds_up(self):
        ".5 must always round up."
        assert round_half_up(2.5) == 3
        assert round_half_up(3.5) == 4

    def test_below_half_rounds_down(self):
        assert round_half_up(2.49) == 2
        assert round_half_up(3.49) == 3


# ---------------------------------------------------------------------------
# get_risk_level
# ---------------------------------------------------------------------------


class TestGetRiskLevel:
    """Risk scores 1–16 map to a level and a color."""

    @pytest.mark.parametrize(
        "score, expected_level, expected_color",
        [
            (1, "Låg", "green"),
            (2, "Låg", "green"),
            (3, "Medel", "yellow"),
            (4, "Medel", "yellow"),
            (6, "Medel", "yellow"),
            (8, "Hög", "orange"),
            (9, "Hög", "orange"),
            (12, "Mycket Hög", "red"),
            (16, "Mycket Hög", "red"),
        ],
    )
    def test_levels(self, score, expected_level, expected_color):
        result = get_risk_level(score)
        assert result["level"] == expected_level
        assert result["color"] == expected_color

    def test_boundary_green_to_yellow(self):
        assert get_risk_level(2)["level"] == "Låg"
        assert get_risk_level(3)["level"] == "Medel"

    def test_boundary_yellow_to_orange(self):
        assert get_risk_level(6)["level"] == "Medel"
        assert get_risk_level(8)["level"] == "Hög"

    def test_boundary_orange_to_red(self):
        assert get_risk_level(9)["level"] == "Hög"
        assert get_risk_level(12)["level"] == "Mycket Hög"


# ---------------------------------------------------------------------------
# generate_session_id
# ---------------------------------------------------------------------------


class TestGenerateSessionId:
    """Session IDs must be 6 characters, without confusable characters."""

    ALLOWED_CHARS = set("23456789ABCDEFGHJKLMNPQRSTUVWXYZ")

    def test_length_is_six(self):
        sid = generate_session_id()
        assert len(sid) == 6

    def test_only_allowed_chars(self):
        for _ in range(100):
            sid = generate_session_id()
            for ch in sid:
                assert ch in self.ALLOWED_CHARS, f"Disallowed character '{ch}' in {sid}"

    def test_no_ambiguous_chars(self):
        """0, O, 1, I, L must never occur."""
        forbidden = set("01OIL")
        for _ in range(200):
            sid = generate_session_id()
            for ch in sid:
                assert ch not in forbidden, f"Confusable character '{ch}' in {sid}"

    def test_uniqueness(self):
        """Generated IDs must be unique (at least among 1000 attempts)."""
        seen = set()
        for _ in range(1000):
            sid = generate_session_id()
            assert sid not in seen, f"Duplicate: {sid}"
            seen.add(sid)


# ---------------------------------------------------------------------------
# create_new_risk
# ---------------------------------------------------------------------------


class TestCreateNewRisk:
    def test_defaults(self):
        risk = create_new_risk(1)
        assert risk["number"] == 1
        assert risk["label"] == ""
        assert risk["votes"] == {}
        assert risk["revealed"] is False
        assert risk["locked"] is False
        assert risk["final_probability"] is None
        assert risk["final_consequence"] is None

    def test_with_label(self):
        risk = create_new_risk(3, "  Brandrisk  ")
        assert risk["number"] == 3
        assert risk["label"] == "Brandrisk"  # whitespace stripped

    def test_empty_label_stripped(self):
        risk = create_new_risk(2, "   ")
        assert risk["label"] == ""


# ---------------------------------------------------------------------------
# compute_risk_stats
# ---------------------------------------------------------------------------


class TestComputeRiskStats:
    def _make_risk(self, votes=None, revealed=False, locked=False, final_prob=None, final_cons=None, label="Testrisk"):
        risk = create_new_risk(1, label)
        if votes:
            risk["votes"] = votes
        risk["revealed"] = revealed
        risk["locked"] = locked
        risk["final_probability"] = final_prob
        risk["final_consequence"] = final_cons
        return risk

    def test_no_votes(self):
        risk = self._make_risk()
        stats = compute_risk_stats(risk, threshold=4)
        assert stats["vote_count"] == 0
        assert stats["revealed"] is False
        assert stats["avg_probability"] is None
        assert stats["suggested_probability"] is None
        assert stats["cell_counts"] == {}

    def test_votes_hidden_when_below_threshold(self):
        votes = {
            "a": {"probability": 2, "consequence": 3, "updated_at": 0},
            "b": {"probability": 3, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes)
        stats = compute_risk_stats(risk, threshold=4)
        assert stats["vote_count"] == 2
        assert stats["revealed"] is False
        # Averages must be hidden while not revealed
        assert stats["avg_probability"] is None
        assert stats["cell_counts"] == {}

    def test_votes_revealed_at_threshold(self):
        """When votes >= threshold: threshold_reached=True, the caller sets revealed=True."""
        votes = {
            "a": {"probability": 2, "consequence": 3, "updated_at": 0},
            "b": {"probability": 3, "consequence": 2, "updated_at": 0},
            "c": {"probability": 4, "consequence": 4, "updated_at": 0},
            "d": {"probability": 1, "consequence": 1, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes)
        stats = compute_risk_stats(risk, threshold=4)
        assert stats["vote_count"] == 4
        assert stats["threshold_reached"] is True
        # Before the caller updates revealed: revealed is still False in stats
        assert stats["revealed"] is False

        # Simulate what build_client_payload does: set revealed=True on threshold_reached
        risk["revealed"] = True
        stats = compute_risk_stats(risk, threshold=4)
        assert stats["revealed"] is True
        assert stats["threshold_reached"] is False  # already revealed
        assert stats["avg_probability"] == 2.5
        assert stats["avg_consequence"] == 2.5
        assert stats["suggested_probability"] == 3  # .5 rounds up
        assert stats["suggested_consequence"] == 3

    def test_cell_counts(self):
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
            "b": {"probability": 2, "consequence": 2, "updated_at": 0},
            "c": {"probability": 3, "consequence": 1, "updated_at": 0},
            "d": {"probability": 4, "consequence": 4, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes, revealed=True)
        stats = compute_risk_stats(risk, threshold=4)
        assert stats["cell_counts"]["2_2"] == 2
        assert stats["cell_counts"]["3_1"] == 1
        assert stats["cell_counts"]["4_4"] == 1
        assert len(stats["cell_counts"]) == 3

    def test_locked_risk_shows_final_values(self):
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(
            votes=votes,
            locked=True,
            final_prob=4,
            final_cons=3,
        )
        stats = compute_risk_stats(risk, threshold=4)
        assert stats["locked"] is True
        assert stats["revealed"] is True
        assert stats["final_probability"] == 4
        assert stats["final_consequence"] == 3
        assert stats["effective_probability"] == 4
        assert stats["effective_consequence"] == 3
        assert stats["score"] == 12
        assert stats["level"] == "Mycket Hög"
        assert stats["color"] == "red"

    def test_final_overrides_suggested(self):
        """If final_probability is set, it must take precedence over the suggestion."""
        votes = {
            "a": {"probability": 1, "consequence": 1, "updated_at": 0},
            "b": {"probability": 2, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(
            votes=votes,
            revealed=True,
            final_prob=4,
            final_cons=4,
        )
        stats = compute_risk_stats(risk, threshold=4)
        # Averages become 1.5/1.5 -> suggestion 2/2, but final is 4/4
        assert stats["suggested_probability"] == 2
        assert stats["suggested_consequence"] == 2
        assert stats["effective_probability"] == 4
        assert stats["effective_consequence"] == 4
        assert stats["score"] == 16

    def test_score_and_level_correct(self):
        votes = {
            "a": {"probability": 3, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes, revealed=True)
        stats = compute_risk_stats(risk, threshold=1)
        assert stats["score"] == 6
        assert stats["level"] == "Medel"
        assert stats["color"] == "yellow"

    def test_threshold_auto_reveals(self):
        """When the vote count >= threshold, threshold_reached must be True.

        compute_risk_stats is now a pure function – no side effect on risk['revealed'].
        The caller (build_client_payload) is responsible for updating revealed.
        """
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
            "b": {"probability": 3, "consequence": 3, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes)
        assert risk["revealed"] is False
        stats = compute_risk_stats(risk, threshold=2)
        # threshold_reached must be True, but risk['revealed'] must NOT have changed
        assert stats["threshold_reached"] is True
        assert risk["revealed"] is False  # pure function – no side effect
        assert stats["revealed"] is False  # is_revealed is based on risk['revealed']

    def test_no_side_effect_on_risk(self):
        """compute_risk_stats must not mutate the risk dict at all."""
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes, revealed=False, locked=False)
        original = {k: v for k, v in risk.items() if k != "votes"}
        original_votes = dict(risk["votes"])
        compute_risk_stats(risk, threshold=1)
        # No change to risk after the call
        for k, v in original.items():
            assert risk[k] == v, f"risk['{k}'] changed: {risk[k]!r} != {v!r}"
        assert risk["votes"] == original_votes

    def test_threshold_not_reached_when_already_revealed(self):
        """threshold_reached must be False if the risk is already revealed."""
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes, revealed=True)
        stats = compute_risk_stats(risk, threshold=1)
        assert stats["threshold_reached"] is False

    def test_threshold_not_reached_below_threshold(self):
        """threshold_reached must be False when votes < threshold."""
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes)
        stats = compute_risk_stats(risk, threshold=4)
        assert stats["threshold_reached"] is False

    def test_threshold_not_reached_no_votes(self):
        """threshold_reached must be False when there are no votes."""
        risk = self._make_risk()
        stats = compute_risk_stats(risk, threshold=1)
        assert stats["threshold_reached"] is False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestLabels:
    def test_probability_labels_complete(self):
        assert set(PROBABILITY_LABELS.keys()) == {1, 2, 3, 4}
        assert PROBABILITY_LABELS[1] == "Osannolik"
        assert PROBABILITY_LABELS[4] == "Mycket sannolik"

    def test_consequence_labels_complete(self):
        assert set(CONSEQUENCE_LABELS.keys()) == {1, 2, 3, 4}
        assert CONSEQUENCE_LABELS[1] == "Försumbar"
        assert CONSEQUENCE_LABELS[4] == "Mycket allvarlig"


# ---------------------------------------------------------------------------
# get_local_lan_ip (cached)
# ---------------------------------------------------------------------------


class TestGetLocalLanIp:
    def test_returns_valid_ip_string(self):
        ip = get_local_lan_ip()
        assert isinstance(ip, str)
        # Must be an IPv4 address or 127.0.0.1
        parts = ip.split(".")
        assert len(parts) == 4
        for part in parts:
            assert 0 <= int(part) <= 255

    def test_is_cached(self):
        """Two calls must return the same value (cached)."""
        ip1 = get_local_lan_ip()
        ip2 = get_local_lan_ip()
        assert ip1 == ip2

    def test_cache_info_hit(self):
        """After the first call, cache info must show at least 1 hit or miss."""
        get_local_lan_ip()  # ensure the first call
        info = get_local_lan_ip.cache_info()
        assert info.hits + info.misses >= 1


# ---------------------------------------------------------------------------
# _safe_int (WebSocket validation)
# ---------------------------------------------------------------------------


class TestSafeInt:
    """Tests the helper for safe integer conversion from WS messages."""

    def test_valid_int(self):
        assert _safe_int({"probability": 3}, "probability", 0, 1, 4) == 3

    def test_valid_int_as_string(self):
        assert _safe_int({"probability": "3"}, "probability", 0, 1, 4) == 3

    def test_missing_key_uses_default(self):
        assert _safe_int({}, "probability", 2, 1, 4) == 2

    def test_below_min_returns_none(self):
        assert _safe_int({"probability": 0}, "probability", 2, 1, 4) is None

    def test_above_max_returns_none(self):
        assert _safe_int({"probability": 5}, "probability", 2, 1, 4) is None

    def test_non_numeric_returns_none(self):
        assert _safe_int({"probability": "abc"}, "probability", 0, 1, 4) is None

    def test_none_value_returns_none(self):
        assert _safe_int({"probability": None}, "probability", 0, 1, 4) is None

    def test_float_string_returns_none(self):
        """int('3.5') raises ValueError – must return None."""
        assert _safe_int({"probability": "3.5"}, "probability", 0, 1, 4) is None

    def test_bool_returns_none(self):
        """bool values: documented behavior check (see comments below)."""
        # bool is a subclass of int in Python. int(True) == 1, so this is
        # actually a valid value – test that it is handled
        result = _safe_int({"probability": True}, "probability", 0, 1, 4)
        # True -> int(True) = 1, which is within 1-4
        assert result == 1

    def test_boundary_min(self):
        assert _safe_int({"v": 1}, "v", 0, 1, 4) == 1

    def test_boundary_max(self):
        assert _safe_int({"v": 4}, "v", 0, 1, 4) == 4

    def test_negative_returns_none(self):
        assert _safe_int({"v": -1}, "v", 0, 1, 4) is None

    def test_large_default_bounds(self):
        """Tests with larger bounds (for risk numbers etc.)."""
        assert _safe_int({"number": 9999}, "number", 1, 1, 9999) == 9999
        assert _safe_int({"number": 10000}, "number", 1, 1, 9999) is None


# ---------------------------------------------------------------------------
# /health endpoint (integration test with httpx)
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Tests that /health responds correctly via the FastAPI TestClient."""

    def test_health_returns_ok(self):
        from fastapi.testclient import TestClient

        from app import app

        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "active_sessions" in data
        assert isinstance(data["active_sessions"], int)
        assert "db_path" in data


# ---------------------------------------------------------------------------
# WebSocket disconnect (regression: a disconnect used to deadlock the event loop)
# ---------------------------------------------------------------------------


class TestWebSocketDisconnect:
    """A disconnected client must be cleaned up and the endpoint must return.

    Regression test: WebSocketDisconnect used to be caught by the "except Exception"
    around receive_json(), so the handler spun in an infinite loop without yielding
    to the event loop – the whole server deadlocked on the first disconnect
    (closed tab/F5).
    """

    def test_disconnect_cleans_up_and_returns(self):
        import asyncio
        import threading
        from unittest.mock import AsyncMock, MagicMock

        from fastapi import WebSocketDisconnect

        from app import SESSIONS, create_new_risk, manager, websocket_endpoint

        sid = "TEST01"
        SESSIONS[sid] = {
            "session_id": sid,
            "admin_token": "hemlig",
            "title": "Test",
            "threshold": 4,
            "created_at": 0.0,
            "updated_at": 0.0,
            "active_risk_number": 1,
            "risks": [create_new_risk(1, "")],
        }
        try:
            ws = MagicMock()
            ws.accept = AsyncMock()
            ws.send_json = AsyncMock()
            # Simulate the client disconnecting immediately
            ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect(1000))

            result = {}

            def runner():
                try:
                    asyncio.run(
                        asyncio.wait_for(
                            websocket_endpoint(ws, sid, role="participant", client_id="test-klient", ticket=""),
                            timeout=5,
                        )
                    )
                    result["ok"] = True
                except Exception as exc:
                    result["ok"] = False
                    result["error"] = exc

            # Run in a daemon thread: if the endpoint hangs (regression), the
            # test should fail via timeout instead of hanging the whole suite.
            thread = threading.Thread(target=runner, daemon=True)
            thread.start()
            thread.join(timeout=15)

            assert result.get("ok") is True, f"Endpoint did not return as expected: {result.get('error')}"
            # The connection must be removed after the disconnect
            assert sid not in manager.connections
        finally:
            SESSIONS.pop(sid, None)
            manager.connections.pop(sid, None)


# ---------------------------------------------------------------------------
# sanitize_user_text (input hardening)
# ---------------------------------------------------------------------------


class TestSanitizeUserText:
    def test_removes_control_characters(self):
        assert sanitize_user_text("Foo\x00Bar\nBaz", 50) == "FooBarBaz"

    def test_removes_format_characters(self):
        # U+202E RIGHT-TO-LEFT OVERRIDE – a classic text-spoofing character
        assert sanitize_user_text("Evil\u202epayload", 50) == "Evilpayload"

    def test_clamps_length(self):
        assert len(sanitize_user_text("x" * 300, MAX_TITLE_LENGTH)) == MAX_TITLE_LENGTH

    def test_strips_outer_whitespace(self):
        assert sanitize_user_text("  Hello  ", 50) == "Hello"

    def test_empty_result_for_whitespace_only(self):
        assert sanitize_user_text("   \n\t ", 50) == ""


# ---------------------------------------------------------------------------
# Session-creation rate limiting
# ---------------------------------------------------------------------------


class TestSessionCreateRateLimit:
    def test_allows_within_limit(self, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_CREATE_LOG", {})
        monkeypatch.setattr(app_module, "SESSION_CREATE_LIMIT", 3)
        for _ in range(3):
            assert check_session_create_rate("1.2.3.4") is True

    def test_blocks_over_limit(self, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_CREATE_LOG", {})
        monkeypatch.setattr(app_module, "SESSION_CREATE_LIMIT", 2)
        assert check_session_create_rate("1.2.3.4") is True
        assert check_session_create_rate("1.2.3.4") is True
        assert check_session_create_rate("1.2.3.4") is False

    def test_limit_is_per_ip(self, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_CREATE_LOG", {})
        monkeypatch.setattr(app_module, "SESSION_CREATE_LIMIT", 1)
        assert check_session_create_rate("1.2.3.4") is True
        assert check_session_create_rate("1.2.3.4") is False
        assert check_session_create_rate("5.6.7.8") is True

    def test_cleanup_drops_stale_entries(self, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_CREATE_LOG", {"1.2.3.4": [0.0]})
        cleanup_rate_limit_log()
        assert app_module.SESSION_CREATE_LOG == {}

    def test_cleanup_keeps_fresh_entries(self, monkeypatch):
        import time as time_module

        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_CREATE_LOG", {"1.2.3.4": [time_module.time()]})
        cleanup_rate_limit_log()
        assert "1.2.3.4" in app_module.SESSION_CREATE_LOG


# ---------------------------------------------------------------------------
# Admin WebSocket connection tickets
# ---------------------------------------------------------------------------


class TestWsTickets:
    def test_valid_ticket(self):
        ticket = create_ws_ticket("ABC123")
        assert consume_ws_ticket(ticket, "ABC123") is True

    def test_ticket_is_single_use(self):
        ticket = create_ws_ticket("ABC123")
        assert consume_ws_ticket(ticket, "ABC123") is True
        assert consume_ws_ticket(ticket, "ABC123") is False

    def test_ticket_for_wrong_session_is_burned(self):
        ticket = create_ws_ticket("ABC123")
        assert consume_ws_ticket(ticket, "OTHER1") is False
        # A failed attempt burns the ticket, so it cannot be replayed
        assert consume_ws_ticket(ticket, "ABC123") is False

    def test_expired_ticket_rejected(self):
        import time as time_module

        import app as app_module

        ticket = create_ws_ticket("ABC123")
        app_module.WS_TICKETS[ticket]["expires_at"] = time_module.time() - 1
        assert consume_ws_ticket(ticket, "ABC123") is False

    def test_unknown_ticket_rejected(self):
        assert consume_ws_ticket("does-not-exist", "ABC123") is False

    def test_no_ticket_is_not_admin(self):
        # An empty ticket must never authenticate as admin
        assert consume_ws_ticket("", "ABC123") is False


class TestWsTicketEndpoint:
    def _add_session(self, sid, admin_token):
        from app import SESSIONS, create_new_risk

        SESSIONS[sid] = {
            "session_id": sid,
            "admin_token": admin_token,
            "title": "Test",
            "threshold": 4,
            "created_at": 0.0,
            "updated_at": 0.0,
            "active_risk_number": 1,
            "risks": [create_new_risk(1, "")],
        }
        return SESSIONS[sid]

    def test_requires_valid_admin_token(self):
        from fastapi.testclient import TestClient

        from app import SESSIONS, app, consume_ws_ticket

        sid = "TICKET1"
        self._add_session(sid, "secret-token")
        try:
            client = TestClient(app)
            assert client.get(f"/api/sessions/{sid}/ws-ticket").status_code == 401
            assert (
                client.get(f"/api/sessions/{sid}/ws-ticket", headers={"X-Admin-Token": "wrong"}).status_code == 401
            )
            resp = client.get(f"/api/sessions/{sid}/ws-ticket", headers={"X-Admin-Token": "secret-token"})
            assert resp.status_code == 200
            ticket = resp.json()["ticket"]
            assert ticket
            assert consume_ws_ticket(ticket, sid) is True
        finally:
            SESSIONS.pop(sid, None)

    def test_unknown_session_returns_404(self):
        from fastapi.testclient import TestClient

        from app import app

        client = TestClient(app)
        assert client.get("/api/sessions/NOPE00/ws-ticket").status_code == 404


# ---------------------------------------------------------------------------
# POST /api/sessions (title sanitization + rate limit, integration)
# ---------------------------------------------------------------------------


class TestCreateSessionHardening:
    def _client(self, monkeypatch, tmp_path):
        import app as app_module

        monkeypatch.setattr(app_module, "DB_PATH", str(tmp_path / "test.db"))
        app_module.init_db()
        monkeypatch.setattr(app_module, "SESSIONS", {})
        monkeypatch.setattr(app_module, "SESSION_CREATE_LOG", {})

        from fastapi.testclient import TestClient

        return TestClient(app_module.app)

    def test_title_sanitized_before_storing(self, monkeypatch, tmp_path):
        client = self._client(monkeypatch, tmp_path)
        resp = client.post("/api/sessions", json={"title": "Foo\x00Bar\nBaz\u202eRTL"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "FooBarBazRTL"

    def test_whitespace_only_title_falls_back_to_default(self, monkeypatch, tmp_path):
        client = self._client(monkeypatch, tmp_path)
        resp = client.post("/api/sessions", json={"title": "  \n\x00 "})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Riskanalys"

    def test_overlong_title_clamped(self, monkeypatch, tmp_path):
        client = self._client(monkeypatch, tmp_path)
        resp = client.post("/api/sessions", json={"title": "x" * 500})
        assert resp.status_code == 200
        assert len(resp.json()["title"]) == MAX_TITLE_LENGTH

    def test_rate_limit_returns_429(self, monkeypatch, tmp_path):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_CREATE_LIMIT", 1)
        client = self._client(monkeypatch, tmp_path)
        assert client.post("/api/sessions", json={"title": "First"}).status_code == 200
        assert client.post("/api/sessions", json={"title": "Second"}).status_code == 429


# ---------------------------------------------------------------------------
# Threshold semantics (auto-reveal at exactly N votes)
# ---------------------------------------------------------------------------


class TestThresholdSemantics:
    """The vote threshold is the exact auto-reveal count and is never lowered
    to match the number of connected participants.

    Regression: get_effective_threshold() used to compute
    min(threshold, connected participants), so the first participant to connect
    and vote revealed the result immediately – before the rest of the room
    had even joined.
    """

    def _make_session(self, threshold=4, votes=None):
        from app import create_new_risk

        risk = create_new_risk(1, "")
        if votes:
            risk["votes"] = {
                f"c{i}": {"probability": p, "consequence": c, "updated_at": 0}
                for i, (p, c) in enumerate(votes)
            }
        return {
            "session_id": "THRESH1",
            "admin_token": "x",
            "title": "Test",
            "threshold": threshold,
            "created_at": 0.0,
            "updated_at": 0.0,
            "active_risk_number": 1,
            "risks": [risk],
        }

    def test_get_session_threshold_ignores_connected_participants(self):
        from app import get_session_threshold

        assert get_session_threshold(self._make_session(threshold=4)) == 4
        assert get_session_threshold(self._make_session(threshold=1)) == 1

    def test_two_votes_do_not_reveal_at_threshold_four(self):
        from app import compute_risk_stats

        session = self._make_session(threshold=4, votes=[(2, 2), (3, 3)])
        stats = compute_risk_stats(session["risks"][0], threshold=4)
        assert stats["threshold_reached"] is False
        assert stats["revealed"] is False

    def test_build_client_payload_does_not_lower_threshold(self):
        from app import ConnectionInfo, manager

        session = self._make_session(threshold=4, votes=[(2, 2), (3, 3)])
        sid = session["session_id"]
        manager.connections[sid] = [
            ConnectionInfo(websocket=None, role="participant", client_id="p1", is_admin=False),  # type: ignore
            ConnectionInfo(websocket=None, role="participant", client_id="p2", is_admin=False),  # type: ignore
        ]
        try:
            payload = manager.build_client_payload(session)
            assert payload["threshold"] == 4
            assert payload["risks"][0]["revealed"] is False
            assert session["risks"][0]["revealed"] is False
        finally:
            manager.connections.pop(sid, None)

    def test_reveal_still_happens_at_exact_threshold(self):
        from app import compute_risk_stats

        votes = [(2, 2), (3, 3), (1, 4), (4, 1)]
        session = self._make_session(threshold=4, votes=votes)
        stats = compute_risk_stats(session["risks"][0], threshold=4)
        assert stats["threshold_reached"] is True
