"""
Cognition Base Tools -- agent-callable semantic search and CRUD layer
on top of cognition_base_db.

Provides embedding-based search using sentence-transformers (all-MiniLM-L6-v2)
and thin async wrappers that delegate to the DB module.

All functions that agents call return JSON-formatted strings (ADK requirement).
"""
import json
import asyncio
from pathlib import Path
from typing import Optional

from tools import cognition_base_db

# Skills directory for seeding
_SKILLS_DIR = Path(__file__).parent.parent / "skills"


# -- Embedding model (lazy singleton) -----------------------------------------

_MODEL = None


def _get_model():
    """Lazy-load the sentence-transformers model (singleton)."""
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


def _embed(text: str) -> bytes:
    """Encode text to an embedding and return as raw bytes."""
    import numpy as np
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return np.array(vec, dtype=np.float32).tobytes()


def _cosine_similarity(a: bytes, b: bytes) -> float:
    """Compute cosine similarity between two embedding byte blobs."""
    import numpy as np
    va = np.frombuffer(a, dtype=np.float32)
    vb = np.frombuffer(b, dtype=np.float32)
    dot = float(np.dot(va, vb))
    norm_a = float(np.linalg.norm(va))
    norm_b = float(np.linalg.norm(vb))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# -- Agent-callable tools (all return JSON strings) ----------------------------

async def search_cognition(query: str, domain: str = None, top_k: int = 5) -> str:
    """
    Semantic search over the cognition base.

    Embeds the query, computes cosine similarity against all stored entries
    (optionally filtered by domain), and returns the top_k results.
    Increments access_count for each returned entry.
    """
    try:
        query_emb = await asyncio.to_thread(_embed, query)
    except ImportError:
        return json.dumps({
            "error": "sentence-transformers is not installed. "
                     "Run: pip install sentence-transformers"
        })

    all_entries = await cognition_base_db.get_all_embeddings(domain=domain)

    scored = []
    for entry in all_entries:
        emb = entry.get("embedding")
        if emb is None:
            continue
        sim = _cosine_similarity(query_emb, emb)
        scored.append({
            "id": entry["id"],
            "domain": entry["domain"],
            "title": entry["title"],
            "similarity_score": round(sim, 4),
        })

    scored.sort(key=lambda x: x["similarity_score"], reverse=True)
    top_results = scored[:top_k]

    # Fetch full content for top results and increment access counts
    enriched = []
    for item in top_results:
        full = await cognition_base_db.get_entry(item["id"])
        if full is None:
            continue
        await cognition_base_db.increment_access(item["id"])
        enriched.append({
            "id": item["id"],
            "domain": item["domain"],
            "title": item["title"],
            "content": full["content"],
            "similarity_score": item["similarity_score"],
        })

    return json.dumps({"results": enriched, "total_searched": len(all_entries)})


async def add_cognition(
    title: str,
    content: str,
    domain: str,
    source: str = "manual",
) -> str:
    """
    Add a new cognition entry with an embedding.

    Returns JSON with the entry id and confirmation.
    """
    try:
        embedding_bytes = await asyncio.to_thread(_embed, content)
    except ImportError:
        return json.dumps({
            "error": "sentence-transformers is not installed. "
                     "Run: pip install sentence-transformers"
        })

    entry_id = await cognition_base_db.add_entry(
        domain=domain,
        title=title,
        content=content,
        embedding_bytes=embedding_bytes,
        source=source,
    )
    return json.dumps({"id": entry_id, "status": "added", "domain": domain, "title": title})


async def seed_cognition_from_skills() -> str:
    """
    Scan aass_agents/skills/ for SKILL.md files and seed them into the
    cognition base.

    Extracts title from the first # heading, domain from the directory path,
    and stores each with source='skill_file'. Skips entries where a matching
    title+domain already exists.

    Returns count of entries added.
    """
    try:
        _get_model()  # ensure model loads before we start
    except ImportError:
        return json.dumps({
            "error": "sentence-transformers is not installed. "
                     "Run: pip install sentence-transformers"
        })

    if not _SKILLS_DIR.exists():
        return json.dumps({"error": f"Skills directory not found: {_SKILLS_DIR}"})

    skill_files = sorted(_SKILLS_DIR.rglob("SKILL.md"))
    added = 0
    skipped = 0

    for skill_path in skill_files:
        text = skill_path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            skipped += 1
            continue

        # Extract title from first # heading
        title = None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                break
        if not title:
            title = skill_path.parent.name

        # Determine domain from path: skills/<domain>/...
        try:
            rel = skill_path.relative_to(_SKILLS_DIR)
            domain = rel.parts[0] if len(rel.parts) > 1 else "general"
        except ValueError:
            domain = "general"

        # Check if entry with same title+domain already exists
        existing = await search_cognition(query=title, domain=domain, top_k=1)
        existing_data = json.loads(existing)
        results = existing_data.get("results", [])
        if results and results[0].get("title") == title and results[0].get("domain") == domain:
            skipped += 1
            continue

        # Add the entry
        content = text
        await add_cognition(
            title=title,
            content=content,
            domain=domain,
            source="skill_file",
        )
        added += 1

    return json.dumps({"added": added, "skipped": skipped, "total_files": len(skill_files)})


async def get_cognition_stats() -> str:
    """
    Return JSON with entry counts per domain and total.
    """
    # Get all entries grouped by domain
    all_entries = await cognition_base_db.get_all_embeddings(domain=None)

    domain_counts: dict[str, int] = {}
    for entry in all_entries:
        d = entry.get("domain", "unknown")
        domain_counts[d] = domain_counts.get(d, 0) + 1

    total = await cognition_base_db.count_entries()

    return json.dumps({
        "total": total,
        "by_domain": domain_counts,
    })
