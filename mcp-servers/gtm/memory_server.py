"""
gtm-memory MCP server — wraps the ADK sales team's SQLite deal memory.

Exposes 5 tools:
  save_deal_context      persist deal context per company
  recall_deal_context    retrieve prior deal context
  list_active_deals      list all companies in memory
  save_agent_output      save a skill output to query history
  recall_past_outputs    recall past outputs (avoid re-doing work)

Run: python memory_server.py
Env: GTM_MEMORY_DB_PATH — path to sales_memory.db (default: sibling of this file)
"""

import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ── DB path ──────────────────────────────────────────────────────────────────
DB_PATH = Path(
    os.environ.get(
        "GTM_MEMORY_DB_PATH",
        Path(__file__).parent.parent.parent
        / "sales-adk-agents"
        / "sales_memory.db",
    )
)


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _init():
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS deal_memory (
                company_name TEXT NOT NULL,
                user_id      TEXT NOT NULL DEFAULT 'default',
                deal_context TEXT NOT NULL,
                updated_at   TEXT NOT NULL,
                PRIMARY KEY (company_name, user_id)
            );
            CREATE TABLE IF NOT EXISTS query_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                user_id      TEXT NOT NULL DEFAULT 'default',
                agent_name   TEXT NOT NULL,
                query        TEXT NOT NULL,
                output       TEXT NOT NULL,
                created_at   TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_qh ON query_history (company_name, user_id);
        """)


_init()

# ── Server ────────────────────────────────────────────────────────────────────
app = Server("gtm-memory")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="save_deal_context",
             description="Persist deal context JSON for a company across sessions.",
             inputSchema={"type": "object", "required": ["company_name", "deal_context_json"],
                          "properties": {"company_name": {"type": "string"},
                                         "deal_context_json": {"type": "string"},
                                         "user_id": {"type": "string", "default": "default"}}}),
        Tool(name="recall_deal_context",
             description="Retrieve saved deal context for a company.",
             inputSchema={"type": "object", "required": ["company_name"],
                          "properties": {"company_name": {"type": "string"},
                                         "user_id": {"type": "string", "default": "default"}}}),
        Tool(name="list_active_deals",
             description="List all companies with saved deal memory.",
             inputSchema={"type": "object", "properties": {"user_id": {"type": "string", "default": "default"}}}),
        Tool(name="save_agent_output",
             description="Save a skill/agent output to query history for future recall.",
             inputSchema={"type": "object",
                          "required": ["company_name", "agent_name", "query", "output"],
                          "properties": {"company_name": {"type": "string"},
                                         "agent_name": {"type": "string"},
                                         "query": {"type": "string"},
                                         "output": {"type": "string"},
                                         "user_id": {"type": "string", "default": "default"}}}),
        Tool(name="recall_past_outputs",
             description="Recall past skill outputs for a company. Use before re-running a skill.",
             inputSchema={"type": "object", "required": ["company_name"],
                          "properties": {"company_name": {"type": "string"},
                                         "agent_name": {"type": "string"},
                                         "limit": {"type": "integer", "default": 3},
                                         "user_id": {"type": "string", "default": "default"}}}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    now = datetime.utcnow().isoformat()

    if name == "save_deal_context":
        company = arguments["company_name"].lower().strip()
        uid = arguments.get("user_id", "default")
        try:
            ctx = json.loads(arguments["deal_context_json"])
        except json.JSONDecodeError as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
        with _conn() as c:
            c.execute(
                "INSERT INTO deal_memory VALUES (?,?,?,?) ON CONFLICT(company_name,user_id)"
                " DO UPDATE SET deal_context=excluded.deal_context, updated_at=excluded.updated_at",
                (company, uid, json.dumps(ctx), now),
            )
        return [TextContent(type="text", text=json.dumps({"saved": True, "company": company}))]

    elif name == "recall_deal_context":
        company = arguments["company_name"].lower().strip()
        uid = arguments.get("user_id", "default")
        with _conn() as c:
            row = c.execute(
                "SELECT deal_context, updated_at FROM deal_memory WHERE company_name=? AND user_id=?",
                (company, uid),
            ).fetchone()
        if row:
            return [TextContent(type="text", text=json.dumps(
                {"deal_context": json.loads(row["deal_context"]), "updated_at": row["updated_at"]}))]
        return [TextContent(type="text", text=json.dumps({"found": False, "company": company}))]

    elif name == "list_active_deals":
        uid = arguments.get("user_id", "default")
        with _conn() as c:
            rows = c.execute(
                "SELECT company_name, updated_at FROM deal_memory WHERE user_id=? ORDER BY updated_at DESC",
                (uid,),
            ).fetchall()
        deals = [dict(r) for r in rows]
        return [TextContent(type="text", text=json.dumps({"deals": deals, "count": len(deals)}))]

    elif name == "save_agent_output":
        company = arguments["company_name"].lower().strip()
        uid = arguments.get("user_id", "default")
        with _conn() as c:
            c.execute(
                "INSERT INTO query_history (company_name,user_id,agent_name,query,output,created_at) VALUES (?,?,?,?,?,?)",
                (company, uid, arguments["agent_name"], arguments["query"], arguments["output"], now),
            )
        return [TextContent(type="text", text=json.dumps({"saved": True}))]

    elif name == "recall_past_outputs":
        company = arguments["company_name"].lower().strip()
        uid = arguments.get("user_id", "default")
        agent = arguments.get("agent_name")
        limit = arguments.get("limit", 3)
        with _conn() as c:
            if agent:
                rows = c.execute(
                    "SELECT agent_name,query,output,created_at FROM query_history"
                    " WHERE company_name=? AND user_id=? AND agent_name=? ORDER BY created_at DESC LIMIT ?",
                    (company, uid, agent, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT agent_name,query,output,created_at FROM query_history"
                    " WHERE company_name=? AND user_id=? ORDER BY created_at DESC LIMIT ?",
                    (company, uid, limit),
                ).fetchall()
        history = [dict(r) for r in rows]
        return [TextContent(type="text", text=json.dumps({"company": company, "history": history, "count": len(history)}))]

    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


async def main():
    async with stdio_server() as (r, w):
        await app.run(r, w, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
