"""Tests for configuration constants and env parsing (riskmatris.config)."""

# Note: user-facing P/C labels moved to the i18n dictionaries (issue #9).

# ---------------------------------------------------------------------------
# Environment variable parsing (safe fallback)
# ---------------------------------------------------------------------------


class TestParseEnvInt:
    """Bare int() would crash at startup on non-numeric values, and a zero or
    negative limit could silently disable a safety mechanism or wedge the app
    in a busy loop – invalid values must fall back to the default with a
    warning."""

    def test_valid_values(self, monkeypatch):
        from app import _parse_env_int

        monkeypatch.setenv("TEST_ENV_INT", "6")
        assert _parse_env_int("TEST_ENV_INT", 48, min_value=1) == 6
        monkeypatch.setenv("TEST_ENV_INT", "1")
        assert _parse_env_int("TEST_ENV_INT", 48, min_value=1) == 1

    def test_unset_returns_default(self, monkeypatch):
        from app import _parse_env_int

        monkeypatch.delenv("TEST_ENV_INT", raising=False)
        assert _parse_env_int("TEST_ENV_INT", 48, min_value=1) == 48

    def test_invalid_falls_back_with_warning(self, monkeypatch, caplog):
        import logging

        from app import _parse_env_int

        for bad in ("abc", "", "3.5", "0", "-5"):
            monkeypatch.setenv("TEST_ENV_INT", bad)
            with caplog.at_level(logging.WARNING, logger="riskmatris"):
                assert _parse_env_int("TEST_ENV_INT", 48, min_value=1) == 48
        assert any("TEST_ENV_INT" in rec.message for rec in caplog.records)

    def test_above_max_falls_back(self, monkeypatch):
        from app import _parse_env_int

        monkeypatch.setenv("TEST_ENV_INT", "999999")
        assert _parse_env_int("TEST_ENV_INT", 100, min_value=1, max_value=1000) == 100


# ---------------------------------------------------------------------------
# Boolean environment variable parsing (safe fallback)
# ---------------------------------------------------------------------------


class TestParseEnvBool:
    def test_true_values(self, monkeypatch):
        from app import _parse_env_bool

        for v in ("1", "true", "TRUE", "Yes", "on"):
            monkeypatch.setenv("TEST_ENV_BOOL", v)
            assert _parse_env_bool("TEST_ENV_BOOL", False) is True

    def test_false_values(self, monkeypatch):
        from app import _parse_env_bool

        for v in ("0", "false", "FALSE", "No", "off"):
            monkeypatch.setenv("TEST_ENV_BOOL", v)
            assert _parse_env_bool("TEST_ENV_BOOL", True) is False

    def test_unset_returns_default(self, monkeypatch):
        from app import _parse_env_bool

        monkeypatch.delenv("TEST_ENV_BOOL", raising=False)
        assert _parse_env_bool("TEST_ENV_BOOL", True) is True
        assert _parse_env_bool("TEST_ENV_BOOL", False) is False

    def test_invalid_falls_back_with_warning(self, monkeypatch, caplog):
        import logging

        from app import _parse_env_bool

        monkeypatch.setenv("TEST_ENV_BOOL", "kanske")
        with caplog.at_level(logging.WARNING, logger="riskmatris"):
            assert _parse_env_bool("TEST_ENV_BOOL", False) is False
        assert any("TEST_ENV_BOOL" in rec.message for rec in caplog.records)

    def test_configured_defaults_are_consistent(self):
        import app as app_module

        assert app_module.ENABLE_DOCS is False  # secure by default (A05-1)
        assert app_module.SQLITE_BUSY_TIMEOUT_MS >= 0
        assert app_module.SESSION_TTL_HOURS >= 1
        assert app_module.SESSION_TTL_SECONDS == app_module.SESSION_TTL_HOURS * 3600
        assert app_module.SESSION_CLEANUP_INTERVAL >= 60
        assert app_module.SESSION_CREATE_LIMIT >= 1
        assert app_module.SESSION_READ_LIMIT >= 1
        assert app_module.SESSION_READ_WINDOW_SECONDS >= 1
        assert 6 <= app_module.SESSION_CODE_LENGTH <= 16
        assert app_module.WS_MAX_CONNECTIONS_PER_SESSION >= 2
        assert app_module.WS_MAX_CONNECTIONS_PER_IP >= 1
        assert app_module.WS_MAX_CONNECTIONS_TOTAL >= 10
        assert app_module.WS_MESSAGE_RATE_LIMIT >= 1
        assert app_module.WS_MESSAGE_RATE_WINDOW_SECONDS >= 1
        assert app_module.WS_MAX_MESSAGE_BYTES >= 256


# ---------------------------------------------------------------------------
# Structured (JSON) logging
# ---------------------------------------------------------------------------


class TestJsonFormatter:
    def test_output_is_parseable_json_with_expected_fields(self):
        import json
        import logging

        from riskmatris.config import JsonFormatter

        record = logging.LogRecord(
            name="riskmatris",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Session %s created",
            args=("ABC123",),
            exc_info=None,
        )
        line = JsonFormatter().format(record)
        payload = json.loads(line)
        assert payload["level"] == "INFO"
        assert payload["logger"] == "riskmatris"
        assert payload["message"] == "Session ABC123 created"
        assert "ts" in payload

    def test_exception_info_included(self):
        import json
        import logging

        from riskmatris.config import JsonFormatter

        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="riskmatris",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="failed",
                args=(),
                exc_info=sys.exc_info(),
            )
        payload = json.loads(JsonFormatter().format(record))
        assert "exc_info" in payload
        assert "ValueError" in payload["exc_info"]
