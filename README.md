# Sales Agent Team — Google ADK

A multi-agent sales assistant built with [Google ADK](https://github.com/google/adk-python).
Seven specialized agents cover the full B2B sales cycle, coordinated by an orchestrator that
maintains deal context across every step.

## Agents

| Agent | What it does |
|---|---|
| `lead_researcher` | Researches companies — firmographics, news, tech stack, pain points, ICP score |
| `outreach_composer` | Writes cold emails, LinkedIn DMs, follow-ups, and multi-touch sequences |
| `sales_call_prep` | Builds pre-call briefs with MEDDIC discovery questions, talk tracks, objection prep |
| `objection_handler` | Real-time objection responses using the ACCA framework |
| `proposal_generator` | Generates one-pagers, mid-market proposals, and enterprise business cases with ROI models |
| `crm_updater` | Logs calls, updates deal stages and fields, creates follow-up tasks (Salesforce + HubSpot) |
| `deal_analyst` | Pipeline health scores, at-risk flags, forecast, and rep coaching callouts |

## Open-Source Stack

All research tools use free, open-source backends — no paid API keys required to get started:

| Tool | Backend | Key required? |
|---|---|---|
| Web search | [DuckDuckGo](https://github.com/deedy5/duckduckgo_search) | No |
| News search | DuckDuckGo News | No |
| Company enrichment | [OpenCorporates](https://opencorporates.com/info/about) + DuckDuckGo | No |
| Contact finder | DuckDuckGo LinkedIn search + GitHub API | GitHub token optional |
| CRM — Salesforce | Salesforce REST API | Yes (Connected App) |
| CRM — HubSpot | HubSpot CRM API v3 | Yes (Private App token) |

## Setup

```bash
# 1. Clone and enter directory
cd sales-adk-agents

# 2. Create virtual environment
python -m venv .venv && source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — at minimum set GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT
```

## Run

```bash
# Interactive CLI
python main.py

# ADK web UI (browser)
python main.py --web

# ADK API server
adk api_server main.py
```

## Example prompts

```
Research Acme Corp — they're 200 people in logistics SaaS
Write a cold email to the VP of Sales at Acme
Prep me for my discovery call with Notion tomorrow
They said our price is too high
Write a proposal for a mid-market logistics company
Log my call — 30 min discovery with Sarah Chen, she confirmed the pain around manual reporting
Pipeline review for Q1
Run the full workflow for Stripe
```

## Project structure

```
sales-adk-agents/
├── main.py                        # Entry point — exports root_agent
├── agents/
│   ├── sales_orchestrator_agent.py  # Root agent — routes and maintains deal card
│   ├── lead_researcher_agent.py
│   ├── outreach_composer_agent.py
│   ├── sales_call_prep_agent.py
│   ├── objection_handler_agent.py
│   ├── proposal_generator_agent.py
│   ├── crm_updater_agent.py
│   └── deal_analyst_agent.py
├── tools/
│   ├── research_tools.py          # DuckDuckGo + OpenCorporates + GitHub
│   └── crm_tools.py               # Salesforce + HubSpot REST tools
├── shared/
│   └── models.py                  # Pydantic models (DealContext, Proposal, etc.)
├── tests/
│   ├── conftest.py
│   └── test_agents.py
├── requirements.txt
├── pytest.ini
└── .env.example
```

## Tests

```bash
pytest
```

Tests run against the live Gemini model. Set `MODEL_ID=gemini-2.0-flash` and a valid
`GOOGLE_API_KEY` before running.
