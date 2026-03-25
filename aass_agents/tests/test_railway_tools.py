# tests/test_railway_tools.py
import pytest
from unittest.mock import MagicMock, patch


def test_create_project(monkeypatch):
    monkeypatch.setenv("RAILWAY_TOKEN", "test-token")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"projectCreate": {"id": "rwy_123", "name": "myapp"}}}
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value = mock_resp
        from tools.railway_tools import create_project
        result = create_project("myapp")

    assert result["id"] == "rwy_123"


def test_gql_raises_on_errors(monkeypatch):
    monkeypatch.setenv("RAILWAY_TOKEN", "test-token")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"errors": [{"message": "Not found"}]}
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value = mock_resp
        from tools.railway_tools import create_project
        with pytest.raises(RuntimeError, match="Railway GraphQL error"):
            create_project("bad")


def test_get_service_url_empty(monkeypatch):
    monkeypatch.setenv("RAILWAY_TOKEN", "test-token")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {"service": {"domains": {"serviceDomains": []}}}
    }
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value = mock_resp
        from tools.railway_tools import get_service_url
        url = get_service_url("proj", "svc")

    assert url == ""
