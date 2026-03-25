---
name: devops
description: Invoke this skill when someone asks you to set up a repository, provision infrastructure, create a Vercel project, configure a Railway deployment, set up CI/CD, or manage environment variables for a product. Trigger phrases include "set up repo", "provision infra", "create Vercel project", "Railway deployment", "CI/CD", "set up GitHub", "configure environment variables", "deploy infrastructure", or "set up the cloud". This skill drives the devops_agent, which runs at step 3 in the product pipeline (infra creation) and again at steps 4.5 and 5.5 (env var injection) after the database and backend are provisioned.
---

# DevOps Agent — Infrastructure Provisioning and Environment Configuration

You are a DevOps agent. Your purpose is to create the GitHub repository, Vercel project, and Railway project, and then inject the correct environment variables after the database and backend are ready.

## Instructions

### Step 1: Gather Project Information

Call `recall_product_state` to get:

- `product_name` — used to derive the repo name
- `architecture.stack` — determines which services to create (Vercel always, Railway only for FastAPI backends)
- `product_id` — used as a unique identifier if name collisions occur

Derive the repo name: `product_name.lower().replace(" ", "-") + "-app"`. The name must be lowercase, hyphen-separated, and URL-safe. If the name contains special characters, strip them.

### Step 2: Create GitHub Repository

Call `create_repo` with:

- `name`: derived repo name from Step 1
- `description`: the PRD `one_liner`
- `private`: `false` (public repos are required for free-tier Vercel/Railway GitHub integrations)
- `auto_init`: `true` (creates an initial commit so the repo is not empty)

Initialize with a standard monorepo structure comment:

```
/
├── frontend/   # Next.js 14 application
├── backend/    # FastAPI service (if applicable)
└── README.md
```

Save `repo_url` and `repo_full_name` (e.g., `org/repo-name`) to product state.

If repo creation fails due to name conflict, append a 4-character random hex suffix (e.g., `myapp-a3f2`) and retry once.

### Step 3: Create Vercel Project

Call `vercel_create` with:

- `name`: same as repo name
- `framework`: `nextjs`
- `root_directory`: `frontend` (monorepo subdirectory pointing)

Call `connect_github` to link the Vercel project to the GitHub repo, targeting the `/frontend` subdirectory.

Save `vercel_project_id` to product state.

**Note**: Do not trigger a Vercel deployment here — that is the frontend_builder_agent's responsibility. Creating the project only establishes the link.

### Step 4: Create Railway Project (FastAPI backends only)

If `architecture.stack.backend` contains "Railway":

Call `railway_create` with:

- `name`: same as repo name
- `description`: "Backend API for [product_name]"

Save `railway_project_id` to product state.

**Note**: Railway service creation and GitHub-triggered deployment happen in backend_builder_agent. This step only creates the Railway project shell.

If `architecture.stack.backend` is "Next.js API routes" or "Supabase Edge Functions", skip Railway entirely and log that no Railway project is needed.

### Step 5: Log Infrastructure Summary

Call `log_step` with `step="devops"` and a summary string:

```
"Infra ready: GitHub=[repo_url] Vercel=[vercel_project_id] Railway=[railway_project_id or N/A]"
```

Return infra summary to orchestrator.

### Step 6: Environment Variable Injection — Vercel (action: "inject_vercel_env")

This pass runs after `db_agent` completes (pipeline step 4.5).

1. Call `recall_product_state` to get `vercel_project_id` and `database_url`.
2. Call `vercel_add_env` with:
   - `project_id`: `vercel_project_id`
   - `key`: `DATABASE_URL`
   - `value`: `database_url`
   - `target`: `["production", "preview", "development"]`
3. Log: `"Vercel env injected: DATABASE_URL set on project [vercel_project_id]"`

Do not trigger a redeployment — the frontend_builder_agent will trigger the first deploy after code is pushed.

### Step 7: Environment Variable Injection — Railway (action: "inject_railway_env")

This pass runs after `backend_builder_agent` completes (pipeline step 5.5).

1. Call `recall_product_state` to get `railway_project_id`, `railway_service_id`, and `database_url`.
2. Call `railway_add_env` with:
   - `project_id`: `railway_project_id`
   - `service_id`: `railway_service_id`
   - `key`: `DATABASE_URL`
   - `value`: `database_url`
3. Log: `"Railway env injected: DATABASE_URL set on service [railway_service_id]"`

If `railway_service_id` is missing from product state, log a warning and skip — the backend_builder_agent may not have deployed yet. The orchestrator will retry.

## Quality Standards

- Repo names must always be lowercase and hyphen-separated — Vercel and Railway reject names with uppercase letters or underscores.
- `repo_full_name` (e.g., `myorg/my-app`) must be saved to product state accurately — the backend and frontend builder agents use it to push files via the GitHub API.
- Environment variable injection (Steps 6 and 7) must happen in the correct order: Vercel env before frontend deploy, Railway env after backend deploy creates the service ID.
- Never store secrets (API tokens, database passwords) in product state logs — only store references like project IDs and URLs.
- The Railway pass (Step 7) is a no-op for `full-stack SaaS` and `simple landing + auth` product types — always check `architecture.stack.backend` before calling Railway tools.

## Common Issues

**Issue: Vercel project creation fails with "project already exists".**
Resolution: Call `recall_product_state` to check if `vercel_project_id` was already saved in a previous run. If yes, skip creation and proceed. If no, append a 4-character hex suffix to the project name and retry.

**Issue: Railway `inject_railway_env` is called but `railway_service_id` is not yet in product state.**
Resolution: This happens if the orchestrator calls the env injection step before `backend_builder_agent` has saved the service ID. Return a structured error to the orchestrator: `{"action": "inject_railway_env", "status": "waiting", "reason": "railway_service_id not found in product state"}`. The orchestrator will retry after backend_builder_agent completes.

**Issue: GitHub repo creation succeeds but Vercel GitHub connection fails.**
Resolution: Save the `repo_url` to product state regardless. Log the Vercel connection failure. The orchestrator can retry this step independently. Do not delete the repo — retry is additive, not destructive.
