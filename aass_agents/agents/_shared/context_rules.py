"""
Shared context engineering constants — Manus pattern adaptations.

Two improvements applied to all orchestrator agents:

1. STABLE_PREFIX (KV-cache optimization)
   Every agent INSTRUCTION must begin with this identical string.
   Because the KV-cache keys on the prompt prefix, a stable opening means
   the expensive first-token computation is cached and reused across calls.
   Changing even one character in the prefix invalidates the entire cache.
   Rule: append agent-specific content AFTER this block, never before it.

2. ERROR_PRESERVATION_RULE (error trace preservation)
   Failed tool calls must stay visible in context. The model learns to avoid
   repeating a failed approach only if the failure is still in its window.
   Cleaning up errors to "keep context tidy" is the single most common cause
   of agents looping on the same mistake.
"""

# ── 1. Stable KV-cache prefix ─────────────────────────────────────────────────
#
# All orchestrators MUST begin their INSTRUCTION with this exact string.
# Do not modify the wording — even minor edits break the shared cache prefix.

STABLE_PREFIX = """\
CRITICAL OUTPUT RULE: Begin DIRECTLY with the deliverable. NEVER write out \
your reasoning, tool errors, or internal deliberation. NEVER ask the user for \
decisions. NEVER offer options menus. If tools fail, use internal knowledge, \
label it [Knowledge-Based], and deliver. Just produce the output.\
"""


# ── 2. Error preservation rule ────────────────────────────────────────────────
#
# Insert this block into orchestrator INSTRUCTIONs after the routing/workflow
# section and before the self-review gate.

ERROR_PRESERVATION_RULE = """\
## Error Handling — Preserve, Don't Discard

When a tool call returns an error:
1. READ the error message fully — it contains information about what went wrong.
2. DO NOT retry the identical call immediately — adjust your approach first.
3. DO NOT summarise or compress the error — leave it verbatim in context.
   The error trace is your memory of what failed; removing it causes you to
   repeat the same mistake on the next attempt.
4. If a tool fails twice with the same error, use internal knowledge and
   label the output [Knowledge-Based — tool unavailable].
5. Move forward — a single tool failure must never stall the full run.\
"""


# ── 3. Todo recency anchoring protocol ───────────────────────────────────────
#
# Insert this block into orchestrator INSTRUCTIONs to establish the todo
# discipline. Agents call write_todo() once at start, read_todo() before each
# step, and complete_todo_step() after each step completes.

TODO_PROTOCOL = """\
## Todo Anchoring — Maintain Your Plan in the Recency Window

On long runs your initial goals drift out of your attention window. Counter this:

1. **Run start**: Call `write_todo(session_id, steps)` with your ordered step plan.
2. **Before each step**: Call `read_todo(session_id)` to re-anchor your goals.
3. **After each step**: Call `complete_todo_step(session_id, step_index)` to mark progress.
4. **If you lose track**: Call `read_todo(session_id)` — never guess your current position.

The session_id is the primary key for the current run (e.g. deal_id, product_id, or
a descriptive string like "sales-acme-2026-03-31").\
"""
