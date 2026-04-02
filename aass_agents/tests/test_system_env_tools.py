"""Tests for system environment detection tools."""
import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from tools.system_env_tools import (
    detect_system_environment,
    get_environment_summary,
    _check_runtime,
    _get_version,
)


class TestDetectSystemEnvironment:
    def test_returns_valid_json(self):
        result = detect_system_environment()
        data = json.loads(result)
        assert "os" in data
        assert "runtimes" in data
        assert "databases" in data
        assert "package_managers" in data
        assert "docker" in data
        assert "constraints_summary" in data

    def test_os_detection(self):
        data = json.loads(detect_system_environment())
        assert data["os"]["platform"] in ("windows", "linux", "darwin")
        assert data["os"]["arch"]
        assert data["os"]["version"]

    def test_python_always_detected(self):
        """Python must always be installed since we're running in it."""
        data = json.loads(detect_system_environment())
        assert data["runtimes"]["python"]["installed"] is True
        assert data["runtimes"]["python"]["version"] is not None

    def test_sqlite_always_installed(self):
        data = json.loads(detect_system_environment())
        assert data["databases"]["sqlite"]["installed"] is True

    def test_missing_binary_returns_false(self):
        with patch("tools.system_env_tools._which", return_value=None):
            data = json.loads(detect_system_environment())
            assert data["databases"]["postgresql"]["installed"] is False
            assert data["databases"]["redis"]["installed"] is False

    def test_subprocess_timeout_handled(self):
        with patch("tools.system_env_tools.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("cmd", 5)):
            version = _get_version("/usr/bin/node", "--version")
            assert version is None

    def test_constraints_summary_mentions_fallbacks(self):
        with patch("tools.system_env_tools._which", return_value=None):
            data = json.loads(detect_system_environment())
            summary = data["constraints_summary"]
            assert "SQLite" in summary
            assert "No PostgreSQL" in summary or "No Redis" in summary


class TestCheckRuntime:
    def test_installed_runtime(self):
        with patch("tools.system_env_tools._which", return_value="/usr/bin/python"), \
             patch("tools.system_env_tools._get_version", return_value="3.12.0"):
            result = _check_runtime("python", {"bin": "python", "flag": "--version"})
            assert result["installed"] is True
            assert result["version"] == "3.12.0"

    def test_missing_runtime(self):
        with patch("tools.system_env_tools._which", return_value=None):
            result = _check_runtime("go", {"bin": "go", "flag": "version"})
            assert result["installed"] is False

    def test_alt_binary_found(self):
        def mock_which(name):
            return "/usr/bin/python3" if name == "python3" else None

        with patch("tools.system_env_tools._which", side_effect=mock_which), \
             patch("tools.system_env_tools._get_version", return_value="3.11.0"):
            result = _check_runtime("python", {"bin": "python", "alt": "python3", "flag": "--version"})
            assert result["installed"] is True


class TestGetEnvironmentSummary:
    def _mock_context(self, state: dict) -> MagicMock:
        ctx = MagicMock()
        ctx.state = state
        return ctx

    def test_missing_state_returns_warning(self):
        ctx = self._mock_context({})
        result = get_environment_summary(ctx)
        assert "WARNING" in result
        assert "SQLite" in result

    def test_valid_state_returns_summary(self):
        env_data = {
            "constraints_summary": "Available: python 3.12, node 20. No PostgreSQL → use SQLite.",
            "runtimes": {
                "python": {"installed": True, "version": "3.12.0"},
                "node": {"installed": True, "version": "20.11.0"},
            },
            "databases": {
                "sqlite": {"installed": True},
                "postgresql": {"installed": False},
            },
            "docker": {"installed": False},
        }
        ctx = self._mock_context({"system_environment": json.dumps(env_data)})
        result = get_environment_summary(ctx)
        assert "python" in result
        assert "node" in result
        assert "postgresql" in result.lower()

    def test_corrupt_state_returns_warning(self):
        ctx = self._mock_context({"system_environment": "not-json{{"})
        result = get_environment_summary(ctx)
        assert "WARNING" in result
