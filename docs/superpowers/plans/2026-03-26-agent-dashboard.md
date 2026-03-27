# Agent Pipeline Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a live Airflow-DAG-style dashboard that visualises the AASS multi-agent pipeline in real-time via WebSocket, with a secondary panel showing the autoresearcher self-evolution loop.

**Architecture:** FastAPI backend extends `evolution_db.py` with two new execution tables; a polling WebSocket pushes events to a React + ReactFlow frontend that renders nodes as a directed graph with colour-coded live status.

**Tech Stack:** Python 3.11 / FastAPI / SQLite WAL / uvicorn[standard] (WebSocket transport) / React 18 / ReactFlow / TailwindCSS / Vite / Vitest

**Spec:** `docs/superpowers/specs/2026-03-25-agent-dashboard-design.md`

---

## File Map

### New files
| File | Responsibility |
|------|---------------|
| `aass_agents/dashboard/__init__.py` | Package marker |
| `aass_agents/dashboard/graph_builder.py` | Build static node/edge hierarchy from agent definitions |
| `aass_agents/dashboard/server.py` | FastAPI app — REST + WebSocket |
| `aass_agents/tests/test_execution_db.py` | Tests for new execution tables/CRUD |
| `aass_agents/tests/test_graph_builder.py` | Tests for graph_builder |
| `aass_agents/tests/test_dashboard_server.py` | Tests for REST endpoints |
| `aass_agents/tests/test_instrumentation.py` | Tests for instrumentation callbacks |
| `aass_agents/dashboard/ui/package.json` | Frontend package manifest |
| `aass_agents/dashboard/ui/vite.config.ts` | Vite build config |
| `aass_agents/dashboard/ui/tsconfig.json` | TypeScript config |
| `aass_agents/dashboard/ui/index.html` | HTML entry point |
| `aass_agents/dashboard/ui/tailwind.config.ts` | Tailwind config |
| `aass_agents/dashboard/ui/src/api.ts` | REST client + type definitions |
| `aass_agents/dashboard/ui/src/hooks/useRunSocket.ts` | WebSocket subscription + auto-reconnect |
| `aass_agents/dashboard/ui/src/hooks/useGraphStatus.ts` | Merge static graph + live event statuses |
| `aass_agents/dashboard/ui/src/components/DAGPanel.tsx` | ReactFlow DAG |
| `aass_agents/dashboard/ui/src/components/RunSelector.tsx` | Run dropdown |
| `aass_agents/dashboard/ui/src/components/RunHistory.tsx` | Recent runs list |
| `aass_agents/dashboard/ui/src/components/AgentDrawer.tsx` | Node-click detail drawer |
| `aass_agents/dashboard/ui/src/components/AutoresearcherPanel.tsx` | Evolution queue + verdicts |
| `aass_agents/dashboard/ui/src/App.tsx` | Root layout |
| `aass_agents/dashboard/ui/src/App.test.tsx` | Smoke test |

### Modified files
| File | Change |
|------|--------|
| `aass_agents/tools/evolution_db.py` | Add `execution_runs` + `execution_events` DDL and 8 CRUD functions |
| `aass_agents/requirements.txt` | `uvicorn>=0.42.0` → `uvicorn[standard]>=0.42.0` |
| `aass_agents/pyproject.toml` | Same |
| `aass_agents/agents/company_orchestrator_agent.py` | Add `before_agent_callback` / `after_agent_callback` for run logging |
| `aass_agents/agents/sales/sales_orchestrator_agent.py` | Add agent-level callbacks |
| `aass_agents/agents/marketing/marketing_orchestrator_agent.py` | Add agent-level callbacks |
| `aass_agents/agents/product/product_orchestrator_agent.py` | Add agent-level callbacks |
| `aass_agents/agents/engineering/engineering_orchestrator_agent.py` | Add agent-level callbacks |
| `aass_agents/agents/research/research_orchestrator_agent.py` | Add agent-level callbacks |
| `aass_agents/agents/qa/qa_orchestrator_agent.py` | Add agent-level callbacks |
| `aass_agents/agents/autoresearcher/autoresearcher_orchestrator_agent.py` | Add agent-level callbacks |

---

## Task 1: Update Dependencies

**Files:**
- Modify: `aass_agents/requirements.txt`
- Modify: `aass_agents/pyproject.toml`

- [ ] **Step 1: Update requirements.txt**

Replace `uvicorn>=0.42.0` with `uvicorn[standard]>=0.42.0`.
`uvicorn[standard]` bundles `websockets` transport — required for the WebSocket endpoint.

```
# requirements.txt change
uvicorn[standard]>=0.42.0   # was: uvicorn>=0.42.0
```

- [ ] **Step 2: Update pyproject.toml**

Same change in `[project] dependencies`.

- [ ] **Step 3: Commit**

```bash
git add aass_agents/requirements.txt aass_agents/pyproject.toml
git commit -m "chore: upgrade uvicorn to [standard] for WebSocket transport"
```

---

## Task 2: Data Layer — Execution Tables

**Files:**
- Modify: `aass_agents/tools/evolution_db.py`
- Create: `aass_agents/tests/test_execution_db.py`

### Step 1: Write the failing tests

- [ ] **Step 1: Write test_execution_db.py**

```python
"""Tests for execution_runs + execution_events tables and CRUD."""
import pytest
import tools.evolution_db as edb


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_exec.db"
    monkeypatch.setattr(edb, "EVOLUTION_DB_PATH", db_path)
    edb.init_db()
    yield


# ── execution_runs ────────────────────────────────────────────────────────────

def test_start_run_returns_int():
    run_id = edb.start_run_sync("test input")
    assert isinstance(run_id, int)
    assert run_id > 0


def test_get_run_returns_running_status():
    run_id = edb.start_run_sync("hello")
    run = edb.get_run_sync(run_id)
    assert run["status"] == "running"
    assert run["trigger_input"] == "hello"
    assert run["finished_at"] is None


def test_finish_run_updates_status():
    run_id = edb.start_run_sync("input")
    edb.finish_run_sync(run_id, "completed")
    run = edb.get_run_sync(run_id)
    assert run["status"] == "completed"
    assert run["finished_at"] is not None


def test_list_runs_returns_most_recent_20():
    for i in range(25):
        edb.start_run_sync(f"input {i}")
    runs = edb.list_runs_sync()
    assert len(runs) == 20


# ── execution_events ──────────────────────────────────────────────────────────

def test_log_agent_start_returns_event_id():
    run_id = edb.start_run_sync("input")
    event_id = edb.log_agent_start_sync(run_id, "sales_orchestrator")
    assert isinstance(event_id, int)


def test_log_agent_start_duplicate_returns_none():
    run_id = edb.start_run_sync("input")
    edb.log_agent_start_sync(run_id, "sales_orchestrator")
    result = edb.log_agent_start_sync(run_id, "sales_orchestrator")
    assert result is None


def test_log_agent_finish_creates_event():
    run_id = edb.start_run_sync("input")
    edb.log_agent_start_sync(run_id, "marketing_orchestrator")
    edb.log_agent_finish_sync(run_id, "marketing_orchestrator", "completed", "output here")
    events = edb.get_run_events_sync(run_id)
    statuses = {e["status"] for e in events}
    assert "completed" in statuses


def test_get_new_events_incremental():
    run_id = edb.start_run_sync("input")
    edb.log_agent_start_sync(run_id, "agent_a")
    edb.log_agent_start_sync(run_id, "agent_b")
    all_events = edb.get_run_events_sync(run_id)
    first_id = all_events[0]["id"]
    new = edb.get_new_events_sync(run_id, after_id=first_id)
    assert len(new) == 1
    assert new[0]["agent_name"] == "agent_b"


def test_get_new_events_empty_when_caught_up():
    run_id = edb.start_run_sync("input")
    edb.log_agent_start_sync(run_id, "only_agent")
    events = edb.get_run_events_sync(run_id)
    last_id = events[-1]["id"]
    assert edb.get_new_events_sync(run_id, after_id=last_id) == []


# ── async smoke tests ─────────────────────────────────────────────────────────

async def test_async_start_and_finish_run():
    run_id = await edb.start_run("async input")
    await edb.finish_run(run_id, "completed")
    run = await edb.get_run(run_id)
    assert run["status"] == "completed"


async def test_async_log_events():
    run_id = await edb.start_run("async input")
    await edb.log_agent_start(run_id, "sales_orchestrator")
    events = await edb.get_run_events(run_id)
    assert len(events) == 1
```

- [ ] **Step 2: Run tests — expect FAIL (functions not defined)**

```bash
cd aass_agents && pytest tests/test_execution_db.py -v 2>&1 | head -30
```
Expected: `AttributeError: module 'tools.evolution_db' has no attribute 'start_run_sync'`

- [ ] **Step 3: Add execution DDL to evolution_db.py**

Append to the `DDL` string (after the `rewrite_locks` table, before the closing `"""`):

```python
CREATE TABLE IF NOT EXISTS execution_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_input TEXT NOT NULL,
    status        TEXT DEFAULT 'running',
    started_at    TEXT NOT NULL,
    finished_at   TEXT
);

CREATE TABLE IF NOT EXISTS execution_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES execution_runs(id),
    agent_name    TEXT NOT NULL,
    status        TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT,
    output_sample TEXT,
    UNIQUE(run_id, agent_name, status)
);

CREATE INDEX IF NOT EXISTS idx_exec_events_run ON execution_events(run_id, id);
```

- [ ] **Step 4: Add CRUD functions to evolution_db.py**

> `asyncio`, `sqlite3`, `Optional`, and `_now_iso` / `_connect` are already present in the file — do not re-import or redefine them.

Add after the `rewrite_locks` section (before `# Init on import`):

```python
# ── execution_runs ─────────────────────────────────────────────────────────────

def start_run_sync(trigger_input: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO execution_runs (trigger_input, status, started_at) VALUES (?, 'running', ?)",
            (trigger_input, _now_iso()),
        )
        return cur.lastrowid


async def start_run(trigger_input: str) -> int:
    return await asyncio.to_thread(start_run_sync, trigger_input)


def finish_run_sync(run_id: int, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE execution_runs SET status=?, finished_at=? WHERE id=?",
            (status, _now_iso(), run_id),
        )


async def finish_run(run_id: int, status: str) -> None:
    await asyncio.to_thread(finish_run_sync, run_id, status)


def get_run_sync(run_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM execution_runs WHERE id=?", (run_id,)
        ).fetchone()
    return dict(row) if row else None


async def get_run(run_id: int) -> Optional[dict]:
    return await asyncio.to_thread(get_run_sync, run_id)


def list_runs_sync(limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM execution_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


async def list_runs(limit: int = 20) -> list[dict]:
    return await asyncio.to_thread(list_runs_sync, limit)


# ── execution_events ──────────────────────────────────────────────────────────

def log_agent_start_sync(run_id: int, agent_name: str) -> Optional[int]:
    """Returns event_id, or None if duplicate (INSERT OR IGNORE)."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO execution_events
              (run_id, agent_name, status, started_at)
            VALUES (?, ?, 'running', ?)
            """,
            (run_id, agent_name, _now_iso()),
        )
        return cur.lastrowid if cur.rowcount == 1 else None


async def log_agent_start(run_id: int, agent_name: str) -> Optional[int]:
    return await asyncio.to_thread(log_agent_start_sync, run_id, agent_name)


def log_agent_finish_sync(
    run_id: int, agent_name: str, status: str, output_sample: str = ""
) -> None:
    sample = (output_sample or "")[:500]
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO execution_events
              (run_id, agent_name, status, finished_at, output_sample)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, agent_name, status, _now_iso(), sample),
        )


async def log_agent_finish(
    run_id: int, agent_name: str, status: str, output_sample: str = ""
) -> None:
    await asyncio.to_thread(log_agent_finish_sync, run_id, agent_name, status, output_sample)


def get_run_events_sync(run_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM execution_events WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
    return [dict(r) for r in rows]


async def get_run_events(run_id: int) -> list[dict]:
    return await asyncio.to_thread(get_run_events_sync, run_id)


def get_new_events_sync(run_id: int, after_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM execution_events WHERE run_id=? AND id>? ORDER BY id",
            (run_id, after_id),
        ).fetchall()
    return [dict(r) for r in rows]


async def get_new_events(run_id: int, after_id: int) -> list[dict]:
    return await asyncio.to_thread(get_new_events_sync, run_id, after_id)
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd aass_agents && pytest tests/test_execution_db.py -v
```
Expected: All tests PASS.

- [ ] **Step 6: Run full test suite to verify no regressions**

```bash
cd aass_agents && pytest --tb=short -q
```
Expected: All existing tests pass.

- [ ] **Step 7: Commit**

```bash
git add aass_agents/tools/evolution_db.py aass_agents/tests/test_execution_db.py
git commit -m "feat: add execution_runs and execution_events tables to evolution_db"
```

---

## Task 3: Graph Builder

**Files:**
- Create: `aass_agents/dashboard/__init__.py`
- Create: `aass_agents/dashboard/graph_builder.py`
- Create: `aass_agents/tests/test_graph_builder.py`

The graph is static — it represents the fixed agent hierarchy as declared in the Python files, not runtime state. Computed once at server startup.

- [ ] **Step 1: Write test_graph_builder.py**

```python
"""Tests for dashboard/graph_builder.py"""
from dashboard.graph_builder import build_graph


def test_build_graph_returns_nodes_and_edges():
    graph = build_graph()
    assert "nodes" in graph
    assert "edges" in graph
    assert len(graph["nodes"]) > 0
    assert len(graph["edges"]) > 0


def test_company_orchestrator_is_root_node():
    graph = build_graph()
    ids = {n["id"] for n in graph["nodes"]}
    assert "company_orchestrator" in ids


def test_all_department_orchestrators_present():
    graph = build_graph()
    ids = {n["id"] for n in graph["nodes"]}
    for dept in ("sales_orchestrator", "marketing_orchestrator", "product_orchestrator",
                 "engineering_orchestrator", "research_orchestrator",
                 "qa_orchestrator", "autoresearcher_orchestrator"):
        assert dept in ids, f"Missing: {dept}"


def test_edges_connect_company_to_departments():
    graph = build_graph()
    sources = {e["source"] for e in graph["edges"]}
    assert "company_orchestrator" in sources


def test_node_has_required_fields():
    graph = build_graph()
    node = graph["nodes"][0]
    assert "id" in node
    assert "label" in node
    assert "department" in node
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd aass_agents && pytest tests/test_graph_builder.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'dashboard'`

- [ ] **Step 3: Create `aass_agents/dashboard/__init__.py`**

```python
```
(empty file — package marker)

- [ ] **Step 4: Create `aass_agents/dashboard/graph_builder.py`**

```python
"""
graph_builder.py — builds the static agent hierarchy graph.

The hierarchy is derived directly from the agent definitions
(sub_agents lists). Called once at FastAPI startup.
"""
from __future__ import annotations

HIERARCHY: dict[str, dict] = {
    "company_orchestrator": {
        "label": "Company Orchestrator",
        "department": "root",
        "children": [
            "sales_orchestrator",
            "marketing_orchestrator",
            "product_orchestrator",
            "engineering_orchestrator",
            "research_orchestrator",
            "qa_orchestrator",
            "autoresearcher_orchestrator",
        ],
    },
    "sales_orchestrator": {
        "label": "Sales Orchestrator",
        "department": "sales",
        "children": [
            "lead_researcher_agent",
            "outreach_composer_agent",
            "sales_call_prep_agent",
            "objection_handler_agent",
            "proposal_generator_agent",
            "crm_updater_agent",
            "deal_analyst_agent",
        ],
    },
    "marketing_orchestrator": {
        "label": "Marketing Orchestrator",
        "department": "marketing",
        "children": [
            "audience_builder_agent",
            "campaign_composer_agent",
            "content_strategist_agent",
            "brand_voice_agent",
            "seo_analyst_agent",
            "campaign_analyst_agent",
        ],
    },
    "product_orchestrator": {
        "label": "Product Orchestrator",
        "department": "product",
        "children": [
            "pm_agent",
            "architect_agent",
            "backend_builder_agent",
            "frontend_builder_agent",
            "db_agent",
            "devops_agent",
            "qa_agent",
        ],
    },
    "engineering_orchestrator": {
        "label": "Engineering Orchestrator",
        "department": "engineering",
        "children": [
            "data_engineer_agent",
            "ml_engineer_agent",
            "solutions_architect_agent",
            "integration_engineer_agent",
            "platform_engineer_agent",
            "systems_engineer_agent",
            "sdet_agent",
        ],
    },
    "research_orchestrator": {
        "label": "Research Orchestrator",
        "department": "research",
        "children": [
            "research_scientist_agent",
            "ml_researcher_agent",
            "user_researcher_agent",
            "data_scientist_agent",
            "applied_scientist_agent",
            "competitive_analyst_agent",
            "knowledge_manager_agent",
        ],
    },
    "qa_orchestrator": {
        "label": "QA Orchestrator",
        "department": "qa",
        "children": [
            "qa_engineer_agent",
            "test_architect_agent",
            "test_automation_engineer_agent",
            "performance_engineer_agent",
            "security_tester_agent",
            "chaos_engineer_agent",
        ],
    },
    "autoresearcher_orchestrator": {
        "label": "Autoresearcher Orchestrator",
        "department": "autoresearcher",
        "children": [
            "evaluator_agent",
            "rewriter_agent",
        ],
    },
}

# Leaf agent labels (not orchestrators)
LEAF_LABELS: dict[str, str] = {
    "lead_researcher_agent": "Lead Researcher",
    "outreach_composer_agent": "Outreach Composer",
    "sales_call_prep_agent": "Sales Call Prep",
    "objection_handler_agent": "Objection Handler",
    "proposal_generator_agent": "Proposal Generator",
    "crm_updater_agent": "CRM Updater",
    "deal_analyst_agent": "Deal Analyst",
    "audience_builder_agent": "Audience Builder",
    "campaign_composer_agent": "Campaign Composer",
    "content_strategist_agent": "Content Strategist",
    "brand_voice_agent": "Brand Voice",
    "seo_analyst_agent": "SEO Analyst",
    "campaign_analyst_agent": "Campaign Analyst",
    "pm_agent": "Product Manager",
    "architect_agent": "Architect",
    "backend_builder_agent": "Backend Builder",
    "frontend_builder_agent": "Frontend Builder",
    "db_agent": "DB Agent",
    "devops_agent": "DevOps",
    "qa_agent": "Product QA",
    "data_engineer_agent": "Data Engineer",
    "ml_engineer_agent": "ML Engineer",
    "solutions_architect_agent": "Solutions Architect",
    "integration_engineer_agent": "Integration Engineer",
    "platform_engineer_agent": "Platform Engineer",
    "systems_engineer_agent": "Systems Engineer",
    "sdet_agent": "SDET",
    "research_scientist_agent": "Research Scientist",
    "ml_researcher_agent": "ML Researcher",
    "user_researcher_agent": "User Researcher",
    "data_scientist_agent": "Data Scientist",
    "applied_scientist_agent": "Applied Scientist",
    "competitive_analyst_agent": "Competitive Analyst",
    "knowledge_manager_agent": "Knowledge Manager",
    "qa_engineer_agent": "QA Engineer",
    "test_architect_agent": "Test Architect",
    "test_automation_engineer_agent": "Test Automation Engineer",
    "performance_engineer_agent": "Performance Engineer",
    "security_tester_agent": "Security Tester",
    "chaos_engineer_agent": "Chaos Engineer",
    "evaluator_agent": "Evaluator",
    "rewriter_agent": "Rewriter",
}


def build_graph() -> dict:
    """Return {"nodes": [...], "edges": [...]} for the full agent hierarchy."""
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_nodes: set[str] = set()

    def add_node(node_id: str, label: str, department: str) -> None:
        if node_id not in seen_nodes:
            nodes.append({"id": node_id, "label": label, "department": department})
            seen_nodes.add(node_id)

    for orch_id, meta in HIERARCHY.items():
        add_node(orch_id, meta["label"], meta["department"])
        for child_id in meta.get("children", []):
            dept = meta["department"] if orch_id != "company_orchestrator" else child_id.replace("_orchestrator", "")
            child_label = LEAF_LABELS.get(child_id, child_id.replace("_", " ").title())
            add_node(child_id, child_label, dept)
            edges.append({"source": orch_id, "target": child_id})

    return {"nodes": nodes, "edges": edges}
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd aass_agents && pytest tests/test_graph_builder.py -v
```
Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add aass_agents/dashboard/ aass_agents/tests/test_graph_builder.py
git commit -m "feat: add dashboard package and static graph builder"
```

---

## Task 4: FastAPI Server — REST Endpoints

**Files:**
- Create: `aass_agents/dashboard/server.py`
- Create: `aass_agents/tests/test_dashboard_server.py`

- [ ] **Step 1: Write test_dashboard_server.py**

```python
"""Tests for FastAPI REST endpoints."""
import pytest
from fastapi.testclient import TestClient
import tools.evolution_db as edb


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_server.db"
    monkeypatch.setattr(edb, "EVOLUTION_DB_PATH", db_path)
    edb.init_db()


@pytest.fixture()
def client():
    from dashboard.server import app
    return TestClient(app)


def test_get_graph_returns_nodes_and_edges(client):
    resp = client.get("/api/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert "nodes" in body and "edges" in body
    assert len(body["nodes"]) > 0


def test_list_runs_empty(client):
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_runs_with_data(client):
    edb.start_run_sync("test input")
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_run_detail(client):
    run_id = edb.start_run_sync("input for detail")
    edb.log_agent_start_sync(run_id, "sales_orchestrator")
    resp = client.get(f"/api/runs/{run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"]["id"] == run_id
    assert len(body["events"]) == 1


def test_get_run_not_found(client):
    resp = client.get("/api/runs/9999")
    assert resp.status_code == 404


def test_get_evolution(client):
    resp = client.get("/api/evolution")
    assert resp.status_code == 200
    body = resp.json()
    assert "queue" in body
    assert "recent_verdicts" in body
    assert "version_history" in body
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd aass_agents && pytest tests/test_dashboard_server.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'dashboard.server'`

- [ ] **Step 3: Create `aass_agents/dashboard/server.py`**

```python
"""
server.py — FastAPI dashboard backend.

REST endpoints:
  GET  /api/runs          — list last 20 pipeline runs
  GET  /api/runs/{run_id} — run detail + events
  GET  /api/graph         — static agent hierarchy
  GET  /api/evolution     — autoresearcher state

WebSocket:
  WS   /ws/runs/{run_id}  — push new execution_events to client
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware

import tools.evolution_db as edb
from dashboard.graph_builder import build_graph

_GRAPH_CACHE: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    _GRAPH_CACHE.update(build_graph())
    yield


app = FastAPI(title="AASS Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST ──────────────────────────────────────────────────────────────────────

@app.get("/api/runs")
async def list_runs() -> list[dict]:
    return await edb.list_runs()


@app.get("/api/runs/{run_id}")
async def get_run(run_id: int) -> dict:
    run = await edb.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    events = await edb.get_run_events(run_id)
    return {"run": run, "events": events}


@app.get("/api/graph")
async def get_graph() -> dict:
    return _GRAPH_CACHE


@app.get("/api/evolution")
async def get_evolution() -> dict:
    queue = await edb.get_queue_pending()
    # recent verdicts: last 5 agent versions with terminal statuses
    verdicts = await _get_recent_verdicts()
    version_history = await _get_version_history()
    return {"queue": queue, "recent_verdicts": verdicts, "version_history": version_history}


async def _get_recent_verdicts() -> list[dict]:
    import asyncio
    from tools.evolution_db import get_pending_watch
    # Re-use existing sync query via asyncio.to_thread
    def _sync() -> list[dict]:
        import sqlite3
        conn = sqlite3.connect(str(edb.EVOLUTION_DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT agent_name, version, status, score_baseline, created_at
            FROM agent_versions
            WHERE status IN ('stable', 'rolled_back')
            ORDER BY created_at DESC LIMIT 5
            """
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    return await asyncio.to_thread(_sync)


async def _get_version_history() -> dict[str, list[dict]]:
    def _sync() -> dict[str, list[dict]]:
        import sqlite3
        conn = sqlite3.connect(str(edb.EVOLUTION_DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT agent_name, version, status, score_baseline FROM agent_versions ORDER BY agent_name, version"
        ).fetchall()
        conn.close()
        history: dict[str, list[dict]] = {}
        for r in rows:
            history.setdefault(r["agent_name"], []).append(dict(r))
        return history
    return await asyncio.to_thread(_sync)


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/runs/{run_id}")
async def ws_run(websocket: WebSocket, run_id: int) -> None:
    await websocket.accept()
    last_seen_id = 0
    while True:
        new_events = await edb.get_new_events(run_id, after_id=last_seen_id)
        for event in new_events:
            await websocket.send_json(event)
            last_seen_id = event["id"]
        run = await edb.get_run(run_id)
        if run is None or run["status"] in ("completed", "failed"):
            await websocket.close()
            break
        await asyncio.sleep(0.5)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd aass_agents && pytest tests/test_dashboard_server.py -v
```
Expected: All 6 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
cd aass_agents && pytest --tb=short -q
```
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add aass_agents/dashboard/server.py aass_agents/tests/test_dashboard_server.py
git commit -m "feat: add FastAPI dashboard server with REST endpoints and WebSocket"
```

---

## Task 5: Orchestrator Instrumentation

**Files:**
- Modify: `aass_agents/agents/company_orchestrator_agent.py`
- Modify: `aass_agents/agents/sales/sales_orchestrator_agent.py`
- Modify: `aass_agents/agents/marketing/marketing_orchestrator_agent.py`
- Modify: `aass_agents/agents/product/product_orchestrator_agent.py`
- Modify: `aass_agents/agents/engineering/engineering_orchestrator_agent.py`
- Modify: `aass_agents/agents/research/research_orchestrator_agent.py`
- Modify: `aass_agents/agents/qa/qa_orchestrator_agent.py`
- Modify: `aass_agents/agents/autoresearcher/autoresearcher_orchestrator_agent.py`

> **Note:** Google ADK's `Agent` supports `before_agent_callback` and `after_agent_callback` parameters. Refer to `adk-cheatsheet` or `adk-observability-guide` skills for exact API signatures before editing. The pattern below assumes standard callback signatures — verify against current ADK docs first.

The `run_id` must be threaded through callbacks. Use a context variable (`contextvars.ContextVar`) so it flows without changing agent signatures.

- [ ] **Step 1: Read the ADK callback API**

Check `adk-cheatsheet` or `adk-observability-guide` skill:
```
skill: adk-observability-guide
```
Look for: `before_agent_callback`, `after_agent_callback`, `CallbackContext`.

- [ ] **Step 1b: Write `aass_agents/tests/test_instrumentation.py` — failing first**

```python
"""Tests for dashboard/instrumentation.py"""
import asyncio
import pytest
import tools.evolution_db as edb
from dashboard.instrumentation import make_callbacks, make_run_callbacks, RUN_ID_VAR


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_instr.db"
    monkeypatch.setattr(edb, "EVOLUTION_DB_PATH", db_path)
    edb.init_db()


def test_make_callbacks_returns_two_callables():
    before, after = make_callbacks("sales_orchestrator")
    assert callable(before) and callable(after)


def test_make_run_callbacks_returns_two_callables():
    before, after = make_run_callbacks("test trigger")
    assert callable(before) and callable(after)


def test_callbacks_are_no_ops_when_run_id_not_set():
    """Callbacks must not raise when RUN_ID_VAR is None (e.g., unit tests, CLI)."""
    RUN_ID_VAR.set(None)
    before, after = make_callbacks("sales_orchestrator")

    class FakeCtx:
        output = "some output"

    before(FakeCtx())  # should not raise
    after(FakeCtx())   # should not raise
```

Run: `cd aass_agents && pytest tests/test_instrumentation.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 2: Create `aass_agents/dashboard/instrumentation.py`**

This module holds the shared run_id context var and callback factories, keeping the agent files clean.

```python
"""
instrumentation.py — thin callbacks for execution event logging.

Usage in agent files:
    from dashboard.instrumentation import make_callbacks, RUN_ID_VAR

    before_cb, after_cb = make_callbacks("sales_orchestrator")
    sales_orchestrator = Agent(..., before_agent_callback=before_cb, after_agent_callback=after_cb)
"""
from __future__ import annotations
import asyncio
from contextvars import ContextVar
from typing import Any

import tools.evolution_db as edb

# Holds the current run_id for the duration of a pipeline execution.
# Set by the company orchestrator's before_agent_callback.
RUN_ID_VAR: ContextVar[int | None] = ContextVar("run_id", default=None)


def make_callbacks(agent_name: str):
    """
    Returns (before_agent_callback, after_agent_callback) for an agent.
    Callbacks are no-ops when RUN_ID_VAR is not set (e.g., unit tests).
    """
    def before_cb(callback_context: Any) -> None:
        run_id = RUN_ID_VAR.get()
        if run_id is not None:
            # Fire-and-forget — don't block the ADK event loop
            asyncio.get_event_loop().create_task(
                edb.log_agent_start(run_id, agent_name)
            )

    def after_cb(callback_context: Any) -> None:
        run_id = RUN_ID_VAR.get()
        if run_id is not None:
            output = getattr(callback_context, "output", "") or ""
            sample = str(output)[:500]
            asyncio.get_event_loop().create_task(
                edb.log_agent_finish(run_id, agent_name, "completed", sample)
            )

    return before_cb, after_cb


def make_run_callbacks(trigger_input: str = ""):
    """
    For the company orchestrator — starts a new run and sets RUN_ID_VAR.
    Returns sync callbacks (same pattern as make_callbacks) that schedule
    coroutines via create_task to avoid blocking the ADK event loop.
    """
    def before_cb(callback_context: Any) -> None:
        loop = asyncio.get_event_loop()

        async def _start() -> None:
            run_id = await edb.start_run(trigger_input or "pipeline run")
            RUN_ID_VAR.set(run_id)
            await edb.log_agent_start(run_id, "company_orchestrator")

        loop.create_task(_start())

    def after_cb(callback_context: Any) -> None:
        run_id = RUN_ID_VAR.get()
        if run_id is not None:
            output = getattr(callback_context, "output", "") or ""
            sample = str(output)[:500]
            asyncio.get_event_loop().create_task(
                _finish_run(run_id, sample)
            )

    async def _finish_run(run_id: int, sample: str) -> None:
        await edb.log_agent_finish(run_id, "company_orchestrator", "completed", sample)
        await edb.finish_run(run_id, "completed")

    return before_cb, after_cb
```

> **ADK API note:** The exact callback signature (`callback_context` type and attribute names) depends on your ADK version. Check `google.adk.agents.callback_context` or similar. Adjust `callback_context.output` if the actual attribute differs.

- [ ] **Step 2b: Run instrumentation tests — expect PASS**

```bash
cd aass_agents && pytest tests/test_instrumentation.py -v
```
Expected: All 3 tests PASS.

- [ ] **Step 3: Add callbacks to company_orchestrator_agent.py**

At the top of the file, add:
```python
from dashboard.instrumentation import make_run_callbacks
_run_before, _run_after = make_run_callbacks()
```

In the `Agent(...)` constructor, add:
```python
before_agent_callback=_run_before,
after_agent_callback=_run_after,
```

- [ ] **Step 4: Add callbacks to each of the 7 department orchestrators**

Repeat this pattern for each of the 7 files listed above. Example for `sales_orchestrator_agent.py`:

```python
from dashboard.instrumentation import make_callbacks
_before_cb, _after_cb = make_callbacks("sales_orchestrator")
```

Then add to the `Agent(...)` constructor:
```python
before_agent_callback=_before_cb,
after_agent_callback=_after_cb,
```

- [ ] **Step 5: Run existing tests to verify no regressions**

```bash
cd aass_agents && pytest --tb=short -q
```
Expected: All tests PASS. (Callbacks are no-ops when RUN_ID_VAR is not set.)

- [ ] **Step 6: Commit**

```bash
git add aass_agents/dashboard/instrumentation.py \
        aass_agents/agents/company_orchestrator_agent.py \
        aass_agents/agents/sales/sales_orchestrator_agent.py \
        aass_agents/agents/marketing/marketing_orchestrator_agent.py \
        aass_agents/agents/product/product_orchestrator_agent.py \
        aass_agents/agents/engineering/engineering_orchestrator_agent.py \
        aass_agents/agents/research/research_orchestrator_agent.py \
        aass_agents/agents/qa/qa_orchestrator_agent.py \
        aass_agents/agents/autoresearcher/autoresearcher_orchestrator_agent.py
git commit -m "feat: instrument orchestrators with execution event logging"
```

---

## Task 6: Frontend Scaffold

**Files:**
- Create: `aass_agents/dashboard/ui/package.json`
- Create: `aass_agents/dashboard/ui/vite.config.ts`
- Create: `aass_agents/dashboard/ui/tsconfig.json`
- Create: `aass_agents/dashboard/ui/index.html`
- Create: `aass_agents/dashboard/ui/tailwind.config.ts`

- [ ] **Step 1: Create `aass_agents/dashboard/ui/package.json`**

```json
{
  "name": "aass-dashboard",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "@xyflow/react": "^12.3.6"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "jsdom": "^25.0.1",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.17",
    "typescript": "^5.7.2",
    "vite": "^6.0.7",
    "vitest": "^2.1.8",
    "@testing-library/react": "^16.1.0",
    "@testing-library/jest-dom": "^6.6.3"
  }
}
```

- [ ] **Step 2: Create `aass_agents/dashboard/ui/vite.config.ts`**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
})
```

- [ ] **Step 3: Create `aass_agents/dashboard/ui/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "isolatedModules": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create `aass_agents/dashboard/ui/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AASS Pipeline Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Create `aass_agents/dashboard/ui/tailwind.config.ts`**

```typescript
import type { Config } from 'tailwindcss'

export default {
  content: ['./src/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
} satisfies Config
```

- [ ] **Step 6: Create `aass_agents/dashboard/ui/src/test-setup.ts`**

```typescript
import '@testing-library/jest-dom'
```

- [ ] **Step 7: Create `aass_agents/dashboard/ui/src/main.tsx`**

```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
```

- [ ] **Step 8: Create `aass_agents/dashboard/ui/src/index.css`**

The spec requires a **radial pulse** for running nodes (not Tailwind's fade pulse). Define a custom keyframe here:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@keyframes radial-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.6); }
  50%       { box-shadow: 0 0 0 8px rgba(59, 130, 246, 0); }
}

.animate-radial-pulse {
  animation: radial-pulse 1.5s ease-in-out infinite;
}
```

- [ ] **Step 9: Install dependencies**

```bash
cd aass_agents/dashboard/ui && npm install
```

- [ ] **Step 10: Commit**

```bash
git add aass_agents/dashboard/ui/
git commit -m "feat: scaffold Vite + React + TailwindCSS frontend for dashboard"
```

---

## Task 7: API Client (`api.ts`)

**Files:**
- Create: `aass_agents/dashboard/ui/src/api.ts`

- [ ] **Step 1: Write tests in `aass_agents/dashboard/ui/src/api.test.ts`**

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchRuns, fetchRun, fetchGraph, fetchEvolution } from './api'

global.fetch = vi.fn()

beforeEach(() => vi.clearAllMocks())

const mockJson = (data: unknown) =>
  Promise.resolve({ ok: true, json: () => Promise.resolve(data) } as Response)

describe('fetchRuns', () => {
  it('calls /api/runs', async () => {
    vi.mocked(fetch).mockReturnValue(mockJson([]))
    await fetchRuns()
    expect(fetch).toHaveBeenCalledWith('/api/runs')
  })
})

describe('fetchGraph', () => {
  it('returns nodes and edges', async () => {
    const graph = { nodes: [{ id: 'a', label: 'A', department: 'root' }], edges: [] }
    vi.mocked(fetch).mockReturnValue(mockJson(graph))
    const result = await fetchGraph()
    expect(result.nodes).toHaveLength(1)
  })
})
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd aass_agents/dashboard/ui && npm test 2>&1 | tail -20
```

- [ ] **Step 3: Create `aass_agents/dashboard/ui/src/api.ts`**

```typescript
// Type definitions
export interface Run {
  id: number
  trigger_input: string
  status: 'running' | 'completed' | 'failed'
  started_at: string
  finished_at: string | null
}

export interface ExecutionEvent {
  id: number
  run_id: number
  agent_name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  started_at: string | null
  finished_at: string | null
  output_sample: string | null
}

export interface GraphNode {
  id: string
  label: string
  department: string
}

export interface GraphEdge {
  source: string
  target: string
}

export interface Graph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface QueueEntry {
  agent_name: string
  priority: number
  confidence: string | null
  queued_at: string
  status: string
}

export interface Verdict {
  agent_name: string
  version: number
  status: string
  score_baseline: number | null
  created_at: string
}

export interface Evolution {
  queue: QueueEntry[]
  recent_verdicts: Verdict[]
  version_history: Record<string, Array<{ version: number; status: string; score_baseline: number | null }>>
}

// REST helpers
async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${path} → ${res.status}`)
  return res.json() as Promise<T>
}

export const fetchRuns = () => get<Run[]>('/api/runs')
export const fetchRun = (id: number) => get<{ run: Run; events: ExecutionEvent[] }>(`/api/runs/${id}`)
export const fetchGraph = () => get<Graph>('/api/graph')
export const fetchEvolution = () => get<Evolution>('/api/evolution')
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd aass_agents/dashboard/ui && npm test
```

- [ ] **Step 5: Commit**

```bash
git add aass_agents/dashboard/ui/src/api.ts aass_agents/dashboard/ui/src/api.test.ts
git commit -m "feat: add typed REST API client for dashboard"
```

---

## Task 8: `useRunSocket` Hook

**Files:**
- Create: `aass_agents/dashboard/ui/src/hooks/useRunSocket.ts`

- [ ] **Step 1: Write the test**

```typescript
// src/hooks/useRunSocket.test.ts
import { renderHook, act } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { useRunSocket } from './useRunSocket'
import type { ExecutionEvent } from '../api'

class MockWebSocket {
  onmessage: ((e: MessageEvent) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  readyState = WebSocket.OPEN
  close = vi.fn()
  static instances: MockWebSocket[] = []
  constructor() { MockWebSocket.instances.push(this) }
}

vi.stubGlobal('WebSocket', MockWebSocket)

describe('useRunSocket', () => {
  beforeEach(() => { MockWebSocket.instances = [] })

  it('opens a WebSocket for the given run_id', () => {
    renderHook(() => useRunSocket(42))
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('appends events from WebSocket messages', () => {
    const { result } = renderHook(() => useRunSocket(1))
    const event: ExecutionEvent = {
      id: 1, run_id: 1, agent_name: 'sales_orchestrator',
      status: 'running', started_at: '2026-03-26T00:00:00Z',
      finished_at: null, output_sample: null,
    }
    act(() => {
      MockWebSocket.instances[0].onmessage?.({ data: JSON.stringify(event) } as MessageEvent)
    })
    expect(result.current.events).toHaveLength(1)
    expect(result.current.events[0].agent_name).toBe('sales_orchestrator')
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Create `aass_agents/dashboard/ui/src/hooks/useRunSocket.ts`**

```typescript
import { useEffect, useRef, useState, useCallback } from 'react'
import type { ExecutionEvent } from '../api'

const MAX_RETRIES = 5
const RETRY_DELAY_MS = 2000

export function useRunSocket(runId: number | null) {
  const [events, setEvents] = useState<ExecutionEvent[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const retriesRef = useRef(0)

  const connect = useCallback(() => {
    if (runId === null) return
    const ws = new WebSocket(`/ws/runs/${runId}`)
    wsRef.current = ws

    ws.onmessage = (e: MessageEvent) => {
      const event: ExecutionEvent = JSON.parse(e.data as string)
      setEvents(prev => [...prev, event])
    }

    ws.onclose = () => {
      if (retriesRef.current < MAX_RETRIES) {
        retriesRef.current += 1
        setTimeout(connect, RETRY_DELAY_MS)
      }
    }

    ws.onerror = () => ws.close()
  }, [runId])

  useEffect(() => {
    setEvents([])
    retriesRef.current = 0
    connect()
    return () => wsRef.current?.close()
  }, [connect])

  return { events }
}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd aass_agents/dashboard/ui && npm test
```

- [ ] **Step 5: Commit**

```bash
git add aass_agents/dashboard/ui/src/hooks/
git commit -m "feat: add useRunSocket hook with auto-reconnect"
```

---

## Task 9: `useGraphStatus` Hook

**Files:**
- Create: `aass_agents/dashboard/ui/src/hooks/useGraphStatus.ts`

This hook merges the static graph (nodes + edges) with live event statuses to produce enriched `ReactFlowNode` objects.

- [ ] **Step 1: Write the test**

```typescript
// src/hooks/useGraphStatus.test.ts
import { describe, it, expect } from 'vitest'
import { applyEventsToNodes } from './useGraphStatus'
import type { GraphNode, ExecutionEvent } from '../api'

const nodes: GraphNode[] = [
  { id: 'company_orchestrator', label: 'Company', department: 'root' },
  { id: 'sales_orchestrator', label: 'Sales', department: 'sales' },
]

describe('applyEventsToNodes', () => {
  it('defaults all nodes to pending', () => {
    const result = applyEventsToNodes(nodes, [])
    expect(result.every(n => n.data.status === 'pending')).toBe(true)
  })

  it('marks a node running when a running event exists', () => {
    const events: ExecutionEvent[] = [{
      id: 1, run_id: 1, agent_name: 'sales_orchestrator',
      status: 'running', started_at: '2026-03-26T00:00:00Z',
      finished_at: null, output_sample: null,
    }]
    const result = applyEventsToNodes(nodes, events)
    const sales = result.find(n => n.id === 'sales_orchestrator')
    expect(sales?.data.status).toBe('running')
  })

  it('completed status overrides running', () => {
    const events: ExecutionEvent[] = [
      { id: 1, run_id: 1, agent_name: 'sales_orchestrator', status: 'running', started_at: null, finished_at: null, output_sample: null },
      { id: 2, run_id: 1, agent_name: 'sales_orchestrator', status: 'completed', started_at: null, finished_at: '2026-03-26T00:01:00Z', output_sample: 'ok' },
    ]
    const result = applyEventsToNodes(nodes, events)
    const sales = result.find(n => n.id === 'sales_orchestrator')
    expect(sales?.data.status).toBe('completed')
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Create `aass_agents/dashboard/ui/src/hooks/useGraphStatus.ts`**

```typescript
import { useMemo } from 'react'
import type { Node } from '@xyflow/react'
import type { GraphNode, ExecutionEvent } from '../api'

export type AgentStatus = 'pending' | 'running' | 'completed' | 'failed'

const STATUS_PRIORITY: Record<AgentStatus, number> = {
  pending: 0, running: 1, completed: 2, failed: 3,
}

export interface AgentNodeData extends Record<string, unknown> {
  label: string
  department: string
  status: AgentStatus
  outputSample: string | null
}

export function applyEventsToNodes(
  nodes: GraphNode[],
  events: ExecutionEvent[],
): Node<AgentNodeData>[] {
  // Build a map of agent_name → highest-priority status seen
  const statusMap = new Map<string, AgentStatus>()
  const outputMap = new Map<string, string | null>()

  for (const e of events) {
    const current = statusMap.get(e.agent_name) ?? 'pending'
    if (STATUS_PRIORITY[e.status as AgentStatus] > STATUS_PRIORITY[current]) {
      statusMap.set(e.agent_name, e.status as AgentStatus)
      if (e.output_sample) outputMap.set(e.agent_name, e.output_sample)
    }
  }

  return nodes.map((n, i) => ({
    id: n.id,
    position: { x: 0, y: i * 80 }, // layout handled by dagre in DAGPanel
    data: {
      label: n.label,
      department: n.department,
      status: statusMap.get(n.id) ?? 'pending',
      outputSample: outputMap.get(n.id) ?? null,
    },
    type: 'agentNode',
  }))
}

export function useGraphStatus(nodes: GraphNode[], events: ExecutionEvent[]) {
  return useMemo(() => applyEventsToNodes(nodes, events), [nodes, events])
}
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add aass_agents/dashboard/ui/src/hooks/useGraphStatus.ts \
        aass_agents/dashboard/ui/src/hooks/useGraphStatus.test.ts
git commit -m "feat: add useGraphStatus hook to merge graph with live statuses"
```

---

## Task 10: RunHistory + RunSelector Components

**Files:**
- Create: `aass_agents/dashboard/ui/src/components/RunHistory.tsx`
- Create: `aass_agents/dashboard/ui/src/components/RunSelector.tsx`

- [ ] **Step 1: Create `RunHistory.tsx`**

```tsx
import type { Run } from '../api'

interface Props {
  runs: Run[]
  selectedId: number | null
  onSelect: (id: number) => void
}

const STATUS_ICON: Record<string, string> = {
  running: '⏳',
  completed: '✅',
  failed: '❌',
}

function duration(run: Run): string {
  if (!run.finished_at) return '…'
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
  const s = Math.floor(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

export function RunHistory({ runs, selectedId, onSelect }: Props) {
  if (runs.length === 0) {
    return <p className="text-slate-400 text-sm px-2">No runs yet</p>
  }
  return (
    <ul className="space-y-1">
      {runs.map(run => (
        <li
          key={run.id}
          onClick={() => onSelect(run.id)}
          className={`cursor-pointer rounded px-2 py-1 text-sm flex justify-between items-center
            ${selectedId === run.id ? 'bg-slate-700' : 'hover:bg-slate-800'}`}
        >
          <span className="text-slate-300">#{run.id}</span>
          <span>{STATUS_ICON[run.status] ?? '?'} {duration(run)}</span>
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 2: Create `RunSelector.tsx`**

```tsx
import type { Run } from '../api'

interface Props {
  runs: Run[]
  selectedId: number | null
  onChange: (id: number) => void
}

export function RunSelector({ runs, selectedId, onChange }: Props) {
  return (
    <select
      value={selectedId ?? ''}
      onChange={e => onChange(Number(e.target.value))}
      className="bg-slate-800 text-slate-200 rounded px-2 py-1 text-sm border border-slate-600"
    >
      <option value="" disabled>Select a run…</option>
      {runs.map(run => (
        <option key={run.id} value={run.id}>
          Run #{run.id} — {run.status}
        </option>
      ))}
    </select>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add aass_agents/dashboard/ui/src/components/RunHistory.tsx \
        aass_agents/dashboard/ui/src/components/RunSelector.tsx
git commit -m "feat: add RunHistory and RunSelector components"
```

---

## Task 11: AgentDrawer Component

**Files:**
- Create: `aass_agents/dashboard/ui/src/components/AgentDrawer.tsx`

- [ ] **Step 1: Create `AgentDrawer.tsx`**

```tsx
import type { AgentNodeData } from '../hooks/useGraphStatus'

interface Props {
  nodeId: string | null
  data: AgentNodeData | null
  onClose: () => void
}

const STATUS_COLOUR: Record<string, string> = {
  pending: 'text-slate-400',
  running: 'text-blue-400',
  completed: 'text-green-400',
  failed: 'text-red-400',
}

export function AgentDrawer({ nodeId, data, onClose }: Props) {
  if (!nodeId || !data) return null

  return (
    <div className="fixed right-0 top-0 h-full w-80 bg-slate-900 border-l border-slate-700 p-4 z-50 overflow-y-auto">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-slate-200 font-semibold">{data.label}</h2>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-200">✕</button>
      </div>

      <dl className="space-y-2 text-sm">
        <dt className="text-slate-500">Agent ID</dt>
        <dd className="text-slate-300 font-mono">{nodeId}</dd>

        <dt className="text-slate-500">Department</dt>
        <dd className="text-slate-300 capitalize">{data.department}</dd>

        <dt className="text-slate-500">Status</dt>
        <dd className={`font-semibold ${STATUS_COLOUR[data.status] ?? 'text-slate-300'}`}>
          {data.status}
        </dd>

        {data.outputSample && (
          <>
            <dt className="text-slate-500">Output sample</dt>
            <dd className="text-slate-300 text-xs font-mono bg-slate-800 rounded p-2 whitespace-pre-wrap">
              {data.outputSample}
            </dd>
          </>
        )}
      </dl>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add aass_agents/dashboard/ui/src/components/AgentDrawer.tsx
git commit -m "feat: add AgentDrawer component for node detail"
```

---

## Task 12: AutoresearcherPanel Component

**Files:**
- Create: `aass_agents/dashboard/ui/src/components/AutoresearcherPanel.tsx`

- [ ] **Step 1: Create `AutoresearcherPanel.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { fetchEvolution, type Evolution } from '../api'

export function AutoresearcherPanel() {
  const [data, setData] = useState<Evolution | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetchEvolution()
      .then(setData)
      .catch(() => setError(true))
  }, [])

  if (error) {
    return (
      <div className="mt-4">
        <h3 className="text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
          Autoresearcher
        </h3>
        <p className="text-slate-500 text-xs">
          <span className="bg-slate-700 rounded px-1">Unavailable</span>
        </p>
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="mt-4">
      <h3 className="text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
        Autoresearcher
      </h3>

      <p className="text-slate-300 text-sm mb-1">
        Queue: {data.queue.length} agent{data.queue.length !== 1 ? 's' : ''}
      </p>

      {data.recent_verdicts.length > 0 && (
        <>
          <p className="text-slate-500 text-xs mt-2 mb-1">Last rewrites</p>
          <ul className="space-y-1">
            {data.recent_verdicts.slice(0, 5).map((v, i) => (
              <li key={i} className="text-xs text-slate-300">
                {v.agent_name} v{v.version} →{' '}
                <span className={v.status === 'stable' ? 'text-green-400' : 'text-red-400'}>
                  {v.status}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add aass_agents/dashboard/ui/src/components/AutoresearcherPanel.tsx
git commit -m "feat: add AutoresearcherPanel component"
```

---

## Task 13: DAGPanel Component

**Files:**
- Create: `aass_agents/dashboard/ui/src/components/DAGPanel.tsx`

> **Note:** ReactFlow v12 (`@xyflow/react`) is used. Node layout uses a simple level-based algorithm (no dagre needed since we have a two-level hierarchy). Check `@xyflow/react` docs for the current `ReactFlow` import path and `NodeTypes` API.

- [ ] **Step 1: Add `dagre` for auto-layout (optional but recommended)**

```bash
cd aass_agents/dashboard/ui && npm install dagre @types/dagre
```

If dagre install conflicts, skip it and use the manual position calculation below.

- [ ] **Step 2: Create `DAGPanel.tsx`**

```tsx
import { useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type NodeTypes,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { GraphEdge } from '../api'
import type { AgentNodeData } from '../hooks/useGraphStatus'

const STATUS_COLOUR: Record<string, string> = {
  pending: '#94a3b8',
  running: '#3b82f6',
  completed: '#22c55e',
  failed: '#ef4444',
}

function AgentNode({ data }: { data: AgentNodeData }) {
  const colour = STATUS_COLOUR[data.status] ?? STATUS_COLOUR.pending
  const isRunning = data.status === 'running'

  return (
    <div
      style={{ borderColor: colour }}
      className={`rounded border-2 px-3 py-2 bg-slate-800 text-sm text-slate-200 min-w-[140px] text-center
        ${isRunning ? 'animate-radial-pulse' : ''}`}
    >
      {data.label}
    </div>
  )
}

const NODE_TYPES: NodeTypes = { agentNode: AgentNode }

interface Props {
  nodes: Node<AgentNodeData>[]
  edges: GraphEdge[]
  onNodeClick: (nodeId: string, data: AgentNodeData) => void
}

/** Simple level-based layout: root at top, departments in row 1, leaves in row 2. */
function layoutNodes(nodes: Node<AgentNodeData>[], edges: GraphEdge[]): Node<AgentNodeData>[] {
  const childOf = new Map<string, string>()
  for (const e of edges) childOf.set(e.target, e.source)

  const level = (id: string): number => {
    const parent = childOf.get(id)
    if (!parent) return 0
    return 1 + level(parent)
  }

  const byLevel = new Map<number, Node<AgentNodeData>[]>()
  for (const n of nodes) {
    const l = level(n.id)
    if (!byLevel.has(l)) byLevel.set(l, [])
    byLevel.get(l)!.push(n)
  }

  return nodes.map(n => {
    const l = level(n.id)
    const siblings = byLevel.get(l)!
    const idx = siblings.indexOf(n)
    return { ...n, position: { x: idx * 180, y: l * 120 } }
  })
}

export function DAGPanel({ nodes, edges, onNodeClick }: Props) {
  const rfEdges: Edge[] = useMemo(
    () => edges.map(e => ({ id: `${e.source}-${e.target}`, source: e.source, target: e.target })),
    [edges],
  )

  const laidOutNodes = useMemo(() => layoutNodes(nodes, edges), [nodes, edges])

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node<AgentNodeData>) => {
      onNodeClick(node.id, node.data)
    },
    [onNodeClick],
  )

  if (nodes.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-500">
        No runs yet
      </div>
    )
  }

  return (
    <div className="flex-1 h-full">
      <ReactFlow
        nodes={laidOutNodes}
        edges={rfEdges}
        nodeTypes={NODE_TYPES}
        onNodeClick={handleNodeClick}
        fitView
      >
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add aass_agents/dashboard/ui/src/components/DAGPanel.tsx
git commit -m "feat: add DAGPanel component with ReactFlow and level-based layout"
```

---

## Task 14: App.tsx — Root Layout

**Files:**
- Create: `aass_agents/dashboard/ui/src/App.tsx`
- Create: `aass_agents/dashboard/ui/src/App.test.tsx`

- [ ] **Step 1: Write `App.test.tsx`**

```tsx
import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import App from './App'

vi.mock('./api', () => ({
  fetchRuns: () => Promise.resolve([]),
  fetchGraph: () => Promise.resolve({ nodes: [], edges: [] }),
  fetchEvolution: () => Promise.resolve({ queue: [], recent_verdicts: [], version_history: {} }),
}))

test('renders dashboard title', async () => {
  render(<App />)
  expect(screen.getByText(/AASS Pipeline Dashboard/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Create `App.tsx`**

```tsx
import { useCallback, useEffect, useState } from 'react'
import { fetchRuns, fetchGraph, type Run, type Graph } from './api'
import { RunHistory } from './components/RunHistory'
import { RunSelector } from './components/RunSelector'
import { DAGPanel } from './components/DAGPanel'
import { AgentDrawer } from './components/AgentDrawer'
import { AutoresearcherPanel } from './components/AutoresearcherPanel'
import { useRunSocket } from './hooks/useRunSocket'
import { useGraphStatus, type AgentNodeData } from './hooks/useGraphStatus'

export default function App() {
  const [runs, setRuns] = useState<Run[]>([])
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [graph, setGraph] = useState<Graph>({ nodes: [], edges: [] })
  const [drawer, setDrawer] = useState<{ id: string; data: AgentNodeData } | null>(null)

  useEffect(() => {
    fetchRuns().then(r => { setRuns(r); if (r.length > 0) setSelectedRunId(r[0].id) })
    fetchGraph().then(setGraph)
  }, [])

  const { events } = useRunSocket(selectedRunId)
  const enrichedNodes = useGraphStatus(graph.nodes, events)

  const handleNodeClick = useCallback((id: string, data: AgentNodeData) => {
    setDrawer({ id, data })
  }, [])

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 flex flex-col">
      {/* Header */}
      <header className="flex items-center gap-4 px-4 py-3 border-b border-slate-800">
        <RunSelector runs={runs} selectedId={selectedRunId} onChange={setSelectedRunId} />
        <h1 className="text-lg font-semibold">AASS Pipeline Dashboard</h1>
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* DAG — main panel */}
        <main className="flex-1 flex flex-col">
          <DAGPanel
            nodes={enrichedNodes}
            edges={graph.edges}
            onNodeClick={handleNodeClick}
          />
        </main>

        {/* Sidebar */}
        <aside className="w-56 border-l border-slate-800 px-3 py-4 overflow-y-auto">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
            Recent Runs
          </h2>
          <RunHistory runs={runs} selectedId={selectedRunId} onSelect={setSelectedRunId} />
          <AutoresearcherPanel />
        </aside>
      </div>

      {/* Node detail drawer */}
      <AgentDrawer
        nodeId={drawer?.id ?? null}
        data={drawer?.data ?? null}
        onClose={() => setDrawer(null)}
      />
    </div>
  )
}
```

- [ ] **Step 4: Run all frontend tests — expect PASS**

```bash
cd aass_agents/dashboard/ui && npm test
```
Expected: All tests PASS (api, hooks, App smoke test).

- [ ] **Step 5: Verify dev server starts**

```bash
cd aass_agents/dashboard/ui && npm run dev &
# Open http://localhost:5173 — should render empty dashboard with "No runs yet"
```

- [ ] **Step 6: Commit**

```bash
git add aass_agents/dashboard/ui/src/App.tsx aass_agents/dashboard/ui/src/App.test.tsx
git commit -m "feat: add App root layout wiring DAG, sidebar, and drawer together"
```

---

## Task 15: Final Integration Check

- [ ] **Step 1: Run all Python tests**

```bash
cd aass_agents && pytest --tb=short -q
```
Expected: All tests pass.

- [ ] **Step 2: Run all frontend tests**

```bash
cd aass_agents/dashboard/ui && npm test
```
Expected: All tests pass.

- [ ] **Step 3: Start backend + frontend together**

Terminal 1:
```bash
cd aass_agents && uvicorn dashboard.server:app --reload --port 8000
```

Terminal 2:
```bash
cd aass_agents/dashboard/ui && npm run dev
```

- [ ] **Step 4: Manual smoke test**

1. Open `http://localhost:5173`
2. Verify: dashboard renders with empty state ("No runs yet" or grey DAG)
3. Verify: `/api/graph` returns nodes + edges
4. Verify: `/api/evolution` returns `{queue, recent_verdicts, version_history}`
5. In Python: `python -c "from tools.evolution_db import start_run_sync; print(start_run_sync('smoke test'))"`
6. Refresh dashboard — new run should appear in sidebar

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete agent pipeline dashboard — FastAPI + React + WebSocket"
```
