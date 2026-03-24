"""
Supervisor — wires EventLog, PipelineRun, LoopGuard, CircuitBreaker,
StalenessRegistry, and DeadLetterQueue into ADK callbacks.
"""
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

import tools.supervisor_db as _db


# ── PipelineRun ───────────────────────────────────────────────────────────────

class PipelineRun:
    def __init__(self, db=_db):
        self._db = db

    def start(self, pipeline_type: str, context: dict) -> str:
        run_id = str(uuid.uuid4())
        self._db.create_run(run_id, pipeline_type, context)
        self._db.update_run(run_id, status="running")
        return run_id

    def mark_step_done(self, run_id: str, step: int, checkpoint: dict) -> None:
        self._db.update_run(
            run_id,
            current_step=step,
            checkpoint_json=json.dumps(checkpoint),
        )

    def complete(self, run_id: str) -> None:
        self._db.update_run(run_id, status="completed")

    def fail(self, run_id: str, error: str) -> None:
        self._db.update_run(run_id, status="failed")
        row = self._db.get_run(run_id)
        if row:
            self._db.append_event(run_id, "_supervisor", "run.failed",
                                  {"error": error})

    def block(self, run_id: str) -> None:
        self._db.update_run(run_id, status="blocked")

    def get_checkpoint(self, run_id: str) -> Optional[dict]:
        row = self._db.get_run(run_id)
        if row and row.get("checkpoint_json"):
            return json.loads(row["checkpoint_json"])
        return None


# ── LoopGuard ─────────────────────────────────────────────────────────────────

EXACT_LOOP_THRESHOLD = 3   # same agent + same hash
THRASH_LOOP_THRESHOLD = 5  # same agent regardless of hash
WINDOW_SIZE = 10


def _compute_input_hash(text: str) -> str:
    """SHA-256 of input text with run-specific fields stripped."""
    cleaned = re.sub(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|'
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?',
        '',
        text,
        flags=re.IGNORECASE,
    )
    return hashlib.sha256(cleaned.encode()).hexdigest()[:16]


class LoopGuard:
    def __init__(self, db=_db):
        self._db = db

    def check(self, run_id: str, agent_name: str, input_text: str) -> Optional[str]:
        events = self._db.get_recent_events(run_id, limit=WINDOW_SIZE)
        called_events = [e for e in events if e["event_type"] == "agent.called"]

        input_hash = _compute_input_hash(input_text)

        same_hash_count = sum(
            1 for e in called_events
            if e["agent_name"] == agent_name
            and json.loads(e.get("payload_json") or "{}").get("input_hash") == input_hash
        )
        if same_hash_count >= EXACT_LOOP_THRESHOLD:
            return (
                f"\u26a0 Loop: {agent_name} called {same_hash_count}x with identical input. "
                f"Try a different approach or skip this step?"
            )

        same_agent_count = sum(
            1 for e in called_events if e["agent_name"] == agent_name
        )
        if same_agent_count >= THRASH_LOOP_THRESHOLD:
            return (
                f"\u26a0 Thrash detected: {agent_name} called {same_agent_count}x in this run. "
                f"Routing to reflection_agent for diagnosis."
            )

        return None

    def record(self, run_id: str, agent_name: str, input_text: str) -> str:
        h = _compute_input_hash(input_text)
        self._db.append_event(run_id, agent_name, "agent.called",
                              {"input_hash": h, "input_excerpt": input_text[:200]})
        return h


# ── CircuitBreaker ────────────────────────────────────────────────────────────

CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_RESET_MINUTES = 30


class CircuitBreaker:
    def __init__(self, db=_db):
        self._db = db

    def check(self, agent_name: str) -> Optional[str]:
        circuit = self._db.get_circuit(agent_name)
        state = circuit["state"]

        if state == "closed":
            return None

        if state == "open":
            opened_at = circuit.get("opened_at")
            if opened_at:
                elapsed = datetime.utcnow() - datetime.fromisoformat(opened_at)
                if elapsed >= timedelta(minutes=CIRCUIT_RESET_MINUTES):
                    self._db.upsert_circuit(agent_name, state="half-open")
                    return None
            return (
                f"\u26a0 {agent_name} failed {circuit['failure_count']}x. "
                f"Last error recorded. Fix the issue or skip this step? "
                f"Reset with: python main.py reset-circuit {agent_name}"
            )

        if state == "half-open":
            return None

        return None

    def record_failure(self, agent_name: str) -> None:
        circuit = self._db.get_circuit(agent_name)
        new_count = circuit["failure_count"] + 1
        new_state = "open" if new_count >= CIRCUIT_FAILURE_THRESHOLD else circuit["state"]
        opened_at = (
            datetime.utcnow().isoformat()
            if new_state == "open" and circuit["state"] != "open"
            else circuit.get("opened_at")
        )
        self._db.upsert_circuit(
            agent_name,
            failure_count=new_count,
            last_failure_at=datetime.utcnow().isoformat(),
            opened_at=opened_at,
            state=new_state,
        )

    def record_success(self, agent_name: str) -> None:
        self._db.upsert_circuit(
            agent_name,
            failure_count=0,
            state="closed",
            opened_at=None,
            last_failure_at=None,
        )

    @staticmethod
    def reset(agent_name: str) -> None:
        _db.upsert_circuit(agent_name, failure_count=0, state="closed",
                           opened_at=None, last_failure_at=None)


# ── StalenessRegistry ─────────────────────────────────────────────────────────

EVENT_INVALIDATION_MAP: dict[str, list[str]] = {
    "new_call_note":               ["sales_call_prep", "crm_updater"],
    "deal_stage_change":           ["proposal_generator", "deal_analyst"],
    "new_product_version":         ["proposal_generator", "qa_agent"],
    "win_loss_recorded":           ["audience_builder", "campaign_composer"],
    "new_company_news":            ["lead_researcher"],
    "campaign_performance_update": ["campaign_analyst", "campaign_composer"],
}


class StalenessRegistry:
    def __init__(self, db=_db):
        self._db = db

    def is_stale(self, entity_id: str, entity_type: str, agent_name: str) -> bool:
        return self._db.is_stale(entity_id.lower().strip(), entity_type, agent_name)

    def record_run(self, entity_id: str, entity_type: str,
                   agent_name: str, run_id: str) -> None:
        ttl = _db.AGENT_TTL_DAYS.get(agent_name, _db.AGENT_TTL_DAYS["_default"])
        self._db.set_validity(
            entity_id.lower().strip(), entity_type, agent_name, run_id, ttl
        )

    def fire_event(self, entity_id: str, entity_type: str, event_name: str) -> None:
        affected = EVENT_INVALIDATION_MAP.get(event_name, [])
        if affected:
            self._db.invalidate(
                entity_id.lower().strip(), entity_type, affected,
                f"event:{event_name}"
            )


# ── DeadLetterQueue ───────────────────────────────────────────────────────────

class DeadLetterQueue:
    def __init__(self, db=_db):
        self._db = db

    def push(self, run_id: str, pipeline_type: str, blocked_on: str,
             last_error: str, completed_steps: list) -> str:
        self._db.push_dlq(run_id, pipeline_type, blocked_on, last_error, completed_steps)
        return (
            f"\u26a0 Run {run_id} blocked after all retries on {blocked_on}. "
            f"Completed: {', '.join(completed_steps) or 'none'}. "
            f"Last error: {last_error}. "
            f"Resume when ready: python main.py resume {run_id}"
        )

    def list_entries(self) -> list[dict]:
        return self._db.list_dlq_entries()


# ── Supervisor ────────────────────────────────────────────────────────────────

class Supervisor:
    """
    Wires all 5 supervisor components. Used by ADK callbacks in main.py.
    """

    def __init__(self, db=_db):
        self.pipeline_run = PipelineRun(db=db)
        self.loop_guard = LoopGuard(db=db)
        self.circuit_breaker = CircuitBreaker(db=db)
        self.staleness = StalenessRegistry(db=db)
        self.dlq = DeadLetterQueue(db=db)
        self._db = db
        self._step_counters: dict[str, list[str]] = {}

    def pre_call_check(self, run_id: Optional[str], agent_name: str,
                       input_text: str) -> Optional[str]:
        if run_id is None:
            return None

        if agent_name in ("reflection_agent", "company_orchestrator",
                          "sales_orchestrator", "marketing_orchestrator",
                          "product_orchestrator"):
            return None

        circuit_msg = self.circuit_breaker.check(agent_name)
        if circuit_msg:
            self._db.append_event(run_id, agent_name, "circuit.opened",
                                  {"message": circuit_msg})
            return circuit_msg

        loop_msg = self.loop_guard.check(run_id, agent_name, input_text)
        if loop_msg:
            self._db.append_event(run_id, agent_name, "loop.detected",
                                  {"message": loop_msg})
            return loop_msg

        return None

    def log_called(self, run_id: Optional[str], agent_name: str,
                   input_text: str) -> None:
        if not run_id:
            return
        self.loop_guard.record(run_id, agent_name, input_text)
        if run_id not in self._step_counters:
            self._step_counters[run_id] = []
        self._step_counters[run_id].append(agent_name)

    def log_returned(self, run_id: Optional[str], agent_name: str,
                     output_text: str, duration_ms: int = 0,
                     error: Optional[str] = None) -> None:
        if not run_id:
            return
        if error:
            self.circuit_breaker.record_failure(agent_name)
        else:
            self.circuit_breaker.record_success(agent_name)
        self._db.append_event(run_id, agent_name, "agent.returned", {
            "output_excerpt": output_text[:500],
            "duration_ms": duration_ms,
            "error": error,
        })

    def checkpoint(self, run_id: Optional[str], agent_name: str) -> None:
        if not run_id:
            return
        steps = self._step_counters.get(run_id, [])
        step_num = len(steps)
        self.pipeline_run.mark_step_done(
            run_id, step_num,
            checkpoint={"last_agent": agent_name, "completed_steps": steps},
        )

    def update_validity(self, run_id: Optional[str], agent_name: str,
                        state: dict) -> None:
        if not run_id:
            return
        entity_id = (state.get("entity_id") or state.get("company")
                     or state.get("campaign") or state.get("product_id") or "unknown")
        entity_type = state.get("entity_type", "company")
        self.staleness.record_run(entity_id, entity_type, agent_name, run_id)
