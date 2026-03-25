"""
Evolution Tools — disk patching, scoring helpers, and path resolution
for the autoresearcher self-evolving loop.

All disk writes are atomic (temp file → os.rename).
All DB operations delegate to evolution_db.
"""
import os
import re
import tempfile
import asyncio
from pathlib import Path
from typing import Optional

from tools import evolution_db

# Root of the agents directory relative to this file
_AGENTS_DIR = Path(__file__).parent.parent / "agents"


# ── Agent file path resolution ────────────────────────────────────────────────

def get_agent_file_path(agent_name: str) -> str:
    """Return absolute path to agents/{agent_name}.py. Raises FileNotFoundError."""
    path = _AGENTS_DIR / f"{agent_name}.py"
    if not path.exists():
        raise FileNotFoundError(
            f"Agent file not found: {path}. "
            f"Ensure the agent follows the naming convention agents/{{agent_name}}.py"
        )
    return str(path)


# ── Dynamic instruction loading ───────────────────────────────────────────────

def get_current_instruction_sync(agent_name: str) -> Optional[str]:
    """Load active instruction from evolution_db; None if no dynamic version."""
    return evolution_db.get_current_instruction_sync(agent_name)


async def get_current_instruction(agent_name: str) -> Optional[str]:
    return await evolution_db.get_current_instruction(agent_name)


# ── Disk patching ─────────────────────────────────────────────────────────────

_INSTRUCTION_PATTERN = re.compile(
    r'(INSTRUCTION\s*=\s*""")(.*?)(""")',
    re.DOTALL,
)


def patch_instruction(agent_file_path: str, new_instruction: str) -> None:
    """
    Atomically replace the INSTRUCTION string in an agent .py file.

    1. Reads current file.
    2. Validates new_instruction syntax via compile().
    3. Replaces INSTRUCTION = \"\"\"...\"\"\" block.
    4. Writes to a temp file, then os.rename (atomic on POSIX).

    Raises:
        FileNotFoundError: if agent_file_path does not exist.
        SyntaxError: if new_instruction fails compile().
        ValueError: if INSTRUCTION block not found in file.
    """
    path = Path(agent_file_path)
    if not path.exists():
        raise FileNotFoundError(f"Agent file not found: {path}")

    # Validate syntax — compile the instruction text as a Python expression
    compile(new_instruction, "<instruction>", "exec")

    content = path.read_text(encoding="utf-8")

    if not _INSTRUCTION_PATTERN.search(content):
        raise ValueError(
            f"No INSTRUCTION = \"\"\"...\"\"\" block found in {path}. "
            "Cannot patch this file."
        )

    new_content = _INSTRUCTION_PATTERN.sub(
        lambda m: f'{m.group(1)}{new_instruction}{m.group(3)}',
        content,
        count=1,
    )

    # Atomic write: temp file in same directory → rename
    dir_ = path.parent
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=dir_,
        suffix=".tmp",
        delete=False,
    ) as tf:
        tf.write(new_content)
        tmp_path = tf.name

    os.rename(tmp_path, str(path))


async def patch_instruction_async(agent_file_path: str, new_instruction: str) -> None:
    await asyncio.to_thread(patch_instruction, agent_file_path, new_instruction)


# ── Version management ────────────────────────────────────────────────────────

async def snapshot_instruction(
    agent_name: str,
    version: int,
    instruction_text: str,
    score_baseline: Optional[float],
    baseline_sampled_at: Optional[str],
    hypothesis_id: Optional[int],
) -> None:
    await evolution_db.snapshot_instruction(
        agent_name, version, instruction_text,
        score_baseline, baseline_sampled_at, hypothesis_id,
    )


async def restore_instruction(agent_name: str, version: int) -> None:
    """
    Restore a specific version's instruction to disk and update DB status.

    1. Reads instruction_text from agent_versions at given version.
    2. Patches disk atomically.
    3. Marks the target version as 'stable' (superseded → stable rollback).
    4. Marks any newer versions as 'superseded'.
    """
    history = await evolution_db.get_evolution_history(agent_name)
    target = next((r for r in history if r["version"] == version), None)
    if not target:
        raise ValueError(f"Version {version} not found for agent {agent_name!r}")

    agent_file_path = get_agent_file_path(agent_name)
    await asyncio.to_thread(patch_instruction, agent_file_path, target["instruction_text"])

    # Mark target as stable (it was rolled_back or superseded → stable)
    await evolution_db.update_version_status(agent_name, version, "stable")

    # Mark all versions newer than target as superseded
    for row in history:
        if row["version"] > version and row["status"] not in ("rolled_back", "superseded"):
            try:
                await evolution_db.update_version_status(agent_name, row["version"], "superseded")
            except evolution_db.InvalidStateTransition:
                pass  # already in terminal state


# ── Scoring ───────────────────────────────────────────────────────────────────

async def get_baseline_score(
    agent_name: str, last_n: int = 10
) -> tuple[float, str]:
    """Return (mean_score, sampled_at_timestamp). Raises ValueError if no events."""
    return await evolution_db.get_baseline_score(agent_name, last_n)


async def get_post_rewrite_scores(
    agent_name: str, after_timestamp: str, n: int = 5
) -> list[float]:
    return await evolution_db.get_post_rewrite_scores(agent_name, after_timestamp, n)


# ── Events ────────────────────────────────────────────────────────────────────

async def log_evolution_event(
    agent_name: str,
    trigger_type: str,
    score: float,
    output_sample: Optional[str] = None,
) -> None:
    await evolution_db.log_evolution_event(agent_name, trigger_type, score, output_sample)


async def mark_event_processed(event_id: int) -> bool:
    return await evolution_db.mark_event_processed(event_id)


async def get_unprocessed_events(limit: int = 500) -> list[dict]:
    return await evolution_db.get_unprocessed_events(limit)


# ── Queue operations ──────────────────────────────────────────────────────────

async def enqueue_agent(
    agent_name: str, priority: float, evidence: list[dict]
) -> None:
    await evolution_db.enqueue_agent(agent_name, priority, evidence)


async def dequeue_next_agent() -> Optional[dict]:
    return await evolution_db.dequeue_next_agent()


async def mark_queue_entry_done(agent_name: str, confidence: str) -> None:
    await evolution_db.mark_queue_entry_done(agent_name, confidence)


async def mark_queue_entry_aborted(agent_name: str, reason: str) -> None:
    await evolution_db.mark_queue_entry_aborted(agent_name, reason)


# ── Locks ─────────────────────────────────────────────────────────────────────

async def acquire_rewrite_lock(agent_name: str, version: int) -> bool:
    return await evolution_db.acquire_rewrite_lock(agent_name, version)


async def release_rewrite_lock(agent_name: str) -> None:
    await evolution_db.release_rewrite_lock(agent_name)


async def release_stale_locks() -> int:
    return await evolution_db.release_stale_locks()


# ── Status queries ────────────────────────────────────────────────────────────

async def get_evolution_history(agent_name: str) -> list[dict]:
    return await evolution_db.get_evolution_history(agent_name)


async def get_rewrite_count_last_24h(agent_name: str) -> int:
    return await evolution_db.get_rewrite_count_last_24h(agent_name)


async def get_rewrite_count_last_30d(agent_name: str) -> int:
    return await evolution_db.get_rewrite_count_last_30d(agent_name)


async def get_consecutive_stable_count(agent_name: str) -> int:
    return await evolution_db.get_consecutive_stable_count(agent_name)


async def get_next_version(agent_name: str) -> int:
    return await evolution_db.get_next_version(agent_name)
