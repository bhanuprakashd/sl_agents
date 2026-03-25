# Autonomous Company — Idea to Shipped Product Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept a natural-language product requirement and autonomously ship a working SaaS product, returning a live URL, then trigger the existing GTM pipeline.

**Architecture:** A `product_orchestrator` agent (new) sits alongside `sales_orchestrator` and `marketing_orchestrator` under `company_orchestrator`. It runs an 8-step pipeline: PM → Architect → DevOps → DB → Backend → Frontend → QA → Return URL. Each step is tracked as a Paperclip issue. State is stored in a dedicated SQLite table (`product_pipeline_state`) separate from the GTM memory store.

**Tech Stack:** Google ADK, Python 3.11+, SQLite, Paperclip REST API, GitHub API, Vercel API, Railway API, NeonDB API, Supabase Management API, Anthropic Claude API (claude-sonnet-4-6 for codegen, claude-haiku-4-5 for PM/QA), Next.js 14 + Tailwind + shadcn/ui, FastAPI

---

## File Map

```
aass_agents/
├── tools/
│   ├── product_memory_tools.py     NEW  — product_pipeline_state SQLite table
│   ├── github_tools.py             NEW  — create repo, push files
│   ├── vercel_tools.py             NEW  — create project, deploy, env vars
│   ├── railway_tools.py            NEW  — create project, deploy, env vars
│   ├── neondb_tools.py             NEW  — provision DB, run migration
│   ├── supabase_tools.py           NEW  — provision DB, run migration
│   ├── code_gen_tools.py           NEW  — Claude API code generation wrapper
│   ├── http_tools.py               NEW  — smoke test HTTP endpoints
│   └── paperclip_client.py         MODIFY — add create_issue()
├── agents/
│   ├── pm_agent.py                 NEW  — requirement → PRD
│   ├── architect_agent.py          NEW  — PRD → stack + file tree
│   ├── devops_agent.py             NEW  — provision GitHub + Vercel + Railway
│   ├── db_agent.py                 NEW  — provision database + schema
│   ├── backend_builder_agent.py    NEW  — generate + deploy backend code
│   ├── frontend_builder_agent.py   NEW  — generate + deploy frontend code
│   ├── qa_agent.py                 NEW  — smoke test live URL
│   ├── product_orchestrator_agent.py NEW — coordinate pipeline
│   └── company_orchestrator_agent.py MODIFY — add product routing + GTM handoff
mcp-servers/gtm/research_server.py  MODIFY — add search_product_web tool
tests/
├── test_product_memory_tools.py    NEW
├── test_github_tools.py            NEW
├── test_code_gen_tools.py          NEW
└── test_http_tools.py              NEW
```

---

## Task 1: Product Memory Store

**Files:**
- Create: `aass_agents/tools/product_memory_tools.py`
- Create: `aass_agents/tests/test_product_memory_tools.py`

- [ ] **Step 1: Write the failing tests**

```python
# aass_agents/tests/test_product_memory_tools.py
import pytest
import uuid
from tools.product_memory_tools import (
    save_product_state,
    recall_product_state,
    init_product_db,
)

@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test_products.db")
    monkeypatch.setenv("PRODUCT_DB_PATH", db)
    init_product_db()

def test_save_and_recall_basic():
    pid = str(uuid.uuid4())
    save_product_state(pid, product_name="TestApp", status="running")
    state = recall_product_state(pid)
    assert state["product_name"] == "TestApp"
    assert state["status"] == "running"

def test_partial_update():
    pid = str(uuid.uuid4())
    save_product_state(pid, product_name="App", status="running")
    save_product_state(pid, backend_url="https://api.example.com")
    state = recall_product_state(pid)
    assert state["product_name"] == "App"
    assert state["backend_url"] == "https://api.example.com"

def test_recall_missing_returns_none():
    state = recall_product_state("nonexistent-id")
    assert state is None

def test_save_json_fields():
    pid = str(uuid.uuid4())
    prd = {"product_name": "X", "features": ["f1", "f2"]}
    save_product_state(pid, prd=prd)
    state = recall_product_state(pid)
    assert state["prd"]["features"] == ["f1", "f2"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/bhanu.prakash/Documents/claude_works/sl_agents/aass_agents
python -m pytest tests/test_product_memory_tools.py -v
```
Expected: `ModuleNotFoundError: No module named 'tools.product_memory_tools'`

- [ ] **Step 3: Implement product_memory_tools.py**

```python
# aass_agents/tools/product_memory_tools.py
"""
Product pipeline state store — separate from GTM memory.
Uses its own SQLite table keyed by product_id (UUID).
"""
import json
import os
import sqlite3
from datetime import datetime
from typing import Any

_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "product_pipeline.db")


def _db_path() -> str:
    return os.environ.get("PRODUCT_DB_PATH", _DEFAULT_DB)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_product_db() -> None:
    """Create the product_pipeline_state table if it does not exist."""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS product_pipeline_state (
                product_id   TEXT PRIMARY KEY,
                product_name TEXT,
                status       TEXT DEFAULT 'running',
                prd          TEXT,
                architecture TEXT,
                repo_url     TEXT,
                database_url TEXT,
                backend_url  TEXT,
                frontend_url TEXT,
                qa_report    TEXT,
                created_at   TEXT,
                updated_at   TEXT
            )
        """)


def save_product_state(product_id: str, **fields: Any) -> None:
    """
    Upsert product pipeline state.
    JSON-serializes dict/list values automatically.
    """
    init_product_db()
    now = datetime.utcnow().isoformat()
    serialized = {
        k: json.dumps(v) if isinstance(v, (dict, list)) else v
        for k, v in fields.items()
    }
    with _conn() as conn:
        existing = conn.execute(
            "SELECT product_id FROM product_pipeline_state WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        if existing is None:
            serialized.setdefault("status", "running")
            cols = ["product_id", "created_at", "updated_at"] + list(serialized.keys())
            vals = [product_id, now, now] + list(serialized.values())
            placeholders = ",".join("?" * len(cols))
            conn.execute(
                f"INSERT INTO product_pipeline_state ({','.join(cols)}) VALUES ({placeholders})",
                vals,
            )
        else:
            set_clause = ", ".join(f"{k} = ?" for k in serialized)
            vals = list(serialized.values()) + [now, product_id]
            conn.execute(
                f"UPDATE product_pipeline_state SET {set_clause}, updated_at = ? WHERE product_id = ?",
                vals,
            )


def recall_product_state(product_id: str) -> dict | None:
    """Return full product state dict, or None if not found."""
    init_product_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM product_pipeline_state WHERE product_id = ?",
            (product_id,),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    for key in ("prd", "architecture", "qa_report"):
        if result.get(key):
            try:
                result[key] = json.loads(result[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_product_memory_tools.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add tools/product_memory_tools.py tests/test_product_memory_tools.py
git commit -m "feat: add product pipeline memory store"
```

---

## Task 2: Paperclip + Research Server Extensions

**Files:**
- Modify: `aass_agents/tools/paperclip_client.py`
- Modify: `mcp-servers/gtm/research_server.py`

- [ ] **Step 1: Add create_issue to paperclip_client.py**

Open `aass_agents/tools/paperclip_client.py` and append after `get_current_agent`:

```python
def create_issue(title: str, description: str, project_id: str | None = None) -> dict:
    """Create a new issue in Paperclip and return the created issue record."""
    payload: dict = {"title": title, "description": description, "status": "todo"}
    if project_id:
        payload["projectId"] = project_id
    with _client() as c:
        r = c.post("/api/issues", json=payload)
        r.raise_for_status()
        return r.json()
```

- [ ] **Step 2: Add search_product_web to research_server.py**

In `mcp-servers/gtm/research_server.py`, add to `list_tools()`:

```python
Tool(
    name="search_product_web",
    description="Search the web for SaaS products, GitHub repos, and tech stacks.",
    inputSchema={
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string"},
            "query_suffix": {"type": "string", "default": ""},
        },
    },
),
```

And add to `call_tool()`:

```python
elif name == "search_product_web":
    from tools.research_tools import search_company_web
    result = search_company_web(
        arguments["query"],
        arguments.get("query_suffix", ""),
    )
```

- [ ] **Step 3: Verify research server still imports cleanly**

```bash
cd /Users/bhanu.prakash/Documents/claude_works/sl_agents
python -c "import sys; sys.path.insert(0, 'aass_agents'); from mcp_servers.gtm import research_server; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add aass_agents/tools/paperclip_client.py mcp-servers/gtm/research_server.py
git commit -m "feat: add create_issue to paperclip client and search_product_web to research MCP"
```

---

## Task 3: Infrastructure Tools (GitHub, Vercel, Railway)

**Files:**
- Create: `aass_agents/tools/github_tools.py`
- Create: `aass_agents/tools/vercel_tools.py`
- Create: `aass_agents/tools/railway_tools.py`

These tools call external APIs. Tests mock the HTTP layer.

- [ ] **Step 1: Write github_tools.py**

```python
# aass_agents/tools/github_tools.py
"""
GitHub API tools for creating repos and pushing files.
Requires: GITHUB_TOKEN env var (personal access token with repo scope)
"""
import base64
import os
import httpx

_GH_API = "https://api.github.com"
_TIMEOUT = 30


def _headers() -> dict:
    token = os.environ["GITHUB_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def create_repo(name: str, description: str = "", private: bool = False) -> dict:
    """Create a new GitHub repo. Returns repo info including clone_url and html_url."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_GH_API}/user/repos",
            headers=_headers(),
            json={"name": name, "description": description, "private": private, "auto_init": True},
        )
        r.raise_for_status()
        return r.json()


def push_file(repo_full_name: str, path: str, content: str, message: str, branch: str = "main") -> dict:
    """
    Create or update a file in the repo.
    repo_full_name: "owner/repo"
    content: raw string (will be base64-encoded)
    """
    encoded = base64.b64encode(content.encode()).decode()
    url = f"{_GH_API}/repos/{repo_full_name}/contents/{path}"
    # Check if file exists to get sha for update
    with httpx.Client(timeout=_TIMEOUT) as c:
        existing = c.get(url, headers=_headers())
        payload: dict = {"message": message, "content": encoded, "branch": branch}
        if existing.status_code == 200:
            payload["sha"] = existing.json()["sha"]
        r = c.put(url, headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()


def get_repo(repo_full_name: str) -> dict:
    """Return repo info."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.get(f"{_GH_API}/repos/{repo_full_name}", headers=_headers())
        r.raise_for_status()
        return r.json()
```

- [ ] **Step 2: Write vercel_tools.py**

```python
# aass_agents/tools/vercel_tools.py
"""
Vercel API tools for creating projects and deploying.
Requires: VERCEL_TOKEN env var
"""
import os
import httpx

_VERCEL_API = "https://api.vercel.com"
_TIMEOUT = 60


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['VERCEL_TOKEN']}"}


def create_project(name: str, framework: str = "nextjs", root_directory: str = "frontend") -> dict:
    """Create a Vercel project. Returns project id and name."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_VERCEL_API}/v9/projects",
            headers=_headers(),
            json={"name": name, "framework": framework, "rootDirectory": root_directory},
        )
        r.raise_for_status()
        return r.json()


def add_env_var(project_id: str, key: str, value: str, target: list[str] | None = None) -> dict:
    """Add an environment variable to a Vercel project."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_VERCEL_API}/v9/projects/{project_id}/env",
            headers=_headers(),
            json={
                "key": key,
                "value": value,
                "type": "encrypted",
                "target": target or ["production", "preview", "development"],
            },
        )
        r.raise_for_status()
        return r.json()


def connect_github(project_id: str, repo_full_name: str) -> dict:
    """Link a GitHub repo to the Vercel project."""
    owner, repo = repo_full_name.split("/", 1)
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.patch(
            f"{_VERCEL_API}/v9/projects/{project_id}",
            headers=_headers(),
            json={"link": {"type": "github", "org": owner, "repo": repo}},
        )
        r.raise_for_status()
        return r.json()


def trigger_deploy(project_id: str) -> dict:
    """Trigger a new deployment and return deployment info including url."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_VERCEL_API}/v13/deployments",
            headers=_headers(),
            json={"name": project_id, "gitSource": {"type": "github", "ref": "main"}},
        )
        r.raise_for_status()
        return r.json()


def get_deployment_url(project_id: str) -> str:
    """Return the latest production deployment URL."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.get(
            f"{_VERCEL_API}/v6/deployments",
            headers=_headers(),
            params={"projectId": project_id, "limit": 1, "state": "READY"},
        )
        r.raise_for_status()
        deployments = r.json().get("deployments", [])
        if not deployments:
            return ""
        return f"https://{deployments[0]['url']}"
```

- [ ] **Step 3: Write railway_tools.py**

```python
# aass_agents/tools/railway_tools.py
"""
Railway GraphQL API tools for creating projects and deploying.
Requires: RAILWAY_TOKEN env var
"""
import os
import httpx

_RAILWAY_API = "https://backboard.railway.app/graphql/v2"
_TIMEOUT = 60


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['RAILWAY_TOKEN']}"}


def _gql(query: str, variables: dict | None = None) -> dict:
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            _RAILWAY_API,
            headers=_headers(),
            json={"query": query, "variables": variables or {}},
        )
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            raise RuntimeError(f"Railway GraphQL error: {data['errors']}")
        return data["data"]


def create_project(name: str) -> dict:
    """Create a Railway project. Returns project id."""
    query = """
    mutation ProjectCreate($input: ProjectCreateInput!) {
      projectCreate(input: $input) { id name }
    }
    """
    return _gql(query, {"input": {"name": name}})["projectCreate"]


def add_env_var(project_id: str, service_id: str, key: str, value: str) -> dict:
    """Add an environment variable to a Railway service."""
    query = """
    mutation VariableUpsert($input: VariableUpsertInput!) {
      variableUpsert(input: $input)
    }
    """
    return _gql(query, {"input": {"projectId": project_id, "serviceId": service_id,
                                   "environmentId": None, "name": key, "value": value}})


def deploy_from_github(project_id: str, repo_full_name: str, branch: str = "main") -> dict:
    """Connect a GitHub repo and deploy. Returns service info."""
    query = """
    mutation ServiceCreate($input: ServiceCreateInput!) {
      serviceCreate(input: $input) { id name }
    }
    """
    return _gql(query, {"input": {
        "projectId": project_id,
        "source": {"repo": repo_full_name, "branch": branch},
    }})["serviceCreate"]


def get_service_url(project_id: str, service_id: str) -> str:
    """Return the public URL for a Railway service."""
    query = """
    query ServiceDomains($projectId: String!, $serviceId: String!) {
      service(id: $serviceId) {
        domains { serviceDomains { domain } }
      }
    }
    """
    data = _gql(query, {"projectId": project_id, "serviceId": service_id})
    domains = data["service"]["domains"]["serviceDomains"]
    if not domains:
        return ""
    return f"https://{domains[0]['domain']}"
```

- [ ] **Step 4: Add env vars to .env.example**

Append to `aass_agents/.env.example`:

```
# Product Engineering Pipeline
GITHUB_TOKEN=your_github_personal_access_token
VERCEL_TOKEN=your_vercel_api_token
RAILWAY_TOKEN=your_railway_api_token
NEONDB_API_KEY=your_neondb_api_key
SUPABASE_ACCESS_TOKEN=your_supabase_access_token
ANTHROPIC_API_KEY=your_anthropic_api_key
```

- [ ] **Step 5: Commit**

```bash
git add tools/github_tools.py tools/vercel_tools.py tools/railway_tools.py .env.example
git commit -m "feat: add GitHub, Vercel, Railway infrastructure tools"
```

---

## Task 4: Database Tools (NeonDB + Supabase)

**Files:**
- Create: `aass_agents/tools/neondb_tools.py`
- Create: `aass_agents/tools/supabase_tools.py`

- [ ] **Step 1: Write neondb_tools.py**

```python
# aass_agents/tools/neondb_tools.py
"""
NeonDB API tools for provisioning a serverless Postgres database.
Requires: NEONDB_API_KEY env var
Docs: https://api-docs.neon.tech/reference/getting-started-with-neon-api
"""
import os
import httpx

_NEON_API = "https://console.neon.tech/api/v2"
_TIMEOUT = 60


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['NEONDB_API_KEY']}",
        "Content-Type": "application/json",
    }


def create_project(name: str) -> dict:
    """Create a new NeonDB project. Returns project info including connection_uris."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_NEON_API}/projects",
            headers=_headers(),
            json={"project": {"name": name, "pg_version": 16}},
        )
        r.raise_for_status()
        return r.json()


def get_connection_string(project: dict) -> str:
    """Extract the primary connection URI from a create_project response."""
    uris = project.get("connection_uris", [])
    if not uris:
        raise ValueError("No connection URIs in NeonDB project response")
    return uris[0]["connection_uri"]


def run_sql(project_id: str, branch_id: str, sql: str) -> dict:
    """Run raw SQL against a NeonDB branch (for schema migrations)."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_NEON_API}/projects/{project_id}/query",
            headers=_headers(),
            json={"query": sql, "branch_id": branch_id},
        )
        r.raise_for_status()
        return r.json()
```

- [ ] **Step 2: Write supabase_tools.py**

```python
# aass_agents/tools/supabase_tools.py
"""
Supabase Management API tools for provisioning a project and running migrations.
Requires: SUPABASE_ACCESS_TOKEN env var
Docs: https://supabase.com/docs/reference/api/introduction
"""
import os
import time
import httpx

_SUPABASE_API = "https://api.supabase.com/v1"
_TIMEOUT = 120  # project provisioning can take up to 60s


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['SUPABASE_ACCESS_TOKEN']}",
        "Content-Type": "application/json",
    }


def create_project(name: str, org_id: str, db_pass: str, region: str = "us-east-1") -> dict:
    """Create a Supabase project. Polls until active. Returns project info."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_SUPABASE_API}/projects",
            headers=_headers(),
            json={"name": name, "organization_id": org_id,
                  "db_pass": db_pass, "region": region, "plan": "free"},
        )
        r.raise_for_status()
        project = r.json()
        project_id = project["id"]
        # Poll until active (max 120s)
        for _ in range(24):
            time.sleep(5)
            status = c.get(f"{_SUPABASE_API}/projects/{project_id}", headers=_headers())
            if status.json().get("status") == "ACTIVE_HEALTHY":
                return status.json()
        raise TimeoutError(f"Supabase project {project_id} did not become active in 120s")


def get_connection_string(project: dict, db_pass: str) -> str:
    """Build a Postgres connection string from project info."""
    ref = project["id"]
    return f"postgresql://postgres:{db_pass}@db.{ref}.supabase.co:5432/postgres"


def run_sql(project_id: str, sql: str) -> dict:
    """Run SQL against a Supabase project (for schema migrations)."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_SUPABASE_API}/projects/{project_id}/database/query",
            headers=_headers(),
            json={"query": sql},
        )
        r.raise_for_status()
        return r.json()
```

- [ ] **Step 3: Commit**

```bash
git add tools/neondb_tools.py tools/supabase_tools.py
git commit -m "feat: add NeonDB and Supabase database provisioning tools"
```

---

## Task 5: Code Generation + HTTP Tools

**Files:**
- Create: `aass_agents/tools/code_gen_tools.py`
- Create: `aass_agents/tools/http_tools.py`
- Create: `aass_agents/tests/test_code_gen_tools.py`
- Create: `aass_agents/tests/test_http_tools.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_code_gen_tools.py
import pytest
from unittest.mock import patch, MagicMock

def test_generate_code_returns_string():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="def hello():\n    return 'world'")]
    with patch("tools.code_gen_tools._client") as mock_client:
        mock_client.return_value.__enter__.return_value.messages.create.return_value = mock_response
        from tools.code_gen_tools import generate_code
        result = generate_code("write a hello function", language="python")
        assert "def hello" in result

def test_generate_code_strips_markdown_fences():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="```python\ndef hello(): pass\n```")]
    with patch("tools.code_gen_tools._client") as mock_client:
        mock_client.return_value.__enter__.return_value.messages.create.return_value = mock_response
        from tools.code_gen_tools import generate_code
        result = generate_code("write hello", language="python")
        assert not result.startswith("```")
```

```python
# tests/test_http_tools.py
import pytest
from unittest.mock import patch, MagicMock

def test_smoke_test_passes_on_200():
    mock_resp = MagicMock(status_code=200)
    with patch("httpx.get", return_value=mock_resp):
        from tools.http_tools import smoke_test
        result = smoke_test("https://example.com")
        assert result["passed"] is True

def test_smoke_test_fails_on_500():
    mock_resp = MagicMock(status_code=500)
    with patch("httpx.get", return_value=mock_resp):
        from tools.http_tools import smoke_test
        result = smoke_test("https://example.com")
        assert result["passed"] is False
        assert "500" in result["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_code_gen_tools.py tests/test_http_tools.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write code_gen_tools.py**

```python
# aass_agents/tools/code_gen_tools.py
"""
Claude API wrapper for code generation.
Uses claude-sonnet-4-6 for code, claude-haiku-4-5 for lightweight tasks.
Requires: ANTHROPIC_API_KEY env var
"""
import os
import re
import anthropic

_SONNET = "claude-sonnet-4-6"
_HAIKU = "claude-haiku-4-5-20251001"


def _client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def generate_code(prompt: str, language: str = "python", context: str = "") -> str:
    """
    Generate code for a given prompt. Returns clean code string (no markdown fences).
    Uses claude-sonnet-4-6.
    """
    system = (
        f"You are an expert {language} developer. "
        "Return ONLY the code — no explanations, no markdown code fences, no comments unless essential."
    )
    messages = []
    if context:
        messages.append({"role": "user", "content": f"Context:\n{context}"})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content": prompt})

    with _client() as c:
        response = c.messages.create(
            model=_SONNET,
            max_tokens=8192,
            system=system,
            messages=messages,
        )
    raw = response.content[0].text
    return _strip_fences(raw)


def generate_json(prompt: str, context: str = "") -> str:
    """Generate a JSON response. Uses claude-haiku-4-5 for cost efficiency."""
    system = "Return ONLY valid JSON. No explanations, no markdown."
    messages = []
    if context:
        messages.append({"role": "user", "content": f"Context:\n{context}"})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content": prompt})

    with _client() as c:
        response = c.messages.create(
            model=_HAIKU,
            max_tokens=4096,
            system=system,
            messages=messages,
        )
    return response.content[0].text


def _strip_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = re.sub(r"^```\w*\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text.strip())
    return text.strip()
```

- [ ] **Step 4: Write http_tools.py**

```python
# aass_agents/tools/http_tools.py
"""
HTTP smoke test tools for QA agent.
"""
import httpx

_TIMEOUT = 15


def smoke_test(url: str) -> dict:
    """
    GET the URL and return {"passed": bool, "status_code": int, "error": str | None}.
    """
    try:
        r = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)
        passed = 200 <= r.status_code < 300
        return {
            "passed": passed,
            "status_code": r.status_code,
            "error": None if passed else f"HTTP {r.status_code}",
        }
    except Exception as e:
        return {"passed": False, "status_code": 0, "error": str(e)}


def health_check(base_url: str) -> dict:
    """Try /api/health then /health. Returns first passing result or last failure."""
    for path in ("/api/health", "/health"):
        result = smoke_test(f"{base_url.rstrip('/')}{path}")
        if result["passed"]:
            return result
    return result


def auth_smoke_test(base_url: str) -> dict:
    """
    POST /api/auth/register with a test account.
    Returns {"passed": bool, "status_code": int, "error": str | None}.
    """
    url = f"{base_url.rstrip('/')}/api/auth/register"
    payload = {"email": "smoketest@test.com", "password": "Test1234!"}
    try:
        r = httpx.post(url, json=payload, timeout=_TIMEOUT)
        passed = r.status_code in (200, 201, 409)  # 409 = already exists (also fine)
        return {
            "passed": passed,
            "status_code": r.status_code,
            "error": None if passed else f"HTTP {r.status_code}: {r.text[:200]}",
        }
    except Exception as e:
        return {"passed": False, "status_code": 0, "error": str(e)}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_code_gen_tools.py tests/test_http_tools.py -v
```
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add tools/code_gen_tools.py tools/http_tools.py tests/test_code_gen_tools.py tests/test_http_tools.py
git commit -m "feat: add code generation and HTTP smoke test tools"
```

---

## Task 6: PM Agent + Architect Agent

**Files:**
- Create: `aass_agents/agents/pm_agent.py`
- Create: `aass_agents/agents/architect_agent.py`

- [ ] **Step 1: Write pm_agent.py**

```python
# aass_agents/agents/pm_agent.py
"""
PM Agent — converts raw requirement into a structured PRD.
Uses DeerFlow (via MCP research_server) for competitor research.
Uses claude-haiku-4-5 via ADK (cost-efficient for structured JSON output).
"""
import os
from google.adk.agents import Agent
from tools.paperclip_client import checkout_issue, complete_issue, add_comment
from tools.product_memory_tools import save_product_state, recall_product_state

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are a Product Manager agent. Your job is to convert a raw product requirement into a
structured PRD (Product Requirements Document).

## Your Process

1. Call `checkout_issue` with the issue_id for the "pm" step (provided in context)
2. Use `search_product_web` and `search_news` to research competitors and market trends
3. Generate a PRD as a JSON object with these exact fields:
   - product_name: short, memorable name (no spaces, PascalCase)
   - one_liner: one sentence describing the product
   - target_user: who it is for
   - core_features: list of max 5 features for v1 (keep it shippable)
   - data_model: list of main entities with key fields
   - acceptance_criteria: list of 3-5 testable criteria
   - product_type: one of [full-stack SaaS, API-heavy backend, simple landing + auth, data-heavy app]
4. Call `save_product_state` with the PRD
5. Call `add_comment` with the PRD summary
6. Call `complete_issue`

## Constraints
- v1 scope only — if the requirement is too large, cut features until it is shippable in one run
- product_type MUST be one of the four listed above — this drives the stack decision downstream
- data_model entities should be realistic for a free-tier single database
"""

from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters

# DeerFlow research tools come from the MCP research_server process
_research_mcp = MCPToolset(
    connection_params=StdioServerParameters(
        command="python",
        args=["-m", "mcp_servers.gtm.research_server"],
        env={**os.environ},
    )
)

pm_agent = Agent(
    model=MODEL,
    name="pm_agent",
    description="Converts a raw product requirement into a structured PRD using market research.",
    instruction=INSTRUCTION,
    tools=[
        checkout_issue, complete_issue, add_comment,
        save_product_state, recall_product_state,
        _research_mcp,   # provides search_product_web + search_news via MCP
    ],
)
```

- [ ] **Step 2: Write architect_agent.py**

```python
# aass_agents/agents/architect_agent.py
"""
Architect Agent — picks tech stack deterministically and generates file tree.
Does NOT use DeerFlow — stack selection is rule-based to avoid non-determinism.
"""
import os
from google.adk.agents import Agent
from tools.paperclip_client import checkout_issue, complete_issue, add_comment
from tools.product_memory_tools import save_product_state, recall_product_state

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are a Software Architect agent. Your job is to pick the tech stack and generate
a complete file tree for the product.

## Stack Decision Table (USE EXACTLY — no deviation)

| product_type           | Frontend              | Backend                      | Database  |
|------------------------|-----------------------|------------------------------|-----------|
| full-stack SaaS        | Vercel (Next.js 14)  | Next.js API routes           | Supabase  |
| API-heavy backend      | Vercel (Next.js 14)  | Railway (FastAPI)            | NeonDB    |
| simple landing + auth  | Vercel (Next.js 14)  | Supabase Edge Functions      | Supabase  |
| data-heavy app         | Vercel (Next.js 14)  | Railway (FastAPI)            | NeonDB    |

## Selection Criteria
- full-stack SaaS: user-facing UI with CRUD operations
- API-heavy backend: primarily an API/webhook/data processing service, minimal UI
- simple landing + auth: marketing site or waitlist with basic signup
- data-heavy app: analytics, dashboards, large dataset queries

## Your Process

1. Call `checkout_issue` with the issue_id for the "architect" step
2. Call `recall_product_state` to get the PRD
3. Read `product_type` from PRD and select stack from table above
4. Generate architecture as JSON:
   - stack: {frontend, backend, database}
   - file_tree: flat list of all files to generate with their purpose
     - frontend files: all under /frontend/
     - backend files: all under /backend/
   - api_endpoints: list of endpoints the backend will expose
5. Call `save_product_state` with the architecture JSON
6. Call `add_comment` with stack summary
7. Call `complete_issue`

## File Tree Requirements
- /frontend/: package.json, next.config.js, tailwind.config.js, src/app/layout.tsx,
  src/app/page.tsx, src/app/globals.css, src/components/ (key UI components)
- /backend/: (FastAPI) main.py, requirements.txt, Dockerfile, routes/, models/
- /backend/: (Next.js API) included in /frontend/src/app/api/
"""

architect_agent = Agent(
    model=MODEL,
    name="architect_agent",
    description="Picks tech stack deterministically and generates project file tree from PRD.",
    instruction=INSTRUCTION,
    tools=[checkout_issue, complete_issue, add_comment,
           save_product_state, recall_product_state],
)
```

- [ ] **Step 3: Verify imports work**

```bash
cd /Users/bhanu.prakash/Documents/claude_works/sl_agents/aass_agents
python -c "from agents.pm_agent import pm_agent; from agents.architect_agent import architect_agent; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add agents/pm_agent.py agents/architect_agent.py
git commit -m "feat: add PM and Architect agents"
```

---

## Task 7: DevOps + DB Agents

**Files:**
- Create: `aass_agents/agents/devops_agent.py`
- Create: `aass_agents/agents/db_agent.py`

- [ ] **Step 1: Write devops_agent.py**

```python
# aass_agents/agents/devops_agent.py
"""
DevOps Agent — creates GitHub repo, Vercel project, Railway project, injects env vars.
Runs TWICE in pipeline:
  - First pass (Step 3): create infra, save IDs
  - Second pass (Step 4.5): inject DATABASE_URL after db_agent completes
"""
import os
from google.adk.agents import Agent
from tools.paperclip_client import checkout_issue, complete_issue, add_comment
from tools.product_memory_tools import save_product_state, recall_product_state
from tools.github_tools import create_repo
from tools.vercel_tools import create_project as vercel_create, add_env_var as vercel_add_env, connect_github, get_deployment_url
from tools.railway_tools import create_project as railway_create, add_env_var as railway_add_env, deploy_from_github

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are a DevOps agent. You set up the infrastructure for the product pipeline.

## Your Process

### First Pass (action: "setup_infra")
1. Call `checkout_issue` for the "devops" step
2. Call `recall_product_state` to get product_name and architecture
3. Create GitHub repo: name = product_name.lower() + "-app", mono-repo structure
4. Create Vercel project linked to /frontend subdir of that repo
5. Create Railway project
6. Save to product state: repo_url, repo_full_name, vercel_project_id, railway_project_id
7. Call `add_comment` with all URLs
8. Call `complete_issue`

### Second Pass (action: "inject_vercel_env") — runs after Step 4 (db_agent)
1. Call `recall_product_state` to get vercel_project_id, database_url
2. Call `vercel_add_env` with DATABASE_URL
3. Done — no issue checkout needed

### Third Pass (action: "inject_railway_env") — runs after Step 5 (backend_builder_agent)
1. Call `recall_product_state` to get railway_project_id, railway_service_id, database_url
   (railway_service_id is saved by backend_builder_agent after deploy_from_github)
2. Call `railway_add_env` with DATABASE_URL and service_id
3. Done — no issue checkout needed

## Important
- Repo name must be URL-safe (lowercase, hyphens only)
- Railway deploy is triggered by backend_builder_agent, not here
- Vercel deploy is triggered by frontend_builder_agent, not here
"""

devops_agent = Agent(
    model=MODEL,
    name="devops_agent",
    description="Creates GitHub repo, Vercel project, Railway project, and injects environment variables.",
    instruction=INSTRUCTION,
    tools=[
        checkout_issue, complete_issue, add_comment,
        save_product_state, recall_product_state,
        create_repo, vercel_create, vercel_add_env, connect_github,
        railway_create, railway_add_env,
    ],
)
```

- [ ] **Step 2: Write db_agent.py**

```python
# aass_agents/agents/db_agent.py
"""
DB Agent — generates SQL schema and provisions NeonDB or Supabase.
"""
import os
from google.adk.agents import Agent
from tools.paperclip_client import checkout_issue, complete_issue, add_comment
from tools.product_memory_tools import save_product_state, recall_product_state
from tools.neondb_tools import create_project as neon_create, get_connection_string as neon_conn, run_sql as neon_sql
from tools.supabase_tools import create_project as supa_create, get_connection_string as supa_conn, run_sql as supa_sql

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are a Database agent. You provision the database and run the schema migration.

## Your Process

1. Call `checkout_issue` for the "db" step
2. Call `recall_product_state` to get PRD (data_model) and architecture (database choice)
3. Generate SQL CREATE TABLE statements from data_model in PRD
4. Provision the database:
   - If architecture.stack.database == "Supabase": call `supa_create`
   - If architecture.stack.database == "NeonDB": call `neon_create`
   - On failure: try the other provider (fallback)
5. Run the SQL migration
6. Save `database_url` to product state via `save_product_state`
   (devops_agent will read this to inject DATABASE_URL env var)
7. Call `add_comment` with "Database provisioned: [provider] — migration complete"
8. Call `complete_issue`

## SQL Guidelines
- Always include: id (UUID or SERIAL PRIMARY KEY), created_at TIMESTAMP DEFAULT NOW()
- Use TEXT for strings, not VARCHAR
- Add basic indexes on foreign keys
- Keep it simple — no stored procedures, no triggers for v1
"""

db_agent = Agent(
    model=MODEL,
    name="db_agent",
    description="Generates SQL schema and provisions NeonDB or Supabase database.",
    instruction=INSTRUCTION,
    tools=[
        checkout_issue, complete_issue, add_comment,
        save_product_state, recall_product_state,
        neon_create, neon_conn, neon_sql,
        supa_create, supa_conn, supa_sql,
    ],
)
```

- [ ] **Step 3: Verify imports**

```bash
python -c "from agents.devops_agent import devops_agent; from agents.db_agent import db_agent; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add agents/devops_agent.py agents/db_agent.py
git commit -m "feat: add DevOps and DB agents"
```

---

## Task 8: Builder Agents (Backend + Frontend)

**Files:**
- Create: `aass_agents/agents/backend_builder_agent.py`
- Create: `aass_agents/agents/frontend_builder_agent.py`

- [ ] **Step 1: Write backend_builder_agent.py**

```python
# aass_agents/agents/backend_builder_agent.py
"""
Backend Builder Agent — generates API code and deploys to Railway or Vercel.
Uses claude-sonnet-4-6 via code_gen_tools for code generation.
"""
import os
from google.adk.agents import Agent
from tools.paperclip_client import checkout_issue, complete_issue, add_comment
from tools.product_memory_tools import save_product_state, recall_product_state
from tools.github_tools import push_file
from tools.railway_tools import deploy_from_github, get_service_url
from tools.code_gen_tools import generate_code

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are a Backend Builder agent. You generate backend API code and deploy it.

## Your Process

1. Call `checkout_issue` for the "backend" step
2. Call `recall_product_state` to get PRD, architecture, repo_full_name, railway_project_id
3. Generate each backend file using `generate_code`:
   - For FastAPI: main.py, requirements.txt, Dockerfile, routes/*.py, models/*.py
   - For Next.js API routes: src/app/api/**/*.ts
4. Push each file to the repo using `push_file` under /backend/ (or /frontend/src/app/api/)
5. Trigger Railway deployment:
   - Call `deploy_from_github` with repo_full_name
   - Save service_id to product state (needed by devops_agent for env var injection)
6. Wait for deploy (poll `get_service_url` until non-empty, max 5 minutes, 30s intervals)
7. Save backend_url to product state
8. Call `add_comment` with backend_url
9. Call `complete_issue`

## Code Generation Guidelines
- FastAPI: include health endpoint at GET /health returning {"status": "ok"}
- FastAPI: include CORS middleware for the Vercel frontend domain
- All endpoints should use Pydantic models for request/response
- Include DATABASE_URL env var usage via os.environ["DATABASE_URL"]
- Retry budget: if deploy fails, retry generate + push up to 3 times total

## Context to pass to generate_code
Pass the full PRD and architecture JSON as context so the LLM knows the data model and endpoints.
"""

backend_builder_agent = Agent(
    model=MODEL,
    name="backend_builder_agent",
    description="Generates backend API code and deploys it to Railway or Vercel API routes.",
    instruction=INSTRUCTION,
    tools=[
        checkout_issue, complete_issue, add_comment,
        save_product_state, recall_product_state,
        push_file, deploy_from_github, get_service_url,
        generate_code,
    ],
)
```

- [ ] **Step 2: Write frontend_builder_agent.py**

```python
# aass_agents/agents/frontend_builder_agent.py
"""
Frontend Builder Agent — generates Next.js UI and deploys to Vercel.
"""
import os
from google.adk.agents import Agent
from tools.paperclip_client import checkout_issue, complete_issue, add_comment
from tools.product_memory_tools import save_product_state, recall_product_state
from tools.github_tools import push_file
from tools.vercel_tools import trigger_deploy, get_deployment_url
from tools.code_gen_tools import generate_code

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are a Frontend Builder agent. You generate a Next.js UI and deploy it to Vercel.

## Your Process

1. Call `checkout_issue` for the "frontend" step
2. Call `recall_product_state` to get PRD, architecture, repo_full_name, vercel_project_id, backend_url
3. Generate frontend files using `generate_code`:
   - package.json (Next.js 14, tailwindcss, shadcn/ui)
   - next.config.js
   - tailwind.config.js
   - src/app/layout.tsx
   - src/app/page.tsx (main landing/dashboard page)
   - src/app/globals.css
   - Key component files from architecture.file_tree
4. Push each file under /frontend/ using `push_file`
5. Trigger Vercel deployment: call `trigger_deploy` with vercel_project_id
6. Poll `get_deployment_url` until non-empty (max 5 minutes, 30s intervals)
7. Save frontend_url to product state
8. Call `add_comment` with frontend_url
9. Call `complete_issue`

## Code Generation Guidelines
- Use Next.js App Router (src/app/ structure)
- Use Tailwind CSS for all styling — no custom CSS files except globals.css
- Use shadcn/ui components (Button, Card, Input, etc.)
- NEXT_PUBLIC_API_URL env var should point to backend_url
- Include a basic loading state for async operations
- Keep it functional — no animations or polish for v1
- Retry budget: if build fails, regenerate and push up to 3 times total
"""

frontend_builder_agent = Agent(
    model=MODEL,
    name="frontend_builder_agent",
    description="Generates Next.js 14 + Tailwind UI and deploys it to Vercel.",
    instruction=INSTRUCTION,
    tools=[
        checkout_issue, complete_issue, add_comment,
        save_product_state, recall_product_state,
        push_file, trigger_deploy, get_deployment_url,
        generate_code,
    ],
)
```

- [ ] **Step 3: Commit**

```bash
git add agents/backend_builder_agent.py agents/frontend_builder_agent.py
git commit -m "feat: add Backend and Frontend builder agents"
```

---

## Task 9: QA Agent

**Files:**
- Create: `aass_agents/agents/qa_agent.py`

- [ ] **Step 1: Write qa_agent.py**

```python
# aass_agents/agents/qa_agent.py
"""
QA Agent — smoke tests the live deployment.
"""
import os
from google.adk.agents import Agent
from tools.paperclip_client import checkout_issue, complete_issue, add_comment
from tools.product_memory_tools import save_product_state, recall_product_state
from tools.http_tools import smoke_test, health_check, auth_smoke_test

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are a QA agent. You smoke test the live deployment.

## Your Process

1. Call `checkout_issue` for the "qa" step
2. Call `recall_product_state` to get frontend_url, backend_url, PRD
3. Run these tests IN ORDER — stop on first failure:

   Test 1: Frontend root
   - `smoke_test(frontend_url)` → must return passed=True
   - If fail: report "Frontend root URL returned HTTP [code]"

   Test 2: Backend health
   - `health_check(backend_url)` → must return passed=True
   - If fail: report "Backend health check failed: [error]"

   Test 3: Auth flow (only if PRD acceptance_criteria mentions auth)
   - `auth_smoke_test(frontend_url)` → must return passed=True (200, 201, or 409)
   - If fail: report "Auth endpoint not responding: [error]"

4. Build qa_report:
   {
     "passed": true/false,
     "tests": [{"name": "...", "passed": true/false, "detail": "..."}],
     "failure_reason": "..." or null
   }
5. Call `save_product_state` with qa_report
6. Call `add_comment` with summary: PASSED or FAILED + reason
7. Call `complete_issue`

## On Failure
Return the qa_report to product_orchestrator — it will decide whether to retry.
Do NOT retry yourself.
"""

qa_agent = Agent(
    model=MODEL,
    name="qa_agent",
    description="Smoke tests the live deployment: root URL, health endpoint, auth flow.",
    instruction=INSTRUCTION,
    tools=[
        checkout_issue, complete_issue, add_comment,
        save_product_state, recall_product_state,
        smoke_test, health_check, auth_smoke_test,
    ],
)
```

- [ ] **Step 2: Commit**

```bash
git add agents/qa_agent.py
git commit -m "feat: add QA agent"
```

---

## Task 10: Product Orchestrator

**Files:**
- Create: `aass_agents/agents/product_orchestrator_agent.py`

- [ ] **Step 1: Write product_orchestrator_agent.py**

```python
# aass_agents/agents/product_orchestrator_agent.py
"""
Product Orchestrator — coordinates the 8-step pipeline from requirement to live URL.
Creates Paperclip issues upfront, runs agents sequentially, returns live URL.
"""
import os
import uuid
from google.adk.agents import Agent
from agents.pm_agent import pm_agent
from agents.architect_agent import architect_agent
from agents.devops_agent import devops_agent
from agents.db_agent import db_agent
from agents.backend_builder_agent import backend_builder_agent
from agents.frontend_builder_agent import frontend_builder_agent
from agents.qa_agent import qa_agent
from tools.paperclip_client import create_issue, add_comment
from tools.product_memory_tools import save_product_state, recall_product_state

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are the Product Orchestrator. You coordinate the full pipeline from requirement to live URL.

## Pipeline Steps

### Setup
1. Generate a product_id (UUID) — this is your pipeline key for all state
2. Create 7 Paperclip issues via `create_issue`:
   - "PM: Generate PRD"
   - "Architect: Define Stack + File Tree"
   - "DevOps: Create GitHub + Vercel + Railway"
   - "DB: Provision Database + Run Schema"
   - "Backend: Build + Deploy API"
   - "Frontend: Build + Deploy UI"
   - "QA: Smoke Test Live URL"
3. Save issue IDs to product state: `save_product_state(product_id, issue_ids={...})`
4. Save the requirement to product state

### Execute (in order — each depends on the previous)
Step 1: Delegate to `pm_agent` with product_id and pm issue_id
Step 2: Delegate to `architect_agent` with product_id and architect issue_id
Step 3: Delegate to `devops_agent` (action="setup_infra") with product_id and devops issue_id
Step 4: Delegate to `db_agent` with product_id and db issue_id
Step 4.5: Delegate to `devops_agent` (action="inject_vercel_env") — inject DATABASE_URL into Vercel only (Railway service doesn't exist yet)
Step 5: Delegate to `backend_builder_agent` with product_id and backend issue_id
Step 5.5: Delegate to `devops_agent` (action="inject_railway_env") — inject DATABASE_URL into Railway service (now that service_id exists in product state)
Step 6: Delegate to `frontend_builder_agent` with product_id and frontend issue_id
Step 7: Delegate to `qa_agent` with product_id and qa issue_id

### Error Handling
- If any agent reports failure: check retry count in product state
  - Builder agents: max 3 deploy retries, 2 QA-triggered rebuilds (5 total)
  - DB agent: try other provider on failure
  - After all retries exhausted: save status="failed", report to user with last error
- Railway billing error detected: pause, notify user "Railway credit exhausted — add billing or switch to Render"

### On Success
Call `save_product_state(product_id, status="shipped", frontend_url=...)`
Return this exact structure:
{
  "status": "shipped",
  "product_id": "<uuid>",
  "live_url": "<frontend_url>",
  "product_name": "<from PRD>",
  "one_liner": "<from PRD>",
  "target_user": "<from PRD>",
  "core_features": ["...", ...]
}
"""

product_orchestrator = Agent(
    model=MODEL,
    name="product_orchestrator",
    description=(
        "Coordinates the full pipeline: requirement → PRD → architecture → infra → database "
        "→ backend → frontend → QA → live URL. Returns shipped product URL."
    ),
    instruction=INSTRUCTION,
    sub_agents=[
        pm_agent,
        architect_agent,
        devops_agent,
        db_agent,
        backend_builder_agent,
        frontend_builder_agent,
        qa_agent,
    ],
    tools=[create_issue, add_comment, save_product_state, recall_product_state],
)
```

- [ ] **Step 2: Verify imports**

```bash
python -c "from agents.product_orchestrator_agent import product_orchestrator; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agents/product_orchestrator_agent.py
git commit -m "feat: add product orchestrator agent"
```

---

## Task 11: Wire Into Company Orchestrator

**Files:**
- Modify: `aass_agents/agents/company_orchestrator_agent.py`

- [ ] **Step 1: Read current company_orchestrator_agent.py**

Read the file at `aass_agents/agents/company_orchestrator_agent.py` to see the current INSTRUCTION and Agent definition.

- [ ] **Step 2: Add product routing to INSTRUCTION**

Add this block to the INSTRUCTION string, after the "## Routing Logic" section:

```python
# Add to INSTRUCTION after existing routing rules:
"""
Route to **Product Team** when:
- "build" / "ship" / "create a product" / "make an app" / "deploy"
- "build me" / "create a SaaS" / "I want an app that" / "ship a tool"
- Any request describing software to be built and deployed

## Product Ship → GTM Auto-Trigger

When product_orchestrator returns a response with `status == "shipped"`:
1. Display the live URL to the user: "✅ Product shipped: [live_url]"
2. Automatically route to marketing_orchestrator with this context:
   - product_name, one_liner, target_user, core_features, live_url
3. Say: "Kicking off GTM — building your audience and campaign now."
"""
```

- [ ] **Step 3: Add product_orchestrator as sub-agent**

In `company_orchestrator_agent.py`, import and add:

```python
from agents.product_orchestrator_agent import product_orchestrator

# In the Agent() call, add product_orchestrator to sub_agents:
company_orchestrator = Agent(
    ...
    sub_agents=[
        marketing_orchestrator,
        sales_orchestrator,
        product_orchestrator,   # ADD THIS
    ],
    ...
)
```

- [ ] **Step 4: Verify the full agent tree imports**

```bash
python -c "from agents.company_orchestrator_agent import company_orchestrator; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add agents/company_orchestrator_agent.py
git commit -m "feat: wire product_orchestrator into company_orchestrator with GTM auto-trigger"
```

---

## Task 12: Integration Smoke Test (Manual)

This task verifies the full pipeline end-to-end with a minimal test product.

- [ ] **Step 1: Set up environment variables**

Copy `.env.example` to `.env` and fill in:
- `GITHUB_TOKEN` — GitHub PAT with `repo` scope
- `VERCEL_TOKEN` — Vercel API token
- `RAILWAY_TOKEN` — Railway API token
- `NEONDB_API_KEY` — NeonDB API key
- `ANTHROPIC_API_KEY` — Anthropic API key
- `PAPERCLIP_API_URL` + `PAPERCLIP_API_KEY` — Paperclip server

- [ ] **Step 2: Run the pipeline with a minimal requirement**

```bash
cd /Users/bhanu.prakash/Documents/claude_works/sl_agents/aass_agents
python main.py
# Send this message to company_orchestrator:
# "Build me a simple task tracker SaaS where users can create, complete, and delete tasks"
```

- [ ] **Step 3: Verify each step in Paperclip dashboard**

Check that all 7 Paperclip issues are created and progress through: todo → in_progress → done

- [ ] **Step 4: Verify live URL**

Open the returned `live_url` in a browser. Confirm:
- Page loads (200 OK)
- UI is visible (not blank)
- Health endpoint responds

- [ ] **Step 5: Verify GTM trigger**

After ship, confirm `marketing_orchestrator` is activated with the product context (check console output for "Kicking off GTM").

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "feat: complete autonomous product pipeline — idea to shipped URL"
```

---

## Environment Variables Summary

| Variable | Used by | Where to get |
|----------|---------|-------------|
| `GITHUB_TOKEN` | github_tools | github.com/settings/tokens (repo scope) |
| `VERCEL_TOKEN` | vercel_tools | vercel.com/account/tokens |
| `RAILWAY_TOKEN` | railway_tools | railway.app/account/tokens |
| `NEONDB_API_KEY` | neondb_tools | console.neon.tech/app/settings/api-keys |
| `SUPABASE_ACCESS_TOKEN` | supabase_tools | supabase.com/dashboard/account/tokens |
| `ANTHROPIC_API_KEY` | code_gen_tools | console.anthropic.com/settings/keys |
| `PAPERCLIP_API_URL` | paperclip_client | your Paperclip server URL |
| `PAPERCLIP_API_KEY` | paperclip_client | your Paperclip API key |
| `SUPABASE_ORG_ID` | supabase_tools | supabase.com/dashboard/org/settings (required for project creation) |
| `SUPABASE_DB_PASS` | supabase_tools | set a strong password; stored in .env only, never in code |
| `PRODUCT_DB_PATH` | product_memory_tools | optional override (defaults to product_pipeline.db) |

---

## Free Tier Limits Reference

| Platform | Free Tier | Limit |
|----------|-----------|-------|
| Vercel | Hobby | 100GB bandwidth, 6000 build minutes/month |
| Railway | $5 credit | ~2 full pipeline runs — add billing after |
| NeonDB | Free | 0.5 GB storage, 1 project |
| Supabase | Free | 500 MB DB, 2 projects |
| Anthropic | Pay per use | ~$0.05 per pipeline run (Haiku + Sonnet mix) |
| GitHub | Free | Unlimited public repos |
