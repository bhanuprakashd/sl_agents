"""
Dynamic Skill Loader — bridges skill_forge staged skills into the product pipeline.

When the product pipeline encounters a domain it hasn't built for before, this module:
1. Checks the staging_registry for relevant domain skills
2. Loads the skill content and injects it as context into agent prompts
3. Discovers relevant MCP servers for the domain
4. Returns a capability bundle the orchestrator can use

This is how sl_agents becomes a dynamic expert — it learns new industries via
skill_forge, then applies that knowledge automatically in future builds.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

from tools.skill_forge_db import (
    list_staged_skills_sync,
    get_staged_skill_sync,
    get_best_skill_version_sync,
    increment_production_runs_sync,
)
from tools.skill_memory import find_similar_skills, _extract_domain
from agents._shared.mcp_hub import mcp_hub

_log = logging.getLogger(__name__)

# ── Domain → MCP capability mapping ────────────────────────────────────────
# Maps industry domains to the MCP capabilities most useful for that domain.
# Any agent can call get_domain_capabilities() to get the right tools.

DOMAIN_MCP_MAP: dict[str, list[str]] = {
    # Core (always available)
    "_core": ["docs", "fetch", "duckduckgo", "thinking", "memory"],

    # Design (available to all visual-heavy domains)
    "_design": ["image_gen", "charts", "diagrams", "svg", "drawio"],

    # Industries
    "agriculture": ["docs", "fetch", "duckduckgo", "sqlite", "calc", "time", "charts"],
    "ecommerce": ["docs", "fetch", "npm_search", "js_sandbox", "packages", "cve", "image_gen", "charts", "svg"],
    "finance": ["docs", "fetch", "calc", "cve", "sqlite", "time", "charts", "diagrams"],
    "healthcare": ["docs", "fetch", "cve", "sqlite", "time", "markitdown", "charts", "diagrams"],
    "education": ["docs", "fetch", "npm_search", "js_sandbox", "markitdown", "image_gen", "charts", "svg"],
    "social": ["docs", "fetch", "npm_search", "js_sandbox", "browser", "image_gen", "svg"],
    "project_management": ["docs", "fetch", "npm_search", "tasks", "sqlite", "time", "charts", "diagrams", "drawio"],
    "content": ["docs", "fetch", "markitdown", "pandoc", "npm_search", "image_gen", "svg", "charts"],
    "analytics": ["docs", "fetch", "sqlite", "calc", "npm_search", "js_sandbox", "charts", "diagrams"],
    "real_estate": ["docs", "fetch", "sqlite", "calc", "duckduckgo", "image_gen", "charts"],
    "logistics": ["docs", "fetch", "sqlite", "calc", "time", "duckduckgo", "charts", "diagrams"],
    "manufacturing": ["docs", "fetch", "sqlite", "calc", "time", "charts", "diagrams"],
    "legal": ["docs", "fetch", "markitdown", "pandoc", "duckduckgo", "cve"],
    "hr": ["docs", "fetch", "sqlite", "time", "markitdown", "charts"],
    "marketing": ["docs", "fetch", "duckduckgo", "npm_search", "browser", "image_gen", "charts", "svg"],
    "security": ["docs", "fetch", "cve", "code_analysis", "duckduckgo", "diagrams"],
    "devops": ["docs", "fetch", "docker", "git", "code_analysis", "cve", "diagrams", "drawio"],
    "iot": ["docs", "fetch", "sqlite", "calc", "time", "npm_search", "diagrams", "charts"],
    "gaming": ["docs", "fetch", "npm_search", "js_sandbox", "code_analysis", "image_gen", "svg"],
    "ai_ml": ["docs", "fetch", "npm_search", "calc", "duckduckgo", "code_analysis", "charts", "diagrams"],

    # Fallback
    "general": ["docs", "fetch", "duckduckgo", "npm_search", "sqlite", "charts", "image_gen"],
}


def get_domain_capabilities(domain: str) -> list[str]:
    """
    Get MCP capability tags relevant for a given industry domain.

    Returns the union of core capabilities + domain-specific capabilities.
    Agents use this to dynamically load the right MCP toolsets.

    Args:
        domain: Industry domain (e.g. "finance", "healthcare", "ecommerce")

    Returns:
        List of MCP capability tags
    """
    core = DOMAIN_MCP_MAP.get("_core", [])
    domain_caps = DOMAIN_MCP_MAP.get(domain, DOMAIN_MCP_MAP["general"])
    # Union, preserving order (core first)
    seen = set()
    result = []
    for cap in core + domain_caps:
        if cap not in seen:
            seen.add(cap)
            result.append(cap)
    return result


def get_domain_toolsets(domain: str) -> list:
    """
    Get actual MCP toolset instances for a domain.

    Convenience wrapper: resolves capability tags → live MCP connections.
    Skips unavailable servers gracefully.

    Args:
        domain: Industry domain

    Returns:
        List of McpToolset instances ready for agent use
    """
    caps = get_domain_capabilities(domain)
    return mcp_hub.get_toolsets(caps)


@dataclass(frozen=True)
class DomainExpertise:
    """Immutable bundle of domain knowledge for injection into agent prompts."""
    domain: str
    skill_content: Optional[str]
    similar_builds: str
    mcp_capabilities: list[str]
    available_mcp_count: int


def load_domain_expertise(
    product_name: str,
    prd: dict,
    architecture: Optional[dict] = None,
) -> str:
    """
    Load all available domain expertise for a product build.

    This is the main entry point. The product pipeline calls this before building
    to get:
    1. Forged skill content (from skill_forge staging registry)
    2. Similar past builds (from skill_memory)
    3. Relevant MCP capabilities for the domain

    Args:
        product_name: Name of the product being built
        prd: PRD dict (parsed or raw)
        architecture: Optional architecture dict

    Returns:
        JSON string with domain expertise bundle
    """
    if isinstance(prd, str):
        try:
            prd = json.loads(prd)
        except (json.JSONDecodeError, TypeError):
            prd = {}

    # 1. Detect domain
    domain = _extract_domain(product_name, prd)

    # 2. Find forged skills for this domain
    skill_content = _find_forged_skill(domain)

    # 3. Find similar past builds
    similar = find_similar_skills(product_name, prd, architecture, limit=3)

    # 4. Get MCP capabilities for this domain
    caps = get_domain_capabilities(domain)
    available = mcp_hub.get_toolsets(caps)

    expertise = DomainExpertise(
        domain=domain,
        skill_content=skill_content,
        similar_builds=similar,
        mcp_capabilities=caps,
        available_mcp_count=len(available),
    )

    result = {
        "domain": expertise.domain,
        "has_forged_skill": expertise.skill_content is not None,
        "skill_content_preview": (expertise.skill_content or "")[:500],
        "similar_builds": json.loads(expertise.similar_builds),
        "mcp_capabilities": expertise.mcp_capabilities,
        "available_mcp_servers": expertise.available_mcp_count,
    }

    if expertise.skill_content:
        result["full_skill_content"] = expertise.skill_content

    _log.info(
        "Domain expertise loaded: domain=%s, forged_skill=%s, similar=%d, mcp=%d",
        domain,
        expertise.skill_content is not None,
        len(json.loads(expertise.similar_builds).get("similar_skills", [])),
        expertise.available_mcp_count,
    )

    return json.dumps(result, indent=2)


def _find_forged_skill(domain: str) -> Optional[str]:
    """Find the best forged skill for a domain from the staging registry."""
    try:
        staged = list_staged_skills_sync()
    except Exception:
        return None

    # Filter by domain match
    matches = [s for s in staged if s.get("domain", "").lower() == domain.lower()]

    if not matches:
        return None

    # Pick highest composite score
    best = max(matches, key=lambda s: s.get("composite_score", 0))

    # Load the actual skill content
    try:
        # The staging registry links to a session — get the best version from it
        # For now, read the skill file if it exists
        skill_path = best.get("file_path", "")
        if skill_path:
            try:
                with open(skill_path, "r", encoding="utf-8") as f:
                    content = f.read()
                increment_production_runs_sync(best["skill_id"])
                return content
            except FileNotFoundError:
                pass
    except Exception as exc:
        _log.warning("Failed to load forged skill: %s", exc)

    return None


def detect_industry(requirement: str) -> str:
    """
    Detect the industry/domain from a raw requirement string.

    Useful for the orchestrator to route to the right MCP toolset
    before the PM agent even generates the PRD.

    Args:
        requirement: Raw user requirement text

    Returns:
        Detected domain string
    """
    req_lower = requirement.lower()

    # Extended industry detection keywords
    industry_keywords: dict[str, list[str]] = {
        "agriculture": ["farm", "crop", "harvest", "irrigation", "aquaculture", "shrimp",
                        "pond", "livestock", "soil", "greenhouse", "fertilizer", "yield"],
        "ecommerce": ["shop", "cart", "checkout", "product catalog", "inventory", "order",
                       "payment", "store", "marketplace", "wishlist", "shipping"],
        "finance": ["bank", "payment", "invoice", "budget", "accounting", "expense",
                     "transaction", "loan", "portfolio", "trading", "fintech", "ledger"],
        "healthcare": ["patient", "medical", "health", "clinic", "appointment", "doctor",
                        "prescription", "ehr", "diagnosis", "telehealth", "pharmacy"],
        "education": ["course", "student", "lesson", "quiz", "learning", "classroom",
                       "teacher", "lms", "curriculum", "grading", "enrollment"],
        "social": ["profile", "post", "feed", "follow", "message", "chat", "community",
                    "forum", "notification", "friend", "group"],
        "project_management": ["task", "project", "sprint", "kanban", "ticket", "milestone",
                                "team", "backlog", "workflow", "gantt", "agile"],
        "content": ["blog", "article", "cms", "publish", "editor", "media", "content",
                     "newsletter", "podcast", "video platform"],
        "analytics": ["dashboard", "chart", "metric", "report", "analytics", "visualization",
                       "data pipeline", "bi", "kpi", "funnel"],
        "real_estate": ["property", "listing", "tenant", "rent", "lease", "real estate",
                         "mortgage", "broker", "apartment"],
        "logistics": ["shipping", "warehouse", "fleet", "delivery", "tracking", "route",
                       "supply chain", "freight", "dispatch", "carrier"],
        "manufacturing": ["production", "assembly", "quality control", "bom", "machine",
                           "factory", "defect", "batch", "inspection"],
        "legal": ["contract", "case", "law firm", "compliance", "litigation", "attorney",
                   "clause", "legal document", "regulation"],
        "hr": ["employee", "hiring", "payroll", "leave", "recruitment", "onboarding",
                "performance review", "benefits", "attendance"],
        "marketing": ["campaign", "lead", "crm", "email marketing", "seo", "conversion",
                       "funnel", "brand", "social media marketing"],
        "security": ["vulnerability", "pentest", "firewall", "threat", "incident",
                      "soc", "siem", "zero trust", "authentication"],
        "devops": ["ci/cd", "pipeline", "deploy", "kubernetes", "docker", "terraform",
                    "monitoring", "infrastructure", "gitops"],
        "iot": ["sensor", "device", "mqtt", "telemetry", "embedded", "smart home",
                 "gateway", "firmware", "edge computing"],
        "gaming": ["game", "player", "score", "level", "multiplayer", "leaderboard",
                    "sprite", "physics engine", "unity", "godot"],
        "ai_ml": ["model", "training", "inference", "dataset", "neural", "llm",
                   "fine-tune", "embeddings", "vector", "ml pipeline"],
    }

    scores: dict[str, int] = {}
    for domain, keywords in industry_keywords.items():
        score = sum(1 for kw in keywords if kw in req_lower)
        if score > 0:
            scores[domain] = score

    if not scores:
        return "general"

    return max(scores, key=scores.get)


def list_supported_industries() -> str:
    """
    List all industries sl_agents can dynamically support.

    Returns:
        JSON with all supported domains and their MCP capability count
    """
    industries = []
    for domain, caps in sorted(DOMAIN_MCP_MAP.items()):
        if domain == "_core":
            continue
        available = len(mcp_hub.get_toolsets(caps))
        industries.append({
            "domain": domain,
            "mcp_capabilities": caps,
            "available_servers": available,
        })

    return json.dumps({
        "total_industries": len(industries),
        "industries": industries,
        "note": "Any new industry can be added via skill_forge + MCP hub config",
    }, indent=2)
