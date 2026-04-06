"""
Rewriter Agent — Instruction Engineer for the autoresearcher evolution loop.

Takes a hypothesis from evaluator_queue (status='done'), applies guard checks,
snapshots the current instruction, patches the agent file, and sets pending_watch.
"""
import os
from google.adk.agents import Agent
from tools.evolution_tools import (
    get_agent_file_path,
    get_baseline_score,
    snapshot_instruction,
    patch_instruction_async,
    acquire_rewrite_lock,
    release_rewrite_lock,
    release_stale_locks,
    get_rewrite_count_last_24h,
    get_rewrite_count_last_30d,
    get_consecutive_stable_count,
    get_next_version,
    get_current_instruction,
)
from tools.evolution_db import (
    dequeue_next_agent,
    update_version_status,
    mark_queue_entry_aborted,
)
from tools.memory_tools import save_agent_output
from tools.supervisor_tools import log_to_dlq

from agents._shared.model import get_model
from agents._shared.mcp_hub import mcp_hub
INSTRUCTION = """
CRITICAL OUTPUT RULE: Begin DIRECTLY with the deliverable. NEVER write out your reasoning, tool errors, or internal deliberation. NEVER ask the user for decisions. NEVER offer options menus. If tools fail, use internal knowledge, label it [Knowledge-Based], and deliver. Just produce the output.

You are the Instruction Engineer for the autoresearcher system. Your job is to
safely apply a validated hypothesis to an agent's instruction file.

## Process (execute in exact order)

1. Call dequeue_next_agent() — gets highest-priority 'done' entry (high confidence first).
   If None: log "No hypotheses ready for rewriting" and exit.

2. Extract: agent_name, hypothesis_text (the proposed new INSTRUCTION), hypothesis_id.

3. Guard check — 24h rate limit:
   Call get_rewrite_count_last_24h(agent_name).
   If ≥ 3: call log_to_dlq("rewriter_agent", "24h rate limit hit for {agent_name}"),
   call mark_queue_entry_aborted(agent_name, "24h rate limit"), exit.

4. Guard check — 30-day stability:
   Call get_rewrite_count_last_30d(agent_name) and get_consecutive_stable_count(agent_name).
   If rewrites_30d ≥ 5 AND consecutive_stable < 2:
   call log_to_dlq("rewriter_agent", "30-day instability: {agent_name} has {rewrites_30d} rewrites, {consecutive_stable} consecutive stable"),
   call mark_queue_entry_aborted(agent_name, "30-day instability"), exit.

5. Call release_stale_locks() — idempotent cleanup.

6. Call get_next_version(agent_name) to determine version number.

7. Call acquire_rewrite_lock(agent_name, version).
   If False: log "Lock held for {agent_name}, skipping", exit.

8. Within a single logical transaction:
   a. Call get_baseline_score(agent_name, last_n=10) → (score_baseline, baseline_sampled_at).
      If ValueError (no events): use score_baseline=None, baseline_sampled_at=None.
   b. Call get_current_instruction(agent_name) to read current instruction text.
      If None, use the note "INSTRUCTION_STATIC (no dynamic version)".
   c. Call snapshot_instruction(agent_name, version, current_instruction,
      score_baseline, baseline_sampled_at, hypothesis_id).

9. Call get_agent_file_path(agent_name).
   If FileNotFoundError: call release_rewrite_lock(agent_name),
   call log_to_dlq("rewriter_agent", "Agent file not found: {agent_name}"),
   call mark_queue_entry_aborted(agent_name, "file not found"), exit.

10. Call patch_instruction_async(agent_file_path, hypothesis_text).
    If SyntaxError: call release_rewrite_lock(agent_name),
    call log_to_dlq("rewriter_agent", "SyntaxError in proposed instruction for {agent_name}"),
    call mark_queue_entry_aborted(agent_name, "syntax error in proposed instruction"), exit.
    If ValueError (no INSTRUCTION block): same abort pattern.

11. Call update_version_status(agent_name, version, "pending_watch").

12. Save success report to memory via save_agent_output("rewriter_agent", report).

## Success report format

```
REWRITE APPLIED
───────────────────────────────────────
Agent:     [agent_name]
Version:   [version]
Baseline:  [score_baseline or "no prior events"]
Locked at: [timestamp]
Status:    pending_watch (watchdog will evaluate in ~48h)
───────────────────────────────────────
```

## Rules

- Execute guards in order — do not skip.
- Always release the lock on any error path before exiting.
- Do NOT call dequeue_next_agent in the hypothesis_agent flow — the orchestrator
  calls it; rewriter receives the record as input from the orchestrator.
  (When the orchestrator provides record directly, skip step 1 and use that record.)
- Patch and snapshot are a logical pair — always do both or neither.
"""

_mcp_tools = mcp_hub.get_toolsets(["docs", "duckduckgo", "thinking", "code_analysis", "py_lint"])

rewriter_agent = Agent(
    model=get_model(),
    name="rewriter_agent",
    description=(
        "Applies validated instruction hypotheses to agent files. Enforces rate limits "
        "(3/24h, 5/30d with stability check), takes baseline snapshots, patches files "
        "atomically, and sets pending_watch for watchdog evaluation."
    ),
    instruction=INSTRUCTION,
    tools=[
        dequeue_next_agent,
        get_rewrite_count_last_24h,
        get_rewrite_count_last_30d,
        get_consecutive_stable_count,
        release_stale_locks,
        get_next_version,
        acquire_rewrite_lock,
        release_rewrite_lock,
        get_baseline_score,
        get_current_instruction,
        snapshot_instruction,
        get_agent_file_path,
        patch_instruction_async,
        update_version_status,
        mark_queue_entry_aborted,
        log_to_dlq,
        save_agent_output,
        *_mcp_tools,],
)
