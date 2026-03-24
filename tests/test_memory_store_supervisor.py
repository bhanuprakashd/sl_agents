import pytest
import importlib
import sqlite3


def test_memory_store_inits_supervisor_tables(tmp_path, monkeypatch):
    """Importing memory_store should create supervisor tables in the same DB."""
    monkeypatch.setattr("tools.supervisor_db.SUPERVISOR_DB_PATH", tmp_path / "mem.db")
    # Also patch the memory_store DB_PATH to the same file
    import shared.memory_store as ms_module
    monkeypatch.setattr(ms_module, "DB_PATH", tmp_path / "mem.db")
    # Re-import to trigger _init_db
    importlib.reload(ms_module)
    conn = sqlite3.connect(tmp_path / "mem.db")
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert "supervisor_runs" in tables
