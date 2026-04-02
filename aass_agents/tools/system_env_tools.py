# aass_agents/tools/system_env_tools.py
"""
System Environment Detection — scans the local machine for installed
runtimes, databases, package managers, and Docker so the architect agent
can pick a stack that actually works.
"""
import json
import platform
import shutil
import subprocess
import re
from typing import Any

from google.adk.tools import ToolContext


# ── Binary → version-flag mapping ───────────────────────────────────────────

_RUNTIMES: dict[str, dict[str, str]] = {
    "python":  {"bin": "python", "alt": "python3", "flag": "--version"},
    "node":    {"bin": "node",                      "flag": "--version"},
    "go":      {"bin": "go",                        "flag": "version"},
    "java":    {"bin": "java",                      "flag": "-version"},
    "rust":    {"bin": "rustc",                     "flag": "--version"},
    "ruby":    {"bin": "ruby",                      "flag": "--version"},
    "php":     {"bin": "php",                       "flag": "--version"},
    "dotnet":  {"bin": "dotnet",                    "flag": "--version"},
}

_DATABASES: dict[str, str] = {
    "postgresql": "psql",
    "mysql":      "mysql",
    "redis":      "redis-server",
    "mongodb":    "mongod",
    "supabase_cli": "supabase",
}

_PKG_MANAGERS: dict[str, dict[str, str]] = {
    "npm":      {"bin": "npm",      "flag": "--version"},
    "yarn":     {"bin": "yarn",     "flag": "--version"},
    "pnpm":     {"bin": "pnpm",     "flag": "--version"},
    "pip":      {"bin": "pip",      "flag": "--version"},
    "cargo":    {"bin": "cargo",    "flag": "--version"},
    "composer": {"bin": "composer", "flag": "--version"},
}

_SEMVER_RE = re.compile(r"(\d+\.\d+[\.\d]*)")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _which(name: str) -> str | None:
    """Find binary on PATH."""
    return shutil.which(name)


def _get_version(binary_path: str, flag: str) -> str | None:
    """Run `binary flag` and extract a version string."""
    try:
        result = subprocess.run(
            [binary_path, flag],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = (result.stdout or "") + (result.stderr or "")
        match = _SEMVER_RE.search(output)
        if match:
            return match.group(1)
        # If no semver found and exit code was non-zero, treat as not working
        if result.returncode != 0:
            return None
        return output.strip().split("\n")[0][:80] or None
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return None


def _check_runtime(name: str, spec: dict[str, str]) -> dict[str, Any]:
    """Check a runtime binary, trying alt name if primary not found."""
    path = _which(spec["bin"])
    if not path and "alt" in spec:
        path = _which(spec["alt"])
    if not path:
        return {"installed": False, "version": None, "path": None}
    version = _get_version(path, spec["flag"])
    return {"installed": True, "version": version, "path": path}


def _check_docker() -> dict[str, Any]:
    """Check Docker and Docker Compose availability."""
    docker_path = _which("docker")
    if not docker_path:
        return {"installed": False, "compose": False}
    # Check compose (v2 plugin)
    compose = False
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True, text=True, timeout=5,
        )
        compose = result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        pass
    # Fallback: v1 standalone
    if not compose:
        compose = _which("docker-compose") is not None
    return {"installed": True, "compose": compose}


def _build_constraints_summary(env: dict) -> str:
    """Build a human-readable constraints summary for the architect."""
    available = []
    fallbacks = []

    # Runtimes
    for name, info in env["runtimes"].items():
        if info["installed"]:
            v = info["version"] or ""
            available.append(f"{name} {v}".strip())

    # Package managers
    for name, info in env["package_managers"].items():
        if info["installed"]:
            available.append(name)

    # Databases
    for name, info in env["databases"].items():
        if info["installed"]:
            available.append(name)

    if not env["databases"]["postgresql"]["installed"]:
        fallbacks.append("No PostgreSQL → use SQLite")
    if not env["databases"]["mysql"]["installed"]:
        fallbacks.append("No MySQL → use SQLite")
    if not env["databases"]["redis"]["installed"]:
        fallbacks.append("No Redis → skip Celery/BullMQ, use built-in async")
    if not env["docker"]["installed"]:
        fallbacks.append("No Docker → all services must run natively")

    parts = [f"Available: {', '.join(available)}."]
    if fallbacks:
        parts.append("Fallbacks: " + "; ".join(fallbacks) + ".")
    return " ".join(parts)


# ── ADK FunctionTools ───────────────────────────────────────────────────────

def detect_system_environment() -> str:
    """Scan the local machine for installed runtimes, databases, package
    managers, and Docker. Returns a JSON report of what is available.
    Call this during setup to inform the architect agent."""

    env: dict[str, Any] = {
        "os": {
            "platform": platform.system().lower(),
            "version": platform.version(),
            "arch": platform.machine(),
        },
        "runtimes": {},
        "databases": {},
        "package_managers": {},
        "docker": {},
    }

    # Runtimes
    for name, spec in _RUNTIMES.items():
        env["runtimes"][name] = _check_runtime(name, spec)

    # Databases (binary presence only, no version needed)
    for name, binary in _DATABASES.items():
        path = _which(binary)
        env["databases"][name] = {"installed": path is not None, "binary": binary}
    # SQLite is always available (Python built-in)
    env["databases"]["sqlite"] = {"installed": True, "note": "built-in with Python"}

    # Package managers
    for name, spec in _PKG_MANAGERS.items():
        path = _which(spec["bin"])
        if path:
            version = _get_version(path, spec["flag"])
            env["package_managers"][name] = {"installed": True, "version": version}
        else:
            env["package_managers"][name] = {"installed": False, "version": None}

    # Docker
    env["docker"] = _check_docker()

    # Summary
    env["constraints_summary"] = _build_constraints_summary(env)

    return json.dumps(env, indent=2)


def get_environment_summary(tool_context: ToolContext) -> str:
    """Read the system environment report from session state (saved by
    setup_agent). Returns a concise summary of what is installed and what
    fallbacks to use. Call this before selecting a tech stack."""

    raw = tool_context.state.get("system_environment")
    if not raw:
        return (
            "WARNING: No system environment data in state. "
            "Assume minimal environment: Python + SQLite only. "
            "Do NOT use PostgreSQL, Redis, Docker, or any external service."
        )

    try:
        env = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return "WARNING: Could not parse environment data. Assume SQLite only."

    lines = [env.get("constraints_summary", "No summary available."), ""]

    # Detailed breakdown
    lines.append("INSTALLED RUNTIMES:")
    for name, info in env.get("runtimes", {}).items():
        if info.get("installed"):
            lines.append(f"  ✓ {name} {info.get('version', '')}")

    lines.append("\nINSTALLED DATABASES:")
    for name, info in env.get("databases", {}).items():
        if info.get("installed"):
            lines.append(f"  ✓ {name}")

    lines.append("\nNOT AVAILABLE (must use fallbacks):")
    for name, info in env.get("databases", {}).items():
        if not info.get("installed"):
            lines.append(f"  ✗ {name}")
    if not env.get("docker", {}).get("installed"):
        lines.append("  ✗ docker")

    return "\n".join(lines)
