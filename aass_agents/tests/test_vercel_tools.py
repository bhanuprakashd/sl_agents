# tests/test_vercel_tools.py
from unittest.mock import MagicMock, patch


def test_create_project(monkeypatch):
    monkeypatch.setenv("VERCEL_TOKEN", "test-token")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": "prj_abc", "name": "myapp"}
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value = mock_resp
        from tools.vercel_tools import vercel_create_project
        result = vercel_create_project("myapp")

    assert result["id"] == "prj_abc"
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["name"] == "myapp"
    assert payload["framework"] == "nextjs"


def test_get_deployment_url_returns_https(monkeypatch):
    monkeypatch.setenv("VERCEL_TOKEN", "test-token")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"deployments": [{"url": "myapp.vercel.app"}]}
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.get.return_value = mock_resp
        from tools.vercel_tools import get_deployment_url
        url = get_deployment_url("prj_abc")

    assert url == "https://myapp.vercel.app"


def test_get_deployment_url_empty(monkeypatch):
    monkeypatch.setenv("VERCEL_TOKEN", "test-token")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"deployments": []}
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.get.return_value = mock_resp
        from tools.vercel_tools import get_deployment_url
        url = get_deployment_url("prj_abc")

    assert url == ""
