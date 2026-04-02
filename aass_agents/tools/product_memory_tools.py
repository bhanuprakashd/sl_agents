"""
Product pipeline state store — separate from GTM memory.
Uses its own SQLite table keyed by product_id (UUID).
Tracks tech preferences, build iterations, and design guidelines.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any  # kept for potential future use

_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "product_pipeline.db")

_VALID_COLUMNS = {
    "product_name", "status", "prd", "architecture",
    "repo_url", "database_url", "backend_url", "frontend_url", "qa_report",
    "tech_preferences", "build_iteration", "design_guidelines",
}

_STEP_LOG_TABLE = "product_step_log"


def _db_path() -> str:
    return os.environ.get("PRODUCT_DB_PATH", _DEFAULT_DB)


def generate_product_id() -> str:
    """Generate a new UUID for a product pipeline. Call this first before save_product_state."""
    import uuid
    return str(uuid.uuid4())


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_product_db() -> None:
    """Create the product_pipeline_state table if it does not exist."""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS product_pipeline_state (
                product_id        TEXT PRIMARY KEY,
                product_name      TEXT,
                status            TEXT DEFAULT 'running',
                prd               TEXT,
                architecture      TEXT,
                repo_url          TEXT,
                database_url      TEXT,
                backend_url       TEXT,
                frontend_url      TEXT,
                qa_report         TEXT,
                tech_preferences  TEXT,
                build_iteration   INTEGER DEFAULT 0,
                design_guidelines TEXT,
                created_at        TEXT,
                updated_at        TEXT
            )
        """)
        # Add new columns to existing tables (safe — ignores if already present)
        for col, col_type in [
            ("tech_preferences", "TEXT"),
            ("build_iteration", "INTEGER DEFAULT 0"),
            ("design_guidelines", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE product_pipeline_state ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass  # column already exists


def save_product_state(
    product_id: str,
    product_name: str = "",
    status: str = "",
    prd: str = "",
    architecture: str = "",
    repo_url: str = "",
    database_url: str = "",
    backend_url: str = "",
    frontend_url: str = "",
    qa_report: str = "",
    tech_preferences: str = "",
    build_iteration: str = "",
    design_guidelines: str = "",
) -> str:
    """
    Upsert product pipeline state. Pass only the fields you want to set or update.
    Returns confirmation message.
    """
    fields = {
        k: v for k, v in {
            "product_name": product_name, "status": status, "prd": prd,
            "architecture": architecture, "repo_url": repo_url,
            "database_url": database_url, "backend_url": backend_url,
            "frontend_url": frontend_url, "qa_report": qa_report,
            "tech_preferences": tech_preferences,
            "build_iteration": build_iteration,
            "design_guidelines": design_guidelines,
        }.items() if v  # skip empty strings
    }
    init_product_db()
    now = datetime.now(timezone.utc).isoformat()
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
            if not serialized:
                # Nothing to update besides the timestamp
                conn.execute(
                    "UPDATE product_pipeline_state SET updated_at = ? WHERE product_id = ?",
                    [now, product_id],
                )
            else:
                set_clause = ", ".join(f"{k} = ?" for k in serialized)
                vals = list(serialized.values()) + [now, product_id]
                conn.execute(
                    f"UPDATE product_pipeline_state SET {set_clause}, updated_at = ? WHERE product_id = ?",
                    vals,
                )
    return f"Product state saved for {product_id}: {list(fields.keys())}"


def log_step(product_id: str, step: str, message: str) -> str:
    """Log a pipeline step progress message to SQLite. Returns confirmation."""
    init_product_db()
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {_STEP_LOG_TABLE} (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                step       TEXT NOT NULL,
                message    TEXT,
                logged_at  TEXT
            )
        """)
        conn.execute(
            f"INSERT INTO {_STEP_LOG_TABLE} (product_id, step, message, logged_at) VALUES (?, ?, ?, ?)",
            (product_id, step, message, now),
        )
    return f"Logged step '{step}' for {product_id}"


def append_product_section(
    product_id: str,
    field: str,
    content: str,
) -> str:
    """
    Append or set a section of a large field (prd or architecture) incrementally.
    Use this to save large outputs in small chunks to avoid malformed tool calls.

    Args:
        product_id: The product UUID.
        field: Which field to append to — must be 'prd' or 'architecture'.
        content: The text chunk to append. Will be concatenated to existing content.

    Example: Call multiple times to build up the PRD piece by piece:
        append_product_section(product_id, "prd", '{"product_name": "Foo", "one_liner": "...",')
        append_product_section(product_id, "prd", '"core_features": [...],')
        append_product_section(product_id, "prd", '"data_model": [...]}')
    """
    if field not in ("prd", "architecture"):
        return f"Error: field must be 'prd' or 'architecture', got '{field}'"
    init_product_db()
    with _conn() as conn:
        row = conn.execute(
            f"SELECT {field} FROM product_pipeline_state WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        existing = (row[field] if row and row[field] else "") if row else ""
        new_value = existing + content
        now = datetime.now(timezone.utc).isoformat()
        if row:
            conn.execute(
                f"UPDATE product_pipeline_state SET {field} = ?, updated_at = ? WHERE product_id = ?",
                (new_value, now, product_id),
            )
        else:
            conn.execute(
                "INSERT INTO product_pipeline_state (product_id, {}, created_at, updated_at) VALUES (?, ?, ?, ?)".format(field),
                (product_id, new_value, now, now),
            )
    return f"Appended {len(content)} chars to {field} for {product_id} (total: {len(new_value)} chars)"


def recall_product_state(product_id: str) -> str:
    """Return full product state as JSON string, or message if not found."""
    init_product_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM product_pipeline_state WHERE product_id = ?",
            (product_id,),
        ).fetchone()
    if row is None:
        return f"No product state found for {product_id}"
    result = dict(row)
    for key, val in result.items():
        if isinstance(val, str) and val and val[0] in ("{", "["):
            try:
                result[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
    return json.dumps(result, indent=2, default=str)
