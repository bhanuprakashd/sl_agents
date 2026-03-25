# Design: DeerFlow + Claude Code Autonomous Product Pipeline

**Date:** 2026-03-24
**Status:** Approved
**Scope:** Single vertical, full end-to-end product engineering pipeline

---

## Overview

Replace the current text-generation-only build loop (`generate_code` + `push_file`) with an
autonomous execution pipeline. ADK agents orchestrate the pipeline stages; DeerFlow skills
execute all code generation, testing, and deployment inside an isolated sandbox. Human approves
PRD and architecture upfront, then Claude Code runs the full pipeline autonomously and reports
back when the product is live. Human can report bugs post-deployment; the system fixes and
redeploys automatically.

---

## Architecture

### Three Layers

```
ADK Agents (Orchestration)
  ├─ product_orchestrator  — routes tasks, receives bug reports
  ├─ pm_agent              — PRD generation (already wired with MCP research)
  ├─ architect_agent       — stack selection + file tree
  ├─ devops_agent          — GitHub + Vercel + Railway provisioning
  ├─ db_agent              — schema + NeonDB/Supabase provisioning
  ├─ backend_builder_agent — calls DeerFlow "backend-build" skill
  ├─ frontend_builder_agent— calls DeerFlow "frontend-build" skill
  ├─ qa_agent              — calls DeerFlow "qa-smoke-test" skill
  └─ bug_fix_agent         — NEW: calls DeerFlow "bug-fix" skill

DeerFlow Skills (Execution in sandbox)
  ├─ backend-build.md      — write → run → fix → push → deploy Railway
  ├─ frontend-build.md     — write → run → fix → push → deploy Vercel
  ├─ qa-smoke-test.md      — smoke tests: root + /health + auth
  └─ bug-fix.md            — diagnose → fix → push → redeploy → verify

Shared Tool
  └─ tools/deerflow_tools.py  — call_deerflow_skill(skill_name, context) → result
```

### Key Design Decision

ADK agents are **orchestrators only** — they provision infrastructure, pass context to DeerFlow,
and save results. All code execution, testing, and self-correction happens inside DeerFlow's
sandbox.

**Sandbox prerequisite:** The current `deer-flow/config.yaml` uses `LocalSandboxProvider`, which
executes commands on the host machine. For true sandbox isolation, production deployments **must**
switch to `AioSandboxProvider` (Docker-based) in `config.yaml`:

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
```

Development can run with `LocalSandboxProvider` but the sandbox isolation guarantee only holds
in production with Docker mode enabled.

---

## Full Pipeline Sequence

```
Human: "Build me a [product requirement]"
        ↓
product_orchestrator
  ├─ New product?  → pm_agent
  └─ Bug report?   → bug_fix_agent

pm_agent
  → research via MCP (search_product_web, search_news)
  → generate PRD JSON
  → save_product_state → complete_issue
        ↓
architect_agent
  → pick stack from PRD.product_type
  → generate file tree
  → save_product_state → complete_issue
        ↓
devops_agent
  → create GitHub repo
  → create Vercel project
  → create Railway project
  → save_product_state (repo, project IDs) → complete_issue
        ↓
db_agent
  → generate SQL schema
  → provision NeonDB/Supabase
  → save DATABASE_URL → complete_issue
        ↓
backend_builder_agent
  → call_deerflow_skill("backend-build", { PRD, arch, repo, railway_id, db_url })
  → save backend_url → complete_issue
        ↓
frontend_builder_agent
  → call_deerflow_skill("frontend-build", { PRD, arch, repo, vercel_id, backend_url })
  → save frontend_url → complete_issue
        ↓
qa_agent
  → call_deerflow_skill("qa-smoke-test", { backend_url, frontend_url })
  → all passed → report to human: "Live at [frontend_url]"
  → failed → auto-route to bug_fix_agent
        ↓
Human tests live product
  → Bug found? Report back → bug_fix_agent → fix → redeploy → verify
  → Clean? Done.
```

---

## DeerFlow Skills Specification

### `backend-build.md`

**Input:** PRD (JSON), architecture (JSON), repo_full_name, railway_project_id, db_url

**Steps:**
1. Generate all backend files: `main.py`, `models/`, `routes/`, `Dockerfile`, `requirements.txt`
2. Write files to sandbox workspace
3. Run `pip install -r requirements.txt`
4. Run `python -m pytest` (if tests exist) or `python main.py --check`
5. Fix import/syntax/runtime errors — repeat until clean (max 5 iterations)
6. Push all files to GitHub under `/backend/`
7. Trigger Railway deploy, poll until URL is live (timeout: 10 min)

**Output:** `{ backend_url, files_pushed, iterations_taken }`

---

### `frontend-build.md`

**Input:** PRD (JSON), architecture (JSON), repo_full_name, vercel_project_id, backend_url

**Steps:**
1. Generate Next.js 14 App Router files: `package.json`, `tailwind.config.js`, `next.config.js`,
   `app/layout.tsx`, `app/page.tsx`, `app/globals.css`, key components from architecture.file_tree
2. Write files to sandbox workspace
3. Run `npm install`
4. Run `npm run build`
5. Fix TypeScript/build errors — repeat until clean (max 5 iterations)
6. Push all files to GitHub under `/frontend/`
7. Trigger Vercel deploy, poll until URL is live (timeout: 10 min)

**Output:** `{ frontend_url, files_pushed, iterations_taken }`

---

### `qa-smoke-test.md`

**Input:** backend_url, frontend_url

**Steps:**
1. `GET {backend_url}/health` → expect `{"status": "ok"}`
2. `GET {frontend_url}` → expect HTTP 200
3. `POST {backend_url}/auth/register` (test user) → expect 201
4. `POST {backend_url}/auth/login` → expect token in response
5. Report pass/fail per check with response details

**Output:** `{ all_passed: bool, results: [{ check, passed, response }] }`

---

### `bug-fix.md`

**Input:** bug_report (human description), backend_url, frontend_url, repo_full_name,
railway_project_id, vercel_project_id

**Steps:**
1. Pull current code from GitHub repo (`git clone {repo_full_name}` in sandbox)
2. Reproduce: run the failing scenario in sandbox using bash
3. Identify root cause from error output
4. Fix relevant files
5. Run build + test cycle until clean (max 5 iterations)
6. Push fixed files to GitHub (git commit + push)
7. Trigger redeploy on affected layer:
   - Backend changes → Railway GraphQL API (`https://backboard.railway.app/graphql/v2`)
     mutation: `deploymentCreate(input: { projectId, serviceId })` with Bearer token
     (or use Railway CLI: `railway up --service {service_id}` if CLI is available in sandbox)
   - Frontend changes → Vercel triggers automatically from git push (no manual trigger needed)
   - Both changed → trigger both
8. Re-run QA smoke tests to verify fix

**URL stability:**
- `backend_url` = Railway service URL — stable across redeploys, does not change
- `frontend_url` = Vercel **project alias** (e.g. `https://myapp.vercel.app`) — NOT the preview
  URL. Alias is set at project creation and never changes.

**Output:** `{ fixed: bool, changes_made: [filenames], backend_url, frontend_url }`
(URLs unchanged — returned for confirmation only)

---

## New & Changed Components

### New: `tools/deerflow_tools.py`

```
call_deerflow_skill(skill_name: str, context: dict) -> dict

- Raises on timeout (25 min) or explicit skill failure
- DEERFLOW_URL from env (default: http://localhost:2024)  ← LangGraph direct port
```

**Exact HTTP call sequence:**

```
# Step 1: create thread
POST {DEERFLOW_URL}/threads
Body: {}
→ response["thread_id"]

# Step 2: stream run
POST {DEERFLOW_URL}/threads/{thread_id}/runs/stream
Body: {
  "assistant_id": "lead_agent",
  "input": {
    "messages": [{
      "role": "human",
      "content": "Use skill: {skill_name}\n\nContext:\n{json.dumps(context)}"
    }]
  },
  "stream_mode": ["values"]
}
→ consume SSE lines, extract report from last "data:" event with non-empty messages[-1].content
```

**Why port 2024 (not 2026):** Port 2026 is the Nginx proxy — it routes `/api/langgraph/*` to
port 2024. Calling LangGraph directly on 2024 avoids the proxy hop and is used by all internal
services. If `DEERFLOW_URL` is set to `http://localhost:2026`, prefix paths with `/api/langgraph`.

**Timeout budget:** 25 minutes total — covers up to 5 build iterations (~2 min each) plus 10 min
deploy poll with margin.

Replaces: `generate_code`, `generate_fastapi_backend`, `generate_nextjs_frontend`,
`generate_db_schema` from `code_gen_tools.py`

---

### New: `agents/bug_fix_agent.py`

**Trigger:** `product_orchestrator` receives input with bug/error/fix keywords AND a live product exists in product state.

**Tools:** `call_deerflow_skill`, `checkout_issue`, `complete_issue`, `add_comment`,
`recall_product_state`, `save_product_state`

**Flow:**
1. `checkout_issue` for "bug-fix" step
2. `recall_product_state` → get repo, backend_url, frontend_url
3. `call_deerflow_skill("bug-fix", { bug_report, backend_url, frontend_url, repo_full_name })`
4. Save new URLs to product state (if changed after redeploy)
5. `add_comment` with fix summary + new URL
6. `complete_issue`

---

### Changed: `agents/backend_builder_agent.py`

Remove: `generate_code`, `push_file`, `deploy_from_github`, `get_service_url`

Add: `call_deerflow_skill`

New flow:
1. `checkout_issue`
2. `recall_product_state`
3. `call_deerflow_skill("backend-build", { prd, architecture, repo_full_name, railway_project_id, db_url })`
4. `save_product_state({ backend_url })`
5. `add_comment(backend_url)`
6. `complete_issue`

---

### Changed: `agents/frontend_builder_agent.py`

Remove: `generate_code`, `push_file`, `trigger_deploy`, `get_deployment_url`

Add: `call_deerflow_skill`

New flow:
1. `checkout_issue`
2. `recall_product_state`
3. `call_deerflow_skill("frontend-build", { prd, architecture, repo_full_name, vercel_project_id, backend_url })`
4. `save_product_state({ frontend_url })`
5. `add_comment(frontend_url)`
6. `complete_issue`

---

### Changed: `agents/qa_agent.py`

Remove: `http_tools` direct curl calls

Add: `call_deerflow_skill`

New flow:
1. `checkout_issue`
2. `recall_product_state`
3. `call_deerflow_skill("qa-smoke-test", { backend_url, frontend_url })`
4. `save_product_state({ qa_report: result })`
5. `complete_issue` (always — QA agent never delegates directly)
6. Return result to `product_orchestrator`

**Routing responsibility stays with `product_orchestrator`:**
- If `qa_report.all_passed == true` → report to human: "Live at [frontend_url]"
- If `qa_report.all_passed == false` → route to `bug_fix_agent`

`qa_agent` does NOT have `bug_fix_agent` in its `sub_agents`. It returns its result upward and
the orchestrator owns the routing decision. This preserves the orchestrator's retry counter logic.

---

### Changed: `agents/product_orchestrator_agent.py`

**New routing rule — bug reports:**
If input contains bug/error/fix/broken keywords AND a shipped product exists → route to `bug_fix_agent`.

**Product ID resolution for bug reports:**
Human bug reports will not contain a product UUID. The orchestrator resolves `product_id` using
`list_active_deals()` from `product_memory_tools` filtered by `status == "shipped"`. If exactly
one shipped product exists, use it. If multiple exist, ask the human: "Which product? [list names]".
If none exist, respond: "No shipped product found — please start a new product requirement."

**QA failure routing:**
If `qa_agent` returns `qa_report.all_passed == false` → route to `bug_fix_agent` with
`bug_report = "QA smoke tests failed: " + qa_report.results`.

---

## Schema Migration: `product_memory_tools.py`

The current `_VALID_COLUMNS` set must be extended. Add these columns:

```python
_VALID_COLUMNS = {
    # existing
    "product_name", "status", "prd", "architecture",
    "repo_url", "database_url", "backend_url", "frontend_url", "qa_report",
    # new — required by pipeline agents
    "repo_full_name",       # str  e.g. "org/repo-name"
    "vercel_project_id",    # str  Vercel project UUID
    "railway_project_id",   # str  Railway project UUID
    "railway_service_id",   # str  Railway service UUID (set by devops, used by backend_builder)
    "issue_ids",            # str  JSON dict of Paperclip issue IDs per stage
}
```

`save_product_state` raises `ValueError` on unknown columns — this migration must land before
any agent that saves these fields.

---

## What Gets Removed / Changed

| File | Action |
|------|--------|
| `tools/code_gen_tools.py` | **Delete** `generate_fastapi_backend`, `generate_nextjs_frontend`, `generate_db_schema`. **Keep** `generate_code` and the Anthropic client — used by `pm_agent` and `architect_agent` for lightweight JSON generation that does not need sandbox execution. |
| `backend_builder_agent.py` | Remove `push_file`, `deploy_from_github`, `get_service_url`, `generate_code` imports |
| `frontend_builder_agent.py` | Remove `push_file`, `trigger_deploy`, `get_deployment_url`, `generate_code` imports |
| `qa_agent.py` | Remove direct `http_tools` curl calls |

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| DeerFlow unreachable | `call_deerflow_skill` raises; agent logs error + calls `release_issue` |
| Skill hits 5-iteration limit | DeerFlow reports failure; QA catches it, routes to bug_fix_agent |
| Deploy timeout (10 min) | Skill reports timeout; agent adds comment + escalates to human |
| Bug fix fails after 5 iterations | `bug_fix_agent` adds comment "Could not auto-fix: [error]", calls `complete_issue` with status failed |

---

## Scope Constraints

- **Single vertical only** — no routing by industry or product category for now
- **Vertical routing** can be added later as a pre-pm_agent router step
- **No UI/UX agent** for now — frontend_builder handles both UI and UX
- **No parallel builds** — pipeline is sequential per product

---

## Success Criteria

1. Human submits a product requirement → receives a live URL with no manual intervention
2. DeerFlow sandbox executes all code — nothing runs on the ADK host
3. Build self-corrects on errors (max 5 iterations per stage)
4. Human can report a bug → system fixes and redeploys autonomously
5. `call_deerflow_skill` is the only execution interface ADK builder agents need
