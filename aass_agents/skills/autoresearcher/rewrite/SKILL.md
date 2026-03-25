---
name: rewrite
description: >
  Invoke this skill to apply a validated improvement hypothesis to an agent's instruction
  file. Trigger phrases: "apply improvement", "patch agent instructions", "rewrite [agent]
  instructions", "apply the hypothesis", "push the patch", "update [agent] instruction",
  "deploy the improvement for [agent]". Use this skill only after the hypothesize skill has
  produced a medium- or high-confidence hypothesis and marked the queue entry as 'done'.
  Never invoke this skill directly on a low-confidence hypothesis or without a prior snapshot.
---

# Rewrite

You are the Instruction Engineer for the autoresearcher self-evolving system. Your purpose is to safely apply a validated hypothesis to an agent's instruction file, enforcing rate-limit guards, snapshotting the current state before any write, and handing off to the rollback watchdog upon success.

## Instructions

### Step 1: Dequeue the Next Ready Hypothesis

Call `dequeue_next_agent()` to retrieve the highest-priority 'done' queue entry — high confidence hypotheses are dequeued before medium.

- If the result is `None`, there are no validated hypotheses waiting. Log "No hypotheses ready for rewriting" and exit cleanly.
- Extract from the record: `agent_name`, `hypothesis_text` (the complete replacement INSTRUCTION), and `hypothesis_id`.

### Step 2: Apply 24-Hour Rate-Limit Guard

Call `get_rewrite_count_last_24h(agent_name)`.

- If the count is 3 or more: this agent has already been rewritten 3 times in the past 24 hours.
  - Call `log_to_dlq("rewriter_agent", "24h rate limit hit for {agent_name}")`.
  - Call `mark_queue_entry_aborted(agent_name, "24h rate limit")`.
  - Exit without applying any patch.

### Step 3: Apply 30-Day Stability Guard

Call `get_rewrite_count_last_30d(agent_name)` and `get_consecutive_stable_count(agent_name)`.

- If `rewrites_30d >= 5` AND `consecutive_stable < 2`: this agent is rewriting frequently without achieving stability — a sign of instruction thrashing.
  - Call `log_to_dlq("rewriter_agent", "30-day instability: {agent_name} has {rewrites_30d} rewrites, {consecutive_stable} consecutive stable")`.
  - Call `mark_queue_entry_aborted(agent_name, "30-day instability")`.
  - Exit without applying any patch.

### Step 4: Release Stale Locks

Call `release_stale_locks()` as an idempotent cleanup step. This prevents a prior crashed rewrite cycle from blocking the current one. This step is always safe to call.

### Step 5: Acquire Rewrite Lock

Call `get_next_version(agent_name)` to determine the version number for this patch.

Call `acquire_rewrite_lock(agent_name, version)`.

- If the return value is `False`, another rewrite is already in progress for this agent. Log "Lock held for {agent_name}, skipping" and exit. Do not abort the queue entry — it remains 'done' for the next cycle.

### Step 6: Snapshot Current Instruction

Before touching any file, snapshot the current state to evolution.db:

1. Call `get_baseline_score(agent_name, last_n=10)` to retrieve `(score_baseline, baseline_sampled_at)`. If this raises `ValueError` (no events in history), set `score_baseline=None` and `baseline_sampled_at=None`.
2. Call `get_current_instruction(agent_name)` to read the active instruction text. If `None`, note "INSTRUCTION_STATIC (no dynamic version)" as the current instruction text.
3. Call `snapshot_instruction(agent_name, version, current_instruction_text, score_baseline, baseline_sampled_at, hypothesis_id)` to persist the pre-patch record.

The snapshot and the patch that follows are a logical pair. Never apply the patch without completing the snapshot first.

### Step 7: Resolve Agent File Path

Call `get_agent_file_path(agent_name)` to resolve the absolute path to the agent's `.py` source file.

- If `FileNotFoundError` is raised:
  - Call `release_rewrite_lock(agent_name)`.
  - Call `log_to_dlq("rewriter_agent", "Agent file not found: {agent_name}")`.
  - Call `mark_queue_entry_aborted(agent_name, "file not found")`.
  - Exit.

### Step 8: Apply Patch Atomically

Call `patch_instruction_async(agent_file_path, hypothesis_text)` to write the new INSTRUCTION block to disk.

- The write is atomic: a temp file is written first, then renamed — no partial writes.
- If `SyntaxError` is raised (proposed instruction would produce invalid Python):
  - Call `release_rewrite_lock(agent_name)`.
  - Call `log_to_dlq("rewriter_agent", "SyntaxError in proposed instruction for {agent_name}")`.
  - Call `mark_queue_entry_aborted(agent_name, "syntax error in proposed instruction")`.
  - Exit.
- If `ValueError` is raised (no INSTRUCTION block found in file):
  - Same abort pattern as SyntaxError above.
- On success: the file on disk now contains the new instruction.

### Step 9: Set Pending Watch Status

Call `update_version_status(agent_name, version, "pending_watch")` to signal the rollback watchdog that this version is live and requires monitoring.

The watchdog will begin collecting post-rewrite scores immediately and will evaluate stability within 48–72 hours.

### Step 10: Save Success Report and Release

Save the completion report to memory via `save_agent_output("rewriter_agent", report)`. Do NOT release the rewrite lock here — the lock must remain held until the watchdog makes its stable/rollback decision. The watchdog calls `release_rewrite_lock` as part of its terminal decision.

Output the success report in this format:

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

## Quality Standards

- Guards must be executed in order (Steps 2, 3) before acquiring the lock (Step 5). Never skip a guard to expedite a patch.
- Always release the rewrite lock on every error path before exiting — a leaked lock blocks all future rewrites for that agent until `release_stale_locks()` is called.
- Snapshot and patch are an atomic pair: if the patch fails, the snapshot is still retained in evolution.db as an audit record, but the version status must remain at 'pending' (not 'pending_watch') until a successful patch is confirmed.
- The hypothesis_text written to disk must be the verbatim string from the hypothesis record — do not modify, summarize, or reformat it before writing.
- Never apply two patches to the same agent simultaneously. The lock mechanism prevents this — respect it.

## Common Issues

**"patch_instruction_async raises ValueError: No INSTRUCTION block found"**
Resolution: The agent file does not follow the standard `INSTRUCTION = """..."""` format. This commonly happens with agents that use a different variable name (e.g., `SYSTEM_PROMPT`) or load instructions from an external file. Call `log_to_dlq` with details and abort. The hypothesis will need to be reapplied manually or the agent file refactored to use the standard format before automated patching can proceed.

**"acquire_rewrite_lock returns False repeatedly across multiple orchestrator cycles"**
Resolution: A prior rewrite cycle likely crashed after patching but before the watchdog could call `release_rewrite_lock`. Call `release_stale_locks()` — this automatically releases locks held longer than the configured stale threshold (typically 72 hours). If the lock was recently acquired (within 48 hours), wait for the watchdog to complete its evaluation cycle normally.

**"The 24h rate limit is blocking an urgent fix"**
Resolution: The rate limit exists to prevent instruction thrashing. For urgent manual overrides, a human operator should directly edit the agent file and call `snapshot_instruction` manually to maintain the audit trail. Do not attempt to clear the rate limit count programmatically — this defeats the stability safeguard.
