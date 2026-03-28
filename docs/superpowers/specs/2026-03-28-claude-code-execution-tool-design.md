# Claude Code Execution Tool — Design Spec

**Date:** 2026-03-28
**Status:** Approved
**Project:** sl_agents / aass_agents

---

## Overview

Integrate Claude Code CLI as a general-purpose local execution tool for the ADK agent system. Agents can instruct Claude Code to build and run anything — website, API, CLI tool, data pipeline, game, script — directly on localhost, sandboxed to the `claude_works/` directory.

---

## Problem

The current system generates code as text and deploys it to cloud services (GitHub → Railway/Vercel). There is no capability to build and run things locally. Users cannot ask the agent team to "build X and show it to me now" without cloud credentials, repos, and deployment pipelines.

---

## Solution

A thin subprocess wrapper (`tools/claude_code_tools.py`) that shells out to the `claude` CLI in non-interactive (`--print`) mode. Orchestrators call this tool directly — no new agent layer. Claude Code does the full work: writes files, installs dependencies, starts the server, and returns the localhost URL. The tool then opens it in Chrome.

---

## Architecture

```
User input: "build a dashboard for X with Y and Z"
    │
    ▼
company_orchestrator  (or any orchestrator)
    │  calls tool directly
    ▼
claude_code_tools.py
    │  subprocess: claude -p "<task>" --add-dir claude_works/<project> --dangerously-skip-permissions
    ▼
claude_works/<project-name>/        ← sandboxed workspace
    │  Claude Code: writes files, installs deps, starts server
    ▼
localhost:<port>
    │  open_in_browser(url)
    ▼
Chrome browser
```

---

## Tool Interface

**File:** `tools/claude_code_tools.py`

### `build_and_run(project_name: str, task: str) -> str`

Runs Claude Code against a sandboxed project directory and returns a result string.

- `project_name` — slug used as the folder name under `claude_works/` (e.g. `"acme-dashboard"`)
- `task` — full natural-language description of what to build. No constraints on type — website, API, script, game, data pipeline, automation, anything.
- Creates `claude_works/<project_name>/` if it does not exist
- Runs: `claude -p "<task>" --add-dir <project_dir> --dangerously-skip-permissions --output-format text`
- Output format is plain text; URL is extracted by scanning for `http://localhost:\d+` pattern
- Timeout: 600 seconds (10 minutes)
- Returns:
  - `"Built and running at http://localhost:<port>"` if a localhost URL is found in output
  - `"Done. Files written to claude_works/<project_name>/"` if no URL (e.g. script, library)
  - Error string prefixed with `"Error: "` on failure

### `open_in_browser(url: str) -> str`

Opens a URL in the system default browser (Chrome on Windows).

- Uses `webbrowser.open(url)`
- Returns `"Opened <url>"` on success or an error string on failure
- Called by the orchestrator after `build_and_run` returns a localhost URL

---

## Data Flow

```
1. User → orchestrator: "build a REST API for task management with SQLite"
2. Orchestrator → build_and_run("task-api", "<full requirement>")
3. Tool: creates claude_works/task-api/
4. Tool: runs claude -p "..." in that directory
5. Claude Code: writes main.py, requirements.txt, etc.
           installs dependencies
           starts uvicorn on port 8000
           outputs "Server running at http://localhost:8000"
6. Tool: parses URL from output
7. build_and_run → orchestrator: "Built and running at http://localhost:8000"
8. Orchestrator → open_in_browser("http://localhost:8000")
9. Orchestrator → user: reports URL + brief summary of what was built
```

---

## Sandbox

- **Root:** `E:\Workspace\sl_agents\claude_works\`
- **Per project:** `claude_works\<project-name>\`
- Claude Code is scoped via `--add-dir <project_dir>` — it has full read/write/execute inside the project folder
- `claude_works/` is gitignored (add to `.gitignore`)

---

## Integration Points

The two tools (`build_and_run`, `open_in_browser`) are added to the tools list of:

1. **`company_orchestrator_agent.py`** — top-level entry point, handles any cross-department build request
2. **`engineering_orchestrator_agent.py`** — handles technical build requests routed from the company orchestrator

All other orchestrators (sales, marketing, product, etc.) reach local execution via the company orchestrator's routing. No rigid per-department restriction — the orchestrators decide when to call.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Claude Code times out (> 10 min) | Return `"Error: timed out after 600s"` |
| Claude Code returns non-zero exit | Return `"Error: <stderr output>"` |
| No localhost URL in output | Return `"Done. Files written to claude_works/<project>/"` |
| `open_in_browser` fails | Log warning, still return the URL so user can open manually |
| `claude` CLI not found on PATH | Return `"Error: claude CLI not found. Install Claude Code."` |

---

## Testing

**File:** `tests/test_claude_code_tools.py`

| Test | Type | Description |
|---|---|---|
| `test_build_and_run_returns_url` | unit | Mock subprocess, verify URL is parsed and returned |
| `test_build_and_run_no_url_returns_done` | unit | Mock subprocess with no URL in output, verify fallback message |
| `test_build_and_run_timeout` | unit | Mock subprocess timeout, verify error string |
| `test_build_and_run_creates_project_dir` | unit | Verify `claude_works/<project>/` is created |
| `test_open_in_browser_success` | unit | Mock `webbrowser.open`, verify return string |
| `test_open_in_browser_bad_url` | unit | Pass malformed URL, verify error handling |
| `test_claude_cli_not_found` | unit | Mock missing CLI, verify error message |
| `test_integration_hello_world` | integration | Actually runs `claude -p "create hello.txt with Hello World"`, verifies file exists |

All unit tests run in CI (no Claude CLI required). Integration test marked `@pytest.mark.integration` — deselected by default per `pytest.ini`.

---

## `.gitignore` Addition

```
claude_works/
```

---

## Out of Scope

- Managing multiple concurrent builds (no parallelism in v1)
- Killing or stopping a running dev server (manual for now)
- Persisting build state across sessions
- Cloud deployment from `claude_works/` (existing Railway/Vercel tools handle that)
