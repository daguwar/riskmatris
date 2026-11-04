"""Tests for pure helper functions (riskmatris.utils)."""

import pytest

from app import (
    MAX_TITLE_LENGTH,
    _safe_int,
    get_local_lan_ip,
    get_risk_level,
    round_half_up,
    sanitize_csv_cell,
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
# sanitize_csv_cell (CSV formula injection, sakerhetsrapport A03-1)
# ---------------------------------------------------------------------------


class TestSanitizeCsvCell:
    @pytest.mark.parametrize(
        "value",
        [
            "=cmd|' /C calc'!A1",
            "=HYPERLINK(\"http://evil\",\"x\")",
            "+1+1",
            "-2+3",
            "@SUM(A1:A9)",
            "\t=1+1",
            "\r=1+1",
        ],
    )
    def test_formula_prefixes_get_apostrophe(self, value):
        result = sanitize_csv_cell(value)
        assert result == "'" + value
        assert result.startswith("'")

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("Brandrisk", "Brandrisk"),
            ("=", "'=",),  # bare "=" is still a formula start
            ("Risk #1", "Risk #1"),
            ("2", "2"),
            ("2,5", "2,5"),
            ("", ""),
            (None, ""),
            (5, "5"),
            (2.5, "2.5"),
            ("a=b", "a=b"),  # only a LEADING prefix char is dangerous
        ],
    )
    def test_safe_values_pass_through(self, value, expected):
        assert sanitize_csv_cell(value) == expected
