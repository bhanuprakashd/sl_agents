# Autoresearcher — Self-Evolving Agent Loop Design Specification

> **Status:** Approved for implementation
> **Date:** 2026-03-25
> **Inspired by:** Karpathy's autoresearch (self-improving loop pattern)
> **Extends:** `docs/superpowers/specs/2026-03-25-engineering-research-teams-design.md`

**Goal:** Add a self-evolving `autoresearcher` department to `sales-adk-agents` that continuously monitors all agent outputs, identifies underperforming agents, rewrites their `INSTRUCTION` strings in-place, and automatically rolls back if quality drops.

**Architecture:** New top-level department (`autoresearcher_orchestrator`) wired into `company_orchestrator` as a peer alongside Sales, Marketing, Product, Engineering, Research, and QA. Four specialist agents handle distinct phases of the evolution loop. A new SQLite-backed tool layer manages version snapshots, scores, and rollback state.

**Tech Stack:** Python 3.11+, Google ADK, SQLite (evolution DB), existing supervisor layer, existing memory tools.

---

## 1. System Context

The system (`sales-adk-agents`) already has:

- `company_orchestrator` — top-level router
- `sales_orchestrator`, `marketing_orchestrator`, `product_orchestrator` — existing departments
- `engineering_orchestrator`, `research_orchestrator`, `qa_orchestrator` — approved (per prior spec)
- `reflection_agent` factory (`make_reflection_agent()`) — scores agent outputs 1-10 in real time
- Supervisor layer: `tools/supervisor.py` with event log, loop guard, circuit breaker, staleness registry, DLQ
- Memory tools: `tools/memory_tools.py` — `save_agent_output`, `recall_past_outputs`
- Existing tools: `github_tools.py`, `code_gen_tools.py`, `research_tools.py`, `http_tools.py`

**Pattern every team follows:**

- One orchestrator with `sub_agents=[]`, `tools=[]`, `instruction=INSTRUCTION`
- Each orchestrator gets `make_reflection_agent()` — never shares singleton
- Specialist agents: `Agent(model=MODEL, name=..., description=..., instruction=..., tools=[...])`
- Memory protocol: recall at session start, save after each agent completes
- Reflection loop: invoke after sub-agent, quality check, re-invoke if needed (max 2 cycles)
- Autonomous execution: no user confirmation between steps; pause only for genuine blockers

---

## 2. Target Architecture

```
company_orchestrator
├── sales_orchestrator           (existing)
├── marketing_orchestrator       (existing)
├── product_orchestrator         (existing)
├── engineering_orchestrator     (approved spec)
├── research_orchestrator        (approved spec)
├── qa_orchestrator              (approved spec)
└── autoresearcher_orchestrator  ← NEW
    ├── evaluator_agent
    ├── hypothesis_agent
    ├── rewriter_agent
    └── rollback_watchdog_agent
```

**New files:**

```
agents/autoresearcher_orchestrator_agent.py
agents/evaluator_agent.py
agents/hypothesis_agent.py
agents/rewriter_agent.py
agents/rollback_watchdog_agent.py
tools/evolution_tools.py
tools/evolution_db.py
tests/test_evolution_db.py
tests/test_evolution_tools.py
tests/test_autoresearcher.py
```

---

## 3. Evolution Loop

```
┌─────────────────────────────────────────────────────────┐
│                   EVOLUTION LOOP                        │
│                                                         │
│  1. DETECT (evaluator_agent)                            │
│     - Batch: reads last N outputs from supervisor DB    │
│     - Real-time: watches evolution_events table for     │
│       reflection scores < threshold (default: 6/10)     │
│     → Flags agent_name + evidence (bad output samples)  │
│                                                         │
│  2. HYPOTHESIZE (hypothesis_agent)                      │
│     - Reads current INSTRUCTION of flagged agent        │
│     - Reads 3-5 bad output samples                      │
│     - Generates: "root cause" + "proposed new           │
│       INSTRUCTION"                                      │
│     → Produces: hypothesis record saved to DB           │
│                                                         │
│  3. REWRITE (rewriter_agent)                            │
│     - Snapshots current INSTRUCTION to evolution_db     │
│       (version N)                                       │
│     - Patches .py file: replaces INSTRUCTION string     │
│     - Logs: agent_name, version, timestamp, hypothesis  │
│     → Agent now runs new instruction live               │
│                                                         │
│  4. WATCH (rollback_watchdog_agent)                     │
│     - Monitors next 5 outputs from rewritten agent      │
│     - Computes avg score vs pre-rewrite baseline        │
│     - If avg score WORSE (>10% drop) → restores ver. N  │
│     - If avg score BETTER → marks version N+1 stable    │
│     → Loop returns to step 1                            │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Triggers

### 4.1 Periodic (Batch)

The supervisor's existing scheduler triggers `autoresearcher_orchestrator` every N completed tasks (configurable, default: 20). The evaluator runs a full batch review across all departments.

### 4.2 Event-Driven (Real-Time)

When `reflection_agent` scores an output below threshold (default: 6/10), it logs to `evolution_events` table. The evaluator monitors this table and immediately initiates the hypothesis → rewrite → watch cycle for the flagged agent.

---

## 5. Database Schema (`evolution_db.py`)

SQLite-backed, following the pattern of `supervisor_db.py`.

```sql
-- Version history: one row per instruction version per agent
CREATE TABLE agent_versions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name       TEXT NOT NULL,
    version          INTEGER NOT NULL,
    instruction_text TEXT NOT NULL,
    score_baseline   REAL,          -- avg score of last 10 outputs before this rewrite
    status           TEXT DEFAULT 'active',  -- active | rolled_back | superseded
    created_at       TEXT NOT NULL
);

-- Score signals feeding the evolution loop
CREATE TABLE evolution_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name   TEXT NOT NULL,
    trigger_type TEXT NOT NULL,    -- reflection_score | batch_review | manual
    score        REAL NOT NULL,
    output_sample TEXT,            -- truncated text of the bad output
    created_at   TEXT NOT NULL
);

-- Hypothesis records linking cause to proposed fix
CREATE TABLE hypotheses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name      TEXT NOT NULL,
    version         INTEGER NOT NULL,     -- target version this hypothesis produced
    root_cause      TEXT NOT NULL,
    hypothesis_text TEXT NOT NULL,        -- the proposed new INSTRUCTION
    created_at      TEXT NOT NULL
);

-- Per-agent rewrite lock: prevents concurrent rewrites
CREATE TABLE rewrite_locks (
    agent_name   TEXT PRIMARY KEY,
    locked_at    TEXT NOT NULL,
    version      INTEGER NOT NULL
);
```

---

## 6. Tool Layer (`evolution_tools.py`)

Used only by `rewriter_agent` and `rollback_watchdog_agent`. All disk writes go through this module.

```python
# Version management
snapshot_instruction(agent_name, version, instruction_text, score_baseline) → None
restore_instruction(agent_name, version) → None   # reads from DB, patches disk

# Disk patching
patch_instruction(agent_file_path, new_instruction) → None  # regex replaces INSTRUCTION = """..."""

# Scoring
get_baseline_score(agent_name, last_n=10) → float
get_post_rewrite_scores(agent_name, after_version, n=5) → float

# Events
log_evolution_event(agent_name, trigger_type, score, output_sample) → None

# Locks
acquire_rewrite_lock(agent_name, version) → bool   # returns False if already locked
release_rewrite_lock(agent_name) → None

# Status
get_evolution_history(agent_name) → list[dict]     # ordered version history
get_rewrite_count_last_24h(agent_name) → int
```

---

## 7. Specialist Agents

### 7.1 `evaluator_agent`

**Real-world title:** Quality Evaluator

**Tools:** `evolution_db` read functions, `supervisor_db` read functions, `recall_past_outputs`

**Inputs:** supervisor event log, evolution_events table, configurable score threshold (default: 6/10)

**Outputs:** ranked list of flagged agents with evidence packets (agent_name, bad output samples, avg score, trigger type)

**Scoring rubric (per output):**
- Accuracy: did it answer the actual question? (1-3)
- Completeness: were all required elements present? (1-3)
- Actionability: is the output usable downstream? (1-4)

Total: 1-10. Below 6 = flagged.

### 7.2 `hypothesis_agent`

**Real-world title:** Improvement Researcher

**Tools:** `read_agent_instruction(agent_name)` (reads .py file), `recall_past_outputs`, `evolution_db` read

**Inputs:** flagged agent_name, 3-5 bad output samples, current INSTRUCTION text

**Outputs:** structured hypothesis record:
```
ROOT CAUSE: [1-2 sentence diagnosis]
GAPS IN CURRENT INSTRUCTION: [bullet list]
PROPOSED INSTRUCTION: [full rewritten INSTRUCTION string]
CONFIDENCE: [high/medium/low]
```

**Constraint:** hypothesis_agent NEVER writes to disk. Output is a text record only.

### 7.3 `rewriter_agent`

**Real-world title:** Instruction Engineer

**Tools:** `evolution_tools` (all write functions), `acquire_rewrite_lock`, `snapshot_instruction`, `patch_instruction`

**Inputs:** hypothesis record from hypothesis_agent

**Process:**
1. Check `get_rewrite_count_last_24h` — if ≥ 3 for this agent, log to supervisor DLQ and abort
2. `acquire_rewrite_lock` — if locked, abort (another rewrite in progress)
3. `get_baseline_score` — record pre-rewrite avg
4. `snapshot_instruction` — save current version to DB
5. `patch_instruction` — write new INSTRUCTION to .py file
6. Log to evolution_events

**Output:** version record with new version number, baseline score, hypothesis id

### 7.4 `rollback_watchdog_agent`

**Real-world title:** Stability Monitor

**Tools:** `evolution_tools` (scoring + restore functions), `release_rewrite_lock`, `save_agent_output`

**Inputs:** agent_name, version number, baseline score (passed from rewriter_agent)

**Process:**
1. Poll `get_post_rewrite_scores` until N=5 new outputs are scored
2. Compare post-rewrite avg vs baseline:
   - **Drop > 10%** → `restore_instruction(agent_name, prev_version)`, mark version `rolled_back`
   - **Equal or better** → mark version `stable`
3. `release_rewrite_lock`
4. Save result to memory tools

**Output:** stability verdict (stable/rolled_back), scores comparison, final status

---

## 8. Autoresearcher Orchestrator

**Routing logic:**

| Trigger | Delegate to |
|---|---|
| "evaluate agents" / "quality review" / "batch analysis" | `evaluator_agent` |
| "improve [agent_name]" / "rewrite instruction" | `hypothesis_agent` → `rewriter_agent` |
| "rollback [agent_name]" / "restore version" | `rollback_watchdog_agent` |
| "evolution status" / "what changed" / "version history" | `evaluator_agent` (summary mode) |
| Periodic cron trigger / low-score event | `evaluator_agent` (auto-mode, full loop) |

**Memory protocol:**
- Session start: `recall_past_outputs("autoresearcher_orchestrator")` — surface recent evolution history
- After each rewrite: `save_agent_output("rewriter_agent", hypothesis + version)`
- After rollback decision: `save_agent_output("rollback_watchdog_agent", result)`

**TTL:** None (router — must not cache)

---

## 9. Rollback Safety Rules

1. `rewriter_agent` always snapshots **before** patching — no write without a restore point
2. `rollback_watchdog_agent` waits for **5 real outputs** before deciding — avoids noise from single bad calls
3. Rollback threshold: post-rewrite avg < pre-rewrite avg by **>10%** → restore
4. Max **1 active rewrite per agent** at a time — rewrite lock in DB held until watchdog resolves
5. Rewrite loop guard: if an agent is rewritten **≥3 times in 24h** without stable improvement → log to supervisor DLQ, pause that agent's evolution
6. `hypothesis_agent` never writes to disk — isolation prevents accidental direct writes

---

## 10. `company_orchestrator` Updates

Add to `INSTRUCTION` routing table:

```
Route to autoresearcher_orchestrator when:
- "improve agents" / "evolve" / "quality review" / "what's underperforming"
- "rollback" / "restore" / "[agent_name] is performing badly"
- "evolution status" / "what changed" / "version history"
- Internal: reflection_agent score < 6 triggers evolution_event log
- Internal: supervisor periodic trigger fires (every 20 tasks)
```

Add to `sub_agents` list: `autoresearcher_orchestrator`

---

## 11. FAANG Alignment

| Component | Industry analogue |
|---|---|
| `evaluator_agent` | Google's Rater teams + automated quality metrics pipelines |
| `hypothesis_agent` | DeepMind's automated hypothesis generation in AlphaCode |
| `rewriter_agent` | Meta's Automated Prompt Engineering (APE) in production |
| `rollback_watchdog_agent` | Netflix's Chaos Engineering + automated canary rollback |
| Evolution loop overall | Karpathy's autoresearch: generate → experiment → evaluate → refine |

---

## 12. Testing Requirements

- **Unit tests** for all `evolution_tools.py` functions (mock SQLite, mock disk writes)
- **Unit tests** for `evolution_db.py` schema init and CRUD operations
- **Integration test:** full loop — seed bad outputs → evaluator flags → hypothesis generated → rewriter patches → watchdog detects improvement → marks stable
- **Rollback integration test:** seed bad outputs → rewrite → seed worse outputs → watchdog detects drop → auto-restores original instruction
- **Lock contention test:** two concurrent rewrite attempts → second is rejected
- **24h guard test:** 3 rewrites in 24h → 4th is blocked, DLQ entry created
- Coverage target: 80%+
