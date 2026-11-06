"""Tests for session snapshot export/import (issue #15)."""

import json


def _snapshot_payload(**overrides):
    payload = {
        "format": "riskmatris-snapshot",
        "version": 1,
        "title": "Projekt Alfa",
        "threshold": 6,
        "exported_at": "2026-11-06T10:00:00+00:00",
        "risks": [
            {
                "number": 1,
                "label": "Brandrisk",
                "revealed": True,
                "locked": True,
                "final_probability": 3,
                "final_consequence": 4,
                "votes": {"c_abc": {"probability": 3, "consequence": 4}},
            },
            {
                "number": 2,
                "label": "  ",
                "revealed": False,
                "locked": False,
                "final_probability": None,
                "final_consequence": None,
                "votes": {},
            },
        ],
    }
    payload.update(overrides)
    return payload


class TestSnapshotExport:
    def test_export_contains_state_but_never_admin_token(self, add_session, test_client):

        sid = "SNAP01"
        session = add_session(sid, admin_token="supersecret")
        risk = session["risks"][0]
        risk["label"] = "Brandrisk"
        risk["locked"] = True
        risk["revealed"] = True
        risk["final_probability"] = 3
        risk["final_consequence"] = 4
        risk["votes"] = {"c_abc": {"probability": 3, "consequence": 4, "updated_at": 0}}

        resp = test_client.get(f"/api/sessions/{sid}/snapshot.json")
        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]
        data = resp.json()
        assert data["format"] == "riskmatris-snapshot"
        assert data["version"] == 1
        assert data["title"] == "Test"
        assert data["risks"][0]["locked"] is True
        assert data["risks"][0]["final_probability"] == 3
        assert data["risks"][0]["votes"]["c_abc"]["probability"] == 3
        assert "admin_token" not in json.dumps(data)
        assert "supersecret" not in json.dumps(data)

    def test_export_unknown_session_404(self, test_client):
        assert test_client.get("/api/sessions/NOPE00/snapshot.json").status_code == 404


class TestSnapshotImport:
    def test_import_creates_session_with_placements(self, isolated_client):
        import app as app_module

        resp = isolated_client.post("/api/sessions/import", json=_snapshot_payload())
        assert resp.status_code == 200
        data = resp.json()
        sid = data["session_id"]
        assert data["title"] == "Projekt Alfa"
        assert data["threshold"] == 6
        session = app_module.SESSIONS[sid]
        assert len(session["risks"]) == 2
        r1 = session["risks"][0]
        assert r1["label"] == "Brandrisk"
        assert r1["locked"] is True and r1["revealed"] is True
        assert r1["final_probability"] == 3 and r1["final_consequence"] == 4
        # votes are NOT imported by default
        assert r1["votes"] == {}
        # whitespace-only label falls back to empty
        assert session["risks"][1]["label"] == ""
        assert session["active_risk_number"] == 1
        assert session["admin_token"] == data["admin_token"]

    def test_import_with_votes(self, isolated_client):
        import app as app_module

        resp = isolated_client.post("/api/sessions/import?include_votes=true", json=_snapshot_payload())
        assert resp.status_code == 200
        session = app_module.SESSIONS[resp.json()["session_id"]]
        assert session["risks"][0]["votes"]["c_abc"]["probability"] == 3

    def test_import_sanitizes_control_chars(self, isolated_client):
        import app as app_module

        payload = _snapshot_payload()
        payload["risks"][0]["label"] = "Brand\x00risk\n"
        resp = isolated_client.post("/api/sessions/import", json=payload)
        assert resp.status_code == 200
        session = app_module.SESSIONS[resp.json()["session_id"]]
        # control chars stripped (angle brackets are escaped at render time, as elsewhere)
        assert session["risks"][0]["label"] == "Brandrisk"

    def test_import_rejects_bad_input(self, isolated_client):
        # not JSON
        assert (
            isolated_client.post(
                "/api/sessions/import", content=b"{not json", headers={"Content-Type": "application/json"}
            ).status_code
            == 400
        )
        # wrong format marker
        assert isolated_client.post("/api/sessions/import", json=_snapshot_payload(format="other")).status_code == 400
        # wrong version
        assert isolated_client.post("/api/sessions/import", json=_snapshot_payload(version=2)).status_code == 400
        # unknown extra field (strict model)
        payload = _snapshot_payload()
        payload["evil"] = True
        assert isolated_client.post("/api/sessions/import", json=payload).status_code == 400
        # out-of-range vote
        payload = _snapshot_payload()
        payload["risks"][0]["votes"]["c_abc"]["probability"] = 9
        assert isolated_client.post("/api/sessions/import", json=payload).status_code == 400

    def test_import_size_cap(self, isolated_client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "MAX_SNAPSHOT_BYTES", 100)
        resp = isolated_client.post("/api/sessions/import", json=_snapshot_payload())
        assert resp.status_code == 413

    def test_import_is_rate_limited_like_create(self, isolated_client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_CREATE_LIMIT", 1)
        assert isolated_client.post("/api/sessions/import", json=_snapshot_payload()).status_code == 200
        assert isolated_client.post("/api/sessions/import", json=_snapshot_payload()).status_code == 429
