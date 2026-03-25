---
name: test-fixing
description: Run tests and systematically fix all failing tests using smart error grouping. Use when user asks to fix failing tests, mentions test failures, CI pipeline is red, or requests to make the automated test suite pass.
triggers:
  - "fix failing tests"
  - "tests are broken"
  - "CI is red"
  - "fix test suite"
  - "make tests pass"
  - "test suite is failing"
---

# Test Fixing

Systematically identify and fix all failing tests using smart grouping strategies. In aass_agents this applies across the QA department's automated test suites covering all agent teams (sales, engineering, research, marketing, product, autoresearcher).

## When to Use

- Explicitly asked to fix tests ("fix these tests", "make tests pass")
- Reports test failures ("tests are failing", "test suite is broken")
- CI pipeline is red after a push or PR
- Implementation complete and tests need to pass before merge
- `pytest` run in `/Users/bhanu.prakash/Documents/claude_works/sl_agents/aass_agents/tests/` reports failures

## aass_agents Context

- **Test runner**: `pytest` (configured via `pytest.ini` at repo root)
- **Test directory**: `tests/` — mirrors `agents/` subdirectory structure (qa, engineering, sales, etc.)
- **Run all tests**: `cd /Users/bhanu.prakash/Documents/claude_works/sl_agents/aass_agents && pytest`
- **Run subset**: `pytest tests/qa/ -v` or `pytest -k "pattern" -v`
- **Agent teams**: `_shared`, `autoresearcher`, `engineering`, `marketing`, `product`, `qa`, `research`, `sales`
- **Shared code**: `shared/` and `agents/_shared/reflection_agent.py` — failures here cascade across all teams

## Systematic Approach

### 1. Initial Test Run

Run `pytest` to identify all failing tests.

Analyze output for:
- Total number of failures
- Error types and patterns
- Affected agent modules/files

### 2. Smart Error Grouping

Group similar failures by:
- **Error type**: ImportError, AttributeError, AssertionError, etc.
- **Module/file**: Same agent file causing multiple test failures
- **Root cause**: Missing dependencies, API changes, agent refactoring impacts

Prioritize groups by:
- Number of affected tests (highest impact first)
- Dependency order (fix `_shared` and infrastructure before individual agents)

### 3. Systematic Fixing Process

For each group (starting with highest impact):

1. **Identify root cause**
   - Read relevant agent code under `agents/`
   - Check recent changes with `git diff`
   - Understand the error pattern

2. **Implement fix**
   - Use Edit tool for code changes
   - Follow project conventions (immutable data patterns, small focused functions)
   - Make minimal, focused changes

3. **Verify fix**
   - Run subset of tests for this group:
     ```bash
     pytest tests/path/to/test_file.py -v
     pytest -k "pattern" -v
     ```
   - Ensure group passes before moving on

4. **Move to next group**

### 4. Fix Order Strategy

**Infrastructure first (highest cascade risk):**
- Import errors in `agents/_shared/` or `shared/`
- Missing dependencies in `requirements.txt` / `pyproject.toml`
- Configuration issues (env vars, DB paths like `sales_memory.db`, `evolution.db`)

**Then agent API changes:**
- Function signature changes in orchestrator agents
- Module reorganization after directory restructuring (e.g., recent renames to `agents/qa/`, `agents/engineering/`)
- Renamed variables/functions in agent definitions

**Finally, logic issues:**
- Assertion failures in agent behaviour tests
- Business logic bugs in individual agents
- Edge case handling in tool integrations

### 5. Final Verification

After all groups fixed:
- Run complete test suite: `pytest`
- Verify no regressions
- Check test coverage remains intact
- Confirm CI would pass (green on all agent team suites)

## Best Practices

- Fix one group at a time
- Run focused tests after each fix
- Use `git diff` to understand recent changes — recent renames (e.g., flat `agents/` to sub-team directories) are a common source of ImportErrors
- Look for patterns in failures
- Do not move to next group until current passes
- Keep changes minimal and focused
- Never modify tests to mask real failures — fix the implementation

## Example Workflow

User: "CI is red after the agent directory restructure"

1. Run `pytest` — 15 failures identified
2. Group errors:
   - 8 ImportErrors (`from agents.qa_agent` → `from agents.qa.qa_agent`)
   - 5 AttributeErrors (orchestrator API changed)
   - 2 AssertionErrors (logic bugs in sales agent)
3. Fix ImportErrors first → Run subset → Verify
4. Fix AttributeErrors → Run subset → Verify
5. Fix AssertionErrors → Run subset → Verify
6. Run full suite → All pass
