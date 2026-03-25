"""
gtm-marketing MCP server — wraps sales-adk-agents/tools/marketing_tools.py

Tools: get_trending_topics, search_competitor_content, fetch_rss_feed,
       search_audience_communities
"""

import asyncio
import json
import sys
from pathlib import Path

ADK_ROOT = Path(__file__).parent.parent.parent / "sales-adk-agents"
sys.path.insert(0, str(ADK_ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

app = Server("gtm-marketing")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="get_trending_topics",
             description="Get trending related queries and topics for a keyword using Google Trends.",
             inputSchema={"type": "object", "required": ["keyword"],
                          "properties": {"keyword": {"type": "string"},
                                         "region": {"type": "string", "default": "US"},
                                         "timeframe": {"type": "string", "default": "today 3-m"}}}),
        Tool(name="search_competitor_content",
             description="Find competitor content on a topic using DuckDuckGo site search.",
             inputSchema={"type": "object", "required": ["competitor_domain"],
                          "properties": {"competitor_domain": {"type": "string"},
                                         "topic": {"type": "string"},
                                         "content_type": {"type": "string", "default": "blog"}}}),
        Tool(name="fetch_rss_feed",
             description="Fetch and parse an RSS/Atom feed for content monitoring.",
             inputSchema={"type": "object", "required": ["feed_url"],
                          "properties": {"feed_url": {"type": "string"},
                                         "max_items": {"type": "integer", "default": 10}}}),
        Tool(name="search_audience_communities",
             description="Find online communities (Reddit, LinkedIn, Slack) where the ICP persona is active.",
             inputSchema={"type": "object", "required": ["persona_description"],
                          "properties": {"persona_description": {"type": "string"},
                                         "platform": {"type": "string", "default": "all"}}}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    from tools.marketing_tools import (
        get_trending_topics, search_competitor_content,
        fetch_rss_feed, search_audience_communities,
    )

    try:
        if name == "get_trending_topics":
            result = get_trending_topics(
                arguments["keyword"],
                arguments.get("region", "US"),
                arguments.get("timeframe", "today 3-m"),
            )
        elif name == "search_competitor_content":
            result = search_competitor_content(
                arguments["competitor_domain"],
                arguments.get("topic"),
                arguments.get("content_type", "blog"),
            )
        elif name == "fetch_rss_feed":
            result = fetch_rss_feed(arguments["feed_url"], arguments.get("max_items", 10))
        elif name == "search_audience_communities":
            result = search_audience_communities(
                arguments["persona_description"],
                arguments.get("platform", "all"),
            )
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as e:
        result = {"error": str(e)}

    return [TextContent(type="text", text=json.dumps(result))]


async def main():
    async with stdio_server() as (r, w):
        await app.run(r, w, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
