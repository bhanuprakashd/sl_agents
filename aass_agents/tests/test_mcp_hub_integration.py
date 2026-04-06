"""Test MCP hub config is valid and consistent."""
import yaml
import pytest
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "agents/_shared/mcp_hub_config.yaml"
LOADER_PATH = Path(__file__).parent.parent / "tools/dynamic_skill_loader.py"


@pytest.fixture
def config():
    return yaml.safe_load(CONFIG_PATH.read_text())


@pytest.fixture
def servers(config):
    return config["servers"]


class TestMcpHubConfig:
    def test_yaml_parses(self):
        """Config file is valid YAML."""
        config = yaml.safe_load(CONFIG_PATH.read_text())
        assert "servers" in config

    def test_minimum_server_count(self, servers):
        """We should have at least 90 servers (all verified on npm/PyPI)."""
        assert len(servers) >= 90, f"Only {len(servers)} servers found"

    def test_no_duplicate_capabilities(self, servers):
        """Each capability tag must be unique."""
        caps = [s["capability"] for s in servers]
        dupes = [c for c in caps if caps.count(c) > 1]
        assert not dupes, f"Duplicate capabilities: {set(dupes)}"

    def test_no_duplicate_names(self, servers):
        """Each server name must be unique."""
        names = [s["name"] for s in servers]
        dupes = [n for n in names if names.count(n) > 1]
        assert not dupes, f"Duplicate names: {set(dupes)}"

    def test_required_fields(self, servers):
        """Each server must have name, capability, description, connection_type."""
        required = {"name", "capability", "description", "connection_type"}
        for s in servers:
            missing = required - set(s.keys())
            assert not missing, f"Server {s.get('name', '?')} missing: {missing}"

    def test_stdio_has_command(self, servers):
        """stdio servers must have command field."""
        for s in servers:
            if s["connection_type"] == "stdio":
                assert "command" in s, f"Server {s['name']} is stdio but has no command"
                assert s["command"] in ("npx", "uvx"), f"Server {s['name']} has unknown command: {s['command']}"

    def test_http_has_url(self, servers):
        """HTTP/SSE servers must have url field."""
        for s in servers:
            if s["connection_type"] in ("http", "sse"):
                assert "url" in s, f"Server {s['name']} is {s['connection_type']} but has no url"

    def test_all_have_tool_prefix(self, servers):
        """Every server should have a tool_prefix for namespace isolation."""
        for s in servers:
            if not s.get("disabled"):
                assert "tool_prefix" in s, f"Server {s['name']} has no tool_prefix"

    def test_no_empty_descriptions(self, servers):
        """Descriptions must not be empty."""
        for s in servers:
            assert s.get("description", "").strip(), f"Server {s['name']} has empty description"


class TestDomainMcpMap:
    def test_domain_map_has_core(self):
        """Domain map must have _core entry."""
        from tools.dynamic_skill_loader import DOMAIN_MCP_MAP
        assert "_core" in DOMAIN_MCP_MAP

    def test_minimum_industries(self):
        """Should have at least 25 industry domains."""
        from tools.dynamic_skill_loader import DOMAIN_MCP_MAP
        industries = [k for k in DOMAIN_MCP_MAP if not k.startswith("_")]
        assert len(industries) >= 25, f"Only {len(industries)} industries"

    def test_general_fallback_exists(self):
        """Must have a general fallback domain."""
        from tools.dynamic_skill_loader import DOMAIN_MCP_MAP
        assert "general" in DOMAIN_MCP_MAP

    def test_detect_industry_returns_string(self):
        """detect_industry should return a string domain."""
        from tools.dynamic_skill_loader import detect_industry
        result = detect_industry("I want to build a shrimp farm management app")
        assert isinstance(result, str)
        assert result == "agriculture"

    def test_detect_industry_fallback(self):
        """Unknown requirements should return 'general'."""
        from tools.dynamic_skill_loader import detect_industry
        result = detect_industry("build me something cool")
        assert result == "general"

    def test_detect_new_industries(self):
        """New industries should be detectable."""
        from tools.dynamic_skill_loader import detect_industry
        assert detect_industry("solar panel grid management") == "energy"
        assert detect_industry("hotel booking system") == "travel"
        assert detect_industry("insurance claim processing") == "insurance"
