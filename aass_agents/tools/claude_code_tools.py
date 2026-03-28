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
