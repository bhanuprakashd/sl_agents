---
name: review-implementing
description: Process and implement code review feedback systematically. Use when user provides reviewer comments, PR feedback, code review notes, or asks to implement suggestions from engineering reviews on the aass_agents codebase.
triggers:
  - "implement review feedback"
  - "address PR comments"
  - "apply review changes"
  - "implement suggestions"
  - "address these comments"
  - "fix review notes"
---

# Review Feedback Implementation

Systematically process and implement changes based on code review feedback. In aass_agents this applies to the engineering department's PR reviews across all agent teams (engineering, product, QA, research, autoresearcher, marketing, sales).

## When to Use

- Provides reviewer comments or feedback on a PR
- Pastes PR review notes from GitHub (`gh pr view <number> --comments`)
- Mentions implementing review suggestions
- Says "address these comments" or "implement feedback"
- Shares list of changes requested by reviewers after `gh pr review`

## aass_agents Context

- **Repo root**: `/Users/bhanu.prakash/Documents/claude_works/sl_agents/aass_agents/`
- **Agent teams**: `agents/_shared`, `agents/autoresearcher`, `agents/engineering`, `agents/marketing`, `agents/product`, `agents/qa`, `agents/research`, `agents/sales`
- **Shared utilities**: `shared/` and `tools/`
- **Tests**: `tests/` — always run after changes: `pytest`
- **Linting**: `ruff check` (configured in `pyproject.toml`)
- **Style**: immutable data patterns, small functions (<50 lines), files <800 lines
- **PR workflow**: `gh pr view`, `gh pr review`, `gh pr comment`

## Systematic Workflow

### 1. Parse Reviewer Notes

Identify individual feedback items:
- Fetch PR comments: `gh api repos/OWNER/REPO/pulls/NUMBER/comments`
- Split numbered lists (1., 2., etc.)
- Handle bullet points or inline review comments
- Extract distinct change requests
- Clarify ambiguous items before starting

### 2. Create Todo List

Use TodoWrite tool to create actionable tasks:
- Each feedback item becomes one or more todos
- Break down complex feedback into smaller tasks
- Make tasks specific and measurable
- Mark first task as `in_progress` before starting

Example for aass_agents:
```
- Add type hints to orchestrator agent function
- Fix duplicate tool registration in engineering_orchestrator_agent.py
- Update docstring in reflection_agent.py
- Add unit test for edge case in qa_engineer_agent
- Address immutability violation in sales/crm_updater_agent.py
```

### 3. Implement Changes Systematically

For each todo item:

**Locate relevant code:**
- Use Grep to search for functions/classes across `agents/`
- Use Glob to find agent files by pattern (e.g., `agents/engineering/*.py`)
- Read current implementation with Read tool

**Make changes:**
- Use Edit tool for modifications
- Follow aass_agents conventions: immutable patterns, no mutation, explicit error handling
- Preserve existing agent functionality unless the review specifically requests a behaviour change

**Verify changes:**
- Check syntax correctness
- Run relevant tests: `pytest tests/<team>/ -v`
- Ensure changes address reviewer's intent

**Update status:**
- Mark todo as `completed` immediately after finishing
- Move to next todo (only one `in_progress` at a time)

### 4. Handle Different Feedback Types

**Code changes:**
- Use Edit tool for existing agent code
- Follow type hint conventions (PEP 604/585)
- Maintain consistent style across the agent team directory

**New features:**
- Create new agent files with Write tool if needed
- Add corresponding tests under `tests/<team>/`
- Update `__init__.py` for the relevant team package

**Documentation:**
- Update docstrings following project style
- Modify markdown files under `docs/` as needed
- Keep explanations concise

**Tests:**
- Write tests as functions, not classes
- Use descriptive names matching the agent under test
- Follow pytest conventions; place in matching `tests/<team>/` directory

**Refactoring:**
- Preserve agent functionality
- Improve code structure (reduce file size, improve cohesion)
- Run `pytest` to verify no regressions after refactoring

### 5. Validation

After implementing all changes:
- Run full test suite: `pytest`
- Check for linting errors: `ruff check .`
- Verify changes don't break existing agent functionality
- Confirm no hardcoded secrets or API keys were introduced

### 6. Communication

Keep user informed:
- Update todo list in real-time
- Ask for clarification on ambiguous feedback
- Report blockers or challenges
- Summarize changes at completion

## Edge Cases

**Conflicting feedback:**
- Ask user for guidance
- Explain the conflict clearly (e.g., reviewer A wants X, reviewer B wants Y)

**Breaking changes required:**
- Notify user before implementing
- Discuss impact on downstream agents (orchestrators that call this agent)

**Tests fail after changes:**
- Fix tests before marking todo complete
- Ensure all related tests pass before moving to next item

## Example Workflow

User: "Address the PR comments on my engineering agent refactor"

1. Fetch PR comments via `gh api` — 4 distinct items identified
2. Create todo list:
   - Fix import path after directory restructure
   - Add missing type hints to `engineering_orchestrator_agent.py`
   - Extract large function (80 lines) into two focused helpers
   - Add test for the new helper
3. Implement each item → run `pytest tests/engineering/ -v` after each
4. Run `ruff check .` → clean
5. Run full `pytest` → all pass
6. Summarize changes to user
