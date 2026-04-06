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

import os
import re
import shutil
import subprocess
import webbrowser
from pathlib import Path

CLAUDE_WORKS_ROOT = Path(__file__).parent.parent / "claude_works"
MAX_FIX_ITERATIONS = 2  # 2 QA fix rounds max

# Per-phase timeouts — total pipeline target: 1.5 hours
# Research agents ~15 min + build ~65 min + QA/ship ~10 min = ~90 min
PHASE_TIMEOUTS = {
    "scaffold": 900,      # 15 min — project setup, DB schema, auth skeleton
    "features": 2400,     # 40 min — core features, endpoints, pages (longest)
    "polish": 900,        # 15 min — UI refinement, error states, responsive
    "server_start": 180,  # 3 min — install deps + start
    "fix": 600,           # 10 min per QA fix — needs time to read code, fix bugs, restart
}
CLAUDE_TIMEOUT = PHASE_TIMEOUTS["features"]  # default fallback

_URL_PATTERN = re.compile(r'https?://localhost:\d+\S*')

# Known error signatures that indicate failure even with exit code 0.
_OUTPUT_ERROR_PATTERNS = (
    "No endpoints found",
    "model not found",
    "invalid_api_key",
    "rate_limit_exceeded",
    "context_length_exceeded",
)

import logging as _logging
_log = _logging.getLogger(__name__)


def _check_output_for_errors(output: str) -> str | None:
    """Return error message if output contains known error patterns, else None."""
    clean = re.sub(r'\x1b\[[0-9;]*m', '', output)
    for pattern in _OUTPUT_ERROR_PATTERNS:
        if pattern.lower() in clean.lower():
            for line in clean.splitlines():
                if pattern.lower() in line.lower():
                    return line.strip()
            return pattern
    return None


def _run_claude(project_dir: str, task: str, timeout: int = CLAUDE_TIMEOUT) -> dict:
    """Run Claude CLI on a project directory with a task prompt."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return {"ok": False, "error": "claude CLI not found on PATH", "output": ""}

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
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=str(project_dir),
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

    output_err = _check_output_for_errors(combined)
    if output_err:
        return {"ok": False, "error": f"claude output error: {output_err}", "output": combined}

    return {"ok": True, "error": None, "output": combined}


def _detect_url(output: str) -> str:
    """Extract localhost URL from output."""
    match = _URL_PATTERN.search(output)
    return match.group(0) if match else ""


def _start_dev_server(project_dir: str) -> str:
    """Detect the stack and start the dev server as a background process.

    Returns the localhost URL if the server starts successfully, else empty string.
    """
    import time
    import socket
    project = Path(project_dir)

    # Pick a free port
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    port = _free_port()

    # Detect stack and build the start command
    if (project / "manage.py").exists():
        # Django
        subprocess.run(["pip", "install", "-r", str(project / "requirements.txt")],
                       cwd=project_dir, capture_output=True, timeout=300)
        subprocess.run(["python", "manage.py", "migrate"],
                       cwd=project_dir, capture_output=True, timeout=120)
        cmd = ["python", "manage.py", "runserver", f"0.0.0.0:{port}"]
    elif (project / "requirements.txt").exists():
        # Flask / FastAPI
        subprocess.run(["pip", "install", "-r", str(project / "requirements.txt")],
                       cwd=project_dir, capture_output=True, timeout=300)
        # Detect FastAPI vs Flask
        main_candidates = ["main.py", "app.py", "server.py", "run.py"]
        app_file = None
        app_module = None
        for candidate in main_candidates:
            fpath = project / candidate
            if fpath.exists():
                content = fpath.read_text(errors="ignore")
                app_file = candidate
                if "FastAPI" in content or "fastapi" in content:
                    module = candidate.replace(".py", "")
                    # Detect the app variable name
                    app_var = "app"
                    for line in content.splitlines():
                        if "FastAPI(" in line and "=" in line:
                            app_var = line.split("=")[0].strip()
                            break
                    cmd = ["python", "-m", "uvicorn", f"{module}:{app_var}",
                           "--host", "0.0.0.0", "--port", str(port)]
                    app_module = f"{module}:{app_var}"
                    break
                elif "Flask" in content or "flask" in content:
                    cmd = ["python", candidate]
                    # Set Flask port via env
                    break
        else:
            return ""

        if not app_file:
            return ""

        # For Flask, inject port via env
        if "Flask" in (project / app_file).read_text(errors="ignore"):
            env = {**__import__("os").environ, "FLASK_RUN_PORT": str(port), "PORT": str(port)}
            # Check if app.run() uses a hardcoded port — if so, use flask run instead
            content = (project / app_file).read_text(errors="ignore")
            if "app.run(" in content and "port" not in content.split("app.run(")[-1].split(")")[0]:
                cmd = ["python", "-m", "flask", "run", "--host", "0.0.0.0", "--port", str(port)]
                env["FLASK_APP"] = app_file
            elif "app.run(" in content:
                # Has hardcoded port — just run it and detect port from output
                cmd = ["python", app_file]
                port = 5000  # Flask default
            else:
                cmd = ["python", "-m", "flask", "run", "--host", "0.0.0.0", "--port", str(port)]
                env["FLASK_APP"] = app_file
        else:
            env = None
    elif (project / "package.json").exists():
        # Node.js
        subprocess.run(["npm", "install"], cwd=project_dir, capture_output=True, timeout=300)
        cmd = ["npm", "run", "dev"]
        env = {**__import__("os").environ, "PORT": str(port)}
    else:
        # Static HTML — check for index.html or any .html file
        html_files = list(project.glob("*.html"))
        if not html_files:
            html_files = list(project.glob("**/*.html"))
        if html_files:
            cmd = ["python", "-m", "http.server", str(port)]
            env = None
        else:
            return ""

    # Start server as background process
    try:
        proc = subprocess.Popen(
            cmd, cwd=project_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env if env else None,
        )
    except Exception:
        return ""

    # Wait for the port to be ready (up to 15 seconds)
    url = f"http://localhost:{port}"
    for _ in range(30):
        time.sleep(0.5)
        if proc.poll() is not None:
            # Process exited — server failed to start
            return ""
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return url
        except OSError:
            continue

    # Timeout — kill and report failure
    proc.terminate()
    return ""


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

    def _save_checkpoint(rpt: dict):
        """Persist current build state to SQLite for resume-from-checkpoint."""
        if not product_id:
            return
        try:
            from tools.product_memory_tools import save_product_state
            save_product_state(product_id, build_checkpoint=json.dumps(rpt))
        except Exception:
            pass  # Checkpoint is best-effort

    phases = [
        ("scaffold", scaffold_task),
        ("features", feature_task),
        ("polish", polish_task),
    ]

    # ── Resume from checkpoint ────────────────────────────────────
    report = {
        "status": "building",
        "url": None,
        "phases_completed": [],
        "phases_failed": [],
        "phase_summaries": {},
        "qa_results": [],
        "fix_iterations": 0,
    }
    _resumed = False
    if product_id:
        try:
            from tools.product_memory_tools import recall_build_checkpoint
            checkpoint = recall_build_checkpoint(product_id)
            if checkpoint and checkpoint.get("phases_completed"):
                report["phases_completed"] = checkpoint["phases_completed"]
                report["phases_failed"] = checkpoint.get("phases_failed", [])
                report["phase_summaries"] = checkpoint.get("phase_summaries", {})
                report["url"] = checkpoint.get("url")
                report["qa_results"] = checkpoint.get("qa_results", [])
                report["fix_iterations"] = checkpoint.get("fix_iterations", 0)
                _resumed = True
                _log_progress("resume", "completed",
                              f"Resumed from checkpoint — phases done: {report['phases_completed']}")
        except Exception:
            pass  # If checkpoint load fails, start fresh

    def _make_context_prefix() -> str:
        """Build forward-context prefix from completed phases."""
        parts = [
            "IMPORTANT: This is an EXISTING project in the current directory. "
            "Read the existing files first to understand the current state. "
            "Do NOT recreate files that already exist — only add or modify.",
        ]
        for prev_name, summary in report["phase_summaries"].items():
            parts.append(f"\n[{prev_name.upper()} PHASE COMPLETED]: {summary}")
        for failure in report["phases_failed"]:
            parts.append(
                f"\n[WARNING: {failure['phase'].upper()} PHASE FAILED]: "
                f"{failure['error'][:200]}. You may need to handle what "
                f"this phase was supposed to do."
            )
        return "\n".join(parts)

    def _run_phase(phase_name: str, phase_prompt: str):
        """Run a single build phase via Claude CLI."""
        if phase_name != "scaffold":
            phase_prompt = _make_context_prefix() + "\n\n" + phase_prompt
        timeout = PHASE_TIMEOUTS.get(phase_name, CLAUDE_TIMEOUT)
        _log_progress(phase_name, "running",
                      f"Building {phase_name} (timeout: {timeout}s)...")
        return _run_claude(str(project_dir), phase_prompt, timeout=timeout)

    def _process_result(phase_name: str, result: dict):
        """Record phase outcome in the report."""
        if result["ok"]:
            report["phases_completed"].append(phase_name)
            url = _detect_url(result["output"])
            if url:
                report["url"] = url
            output = result["output"]
            summary = output[-300:].strip() if len(output) > 300 else output.strip()
            for line in reversed(summary.split("\n")):
                if len(line.strip()) > 20:
                    summary = line.strip()
                    break
            report["phase_summaries"][phase_name] = summary[:500]
            _log_progress(phase_name, "completed", summary[:200])
        else:
            report["phases_failed"].append({"phase": phase_name, "error": result["error"]})
            _log_progress(phase_name, "failed", f"{phase_name} failed: {result['error']}")

    # --- Phase 1: Scaffold (always sequential — sets up project structure) ---
    if "scaffold" in report["phases_completed"]:
        _log_progress("scaffold", "skipped", "Already completed (resumed from checkpoint)")
    else:
        _log_progress("scaffold", "starting", "Beginning scaffold phase")
        result = _run_phase("scaffold", scaffold_task)
        _process_result("scaffold", result)
        _save_checkpoint(report)

    # --- Start dev server early for live preview during build ---
    if not report["url"] and "scaffold" in report["phases_completed"]:
        _log_progress("server_start", "starting", "Starting dev server for live preview...")
        url = _start_dev_server(str(project_dir))
        if url:
            report["url"] = url
            _log_progress("server_start", "completed", f"Live preview at {url}")

    # --- Phase 2: Features ---
    if "features" in report["phases_completed"]:
        _log_progress("features", "skipped", "Already completed (resumed from checkpoint)")
    else:
        _log_progress("features", "starting", "Beginning features phase")
        result = _run_phase("features", feature_task)
        _process_result("features", result)
        _save_checkpoint(report)

    # --- Phase 3: Polish ---
    if "polish" in report["phases_completed"]:
        _log_progress("polish", "skipped", "Already completed (resumed from checkpoint)")
    else:
        _log_progress("polish", "starting", "Beginning polish phase")
        result = _run_phase("polish", polish_task)
        _process_result("polish", result)
        _save_checkpoint(report)

    # --- Start dev server if not already running ---
    if not report["url"]:
        _log_progress("server_start", "starting", "Starting dev server...")
        url = _start_dev_server(str(project_dir))
        if url:
            report["url"] = url
            _log_progress("server_start", "completed", f"Server running at {url}")
        else:
            _log_progress("server_start", "failed", "Could not start dev server")

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
            _save_checkpoint(report)
        else:
            if report["url"]:
                report["status"] = "shipped_with_issues"
            else:
                report["status"] = "built"
    else:
        report["status"] = "built_no_server"

    # Final checkpoint — clear it on success (no need to resume a completed build)
    _save_checkpoint(report)
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
