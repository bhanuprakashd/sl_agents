"""Tests for claude_code_tools — build_and_run and open_in_browser."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.claude_code_tools import build_and_run, open_in_browser


def test_build_and_run_returns_url(tmp_path, monkeypatch):
    """URL in Claude Code output → return 'Built and running at ...'"""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Created files.\nServer running at http://localhost:3000\n"
    mock_result.stderr = ""
    with patch("tools.claude_code_tools.shutil.which", return_value="/usr/bin/claude"), \
         patch("tools.claude_code_tools.subprocess.run", return_value=mock_result):
        result = build_and_run("test-proj", "build a hello world app")
    assert result == "Built and running at http://localhost:3000"


def test_build_and_run_no_url_returns_done(tmp_path, monkeypatch):
    """No URL in output → return 'Done. Files written to ...'"""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Created hello.py with print('hello')"
    mock_result.stderr = ""
    with patch("tools.claude_code_tools.shutil.which", return_value="/usr/bin/claude"), \
         patch("tools.claude_code_tools.subprocess.run", return_value=mock_result):
        result = build_and_run("test-script", "write a hello world python script")
    assert result == "Done. Files written to claude_works/test-script/"


def test_build_and_run_timeout(tmp_path, monkeypatch):
    """Subprocess timeout → return error string."""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    with patch("tools.claude_code_tools.shutil.which", return_value="/usr/bin/claude"), \
         patch("tools.claude_code_tools.subprocess.run",
               side_effect=subprocess.TimeoutExpired("claude", 600)):
        result = build_and_run("test-proj", "build something")
    assert result == "Error: timed out after 600s"


def test_build_and_run_creates_project_dir(tmp_path, monkeypatch):
    """Project directory is created under CLAUDE_WORKS_ROOT."""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    with patch("tools.claude_code_tools.shutil.which", return_value="/usr/bin/claude"), \
         patch("tools.claude_code_tools.subprocess.run", return_value=mock_result):
        build_and_run("my-new-project", "build something")
    assert (tmp_path / "my-new-project").is_dir()


def test_claude_cli_not_found(tmp_path, monkeypatch):
    """Missing claude binary → return helpful error."""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    with patch("tools.claude_code_tools.shutil.which", return_value=None):
        result = build_and_run("test-proj", "build something")
    assert result.startswith("Error: claude CLI not found")


def test_build_and_run_nonzero_exit(tmp_path, monkeypatch):
    """Non-zero exit code → return stderr as error."""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "Permission denied"
    with patch("tools.claude_code_tools.shutil.which", return_value="/usr/bin/claude"), \
         patch("tools.claude_code_tools.subprocess.run", return_value=mock_result):
        result = build_and_run("test-proj", "build something")
    assert result == "Error: Permission denied"


def test_open_in_browser_success():
    """Successful browser open → return 'Opened <url>'."""
    with patch("tools.claude_code_tools.webbrowser.open", return_value=True):
        result = open_in_browser("http://localhost:3000")
    assert result == "Opened http://localhost:3000"


def test_open_in_browser_exception():
    """Browser open raises → return error string."""
    with patch("tools.claude_code_tools.webbrowser.open",
               side_effect=Exception("no browser available")):
        result = open_in_browser("http://localhost:3000")
    assert result.startswith("Error:")


@pytest.mark.integration
def test_integration_hello_world(tmp_path, monkeypatch):
    """Actually runs claude CLI to write a file. Requires claude CLI + ANTHROPIC_API_KEY."""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    result = build_and_run(
        "integration-test",
        "Create a file called hello.txt containing exactly: Hello World",
    )
    assert "Error" not in result
    assert (tmp_path / "integration-test" / "hello.txt").exists()
