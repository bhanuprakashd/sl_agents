"""
gtm-crm MCP server — wraps sales-adk-agents/tools/crm_tools.py

Tools: sf_find_opportunity, sf_update_opportunity, sf_log_call, sf_create_task,
       sf_get_pipeline, hs_find_deal, hs_log_note, hs_update_deal, hs_create_task

Env: SALESFORCE_ACCESS_TOKEN, SALESFORCE_INSTANCE_URL, HUBSPOT_API_KEY
"""

import asyncio
import json
import os
import sys
from pathlib import Path

ADK_ROOT = Path(__file__).parent.parent.parent / "sales-adk-agents"
sys.path.insert(0, str(ADK_ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

app = Server("gtm-crm")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="sf_find_opportunity",
             description="Find an open opportunity in Salesforce by company name.",
             inputSchema={"type": "object", "required": ["company_name"],
                          "properties": {"company_name": {"type": "string"}}}),
        Tool(name="sf_update_opportunity",
             description="Update a Salesforce opportunity (stage, amount, close date, next step).",
             inputSchema={"type": "object", "required": ["opportunity_id"],
                          "properties": {"opportunity_id": {"type": "string"},
                                         "stage": {"type": "string"},
                                         "amount": {"type": "number"},
                                         "close_date": {"type": "string"},
                                         "next_step": {"type": "string"}}}),
        Tool(name="sf_log_call",
             description="Log a call activity on a Salesforce opportunity.",
             inputSchema={"type": "object", "required": ["opportunity_id", "subject", "notes", "call_date"],
                          "properties": {"opportunity_id": {"type": "string"}, "subject": {"type": "string"},
                                         "notes": {"type": "string"}, "call_date": {"type": "string"}}}),
        Tool(name="sf_create_task",
             description="Create a follow-up task on a Salesforce opportunity.",
             inputSchema={"type": "object", "required": ["opportunity_id", "subject", "due_date"],
                          "properties": {"opportunity_id": {"type": "string"}, "subject": {"type": "string"},
                                         "due_date": {"type": "string"}, "notes": {"type": "string"},
                                         "priority": {"type": "string", "default": "Normal"}}}),
        Tool(name="sf_get_pipeline",
             description="Fetch all open pipeline opportunities from Salesforce.",
             inputSchema={"type": "object",
                          "properties": {"owner_id": {"type": "string"},
                                         "fiscal_quarter": {"type": "string"}}}),
        Tool(name="hs_find_deal",
             description="Find a HubSpot deal by company name.",
             inputSchema={"type": "object", "required": ["company_name"],
                          "properties": {"company_name": {"type": "string"}}}),
        Tool(name="hs_log_note",
             description="Log a note on a HubSpot deal.",
             inputSchema={"type": "object", "required": ["deal_id", "note_body"],
                          "properties": {"deal_id": {"type": "string"}, "note_body": {"type": "string"}}}),
        Tool(name="hs_update_deal",
             description="Update a HubSpot deal's stage, amount, close date, or next step.",
             inputSchema={"type": "object", "required": ["deal_id"],
                          "properties": {"deal_id": {"type": "string"}, "stage": {"type": "string"},
                                         "amount": {"type": "number"}, "close_date": {"type": "string"},
                                         "next_step": {"type": "string"}}}),
        Tool(name="hs_create_task",
             description="Create a follow-up task on a HubSpot deal.",
             inputSchema={"type": "object", "required": ["deal_id", "subject", "due_date"],
                          "properties": {"deal_id": {"type": "string"}, "subject": {"type": "string"},
                                         "due_date": {"type": "string"}, "notes": {"type": "string"},
                                         "priority": {"type": "string", "default": "MEDIUM"}}}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    from tools.crm_tools import (
        sf_find_opportunity, sf_update_opportunity, sf_log_call, sf_create_task, sf_get_pipeline,
        hs_find_deal, hs_log_note, hs_update_deal, hs_create_task,
    )

    try:
        fn_map = {
            "sf_find_opportunity": lambda a: sf_find_opportunity(a["company_name"]),
            "sf_update_opportunity": lambda a: sf_update_opportunity(
                a["opportunity_id"], a.get("stage"), a.get("amount"), a.get("close_date"), a.get("next_step")),
            "sf_log_call": lambda a: sf_log_call(a["opportunity_id"], a["subject"], a["notes"], a["call_date"]),
            "sf_create_task": lambda a: sf_create_task(
                a["opportunity_id"], a["subject"], a["due_date"], a.get("notes"), a.get("priority", "Normal")),
            "sf_get_pipeline": lambda a: sf_get_pipeline(a.get("owner_id"), a.get("fiscal_quarter")),
            "hs_find_deal": lambda a: hs_find_deal(a["company_name"]),
            "hs_log_note": lambda a: hs_log_note(a["deal_id"], a["note_body"]),
            "hs_update_deal": lambda a: hs_update_deal(
                a["deal_id"], a.get("stage"), a.get("amount"), a.get("close_date"), a.get("next_step")),
            "hs_create_task": lambda a: hs_create_task(
                a["deal_id"], a["subject"], a["due_date"], a.get("notes"), a.get("priority", "MEDIUM")),
        }
        result = fn_map[name](arguments)
    except Exception as e:
        result = {"error": str(e)}

    return [TextContent(type="text", text=json.dumps(result))]


async def main():
    async with stdio_server() as (r, w):
        await app.run(r, w, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
