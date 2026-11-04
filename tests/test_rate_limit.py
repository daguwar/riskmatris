"""Tests for the rate limiters (riskmatris.rate_limit)."""

from app import (
    check_session_create_rate,
    check_session_read_rate,
    cleanup_rate_limit_log,
    cleanup_read_rate_limit_log,
)

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
# Read/probe rate limiting (sakerhetsrapport A01-3: session-code enumeration)
# ---------------------------------------------------------------------------


class TestSessionReadRateLimit:
    def test_allows_within_limit(self, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_READ_LOG", {})
        monkeypatch.setattr(app_module, "SESSION_READ_LIMIT", 3)
        for _ in range(3):
            assert check_session_read_rate("1.2.3.4") is True

    def test_blocks_over_limit(self, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_READ_LOG", {})
        monkeypatch.setattr(app_module, "SESSION_READ_LIMIT", 2)
        assert check_session_read_rate("1.2.3.4") is True
        assert check_session_read_rate("1.2.3.4") is True
        assert check_session_read_rate("1.2.3.4") is False

    def test_limit_is_per_ip(self, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_READ_LOG", {})
        monkeypatch.setattr(app_module, "SESSION_READ_LIMIT", 1)
        assert check_session_read_rate("1.2.3.4") is True
        assert check_session_read_rate("1.2.3.4") is False
        assert check_session_read_rate("5.6.7.8") is True

    def test_window_expiry_allows_again(self, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_READ_LOG", {})
        monkeypatch.setattr(app_module, "SESSION_READ_LIMIT", 1)
        monkeypatch.setattr(app_module, "SESSION_READ_WINDOW_SECONDS", 60)
        # One old, expired entry plus a fresh "now" far in the future
        import riskmatris.rate_limit as rl

        monkeypatch.setattr(app_module, "SESSION_READ_LOG", {"1.2.3.4": [0.0]})
        assert rl.check_rate(app_module.SESSION_READ_LOG, "1.2.3.4", 1, 60, now=120.0) is True

    def test_cleanup_read_log_drops_stale_entries(self, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_READ_LOG", {"1.2.3.4": [0.0]})
        cleanup_read_rate_limit_log()
        assert app_module.SESSION_READ_LOG == {}

    def test_cleanup_read_log_keeps_fresh_entries(self, monkeypatch):
        import time as time_module

        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_READ_LOG", {"1.2.3.4": [time_module.time()]})
        cleanup_read_rate_limit_log()
        assert "1.2.3.4" in app_module.SESSION_READ_LOG

    def test_create_and_read_logs_are_separate(self, monkeypatch):
        """Hitting the create limit must not consume read budget and vice versa."""
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_CREATE_LOG", {})
        monkeypatch.setattr(app_module, "SESSION_READ_LOG", {})
        monkeypatch.setattr(app_module, "SESSION_CREATE_LIMIT", 1)
        monkeypatch.setattr(app_module, "SESSION_READ_LIMIT", 1)
        assert check_session_create_rate("1.2.3.4") is True
        assert check_session_create_rate("1.2.3.4") is False
        assert check_session_read_rate("1.2.3.4") is True
