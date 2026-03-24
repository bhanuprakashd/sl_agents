# tests/test_supervisor.py
import sqlite3, pytest
from pathlib import Path
from tools.supervisor_db import init_supervisor_tables, SUPERVISOR_DB_PATH

def test_init_creates_all_tables(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr("tools.supervisor_db.SUPERVISOR_DB_PATH", db)
    init_supervisor_tables()
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert tables >= {
        "supervisor_runs", "supervisor_events",
        "supervisor_circuit_breakers", "supervisor_dlq",
        "supervisor_output_validity"
    }
    conn.close()
