"""
Claude Code execution tools — iterative build system.

Provides build_and_run() for simple single-shot builds, and
build_review_improve() for sophisticated multi-phase iterative builds
that produce production-quality output comparable to human-Claude sessions.

The iterative builder:
  Phase 1: Scaffold (project structure, DB schema, config)
  Phase 2: Features (all core features, API endpoints, pages)
  Phase 3: Polish (UI refinement, error handling, edge cases)
  Phase 4: QA test loop (curl tests → fix → retest, up to 3 iterations)

Requirements:
  - claude CLI on PATH  (install from https://claude.ai/code)
  - ANTHROPIC_API_KEY env var available to the subprocess
"""

import re
import shutil
import subprocess
import webbrowser
from pathlib import Path

CLAUDE_WORKS_ROOT = Path(__file__).parent.parent / "claude_works"
MAX_FIX_ITERATIONS = 2  # 2 QA fix rounds max

# Per-phase timeouts — total pipeline target: 1 hour
# Research agents ~10 min + build ~48 min + QA/ship ~2 min = ~60 min
PHASE_TIMEOUTS = {
    "scaffold": 480,      # 8 min — project setup, DB schema, auth skeleton
    "features": 1200,     # 20 min — core features, endpoints, pages (longest)
    "polish": 480,        # 8 min — UI refinement, error states, responsive
    "server_start": 120,  # 2 min — install deps + start
    "fix": 300,           # 5 min per QA fix — needs time to read code, fix bugs, restart
}
CLAUDE_TIMEOUT = PHASE_TIMEOUTS["features"]  # default fallback

_URL_PATTERN = re.compile(r'https?://localhost:\d+\S*')


def _run_claude(project_dir: str, task: str, timeout: int = CLAUDE_TIMEOUT) -> dict:
    """Run Claude CLI and return structured result."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return {"ok": False, "error": "claude CLI not found", "output": ""}

    cmd = [
        claude_bin,
        "--print",
        "--add-dir", str(project_dir),
        "--dangerously-skip-permissions",
        "--output-format", "text",
        task,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(project_dir),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timed out after {timeout}s", "output": ""}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "output": ""}

    combined = result.stdout + result.stderr
    if result.returncode != 0:
        stderr = result.stderr.strip()
        return {
            "ok": False,
            "error": stderr or f"claude exited with code {result.returncode}",
            "output": combined,
        }

    return {"ok": True, "error": None, "output": combined}


def _detect_url(output: str) -> str:
    """Extract localhost URL from output."""
    match = _URL_PATTERN.search(output)
    return match.group(0) if match else ""


def _run_curl_tests(base_url: str) -> str:
    """Run basic curl smoke tests against the running app."""
    tests = []
    try:
        import urllib.request
        import urllib.error

        # Test 1: Homepage loads
        try:
            req = urllib.request.Request(base_url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                body_preview = resp.read(500).decode("utf-8", errors="replace")
                tests.append(f"GET {base_url} => {status} OK (body: {len(body_preview)} chars)")
        except Exception as e:
            tests.append(f"GET {base_url} => FAIL: {e}")

        # Test 2: Check common API endpoints
        for endpoint in ["/api/auth/login", "/api/auth/signup"]:
            url = base_url.rstrip("/") + endpoint
            try:
                import json as _json
                data = _json.dumps({"email": "test@test.com", "password": "test123"}).encode()
                req = urllib.request.Request(url, data=data, method="POST")
                req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    tests.append(f"POST {endpoint} => {resp.status}")
            except urllib.error.HTTPError as e:
                tests.append(f"POST {endpoint} => HTTP {e.code} ({e.reason})")
            except Exception as e:
                tests.append(f"POST {endpoint} => FAIL: {e}")

        # Test 3: Check if dashboard/main pages exist
        for page in ["/dashboard", "/ponds", "/about"]:
            url = base_url.rstrip("/") + page
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    tests.append(f"GET {page} => {resp.status}")
            except urllib.error.HTTPError as e:
                tests.append(f"GET {page} => HTTP {e.code}")
            except Exception as e:
                tests.append(f"GET {page} => FAIL: {e}")

    except Exception as e:
        tests.append(f"Test framework error: {e}")

    return "\n".join(tests)


def build_and_run(project_name: str, task: str) -> str:
    """
    Single-shot build using Claude Code CLI. Use build_review_improve for better results.

    Args:
        project_name: Folder slug under claude_works/ (e.g. "acme-dashboard").
        task: Full natural-language description of what to build.

    Returns:
        "Built and running at http://localhost:<port>" — dev server detected
        "Done. Files written to claude_works/<project_name>/" — no server
        "Error: <reason>" — timeout, missing CLI, or non-zero exit
    """
    project_dir = CLAUDE_WORKS_ROOT / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    result = _run_claude(str(project_dir), task)
    if not result["ok"]:
        return f"Error: {result['error']}"

    url = _detect_url(result["output"])
    if url:
        return f"Built and running at {url}"
    return f"Done. Files written to claude_works/{project_name}/"


def build_review_improve(
    project_name: str,
    scaffold_task: str,
    feature_task: str,
    polish_task: str,
    product_id: str = "",
) -> str:
    """
    Iterative multi-phase build that produces production-quality apps.

    Executes 3 build phases sequentially, then runs automated tests and
    iterates fixes up to 3 times. This mimics a human-Claude session where
    you build incrementally, test, and refine.

    Phase 1 (Scaffold): Project structure, database schema, config, auth
    Phase 2 (Features): All core features, API endpoints, pages, CRUD
    Phase 3 (Polish): UI refinement, error states, loading states, responsive design
    Phase 4 (QA Loop): Automated curl tests → fix issues → retest (up to 3x)

    Args:
        project_name: Folder slug under claude_works/ (e.g. "shrimp-farm-hub").
        scaffold_task: Phase 1 prompt — project setup, DB, auth, config.
        feature_task: Phase 2 prompt — all features, endpoints, pages.
        polish_task: Phase 3 prompt — UI polish, error handling, edge cases.
        product_id: Optional UUID for progress tracking (enables real-time monitoring).

    Returns:
        JSON string with: status, url, phases_completed, qa_results, iterations
    """
    import json
    project_dir = CLAUDE_WORKS_ROOT / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    # Progress tracking helper
    def _log_progress(phase: str, status: str, message: str = "", output: str = ""):
        if product_id:
            try:
                from tools.build_progress import log_build_phase
                log_build_phase(product_id, phase, status, message, output[:500])
            except Exception:
                pass  # Progress tracking is best-effort, never blocks build

    phases = [
        ("scaffold", scaffold_task),
        ("features", feature_task),
        ("polish", polish_task),
    ]

    report = {
        "status": "building",
        "url": None,
        "phases_completed": [],
        "phases_failed": [],
        "phase_summaries": {},
        "qa_results": [],
        "fix_iterations": 0,
    }

    # --- Phase 1-3: Build incrementally with forward context ---
    for phase_name, phase_prompt in phases:
        _log_progress(phase_name, "starting", f"Beginning {phase_name} phase")

        # Feed forward: inject prior phase outcomes into current prompt
        if phase_name != "scaffold":
            context_parts = [
                "IMPORTANT: This is an EXISTING project in the current directory. "
                "Read the existing files first to understand the current state. "
                "Do NOT recreate files that already exist — only add or modify.",
            ]

            # Inject prior phase summaries so each phase builds on what came before
            for prev_name, summary in report["phase_summaries"].items():
                context_parts.append(
                    f"\n[{prev_name.upper()} PHASE COMPLETED]: {summary}"
                )

            # If previous phases failed, warn about what needs attention
            for failure in report["phases_failed"]:
                context_parts.append(
                    f"\n[WARNING: {failure['phase'].upper()} PHASE FAILED]: "
                    f"{failure['error'][:200]}. You may need to handle what "
                    f"this phase was supposed to do."
                )

            phase_prompt = "\n".join(context_parts) + "\n\n" + phase_prompt

        phase_timeout = PHASE_TIMEOUTS.get(phase_name, CLAUDE_TIMEOUT)
        _log_progress(phase_name, "running", f"Claude Code building {phase_name} (timeout: {phase_timeout}s)...")
        result = _run_claude(str(project_dir), phase_prompt, timeout=phase_timeout)

        if result["ok"]:
            report["phases_completed"].append(phase_name)
            url = _detect_url(result["output"])
            if url:
                report["url"] = url

            # Extract a phase summary for forward context (last 300 chars often have the summary)
            output = result["output"]
            summary = output[-300:].strip() if len(output) > 300 else output.strip()
            # Clean: take last meaningful paragraph
            paragraphs = [p.strip() for p in summary.split("\n") if p.strip()]
            report["phase_summaries"][phase_name] = " | ".join(paragraphs[-3:])[:200]

            _log_progress(phase_name, "completed", f"{phase_name} phase done", output)
        else:
            report["phases_failed"].append({
                "phase": phase_name,
                "error": result["error"],
            })
            _log_progress(phase_name, "failed", f"{phase_name} failed: {result['error']}")
            # Don't abort — try remaining phases even if one fails

    # --- Start dev server if not already running ---
    if not report["url"]:
        _log_progress("server_start", "starting", "Starting dev server...")
        start_result = _run_claude(
            str(project_dir),
            "Read the existing project files. Install dependencies if needed (npm install). "
            "Then start the dev server (npm run dev). The project is already built — "
            "just get it running.",
            timeout=PHASE_TIMEOUTS["server_start"],
        )
        if start_result["ok"]:
            url = _detect_url(start_result["output"])
            if url:
                report["url"] = url
                _log_progress("server_start", "completed", f"Server running at {url}")
            else:
                _log_progress("server_start", "failed", "No server URL detected")
        else:
            _log_progress("server_start", "failed", start_result["error"])

    # --- QA test loop with structured result parsing ---
    if report["url"]:
        for iteration in range(MAX_FIX_ITERATIONS):
            report["fix_iterations"] = iteration + 1
            phase_label = f"qa_test_{iteration + 1}"

            _log_progress(phase_label, "starting", f"QA test iteration {iteration + 1}")

            # Run tests
            test_results = _run_curl_tests(report["url"])

            # Structured parsing — don't just search for "FAIL" substring
            test_lines = test_results.strip().split("\n")
            failed_tests = [l for l in test_lines if "=> FAIL" in l or "=> HTTP 5" in l]
            passed_tests = [l for l in test_lines if "=> 200" in l or "OK" in l]
            warning_tests = [l for l in test_lines if "=> HTTP 4" in l and "=> HTTP 5" not in l]

            report["qa_results"].append({
                "iteration": iteration + 1,
                "results": test_results,
                "passed": len(passed_tests),
                "failed": len(failed_tests),
                "warnings": len(warning_tests),
            })

            # All tests pass if zero failures (warnings like 401 for auth are acceptable)
            if not failed_tests:
                report["status"] = "shipped"
                _log_progress(phase_label, "completed",
                              f"All tests passed ({len(passed_tests)} OK, {len(warning_tests)} warnings)")
                break

            _log_progress(phase_label, "completed",
                          f"{len(failed_tests)} failures, {len(passed_tests)} passed — fixing")

            # Fix with specific failure context
            fix_label = f"fix_{iteration + 1}"
            _log_progress(fix_label, "starting", f"Fixing {len(failed_tests)} issues (attempt {iteration + 1})")

            # Build targeted fix prompt with specific failure details
            failure_detail = "\n".join(f"  FAILED: {l}" for l in failed_tests)
            success_detail = "\n".join(f"  PASSED: {l}" for l in passed_tests[:5])

            fix_prompt = (
                f"IMPORTANT: This is an EXISTING project. Read the current files first.\n\n"
                f"The app is running at {report['url']}.\n\n"
                f"## Test Results Summary\n"
                f"Passed: {len(passed_tests)} | Failed: {len(failed_tests)} | Warnings: {len(warning_tests)}\n\n"
                f"## Failures (MUST FIX — these are blocking):\n{failure_detail}\n\n"
                f"## Already Working (DO NOT BREAK):\n{success_detail}\n\n"
                f"## Fix Strategy\n"
                f"1. Read the relevant source files for each failure\n"
                f"2. Identify the root cause (missing route? wrong DB query? missing page?)\n"
                f"3. Fix each failure WITHOUT breaking the passing tests\n"
                f"4. After fixing, restart the dev server\n"
            )
            fix_result = _run_claude(str(project_dir), fix_prompt, timeout=PHASE_TIMEOUTS["fix"])
            if fix_result["ok"]:
                new_url = _detect_url(fix_result["output"])
                if new_url:
                    report["url"] = new_url
                _log_progress(fix_label, "completed", f"Fixes applied for {len(failed_tests)} failures")
            else:
                _log_progress(fix_label, "failed", fix_result["error"])
        else:
            if report["url"]:
                report["status"] = "shipped_with_issues"
            else:
                report["status"] = "built"
    else:
        report["status"] = "built_no_server"

    return json.dumps(report, indent=2)


def build_with_feedback_loop(
    project_name: str,
    scaffold_task: str,
    feature_task: str,
    polish_task: str,
    product_id: str = "",
    prd: str = "",
    max_feedback_rounds: int = 5,
) -> str:
    """
    Multi-phase build + human-in-the-loop feedback loop.

    Runs the standard build_review_improve pipeline, then enters an
    interactive feedback loop where the user reviews the live app and
    provides improvement feedback. The system intelligently analyzes
    feedback (explicit + inferred + self-critique), generates a targeted
    improvement plan, rebuilds, and repeats until the user approves.

    Args:
        project_name: Folder slug under claude_works/
        scaffold_task: Phase 1 prompt — project setup, DB, auth, config
        feature_task: Phase 2 prompt — all features, endpoints, pages
        polish_task: Phase 3 prompt — UI polish, error handling, edge cases
        product_id: UUID for progress tracking
        prd: Original PRD text/JSON for self-critique against requirements
        max_feedback_rounds: Max feedback rounds (default 5). 0 = ask user.

    Returns:
        JSON string with build result + feedback loop outcome
    """
    import json

    # Inject learned skills + common feedback pitfalls into build prompts
    try:
        from tools.human_feedback_loop import get_prebuild_quality_context
        quality_ctx = get_prebuild_quality_context(project_name, prd)
        if quality_ctx:
            quality_block = (
                "\n\n## Quality Context (from past builds — avoid these known issues):\n"
                + quality_ctx + "\n"
            )
            scaffold_task += quality_block
            feature_task += quality_block
            polish_task += quality_block
    except Exception:
        pass  # Quality context is best-effort

    # Phase 1: Run the standard multi-phase build
    build_result_json = build_review_improve(
        project_name, scaffold_task, feature_task, polish_task, product_id,
    )
    build_result = json.loads(build_result_json)

    # Phase 2: Enter feedback loop if we have a running URL
    if build_result.get("url"):
        from tools.human_feedback_loop import run_feedback_loop

        feedback_result_json = run_feedback_loop(
            product_id=product_id,
            project_name=project_name,
            build_url=build_result["url"],
            prd=prd,
            qa_report=json.dumps(build_result.get("qa_results", [])),
            max_rounds=max_feedback_rounds,
        )
        feedback_result = json.loads(feedback_result_json)

        build_result["feedback"] = feedback_result
        if feedback_result.get("url"):
            build_result["url"] = feedback_result["url"]
        if feedback_result.get("status") == "approved":
            build_result["status"] = "approved"

        # Phase 3: Meta-learning — update skill quality based on feedback outcome
        if product_id:
            try:
                from tools.skill_memory import update_skill_quality_from_feedback
                update_skill_quality_from_feedback(product_id, feedback_result)
            except Exception:
                pass  # Meta-learning is best-effort

    return json.dumps(build_result, indent=2)


def open_in_browser(url: str) -> str:
    """
    Open a URL in the system default browser.

    Args:
        url: URL to open, e.g. "http://localhost:3000"

    Returns:
        "Opened <url>" on success, "Error: <reason>" on failure.
    """
    try:
        webbrowser.open(url)
        return f"Opened {url}"
    except Exception as exc:
        return f"Error: {exc}"
