# SL Agents

A self-improving, multi-department AI agent collective with 66 agents across 10 departments, 98 MCP servers, population-based evolution (UCB1), and cross-agent learning.

---

## Quick Start

### Prerequisites

- Python 3.11+
- API keys: set in `.env` (copy from `.env.example`)

### Run

```bash
# Interactive CLI
python main.py

# Web dashboard (default :8080)
python main.py --web
# or
./start.sh [port]    # Unix
start.bat [port]     # Windows

# A2A inter-agent server (:8090)
uvicorn a2a_server:app --port 8090
```

### Install

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## Architecture Overview

```
                        company_orchestrator
                               |
         +-----------+---------+---------+-----------+
         |           |         |         |           |
    sales_orch  product_orch  eng_orch  research_orch  ...
         |           |         |         |
    8 agents    12 agents   8 agents   8 agents
         |           |         |         |
         +-----+-----+---------+---------+
               |
          tool_registry (69 tools)
               |
          mcp_hub (98 servers)
               |
       +-------+-------+
       |       |       |
   evolution  skill   supervisor
    loop     forge    (circuit breakers)
```

### Core Layers

| Layer | Purpose | Key Files |
|-------|---------|-----------|
| **Agents** | Domain-specific AI workers | `agents/` (66 agents) |
| **Tools** | Capabilities agents can call | `tools/` (45 modules) |
| **Pipelines** | DAG-based workflow orchestration | `agents/_shared/pipeline_defs.py` |
| **MCP Hub** | External tool gateway (98 servers) | `agents/_shared/mcp_hub_config.yaml` |
| **Supervisor** | Failure handling, circuit breakers, DLQ | `tools/supervisor.py` |
| **Evolution** | Self-improving agent instructions | `agents/autoresearcher/` |
| **Skill Forge** | 8-stage skill generation pipeline | `agents/skill_forge/` |
| **Cognition Base** | Domain knowledge store with embeddings | `tools/cognition_base_*.py` |

---

## Departments & Agents

### Sales (8 agents)

| Agent | Role | Key Tools |
|-------|------|-----------|
| `sales_orchestrator` | Routes to sub-agents | - |
| `lead_researcher` | Company/contact research | research_tools, http_tools |
| `outreach_composer` | Cold email/sequence drafting | marketing_tools |
| `sales_call_prep` | Pre-call briefings | memory_tools, research_tools |
| `objection_handler` | Objection response library | memory_tools |
| `proposal_generator` | Proposal document creation | document_tools, code_gen_tools |
| `crm_updater` | CRM sync | crm_tools |
| `deal_analyst` | Pipeline analytics | memory_tools |

### Product (12 agents)

| Agent | Role | Key Tools |
|-------|------|-----------|
| `product_orchestrator` | Routes product pipeline | - |
| `pm_agent` | PRD generation | memory_tools |
| `architect_agent` | System design | code_gen_tools, website_cloner_tools |
| `architect_critic_agent` | Architecture review | - |
| `backend_builder` | FastAPI/backend code | code_gen_tools, claude_code_tools |
| `frontend_builder` | React/frontend code | code_gen_tools, website_cloner_tools |
| `db_agent` | Schema design | code_gen_tools |
| `devops_agent` | CI/CD, deployment | railway_tools, vercel_tools |
| `qa_agent` | Test generation | code_gen_tools |
| `setup_agent` | Project scaffolding | claude_code_tools |
| `ship_agent` | Release management | github_tools |
| `builder_agent` | Full-stack builder | code_gen_tools, website_cloner_tools |

### Engineering (8 agents)

| Agent | Role | Key Tools |
|-------|------|-----------|
| `engineering_orchestrator` | Routes engineering tasks | - |
| `solutions_architect` | Architecture decisions | website_cloner_tools |
| `data_engineer` | Data pipelines | graph_tools, neondb_tools |
| `ml_engineer` | ML model development | code_gen_tools |
| `systems_engineer` | Infrastructure | system_env_tools |
| `integration_engineer` | API integrations | http_tools |
| `platform_engineer` | Platform operations | railway_tools, vercel_tools |
| `sdet_agent` | Test infrastructure | engineering_tools |

### Research (8 agents)

| Agent | Role | Key Tools |
|-------|------|-----------|
| `research_orchestrator` | Routes research tasks | - |
| `research_scientist` | Literature review | research_tools, graph_tools |
| `ml_researcher` | ML paper analysis | research_tools |
| `applied_scientist` | Applied research | code_gen_tools |
| `data_scientist` | Data analysis | research_tools |
| `competitive_analyst` | Market intelligence | research_tools, graph_tools |
| `user_researcher` | User research | research_tools |
| `knowledge_manager` | Knowledge graph curation | graph_tools, vault_tools |

### Marketing (7 agents)

| Agent | Role |
|-------|------|
| `marketing_orchestrator` | Routes marketing tasks |
| `audience_builder` | ICP/persona development |
| `campaign_composer` | Campaign content creation |
| `content_strategist` | Content planning |
| `seo_analyst` | SEO optimization |
| `campaign_analyst` | Campaign performance |
| `brand_voice` | Brand consistency |

### QA (7 agents)

| Agent | Role |
|-------|------|
| `qa_orchestrator` | Routes QA tasks |
| `test_architect` | Test strategy design |
| `test_automation_engineer` | Test automation |
| `performance_engineer` | Load/perf testing |
| `security_tester` | Security scanning |
| `qa_engineer` | Manual QA processes |
| `chaos_engineer` | Failure injection |

### Skill Forge (9 agents)

| Agent | Stage | Role |
|-------|-------|------|
| `forge_orchestrator` | - | Pipeline coordinator |
| `intent_parser` | 1 | Parse user intent into TaskSpec |
| `research_swarm` | 2 | 3 parallel researchers |
| `expert_synthesizer` | 3 | Blueprint from research |
| `skill_drafter` | 4 | Draft SKILL.md |
| `critic_panel` | 5 | 3-critic A-HMAD scoring |
| `red_team` | 6 | 100-case battle testing |
| `iteration_agent` | 7 | GEPA reflective loop |
| `promoter_agent` | 8 | Statistical promotion gates |

### Autoresearcher (6 agents)

| Agent | Phase | Role |
|-------|-------|------|
| `autoresearcher_orchestrator` | - | Loop coordinator |
| `evaluator_agent` | 1 | Detect underperformers (progressive validation) |
| `analyzer_agent` | 2 | Causal insight extraction |
| `hypothesis_agent` | 3 | Propose instruction improvements (UCB1 + cognition) |
| `rewriter_agent` | 4 | Atomic instruction patching |
| `rollback_watchdog` | 5 | Stability monitoring + cross-agent transfer |

### Meta

| Agent | Role |
|-------|------|
| `company_orchestrator` | Top-level router across all departments |
| `reflection_agent` | Quality scoring (Accuracy + Completeness + Actionability) |

---

## Pipelines

Declarative DAG templates in `agents/_shared/pipeline_defs.py`. Executed by `tools/parallel_executor.py` with topological sorting.

### Product Build Pipeline

```
pm_agent ──> architect_agent ──┬──> backend_builder (parallel)
                               ├──> frontend_builder (parallel)
                               └──> db_agent (parallel)
                                         │
                                    qa_agent (waits for all)
```

### Research Pipeline

```
competitive_analyst ──┐
user_researcher ──────┼──> knowledge_manager
data_scientist ───────┘
```

### QA Pipeline

```
test_automation_engineer ──┐
performance_engineer ──────┼──> test_architect
security_tester ───────────┘
```

### Running a Pipeline

Pipelines are triggered by the department orchestrator when it recognizes a multi-agent task. The `parallel_executor` handles:
- Dependency resolution (topological sort)
- Parallel execution of independent stages
- Context injection between stages (`{variable}` placeholders)
- Result aggregation

---

## Tool System

### Registry (`tool_registry.yaml`)

Each tool entry has:
```yaml
tool_name:
  module: tools.module_name
  capabilities: [search, analysis, ...]
  departments: [sales, engineering, all]
  tier: fast | std | deep
  description: "What this tool does"
```

**Tiers:**
- `fast` — Lightweight, <1s (lookups, memory reads)
- `std` — Standard, <30s (API calls, searches)
- `deep` — Expensive, <5min (code generation, full pipelines)

### Tool Masking (`agents/_shared/tool_mask.py`)

Agents only see tools relevant to their department and capabilities. The `mcp_hub.get_toolsets(tags)` method filters tools by capability tag.

### Key Tool Categories

| Category | Tools | Description |
|----------|-------|-------------|
| **Memory** | memory_tools, product_memory_tools, skill_memory | Persistent state across sessions |
| **Code Gen** | code_gen_tools, claude_code_tools | LLM-powered code generation |
| **Browser** | browser_tools | Playwright-based web automation |
| **Research** | research_tools, http_tools | Company/contact enrichment |
| **Deploy** | railway_tools, vercel_tools | One-click deployment |
| **Knowledge** | graph_tools, vault_tools | Knowledge graph + Obsidian vault |
| **Website Clone** | website_cloner_tools | 3-phase site cloning pipeline |
| **Evolution** | evolution_tools, cognition_base_tools | Self-improvement infrastructure |
| **Supervision** | supervisor_tools | Circuit breakers, DLQ, audit log |

---

## MCP Hub

Central gateway to 98 external tool servers. Configured in `agents/_shared/mcp_hub_config.yaml`.

### Server Categories

| Category | Count | Examples |
|----------|-------|---------|
| Core Dev | 4 | context7, github, playwright, package-registry |
| Research | 3 | firecrawl, exa-search, brave-search |
| Deploy | 3 | vercel, railway, supabase |
| Productivity | 8 | filesystem, git, memory, duckduckgo, docker |
| Databases | 10 | postgres, duckdb, mongodb, redis, chroma, qdrant, neo4j |
| Search | 6 | arxiv, wikipedia, hacker-news, rss, web-scraper |
| Testing | 5 | jest, pytest, lighthouse, accessibility, ci-config |
| Security | 3 | security-audit, secret-scanner, osint |
| Media | 10 | pollinations, mermaid, excalidraw, svgmaker, charts |
| Industry | 6 | financial, healthcare, legal, education, ecommerce, crm |
| Others | 40 | language tools, cloud, comms, math, utilities |

### Usage

```python
from agents._shared.mcp_hub import mcp_hub

# Get tools by capability tag
tools = mcp_hub.get_toolsets(["docs", "web_search", "thinking"])

# In agent definition
agent = Agent(
    tools=[*local_tools, *mcp_hub.get_toolsets(["docs", "charts"])],
)
```

---

## Databases

5 SQLite databases (WAL mode, async via `asyncio.to_thread`):

### supervisor (sales_memory.db)

| Table | Purpose |
|-------|---------|
| `supervisor_runs` | Pipeline run lifecycle (pending/running/complete/failed) |
| `supervisor_events` | Event log per run |
| `supervisor_circuit_breakers` | Per-agent circuit state (closed/open/half_open) |
| `supervisor_audit_log` | Immutable tamper-evident chain (SHA256 hashes) |
| `supervisor_dlq` | Dead letter queue for non-retryable failures |
| `supervisor_output_validity` | Output quality tracking |

### evolution.db

| Table | Purpose |
|-------|---------|
| `agent_versions` | Instruction version history with status (pending_watch/stable/superseded/rolled_back) |
| `evolution_events` | Quality score signals from reflection_agent |
| `hypotheses` | Root cause diagnoses + proposed instruction patches |
| `evaluator_queue` | Priority queue for underperforming agents |
| `rewrite_locks` | Per-agent mutex preventing concurrent rewrites (72h TTL) |
| `candidate_pool` | Population-based evolution with UCB1 sampling |

### skill_forge.db

| Table | Purpose |
|-------|---------|
| `forge_sessions` | Session lifecycle + task_spec |
| `skill_versions` | Version-tracked skill content + composite scores |
| `battle_test_results` | 100-case test results per version |
| `staging_registry` | Promoted skills awaiting production rollout |

### cognition_base.db

| Table | Purpose |
|-------|---------|
| `cognition_entries` | Domain-keyed heuristics with sentence-transformer embeddings |

### sessions.db

Managed by `agents/_shared/session_store.py` via SQLAlchemy + aiosqlite. Stores conversation state and checkpoints for session persistence.

---

## Self-Evolution System

### Autoresearcher Loop (5 phases)

```
1. EVALUATE ──> 2. ANALYZE ──> 3. HYPOTHESIZE ──> 4. REWRITE ──> 5. WATCH + TRANSFER
   (detect)       (diagnose)     (propose fix)     (patch)       (verify + propagate)
```

**Phase 1 — Evaluate** (evaluator_agent)
- Scans `evolution_events` for unprocessed quality signals
- Groups by agent, flags those with avg score < 6.0
- Progressive validation: quick check → standard eval → deep validation

**Phase 2 — Analyze** (analyzer_agent)
- Causal root cause extraction (not just "score low" but *why*)
- Saves reusable insights to cognition_base.db
- Produces: COVERAGE, CAUSAL ANALYSIS, ACTIONABLE INSIGHTS, REUSABLE PATTERNS

**Phase 3 — Hypothesize** (hypothesis_agent)
- Reads cognition base for domain knowledge
- Uses UCB1 sampling from candidate_pool for population-based evolution
- Produces complete replacement INSTRUCTION with confidence rating

**Phase 4 — Rewrite** (rewriter_agent)
- Atomic disk patching (temp file + os.replace)
- Syntax validation before write
- Baseline score snapshot, status → pending_watch

**Phase 5 — Watch + Transfer** (rollback_watchdog_agent)
- Hourly poll of pending_watch versions
- If improved → stable + cross-agent pattern transfer to sibling agents
- If regressed → rolled_back + restore previous version

### Population Evolution (UCB1)

Each agent maintains up to 10 instruction candidates:
```
UCB1 score = avg_reward + 1.41 * sqrt(ln(total_visits) / visit_count)
```
- Unvisited candidates get infinite UCB1 → exploration first
- Champion promotion when fitness consistently highest
- Auto-retirement below 25th percentile after 5+ visits

### Cross-Agent Learning

When an agent's evolution succeeds:
1. Pattern saved to cognition base (domain-tagged)
2. Transfer hypotheses queued for sibling agents (same department)
3. Role-group transfer for similar agents across departments

---

## Skill Forge Pipeline

8-stage pipeline for generating production-quality skills:

```
1. UNDERSTAND ──> 2. RESEARCH ──> 3. SYNTHESIZE ──> 4. DRAFT
       │               │                │               │
   TaskSpec      3 parallel         Blueprint       SKILL.md v1
                 researchers                            │
                                                        v
5. CRITIQUE ──> 6. BATTLE-TEST ──> 7. ITERATE ──> 8. PROMOTE
       │               │               │               │
  3-critic A-HMAD   100 test       GEPA loop      Statistical
  (composite ≥7.5)   cases       (max 10 iter)    gates → deploy
```

**Scoring:** `composite = 0.35*correctness + 0.25*robustness + 0.20*clarity + 0.20*domain_accuracy`

**Quality gates:**
- Stage 5: composite ≥ 7.5 to pass (else redraft, max 3 cycles)
- Stage 7: target composite ≥ 8.5 (else needs_review=true)
- Stage 8: statistical promotion to staging_registry

---

## Supervisor System

### Failure Handling

| Category | Max Retries | Backoff | Circuit Break |
|----------|-------------|---------|---------------|
| TIMEOUT | 2 | 5s | No |
| RATE_LIMIT | 3 | 30s | No |
| DEPENDENCY | 2 | 10s | Yes |
| AUTH | 0 | - | Yes (immediate) |
| VALIDATION | 0 | - | No |
| INTERNAL | 1 | 5s | Yes |
| UNKNOWN | 1 | 5s | Yes |

### Circuit Breaker States

```
CLOSED ──(failures exceed threshold)──> OPEN ──(cooldown expires)──> HALF_OPEN
   ^                                                                      │
   └──────────────────(success)───────────────────────────────────────────┘
```

### Audit Log

Immutable, tamper-evident chain. Each entry stores:
- `entry_hash` (SHA256 of content)
- `prev_hash` (hash of previous entry)
- `run_id`, `agent_name`, `action`, `detail`, `actor`, `timestamp`

### Dead Letter Queue

Non-retryable failures are captured with checkpoint data for manual or automated resumption.

---

## API Endpoints

### REST API (`api.py` — FastAPI)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/run` | Execute agent pipeline with prompt |
| GET | `/sessions` | List user sessions |
| GET | `/runs/{run_id}` | Fetch run status and metrics |
| GET | `/metrics/pipeline` | Aggregate pipeline stats |
| GET | `/metrics/recent` | Recent runs summary |
| GET | `/circuit-breakers` | View open circuit breakers |
| GET | `/dlq` | List dead-lettered runs |
| GET | `/skills/registry` | List generated skills |
| GET | `/stream/{session_id}` | SSE real-time event stream |

### A2A Protocol (`a2a_server.py`)

Exposes agents over the Agent2Agent protocol for inter-system communication.

```bash
# Default: product_orchestrator
uvicorn a2a_server:app --port 8090

# Custom agent
export A2A_AGENT=company_orchestrator
uvicorn a2a_server:app --port 8090
```

---

## Configuration

### Environment Variables (`.env`)

```bash
# Model (required)
MODEL_ID=openrouter/google/gemini-2.5-flash

# API Keys (as needed)
GITHUB_TOKEN=...
FIRECRAWL_API_KEY=...
EXA_API_KEY=...
BRAVE_API_KEY=...
SUPABASE_URL=...
SUPABASE_KEY=...

# Server
PORT=8080
A2A_PORT=8090

# Obsidian Vault
OBSIDIAN_VAULT_PATH=./obsidian_vault
```

### Model Tiers (`agents/_shared/model.py`)

| Tier | Use Case | Default |
|------|----------|---------|
| `FAST` | Lightweight, frequent calls | Same as MODEL_ID |
| `STD` | Standard development work | MODEL_ID |
| `DEEP` | Complex reasoning, architecture | MODEL_ID |

Supports `thinking_level` per tier for models that support it (Gemini 2.5+).

### Hooks (`hooks.yaml`)

11 lifecycle hooks across 6 event types:
- `pre_agent` — Before agent execution
- `post_agent` — After agent execution
- `on_error` — On failure
- `on_circuit_open` — Circuit breaker tripped
- `on_dlq` — Dead letter queue entry
- `on_session_start` — Session initialization

---

## Project Structure

```
aass_agents/
├── agents/
│   ├── _shared/              # Shared modules (model, mcp_hub, pipelines, etc.)
│   ├── autoresearcher/       # Self-evolution loop (6 agents)
│   ├── engineering/          # Engineering dept (8 agents)
│   ├── marketing/            # Marketing dept (7 agents)
│   ├── product/              # Product dept (12 agents)
│   ├── qa/                   # QA dept (7 agents)
│   ├── research/             # Research dept (8 agents)
│   ├── sales/                # Sales dept (8 agents)
│   ├── skill_forge/          # Skill generation (9 agents)
│   └── company_orchestrator_agent.py
├── tools/                    # 45 tool modules
├── shared/                   # Shared models (Pydantic)
├── skills/                   # SKILL.md templates per department
├── tests/                    # 36 test files
├── main.py                   # CLI + web entry point
├── api.py                    # FastAPI dashboard backend
├── a2a_server.py             # A2A protocol server
├── tool_registry.yaml        # Tool metadata (69 entries)
├── hooks.yaml                # Lifecycle hook definitions
├── requirements.txt          # Python dependencies
├── sl_agents.md              # This file
└── .env                      # Environment configuration
```

---

## Key Statistics

| Metric | Count |
|--------|-------|
| Total agents | 66 |
| Departments | 10 |
| Internal tools | 45 modules |
| Registry tools | 69 entries |
| MCP servers | 98 |
| SQLite databases | 5 |
| Pipeline DAGs | 3 |
| Skill forge stages | 8 |
| Evolution phases | 5 |
| Test files | 36 |
| Lifecycle hooks | 11 |
| Failure categories | 7 |

---

## Onboarding Guide

### For Developers

1. **Clone and install:**
   ```bash
   git clone https://github.com/bhanuprakashd/sl_agents.git
   cd sl_agents/aass_agents
   pip install -r requirements.txt
   playwright install chromium
   cp .env.example .env  # fill in API keys
   ```

2. **Understand the routing:** All user requests enter via `company_orchestrator` which routes to the right department orchestrator, which then routes to specific agents.

3. **Adding a new agent:**
   - Create `agents/{department}/{name}_agent.py`
   - Follow the pattern: `INSTRUCTION` string + `Agent()` constructor
   - Import tools from `tools/` and MCP tools from `mcp_hub`
   - Register in the department orchestrator's `sub_agents` list
   - Add to `agents/_shared/agent_registry.py` AGENT_DEPARTMENT_MAP
   - Add to `tools/cross_agent_learning.py` DEPARTMENT_MAP if needed

4. **Adding a new tool:**
   - Create function in `tools/{module}.py`
   - Register in `tool_registry.yaml` with capabilities, departments, tier
   - Import in relevant agents

5. **Running tests:**
   ```bash
   pytest tests/ -v
   pytest tests/test_asi_evolve.py -v  # evolution tests
   pytest tests/skill_forge/ -v        # skill forge tests
   ```

### For Operators

1. **Monitor health:** `GET /circuit-breakers` shows tripped circuits
2. **Check failures:** `GET /dlq` lists dead-lettered runs
3. **View metrics:** `GET /metrics/pipeline` for aggregate stats
4. **Evolution status:** Run `python main.py` and ask "evolution status"
5. **Seed cognition:** On first run, the cognition base can be seeded from existing skills:
   ```python
   from tools.cognition_base_tools import seed_cognition_from_skills
   seed_cognition_from_skills()
   ```
