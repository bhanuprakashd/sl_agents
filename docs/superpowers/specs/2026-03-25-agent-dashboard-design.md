# Agent Pipeline Dashboard — Design Spec
**Date:** 2026-03-25
**Status:** Approved (v2 — post spec-review)

## Overview

A live pipeline tracking dashboard for the AASS multi-agent system, modelled on Apache Airflow's DAG view. Shows the full company agent hierarchy as a directed graph, with per-run execution state (pending / running / completed / failed) updated in real-time via WebSocket. Includes a secondary panel for the autoresearcher self-evolution loop.

---

## 1. Data Layer

### New tables added to `evolution_db.py`

The two new tables and their CRUD are added as a new section in the existing `aass_agents/tools/evolution_db.py` (consistent with the existing pattern — no new file needed).

**`execution_runs`** — one row per pipeline invocation
```sql
CREATE TABLE IF NOT EXISTS execution_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_input TEXT NOT NULL,
    status        TEXT DEFAULT 'running',   -- running | completed | failed
    started_at    TEXT NOT NULL,
    finished_at   TEXT
);
```

**`execution_events`** — one row per agent status change within a run
```sql
CREATE TABLE IF NOT EXISTS execution_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES execution_runs(id),
    agent_name    TEXT NOT NULL,
    status        TEXT NOT NULL,            -- pending | running | completed | failed
    started_at    TEXT,
    finished_at   TEXT,
    output_sample TEXT,                     -- first 500 chars of agent output
    UNIQUE(run_id, agent_name, status)      -- prevent duplicate status events
);

CREATE INDEX IF NOT EXISTS idx_exec_events_run ON execution_events(run_id, id);
```

The `UNIQUE(run_id, agent_name, status)` constraint + the index on `(run_id, id)` protect against duplicate events on error paths and ensure the WebSocket polling query (`WHERE run_id = ? AND id > ?`) is served by index scan, not full table scan.

### New functions in `evolution_db.py`

```python
# Runs
start_run(trigger_input: str) -> int               # returns run_id
finish_run(run_id: int, status: str) -> None

# Events
log_agent_start(run_id: int, agent_name: str) -> int | None   # returns event_id, or None if duplicate (INSERT OR IGNORE)
log_agent_finish(run_id: int, agent_name: str,
                 status: str, output_sample: str) -> None

# Queries
get_run(run_id: int) -> dict
list_runs(limit: int = 20) -> list[dict]
get_run_events(run_id: int) -> list[dict]
get_new_events(run_id: int, after_id: int) -> list[dict]  # used by WebSocket poll
```

All functions follow the existing async/sync pattern in `evolution_db.py` (sync impl + `asyncio.to_thread` wrapper).

### Agent instrumentation

Thin logging calls added to:
- `company_orchestrator_agent.py`
- All 7 department orchestrators (sales, marketing, product, engineering, research, qa, autoresearcher)

Pattern: call `log_agent_start` before routing to a sub-agent, `log_agent_finish` after it returns. **Leaf agents are not instrumented** — their status is inferred from orchestrator routing events.

Note: the existing unstaged changes to `content_strategist_agent.py`, `pm_agent.py`, and `lead_researcher_agent.py` are unrelated MCP API fixes from a prior session — not dashboard instrumentation.

---

## 2. Backend

**Location:** `aass_agents/dashboard/server.py`
**Framework:** FastAPI + uvicorn[standard]

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/runs` | List last 20 pipeline runs (id, status, started_at, duration) |
| `GET` | `/api/runs/{run_id}` | Full run detail: all execution_events for that run |
| `GET` | `/api/graph` | Static agent hierarchy: nodes + directed edges, computed once at startup |
| `GET` | `/api/evolution` | Autoresearcher state: evaluator_queue, latest rewrite verdicts, version history |

### `/api/graph` response schema

```json
{
  "nodes": [
    {"id": "company_orchestrator", "label": "Company Orchestrator", "department": "root"},
    {"id": "sales_orchestrator", "label": "Sales Orchestrator", "department": "sales"},
    {"id": "lead_researcher_agent", "label": "Lead Researcher", "department": "sales"}
  ],
  "edges": [
    {"source": "company_orchestrator", "target": "sales_orchestrator"},
    {"source": "sales_orchestrator", "target": "lead_researcher_agent"}
  ]
}
```

Computed once at startup from agent definitions. The hierarchy is static — only node statuses change at runtime.

### `/api/evolution` response schema

```json
{
  "queue": [
    {"agent_name": "lead_researcher_agent", "priority": 4.2, "confidence": "medium", "queued_at": "2026-03-25T09:00:00Z", "status": "pending"}
  ],
  "recent_verdicts": [
    {"agent_name": "lead_researcher_agent", "version": 3, "status": "stable", "score_baseline": 5.1, "created_at": "2026-03-25T08:00:00Z"},
    {"agent_name": "pm_agent", "version": 2, "status": "rolled_back", "score_baseline": 4.8, "created_at": "2026-03-24T14:00:00Z"}
  ],
  "version_history": {
    "lead_researcher_agent": [
      {"version": 1, "status": "rolled_back", "score_baseline": 4.2},
      {"version": 2, "status": "stable", "score_baseline": 6.8},
      {"version": 3, "status": "pending_watch", "score_baseline": 5.1}
    ]
  }
}
```

### WebSocket

```
WS /ws/runs/{run_id}
```

SQLite has no native pub/sub. The WebSocket handler uses an **asyncio polling loop** on the server side:

```python
@app.websocket("/ws/runs/{run_id}")
async def ws_run(websocket: WebSocket, run_id: int):
    await websocket.accept()
    last_seen_id = 0
    while True:
        new_events = await get_new_events(run_id, after_id=last_seen_id)
        for event in new_events:
            await websocket.send_json(event)
            last_seen_id = event["id"]
        run = await get_run(run_id)
        if run["status"] in ("completed", "failed"):
            await websocket.close()
            break
        await asyncio.sleep(0.5)   # 500ms poll interval
```

Push event shape:
```json
{"id": 42, "agent_name": "lead_researcher_agent", "status": "running", "started_at": "2026-03-25T10:00:00Z"}
```

The `idx_exec_events_run` index ensures the `WHERE run_id = ? AND id > ?` query is served by index scan. At 500ms polling with SQLite WAL mode, write contention is negligible for this workload.

Client reconnects automatically on disconnect (handled in `useRunSocket.ts`).

### Dependencies

Add to `requirements.txt` / `pyproject.toml`:
```
uvicorn[standard]>=0.42.0   # includes websockets transport
```
(replaces bare `uvicorn` pin)

---

## 3. Frontend

**Location:** `aass_agents/dashboard/ui/`
**Stack:** React + ReactFlow + TailwindCSS
**Build:** Vite

### Layout

```
┌─────────────────────────────────────────────────────┬───────────────────┐
│  [Run selector ▼]          AASS Pipeline Dashboard  │  Recent Runs      │
│                                                      │  ──────────────── │
│                                                      │  #42 ✅ 2m 14s   │
│          [  DAG — ReactFlow  ]                       │  #41 ✅ 1m 58s   │
│                                                      │  #40 ❌ 0m 32s   │
│   ○ pending   ◉ running (pulse)                      │                   │
│   ● completed  ✕ failed                              │  Autoresearcher   │
│                                                      │  ──────────────── │
│                                                      │  Queue: 2 agents  │
│                                                      │  Last rewrite:    │
│                                                      │  lead_researcher  │
│                                                      │  v3 → stable ✅   │
└─────────────────────────────────────────────────────┴───────────────────┘
```

### Node colours

| Status | Colour | Animation |
|--------|--------|-----------|
| `pending` | Grey `#94a3b8` | None |
| `running` | Blue `#3b82f6` | Radial pulse (CSS keyframe) |
| `completed` | Green `#22c55e` | None |
| `failed` | Red `#ef4444` | None |

### Node click → drawer

Clicking any node opens a right-side drawer showing:
- Agent name + department
- Status + duration
- Output sample (first 500 chars)
- Link to evolution history if agent has been rewritten

### Autoresearcher panel (right sidebar, bottom)

- Evaluator queue: agent name, priority score, status
- Last 5 rewrite verdicts: `agent_name vN → stable | rolled_back`
- Version history per agent: score_baseline across versions

---

## 4. File Structure

```
aass_agents/
  tools/
    evolution_db.py          # EXTENDED: new execution_runs + execution_events tables + CRUD
  dashboard/
    server.py                # FastAPI app
    graph_builder.py         # Builds static agent hierarchy from agent definitions
    ui/
      package.json
      vite.config.ts
      src/
        App.tsx
        components/
          DAGPanel.tsx             # ReactFlow DAG
          RunSelector.tsx
          RunHistory.tsx
          AgentDrawer.tsx          # Node click detail
          AutoresearcherPanel.tsx
        hooks/
          useRunSocket.ts          # WebSocket subscription + auto-reconnect
          useGraphStatus.ts        # Merges static graph + live statuses
        api.ts                     # REST client
```

---

## 5. Error Handling

- WebSocket disconnect: client auto-reconnects with 2s backoff, max 5 retries
- Agent fails mid-run: node turns red, run marked `failed`, remaining nodes stay grey
- No runs yet: DAG renders in full grey with "No runs yet" overlay
- Evolution DB unavailable: autoresearcher panel shows "Unavailable" badge, rest of dashboard unaffected
- Duplicate `log_agent_start` calls: `UNIQUE(run_id, agent_name, status)` constraint silently ignores duplicates via `INSERT OR IGNORE`

---

## 6. Out of Scope

- Authentication (dev-only tool)
- Historical trend charts beyond last 20 runs
- Manual triggering of runs from the dashboard
- Mobile layout
- Hot-reload of agent instructions (separate feature)
