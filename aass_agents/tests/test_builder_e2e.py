"""
E2E test for the builder pipeline — validates build_review_improve works end-to-end.
Runs a simple "rocket-themed login page" build and checks output.

Usage:
    python -m pytest tests/test_builder_e2e.py -v -s --timeout=600
    # or directly:
    python tests/test_builder_e2e.py
"""
import json
import os
import shutil
import sys
import time

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from tools.claude_code_tools import (
    build_review_improve,
    CLAUDE_WORKS_ROOT,
    _check_output_for_errors,
)


PROJECT_NAME = "test-rocket-login"
PROJECT_DIR = CLAUDE_WORKS_ROOT / PROJECT_NAME


def cleanup():
    """Remove test project dir if it exists."""
    if PROJECT_DIR.exists():
        shutil.rmtree(PROJECT_DIR, ignore_errors=True)


def test_error_detection():
    """Unit test: _check_output_for_errors catches known patterns."""
    # Should detect
    assert _check_output_for_errors("Error: No endpoints found for google/gemini-3-pro") is not None
    assert _check_output_for_errors("\x1b[91mError: No endpoints found for foo\x1b[0m") is not None
    assert _check_output_for_errors("model not found: gpt-99") is not None
    # Should pass clean
    assert _check_output_for_errors("Build completed successfully") is None
    assert _check_output_for_errors("All files written") is None
    print("PASS: _check_output_for_errors")


def test_claude_on_path():
    """Unit test: claude CLI is available."""
    import shutil
    assert shutil.which("claude"), "claude CLI not found on PATH"
    print("PASS: claude CLI found")


def test_build_rocket_login():
    """E2E test: build a rocket-themed login page and verify output."""
    cleanup()

    scaffold_task = (
        "Create a simple single-page login application with a rocket/space theme.\n"
        "Tech stack: Python + Flask + SQLite.\n"
        "Files to create:\n"
        "  - app.py (Flask app with login/signup routes)\n"
        "  - requirements.txt (flask, flask-cors)\n"
        "  - templates/login.html (rocket-themed login page)\n"
        "  - schema.sql (users table: id, email, password_hash, created_at)\n"
        "Setup: initialize DB from schema.sql in app startup.\n"
        "Do NOT start a dev server yet.\n"
    )

    feature_task = (
        "IMPORTANT: This is an EXISTING project. Read the existing files first.\n"
        "Implement these features in the existing Flask app:\n"
        "1. POST /login — validate email+password, return success/error\n"
        "2. POST /signup — create user, hash password, return success\n"
        "3. GET / — serve the login page (templates/login.html)\n"
        "4. The login page must have:\n"
        "   - Rocket/space themed design (dark background, stars, rocket emoji or SVG)\n"
        "   - Email + password fields\n"
        "   - Login and Sign Up buttons\n"
        "   - Client-side form validation\n"
        "   - Responsive layout\n"
        "Do NOT start a dev server.\n"
    )

    polish_task = (
        "IMPORTANT: This is an EXISTING project. Read the existing files first.\n"
        "Polish the rocket login page:\n"
        "- Add CSS animations (floating stars, rocket launch on submit)\n"
        "- Add error/success toast messages\n"
        "- Ensure mobile responsive\n"
        "- Add a subtle gradient background\n"
        "After polish, START the dev server (flask run or python app.py).\n"
    )

    print(f"\n{'='*60}")
    print(f"BUILDING: {PROJECT_NAME}")
    print(f"DIR: {PROJECT_DIR}")
    print(f"{'='*60}\n")

    start = time.time()
    result_json = build_review_improve(
        project_name=PROJECT_NAME,
        scaffold_task=scaffold_task,
        feature_task=feature_task,
        polish_task=polish_task,
        product_id="test-rocket-001",
    )
    elapsed = time.time() - start

    result = json.loads(result_json)

    print(f"\n{'='*60}")
    print(f"BUILD RESULT ({elapsed:.0f}s)")
    print(f"{'='*60}")
    print(f"Status:           {result['status']}")
    print(f"URL:              {result.get('url', 'none')}")
    print(f"Phases completed: {result['phases_completed']}")
    print(f"Phases failed:    {result.get('phases_failed', [])}")
    print(f"QA iterations:    {result.get('fix_iterations', 0)}")
    print(f"QA results:       {len(result.get('qa_results', []))} rounds")

    # Check files were actually created
    files_created = list(PROJECT_DIR.rglob("*"))
    py_files = [f for f in files_created if f.suffix == ".py"]
    html_files = [f for f in files_created if f.suffix == ".html"]
    print(f"\nFiles created:    {len(files_created)} total, {len(py_files)} .py, {len(html_files)} .html")

    # Assertions
    errors = []
    if "scaffold" not in result["phases_completed"]:
        errors.append("scaffold phase did not complete")
    if "features" not in result["phases_completed"]:
        errors.append("features phase did not complete")
    if not py_files:
        errors.append("no Python files created")
    if not html_files:
        errors.append("no HTML files created")
    if result["status"] in ("building", "built_no_server"):
        # Not fatal but worth noting
        print(f"\nWARNING: status is '{result['status']}' — server may not have started")

    if errors:
        print(f"\nFAILED: {errors}")
        return False
    else:
        print(f"\nPASS: Rocket login page built successfully!")
        return True


if __name__ == "__main__":
    print("=" * 60)
    print("BUILDER AGENT E2E TEST")
    print("=" * 60)

    # Run unit tests first
    test_error_detection()
    test_claude_on_path()

    # Run E2E build test
    passed = test_build_rocket_login()
    sys.exit(0 if passed else 1)
