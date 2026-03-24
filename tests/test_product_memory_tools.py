import pytest
import uuid
from tools.product_memory_tools import (
    save_product_state,
    recall_product_state,
    init_product_db,
)

@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test_products.db")
    monkeypatch.setenv("PRODUCT_DB_PATH", db)
    init_product_db()

def test_save_and_recall_basic():
    pid = str(uuid.uuid4())
    save_product_state(pid, product_name="TestApp", status="running")
    state = recall_product_state(pid)
    assert state["product_name"] == "TestApp"
    assert state["status"] == "running"

def test_partial_update():
    pid = str(uuid.uuid4())
    save_product_state(pid, product_name="App", status="running")
    save_product_state(pid, backend_url="https://api.example.com")
    state = recall_product_state(pid)
    assert state["product_name"] == "App"
    assert state["backend_url"] == "https://api.example.com"

def test_recall_missing_returns_none():
    state = recall_product_state("nonexistent-id")
    assert state is None

def test_save_json_fields():
    pid = str(uuid.uuid4())
    prd = {"product_name": "X", "features": ["f1", "f2"]}
    save_product_state(pid, prd=prd)
    state = recall_product_state(pid)
    assert state["prd"]["features"] == ["f1", "f2"]
