# Claude Code Execution Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `build_and_run` and `open_in_browser` tools that let ADK orchestrators invoke Claude Code CLI to build and run anything locally inside `claude_works/`.

**Architecture:** A single `tools/claude_code_tools.py` shells out to `claude --print --dangerously-skip-permissions` inside a sandboxed `claude_works/<project>/` directory. Both functions are registered directly on `company_orchestrator` and `engineering_orchestrator`. No new agent layer.

**Tech Stack:** Python stdlib (`subprocess`, `shutil`, `webbrowser`, `re`, `pathlib`), Claude Code CLI, pytest + `unittest.mock`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `aass_agents/tools/claude_code_tools.py` | `build_and_run`, `open_in_browser` |
| Create | `aass_agents/tests/test_claude_code_tools.py` | All unit + integration tests |
| Modify | `aass_agents/agents/company_orchestrator_agent.py` | Import + register both tools |
| Modify | `aass_agents/agents/engineering/engineering_orchestrator_agent.py` | Import + register both tools |
| Modify | `.gitignore` | Add `claude_works/` |

---

### Task 1: Gitignore + workspace directory

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add `claude_works/` to `.gitignore`**

Append to `E:/Workspace/sl_agents/.gitignore` (create if missing):
```
claude_works/
```

- [ ] **Step 2: Create the workspace root**

```bash
mkdir -p E:/Workspace/sl_agents/aass_agents/claude_works
```

- [ ] **Step 3: Commit**

```bash
cd E:/Workspace/sl_agents
git add .gitignore
git commit -m "chore: ignore claude_works/ build sandbox"
```

---

### Task 2: Failing tests for `build_and_run`

**Files:**
- Create: `aass_agents/tests/test_claude_code_tools.py`

- [ ] **Step 1: Write failing tests**

Create `aass_agents/tests/test_claude_code_tools.py`:

```python
"""Tests for claude_code_tools — build_and_run and open_in_browser."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_build_and_run_returns_url(tmp_path, monkeypatch):
    """URL in Claude Code output → return 'Built and running at ...'"""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Created files.\nServer running at http://localhost:3000\n"
    mock_result.stderr = ""
    with patch("tools.claude_code_tools.shutil.which", return_value="/usr/bin/claude"), \
         patch("tools.claude_code_tools.subprocess.run", return_value=mock_result):
        result = build_and_run("test-proj", "build a hello world app")
    assert result == "Built and running at http://localhost:3000"


def test_build_and_run_no_url_returns_done(tmp_path, monkeypatch):
    """No URL in output → return 'Done. Files written to ...'"""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Created hello.py with print('hello')"
    mock_result.stderr = ""
    with patch("tools.claude_code_tools.shutil.which", return_value="/usr/bin/claude"), \
         patch("tools.claude_code_tools.subprocess.run", return_value=mock_result):
        result = build_and_run("test-script", "write a hello world python script")
    assert result == "Done. Files written to claude_works/test-script/"


def test_build_and_run_timeout(tmp_path, monkeypatch):
    """Subprocess timeout → return error string."""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    with patch("tools.claude_code_tools.shutil.which", return_value="/usr/bin/claude"), \
         patch("tools.claude_code_tools.subprocess.run",
               side_effect=subprocess.TimeoutExpired("claude", 600)):
        result = build_and_run("test-proj", "build something")
    assert result == "Error: timed out after 600s"


def test_build_and_run_creates_project_dir(tmp_path, monkeypatch):
    """Project directory is created under CLAUDE_WORKS_ROOT."""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    with patch("tools.claude_code_tools.shutil.which", return_value="/usr/bin/claude"), \
         patch("tools.claude_code_tools.subprocess.run", return_value=mock_result):
        build_and_run("my-new-project", "build something")
    assert (tmp_path / "my-new-project").is_dir()


def test_claude_cli_not_found(tmp_path, monkeypatch):
    """Missing claude binary → return helpful error."""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    with patch("tools.claude_code_tools.shutil.which", return_value=None):
        result = build_and_run("test-proj", "build something")
    assert result.startswith("Error: claude CLI not found")


def test_build_and_run_nonzero_exit(tmp_path, monkeypatch):
    """Non-zero exit code → return stderr as error."""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "Permission denied"
    with patch("tools.claude_code_tools.shutil.which", return_value="/usr/bin/claude"), \
         patch("tools.claude_code_tools.subprocess.run", return_value=mock_result):
        result = build_and_run("test-proj", "build something")
    assert result == "Error: Permission denied"


def test_open_in_browser_success():
    """Successful browser open → return 'Opened <url>'."""
    with patch("tools.claude_code_tools.webbrowser.open", return_value=True):
        result = open_in_browser("http://localhost:3000")
    assert result == "Opened http://localhost:3000"


def test_open_in_browser_exception():
    """Browser open raises → return error string."""
    with patch("tools.claude_code_tools.webbrowser.open",
               side_effect=Exception("no browser available")):
        result = open_in_browser("http://localhost:3000")
    assert result.startswith("Error:")


@pytest.mark.integration
def test_integration_hello_world(tmp_path, monkeypatch):
    """Actually runs claude CLI to write a file. Requires claude CLI + ANTHROPIC_API_KEY."""
    monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)
    result = build_and_run(
        "integration-test",
        "Create a file called hello.txt containing exactly: Hello World",
    )
    assert "Error" not in result
    assert (tmp_path / "integration-test" / "hello.txt").exists()
```

Note: this file has no imports yet — it will fail with `NameError` until Task 3 adds them.

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd E:/Workspace/sl_agents/aass_agents
python -m pytest tests/test_claude_code_tools.py -v 2>&1 | head -20
```

Expected: `NameError: name 'build_and_run' is not defined` (or similar collection error)

---

### Task 3: Implement `claude_code_tools.py` + fix test imports

**Files:**
- Create: `aass_agents/tools/claude_code_tools.py`
- Modify: `aass_agents/tests/test_claude_code_tools.py` (add imports)

- [ ] **Step 1: Create `tools/claude_code_tools.py`**

```python
"""
Claude Code execution tools.

Provides build_and_run() and open_in_browser() as ADK tools so orchestrators
can build and run anything locally — website, API, script, game, data pipeline —
inside the sandboxed claude_works/ directory.

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
CLAUDE_TIMEOUT = 600  # seconds

_URL_PATTERN = re.compile(r'https?://localhost:\d+\S*')


def build_and_run(project_name: str, task: str) -> str:
    """
    Use Claude Code CLI to build and run anything in a sandboxed local folder.

    Creates claude_works/<project_name>/, runs claude --print with the task,
    and returns the localhost URL when a dev server is started, or a completion
    message when no server is needed (scripts, libraries, data pipelines, etc.).

    Args:
        project_name: Folder slug under claude_works/ (e.g. "acme-dashboard").
                      Lowercase-hyphenated. Created automatically if missing.
        task: Full natural-language description of what to build. Pass the user's
              requirement verbatim — website, REST API, CLI tool, game, data pipeline,
              automation script, anything.

    Returns:
        "Built and running at http://localhost:<port>" — dev server detected in output
        "Done. Files written to claude_works/<project_name>/" — no server (script/lib)
        "Error: <reason>" — timeout, missing CLI, or non-zero exit
    """
    project_dir = CLAUDE_WORKS_ROOT / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    claude_bin = shutil.which("claude")
    if not claude_bin:
        return "Error: claude CLI not found. Install Claude Code from https://claude.ai/code"

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
            timeout=CLAUDE_TIMEOUT,
            cwd=str(project_dir),
        )
    except subprocess.TimeoutExpired:
        return f"Error: timed out after {CLAUDE_TIMEOUT}s"
    except Exception as exc:
        return f"Error: {exc}"

    if result.returncode != 0:
        stderr = result.stderr.strip()
        return f"Error: {stderr or f'claude exited with code {result.returncode}'}"

    combined = result.stdout + result.stderr
    url_match = _URL_PATTERN.search(combined)
    if url_match:
        return f"Built and running at {url_match.group(0)}"

    return f"Done. Files written to claude_works/{project_name}/"


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
```

- [ ] **Step 2: Add imports to test file**

Add at the top of `aass_agents/tests/test_claude_code_tools.py` (before the first `def`):

```python
from tools.claude_code_tools import build_and_run, open_in_browser
```

- [ ] **Step 3: Run all unit tests — confirm they pass**

```bash
cd E:/Workspace/sl_agents/aass_agents
python -m pytest tests/test_claude_code_tools.py -v 2>&1
```

Expected:
```
test_build_and_run_returns_url          PASSED
test_build_and_run_no_url_returns_done  PASSED
test_build_and_run_timeout              PASSED
test_build_and_run_creates_project_dir  PASSED
test_claude_cli_not_found               PASSED
test_build_and_run_nonzero_exit         PASSED
test_open_in_browser_success            PASSED
test_open_in_browser_exception          PASSED
8 passed, 1 deselected
```

- [ ] **Step 4: Run full test suite — confirm nothing broken**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```

Expected: all previously passing tests still pass, 8 new tests added.

- [ ] **Step 5: Commit**

```bash
cd E:/Workspace/sl_agents/aass_agents
git add tools/claude_code_tools.py tests/test_claude_code_tools.py
git commit -m "feat: add claude_code_tools — build_and_run and open_in_browser"
```

---

### Task 4: Wire tools into `company_orchestrator_agent.py`

**Files:**
- Modify: `aass_agents/agents/company_orchestrator_agent.py`

- [ ] **Step 1: Add import**

In `company_orchestrator_agent.py`, after the existing `from tools.memory_tools import ...` line, add:

```python
from tools.claude_code_tools import build_and_run, open_in_browser
```

- [ ] **Step 2: Add tools to agent**

Change the `tools=[...]` block in the `company_orchestrator = Agent(...)` call from:

```python
    tools=[
        save_deal_context,
        recall_deal_context,
        list_active_deals,
        save_agent_output,
        recall_past_outputs,
    ],
```

to:

```python
    tools=[
        save_deal_context,
        recall_deal_context,
        list_active_deals,
        save_agent_output,
        recall_past_outputs,
        build_and_run,
        open_in_browser,
    ],
```

- [ ] **Step 3: Verify import works**

```bash
cd E:/Workspace/sl_agents/aass_agents
python -c "from agents.company_orchestrator_agent import company_orchestrator; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```

Expected: same pass count as after Task 3, no regressions.

- [ ] **Step 5: Commit**

```bash
git add agents/company_orchestrator_agent.py
git commit -m "feat: register build_and_run and open_in_browser on company_orchestrator"
```

---

### Task 5: Wire tools into `engineering_orchestrator_agent.py`

**Files:**
- Modify: `aass_agents/agents/engineering/engineering_orchestrator_agent.py`

- [ ] **Step 1: Add import**

In `engineering_orchestrator_agent.py`, after the existing `from tools.engineering_tools import ...` line, add:

```python
from tools.claude_code_tools import build_and_run, open_in_browser
```

- [ ] **Step 2: Add tools to agent**

Change the `tools=[...]` line in `engineering_orchestrator = Agent(...)` from:

```python
    tools=[save_agent_output, recall_past_outputs, create_pipeline_spec, get_pipeline_status, log_integration],
```

to:

```python
    tools=[
        save_agent_output,
        recall_past_outputs,
        create_pipeline_spec,
        get_pipeline_status,
        log_integration,
        build_and_run,
        open_in_browser,
    ],
```

- [ ] **Step 3: Verify import works**

```bash
cd E:/Workspace/sl_agents/aass_agents
python -c "from agents.engineering.engineering_orchestrator_agent import engineering_orchestrator; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```

Expected: all tests pass, no regressions.

- [ ] **Step 5: Final commit**

```bash
git add agents/engineering/engineering_orchestrator_agent.py
git commit -m "feat: register build_and_run and open_in_browser on engineering_orchestrator"
```
