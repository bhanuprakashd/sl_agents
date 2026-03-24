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
