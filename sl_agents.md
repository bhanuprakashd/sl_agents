# SL Agents — Full System Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [System Components](#system-components)
   - [DeerFlow](#deerflow)
   - [Sales ADK Agents](#aass_agents)
   - [MCP Servers (GTM)](#mcp-servers-gtm)
   - [gstack (Claude Code Skills)](#gstack-claude-code-skills)
4. [Agents Reference](#agents-reference)
5. [Tools Reference](#tools-reference)
6. [MCP Servers Reference](#mcp-servers-reference)
7. [Environment Variables](#environment-variables)
8. [Startup & Entry Points](#startup--entry-points)
9. [Configuration Files](#configuration-files)
10. [Key Ports](#key-ports)
11. [Integrations](#integrations)

---

## Overview

SL Agents is a multi-system autonomous AI platform combining:

- **DeerFlow** — LangGraph-based super agent with sandbox execution, memory, and MCP tool support
- **Sales ADK Agents** — Google ADK B2B sales and product engineering team (26 agents)
- **MCP Servers (GTM)** — 4 MCP servers exposing research, CRM, memory, and marketing tools
- **gstack** — Claude Code skills library providing slash commands and a headless browser for QA

The systems are integrated: DeerFlow provides deep research capabilities to the sales team via its LangGraph API, MCP servers bridge tooling across both agent runtimes, and gstack slash commands are available in any Claude Code session.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User / API Client                         │
└───────────────┬──────────────────────────┬──────────────────────┘
                │                          │
    ┌───────────▼──────────┐   ┌───────────▼──────────┐
    │      DeerFlow        │   │   Sales ADK Agents   │
    │  (port 2026 via Nginx)│   │   (CLI / ADK API)    │
    │                      │   │                      │
    │  Lead Agent          │   │  company_orchestrator│
    │  ├─ 12 middlewares   │   │  ├─ sales_orchestrator│
    │  ├─ Sandbox (bash,   │   │  │  └─ 7 sales agents│
    │  │    file ops)      │   │  ├─ marketing_orches. │
    │  ├─ Web search/fetch │   │  │  └─ 6 mktg agents │
    │  ├─ Subagents        │   │  └─ product_orchestr. │
    │  └─ MCP clients      │   │     └─ 7 prod agents │
    └──────────┬───────────┘   └───────────┬──────────┘
               │                           │
    ┌──────────▼───────────────────────────▼──────────┐
    │                MCP Servers (GTM)                  │
    │  gtm-research │ gtm-crm │ gtm-memory │ gtm-mktg  │
    └──────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────┐
    │         gstack (Claude Code Skills)              │
    │  deer-flow/skills/gstack → ~/.claude/skills/gstack│
    │  Slash commands: /ship /review /qa /investigate  │
    │  Browse binary: headless Chromium for QA agent   │
    └─────────────────────────────────────────────────┘
```

### Data Flow

1. User sends a request to DeerFlow or Sales ADK
2. Orchestrator routes to the appropriate specialist agent
3. Agent calls tools (research, CRM, code gen, deployment)
4. DeerFlow's `deep_research` tool calls DeerFlow LangGraph API for synthesized reports
5. Product pipeline state is tracked in SQLite via `product_memory_tools` (`save_product_state`, `recall_product_state`, `log_step`)
6. MCP servers bridge tools to any MCP-compatible client
7. gstack slash commands are available in any Claude Code session via the `~/.claude/skills/gstack` symlink

---

## System Components

### DeerFlow

**Location**: `deer-flow/`

LangGraph-based super agent harness. Provides an agent runtime with sandbox execution, pluggable LLM providers, skills, memory, subagents, and MCP tool support.

**Key directories:**
```
deer-flow/
├── backend/
│   ├── packages/harness/deerflow/   # Publishable framework package
│   │   ├── agents/                  # Lead agent + 12 middlewares
│   │   ├── config/                  # Config loaders (models, tools, sandbox, memory...)
│   │   ├── models/                  # LLM provider integrations
│   │   ├── tools/                   # Built-in + community tools
│   │   ├── sandbox/                 # Local + Docker sandbox
│   │   ├── skills/                  # SKILL.md loader/parser
│   │   ├── subagents/               # Background subagent execution
│   │   ├── mcp/                     # MCP multi-server client
│   │   ├── guardrails/              # Pre-call authorization
│   │   └── channels/                # Feishu, Slack, Telegram
│   ├── app/
│   │   └── gateway/                 # FastAPI gateway (port 8001)
│   ├── config.yaml                  # Active config (from config.example.yaml)
│   └── langgraph.json               # LangGraph server definition
├── frontend/                        # Next.js UI (port 3000)
└── Makefile                         # make dev / make build / etc.
```

**Middleware chain** (applied in order on every agent invocation):

| # | Middleware | Purpose |
|---|-----------|---------|
| 1 | ThreadDataMiddleware | Creates per-thread workspace directories |
| 2 | UploadsMiddleware | Tracks uploaded files |
| 3 | SandboxMiddleware | Acquires sandbox instance |
| 4 | DanglingToolCallMiddleware | Fills missing tool responses |
| 5 | GuardrailMiddleware | Pre-call tool authorization |
| 6 | SummarizationMiddleware | Reduces context when token threshold hit |
| 7 | TodoListMiddleware | Tracks agent task list |
| 8 | TitleMiddleware | Auto-generates thread title |
| 9 | MemoryMiddleware | Queues async memory updates (30s debounce) |
| 10 | ViewImageMiddleware | Injects images for vision models |
| 11 | SubagentLimitMiddleware | Enforces MAX_CONCURRENT_SUBAGENTS |
| 12 | ClarificationMiddleware | Interrupts on ask_clarification |

**Tool assembly order:**
1. Config-defined tools (resolved via Python reflection)
2. MCP tools (lazy init, mtime-cached)
3. Built-in tools (present_files, ask_clarification, view_image, task, tool_search)
4. Community tools (Tavily, Jina, Firecrawl, image_search)

---

### Sales ADK Agents

**Location**: `aass_agents/`

Google ADK agent team covering B2B sales, marketing, and autonomous product engineering. 26 specialized agents organized into 3 orchestrated teams.

**Key files:**
```
aass_agents/
├── main.py                          # Entry point; exports root_agent
├── agents/                          # 22 agent files
├── tools/                           # 14 tool modules
├── shared/
│   ├── memory_store.py              # SQLite deal memory (sales_memory.db)
│   └── models.py                    # Pydantic models (DealContext, Proposal...)
├── requirements.txt
└── .env.example
```

**Startup modes:**

| Command | Mode |
|---------|------|
| `python main.py` | Interactive CLI |
| `python main.py --web` | ADK web UI |
| `adk api_server main.py` | HTTP API server |

On CLI startup: loads `.env`, then opens interactive loop with `company_orchestrator` as root agent.

---

### MCP Servers (GTM)

**Location**: `mcp-servers/gtm/`

Four stdio MCP servers that expose Sales ADK tools to any MCP-compatible client (including DeerFlow).

```
mcp-servers/gtm/
├── research_server.py    # Web search, enrichment, contacts, news, deep_research
├── crm_server.py         # Salesforce + HubSpot operations
├── memory_server.py      # SQLite deal memory read/write
└── marketing_server.py   # Google Trends, competitor content, RSS, communities
```

Each server uses `mcp.server.stdio` transport. Add them to DeerFlow's `extensions_config.json` to activate.

---

### gstack (Claude Code Skills)

**Location**: `deer-flow/skills/gstack` (symlinked to `~/.claude/skills/gstack`)

A Claude Code skills library by Garry Tan (YC CEO). Provides slash commands and a headless Chromium browser binary for use in Claude Code sessions. Skills are automatically available in any Claude Code session via the symlink.

**Available slash commands:**

| Command | Purpose |
|---------|---------|
| `/ship` | Ship a feature end-to-end |
| `/review` | Code review |
| `/qa` | Run QA with visual browser testing |
| `/qa-only` | QA without shipping |
| `/investigate` | Investigate a bug or issue |
| `/autoplan` | Auto-generate an implementation plan |
| `/plan-eng-review` | Engineering review of a plan |
| `/plan-ceo-review` | CEO review of a plan |
| `/plan-design-review` | Design review of a plan |
| `/design-review` | Review UI/UX design |
| `/canary` | Canary deployment check |
| `/cso` | Security audit |
| `/office-hours` | Office hours / Q&A session |
| `/retro` | Retrospective |
| `/codex` | Code documentation generation |
| `/land-and-deploy` | Land changes and deploy |

**Browse binary (headless Chromium):**

- Binary: `deer-flow/skills/gstack/browse/dist/browse`
- Used by the QA agent for visual testing and screenshot-based verification
- Built with Bun; setup already complete (`bun install && bun run build` in `deer-flow/skills/gstack`)

**Setup (already done):**
```bash
cd deer-flow/skills/gstack
bun install
bun run build
# symlink is active: ~/.claude/skills/gstack → deer-flow/skills/gstack
```

---

## Agents Reference

### DeerFlow

| Agent | Role | Tools |
|-------|------|-------|
| **Lead Agent** | Super agent; routes, delegates, manages state | All tools (sandbox, web, MCP, subagents) |
| **General-Purpose Subagent** | Background research/execution | All tools except `task` |
| **Bash Subagent** | Shell command specialist | `bash` only |

### Sales ADK Agents

#### Top-Level
| Agent | Role |
|-------|------|
| **company_orchestrator** | Root router; routes to sales/marketing/product; maintains deal card |

#### Sales Team
| Agent | Role | Key Tools |
|-------|------|-----------|
| **lead_researcher** | Company research; firmographics, tech stack, contacts, buying signals | `deep_research`, `search_company_web`, `enrich_company`, `find_contacts`, `search_news` |
| **outreach_composer** | Cold emails, LinkedIn DMs, multi-touch sequences | `search_company_web`, memory tools |
| **sales_call_prep** | MEDDIC discovery briefs, talk tracks, objection prep | Research tools, memory tools |
| **objection_handler** | Real-time objection responses using ACCA framework | `search_company_web`, memory tools |
| **proposal_generator** | ROI models, one-pagers, business cases | Research tools, memory tools |
| **crm_updater** | Salesforce/HubSpot: log calls, update stages, create tasks | `sf_*` tools, `hs_*` tools |
| **deal_analyst** | Pipeline health, at-risk flags, forecast, coaching | CRM tools, memory tools |

#### Marketing Team
| Agent | Role | Key Tools |
|-------|------|-----------|
| **marketing_orchestrator** | Routes marketing tasks | — |
| **audience_builder** | ICP definition, tier-1 MQL lists | Research tools, marketing tools |
| **campaign_composer** | Email, LinkedIn, landing page campaigns | Marketing tools |
| **campaign_analyst** | Performance measurement, A/B test analysis | Marketing tools |
| **brand_voice** | Reviews copy for brand consistency | — |
| **content_strategist** | Content briefs, blog posts, SEO-aligned plans | `fetch_rss_feed`, research tools |

#### Product Engineering Team
| Agent | Role | Key Tools |
|-------|------|-----------|
| **product_orchestrator** | Routes product pipeline tasks | — |
| **pm_agent** | PRD creation with market research | Research tools, product memory |
| **architect_agent** | Tech stack selection, file tree generation | — |
| **devops_agent** | GitHub repo, Vercel project, Railway provisioning | `github_tools`, `vercel_tools`, `railway_tools` |
| **db_agent** | SQL schema generation, NeonDB/Supabase provisioning | `neondb_tools`, `supabase_tools` |
| **backend_builder_agent** | FastAPI backend code generation + Railway deploy | `code_gen_tools`, `railway_tools` |
| **frontend_builder_agent** | Next.js + Tailwind UI + Vercel deploy | `code_gen_tools`, `vercel_tools` |
| **qa_agent** | Smoke tests: root, health, auth endpoints | `http_tools` |

---

## Tools Reference

### DeerFlow Built-in Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `bash` | Execute shell commands in sandbox | Local filesystem |
| `ls` | List directory (tree format, 2 levels) | Local filesystem |
| `read_file` | Read file with optional line range | Local filesystem |
| `write_file` | Write/append to file (creates dirs) | Local filesystem |
| `str_replace` | Substring replacement (single or all) | Local filesystem |
| `web_search` | Web search (5 results) | Tavily API |
| `web_fetch` | Fetch + parse web content (4KB) | Jina Reader API |
| `image_search` | Image search | DuckDuckGo Images |
| `present_files` | Make output files visible to user | Local filesystem |
| `ask_clarification` | Request user input (interrupts agent) | User input |
| `view_image` | Read image as base64 (vision models) | Local filesystem |
| `task` | Delegate to subagent (background) | Thread pool |
| `tool_search` | Search available tools by name/desc | Tool registry |

### Sales ADK Research Tools (`tools/research_tools.py`)

| Tool | Description | Backend |
|------|-------------|---------|
| `search_company_web` | Company web search with relevance scoring | DuckDuckGo (free) |
| `enrich_company` | Firmographics + description + tech signals | OpenCorporates + DuckDuckGo |
| `find_contacts` | Decision maker contacts | GitHub API + DuckDuckGo LinkedIn |
| `search_news` | Recent company news (7/30/90/180 days) | DuckDuckGo News |
| `search_product_web` | SaaS products, GitHub repos, tech stacks | DuckDuckGo |
| `deep_research` | Multi-step synthesized research report | DeerFlow LangGraph API (falls back to DuckDuckGo) |

### Sales ADK CRM Tools (`tools/crm_tools.py`)

| Tool | Description | Backend |
|------|-------------|---------|
| `sf_find_opportunity` | Search Salesforce opportunities | Salesforce REST API |
| `sf_update_opportunity` | Update deal stage/fields | Salesforce REST API |
| `sf_log_call` | Log call activity | Salesforce REST API |
| `sf_create_task` | Create follow-up task | Salesforce REST API |
| `sf_get_pipeline` | Get pipeline summary | Salesforce REST API |
| `hs_find_deal` | Search HubSpot deals | HubSpot CRM API v3 |
| `hs_log_note` | Log note on deal | HubSpot CRM API v3 |
| `hs_update_deal` | Update deal properties | HubSpot CRM API v3 |
| `hs_create_task` | Create follow-up task | HubSpot CRM API v3 |

### Sales ADK Marketing Tools (`tools/marketing_tools.py`)

| Tool | Description | Backend |
|------|-------------|---------|
| `get_trending_topics` | Trending topics by region/category | Google Trends (pytrends) |
| `search_competitor_content` | Competitor site content search | DuckDuckGo site: operator |
| `fetch_rss_feed` | Parse RSS/Atom feed | feedparser |
| `search_audience_communities` | Find communities (Reddit, LinkedIn) | DuckDuckGo |

### Sales ADK Infrastructure Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `github_tools` | Repo creation, org management | GitHub API |
| `vercel_tools` | Project provisioning, deploys | Vercel API |
| `railway_tools` | Service provisioning, deploys | Railway API |
| `neondb_tools` | Database provisioning | NeonDB API |
| `supabase_tools` | Project + DB provisioning | Supabase Management API |
| `code_gen_tools` | Code generation utilities | Local |

### Sales ADK Product Memory Tools (`tools/product_memory_tools.py`)

Pipeline state is tracked in SQLite (`product_pipeline.db`) — no external task tracking service needed.

| Function | Description |
|----------|-------------|
| `save_product_state(key, value)` | Persist a product pipeline state value |
| `recall_product_state(key)` | Retrieve a stored product pipeline state value |
| `log_step(step_name, details)` | Write a step entry to `product_step_log` table in `product_pipeline.db` |

---

## MCP Servers Reference

All servers use **stdio transport**. Configure in `deer-flow/extensions_config.json`.

### medium (`medium-mcp-server`)

Browser-based Medium integration using Playwright. No API key required — uses a local login session.

| Tool | Description |
|------|-------------|
| `search-medium` | Search Medium articles by keywords — returns titles, URLs, authors, excerpts |
| `publish-article` | Publish or draft an article (title, markdown content, tags, isDraft) |
| `get-my-articles` | Retrieve your own published articles |

**Used by:** `lead_researcher_agent` (industry research), `pm_agent` (market research), `content_strategist_agent` (content research + publishing)

**Setup:**
```bash
git clone https://github.com/jackyckma/medium-mcp-server.git
cd medium-mcp-server && npm install && npx playwright install chromium && npm run build
node dist/index.js   # run once to complete browser login → saves medium-session.json
```

---

### gtm-research (`research_server.py`)

| Tool | Description |
|------|-------------|
| `search_company_web` | DuckDuckGo company search |
| `enrich_company` | OpenCorporates + DuckDuckGo enrichment |
| `find_contacts` | GitHub + LinkedIn contact finder |
| `search_news` | DuckDuckGo news search |
| `search_product_web` | Tech/SaaS product search |
| `deep_research` | DeerFlow multi-step research (DuckDuckGo fallback) |

### gtm-crm (`crm_server.py`)

| Tool | Description |
|------|-------------|
| `sf_find_opportunity` | Salesforce opportunity search |
| `sf_update_opportunity` | Update Salesforce deal |
| `sf_log_call` | Log call in Salesforce |
| `sf_create_task` | Create Salesforce task |
| `sf_get_pipeline` | Get Salesforce pipeline |
| `hs_find_deal` | HubSpot deal search |
| `hs_log_note` | Log HubSpot note |
| `hs_update_deal` | Update HubSpot deal |
| `hs_create_task` | Create HubSpot task |

### gtm-memory (`memory_server.py`)

| Tool | Description |
|------|-------------|
| `save_deal_context` | Persist deal context to SQLite |
| `recall_deal_context` | Retrieve deal context |
| `list_active_deals` | List all active deals |
| `save_agent_output` | Store agent output artifact |
| `recall_past_outputs` | Retrieve past agent outputs |

### gtm-marketing (`marketing_server.py`)

| Tool | Description |
|------|-------------|
| `get_trending_topics` | Google Trends data |
| `search_competitor_content` | Competitor content search |
| `fetch_rss_feed` | RSS/Atom feed parsing |
| `search_audience_communities` | Community discovery |

---

## Environment Variables

### Required

| Variable | Purpose | Used By |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Claude API access | DeerFlow (if using Claude), `deep_research` tool |
| `GOOGLE_API_KEY` | Gemini API access | Sales ADK (required for Gemini models) |

### Optional — LLM Providers

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI / GPT models |
| `DEEPSEEK_API_KEY` | DeepSeek models |
| `NOVITA_API_KEY` | Novita AI (OpenAI-compatible) |
| `MINIMAX_API_KEY` | MiniMax (OpenAI-compatible) |
| `VOLCENGINE_API_KEY` | Volcengine / Doubao models |
| `MOONSHOT_API_KEY` | Kimi models |
| `MODEL_ID` | Override default model for Sales ADK (default: `gemini-2.0-flash`) |

### Optional — Web & Research Tools

| Variable | Purpose | Notes |
|----------|---------|-------|
| `TAVILY_API_KEY` | Web search (DeerFlow) | DuckDuckGo is free alternative |
| `JINA_API_KEY` | Web fetch (DeerFlow) | Optional |
| `FIRECRAWL_API_KEY` | Web scraping (DeerFlow) | Optional |
| `GITHUB_TOKEN` | GitHub API | Increases rate limits for contact finding |

### Optional — CRM

| Variable | Purpose |
|----------|---------|
| `SALESFORCE_ACCESS_TOKEN` | Salesforce REST API OAuth token |
| `SALESFORCE_INSTANCE_URL` | Salesforce org URL (e.g. `https://yourorg.my.salesforce.com`) |
| `HUBSPOT_API_KEY` | HubSpot Private App token |

### Optional — Infrastructure (Product Pipeline)

| Variable | Purpose |
|----------|---------|
| `VERCEL_TOKEN` | Vercel API token |
| `RAILWAY_TOKEN` | Railway API token |
| `NEONDB_API_KEY` | NeonDB API key |
| `SUPABASE_ACCESS_TOKEN` | Supabase Management API token |

### Optional — Medium MCP

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEDIUM_MCP_PATH` | `../medium-mcp-server` | Path to cloned + built medium-mcp-server repo |

### Optional — IM Channels (DeerFlow)

| Variable | Purpose |
|----------|---------|
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | Feishu integration |
| `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` | Slack integration (Socket Mode) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot |

### Optional — DeerFlow Runtime

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEERFLOW_URL` | `http://localhost:2026` | DeerFlow base URL (used by `deep_research` tool) |
| `DEER_FLOW_CONFIG_PATH` | `./config.yaml` | Override config.yaml path |
| `DEER_FLOW_EXTENSIONS_CONFIG_PATH` | `./extensions_config.json` | Override extensions config path |
| `MAX_CONCURRENT_SUBAGENTS` | `3` | Subagent concurrency limit |
| `MAX_THINKING_TOKENS` | `31999` | Extended thinking token budget |

### Optional — Vertex AI (alternative to Google API Key)

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | GCP region (e.g. `us-central1`) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON |

---

## Startup & Entry Points

### DeerFlow

```bash
cd deer-flow
make dev
```

Starts 4 processes:
| Process | Port | Entry |
|---------|------|-------|
| LangGraph Server | 2024 | `backend/langgraph.json` → `deerflow.agents:make_lead_agent` |
| Gateway API | 8001 | `backend/app/gateway/app.py` (FastAPI) |
| Frontend | 3000 | `frontend/` (Next.js) |
| Nginx proxy | 2026 | Unified entry point |

Config is hot-reloaded from `config.yaml` on mtime change (no restart needed).

### Sales ADK Agents

```bash
cd aass_agents
cp .env.example .env   # fill in keys
pip install -r requirements.txt

python main.py          # interactive CLI
python main.py --web    # ADK web UI
adk api_server main.py  # HTTP API server
```

On startup (CLI mode):
1. Loads `.env`
2. Opens interactive loop with `company_orchestrator` as root agent

### MCP Servers

Each server is a standalone stdio process. Run directly:
```bash
cd mcp-servers/gtm
pip install -r requirements.txt
python research_server.py   # or crm_server.py, memory_server.py, marketing_server.py
```

Or add to DeerFlow's `extensions_config.json`:
```json
{
  "mcp_servers": {
    "gtm-research": {
      "enabled": true,
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/mcp-servers/gtm/research_server.py"]
    }
  }
}
```

---

## Configuration Files

### `deer-flow/config.yaml`

Primary DeerFlow configuration. Copied from `config.example.yaml`.

Key sections:
- `models` — LLM provider definitions (name, class, model ID, API key)
- `tools` / `tool_groups` — Tool definitions and groups
- `sandbox` — Local or Docker sandbox
- `memory` — Memory settings (enabled, storage path, max facts)
- `summarization` — Token threshold, keep policy
- `checkpointer` — State persistence (memory / sqlite / postgres)
- `skills` — Skills directory path
- `title` — Auto-title generation
- `channels` — IM channel config (Feishu, Slack, Telegram)
- `guardrails` — Pre-call authorization provider

Environment variables are resolved with `$VAR_NAME` syntax throughout.

### `deer-flow/extensions_config.json`

MCP servers and skills enabled state. Managed via:
- Direct file edit
- Gateway API: `PUT /api/mcp/config`

```json
{
  "mcp_servers": {
    "server-name": {
      "enabled": true,
      "type": "stdio",
      "command": "python",
      "args": ["path/to/server.py"],
      "env": {}
    }
  },
  "skills": {
    "skill-name": { "enabled": true }
  }
}
```

### `aass_agents/.env`

Copied from `.env.example`. Contains all API keys and configuration for Sales ADK. Loaded via `python-dotenv` at startup.

### `aass_agents/requirements.txt`

Core deps: `google-adk`, `duckduckgo-search`, `pydantic`, `python-dotenv`, `httpx`, `feedparser`, `pytrends`

### `mcp-servers/gtm/requirements.txt`

Core deps: `mcp`, `duckduckgo-search`, `httpx`, `pydantic`, `pytrends`, `feedparser`

---

## Key Ports

| Port | Service | Notes |
|------|---------|-------|
| 2026 | DeerFlow (Nginx proxy) | Main entry point for DeerFlow |
| 2024 | DeerFlow LangGraph Server | Direct LangGraph API |
| 8001 | DeerFlow Gateway API | Models, MCP, skills, memory management |
| 3000 | DeerFlow Frontend | Next.js UI |

---

## Integrations

### DeerFlow ↔ Sales ADK (via `deep_research`)

The `deep_research` tool in `tools/research_tools.py` calls DeerFlow's LangGraph API:

1. `POST /api/langgraph/threads` — creates a research thread
2. `POST /api/langgraph/threads/{id}/runs/stream` — streams SSE events
3. Extracts final synthesized report from `values` events
4. Falls back to DuckDuckGo if DeerFlow is unreachable

Configure `DEERFLOW_URL` env var (default: `http://localhost:2026`).

The same tool is also exposed in `mcp-servers/gtm/research_server.py` for MCP clients.

### Product Pipeline State Tracking (via `product_memory_tools`)

The product engineering pipeline tracks state in SQLite (`product_pipeline.db`) — no external task tracking service is needed.

- `save_product_state(key, value)` / `recall_product_state(key)` — store and retrieve arbitrary pipeline state
- `log_step(step_name, details)` — writes an entry to the `product_step_log` table in `product_pipeline.db`

Each product pipeline agent (pm_agent, architect_agent, devops_agent, db_agent, backend_builder_agent, frontend_builder_agent, qa_agent) calls `log_step()` after completing its phase so the full build history is queryable from SQLite.

### DeerFlow ↔ MCP Servers

MCP servers bridge Sales ADK tools to DeerFlow via stdio. Enable in `extensions_config.json`. DeerFlow lazy-loads MCP tools on first use with mtime-based cache invalidation.

### Sales ADK + DeerFlow ↔ Medium MCP

Medium is integrated via `MCPToolset` in 3 ADK agents and as a tool in `gtm-research` MCP server.

**Agents wired:**
- `lead_researcher_agent` — `search-medium` for prospect industry trends and thought leadership
- `pm_agent` — `search-medium` for competitor articles during PRD market research
- `content_strategist_agent` — `search-medium` for content gap analysis + `publish-article` for publishing

**DeerFlow:** Medium MCP registered in `extensions_config.json` — available to DeerFlow's lead agent for any research or publishing task.

**GTM research server:** `search_medium` tool proxies to the Medium MCP subprocess for MCP clients.

**One-time setup:**
```bash
# 1. Clone and build Medium MCP server
git clone https://github.com/jackyckma/medium-mcp-server.git
cd medium-mcp-server
npm install
npx playwright install chromium
npm run build

# 2. Login once (opens browser, saves medium-session.json)
node dist/index.js

# 3. Set path in .env
MEDIUM_MCP_PATH=../medium-mcp-server

# 4. Build gstack browse binary (already done)
cd deer-flow/skills/gstack
bun install
bun run build
# Symlink active: ~/.claude/skills/gstack → deer-flow/skills/gstack
```

After setup, all agents that use Medium tools will connect automatically via the saved session. No API key required — Medium discontinued public API tokens in 2023; this uses browser automation.

### gstack ↔ Claude Code

gstack slash commands are loaded automatically by Claude Code from `~/.claude/skills/gstack` (symlinked to `deer-flow/skills/gstack`). No explicit configuration is required in a session — commands like `/ship`, `/review`, `/qa`, `/investigate` are available immediately.

The `/qa` and `/qa-only` commands use the headless Chromium `browse` binary at `deer-flow/skills/gstack/browse/dist/browse` for visual page verification and screenshot-based test assertions.

### IM Channels ↔ DeerFlow

Feishu, Slack, and Telegram channels configured in `config.yaml` connect to DeerFlow via `langgraph-sdk` HTTP client. Message flow: external platform → channel → message bus → channel manager → LangGraph thread → streamed response.

Thread persistence: `channel:chat[:topic]` → `thread_id` mapping in JSON file.
