"""
Parallel Executor — run independent agents concurrently with DAG scheduling.

Inspired by Claude Code's TeamCreateTool + InProcessTeammateTask pattern
and open-multi-agent's AgentPool scheduling strategies.

Features:
  - DAG-based topological sorting with wave execution
  - 4 scheduling strategies: dependency_first, round_robin, least_busy, capability_match
  - Semaphore-based concurrency control respecting rate limits
  - Isolated ADK sessions per task (no context contamination)
  - Supervisor safety checks (circuit breakers, loop detection) per task
"""
import asyncio
import json
import os
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from tools.progress_callbacks import broadcaster


# ── Scheduling Strategies ────────────────────────────────────────────────────

class SchedulingStrategy(str, Enum):
    """Agent pool scheduling strategies (borrowed from open-multi-agent)."""
    DEPENDENCY_FIRST = "dependency_first"  # Default: topological DAG order
    ROUND_ROBIN = "round_robin"            # Cycle agents evenly across slots
    LEAST_BUSY = "least_busy"              # Pick agent with fewest active tasks
    CAPABILITY_MATCH = "capability_match"  # Match agent capabilities to task needs


@dataclass(frozen=True)
class ParallelTask:
    """A single task in a parallel pipeline."""
    agent_name: str
    prompt: str
    depends_on: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()  # For capability_match strategy


@dataclass(frozen=True)
class TaskResult:
    """Result of a parallel task execution."""
    agent_name: str
    output: str
    success: bool
    duration_ms: int
    error: Optional[str] = None


class _AgentLoadTracker:
    """Tracks active task count per agent for least-busy scheduling."""

    def __init__(self) -> None:
        self._active: dict[str, int] = defaultdict(int)

    def acquire(self, agent_name: str) -> None:
        self._active[agent_name] += 1

    def release(self, agent_name: str) -> None:
        self._active[agent_name] = max(0, self._active[agent_name] - 1)

    def get_load(self, agent_name: str) -> int:
        return self._active[agent_name]

    def least_busy(self, candidates: list[str]) -> str:
        """Return the candidate with the fewest active tasks."""
        return min(candidates, key=lambda a: self._active[a])


def _topological_sort(tasks: list[ParallelTask]) -> list[list[ParallelTask]]:
    """
    Sort tasks into waves where each wave's tasks can run in parallel.
    Returns list of waves, each wave is a list of independent tasks.
    """
    task_map = {t.agent_name: t for t in tasks}
    completed: set[str] = set()
    waves: list[list[ParallelTask]] = []

    remaining = set(task_map.keys())

    while remaining:
        # Find tasks whose dependencies are all completed
        wave = [
            task_map[name] for name in remaining
            if all(dep in completed for dep in task_map[name].depends_on)
        ]

        if not wave:
            # Circular dependency or missing dependency
            unresolved = remaining - completed
            raise ValueError(
                f"Unresolvable dependencies: {unresolved}. "
                f"Check depends_on references."
            )

        waves.append(wave)
        for task in wave:
            completed.add(task.agent_name)
            remaining.discard(task.agent_name)

    return waves


def _apply_round_robin(wave: list[ParallelTask], max_slots: int) -> list[list[ParallelTask]]:
    """Split a wave into sub-waves using round-robin across available slots."""
    if len(wave) <= max_slots:
        return [wave]
    sub_waves: list[list[ParallelTask]] = [[] for _ in range(max_slots)]
    for i, task in enumerate(wave):
        sub_waves[i % max_slots].append(task)
    return [sw for sw in sub_waves if sw]


def _reorder_by_least_busy(
    wave: list[ParallelTask], tracker: _AgentLoadTracker,
) -> list[ParallelTask]:
    """Reorder a wave so least-busy agents run first (get picked up by semaphore sooner)."""
    return sorted(wave, key=lambda t: tracker.get_load(t.agent_name))


def _reorder_by_capability_match(wave: list[ParallelTask]) -> list[ParallelTask]:
    """Reorder a wave so tasks with specific capabilities run before generic ones."""
    return sorted(wave, key=lambda t: -len(t.required_capabilities))


class ParallelExecutor:
    """
    Execute a DAG of agent tasks with concurrency control and scheduling strategies.

    Strategies:
      - dependency_first: Default DAG topological order
      - round_robin:      Distribute tasks evenly across concurrent slots
      - least_busy:       Prioritize agents with fewer active tasks
      - capability_match: Prioritize tasks with specific capability requirements

    Usage:
        executor = ParallelExecutor(runner, supervisor, session_service)
        results = await executor.execute(tasks, run_id, strategy="least_busy")
    """

    def __init__(
        self,
        runner_factory: "callable",  # (agent_name) -> Runner
        supervisor: "Supervisor",
        session_service: "InMemorySessionService",
        app_name: str = "sl-agents-parallel",
        max_concurrent: int = 0,
    ):
        self._runner_factory = runner_factory
        self._supervisor = supervisor
        self._session_service = session_service
        self._app_name = app_name
        self._max_concurrent = max_concurrent or int(os.getenv("MAX_PARALLEL_AGENTS", "3"))
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._load_tracker = _AgentLoadTracker()

    async def _run_single_task(
        self,
        task: ParallelTask,
        run_id: str,
        context: dict[str, str],
        user_id: str = "parallel-executor",
    ) -> TaskResult:
        """Execute a single agent task with supervisor safety checks."""
        from google.genai.types import Content, Part

        async with self._semaphore:
            self._load_tracker.acquire(task.agent_name)
            start = time.monotonic()
            agent_name = task.agent_name

            # Emit progress
            await broadcaster.emit_agent_event(
                run_id, agent_name, "agent.started",
                f"Starting parallel task: {agent_name}",
            )

            # Check circuit breaker
            block_msg = self._supervisor.pre_call_check(run_id, agent_name, task.prompt)
            if block_msg:
                duration = int((time.monotonic() - start) * 1000)
                await broadcaster.emit_agent_event(
                    run_id, agent_name, "agent.failed", block_msg,
                )
                return TaskResult(
                    agent_name=agent_name,
                    output=block_msg,
                    success=False,
                    duration_ms=duration,
                    error=f"Supervisor blocked: {block_msg}",
                )

            self._supervisor.log_called(run_id, agent_name, task.prompt)

            # Create isolated session for this task
            session_id = f"parallel-{run_id}-{agent_name}"
            try:
                await self._session_service.create_session(
                    app_name=self._app_name,
                    user_id=user_id,
                    session_id=session_id,
                )
            except Exception:
                pass  # Session may already exist

            # Substitute context variables in prompt
            prompt = task.prompt
            for key, value in context.items():
                prompt = prompt.replace(f"{{{key}}}", value)

            try:
                runner = self._runner_factory(agent_name)
                output_parts: list[str] = []

                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=Content(
                        role="user",
                        parts=[Part(text=prompt)],
                    ),
                ):
                    if event.is_final_response():
                        if event.content and event.content.parts:
                            for part in event.content.parts:
                                if hasattr(part, "text") and part.text:
                                    output_parts.append(part.text)

                output = "\n".join(output_parts) or "(no output)"
                duration = int((time.monotonic() - start) * 1000)

                self._supervisor.log_returned(run_id, agent_name, output, duration)
                self._supervisor.checkpoint(run_id, agent_name)

                await broadcaster.emit_agent_event(
                    run_id, agent_name, "agent.completed",
                    f"Completed in {duration}ms",
                )

                self._load_tracker.release(agent_name)
                return TaskResult(
                    agent_name=agent_name,
                    output=output,
                    success=True,
                    duration_ms=duration,
                )

            except Exception as exc:
                duration = int((time.monotonic() - start) * 1000)
                error_msg = str(exc)

                self._supervisor.log_returned(
                    run_id, agent_name, "", duration, error=error_msg,
                )

                await broadcaster.emit_agent_event(
                    run_id, agent_name, "agent.failed", error_msg,
                )

                self._load_tracker.release(agent_name)
                return TaskResult(
                    agent_name=agent_name,
                    output="",
                    success=False,
                    duration_ms=duration,
                    error=error_msg,
                )

    async def execute(
        self,
        tasks: list[ParallelTask],
        run_id: str,
        initial_context: Optional[dict[str, str]] = None,
        strategy: SchedulingStrategy = SchedulingStrategy.DEPENDENCY_FIRST,
    ) -> list[TaskResult]:
        """
        Execute a DAG of tasks with configurable scheduling strategy.

        Strategies:
          - dependency_first: Default topological wave order
          - round_robin:      Split waves evenly across concurrent slots
          - least_busy:       Prioritize agents with fewer active tasks
          - capability_match: Prioritize tasks needing specific capabilities

        Tasks within the same wave run concurrently. Waves execute sequentially.
        If a task fails, dependent tasks in later waves are skipped.
        Context from completed tasks is passed to later tasks via substitution.
        """
        waves = _topological_sort(tasks)
        all_results: list[TaskResult] = []
        context: dict[str, str] = dict(initial_context or {})
        failed_agents: set[str] = set()

        for wave_idx, wave in enumerate(waves):
            # Filter out tasks whose dependencies failed
            runnable = []
            for task in wave:
                failed_deps = [d for d in task.depends_on if d in failed_agents]
                if failed_deps:
                    failed_agents.add(task.agent_name)
                    all_results.append(TaskResult(
                        agent_name=task.agent_name,
                        output=f"Skipped: dependency failed ({', '.join(failed_deps)})",
                        success=False,
                        duration_ms=0,
                        error=f"Dependencies failed: {', '.join(failed_deps)}",
                    ))
                else:
                    runnable.append(task)

            if not runnable:
                continue

            # Apply scheduling strategy to reorder tasks within the wave
            if strategy == SchedulingStrategy.LEAST_BUSY:
                runnable = _reorder_by_least_busy(runnable, self._load_tracker)
            elif strategy == SchedulingStrategy.CAPABILITY_MATCH:
                runnable = _reorder_by_capability_match(runnable)
            elif strategy == SchedulingStrategy.ROUND_ROBIN:
                # Round-robin splits into sub-waves executed sequentially
                sub_waves = _apply_round_robin(runnable, self._max_concurrent)
                for sub_wave in sub_waves:
                    sub_results = await self._execute_wave(sub_wave, run_id, context)
                    for task, result in sub_results:
                        all_results.append(result)
                        if result.success:
                            context[task.agent_name] = result.output
                        else:
                            failed_agents.add(task.agent_name)
                continue

            # Default: execute full wave in parallel
            wave_results = await self._execute_wave(runnable, run_id, context)
            for task, result in wave_results:
                all_results.append(result)
                if result.success:
                    context[task.agent_name] = result.output
                else:
                    failed_agents.add(task.agent_name)

        return all_results

    async def _execute_wave(
        self,
        tasks: list[ParallelTask],
        run_id: str,
        context: dict[str, str],
    ) -> list[tuple[ParallelTask, TaskResult]]:
        """Execute a wave of tasks in parallel, returning (task, result) pairs."""
        coros = [
            self._run_single_task(task, run_id, context)
            for task in tasks
        ]
        raw_results = await asyncio.gather(*coros, return_exceptions=True)

        paired: list[tuple[ParallelTask, TaskResult]] = []
        for task, result in zip(tasks, raw_results):
            if isinstance(result, Exception):
                result = TaskResult(
                    agent_name=task.agent_name,
                    output="",
                    success=False,
                    duration_ms=0,
                    error=str(result),
                )
            paired.append((task, result))
        return paired


# ── ADK Tool Function ────────────────────────────────────────────────────────

def run_parallel_pipeline(
    pipeline_name: str,
    context_json: str = "{}",
    strategy: str = "dependency_first",
) -> str:
    """
    Execute a named parallel pipeline with a scheduling strategy.

    Args:
        pipeline_name: Name of the pipeline to execute (e.g., "product_build")
        context_json: JSON string with context variables for prompt substitution
        strategy: Scheduling strategy — one of "dependency_first", "round_robin", "least_busy", "capability_match"

    Returns:
        JSON string with execution results for all tasks
    """
    from agents._shared.pipeline_defs import get_pipeline

    pipeline = get_pipeline(pipeline_name)
    if pipeline is None:
        return json.dumps({
            "error": f"Unknown pipeline: {pipeline_name}",
            "available": list(_get_available_pipelines()),
        })

    try:
        sched = SchedulingStrategy(strategy)
    except ValueError:
        return json.dumps({
            "error": f"Unknown strategy: {strategy}",
            "available": [s.value for s in SchedulingStrategy],
        })

    try:
        context = json.loads(context_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid context_json"})

    # This function is sync (ADK tool), so we need to run async code
    try:
        loop = asyncio.get_running_loop()
        # Already in async context — create a task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, _execute_pipeline(pipeline, context))
            results = future.result(timeout=600)
    except RuntimeError:
        # No running loop — we can use asyncio.run directly
        results = asyncio.run(_execute_pipeline(pipeline, context))

    return json.dumps({
        "pipeline": pipeline_name,
        "strategy": sched.value,
        "results": [
            {
                "agent": r.agent_name,
                "success": r.success,
                "duration_ms": r.duration_ms,
                "output_preview": r.output[:500] if r.output else "",
                "error": r.error,
            }
            for r in results
        ],
        "total_duration_ms": sum(r.duration_ms for r in results),
        "all_succeeded": all(r.success for r in results),
    }, indent=2)


async def _execute_pipeline(
    tasks: list[ParallelTask],
    context: dict,
) -> list[TaskResult]:
    """Internal async pipeline execution."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from tools.supervisor import Supervisor

    session_service = InMemorySessionService()
    supervisor = Supervisor()
    run_id = str(uuid.uuid4())

    # We need agent instances to create runners
    # Import lazily to avoid circular imports
    from agents.company_orchestrator_agent import company_orchestrator

    def runner_factory(agent_name: str) -> Runner:
        # Find the sub-agent by name in the agent tree
        agent = _find_agent(company_orchestrator, agent_name)
        if agent is None:
            raise ValueError(f"Agent not found: {agent_name}")
        return Runner(
            agent=agent,
            app_name="sl-agents-parallel",
            session_service=session_service,
        )

    executor = ParallelExecutor(
        runner_factory=runner_factory,
        supervisor=supervisor,
        session_service=session_service,
    )

    return await executor.execute(tasks, run_id, context)


def _find_agent(root, name: str):
    """Recursively find a sub-agent by name."""
    if root.name == name:
        return root
    for sub in getattr(root, "sub_agents", []):
        found = _find_agent(sub, name)
        if found:
            return found
    return None


def _get_available_pipelines() -> list[str]:
    """Return available pipeline names."""
    from agents._shared.pipeline_defs import PIPELINES
    return list(PIPELINES.keys())
