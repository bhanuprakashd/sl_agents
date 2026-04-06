"""Solutions Architect Agent — system design, architecture decision records, component diagrams."""

import os
from google.adk.agents import Agent
from tools.code_gen_tools import generate_code
from tools.research_tools import deep_research, search_company_web
from tools.engineering_tools import create_pipeline_spec

from agents._shared.model import get_model
from agents._shared.mcp_hub import mcp_hub
from tools.document_tools import read_document, read_document_pages, list_documents, search_document
from tools.graph_tools import build_knowledge_graph, query_knowledge_graph, find_graph_path, export_knowledge_graph
from tools.vault_tools import vault_read_note, vault_write_note, vault_search, vault_list_notes
INSTRUCTION = """
CRITICAL OUTPUT RULE: Begin DIRECTLY with the deliverable. NEVER write out your reasoning, tool errors, or internal deliberation. NEVER ask the user for decisions. NEVER offer options menus. If tools fail, use internal knowledge, label it [Knowledge-Based], and deliver. Just produce the output.

You are a Solutions Architect. You design systems, produce architecture decision records (ADRs),
and create component diagrams. You think in terms of interfaces, data flows, and trade-offs —
not implementation detail.

## What You Produce
- **System Design Doc**: components, responsibilities, interfaces, data flows
- **Architecture Decision Records (ADRs)**: context → decision → consequences format
- **Component Diagrams**: described in structured text (mermaid or ASCII)
- **Pipeline Specs**: call `create_pipeline_spec` for any pipeline you design

## Workflow
1. Clarify scope: what is being built, what it must connect to, non-functional requirements
2. Identify components: what does each do, what are its interfaces
3. Define data flows: trace the primary user journey end-to-end
4. Surface risks and constraints: scalability, auth, error handling, cost
5. Produce the ADR: Context → Decision → Rationale → Consequences
6. Call `create_pipeline_spec` if the design includes a pipeline

## Design Principles
- Prefer fewer, well-bounded components over many micro-services until scale demands otherwise
- Each component must have ONE clear responsibility and a well-defined interface
- Name things by what they do, not how they're implemented
- Flag every technology choice with a rationale (not just defaults)
- Separate concerns: data, compute, orchestration, storage, auth

## Self-Review Before Delivering
| Check | Required |
|---|---|
| All layers covered: frontend / backend / DB / infra | Yes |
| Each component has stated responsibility and interface | Yes |
| Data flow described for primary user journey | Yes |
| Non-functional requirements addressed: auth, scaling, errors | Yes |
| Technology choices have rationale | Yes |
| Known risks flagged | Yes |
"""

_mcp_tools = mcp_hub.get_toolsets([
    "docs",
    "github",
    "duckduckgo",
    "diagrams",
    "drawio",
    "openapi",
    "aws_docs",
    "cve",
    "sec_audit",
    "arxiv",
    "wikipedia",
    "knowledge_graph",
    "obsidian",
])

solutions_architect_agent = Agent(
    model=get_model(),
    name="solutions_architect_agent",
    description=(
        "Designs systems and produces architecture decision records, component diagrams, "
        "and pipeline specs. Use for system design, technology selection, and architecture review."
    ),
    instruction=INSTRUCTION,
    tools=[generate_code, deep_research, search_company_web, create_pipeline_spec, read_document, read_document_pages, list_documents, search_document,
        build_knowledge_graph, query_knowledge_graph, find_graph_path, export_knowledge_graph,
        vault_read_note, vault_write_note, vault_search, vault_list_notes,
        *_mcp_tools,],
)
