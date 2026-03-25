# tests/test_http_tools.py
import pytest
from unittest.mock import MagicMock, patch


def test_check_url_ok():
    mock_resp = MagicMock(status_code=200)
    with patch("httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.get.return_value = mock_resp
        from tools.http_tools import check_url
        result = check_url("https://example.com")
    assert result["ok"] is True
    assert result["status_code"] == 200
    assert result["error"] is None


def test_check_url_wrong_status():
    mock_resp = MagicMock(status_code=404)
    with patch("httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.get.return_value = mock_resp
        from tools.http_tools import check_url
        result = check_url("https://example.com")
    assert result["ok"] is False
    assert result["status_code"] == 404


def test_check_url_exception():
    with patch("httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.get.side_effect = Exception("connection refused")
        from tools.http_tools import check_url
        result = check_url("https://bad.example.com")
    assert result["ok"] is False
    assert "connection refused" in result["error"]


def test_smoke_test_multiple_urls():
    mock_resp_ok = MagicMock(status_code=200)
    mock_resp_fail = MagicMock(status_code=503)
    responses = [mock_resp_ok, mock_resp_fail]

    call_count = 0

    def side_effect(url, **kwargs):
        nonlocal call_count
        resp = responses[call_count % len(responses)]
        call_count += 1
        return resp

    with patch("httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.get.side_effect = side_effect
        from tools.http_tools import smoke_test
        results = smoke_test(["https://a.com", "https://b.com"])

    assert results[0]["ok"] is True
    assert results[1]["ok"] is False
    assert results[0]["url"] == "https://a.com"
    assert results[1]["url"] == "https://b.com"
