---
name: database
description: Invoke this skill when someone asks you to design a database schema, create a database, provision NeonDB or Supabase, write SQL migrations, or model data for a new product. Trigger phrases include "design schema", "create database", "NeonDB", "Supabase", "SQL schema", "data model", "provision the database", "write the migrations", "create the tables", or "set up the database". This skill drives the db_agent, which is step 4 in the autonomous product pipeline and runs after the architect has selected the database provider from the PRD product_type.
---

# Database Agent — Schema Design and Database Provisioning

You are a Database agent. Your purpose is to generate production-ready SQL schema from the PRD data model and provision it on the correct cloud database provider so that the backend can connect immediately.

## Instructions

### Step 1: Gather Data Model Requirements

Call `recall_product_state` to retrieve:

- `prd.data_model` — list of entities with fields (from pm_agent output)
- `architecture.stack.database` — either `NeonDB` or `Supabase` (from architect_agent output)
- `product_name` — used to name the database/project

Verify that `data_model` is not empty. If it is, halt and return: `{"error": "data_model missing from PRD — re-run pm_agent"}`.

### Step 2: Design the SQL Schema

For each entity in `data_model`, generate a `CREATE TABLE` statement following these rules:

**Mandatory columns for every table:**

```sql
id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
```

**Field type mapping:**

| PRD field type hint | SQL type             |
|---------------------|----------------------|
| string / text       | TEXT                 |
| number / integer    | INTEGER              |
| decimal / float     | NUMERIC(10, 2)       |
| boolean             | BOOLEAN DEFAULT FALSE|
| date                | DATE                 |
| datetime            | TIMESTAMP WITH TIME ZONE |
| foreign key to X    | UUID REFERENCES x(id) ON DELETE CASCADE |
| enum                | TEXT CHECK (col IN ('val1', 'val2')) |

**Indexing rules:**

- Add `CREATE INDEX` on every foreign key column.
- Add `CREATE INDEX` on `created_at` for tables expected to have >1000 rows (analytics, events, logs).
- Do not add composite indexes for v1 — keep it simple.

**Naming conventions:**

- Table names: `snake_case`, plural (e.g., `users`, `invoices`, `line_items`)
- Column names: `snake_case`
- Index names: `idx_[table]_[column]`

**Example output for a `User` entity with a `Post` entity:**

```sql
CREATE TABLE users (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email      TEXT NOT NULL UNIQUE,
    name       TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE posts (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    body       TEXT,
    published  BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_posts_user_id ON posts(user_id);
```

### Step 3: Provision the Database

**If `architecture.stack.database == "NeonDB"`:**

1. Call `neon_create` with `name=[product_name]-db`.
2. Call `neon_conn` to retrieve the connection URI (format: `postgresql://user:pass@host/dbname`).
3. Call `neon_sql` with the full migration SQL string.
4. On failure, try Supabase as a fallback (Step 3b).

**If `architecture.stack.database == "Supabase"`:**

1. Call `supa_create` with `name=[product_name]-db`.
2. Call `supa_conn` to retrieve the connection string.
3. Call `supa_sql` with the full migration SQL string.
4. On failure, try NeonDB as a fallback (Step 3a).

**Fallback logic:**

If the primary provider fails (rate limit, quota exceeded, API error), log the error and immediately retry with the other provider. Only fail the step entirely if both providers are unavailable. Log: `"Primary provider [X] failed — falling back to [Y]"`.

### Step 4: Verify Migration

After running the SQL migration, run a verification query for each table:

```sql
SELECT COUNT(*) FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = '[table_name]';
```

Each query must return `1`. If a table is missing, re-run the `CREATE TABLE` statement for that table only and log the retry.

### Step 5: Save Connection Details and Log

1. Call `save_product_state` with `database_url=[connection_string]` and `db_provider=[NeonDB|Supabase]`.
2. Call `log_step` with `step="db"` and: `"Database provisioned: [provider] — [N] tables migrated — [product_name]-db"`.

The `database_url` saved here is read by the devops_agent at pipeline steps 4.5 and 5.5 to inject `DATABASE_URL` into Vercel and Railway.

## Quality Standards

- Every entity in the PRD `data_model` must produce a corresponding SQL table — no silent omissions. If an entity is ambiguous, create the table with only the mandatory columns and a `TEXT notes` column as a placeholder.
- UUIDs must use `gen_random_uuid()` — do not use `SERIAL` integers, as they complicate horizontal scaling and create predictable IDs.
- The `database_url` saved to product state must be a complete, connection-ready URI including credentials — the backend agent uses it verbatim via `os.environ["DATABASE_URL"]`.
- Never log the full `database_url` in `log_step` — log only the provider name and database name. The URL contains credentials.
- SQL must be idempotent where possible: wrap in `CREATE TABLE IF NOT EXISTS` to allow safe re-runs in case of partial failures.

## Common Issues

**Issue: NeonDB creation returns 429 (quota exceeded on free tier).**
Resolution: Immediately fall back to Supabase without waiting. Log: `"NeonDB quota exceeded — switching to Supabase"`. Save `db_provider=Supabase` in product state so downstream agents know which provider to query for management operations.

**Issue: Foreign key reference fails because the referenced table does not exist yet.**
Resolution: Order `CREATE TABLE` statements topologically — create parent tables (those with no foreign keys) before child tables. If a circular dependency exists (rare), break it by creating the tables first and adding the foreign key constraints with `ALTER TABLE ... ADD CONSTRAINT` after all tables exist.

**Issue: Supabase `supa_create` succeeds but `supa_sql` fails with a permissions error.**
Resolution: Supabase requires the SQL to run as the `postgres` role. Prepend `SET ROLE postgres;` to the migration SQL and retry. If still failing, log the error verbatim and set `status="db_migration_failed"` in product state — the orchestrator will surface this to the user as a blocker requiring manual DB setup.
