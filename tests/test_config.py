"""Tests for configuration constants and env parsing (riskmatris.config)."""

from app import CONSEQUENCE_LABELS, PROBABILITY_LABELS

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

    def test_configured_defaults_are_consistent(self):
        import app as app_module

        assert app_module.SESSION_TTL_HOURS >= 1
        assert app_module.SESSION_TTL_SECONDS == app_module.SESSION_TTL_HOURS * 3600
        assert app_module.SESSION_CLEANUP_INTERVAL >= 60
        assert app_module.SESSION_CREATE_LIMIT >= 1
        assert app_module.WS_MAX_CONNECTIONS_PER_SESSION >= 2
        assert app_module.WS_MAX_MESSAGE_BYTES >= 256
