"""Tests for the session-creation rate limiter (riskmatris.rate_limit)."""

from app import check_session_create_rate, cleanup_rate_limit_log

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
