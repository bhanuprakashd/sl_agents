# SOTA Autonomous Supervisor Layer — Design Spec

**Date:** 2026-03-24
**Project:** sales-adk-agents
**Status:** Approved for implementation

---

## Problem Statement

The current `sales-adk-agents` system has four failure modes that make it unsuitable for fully autonomous operation:

- **A — Context loss:** Agents lose pipeline state mid-run (e.g. architect decisions forgotten by backend builder)
- **B — No observability:** Black-box execution with no audit trail
- **C — Runaway execution:** No loop detection or failure isolation; one stuck agent blocks everything
- **D — Stale context:** Agents act on outdated research/proposals without knowing the world has changed

---

## Approach: Hybrid Supervisor Module

Keep all existing ADK `Agent` classes and `sub_agents=[]` definitions unchanged. Add a pure Python supervisor layer that hooks into the **ADK runner event stream** in `main.py` — not through tool calls to orchestrators. The supervisor intercepts ADK events emitted by `runner.run_async()` to log, guard, and checkpoint every agent invocation. Zero structural changes to any agent file.

**Key constraint:** The supervisor itself makes zero additional LLM calls. It may route to the existing `reflection_agent` (already part of each orchestrator's `sub_agents` list), which counts against the reflection loop budget already in the system — not as new overhead.

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                     main.py (ADK Runner)                    │
│                                                            │
│   runner.run_async(agent, session, message)                │
│           │                                                │
│           ▼                                                │
│   ┌───────────────────────────────────────────────────┐   │
│   │         SupervisorEventStream (tools/supervisor.py)│   │
│   │                                                   │   │
│   │  Pre-event hook:                                  │   │
│   │    StalenessRegistry.check()                      │   │
│   │    LoopGuard.check()                              │   │
│   │    CircuitBreaker.check()                         │   │
│   │    EventLog.write(agent.called)                   │   │
│   │    PipelineRun.set_step(running)                  │   │
│   │                                                   │   │
│   │  Post-event hook:                                 │   │
│   │    EventLog.write(agent.returned)                 │   │
│   │    PipelineRun.checkpoint()                       │   │
│   │    StalenessRegistry.update_validity()            │   │
│   │    CircuitBreaker.record_result()                 │   │
│   └───────────────────────────────────────────────────┘   │
│           │                                                │
│           ▼                                                │
│   ┌─────────────────────────────────────────────────┐     │
│   │           company_orchestrator                   │     │
│   │  ┌──────────────┐ ┌───────────┐ ┌────────────┐  │     │
│   │  │  marketing_  │ │  sales_   │ │  product_  │  │     │
│   │  │ orchestrator │ │orchestrat.│ │orchestrat. │  │     │
│   │  └──────┬───────┘ └─────┬─────┘ └─────┬──────┘  │     │
│   │         │               │             │          │     │
│   │    sub-agents...   sub-agents...  sub-agents...  │     │
│   └─────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────┘
                              │
                    sales_memory.db + product_pipeline.db
```

**Integration point — two mechanisms, each with a distinct role:**

1. **`before_agent_callback` / `after_agent_callback`** set on the root `company_orchestrator` agent. ADK propagates these callbacks to all sub-agent invocations in the tree. `before_agent_callback` receives a `CallbackContext` and can return a `Content` object to **skip the agent call entirely** — this is where staleness checks, loop guards, and circuit breaker checks run. Returning `None` allows the call to proceed normally. This is the only way to truly block a call before ADK dispatches it.

2. **`runner.run_async()` event stream** — used for post-event logging (`agent.returned`, duration, output excerpt) and state checkpointing. The event stream cannot block calls — it only observes what has already happened.

No agent files change. Callbacks are set programmatically in `main.py` on the already-constructed `company_orchestrator` instance before the runner starts.

---

## Components

### 1. PipelineRun — State Machine

- Each top-level user request creates a `PipelineRun` with a UUID (`run_id`)
- Steps transition: `pending → running → completed | failed | blocked`
- On any unhandled exception: snapshots `current_step` and full `context_json` to `supervisor_runs`
- For the **product pipeline**: `checkpoint_json` stores a reference to the `product_id` and `current_step` from the existing `product_pipeline.db` — the existing product state store remains the source of truth for product-specific data; `supervisor_runs` is the meta-layer only
- Next invocation with same `run_id` resumes from checkpoint — no restart from scratch
- Supervisor wrapping covers **all** agent levels: `company_orchestrator → team orchestrators → sub-agents`

### 2. EventLog — Append-Only Audit Trail

- Every agent invocation in the ADK event stream writes two events: `agent.called` and `agent.returned`
- Optional events: `reflection.triggered`, `reflection.verdict`, `loop.detected`, `circuit.opened`, `staleness.hit`, `hitl.escalated`
- Stored in `supervisor_events` table in `sales_memory.db`
- Payload includes: `input_hash` (SHA-256), output excerpt (first 500 chars), `duration_ms`, error message if any
- **Input hash definition:** SHA-256 of the delegation message text passed to the sub-agent, with run-specific fields (timestamps, run_ids, session ids) stripped before hashing. Computed in the supervisor pre-event hook.
- Queryable by `run_id`, `agent_name`, `timestamp`, `pipeline_type`
- Uses `asyncio.to_thread` + WAL mode for safe concurrent async writes (matching existing `memory_store.py` pattern)

### 3. LoopGuard — Loop Detection

Sliding window of last 10 agent events per `run_id`. Two detection patterns:

| Pattern | Condition | Action |
|---|---|---|
| Exact loop | Same agent + identical `input_hash` 3+ times in window | Hard stop → HITL |
| Thrash loop | Same agent appears 5+ times in window regardless of input | Route to `reflection_agent` first (uses existing budget); if still unresolved → HITL |

### 4. CircuitBreaker — Failure Isolation

- Per-agent failure counter persisted in `supervisor_circuit_breakers` in `sales_memory.db`
- After 3 consecutive failures: circuit opens, agent is bypassed, run continues with a flagged gap
- Circuit state: `closed` (normal) | `open` (bypassed) | `half-open` (testing after reset)
- Resets after 30 minutes automatically (half-open state — next call is a probe)
- **Manual reset:** CLI-only via `python main.py reset-circuit <agent_name>`. NOT exposed as an ADK tool to orchestrators — preventing autonomous circuit override

### 5. StalenessRegistry — Two-Layer Invalidation

**TTL defaults — all 23 agents:**

| Agent | TTL | Notes |
|---|---|---|
| lead_researcher | 7 days | |
| outreach_composer | 14 days | |
| sales_call_prep | 3 days | Situation changes fast |
| objection_handler | per-run | Situation-specific, never reuse |
| proposal_generator | 30 days | |
| crm_updater | per-run | Always re-run |
| deal_analyst | 1 day | |
| audience_builder | 7 days | |
| campaign_composer | 14 days | |
| content_strategist | 14 days | |
| seo_analyst | 30 days | Keywords stable medium-term |
| campaign_analyst | 7 days | |
| brand_voice | 90 days | Guidelines rarely change |
| pm_agent | per product run | |
| architect_agent | ∞ | Manual reset only |
| devops_agent | per product run | |
| db_agent | per product run | |
| backend_builder_agent | per product run | |
| frontend_builder_agent | per product run | |
| qa_agent | per product run | |
| reflection_agent | N/A | Meta-agent, not cached |
| company_orchestrator | N/A | Router, not cached |
| Default (unlisted) | 7 days | Safety net for any new agent |

**Entity keying:** The staleness table uses `(entity_id, entity_type, agent_name)` as primary key — not `company_name`. `entity_type` is one of: `company` (sales), `campaign` (marketing), `product` (product pipeline). This supports all three pipelines.

**Event invalidation triggers:**

| Event | Invalidates |
|---|---|
| new_call_note added | sales_call_prep, crm_updater |
| deal stage change | proposal_generator, deal_analyst |
| new product version deployed | proposal_generator, qa_agent |
| win/loss recorded | audience_builder, campaign_composer |
| new company news detected | lead_researcher |
| campaign performance data updated | campaign_analyst, campaign_composer |

Staleness check runs **before** every agent event in the stream. Stale output triggers re-run, not reuse.

### 6. DeadLetterQueue

- Runs that exhaust all retries and circuit-breaker fallbacks written to `supervisor_dlq` in `sales_memory.db`
- Surfaced to user: `"⚠ Run <id> blocked on <agent>. Completed: <steps>. Resume when ready with: python main.py resume <run_id>"`
- `list_dlq` tool exposed to orchestrators returns: `{run_id, pipeline_type, blocked_on, last_error, completed_steps: [...], created_at}`

---

## Data Model

### `sales_memory.db` — New Tables

```sql
-- One row per top-level user request (all pipeline types)
CREATE TABLE supervisor_runs (
    run_id TEXT PRIMARY KEY,
    pipeline_type TEXT NOT NULL,     -- sales | marketing | product
    status TEXT NOT NULL DEFAULT 'pending',  -- pending|running|completed|failed|blocked
    current_step INT DEFAULT 0,
    total_steps INT,
    context_json TEXT,               -- full input context snapshot
    checkpoint_json TEXT,            -- step state at last checkpoint
                                     -- for product: {product_id, product_step}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Append-only event stream
CREATE TABLE supervisor_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    event_type TEXT NOT NULL,        -- agent.called|agent.returned|reflection.triggered
                                     -- loop.detected|circuit.opened|staleness.hit|hitl.escalated
    payload_json TEXT,               -- {input_hash, output_excerpt, duration_ms, error}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_supervisor_events_run ON supervisor_events(run_id);
CREATE INDEX idx_supervisor_events_agent ON supervisor_events(agent_name, created_at);

-- Per-agent failure state
CREATE TABLE supervisor_circuit_breakers (
    agent_name TEXT PRIMARY KEY,
    failure_count INT NOT NULL DEFAULT 0,
    last_failure_at TIMESTAMP,
    opened_at TIMESTAMP,                  -- set when state → open; used as 30-min reset baseline
    state TEXT NOT NULL DEFAULT 'closed'  -- closed|open|half-open
);

-- Exhausted runs needing human
CREATE TABLE supervisor_dlq (
    run_id TEXT PRIMARY KEY,
    pipeline_type TEXT,
    blocked_on TEXT,
    last_error TEXT,
    completed_steps_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Staleness tracking per agent output (entity-keyed for all pipeline types)
CREATE TABLE supervisor_output_validity (
    entity_id TEXT NOT NULL,         -- company_name | campaign_name | product_id
    entity_type TEXT NOT NULL,       -- company | campaign | product
    agent_name TEXT NOT NULL,
    run_id TEXT,
    last_run_at TIMESTAMP,           -- when this output was last produced; used to recalculate
                                     -- expires_at if TTL policy changes after row is written
    invalidated_by TEXT,             -- ttl | event:<event_name> | manual
    expires_at TIMESTAMP,            -- = last_run_at + TTL for this agent_name
    PRIMARY KEY (entity_id, entity_type, agent_name)
);
```

### Read-Only Observability Tools vs. Control-Plane Prohibition

The spec prohibits supervisor integration through tool calls to orchestrators for **control-plane operations** (dispatching agents, resetting circuits, resuming runs). This prevents orchestrators from autonomously overriding supervisor guards.

`list_dlq` is explicitly a **read-only observability tool** — it queries what is blocked and returns data for display. It does not affect supervisor state. This is the same category as `list_active_deals` or `recall_past_outputs` already in the system. Its exposure as an ADK tool to orchestrators is intentional and does not violate the control-plane prohibition.

The rule: if a tool **writes** supervisor state or **bypasses** a guard → CLI-only. If a tool **reads** supervisor state → may be exposed as an ADK tool.

### `product_pipeline.db` — Unchanged

Existing `product_pipeline_state` and `product_step_log` tables remain the authoritative source for product pipeline data. `supervisor_runs.checkpoint_json` for product runs stores `{"product_id": "...", "product_step": N}` — a pointer to the product DB, not a duplicate.

---

## Integration Point: `main.py`

The supervisor wraps the ADK runner in `main.py`. No agent files change.

```python
# main.py (conceptual — exact ADK runner API may vary)
from tools.supervisor import Supervisor
from google.adk.agents import CallbackContext, Content

supervisor = Supervisor()

def before_agent_callback(ctx: CallbackContext) -> Content | None:
    """
    Runs BEFORE ADK dispatches any agent call.
    Return Content to skip the agent (guard triggered).
    Return None to allow the call to proceed.
    """
    run_id = ctx.state.get("run_id")
    agent_name = ctx.agent_name
    input_text = ctx.user_content.parts[0].text if ctx.user_content else ""

    block_reason = supervisor.pre_call_check(run_id, agent_name, input_text)
    if block_reason:
        # HITL escalation message returned as agent output
        return Content(parts=[Part(text=block_reason)])
    supervisor.log_called(run_id, agent_name, input_text)
    return None  # proceed normally

def after_agent_callback(ctx: CallbackContext, response: Content) -> Content | None:
    """Runs AFTER ADK gets the agent's response. Used for logging and checkpointing."""
    run_id = ctx.state.get("run_id")
    supervisor.log_returned(run_id, ctx.agent_name, response)
    supervisor.checkpoint(run_id, ctx.agent_name)
    supervisor.update_validity(run_id, ctx.agent_name, ctx.state)
    return None  # pass response through unchanged

# Attach callbacks to root agent — ADK propagates to all sub-agents
company_orchestrator.before_agent_callback = before_agent_callback
company_orchestrator.after_agent_callback = after_agent_callback
```

**Concurrency:** All supervisor DB writes use `asyncio.to_thread(sqlite_call)` matching the pattern in `shared/memory_store.py`. SQLite opened in WAL mode.

---

## HITL Escalation — Exactly 4 Triggers

Only genuine blockers surface to the human:

| Trigger | Message |
|---|---|
| Exact loop detected | `"⚠ Loop: <agent> called 3x with same input. Last output: <excerpt>. Try different approach or skip?"` |
| Circuit opened | `"⚠ <agent> failed 3x. Last error: <msg>. Fix the issue or skip this step? Reset with: python main.py reset-circuit <agent>"` |
| Run added to DLQ | `"⚠ Run <id> blocked after all retries on <agent>. Completed: <steps>. Resume when ready: python main.py resume <id>"` |
| Ambiguous requirement | `"⚠ Cannot proceed without: <specific field>. Everything else is ready."` |

**Does NOT trigger HITL** (autonomous handling):
- Reflection NEEDS_REVISION → re-runs agent (max 2 cycles, existing reflection loop)
- Staleness hit → re-runs agent automatically
- Single agent failure → retries up to circuit breaker threshold (3)
- Soft thrash loop → routes to `reflection_agent` for diagnosis first

---

## SOTA Patterns Incorporated

| Pattern | Source Inspiration | Failure Mode Solved |
|---|---|---|
| Event sourcing | Temporal, LangGraph | B — full audit trail |
| Circuit breaker | Netflix Hystrix | C — failure isolation |
| Saga / checkpoint-resume | Distributed sagas | A — no lost pipeline context |
| Sliding window loop detection | AgentBench, AutoGPT post-mortems | C — stops thrash loops |
| TTL + event invalidation | LlamaIndex, LangMem | D — no stale context |
| Dead letter queue | Kafka, SQS | B+C — human-visible triage |
| Structured state machine | LangGraph, CrewAI | A — explicit step transitions |
| Runner-level event interception | LangGraph node hooks, Temporal activities | All — non-invasive observability |

---

## Files to Create / Modify

**New:**
- `tools/supervisor.py` — `SupervisorEventStream`, `PipelineRun`, `LoopGuard`, `CircuitBreaker`, `StalenessRegistry`, `DeadLetterQueue` (~600 lines)
- `tools/supervisor_db.py` — schema init + async query helpers for supervisor tables
- `tests/test_supervisor.py` — unit tests for all 5 components (uses `unittest.mock` time-override for TTL tests; event-injection helper for invalidation tests)

**Modified:**
- `main.py` — wrap `runner.run_async()` with `SupervisorEventStream`
- `shared/memory_store.py` — call `init_supervisor_tables()` on DB init

**Unchanged:**
- All `agents/*.py` files
- `tools/product_memory_tools.py`
- `shared/models.py`

---

## Success Criteria

- [ ] Any pipeline can be resumed from last checkpoint after a crash (product: from exact step N, sales/marketing: from last completed agent)
- [ ] Every agent invocation produces at minimum two structured events (`agent.called`, `agent.returned`) in `supervisor_events`
- [ ] Exact loops are detected and stopped before the 4th call with same input hash
- [ ] Stale outputs (TTL or event-triggered) are automatically re-run without user intervention
- [ ] A failing agent opens its circuit after 3 consecutive failures and is bypassed cleanly
- [ ] HITL is triggered for exactly the 4 defined blockers; all other failure paths are handled autonomously
- [ ] `reset_circuit` is only accessible via CLI, not via any agent tool
- [ ] All supervisor logic has ≥80% test coverage; TTL tests use time-mock; event tests use injection helper
- [ ] No changes required to any `agents/*.py` file
