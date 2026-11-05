"""Tests for the Pydantic WebSocket message models (riskmatris.ws_messages)."""

import pytest
from pydantic import ValidationError

from riskmatris.ws_messages import WS_ACTION_MODELS, format_validation_error, parse_ws_message


class TestParseWsMessage:
    def test_all_thirteen_actions_have_models(self):
        assert set(WS_ACTION_MODELS) == {
            "vote",
            "reveal_now",
            "set_label",
            "set_title",
            "set_threshold",
            "lock_risk",
            "unlock_risk",
            "set_final_cell",
            "next_risk",
            "select_risk",
            "reset_votes",
            "delete_risk",
            "set_qr_visible",
        }

    def test_set_qr_visible_valid(self):
        msg = parse_ws_message("set_qr_visible", {"action": "set_qr_visible", "visible": False})
        assert msg.visible is False
        # Default: missing flag means "show"
        msg_default = parse_ws_message("set_qr_visible", {"action": "set_qr_visible"})
        assert msg_default.visible is True

    def test_vote_valid(self):
        msg = parse_ws_message("vote", {"action": "vote", "probability": 3, "consequence": 2})
        assert msg.probability == 3
        assert msg.consequence == 2

    def test_vote_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            parse_ws_message("vote", {"action": "vote", "probability": 5, "consequence": 2})

    def test_vote_missing_field_rejected(self):
        with pytest.raises(ValidationError):
            parse_ws_message("vote", {"action": "vote", "probability": 3})

    def test_numeric_string_coerced(self):
        msg = parse_ws_message("vote", {"action": "vote", "probability": "3", "consequence": "2"})
        assert msg.probability == 3

    def test_optional_fields_pass_when_absent(self):
        msg = parse_ws_message("lock_risk", {"action": "lock_risk"})
        assert msg.probability is None

    def test_invalid_optional_field_rejected(self):
        with pytest.raises(ValidationError):
            parse_ws_message("set_threshold", {"action": "set_threshold", "threshold": 0})

    def test_unknown_action_returns_none(self):
        assert parse_ws_message("not_an_action", {"action": "not_an_action"}) is None

    def test_format_validation_error_mentions_field(self):
        try:
            parse_ws_message("vote", {"action": "vote", "probability": 9, "consequence": 2})
            raise AssertionError("expected ValidationError")
        except ValidationError as exc:
            text = format_validation_error(exc)
            assert "probability" in text
            assert text.startswith("Ogiltigt meddelande")
