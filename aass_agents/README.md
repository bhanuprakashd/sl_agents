# SL Agents — Multi-Department AI Agent System

A production-grade multi-agent enterprise system built with [Google ADK](https://github.com/google/adk-python).
68 specialized agents across 8 departments, coordinated by a company-level orchestrator.
Ships full-stack applications from a single prompt.

## Architecture

```
                        company_orchestrator (LlmAgent)
                                    |
        ┌───────────┬───────────┬───────────┬───────────┬───────────┬───────────┬───────────┐
        v           v           v           v           v           v           v           v
      Sales    Marketing   Product    Engineering  Research     QA       AutoResearcher  SkillForge
     (8 agents) (7 agents) (11 agents) (8 agents) (8 agents) (7 agents)  (5 agents)    (9 agents)
```

### Product Pipeline (SequentialAgent)

The product department uses ADK `SequentialAgent` for deterministic multi-phase builds:

```
setup_agent → pm_agent → architect_agent → builder_agent → qa_agent → ship_agent
     |            |              |               |             |           |
  product_id   PRD JSON    architecture     build result    QA report   final JSON
   (state)      (state)      (state)          (state)       (state)     (output)
```

Each agent saves output to session state via `output_key`, and the next agent reads it.

## Departments

| Department | Orchestrator | Agents | Purpose |
|---|---|---|---|
| Sales | `sales_orchestrator` | 8 | Lead research, outreach, call prep, objections, proposals, CRM, deal analysis |
| Marketing | `marketing_orchestrator` | 7 | Audience building, campaigns, content strategy, SEO, brand voice, analytics |
| Product | `product_orchestrator` | 11 | PRD, architecture, build, QA, ship — full app from prompt to localhost |
| Engineering | `engineering_orchestrator` | 8 | Data engineering, ML, platform, integration, systems, SDET |
| Research | `research_orchestrator` | 8 | Competitive analysis, user research, data science, ML research, knowledge mgmt |
| QA & Testing | `qa_orchestrator` | 7 | Test architecture, automation, performance, security, chaos engineering |
| AutoResearcher | `autoresearcher_orchestrator` | 5 | Self-evolving quality loop: hypothesize, evaluate, rewrite, rollback |
| Skill Forge | `forge_orchestrator` | 9 | Skill drafting, research swarm, expert synthesis, red team, critic panel |

## Tools

| Category | Tools | Purpose |
|---|---|---|
| Research | `agent_reach_tools` | GitHub search, Reddit, YouTube, RSS, web scraping |
| Build | `claude_code_tools` | Multi-phase iterative builds via Claude Code CLI |
| Memory | `memory_tools`, `product_memory_tools`, `skill_memory` | SQLite-backed state persistence |
| Deployment | `railway_tools`, `vercel_tools` | Cloud deployment |
| CRM | `crm_tools` | Salesforce + HubSpot integration |
| Monitoring | `supervisor`, `cost_tracker`, `build_progress` | Pipeline supervision, cost tracking |
| Feedback | `human_feedback_loop` | Human-in-the-loop review cycle |
| Browser | `browser_tools`, `http_tools` | Headless browsing, smoke tests |
| Hooks | `hook_engine`, `hook_handlers` | Declarative pre/post agent hooks |

## Setup

```bash
# 1. Clone and enter directory
cd aass_agents

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — set MODEL_ID and required API keys

# 4. Install GitHub CLI (for agent research tools)
winget install GitHub.cli   # Windows
brew install gh             # macOS
```

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `MODEL_ID` | Yes | `gemini-2.0-flash` | Primary model (e.g. `openrouter/google/gemini-2.5-flash`) |
| `MODEL_ID_FAST` | No | Falls back to MODEL_ID | Cheap model for research agents |
| `MODEL_ID_DEEP` | No | Falls back to MODEL_ID | Powerful model for architecture decisions |
| `ANTHROPIC_API_KEY` | For builds | — | Required for Claude Code CLI (build phase) |
| `MAX_RPM` | No | `38` | Rate limit (requests per minute) |

## Run

```bash
# Interactive CLI
python -X utf8 main.py

# FastAPI server + dashboard
python -X utf8 -m uvicorn api:app --port 8080

# ADK web UI
python main.py --web
```

The `-X utf8` flag prevents Unicode encoding errors on Windows.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/run` | Stream agent execution via SSE |
| `GET` | `/api/status` | System status |
| `GET` | `/api/status/live` | Expanded status with supervisor stats |
| `GET` | `/api/skills` | Staged skills registry |
| `GET` | `/api/supervisor/stats` | KPI summary |
| `GET` | `/api/supervisor/circuits` | Circuit breaker states |
| `GET` | `/api/supervisor/dlq` | Dead letter queue |
| `GET` | `/api/supervisor/runs` | Pipeline run history |
| `GET` | `/api/supervisor/events` | Supervisor events |
| `GET` | `/api/evolution/history` | Agent evolution history |
| `GET` | `/api/forge/registry` | Skill forge registry |
| `GET` | `/api/agents/status` | All agent statuses |

## Example Prompts

```
# Product — builds a full-stack app
build an application that can be used in space travel
build a SaaS dashboard for managing shrimp farms

# Sales
Research Acme Corp — they're 200 people in logistics SaaS
Write a cold email to the VP of Sales at Acme

# Marketing
Create a content strategy for our new developer tool launch
Build an SEO analysis for our landing page

# Research
Run competitive analysis on Notion vs Coda vs Slite
```

## Project Structure

```
aass_agents/
├── main.py                          # Entry point — root_agent + callbacks
├── api.py                           # FastAPI server + SSE streaming
├── dashboard.html                   # Enterprise dashboard UI
├── agents/
│   ├── company_orchestrator_agent.py  # Top-level router
│   ├── _shared/
│   │   ├── model.py                 # Smart model factory (FAST/STD/DEEP tiers)
│   │   ├── context_rules.py         # KV-cache prefix, error preservation
│   │   ├── reflection_agent.py      # Shared reflection utilities
│   │   └── agent_registry.py        # Agent registration
│   ├── product/
│   │   ├── product_orchestrator_agent.py  # SequentialAgent pipeline
│   │   ├── setup_agent.py           # Pipeline initialization
│   │   ├── pm_agent.py              # PRD generation (output_key)
│   │   ├── architect_agent.py       # Tech stack design (output_key)
│   │   ├── builder_agent.py         # Claude Code builds (output_key)
│   │   ├── qa_agent.py              # Smoke tests (output_key)
│   │   └── ship_agent.py            # Finalization (output_key)
│   ├── sales/                       # 8 sales agents
│   ├── marketing/                   # 7 marketing agents
│   ├── engineering/                 # 8 engineering agents
│   ├── research/                    # 8 research agents
│   ├── qa/                          # 7 QA agents
│   ├── autoresearcher/              # 5 self-evolution agents
│   └── skill_forge/                 # 9 skill creation agents
├── tools/                           # 42 tool modules
├── skills/                          # SKILL.md files for each agent
├── hooks.yaml                       # Declarative hook config
├── tool_registry.yaml               # Tool registry
├── requirements.txt
└── .env.example
```

## Key Design Decisions

- **SequentialAgent for pipelines**: ADK's LlmAgent treats sub-agent text as final response.
  SequentialAgent runs all agents in order, passing data via session state.
- **output_key for state flow**: Each agent saves its output to session state automatically.
  Next agent reads it via `{state_key}` templates or `read_state()` tool.
- **Tiered models**: `FAST` for research, `STD` for most work, `DEEP` for architecture.
  Configured via `MODEL_ID`, `MODEL_ID_FAST`, `MODEL_ID_DEEP` env vars.
- **Retry with jitter**: MALFORMED_FUNCTION_CALL errors from providers get automatic retry
  with exponential backoff + full jitter.
- **Rate limiting**: Global RPM limiter prevents provider throttling.

## Tests

```bash
pytest
```
