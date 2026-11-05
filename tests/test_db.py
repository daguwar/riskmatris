"""Tests for SQLite connection hardening (riskmatris.db)."""

import sqlite3
import time


class TestSqliteConnectionHardening:
    def test_wal_and_busy_timeout_applied(self, monkeypatch, tmp_path):
        import app as app_module
        import riskmatris.db as db

        monkeypatch.setattr(app_module, "DB_PATH", str(tmp_path / "hardening.db"))
        conn = db._connect()
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == app_module.SQLITE_BUSY_TIMEOUT_MS
        finally:
            conn.close()

    def test_busy_timeout_is_configurable(self, monkeypatch, tmp_path):
        import app as app_module
        import riskmatris.db as db

        monkeypatch.setattr(app_module, "DB_PATH", str(tmp_path / "hardening2.db"))
        monkeypatch.setattr(app_module, "SQLITE_BUSY_TIMEOUT_MS", 1234)
        conn = db._connect()
        try:
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 1234
        finally:
            conn.close()

    def test_wal_persists_on_the_database_file(self, monkeypatch, tmp_path):
        """WAL is persistent per database file: even a plain new connection sees it."""
        import app as app_module
        import riskmatris.db as db

        path = str(tmp_path / "hardening3.db")
        monkeypatch.setattr(app_module, "DB_PATH", path)
        db.init_db()
        with sqlite3.connect(path) as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    def test_save_and_load_roundtrip_still_works(self, monkeypatch, tmp_path):
        import app as app_module
        import riskmatris.db as db

        monkeypatch.setattr(app_module, "DB_PATH", str(tmp_path / "roundtrip.db"))
        db.init_db()
        now = time.time()
        session = {
            "session_id": "DBRT01",
            "admin_token": "tok",
            "title": "Roundtrip",
            "threshold": 4,
            "created_at": now,
            "updated_at": now,
            "active_risk_number": 1,
            "risks": [],
        }
        db.save_session_to_db(session)
        loaded = db.load_sessions_from_db()
        assert "DBRT01" in loaded
        assert loaded["DBRT01"]["title"] == "Roundtrip"
