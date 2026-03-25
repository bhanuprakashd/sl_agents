# tests/test_github_tools.py
import base64
from unittest.mock import MagicMock, patch


def test_create_repo_sends_correct_payload(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"full_name": "user/myapp", "html_url": "https://github.com/user/myapp"}
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value = mock_resp
        from tools.github_tools import create_repo
        result = create_repo("myapp", "A test app")

    assert result["full_name"] == "user/myapp"
    call_kwargs = mock_client.post.call_args
    assert call_kwargs.kwargs["json"]["name"] == "myapp"
    assert call_kwargs.kwargs["json"]["auto_init"] is True


def test_push_file_creates_new_file(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    mock_get = MagicMock(status_code=404)
    mock_put = MagicMock()
    mock_put.json.return_value = {"content": {"path": "README.md"}}
    mock_put.raise_for_status.return_value = None

    with patch("httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.get.return_value = mock_get
        mock_client.put.return_value = mock_put
        from tools.github_tools import push_file
        result = push_file("user/repo", "README.md", "hello", "init")

    put_payload = mock_client.put.call_args.kwargs["json"]
    assert base64.b64decode(put_payload["content"]).decode() == "hello"
    assert "sha" not in put_payload


def test_push_file_updates_existing_file(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    mock_get = MagicMock(status_code=200)
    mock_get.json.return_value = {"sha": "abc123"}
    mock_put = MagicMock()
    mock_put.json.return_value = {"content": {"path": "README.md"}}
    mock_put.raise_for_status.return_value = None

    with patch("httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.get.return_value = mock_get
        mock_client.put.return_value = mock_put
        from tools.github_tools import push_file
        push_file("user/repo", "README.md", "updated", "update")

    put_payload = mock_client.put.call_args.kwargs["json"]
    assert put_payload["sha"] == "abc123"
