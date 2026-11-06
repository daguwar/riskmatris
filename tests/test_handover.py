"""Tests for one-time admin handover tokens and their endpoints (issue #12)."""


class TestHandoverTokens:
    def test_valid_token(self):
        from app import consume_handover_token, create_handover_token

        token = create_handover_token("ABC123")
        assert consume_handover_token(token, "ABC123") is True

    def test_token_is_single_use(self):
        from app import consume_handover_token, create_handover_token

        token = create_handover_token("ABC123")
        assert consume_handover_token(token, "ABC123") is True
        assert consume_handover_token(token, "ABC123") is False

    def test_token_for_wrong_session_is_burned(self):
        from app import consume_handover_token, create_handover_token

        token = create_handover_token("ABC123")
        assert consume_handover_token(token, "OTHER1") is False
        assert consume_handover_token(token, "ABC123") is False

    def test_expired_token_rejected(self, monkeypatch):
        import time as time_module

        import app as app_module
        from app import consume_handover_token, create_handover_token

        token = create_handover_token("ABC123")
        app_module.HANDOVER_TOKENS[token]["expires_at"] = time_module.time() - 1
        assert consume_handover_token(token, "ABC123") is False

    def test_unknown_token_rejected(self):
        from app import consume_handover_token

        assert consume_handover_token("does-not-exist", "ABC123") is False


class TestHandoverEndpoints:
    def test_create_requires_admin_token(self, add_session, test_client):
        sid = "HOVER01"
        add_session(sid, admin_token="secret")
        assert test_client.post(f"/api/sessions/{sid}/admin-handover").status_code == 401
        assert (
            test_client.post(f"/api/sessions/{sid}/admin-handover", headers={"X-Admin-Token": "wrong"}).status_code
            == 401
        )
        assert (
            test_client.post("/api/sessions/NOPE00/admin-handover", headers={"X-Admin-Token": "x"}).status_code == 404
        )
        resp = test_client.post(f"/api/sessions/{sid}/admin-handover", headers={"X-Admin-Token": "secret"})
        assert resp.status_code == 200
        assert resp.json()["ticket"]
        assert resp.json()["expires_in"] > 0

    def test_consume_returns_admin_token_and_is_single_use(self, add_session, test_client):
        sid = "HOVER02"
        session = add_session(sid, admin_token="secret")
        ticket = test_client.post(f"/api/sessions/{sid}/admin-handover", headers={"X-Admin-Token": "secret"}).json()[
            "ticket"
        ]
        resp = test_client.post(f"/api/sessions/{sid}/consume-handover", json={"token": ticket})
        assert resp.status_code == 200
        assert resp.json()["admin_token"] == session["admin_token"] == "secret"
        # Replay is rejected
        assert test_client.post(f"/api/sessions/{sid}/consume-handover", json={"token": ticket}).status_code == 401

    def test_consume_rejects_garbage_and_unknown_session(self, add_session, test_client):
        sid = "HOVER03"
        add_session(sid)
        assert test_client.post(f"/api/sessions/{sid}/consume-handover", json={"token": "garbage"}).status_code == 401
        assert test_client.post("/api/sessions/NOPE00/consume-handover", json={"token": "x"}).status_code == 404
