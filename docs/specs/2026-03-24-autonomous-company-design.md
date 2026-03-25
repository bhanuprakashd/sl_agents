# Autonomous Company — Idea to Shipped Product

**Date:** 2026-03-24
**Status:** Approved
**Scope:** Phase 1 — Product Engineering pipeline (idea → live URL)

---

## 1. Goal

Enable the existing ADK multi-agent system (Paperclip + DeerFlow + ADK) to accept a natural-language product requirement from a human and autonomously ship a working SaaS product, returning a live URL. After shipping, the existing GTM pipeline (marketing + sales agents) automatically activates with the product context.

---

## 2. Complete Flow

```
Human: "Build me a SaaS tool that does X"
    │
    ▼
company_orchestrator        (existing — new routing rule added)
    │  "ship product" intent detected
    ▼
product_orchestrator        (NEW)
    │
    ├── Step 1: pm_agent               → PRD + feature list + acceptance criteria
    ├── Step 2: architect_agent        → stack decision + architecture doc + file tree
    ├── Step 3: devops_agent           → GitHub repo + Vercel project + Railway project
    ├── Step 4: db_agent               → SQL schema + provision NeonDB or Supabase
    ├── Step 5: backend_builder_agent  → API code → push to GitHub → deploy to Railway
    ├── Step 6: frontend_builder_agent → Next.js UI → push to GitHub → deploy to Vercel
    ├── Step 7: qa_agent               → smoke test live URL → pass/fail report
    └── Step 8: product_orchestrator   → collects live_url → returns to company_orchestrator
    │
    ▼  (structured return detected by company_orchestrator instruction)
company_orchestrator routes to marketing_orchestrator with product context
```

---

## 3. New Agents

### 3.1 `product_orchestrator`
- **Role:** Top-level coordinator for the product engineering pipeline
- **Sits under:** `company_orchestrator` (alongside `sales_orchestrator`, `marketing_orchestrator`)
- **Triggered by:** Intent keywords — "build", "ship", "create a product", "make an app", "deploy"
- **Sub-agents:** `pm_agent`, `architect_agent`, `db_agent`, `backend_builder_agent`, `frontend_builder_agent`, `devops_agent`, `qa_agent`
- **Tools:** `save_product_state`, `recall_product_state` (new — see Section 6), `create_issue`, `add_comment` (from `paperclip_client.py`)
- **On complete:** Returns structured payload `{"status": "shipped", "product_id": ..., "live_url": ..., "product_name": ..., "one_liner": ..., "target_user": ..., "core_features": [...]}` — `company_orchestrator` instruction detects this and routes to `marketing_orchestrator`

### 3.2 `pm_agent` (Product Manager)
- **Role:** Converts raw requirement into a structured PRD
- **Output:** PRD with: product_name, one_liner, target_user, core_features (max 5 for v1), data_model outline, acceptance_criteria
- **Uses DeerFlow** via MCP `research_server` (`search_product_web`, `search_news`) for competitor research and trend validation
- **Constraint:** v1 scope must be shippable in one pipeline run — no scope creep

### 3.3 `architect_agent`
- **Role:** Picks tech stack from a deterministic decision table; generates architecture doc + file tree
- **No DeerFlow usage** — stack selection is rule-based, not search-based (eliminates non-determinism)
- **Stack decision logic:**

| Product Type | Frontend | Backend | Database |
|-------------|----------|---------|----------|
| Full-stack SaaS | Vercel (Next.js) | Next.js API routes | Supabase |
| API-heavy backend | Vercel (Next.js) | Railway (FastAPI) | NeonDB |
| Simple landing + auth | Vercel (Next.js) | Supabase Edge Functions | Supabase |
| Data-heavy app | Vercel (Next.js) | Railway (FastAPI) | NeonDB |

- **Stack selection criteria:**
  - Choose "Full-stack SaaS" if PRD includes a user-facing UI with CRUD operations
  - Choose "API-heavy backend" if PRD is primarily an API, webhook, or data processing service with minimal UI
  - Choose "Simple landing + auth" if PRD is a marketing site or waitlist with basic signup
  - Choose "Data-heavy app" if PRD involves analytics, dashboards, or large dataset queries
- **Output:** `architecture.md` + directory tree + file list (consumed by builder agents)

### 3.4 `devops_agent`
- **Role:** Creates GitHub repo, wires Vercel and Railway deployments, injects env vars
- **Runs:** Step 3 — before any builder agents, after architecture is defined
- **Responsibilities:**
  - Create GitHub repo (mono-repo: `/frontend` + `/backend` subdirs)
  - Create Vercel project linked to `/frontend`
  - Create Railway project linked to `/backend`
  - Inject `DATABASE_URL` env var into both Vercel and Railway after `db_agent` completes
- **Tools:** `github_tools.py`, `vercel_tools.py`, `railway_tools.py`
- **Output:** `repo_url`, `vercel_project_id`, `railway_project_id` — saved to product state

### 3.5 `db_agent` (Database Agent)
- **Role:** Generates SQL schema from PRD data model, provisions database
- **Targets:** NeonDB (via NeonDB API) or Supabase (via Supabase Management API), per architect decision
- **Output:** `connection_string` — injected as `DATABASE_URL` env var via `devops_agent` tools
- **Fallback:** If Supabase provisioning fails, retry once with NeonDB (and vice versa)
- **Constraint:** Free tier only — single database, no paid add-ons
- **Tools:** `neondb_tools.py`, `supabase_tools.py`

### 3.6 `backend_builder_agent`
- **Role:** Generates backend API code from PRD + architecture doc
- **Generates:** FastAPI (Railway) or Next.js API routes (Vercel), per architect decision
- **Uses:** `code_gen_tools.py` (Claude API `claude-sonnet-4-6`)
- **Output:** Code pushed to `/backend` in GitHub repo; Railway deploy triggered
- **Retry budget:** Max 3 deploy-level retries (independent of QA retries)

### 3.7 `frontend_builder_agent`
- **Role:** Generates Next.js UI from PRD + API spec
- **Stack:** Next.js 14, Tailwind CSS, shadcn/ui components
- **Uses:** `code_gen_tools.py` (Claude API `claude-sonnet-4-6`)
- **Output:** Code pushed to `/frontend` in GitHub repo; Vercel deploy triggered
- **Retry budget:** Max 3 deploy-level retries (independent of QA retries)

### 3.8 `qa_agent`
- **Role:** Smoke tests the live deployment
- **Tests:**
  1. HTTP GET on root URL → assert 200 OK
  2. HTTP GET on `/api/health` or `/health` → assert 200 OK
  3. Auth smoke test (if auth is in PRD): `POST /api/auth/register` with test payload `{"email": "test@test.com", "password": "Test1234!"}` → assert 200 or 201 response
- **On failure:** Reports specific failure to `product_orchestrator`; triggers rebuild of relevant agent (max 2 QA-triggered rebuilds, independent of that agent's deploy-level retries)
- **Total attempt budget per builder:** 3 deploy retries + 2 QA rebuilds = max 5 total attempts
- **All retries exhausted:** Save state to product memory, report partial completion + last error to human
- **Tools:** `http_tools.py`

---

## 4. Paperclip Integration

`product_orchestrator` creates all pipeline issues upfront via `create_issue`. Agents claim and complete them in sequence.

```
product_orchestrator
  │ creates 7 issues at pipeline start (pm, architect, devops, db, backend, frontend, qa)
  │
  ├── pm_agent            → checkout_issue("pm")       → add_comment(PRD)        → complete_issue
  ├── architect_agent     → checkout_issue("architect") → add_comment(arch_doc)   → complete_issue
  ├── devops_agent        → checkout_issue("devops")   → add_comment(repo_urls)   → complete_issue
  ├── db_agent            → checkout_issue("db")       → add_comment("db ready")  → complete_issue
  ├── backend_builder     → checkout_issue("backend")  → add_comment(deploy_url)  → complete_issue
  ├── frontend_builder    → checkout_issue("frontend") → add_comment(deploy_url)  → complete_issue
  └── qa_agent            → checkout_issue("qa")       → add_comment(qa_report)   → complete_issue
```

**`paperclip_client.py` additions required:**
- `create_issue(title: str, description: str) -> dict` — `POST /api/issues`

**Benefit:** Full pipeline visibility in Paperclip dashboard — each step's status, progress, and outputs are visible in real-time.

---

## 5. DeerFlow Integration

DeerFlow research is used by `pm_agent` only via the existing MCP `research_server`:

| Agent | DeerFlow Usage | Tool |
|-------|---------------|------|
| `pm_agent` | Search for competing products, validate demand | `search_product_web` (NEW) |
| `pm_agent` | Find recent news/trends in the product space | `search_news` (existing) |

**`architect_agent` does NOT use DeerFlow** — stack selection is deterministic from the decision table in Section 3.3. This avoids non-determinism cascading into the file tree and builder agents.

**New tool added to `mcp-servers/gtm/research_server.py`:**

```python
Tool(
    name="search_product_web",
    description="Search the web for SaaS products, GitHub repos, and tech stacks.",
    inputSchema={
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string"},
            "query_suffix": {"type": "string", "default": ""}
        }
    }
)
```

---

## 6. Tools (New)

| Tool File | Purpose | Used by |
|-----------|---------|---------|
| `tools/github_tools.py` | Create mono-repo, push files, create subdirs | `devops_agent`, `backend_builder_agent`, `frontend_builder_agent` |
| `tools/vercel_tools.py` | Create project, set root dir, deploy, inject env vars, get URL | `devops_agent`, `frontend_builder_agent` |
| `tools/railway_tools.py` | Create project, deploy service, inject env vars, get URL | `devops_agent`, `backend_builder_agent` |
| `tools/neondb_tools.py` | Create project, run migration, get connection string | `db_agent` |
| `tools/supabase_tools.py` | Create project, run migration, get connection string | `db_agent` |
| `tools/code_gen_tools.py` | Claude API wrapper for code generation | `backend_builder_agent`, `frontend_builder_agent` |
| `tools/http_tools.py` | Smoke test HTTP endpoints (GET, status check) | `qa_agent` |
| `tools/product_memory_tools.py` | Save/recall product pipeline state (separate from GTM memory) | `product_orchestrator`, all pipeline agents |

**Existing tools reused:**
- `tools/paperclip_client.py` — `checkout_issue`, `complete_issue`, `add_comment` (+ new `create_issue`)
- `tools/memory_tools.py` — unchanged; used only by GTM agents

**MCP servers extended:**
- `mcp-servers/gtm/research_server.py` — add `search_product_web` tool

---

## 7. Product Memory (Separate from GTM Memory)

The product pipeline uses its own memory table to avoid polluting the GTM memory store (which uses `company_name` as the primary key — incompatible with `product_id`).

**New file:** `tools/product_memory_tools.py`

```
Table: product_pipeline_state
  product_id      TEXT PRIMARY KEY  (UUID, generated by product_orchestrator at start)
  product_name    TEXT
  status          TEXT              (running | shipped | failed)
  prd             TEXT              (JSON)
  architecture    TEXT              (JSON)
  repo_url        TEXT
  database_url    TEXT              (written by db_agent; read by devops_agent for env var injection)
  backend_url     TEXT
  frontend_url    TEXT
  qa_report       TEXT
  created_at      DATETIME
  updated_at      DATETIME
```

**`DATABASE_URL` handoff flow:**
1. `db_agent` provisions the database and calls `save_product_state(product_id, database_url=connection_string)`
2. `devops_agent` calls `recall_product_state(product_id)` to retrieve `database_url`
3. `devops_agent` injects it as `DATABASE_URL` env var into both Vercel and Railway projects via their respective APIs

Functions: `save_product_state(product_id, **fields)`, `recall_product_state(product_id) -> dict`

`product_id` is a UUID generated by `product_orchestrator` at pipeline start and passed to all sub-agents.

---

## 8. Data Flow

```
Requirement (string)
    → pm_agent              → PRD (saved to product_pipeline_state)
    → architect_agent       → architecture.md + file_tree (saved to product_pipeline_state)
    → devops_agent          → repo_url, vercel_project_id, railway_project_id (saved)
    → db_agent              → DATABASE_URL injected via devops_agent tools (not stored in memory)
    → backend_builder_agent → backend_url (saved to product_pipeline_state)
    → frontend_builder_agent→ frontend_url (saved to product_pipeline_state)
    → qa_agent              → qa_report (saved to product_pipeline_state)
    → product_orchestrator  → returns structured payload to company_orchestrator
```

---

## 9. Error Handling

| Failure Point | Response |
|--------------|---------|
| PRD generation fails | Retry once; if still fails, ask human to clarify requirement |
| Stack decision ambiguous | Default to: Vercel + Next.js API routes + Supabase |
| DB provisioning fails (Supabase) | Retry once with NeonDB |
| DB provisioning fails (NeonDB) | Report failure to human |
| Build fails | Return error to builder agent with message; max 3 deploy retries |
| Deploy fails | Return platform error; max 3 deploy retries |
| QA fails | Trigger rebuild; max 2 QA-triggered rebuilds per builder |
| Railway credit exhausted | Pause pipeline; notify human to add billing or switch to Render |
| All retries exhausted | Save state to product memory, report partial progress + last error to human |

---

## 10. Budget Constraints

- **Platforms (free tiers):** Vercel Hobby, Railway $5 free credit (~2 pipeline runs; see note), Supabase Free, NeonDB Free
- **Railway note:** $5 is a one-time trial credit, not an ongoing free tier. After ~2 runs, Railway requires paid plan. Alternative: Render (genuine free tier for web services). The error handler above catches billing failures.
- **LLM usage:** `claude-haiku-4-5` for PM/QA tasks, `claude-sonnet-4-6` for code generation only
- **No paid APIs or add-ons in Phase 1**
- Budget middleware (Phase 2) will enforce per-pipeline cost limits

---

## 11. GTM Handoff (Post-Ship)

`product_orchestrator` returns a structured dict to `company_orchestrator`:

```python
{
    "status": "shipped",
    "product_id": "<uuid>",
    "live_url": "https://...",
    "product_name": "...",
    "one_liner": "...",
    "target_user": "...",
    "core_features": ["...", "...", "..."]
}
```

`company_orchestrator`'s instruction detects `status == "shipped"` and routes to `marketing_orchestrator` with this context to begin the GTM sequence (Step 1: audience builder).

---

## 12. Out of Scope (Phase 1)

- Custom domains
- Auth/payments beyond basic scaffold
- CI/CD pipelines
- Monitoring / alerting
- Budget middleware (Phase 2)
- Supermemory integration (Phase 2 — replaces SQLite memory with semantic memory engine)
- Full autonomous company (other departments)

---

## 13. Files to Create / Modify

```
aass_agents/
├── agents/
│   ├── product_orchestrator_agent.py    NEW
│   ├── pm_agent.py                      NEW
│   ├── architect_agent.py               NEW
│   ├── db_agent.py                      NEW
│   ├── backend_builder_agent.py         NEW
│   ├── frontend_builder_agent.py        NEW
│   ├── devops_agent.py                  NEW
│   └── qa_agent.py                      NEW
├── tools/
│   ├── github_tools.py                  NEW
│   ├── vercel_tools.py                  NEW
│   ├── railway_tools.py                 NEW
│   ├── neondb_tools.py                  NEW
│   ├── supabase_tools.py                NEW
│   ├── code_gen_tools.py                NEW
│   ├── http_tools.py                    NEW
│   ├── product_memory_tools.py          NEW
│   └── paperclip_client.py              MODIFY — add create_issue()
├── agents/company_orchestrator_agent.py MODIFY — add "ship product" routing + GTM handoff detection
mcp-servers/gtm/research_server.py       MODIFY — add search_product_web tool
```
