# tests/test_code_gen_tools.py
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def reset_client():
    import tools.code_gen_tools as cgt
    cgt._CLIENT = None
    yield
    cgt._CLIENT = None


def _mock_anthropic(text: str):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    return mock_client


def test_generate_code_returns_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mock_client = _mock_anthropic("def hello(): pass")
    with patch("anthropic.Anthropic", return_value=mock_client):
        from tools.code_gen_tools import generate_code
        result = generate_code("write hello world")
    assert result == "def hello(): pass"


def test_generate_code_uses_correct_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mock_client = _mock_anthropic("SELECT 1")
    with patch("anthropic.Anthropic", return_value=mock_client):
        from tools.code_gen_tools import generate_code
        generate_code("sql query", model="claude-haiku-4-5-20251001")
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


def test_generate_db_schema(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    expected_sql = "CREATE TABLE users (id UUID PRIMARY KEY);"
    mock_client = _mock_anthropic(expected_sql)
    with patch("anthropic.Anthropic", return_value=mock_client):
        from tools.code_gen_tools import generate_db_schema
        result = generate_db_schema({"product_name": "TestApp"})
    assert result == expected_sql
