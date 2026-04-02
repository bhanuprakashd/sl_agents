# SL Agent OS — Enterprise Command Center Design

**Date:** 2026-03-28
**Status:** Draft
**Scope:** Complete rewrite of `aass_agents/dashboard.html` + new API endpoints in `aass_agents/api.py`

---

## 1. Overview

Transform the current 1150-line single-file dashboard into an enterprise-grade command center — a one-stop application for monitoring, operating, and interacting with all 62 agents across 9 departments. Zero external dependencies (pure HTML/CSS/JS/SVG).

### Goals
- Real-time system observability (circuit breakers, DLQ, pipeline runs, events)
- Interactive org chart with all 62 agents and live status overlay
- Company Pipeline: the hero view showing end-to-end autonomous orchestration
- Console for running prompts with rich SSE activity feed
- All 8 department workflows visualized
- Full supervisor observability (circuit breakers, DLQ, pipeline runs, event log, evolution history)
- Enterprise dark theme with glass morphism, smooth animations, professional polish

### Constraints
- Zero external CDN dependencies — pure HTML/CSS/JS/SVG
- Single HTML file (dashboard.html) + API expansion in api.py
- Must work when served via `uvicorn api:app --reload --port 8080`
- All live data from new API endpoints; no hardcoded agent data where API can provide it

---

## 2. Layout Shell

### Structure
```
┌──────────────────────────────────────────────────────┐
│  TOP STATUS BAR (48px) — live system pulse           │
├────────┬─────────────────────────────────────────────┤
│        │                                             │
│  SIDE  │           MAIN CONTENT AREA                 │
│  BAR   │     (smooth crossfade between views)        │
│ 260px  │                                             │
│ collap-│                                             │
│ sible  │                                             │
│ → 64px │                                             │
│        │                                             │
└────────┴─────────────────────────────────────────────┘
```

### Top Status Bar (48px, always visible)
- Left: SL Agent OS logo wordmark + "Command Center"
- Center: live ticker chips — `62 Agents` · `Running: N` · `Breakers: N open` · `DLQ: N` · `Model: <model_id>`
- Right: connection status dot (green/red) + last refresh timestamp
- Polls `GET /api/status/live` every 5 seconds
- Chips turn red/amber when values are non-zero for error states

### Sidebar (260px, collapsible to 64px)
- Glass panel: `background: rgba(18,19,26,0.85); backdrop-filter: blur(12px)`
- 11 navigation items with inline SVG icons (no emoji):
  1. Dashboard (grid icon)
  2. Company Pipeline (play-circle icon)
  3. Org Chart (sitemap icon)
  4. Agents (users icon)
  5. Console (terminal icon)
  6. Workflows (git-branch icon)
  7. Handoffs (shuffle icon)
  8. Skill Forge (hammer icon)
  9. RAMP (beaker icon)
  10. Tech Stack (layers icon)
  11. Supervisor (shield icon)
- Active item: 3px indigo left border bar + filled icon + white text
- Hover: `rgba(255,255,255,0.04)` background
- Collapsed mode: icon-only with tooltip on hover
- Footer: collapse toggle button + "v1.0" badge

### Theme
- Background: `#0a0b10` (base), `#12131a` (surface), `#1a1c28` (elevated)
- Glass: `backdrop-filter: blur(12px)` on sidebar, modals, slide-out panels
- Border: `rgba(255,255,255,0.06)` throughout
- Text: `#e2e8f0` (primary), `#64748b` (muted), `#94a3b8` (secondary)
- Accent: `#6366f1` (indigo primary)
- Department colors:
  - Sales: `#3b82f6` (blue)
  - Marketing: `#a855f7` (purple)
  - Product: `#10b981` (emerald)
  - Engineering: `#f59e0b` (amber)
  - Research: `#14b8a6` (teal)
  - QA: `#ef4444` (red)
  - Autoresearcher: `#f97316` (orange)
  - Skill Forge: `#ec4899` (pink)
  - Shared: `#6366f1` (indigo)
- Typography: `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`
- Transitions: `200ms ease` on all interactive elements
- Scrollbars: thin (6px), `#1a1c28` track, `#334155` thumb
- Animations: `@keyframes pulse` for active states, smooth crossfade on view transitions

### Responsive Behavior
- >= 1400px: full sidebar (260px) + main content
- 1000-1399px: collapsed sidebar (64px) + main content
- < 1000px: sidebar hidden (hamburger toggle), top bar stacks vertically, grids collapse to single column

---

## 3. View: Dashboard (Command Center Home)

### Row 1 — KPI Cards (6 cards, horizontal scroll on mobile)
| Card | Value Source | Color | Click Target |
|------|-------------|-------|-------------|
| Total Agents | Hardcoded `62` | indigo | Agents view |
| Departments | Hardcoded `9` | blue | Org Chart |
| Active Runs | `/api/supervisor/stats` → `active_runs` | green (pulse when > 0) | Company Pipeline |
| Breakers Open | `/api/supervisor/stats` → `open_breakers` | green normal, red when > 0 | Supervisor > Circuits |
| DLQ Entries | `/api/supervisor/stats` → `dlq_count` | green normal, amber when > 0 | Supervisor > DLQ |
| Forged Skills | `/api/forge/registry` → count | pink | Skill Forge |

Card style: glass surface, 64px-tall number, 12px label, department-colored left accent bar, subtle icon top-right.

### Row 2 — Department Health Grid (3x3 grid)
9 cards, one per department. Each card:
- Department name + colored top border (3px)
- Agent count (e.g., "7 agents")
- Status dot: green (all healthy) / amber (half-open breaker) / red (open breaker or DLQ)
- Mini agent name list (dimmed idle, bright active)
- Data from `/api/agents/status` aggregated by department
- Click → navigates to Agents view filtered by that department

### Row 3 — Two-column Split

**Left (50%): Live Event Stream**
- Polls `GET /api/supervisor/events?limit=50` every 5s
- Each row: relative timestamp, agent name (department-colored), event type badge
- Badge colors: `agent.called` (blue), `agent.returned` (green), `circuit.opened` (red), `dlq.pushed` (amber), `run.failed` (red)
- Auto-scrolls to bottom, "View all" link → Supervisor > Event Log
- Empty: "No recent activity"

**Right (50%): Active Pipelines**
- Data from `GET /api/supervisor/runs?status=running`
- Each row: truncated run_id, pipeline_type badge, status pill, step progress (current/total), elapsed time
- Click row → Company Pipeline view with that run
- Empty: "No active pipelines"

### Row 4 — System Alerts (conditional)
Only rendered when problems exist:
- Open breakers → red banner listing agent names
- DLQ entries → amber banner with count
- Hidden when all-clear

---

## 4. View: Company Pipeline (Hero View)

### Pipeline Launcher (top)
- Large input bar: placeholder "Describe what you want to build, research, or create..."
- Run button (indigo) with dropdown: `Run Autonomous` | `Run with Approval Gates`
- Quick-start chips below: "Build a SaaS app", "Research competitor X", "Forge a skill for Y", "Full GTM for product Z", "Improve agent quality"
- Triggers `POST /api/run` with SSE streaming

### Live Pipeline Visualization (middle)
When running: horizontal flow diagram built in real-time from SSE events.
- Each node: rounded rect, department-colored top border, agent name, status icon
- Status icons: `○` pending, `●` active (pulse animation), `✓` done (green), `✗` error (red)
- Nodes appear dynamically as orchestrator invokes agents
- Connecting lines animate left-to-right (small dot traveling the path)
- Cross-department handoffs: thicker bridge lines with protocol label
- Implementation: pure SVG, dynamically built via JS as SSE events arrive
- Node click → slide-out detail panel (right side, 400px)

When idle: static architecture diagram showing company_orchestrator at center, 8 department clusters around it with dashed potential flow paths. Each department cluster clickable → Workflows view.

### Slide-out Detail Panel (on node click)
- Agent name + department badge
- Input received (expandable)
- Output produced (expandable)
- Tools called (list with args)
- Duration
- Reflection gate result
- Circuit breaker state
- Close button (X) or click outside

### Pipeline History (bottom)
- Table of recent 20 runs from `GET /api/supervisor/runs?limit=20`
- Columns: Run ID, Type, Status (pill), Steps, Duration, Started
- Status pills: running (blue pulse), completed (green), failed (red), blocked (amber)
- Click row → replays flow diagram from stored event data
- Filter by: pipeline_type, status, date range

---

## 5. View: Org Chart (Interactive Hierarchy)

### Canvas
- Full-width SVG with pan (click-drag) and zoom (scroll wheel)
- Zoom controls top-right: +, -, fit-to-screen, reset

### Node Layout
- Top-down tree: company_orchestrator at top, 8 department orchestrators below, leaf agents below each
- Orchestrator nodes: 200x80px, larger font
- Leaf nodes: 160x60px
- Vertical spacing: 100px between levels, horizontal auto-distributed

### Node Design
- Rounded rect with department-colored top border (3px)
- Agent name (bold 13px), role subtitle (dimmed 11px)
- Status dot: green/amber/red from circuit breaker state
- One-liner capability text (10px, muted)

### Interactions
- Click orchestrator → expand/collapse children (smooth 300ms animation)
- Click leaf agent → detail modal (inputs, outputs, tools, reflection, TTL, circuit state, recent events)
- Hover → glow effect in department color + tooltip
- Default: all expanded, all 62 agents visible

### Connection Lines
- Solid: orchestrator → children (1.5px, department-colored at 50% opacity)
- Dashed: cross-department handoffs (Marketing↔Sales, Research→Sales/Marketing, Product→Marketing, QA→Engineering/Product, Autoresearcher→All)
- Handoff lines labeled on hover with protocol name

### Live Mode Toggle (top-left button)
- ON: active agents pulse, data flow dots animate along connections, idle agents dimmed
- OFF: static view, all agents same brightness

### Toolbar
- Department filter chips: All, Sales, Marketing, Product, Engineering, Research, QA, Autoresearcher, Forge
- Search input: highlights + auto-pans to matched agent
- Layout toggle: Tree (default) | Radial (center-out)

---

## 6. View: Agents (Filterable Grid)

### Toolbar
- Department filter chips with counts: All (62), Orchestrators (9), Sales (7), Marketing (6), Product (7), Engineering (7), Research (7), QA (6), Autoresearcher (4), Skill Forge (9), Shared (1)
- Search input: filters by name, capability, tool name
- Sort: Name A-Z, Department, Status (errors first), TTL
- View toggle: Grid | Table

### Agent Card (grid view)
Glass surface card with:
- Header: icon placeholder + agent name (bold) + department badge (pill)
- Status row: status dot + "Healthy"/"Warning"/"Error" + TTL value + cache validity
- Two-column: Inputs (left) | Outputs (right) — each as compact list items with colored left border
- Tools: pill chips (monospace, purple-tinted)
- Reflection Gate: muted box with gate criteria text
- Data: static agent metadata merged with live status from `/api/agents/status`

### Agent Card Click → inline expand
Card grows to show:
- Full inputs/outputs lists (un-truncated)
- All tools with descriptions
- Full reflection gate text
- Recent 5 events from `/api/supervisor/events?agent=<name>&limit=5`
- Circuit breaker detail: state, failure_count, last_failure_at, opened_at

### Table View (compact)
| Agent | Department | Status | Circuit | TTL | Cache | Last Run | Tools Count |
Sortable columns, click row → same inline expand.

---

## 7. View: Console (Prompt Runner)

### Input Bar (top)
- Full-width text input with placeholder
- Run button (indigo) + Clear button (ghost)
- Session indicator: current session ID + "New Session" button
- Recent prompts: last 5 as clickable chips (stored in localStorage)

### Two-Pane Layout

**Left (50%): Agent Activity Feed**
- Header: "Agent Activity" + event count + auto-scroll toggle
- Event rows by type:
  - `agent_text`: `[agent_name]` (dept color, mono) + text preview (expandable on click)
  - `tool_call`: `[agent_name]` + blue tool badge + args (mono, dimmed)
  - `tool_result`: indented 20px, green `✓` + result preview
  - `final`: green highlight banner
  - `error`: red highlight banner
- Each row: relative timestamp on right edge
- Department color bar on left edge (3px)
- Max height with overflow scroll, auto-scroll to bottom

**Right (50%): Final Output**
- Header: "Final Output" + copy button
- Rendered text with proper whitespace
- Streaming: shows intermediate text dimmed, replaced by final
- Empty: "Output will appear here..." with subtle pulse

### Bottom Status Bar
- Left: status dot (pulse when running) + status text
- Center: active agent name (dept-colored mono)
- Right: elapsed time counter
- Connection error: shows backend requirement note on first fetch failure

### SSE Implementation
Same as current: `POST /api/run` → SSE stream. Event types: `run_start`, `tool_call`, `tool_result`, `agent_text`, `final`, `error`, `done`.

---

## 8. View: Workflows (All Department Pipelines)

### Sub-tab Navigation (8 tabs)
Sales | Marketing | Product | Engineering | Research | QA | Autoresearcher | Skill Forge

### Step Flow Rendering
Vertical step flow per pipeline:
- Circle with step number (department-colored border)
- Vertical connecting line between steps
- Step content card: agent name (clickable → Agents view), title, description, output box
- Cross-department handoff steps: dashed border, bridge icon, different accent

### Pipeline Data

**Sales (10 steps):**
1. [MQL from Marketing] → prospect profile
2. outreach_composer → cold email + LinkedIn DM
3. [Wait for response]
4. sales_call_prep → call brief + MEDDIC questions
5. objection_handler → ACCA responses
6. crm_updater → log call + update stage
7. outreach_composer → follow-up
8. proposal_generator → proposal + ROI model
9. crm_updater → log proposal + next step
10. deal_analyst → pipeline review
→ [Win/Loss feedback to Marketing]

**Marketing (8 steps):**
1. audience_builder → ICP segments + MQL packages
2. campaign_composer → email sequence + ads + landing page
3. brand_voice → copy review
4. seo_analyst → keyword strategy + content gaps
5. content_strategist → content pillars + briefs
6. [MQL Handoff → Sales]
7. campaign_analyst → performance review
8. campaign_composer → optimized second wave

**Product (8 steps):**
1. pm_agent → PRD
2. architect_agent → architecture + file tree
3. devops_agent → GitHub + Railway + Supabase provisioning
4. db_agent → SQL schema + migrations
5. devops_agent → inject env vars
6. backend_builder_agent → FastAPI code + deploy
7. frontend_builder_agent → Next.js + Tailwind + deploy
8. qa_agent → smoke test live deployment

**Engineering (7 steps):**
1. solutions_architect_agent → system design + ADRs
2. data_engineer_agent → data pipeline spec
3. ml_engineer_agent → training pipeline
4. systems_engineer_agent → toolchain setup
5. integration_engineer_agent → API connectors
6. platform_engineer_agent → IaC + CI/CD
7. sdet_agent → integration tests

**Research (7 steps):**
1. research_scientist_agent → literature review
2. ml_researcher_agent → SOTA benchmarks
3. applied_scientist_agent → feasibility report
4. data_scientist_agent → experiment design
5. competitive_analyst_agent → market analysis
6. user_researcher_agent → personas + interviews
7. knowledge_manager_agent → synthesis brief

**QA (6 steps):**
1. test_architect_agent → test strategy + quality gates
2. test_automation_engineer_agent → automated suites
3. performance_engineer_agent → load test baselines
4. security_tester_agent → OWASP + pen test
5. qa_engineer_agent → manual QA + bug reports
6. chaos_engineer_agent → failure injection

**Autoresearcher (4 phases — circular flow):**
Rendered as a cycle diagram (not linear):
- EVALUATE (evaluator_agent) → HYPOTHESIZE (hypothesis_agent) → REWRITE (rewriter_agent) → ROLLBACK WATCHDOG (rollback_watchdog_agent) → back to EVALUATE
- Each phase: agent name, description, DB tables touched, transition conditions
- Arrows labeled: "underperformance detected", "hypothesis ready", "patch applied", "score < baseline → rollback" / "score >= baseline → stable"

**Skill Forge (8 stages):**
Linear flow using same step pattern:
1. intent_parser_agent → TaskSpec
2. research_swarm_agent → 3 parallel researchers
3. expert_synthesizer_agent → ExpertBlueprint
4. skill_drafter_agent → SKILL.md v0
5. critic_panel_agent → A-HMAD evaluation (gate >= 7.5)
6. red_team_agent → 100 test cases
7. iteration_agent → GEPA loop (gate >= 8.5)
8. promoter_agent → staging registry

---

## 9. View: Handoffs (Cross-Team Protocols)

6 handoff cards (glass surface):
1. **Marketing → Sales (MQL):** Tier 1 MQL packages with ICP score, intent signal, outreach angle. Fields: company, contact, ICP score, intent signal, pain point, channel rec, content engaged.
2. **Sales → Marketing (Win/Loss):** Deal outcome, objections, competitor mentioned, helpful content, ICP profile. Routes to: audience_builder, content_strategist, campaign_composer.
3. **Research → Sales/Marketing (Competitive Intel):** Competitor profiles, battle cards, positioning briefs. Requires reflection-check. Routes to: objection_handler (sales), brand_voice + campaign_composer (marketing).
4. **Product → Marketing (GTM Auto-Trigger):** product_name, live_url, features, target_persona, campaign_angle. Triggers: campaign_composer, content_strategist, seo_analyst.
5. **QA → Engineering/Product (Quality Gates):** PASS → clear for next stage. CRITICAL DEFECT → block + structured defect report. Routes to: engineering_orchestrator or product_orchestrator.
6. **Autoresearcher → All (Evolution):** hypothesis, target_agent, versions, evaluation_score, rollback_trigger.

Each card: source → target with department colors, field list with colored left borders, routing info.

**Shared Context Table (bottom):**
6 rows showing cross-team data sharing (company profiles, ICP scores, objections, win/loss, proposals, campaign assets) with Created By, Used By, Storage columns.

Agent names clickable → Agents view.

---

## 10. View: Skill Forge

- **Top:** trigger examples card + promotion gates sidebar (gate >= 7.5, CI >= 0.80, composite >= 8.5, kappa >= 0.70, 5 prod runs)
- **Middle:** 8-stage pipeline as horizontal connected cards with stage number, icon, agent name, description, gate thresholds
- **Scoring formula:** 4-column grid: Correctness (0.35), Robustness (0.25), Clarity (0.20), Domain Accuracy (0.20)
- **Bottom:** Staged Skills Registry from `GET /api/forge/registry`. Skill cards with: name, domain, department, composite score, production runs, review status (Staged/Needs Review), file path. Refresh button.

---

## 11. View: RAMP

4 glass cards in a row:
1. **Reflection Loop** — 3-layer quality enforcement. Metric: +28pp accuracy.
2. **Long-Term Memory** — Shared SQLite store, cross-team learning. Metric: +20pp recall.
3. **Output Verification** — Tool-level verification, DuckDuckGo scoring, MQL validation. Metric: prevents bad data propagation.
4. **Agent Evolution** — Autoresearcher self-improvement loop. Metric: continuous quality improvement across all 62 agents.

---

## 12. View: Tech Stack

11 sections as styled tables:
1. **Core:** google-adk, fastapi, litellm, pydantic, python-dotenv, httpx
2. **Execution Layer:** Claude Code CLI, SQLite WAL, subprocess
3. **AI Models:** nemotron-3-super (primary), gemini-2.0-flash (fallback)
4. **Research & Marketing Tools:** DuckDuckGo, Google Trends, RSS/feedparser
5. **Deployment Tools:** GitHub API, Vercel, Railway, Supabase, NeonDB
6. **Document Ingestion:** PDF (pdfplumber), DOCX (python-docx), MD, HTML, XLSX, CSV
7. **Code Generation:** Claude API (sonnet-4-6, haiku-4-5)
8. **CRM Integrations:** Salesforce (5 tools), HubSpot (4 tools)
9. **Database Schemas:** all 4 DBs with 19 tables total:
   - sales_memory.db: deal_memory, query_history
   - supervisor tables: supervisor_runs, supervisor_events, supervisor_circuit_breakers, supervisor_dlq, supervisor_output_validity
   - skill_forge.db: forge_sessions, research_bundles, skill_versions, battle_test_results, staging_registry
   - evolution.db: agent_versions, evolution_events, hypotheses, evaluator_queue, rewrite_locks
   - product_pipeline.db: product_pipeline_state, product_step_log
10. **Memory & Persistence:** session (ADK InMemory), deal memory, query history, product state, skill forge state, evolution state
11. **Environment Variables:** all required + optional env vars with descriptions

---

## 13. View: Supervisor (Full Observability)

### Sub-tabs (6)
Overview | Circuit Breakers | Dead Letter Queue | Pipeline Runs | Event Log | Evolution History

**Overview:**
- 4 KPI cards: Open Breakers, DLQ Entries, Active Runs, Events (24h)
- Combined alert list below

**Circuit Breakers:**
- Table: all 62 agents — Agent, Department, State (pill), Failure Count, Last Failure, Opened At
- Sort by state (open first), filter by department
- Open rows highlighted red
- Reset button per row → `POST /api/supervisor/circuits/{agent}/reset`

**Dead Letter Queue:**
- Table: Run ID, Pipeline Type, Blocked On, Last Error (expandable), Completed Steps, Created At
- Resume button per row → `POST /api/supervisor/dlq/{run_id}/resume`
- Empty: green "No blocked pipelines"

**Pipeline Runs:**
- Table: Run ID, Type, Status (pill), Step (current/total), Context (truncated), Created, Updated, Duration
- Filter: status, pipeline_type, date range
- Click row → Company Pipeline view
- Auto-refresh every 5s when running

**Event Log:**
- Scrollable table: Timestamp, Run ID, Agent (dept-colored), Event Type (badge), Payload (expandable JSON)
- Badge colors by event type
- Filter: agent, event_type, run_id, date range
- Search payload text
- Paginated: 50 per page

**Evolution History:**
- Table from evolution.db: Agent, Version, Status (pill: pending_watch/stable/rolled_back), Score Baseline, Hypothesis (truncated), Confidence, Created At
- Expandable: full hypothesis, root cause, instruction diff
- Filter: agent, status

---

## 14. New API Endpoints (api.py)

All new endpoints read from existing SQLite databases. No new tables needed.

### Agent Registry
```
GET /api/agents
  → [{name, department, title, capabilities, inputs, outputs, tools, reflection, ttl}]
  Source: new comprehensive AGENT_REGISTRY dict in api.py covering all 62 agents across 9 departments.
  Note: register_agents.py AGENT_TREE only covers 3 departments — do NOT reuse it. Build fresh from the full agent inventory.

GET /api/agents/status
  → [{name, circuit_state, failure_count, last_invoked, cache_valid}]
  Source: supervisor_circuit_breakers + supervisor_events + supervisor_output_validity
```

### Supervisor
```
GET /api/supervisor/stats
  → {active_runs, open_breakers, dlq_count, events_24h}
  Source: aggregated queries across supervisor tables

GET /api/supervisor/circuits
  → [{agent_name, state, failure_count, last_failure_at, opened_at}]
  Source: supervisor_circuit_breakers

POST /api/supervisor/circuits/{agent_name}/reset
  → {success: true}
  Action: reset circuit breaker state to closed

GET /api/supervisor/dlq
  → [{run_id, pipeline_type, blocked_on, last_error, completed_steps, created_at}]
  Source: supervisor_dlq

POST /api/supervisor/dlq/{run_id}/resume
  → {success: true, run_id}
  Action: re-queue blocked run

GET /api/supervisor/runs?status=&type=&limit=20
  → [{run_id, pipeline_type, status, current_step, total_steps, created_at, updated_at}]
  Source: supervisor_runs

GET /api/supervisor/events?agent=&type=&run_id=&limit=50&offset=0
  → [{id, run_id, agent_name, event_type, payload, created_at}]
  Source: supervisor_events

GET /api/supervisor/evolution
  → [{agent_name, version, status, score_baseline, hypothesis, confidence, created_at}]
  Source: evolution.db agent_versions + hypotheses
```

### Forge
```
GET /api/forge/registry
  → {skills: [{skill_id, name, domain, department, composite_score, needs_review, production_runs, file_path}]}
  Source: skill_forge.db staging_registry
```

### Status (expanded)
```
GET /api/status/live
  → {status, model, agent, agent_count: 62, department_count: 9, active_runs, open_breakers, dlq_count, uptime_seconds}
  Source: aggregated
```

---

## 15. Data Flow

```
dashboard.html (browser)
    │
    ├── On load: GET /api/status/live → top bar
    ├── Every 5s: GET /api/status/live → top bar refresh
    ├── On Dashboard view: GET /api/supervisor/stats + /api/supervisor/events + /api/supervisor/runs
    ├── On Agents view: GET /api/agents + /api/agents/status
    ├── On Supervisor view: respective sub-endpoints
    ├── On Forge view: GET /api/forge/registry
    ├── On Console/Pipeline: POST /api/run → SSE stream
    └── On circuit reset / DLQ resume: POST actions
```

---

## 16. Implementation Notes

### File Changes
- `aass_agents/dashboard.html` — complete rewrite (~3000-4000 lines estimated)
- `aass_agents/api.py` — add ~12 new endpoints (~200 lines)

### Performance
- Top bar polling: 5s interval, lightweight aggregation query
- Dashboard polling: 5s for events/runs, only when Dashboard view is active
- Supervisor views: 5s auto-refresh only for active sub-tab
- All other views: fetch once on view switch, manual refresh buttons
- SVG org chart: render once, update status dots via polling

### Accessibility
- Keyboard navigation: Tab through sidebar items, Enter to select
- Focus indicators on all interactive elements
- Semantic HTML where possible within single-file constraint
- Color + icon for status (not color alone)

### Browser Support
- Modern browsers (Chrome, Firefox, Edge, Safari — last 2 versions)
- CSS features: backdrop-filter, CSS grid, custom properties, scroll-snap
- JS features: fetch, async/await, SSE (EventSource not used — manual fetch + reader for POST SSE)
