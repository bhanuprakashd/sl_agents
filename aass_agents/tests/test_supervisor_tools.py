import pytest
import tools.supervisor_db as db
from pathlib import Path


@pytest.fixture
def sdb(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.supervisor_db.SUPERVISOR_DB_PATH", tmp_path / "test.db")
    db.init_supervisor_tables()
    return db


def test_list_dlq_returns_entries(sdb, monkeypatch):
    monkeypatch.setattr("tools.supervisor_tools._db", sdb)
    sdb.push_dlq("run-10", "sales", "lead_researcher", "API down", ["pm_agent"])
    from tools.supervisor_tools import list_dlq
    result = list_dlq()
    assert result["count"] == 1
    assert result["entries"][0]["blocked_on"] == "lead_researcher"


def test_get_run_status_found(sdb, monkeypatch):
    monkeypatch.setattr("tools.supervisor_tools._db", sdb)
    sdb.create_run("run-20", "marketing", {"campaign": "Q2"})
    from tools.supervisor_tools import get_run_status
    result = get_run_status("run-20")
    assert result["found"] is True
    assert result["status"] == "pending"


def test_get_run_status_not_found(sdb, monkeypatch):
    monkeypatch.setattr("tools.supervisor_tools._db", sdb)
    from tools.supervisor_tools import get_run_status
    result = get_run_status("nonexistent")
    assert result["found"] is False
