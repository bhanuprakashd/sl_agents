"""
gtm-research MCP server — wraps aass_agents/tools/research_tools.py

Tools: search_company_web, enrich_company, find_contacts, search_news, deep_research
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

# Allow importing from the ADK project
ADK_ROOT = Path(__file__).parent.parent.parent / "aass_agents"
sys.path.insert(0, str(ADK_ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

app = Server("gtm-research")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="search_company_web",
             description="Search the web for company information using DuckDuckGo (no API key needed).",
             inputSchema={"type": "object", "required": ["company_name"],
                          "properties": {"company_name": {"type": "string"},
                                         "query_suffix": {"type": "string", "default": ""}}}),
        Tool(name="enrich_company",
             description="Enrich company firmographic data via OpenCorporates + DuckDuckGo.",
             inputSchema={"type": "object", "required": ["domain"],
                          "properties": {"domain": {"type": "string"}}}),
        Tool(name="find_contacts",
             description="Find decision-maker contacts using GitHub API and DuckDuckGo LinkedIn search.",
             inputSchema={"type": "object", "required": ["company_domain"],
                          "properties": {"company_domain": {"type": "string"},
                                         "title_filter": {"type": "string"}}}),
        Tool(name="search_news",
             description="Search for recent news about a company using DuckDuckGo News.",
             inputSchema={"type": "object", "required": ["company_name"],
                          "properties": {"company_name": {"type": "string"},
                                         "days_back": {"type": "integer", "default": 180}}}),
        Tool(
            name="search_product_web",
            description="Search the web for SaaS products, GitHub repos, and tech stacks.",
            inputSchema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "query_suffix": {"type": "string", "default": ""},
                },
            },
        ),
        Tool(
            name="search_medium",
            description="Search Medium articles by keywords. Returns titles, URLs, authors, and excerpts.",
            inputSchema={
                "type": "object",
                "required": ["keywords"],
                "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
            },
        ),
        Tool(
            name="deep_research",
            description=(
                "Run a deep multi-step research query via DeerFlow. Returns a synthesized "
                "report with citations. Falls back to DuckDuckGo if DeerFlow is unavailable."
            ),
            inputSchema={
                "type": "object",
                "required": ["query"],
                "properties": {"query": {"type": "string"}},
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    from tools.research_tools import (
        search_company_web, enrich_company, find_contacts, search_news,
    )

    try:
        if name == "search_company_web":
            result = search_company_web(
                arguments["company_name"],
                arguments.get("query_suffix", ""),
            )
        elif name == "enrich_company":
            result = enrich_company(arguments["domain"])
        elif name == "find_contacts":
            result = find_contacts(
                arguments["company_domain"],
                arguments.get("title_filter"),
            )
        elif name == "search_news":
            result = search_news(
                arguments["company_name"],
                arguments.get("days_back", 180),
            )
        elif name == "search_product_web":
            from tools.research_tools import search_company_web
            result = search_company_web(
                arguments["query"],
                arguments.get("query_suffix", ""),
            )
        elif name == "search_medium":
            result = await _search_medium(arguments["keywords"])
        elif name == "deep_research":
            result = await _deep_research(arguments["query"])
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as e:
        result = {"error": str(e)}

    return [TextContent(type="text", text=json.dumps(result))]


DEERFLOW_URL = os.environ.get("DEERFLOW_URL", "http://localhost:2026")
MEDIUM_MCP_PATH = os.environ.get("MEDIUM_MCP_PATH", "../medium-mcp-server")


async def _search_medium(keywords: list[str]) -> dict:
    """Call the Medium MCP server subprocess to search articles."""
    import asyncio
    try:
        proc = await asyncio.create_subprocess_exec(
            "node", f"{MEDIUM_MCP_PATH}/dist/index.js",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=MEDIUM_MCP_PATH,
        )
        # Send MCP JSON-RPC call for search-medium
        request = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "search-medium", "arguments": {"keywords": keywords}}
        }) + "\n"
        stdout, _ = await asyncio.wait_for(
            proc.communicate(request.encode()), timeout=30
        )
        for line in stdout.decode().splitlines():
            if line.strip().startswith("{"):
                resp = json.loads(line)
                if "result" in resp:
                    return {"articles": resp["result"], "keywords": keywords, "source": "medium"}
        return {"articles": [], "keywords": keywords, "source": "medium", "error": "no result"}
    except Exception as exc:
        return {"articles": [], "keywords": keywords, "source": "medium", "error": str(exc)}


async def _deep_research(query: str) -> dict:
    """Run deep research via DeerFlow LangGraph API, fall back to DuckDuckGo."""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # Step 1: create thread
            thread_resp = await client.post(
                f"{DEERFLOW_URL}/api/langgraph/threads",
                json={},
            )
            thread_resp.raise_for_status()
            thread_id = thread_resp.json()["thread_id"]

            # Step 2: stream run and collect SSE events
            payload = {
                "assistant_id": "lead_agent",
                "input": {"messages": [{"role": "human", "content": query}]},
                "stream_mode": ["values"],
            }
            report = ""
            async with client.stream(
                "POST",
                f"{DEERFLOW_URL}/api/langgraph/threads/{thread_id}/runs/stream",
                json=payload,
            ) as stream:
                async for line in stream.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        event = json.loads(data_str)
                        # Extract final report from values event
                        messages = event.get("messages", [])
                        if messages:
                            last = messages[-1]
                            content = last.get("content", "")
                            if isinstance(content, str) and content:
                                report = content
                    except json.JSONDecodeError:
                        continue

            return {"report": report, "source": "deerflow", "query": query}

    except Exception as exc:
        # Fallback: lightweight DuckDuckGo search
        try:
            from tools.research_tools import search_company_web
            fallback = search_company_web(query, "")
            return {"report": json.dumps(fallback), "source": "duckduckgo_fallback", "query": query}
        except Exception:
            return {"error": f"DeerFlow unavailable ({exc}) and fallback also failed"}


async def main():
    async with stdio_server() as (r, w):
        await app.run(r, w, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
