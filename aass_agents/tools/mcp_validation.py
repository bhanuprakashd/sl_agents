"""
MCP Validation — checks which servers are actually installable/runnable.

Usage:
    python -m tools.mcp_validation --check-all
    python -m tools.mcp_validation --check-free
    python -m tools.mcp_validation --category database
"""
import subprocess
import yaml
import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "agents/_shared/mcp_hub_config.yaml"


def check_npx_package(name: str, args: list[str]) -> dict:
    """Check if an npx package exists and is installable."""
    pkg = args[1] if len(args) > 1 else args[0]
    try:
        result = subprocess.run(
            ["npx", "-y", pkg, "--help"],
            capture_output=True, text=True, timeout=30,
        )
        return {"name": name, "package": pkg, "available": True, "exit_code": result.returncode}
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"name": name, "package": pkg, "available": False, "error": str(e)}


def check_uvx_package(name: str, args: list[str]) -> dict:
    """Check if a uvx package exists."""
    pkg = args[0]
    try:
        result = subprocess.run(
            ["uvx", pkg, "--help"],
            capture_output=True, text=True, timeout=30,
        )
        return {"name": name, "package": pkg, "available": True, "exit_code": result.returncode}
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"name": name, "package": pkg, "available": False, "error": str(e)}


def validate_all(free_only: bool = False) -> list[dict]:
    """Validate all MCP servers in config."""
    config = yaml.safe_load(CONFIG_PATH.read_text())
    results = []
    for server in config["servers"]:
        if server.get("disabled"):
            continue
        if free_only and server.get("env_keys"):
            continue
        cmd = server.get("command", "")
        args = server.get("args", [])
        if cmd == "npx":
            results.append(check_npx_package(server["name"], args))
        elif cmd == "uvx":
            results.append(check_uvx_package(server["name"], args))
    return results


def get_config_stats() -> dict:
    """Get statistics about the MCP hub config without running any servers."""
    config = yaml.safe_load(CONFIG_PATH.read_text())
    servers = config["servers"]
    total = len(servers)
    free = sum(1 for s in servers if not s.get("env_keys") and not s.get("disabled"))
    api_required = sum(1 for s in servers if s.get("env_keys") and not s.get("disabled"))
    disabled = sum(1 for s in servers if s.get("disabled"))
    capabilities = set(s["capability"] for s in servers)
    npx_count = sum(1 for s in servers if s.get("command") == "npx")
    uvx_count = sum(1 for s in servers if s.get("command") == "uvx")
    http_count = sum(1 for s in servers if s.get("connection_type") in ("http", "sse"))

    return {
        "total_servers": total,
        "free_no_key": free,
        "api_key_required": api_required,
        "disabled": disabled,
        "unique_capabilities": len(capabilities),
        "transport": {"npx": npx_count, "uvx": uvx_count, "http": http_count},
    }


if __name__ == "__main__":
    if "--stats" in sys.argv:
        stats = get_config_stats()
        print(json.dumps(stats, indent=2))
        sys.exit(0)

    free_only = "--check-free" in sys.argv
    results = validate_all(free_only=free_only)
    available = [r for r in results if r["available"]]
    missing = [r for r in results if not r["available"]]
    print(f"Available: {len(available)}/{len(results)}")
    if missing:
        print(f"Missing ({len(missing)}):")
        for m in missing:
            print(f"  {m['name']}: {m.get('error', 'unknown')}")
    print(json.dumps({"available": len(available), "total": len(results)}, indent=2))
