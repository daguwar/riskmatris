"""Unit tests for WebSocket action handlers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from riskmatris.session import create_new_risk
from riskmatris.ws_actions import (
    handle_delete_risk,
    handle_lock_risk,
    handle_next_risk,
    handle_reset_votes,
    handle_reveal_now,
    handle_select_risk,
    handle_set_final_cell,
    handle_set_label,
    handle_set_qr_visible,
    handle_set_threshold,
    handle_set_title,
    handle_unlock_risk,
    handle_vote,
)
from riskmatris.ws_manager import ConnectionInfo


@pytest.fixture
def mock_conn():
    ws = MagicMock()
    ws.send_json = AsyncMock()
    return ConnectionInfo(websocket=ws, role="participant", client_id="test_client", is_admin=False)


@pytest.fixture
def mock_admin_conn():
    ws = MagicMock()
    ws.send_json = AsyncMock()
    return ConnectionInfo(websocket=ws, role="admin", client_id="admin_client", is_admin=True)


@pytest.fixture
def test_session():
    risk = create_new_risk(1, "Test Risk")
    return {
        "session_id": "TESTWS",
        "admin_token": "token123",
        "title": "Initial Title",
        "threshold": 4,
        "created_at": 0.0,
        "updated_at": 0.0,
        "active_risk_number": 1,
        "risks": [risk],
    }


@pytest.mark.asyncio
async def test_handle_vote_valid(test_session, mock_conn):
    active_risk = test_session["risks"][0]
    msg = {"action": "vote", "probability": 3, "consequence": 2}
    result = await handle_vote(test_session, active_risk, msg, mock_conn)

    assert result is True
    assert "test_client" in active_risk["votes"]
    assert active_risk["votes"]["test_client"]["probability"] == 3
    assert active_risk["votes"]["test_client"]["consequence"] == 2
    assert active_risk["revealed"] is False  # 1 vote < threshold 4


@pytest.mark.asyncio
async def test_handle_vote_reaches_threshold(test_session, mock_conn):
    test_session["threshold"] = 1
    active_risk = test_session["risks"][0]
    msg = {"action": "vote", "probability": 2, "consequence": 4}
    result = await handle_vote(test_session, active_risk, msg, mock_conn)

    assert result is True
    assert active_risk["revealed"] is True


@pytest.mark.asyncio
async def test_handle_vote_invalid_bounds(test_session, mock_conn):
    active_risk = test_session["risks"][0]
    msg = {"action": "vote", "probability": 5, "consequence": 2}
    result = await handle_vote(test_session, active_risk, msg, mock_conn)

    assert result is False
    mock_conn.websocket.send_json.assert_awaited_once_with(
        {"type": "error", "message": "Sannolikhet och Konsekvens måste vara heltal 1–4."}
    )


@pytest.mark.asyncio
async def test_handle_vote_locked_risk(test_session, mock_conn):
    active_risk = test_session["risks"][0]
    active_risk["locked"] = True
    msg = {"action": "vote", "probability": 2, "consequence": 2}
    result = await handle_vote(test_session, active_risk, msg, mock_conn)

    assert result is False
    mock_conn.websocket.send_json.assert_awaited_once_with(
        {"type": "error", "message": "Denna risk är låst – röstning ej möjlig."}
    )


@pytest.mark.asyncio
async def test_handle_reveal_now(test_session, mock_admin_conn):
    active_risk = test_session["risks"][0]
    result = await handle_reveal_now(test_session, active_risk, {}, mock_admin_conn)
    assert result is True
    assert active_risk["revealed"] is True


@pytest.mark.asyncio
async def test_handle_set_label(test_session, mock_admin_conn):
    active_risk = test_session["risks"][0]
    msg = {"action": "set_label", "number": 1, "label": "Ny etikett"}
    result = await handle_set_label(test_session, active_risk, msg, mock_admin_conn)
    assert result is True
    assert active_risk["label"] == "Ny etikett"


@pytest.mark.asyncio
async def test_handle_set_title(test_session, mock_admin_conn):
    active_risk = test_session["risks"][0]
    msg = {"action": "set_title", "title": "Uppdaterad Titel"}
    result = await handle_set_title(test_session, active_risk, msg, mock_admin_conn)
    assert result is True
    assert test_session["title"] == "Uppdaterad Titel"

    # Empty title should fail
    bad_msg = {"action": "set_title", "title": "   "}
    bad_result = await handle_set_title(test_session, active_risk, bad_msg, mock_admin_conn)
    assert bad_result is False


@pytest.mark.asyncio
async def test_handle_set_threshold(test_session, mock_admin_conn):
    active_risk = test_session["risks"][0]
    msg = {"action": "set_threshold", "threshold": 8}
    result = await handle_set_threshold(test_session, active_risk, msg, mock_admin_conn)
    assert result is True
    assert test_session["threshold"] == 8

    # Invalid threshold
    bad_msg = {"action": "set_threshold", "threshold": 0}
    bad_result = await handle_set_threshold(test_session, active_risk, bad_msg, mock_admin_conn)
    assert bad_result is False


@pytest.mark.asyncio
async def test_handle_lock_and_unlock_risk(test_session, mock_admin_conn):
    active_risk = test_session["risks"][0]
    lock_msg = {"action": "lock_risk", "probability": 3, "consequence": 4}
    res = await handle_lock_risk(test_session, active_risk, lock_msg, mock_admin_conn)
    assert res is True
    assert active_risk["locked"] is True
    assert active_risk["final_probability"] == 3
    assert active_risk["final_consequence"] == 4

    unlock_msg = {"action": "unlock_risk"}
    res_unlock = await handle_unlock_risk(test_session, active_risk, unlock_msg, mock_admin_conn)
    assert res_unlock is True
    assert active_risk["locked"] is False


@pytest.mark.asyncio
async def test_handle_set_final_cell(test_session, mock_admin_conn):
    active_risk = test_session["risks"][0]
    msg = {"action": "set_final_cell", "probability": 2, "consequence": 3, "lock": True}
    res = await handle_set_final_cell(test_session, active_risk, msg, mock_admin_conn)
    assert res is True
    assert active_risk["final_probability"] == 2
    assert active_risk["final_consequence"] == 3
    assert active_risk["locked"] is True


@pytest.mark.asyncio
async def test_handle_next_risk(test_session, mock_admin_conn):
    active_risk = test_session["risks"][0]
    msg = {"action": "next_risk", "label": "Andra risken", "auto_lock": False}
    res = await handle_next_risk(test_session, active_risk, msg, mock_admin_conn)
    assert res is True
    assert len(test_session["risks"]) == 2
    assert test_session["active_risk_number"] == 2
    assert test_session["risks"][1]["number"] == 2
    assert test_session["risks"][1]["label"] == "Andra risken"


@pytest.mark.asyncio
async def test_handle_select_risk(test_session, mock_admin_conn):
    active_risk = test_session["risks"][0]
    # Add a second risk first
    test_session["risks"].append(create_new_risk(2, "Risk 2"))

    msg = {"action": "select_risk", "number": 2}
    res = await handle_select_risk(test_session, active_risk, msg, mock_admin_conn)
    assert res is True
    assert test_session["active_risk_number"] == 2

    # Nonexistent risk
    bad_msg = {"action": "select_risk", "number": 99}
    bad_res = await handle_select_risk(test_session, active_risk, bad_msg, mock_admin_conn)
    assert bad_res is False


@pytest.mark.asyncio
async def test_handle_reset_votes(test_session, mock_admin_conn):
    active_risk = test_session["risks"][0]
    active_risk["votes"] = {"c1": {"probability": 2, "consequence": 2, "updated_at": 0}}
    active_risk["revealed"] = True
    active_risk["locked"] = True
    active_risk["final_probability"] = 2
    active_risk["final_consequence"] = 2

    res = await handle_reset_votes(test_session, active_risk, {}, mock_admin_conn)
    assert res is True
    assert active_risk["votes"] == {}
    assert active_risk["revealed"] is False
    assert active_risk["locked"] is False
    assert active_risk["final_probability"] is None
    assert active_risk["final_consequence"] is None


@pytest.mark.asyncio
async def test_handle_delete_risk(test_session, mock_admin_conn):
    active_risk = test_session["risks"][0]
    # Only 1 risk: cannot delete
    res = await handle_delete_risk(test_session, active_risk, {"number": 1}, mock_admin_conn)
    assert res is False
    assert len(test_session["risks"]) == 1

    # Add a second risk and delete one
    risk2 = create_new_risk(2, "Risk 2")
    test_session["risks"].append(risk2)
    test_session["active_risk_number"] = 2

    res_del = await handle_delete_risk(test_session, risk2, {"number": 2}, mock_admin_conn)
    assert res_del is True
    assert len(test_session["risks"]) == 1
    assert test_session["active_risk_number"] == 1


@pytest.mark.asyncio
async def test_handle_set_qr_visible(test_session, mock_admin_conn):
    active_risk = test_session["risks"][0]

    res_show = await handle_set_qr_visible(test_session, active_risk, {"visible": True}, mock_admin_conn)
    assert res_show is True
    assert test_session["qr_visible"] is True

    res_hide = await handle_set_qr_visible(test_session, active_risk, {"visible": False}, mock_admin_conn)
    assert res_hide is True
    assert test_session["qr_visible"] is False

    # Missing flag defaults to showing the overlay
    res_default = await handle_set_qr_visible(test_session, active_risk, {}, mock_admin_conn)
    assert res_default is True
    assert test_session["qr_visible"] is True
