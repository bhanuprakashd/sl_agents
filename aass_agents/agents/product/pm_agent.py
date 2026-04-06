# aass_agents/agents/pm_agent.py
"""
PM Agent — converts raw requirement into a rich, structured PRD.
Uses DeerFlow (via MCP research_server) for competitor research.
Uses ADK output_key to auto-save PRD to session state.
"""
import os
import sys
from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams, StdioServerParameters
from tools.agent_reach_tools import (
    read_webpage, search_reddit, read_rss_feed, search_youtube,
    search_github_repos, search_github_code,
)

from agents._shared.model import get_model, FAST
from agents._shared.mcp_hub import mcp_hub
from tools.document_tools import read_document, read_document_pages, list_documents, search_document

INSTRUCTION = """
You are a PM agent. Research the market, then output a complete PRD as JSON.
Your response will be automatically saved to session state via output_key.

## Process
1. Research (do ALL before writing PRD):
   a. search_github_repos for similar products
   b. search_github_code for implementation patterns
   c. search_reddit, search_youtube for market context
   d. read_webpage on top 1-2 GitHub repos
2. Output the PRD as a single JSON object (no markdown, no code fences, just raw JSON)

## PRD JSON Fields
{
  "product_name": "PascalCase name",
  "one_liner": "short description",
  "target_user": "who uses it",
  "problem_statement": "what problem it solves",
  "core_features": [{"name": "", "description": "", "user_story": "", "priority": "P0|P1|P2"}],
  "data_model": [{"name": "", "fields": [{"name": "", "type": ""}], "relationships": []}],
  "acceptance_criteria": ["testable binary pass/fail statements"],
  "product_type": "full-stack SaaS|full-stack python|API-heavy backend|API-heavy python|data-heavy app|data-heavy python|simple landing|static|CLI",
  "tech_preferences": {"language": "", "frontend": "", "backend": "", "database": "", "styling": "", "other": ""},
  "design_guidelines": {"theme": "light|dark|auto", "style": "modern|minimalist|enterprise|playful", "color_direction": "", "key_interactions": [], "inspiration": ""},
  "pages": [{"path": "", "name": "", "description": ""}],
  "api_endpoints": [{"method": "", "path": "", "description": ""}],
  "market_research": {"github_repos": "", "implementation_patterns": "", "market_context": "", "user_pain_points": ""}
}

## Rules
- v1 scope only. 5-7 core features. Complete data model. 5-8 testable acceptance criteria.
- Python mention → python variants.
- On tool failure: use knowledge, label [Knowledge-Based], deliver anyway.
- CRITICAL: Your entire response must be a single JSON object. No preamble, no explanation, no markdown code fences, no text before or after the JSON. Start with { and end with }. This is mandatory because your output is parsed by downstream agents.
"""

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH_SERVER = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "mcp-servers", "gtm", "research_server.py"))

# DeerFlow research tools come from the MCP research_server process
_research_mcp = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[_RESEARCH_SERVER],
            env={**os.environ},
        ),
        timeout=300.0,
    )
)

# MCP tools: search, crawl, duckduckgo, npm_search, docs, fetch,
# github (repo/code search for market research)
_mcp_tools = mcp_hub.get_toolsets([
    "search", "crawl", "duckduckgo", "npm_search", "docs", "fetch", "github",
    "arxiv", "wikipedia", "hacker_news", "web_search", "readability",
])

pm_agent = Agent(
    model=get_model(FAST),
    name="pm_agent",
    description="Converts a raw product requirement into a comprehensive PRD with tech preferences, design guidelines, and detailed acceptance criteria.",
    instruction=INSTRUCTION,
    output_key="prd_output",  # Auto-save response to state["prd_output"]
    tools=[_research_mcp, read_document, read_document_pages, list_documents, search_document,
           read_webpage, search_reddit, read_rss_feed, search_youtube,
           search_github_repos, search_github_code,
           *_mcp_tools],
)
