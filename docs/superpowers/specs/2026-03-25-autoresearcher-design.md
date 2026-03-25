# Autoresearcher — Self-Evolving Agent Loop Design Specification

> **Status:** Approved for implementation
> **Date:** 2026-03-25
> **Inspired by:** Karpathy's autoresearch (self-improving loop pattern)
> **Extends:** `docs/superpowers/specs/2026-03-25-engineering-research-teams-design.md`

**Goal:** Add a self-evolving `autoresearcher` department to `sales-adk-agents` that continuously monitors all agent outputs, identifies underperforming agents, rewrites their active instructions, and automatically rolls back if quality drops.

**Architecture:** New top-level department (`autoresearcher_orchestrator`) wired into `company_orchestrator` as a peer alongside Sales, Marketing, Product, Engineering, Research, and QA. Four specialist agents handle distinct phases of the evolution loop. A new SQLite-backed tool layer manages version snapshots, scores, rollback state, and dynamic instruction loading.

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

**Reflection agent coverage:** Each department orchestrator invokes `reflection_agent` on every sub-agent output. The reflection score (1-10) is logged to `evolution_events` immediately via `log_evolution_event()` whenever score < 6. This is the primary data feed for the evolution loop.

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

## 3. Dynamic Instruction Loading (Hot-Reload Pattern)

ADK agents load `instruction=INSTRUCTION` at construction time from a Python module constant. Patching the `.py` file does not reload the in-memory agent. To support live instruction updates without process restart, all agents in the system are updated to use **dynamic instruction loading**:

```python
# In every agent .py file (small wrapper added during implementation):
from tools.evolution_db import get_current_instruction

INSTRUCTION_STATIC = """..."""  # original hardcoded instruction (preserved as fallback)

def get_instruction(agent_name: str) -> str:
    """Load active instruction from evolution_db, fallback to static."""
    dynamic = get_current_instruction(agent_name)
    return dynamic if dynamic is not None else INSTRUCTION_STATIC
```

Each `Agent(...)` call passes `instruction=get_instruction("agent_name")` at instantiation. Since ADK re-instantiates agents per invocation (or orchestrator re-runs), this reads the DB on each call — effectively hot-reloading.

`get_current_instruction(agent_name)` queries `agent_versions` for the most recent `stable` or `pending_watch` row and returns its `instruction_text`. Returns `None` if no dynamic version exists (preserves static fallback).

**Agents to update:** all existing agents in `agents/` that participate in the evolution loop (initially all agents tracked in `evolution_db`). The static `INSTRUCTION` string is always preserved in the file as the `INSTRUCTION_STATIC` fallback and ground truth for version 0 snapshots.

---

## 4. Evolution Loop

```
┌─────────────────────────────────────────────────────────┐
│                   EVOLUTION LOOP                        │
│                                                         │
│  1. DETECT (evaluator_agent — monitor mode)             │
│     - Batch: scans evolution_events for unprocessed     │
│       low-score entries; reads supervisor event log     │
│     - Aggregates per agent: avg score of last 10 events │
│     - Enqueues agents with avg score < 6 into           │
│       evaluator_queue table (priority = avg score asc)  │
│     - Marks processed events as processed=1             │
│     - Saves flagged list summary to memory              │
│     → evaluator_queue table is the durable handoff      │
│                                                         │
│  2. HYPOTHESIZE (hypothesis_agent)                      │
│     - Reads highest-priority agent from evaluator_queue │
│     - Reads current active instruction (evolution_db    │
│       or INSTRUCTION_STATIC via get_current_instruction)│
│     - Reads 3-5 most recent bad output samples          │
│     - Generates root cause + proposed INSTRUCTION +     │
│       CONFIDENCE (high/medium/low)                      │
│     - Saves hypothesis to hypotheses table + memory     │
│     → CONFIDENCE == low → DLQ + remove from queue       │
│     → CONFIDENCE == medium/high → pass to rewriter      │
│       (high prioritized over medium in queue)           │
│                                                         │
│  3. REWRITE (rewriter_agent)                            │
│     - Guard checks (24h, 30-day, lock)                  │
│     - Snapshot baseline score at patch time             │
│       (locked via DB transaction to prevent race)       │
│     - Snapshot current INSTRUCTION to agent_versions    │
│     - Validate syntax with compile()                    │
│     - Patch .py file atomically (temp→rename)           │
│       AND update agent_versions with new instruction    │
│       (both tables updated — dual-write)                │
│     - Set status='pending_watch'                        │
│     - Remove agent from evaluator_queue                 │
│     → Watchdog reads pending_watch from agent_versions  │
│                                                         │
│  4. WATCH (rollback_watchdog_agent)                     │
│     - Reads pending_watch entries from agent_versions   │
│     - Passively waits for reflection_agent to log new   │
│       evolution_events for this agent (natural usage)   │
│     - Polls every hour; timeout = 48h wall-clock        │
│     - Timeout fallback (< 5 outputs after 48h):         │
│       mark stable, release lock (idle agent)            │
│     - If exactly N outputs received before timeout:     │
│       compare avg vs baseline                           │
│       - Drop > 10% → restore, mark rolled_back          │
│       - Equal or better → mark stable                   │
│     - Release rewrite lock                              │
│     - Save verdict to memory                            │
│     → Loop returns to step 1                            │
└─────────────────────────────────────────────────────────┘
```

**Loop execution model:** Evaluator runs once per trigger and processes the full unprocessed event queue in that invocation. When it completes, control returns to the orchestrator. On the next trigger (task-count or real-time event), evaluator is re-invoked and processes newly appended events. hypothesis → rewriter → watchdog execute sequentially per agent, one at a time per agent (enforced by rewrite_lock).

---

## 5. Triggers

### 5.1 Periodic (Task-Count Based)

Supervisor maintains a task counter. After every N completed tasks (configurable, default: 20), supervisor routes the message `"autoresearcher:batch_review"` through `company_orchestrator`, which routes to `autoresearcher_orchestrator`. Evaluator runs in monitor mode — full batch review across all monitored agents.

**Supervisor integration point:** Add to `supervisor.py`:
```python
if task_count % AUTORESEARCHER_BATCH_INTERVAL == 0:
    company_orchestrator.route("autoresearcher:batch_review")
```

### 5.2 Event-Driven (Real-Time)

When reflection_agent scores < 6, `log_evolution_event()` writes to `evolution_events`. The next evaluator invocation (periodic or manual) processes this event. Real-time events do not immediately trigger a new evaluator run — they are buffered in `evolution_events` and consumed on the next scheduled trigger. This prevents runaway evaluator invocations on cascading failures.

### 5.3 Manual

User says "improve [agent_name]" → orchestrator routes directly to `hypothesis_agent`. `hypothesis_agent` calls `recall_past_outputs(agent_name)` to fetch recent samples. Returns at least 3 samples or aborts: "No output history found for [agent_name]. The agent must have run at least 3 times before manual improvement is possible." If `recall_past_outputs` returns `None` or empty list, treat as no history.

### 5.4 Routing Entry for Periodic Trigger

Add to `company_orchestrator` INSTRUCTION:
```
Route to autoresearcher_orchestrator when:
- message starts with "autoresearcher:" (internal supervisor trigger)
- "improve agents" / "evolve" / "quality review" / "what's underperforming"
- "rollback" / "restore" / "[agent_name] is performing badly"
- "evolution status" / "what changed" / "version history"
```

---

## 6. Database Schema (`evolution_db.py`)

SQLite-backed, following the pattern of `supervisor_db.py`.

**Version numbering:** Versions start at 0 (original instruction at agent creation). Increment monotonically per agent, never reset. Rollbacks restore content but do not decrement the version counter.

**Consecutive stable definition:** "≥ 2 consecutive stable versions" means the most recent 2 complete entries in `agent_versions` for this agent (ordered by version DESC, taking only terminal-state rows: `stable` or `rolled_back`) are both marked `stable`. A `rolled_back` entry breaks the streak.

**Status state machine (strict — no other transitions allowed):**
```
pending_watch → stable       (watchdog: improvement or timeout)
pending_watch → rolled_back  (watchdog: quality drop)
stable        → superseded   (when newer version becomes stable)
superseded    → stable        (when rollback restores this version)
rolled_back   → [terminal]   (no further transitions)
```
Any code attempting an unlisted transition must raise `InvalidStateTransition` and log to DLQ.

```sql
-- Version history: one row per instruction version per agent
CREATE TABLE agent_versions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name       TEXT NOT NULL,
    version          INTEGER NOT NULL,
    instruction_text TEXT NOT NULL,
    score_baseline   REAL,       -- mean of last 10 events at baseline_sampled_at
    baseline_sampled_at TEXT,    -- ISO timestamp: when baseline was locked
    status           TEXT DEFAULT 'pending_watch',
                                 -- pending_watch | stable | rolled_back | superseded
    hypothesis_id    INTEGER,    -- FK to hypotheses.id
    created_at       TEXT NOT NULL
);

-- Score signals feeding the evolution loop
CREATE TABLE evolution_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name    TEXT NOT NULL,
    trigger_type  TEXT NOT NULL,  -- reflection_score | batch_review | manual
    score         REAL NOT NULL,
    output_sample TEXT,           -- truncated to 2000 chars, UTF-8 plain text
    processed     INTEGER DEFAULT 0,  -- 0 = unprocessed, 1 = consumed by evaluator
    created_at    TEXT NOT NULL
);

-- Hypothesis records linking cause to proposed fix
CREATE TABLE hypotheses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name       TEXT NOT NULL,
    version          INTEGER NOT NULL,  -- target version this hypothesis produced
    root_cause       TEXT NOT NULL,
    hypothesis_text  TEXT NOT NULL,     -- the proposed new INSTRUCTION string
    confidence       TEXT NOT NULL,     -- high | medium | low
    created_at       TEXT NOT NULL
);

-- Per-agent rewrite lock: prevents concurrent rewrites
-- SQLite UNIQUE on agent_name; acquire via INSERT OR IGNORE
CREATE TABLE rewrite_locks (
    agent_name  TEXT PRIMARY KEY,
    locked_at   TEXT NOT NULL,
    expires_at  TEXT NOT NULL,  -- locked_at + 72h; stale locks auto-released
    version     INTEGER NOT NULL
);

-- Durable priority queue for evaluator → hypothesis handoff
-- Priority: lower score = higher priority (process worst first)
CREATE TABLE evaluator_queue (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name    TEXT NOT NULL UNIQUE,  -- one entry per agent at a time
    priority      REAL NOT NULL,         -- avg score (lower = more urgent)
    evidence      TEXT NOT NULL,         -- JSON: list of {score, output_sample, created_at}
    confidence    TEXT,                  -- filled by hypothesis_agent before processing
    queued_at     TEXT NOT NULL,
    status        TEXT DEFAULT 'pending'  -- pending | processing | done | aborted
);
```

---

## 7. Tool Layer (`evolution_tools.py`)

All disk writes go through this module. Used only by `rewriter_agent` and `rollback_watchdog_agent`.

```python
# Dynamic instruction loading (used by all agents)
get_current_instruction(agent_name: str) → str | None
  # queries agent_versions for most recent stable/pending_watch row
  # returns instruction_text or None if no dynamic version exists

# Version management
snapshot_instruction(agent_name, version, instruction_text, score_baseline,
                     baseline_sampled_at, hypothesis_id) → None
restore_instruction(agent_name, version) → None
  # reads instruction_text from agent_versions, patches disk + updates DB status

# Disk patching (atomic: temp file → os.rename)
# Uses re.DOTALL for multi-line strings; validates syntax via compile() before write
patch_instruction(agent_file_path: str, new_instruction: str) → None

# Scoring — all queries scoped by created_at to avoid race conditions
# get_baseline_score uses a DB transaction: SELECT FOR consistent snapshot
get_baseline_score(agent_name: str, last_n: int = 10) → tuple[float, str]
  # returns (mean_score, sampled_at_timestamp) — timestamp locked at query time

get_post_rewrite_scores(agent_name: str, after_timestamp: str, n: int = 5) → list[float]
  # returns up to n scores from evolution_events where created_at > after_timestamp

# Events
log_evolution_event(agent_name, trigger_type, score, output_sample) → None
  # output_sample truncated to 2000 chars UTF-8 before insert
mark_event_processed(event_id: int) → None

# Queue operations (evaluator_queue table)
enqueue_agent(agent_name: str, priority: float, evidence: list[dict]) → None
  # UPSERT: if agent already in queue, update priority if new priority is worse
dequeue_next_agent() → dict | None  # returns highest priority pending entry
mark_queue_entry_done(agent_name: str) → None
mark_queue_entry_aborted(agent_name: str, reason: str) → None

# Locks (SQLite UNIQUE + INSERT OR IGNORE for atomic acquisition)
acquire_rewrite_lock(agent_name: str, version: int) → bool  # False if already locked
release_rewrite_lock(agent_name: str) → None
release_stale_locks() → int  # clears entries past expires_at; returns count released

# Agent file path resolution
# Convention: agents/{agent_name}.py (underscore-to-filename mapping)
# Raises FileNotFoundError if not found; callers must handle
get_agent_file_path(agent_name: str) → str

# Status queries
get_evolution_history(agent_name: str) → list[dict]
get_rewrite_count_last_24h(agent_name: str) → int
get_rewrite_count_last_30d(agent_name: str) → int
get_consecutive_stable_count(agent_name: str) → int
  # counts most recent consecutive stable versions (stops at first non-stable)
```

**Agent file path resolution:** Convention is `agents/{agent_name}.py`. All agents in the system follow `name="foo_agent"` → file `agents/foo_agent.py`. `get_agent_file_path` checks this path exists; raises `FileNotFoundError` if not. Callers log to DLQ and abort on this error.

**Output sample encoding:** Plain UTF-8 text, truncated to 2000 characters. Binary outputs (non-text) stored as `"[binary output: {type}]"` placeholder.

---

## 8. Specialist Agents

### 8.1 `evaluator_agent`

**Real-world title:** Quality Evaluator

**Monitored agents:** All agents in `agents/` directory whose `name` attribute is registered in `evolution_db`. Initial registration happens when first snapshot is taken or first evolution_event is logged. No whitelist needed — any agent that has produced scored outputs is automatically eligible.

**Tools:** `evolution_db` read functions, `supervisor_db` read functions, `recall_past_outputs`, `save_agent_output`, `mark_event_processed`, `enqueue_agent`

**Modes:**
- **Monitor mode** (auto-triggered): reads all unprocessed `evolution_events`, aggregates per-agent avg score, enqueues agents below threshold into `evaluator_queue`, marks events processed, saves summary to memory. Runs to completion and exits — does not loop internally.
- **Query mode** (user "evolution status"): reads `agent_versions` history + `evaluator_queue` status. Read-only — does not modify `processed` flag or `evaluator_queue`. Can run concurrently with monitor mode (different tables accessed).

**Reflection loop:** `evaluator_agent` has its own `make_reflection_agent()` instance. The reflection agent scores the quality of the **flagged list** using this rubric:
- Precision: for each flagged agent, are ≥ 3 low-score outputs provided as evidence? Score = min(4, count of flagged agents with ≥ 3 supporting samples) — max 4 points
- Recall: did evaluator flag ALL agents that have avg(last N evolution_events) < 6, where N ≥ 3 events exist? Yes=3, any false negatives=1
- Evidence quality: are the sample outputs genuinely poor (not isolated one-offs or test artifacts)? Clear poor outputs=3, borderline=2, mostly noise=1

Total: 1-10. Below 6 → re-run with broader window (N → 2N output samples for all agents with ≥ 1 event), max 2 cycles.

**Scoring rubric (per individual agent output in evolution_events):**
- Accuracy: did it answer the actual question? (1-3)
- Completeness: were all required elements present? (1-3)
- Actionability: is the output usable downstream? (1-4)

Total: 1-10. Below 6 = flagged.

### 8.2 `hypothesis_agent`

**Real-world title:** Improvement Researcher

**Tools:** `read_agent_instruction` (via `get_current_instruction` + INSTRUCTION_STATIC fallback), `recall_past_outputs`, `evolution_db` read, `dequeue_next_agent`, `save_agent_output`

**Inputs:** dequeues highest-priority entry from `evaluator_queue`; reads agent's current active instruction; reads 3-5 bad output samples from evidence field + `recall_past_outputs`

**Outputs:** structured hypothesis record saved to `hypotheses` table and memory:
```
ROOT CAUSE: [1-2 sentence diagnosis]
GAPS IN CURRENT INSTRUCTION: [bullet list]
PROPOSED INSTRUCTION: [full rewritten INSTRUCTION string]
CONFIDENCE: [high/medium/low]
```

**Confidence gating:**
- `low` → `mark_queue_entry_aborted(agent_name, reason)`, log to supervisor DLQ, stop
- `medium` → pass to rewriter (lower priority than high)
- `high` → pass to rewriter (higher priority; rewriter prefers high over medium in queue)

Confidence prioritization is embedded in `evaluator_queue`: when hypothesis_agent writes its confidence back to the queue entry, `mark_queue_entry_done` updates the row. When orchestrator invokes `rewriter_agent`, it calls `dequeue_next_agent()` which executes `SELECT ... WHERE status='done' ORDER BY confidence DESC, priority ASC LIMIT 1` — high confidence first, then worst avg score first within the same confidence tier. The orchestrator is responsible for calling `dequeue_next_agent()` before routing to rewriter; rewriter receives the dequeued record directly as input and does NOT call `dequeue_next_agent()` itself.

**Manual trigger:** When invoked via "improve [agent_name]", hypothesis_agent receives `agent_name` as a direct parameter and does **NOT** call `dequeue_next_agent()`. It uses `agent_name` directly to read instruction and samples. `recall_past_outputs(agent_name)` → if returns `None`, empty list, or raises an exception → abort with message: "No output history found for [agent_name]. The agent must have run at least 3 times before manual improvement is possible." (exception case adds: log to supervisor DLQ).

**Constraint:** `hypothesis_agent` NEVER writes to disk. DB + memory only.

### 8.3 `rewriter_agent`

**Real-world title:** Instruction Engineer

**Tools:** `evolution_tools` (all write functions)

**Inputs:** reads next `done`-ready entry from `evaluator_queue` (hypothesis_id, agent_name, proposed instruction, confidence)

**Process:**
1. Check `get_rewrite_count_last_24h` — if ≥ 3, DLQ + abort
2. Check `get_rewrite_count_last_30d` and `get_consecutive_stable_count` — if ≥ 5 rewrites in 30 days with < 2 consecutive stable versions, DLQ escalate + abort
3. `release_stale_locks()` — idempotent cleanup
4. `acquire_rewrite_lock(agent_name, version)` — if returns False, abort
5. Within a DB transaction: `get_baseline_score(agent_name, last_n=10)` → returns `(score, sampled_at)` — baseline is locked at this exact moment
6. `snapshot_instruction(agent_name, version, current_instruction, score_baseline, baseline_sampled_at, hypothesis_id)` — saves version N to DB
7. Validate proposed INSTRUCTION: `compile(proposed_text, '<string>', 'exec')` — if `SyntaxError`, release lock, DLQ, abort
8. `patch_instruction(agent_file_path, new_instruction)` — atomic write via temp→rename
9. Update `agent_versions` status to `pending_watch`; update `evaluator_queue` entry status to `done`

**Output:** `agent_versions` row with `status='pending_watch'` is the durable handoff to watchdog. Watchdog polls this table; no direct parameter passing between agents.

### 8.4 `rollback_watchdog_agent`

**Real-world title:** Stability Monitor

**Tools:** `evolution_tools` (scoring + restore + lock functions), `save_agent_output`

**Inputs:** polls `agent_versions` where `status = 'pending_watch'` — DB is the handoff, not direct parameters

**Polling interval:** every 1 hour, timeout = 48h wall-clock from `created_at` of pending_watch row.

**Timeout resolution:**
- If **0 post-rewrite outputs** exist after 48h (agent was not invoked at all since rewrite): **do not mark stable**. Instead, extend the watchdog window by 24h (to 72h total). If still 0 outputs at 72h, mark `stable` with warning log: "version X marked stable by extended timeout (0 outputs in 72h — agent appears idle)." Additionally, `log_evolution_event(agent_name, "batch_review", score=0, output_sample="[idle: no invocations post-rewrite]")` to flag the agent for the next evaluator run.
- If **1-4 outputs** collected before 48h: use available outputs for decision (avg of available; if drop > 10%, rollback; otherwise stable). Log count in verdict.
- If **5+ outputs** collected: normal comparison path.

**Score collection:** watchdog calls `get_post_rewrite_scores(agent_name, after_timestamp=baseline_sampled_at, n=5)`. These scores come from reflection_agent naturally scoring the agent as it is used in the normal workflow. Watchdog does NOT invoke the agent directly — it passively waits.

**Decision logic (once N outputs collected OR timeout reached):**
- Drop > 10%: `restore_instruction(agent_name, prev_version)` where `prev_version` = the most recent row in `agent_versions` for this agent where `version < current AND status IN ('stable', 'superseded')`. If no such row exists, restore `INSTRUCTION_STATIC` from the agent's `.py` file directly. Mark current version `rolled_back`. Mark the restored version back to `stable`. If restoring to INSTRUCTION_STATIC, insert a version 0 row if it doesn't already exist.
- Equal or better: mark version `stable`, mark all prior versions for this agent as `superseded`.
- Timeout (0 outputs in 72h): mark `stable` with warning, log idle event (see timeout resolution above).

**Concurrent version semantics:** `superseded` means "was the active version but has been replaced by a newer stable version." Rolled-back versions restore the immediately prior version to active status. Version chain is linear — no branching.

**Output:** saves verdict to memory via `save_agent_output`, releases rewrite lock.

---

## 9. Autoresearcher Orchestrator

**Routing logic:**

| Trigger | Mode | Delegate to |
|---|---|---|
| "autoresearcher:batch_review" (supervisor) / "evaluate agents" / "quality review" | monitor | `evaluator_agent` |
| "evolution status" / "version history" / "what changed" | query | `evaluator_agent` |
| "improve [agent_name]" / "rewrite instruction" | manual | `hypothesis_agent` → (auto) `rewriter_agent` |
| "rollback [agent_name]" / "restore version" | manual | `rollback_watchdog_agent` |

**Manual flow (hypothesis → rewriter):** When orchestrator routes to `hypothesis_agent` for a manual trigger, it automatically invokes `rewriter_agent` after `hypothesis_agent` completes (if confidence ≠ low). No user confirmation needed between hypothesis and rewrite steps. Orchestrator then invokes `rollback_watchdog_agent` automatically to monitor the result.

**Memory protocol:**
- Session start: `recall_past_outputs("autoresearcher_orchestrator")`
- After evaluator flags: `save_agent_output("evaluator_agent", flagged_list)` (evaluator saves itself)
- After hypothesis: `save_agent_output("hypothesis_agent", hypothesis_record)` (hypothesis_agent saves itself)
- After rewrite: `save_agent_output("rewriter_agent", version_record)`
- After watchdog decision: `save_agent_output("rollback_watchdog_agent", verdict)`

**TTL:** None (router — must not cache)

**Specialist agent TTLs:** None (evolution state is time-sensitive). Memory outputs stamped with `created_at`; consumers filter by recency.

**Reflection loops:**
- `autoresearcher_orchestrator`: one `make_reflection_agent()` instance for orchestrator-level quality
- `evaluator_agent`: its own `make_reflection_agent()` for meta-evaluation of flagged lists
- `hypothesis_agent`: its own `make_reflection_agent()` to score hypothesis quality before passing downstream. If hypothesis reflection score < 7, re-generate (max 2 cycles)
- `rewriter_agent`, `rollback_watchdog_agent`: inherit orchestrator reflection (one-shot, max 1 cycle)

**Hypothesis reflection threshold:** `hypothesis_agent` uses threshold 7 (vs. standard 6) because hypotheses are higher-stakes than regular agent outputs — a low-quality hypothesis causes a disk write. The stricter threshold ensures only well-reasoned rewrites proceed.

---

## 10. Rollback Safety Rules

1. `rewriter_agent` always snapshots **before** patching — no write without a restore point
2. Baseline score is sampled **inside a DB transaction at patch time** — prevents race between sampling and patching
3. `patch_instruction` is **atomic** — temp file → `os.rename()`. Uses `re.DOTALL`. Validates syntax via `compile()` before writing. Does not write on syntax error.
4. **Dual-write:** both the `.py` file and `agent_versions` DB are updated. `get_current_instruction()` reads from DB (hot-reload path). File on disk is the durable backup.
5. `rollback_watchdog_agent` waits for **5 real outputs** OR **48h timeout** — passively monitors reflection scores from normal agent usage
6. Rollback threshold: post-rewrite avg < baseline by **> 10%** → restore
7. Max **1 active rewrite per agent** at a time — `rewrite_locks` SQLite UNIQUE + `INSERT OR IGNORE`
8. **Lock TTL:** `expires_at = locked_at + 72h`; `release_stale_locks()` called before each acquire
9. **24h guard:** ≥ 3 rewrites in 24h → DLQ + pause
10. **30-day guard:** ≥ 5 rewrites in 30 days with < 2 consecutive stable versions → DLQ escalate for human review
11. **Consecutive stable definition:** 2 most recent entries in `agent_versions` (ordered by version DESC) both marked `stable`
12. **Confidence gate:** `low` hypotheses → DLQ, never reach rewriter
13. `hypothesis_agent` never writes to disk
14. `FileNotFoundError` on agent file → log to DLQ, release lock, abort (do not crash)
15. `release_stale_locks()` is called idempotently by rewriter, evaluator, and watchdog at entry. Supervisor calls it every 100 tasks as a background safety net.

---

## 11. `company_orchestrator` Updates

Add to `INSTRUCTION` routing:
```
Route to autoresearcher_orchestrator when:
- message starts with "autoresearcher:" (internal supervisor trigger)
- "improve agents" / "evolve" / "quality review" / "what's underperforming"
- "rollback" / "restore" / "[agent_name] is performing badly"
- "evolution status" / "what changed" / "version history"
```

**Supervisor integration:** Add to `supervisor.py` task counter logic:
```python
AUTORESEARCHER_BATCH_INTERVAL = int(os.getenv("AUTORESEARCHER_BATCH_INTERVAL", "20"))
if self.task_count % AUTORESEARCHER_BATCH_INTERVAL == 0:
    self._route_to_company_orchestrator("autoresearcher:batch_review")
    # Blocking: supervisor awaits evaluator completion before returning.
    # Evaluator runs to completion in a single invocation (no internal loop).
    # Only one "autoresearcher:batch_review" can be in-flight at a time;
    # if already running, supervisor increments counter but does not re-trigger.
```

**Reflection agent responsibility:** Each department orchestrator logs to `evolution_events` after reflection scoring. Autoresearcher passively reads this table — no changes needed to existing orchestrators beyond adding the `log_evolution_event()` call when reflection score < 6.

Add to `sub_agents` list: `autoresearcher_orchestrator`

---

## 12. FAANG Alignment

| Component | Industry analogue |
|---|---|
| `evaluator_agent` | Google's Rater teams + automated quality metrics pipelines |
| `hypothesis_agent` | DeepMind's automated hypothesis generation in AlphaCode |
| `rewriter_agent` | Meta's Automated Prompt Engineering (APE) in production |
| `rollback_watchdog_agent` | Netflix's Chaos Engineering + automated canary rollback |
| `get_current_instruction()` hot-reload | Airbnb's dynamic feature flag config without deploys |
| Evolution loop overall | Karpathy's autoresearch: generate → experiment → evaluate → refine |

---

## 13. Testing Requirements

### Unit Tests (`test_evolution_db.py`)
- Schema initialization creates all 5 tables (including `evaluator_queue`)
- CRUD for `agent_versions`, `evolution_events`, `hypotheses`, `rewrite_locks`, `evaluator_queue`
- `INSERT OR IGNORE` on `rewrite_locks` rejects duplicate `agent_name`
- `INSERT OR IGNORE` on `evaluator_queue` UNIQUE `agent_name` handles duplicate enqueue

### Unit Tests (`test_evolution_tools.py` — mock SQLite)
- `get_baseline_score` returns correct mean of last N events; returns `(0.0, now)` if 0 events; uses available events if < N exist
- `acquire_rewrite_lock` returns False when lock exists and not expired
- `acquire_rewrite_lock` returns True after `release_stale_locks` clears expired lock
- `get_rewrite_count_last_24h` and `_last_30d` count correctly within window
- `get_consecutive_stable_count` returns 0 on no history, 1 on one stable, 0 on rolled_back followed by stable
- `get_current_instruction` returns None when no dynamic version exists; returns latest stable text when available
- `enqueue_agent` UPSERT updates priority when new score is worse

### Integration Tests (`test_evolution_tools.py` — real temp files)
- `patch_instruction` patches INSTRUCTION_STATIC string in valid `.py` fixture; result is valid Python
- `patch_instruction` with syntax-error instruction: raises before writing, original file unchanged
- `restore_instruction` reads DB snapshot and correctly restores original content to disk
- `get_current_instruction` returns correct text after `snapshot_instruction` + `patch_instruction` cycle

### Integration Tests (`test_autoresearcher.py`)
- **Happy path:** seed bad outputs → evaluator flags → enqueued → hypothesis generated (high confidence) → rewriter patches → `get_current_instruction` returns new text → watchdog collects 5 improved scores → marks stable
- **Rollback path:** seed bad outputs → rewrite → seed worse post-rewrite evolution_events → watchdog detects >10% drop → restores instruction (disk + DB), marks rolled_back, prior version back to stable
- **Lock contention:** two concurrent `acquire_rewrite_lock` for same agent → second returns False
- **24h guard:** simulate 3 rewrites within 24h window → 4th attempt blocked, DLQ entry created
- **30-day guard:** simulate 5 rewrites in 30d with 0 consecutive stable → blocked, DLQ escalation logged
- **Low-confidence abort:** hypothesis returns CONFIDENCE=low → `mark_queue_entry_aborted` called, rewriter never invoked
- **48h idle timeout:** rewrite applied, 0 new evolution_events after 48h → watchdog marks stable, lock released
- **Partial outputs (1-4 before timeout):** watchdog uses available outputs for decision; if > 10% drop, rollback; if not, mark stable
- **Evaluator query vs monitor mode:** "evolution status" query does not set processed=1 on events, does not modify evaluator_queue
- **Agent file not found:** `get_agent_file_path` raises FileNotFoundError → rewriter logs DLQ entry, lock released
- **Stale lock auto-release:** lock with past `expires_at` is cleared on next `acquire_rewrite_lock` call → new acquire succeeds
- **Duplicate enqueue:** evaluator enqueues agent_A twice → second call updates priority, one row in queue
- **Evaluator reflection re-run:** seed evidence with only 1 bad sample per agent → meta-score < 6 → evaluator widens to 2N samples, re-flags with stronger evidence
- **Dynamic hot-reload:** patch_instruction updates .py file; `get_current_instruction` immediately returns new instruction; static fallback used if no DB entry

- **Concurrent evaluator:** Two evaluator monitor-mode runs triggered in parallel → both consume disjoint subsets of unprocessed events (processed=1 is set atomically); no duplicate enqueues in evaluator_queue (UNIQUE constraint prevents); no lost updates
- **Invalid status transition:** Attempt to move `rolled_back` → `stable` → raises `InvalidStateTransition`, logged to DLQ
- **Restore to INSTRUCTION_STATIC:** All prior versions are rolled_back, no stable version in DB → watchdog restores from INSTRUCTION_STATIC directly, inserts version 0 row

### Coverage target: 80%+
