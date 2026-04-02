"""
Skill Learning — remembers successful builds and reuses patterns.

After each successful product build, saves the PRD → architecture → build
outcome as a "learned skill." Before new builds, queries for similar past
products and injects proven patterns as context.

This is how the pipeline gets smarter over time — instead of designing from
scratch every time, it learns from what worked before.

Tables:
  learned_skills: product patterns that succeeded
  skill_tags: searchable tags for similarity matching
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "product_pipeline.db")


def _db_path() -> str:
    return os.environ.get("PRODUCT_DB_PATH", _DEFAULT_DB)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init_skill_tables() -> None:
    """Create skill learning tables if they don't exist."""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learned_skills (
                skill_id      TEXT PRIMARY KEY,
                product_name  TEXT NOT NULL,
                product_type  TEXT,
                domain        TEXT,
                tech_stack    TEXT,
                prd_summary   TEXT,
                architecture  TEXT,
                build_phases  TEXT,
                qa_result     TEXT,
                quality_score INTEGER DEFAULT 0,
                times_reused  INTEGER DEFAULT 0,
                created_at    TEXT,
                updated_at    TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_tags (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_id  TEXT NOT NULL,
                tag       TEXT NOT NULL,
                FOREIGN KEY (skill_id) REFERENCES learned_skills(skill_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_skill_tags_tag ON skill_tags(tag)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_learned_skills_domain ON learned_skills(domain)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_learned_skills_product_type ON learned_skills(product_type)
        """)


def _extract_domain(product_name: str, prd: dict) -> str:
    """Extract the business domain from product name and PRD."""
    name_lower = (product_name or "").lower()
    one_liner = (prd.get("one_liner", "") or "").lower()
    features_text = " ".join(
        f.get("name", "") if isinstance(f, dict) else str(f)
        for f in (prd.get("core_features", []) or [])
    ).lower()
    combined = f"{name_lower} {one_liner} {features_text}"

    domains = {
        "agriculture": ["farm", "crop", "harvest", "irrigation", "aquaculture", "shrimp", "pond", "livestock"],
        "ecommerce": ["shop", "cart", "checkout", "product", "inventory", "order", "payment", "store"],
        "finance": ["bank", "payment", "invoice", "budget", "accounting", "expense", "transaction"],
        "healthcare": ["patient", "medical", "health", "clinic", "appointment", "doctor", "prescription"],
        "education": ["course", "student", "lesson", "quiz", "learning", "classroom", "teacher"],
        "social": ["profile", "post", "feed", "follow", "message", "chat", "community"],
        "project_management": ["task", "project", "sprint", "kanban", "ticket", "milestone", "team"],
        "content": ["blog", "article", "cms", "publish", "editor", "media", "content"],
        "analytics": ["dashboard", "chart", "metric", "report", "analytics", "visualization", "data"],
        "real_estate": ["property", "listing", "tenant", "rent", "lease", "real estate"],
    }

    for domain, keywords in domains.items():
        if any(kw in combined for kw in keywords):
            return domain
    return "general"


def _extract_tags(product_name: str, prd: dict, architecture: dict) -> list:
    """Extract searchable tags from product data."""
    tags = set()

    # Domain tags
    domain = _extract_domain(product_name, prd)
    tags.add(f"domain:{domain}")

    # Product type
    product_type = prd.get("product_type", "")
    if product_type:
        tags.add(f"type:{product_type}")

    # Tech stack tags
    stack = architecture.get("stack", {}) if isinstance(architecture, dict) else {}
    for key, val in stack.items():
        if val:
            tags.add(f"tech:{str(val).lower()}")

    # Feature tags (from feature names)
    for feature in (prd.get("core_features", []) or []):
        name = feature.get("name", "") if isinstance(feature, dict) else str(feature)
        for word in name.lower().split():
            if len(word) > 3:
                tags.add(f"feature:{word}")

    # Entity tags (from data model)
    for entity in (prd.get("data_model", []) or []):
        name = entity.get("name", "") if isinstance(entity, dict) else str(entity)
        if name:
            tags.add(f"entity:{name.lower()}")

    return list(tags)


def _compute_quality_score(build_result: dict, base_score: int = 70) -> int:
    """
    Compute quality score from build outcome — a learning organization measures results.

    Score adjustments:
    - Fewer feedback rounds = higher quality (got it right sooner)
    - All QA tests passed = bonus
    - Phases that failed = penalty
    - User approved = big bonus
    """
    score = base_score

    # Feedback loop performance (most important signal)
    feedback = build_result.get("feedback", {})
    total_rounds = feedback.get("total_rounds", 0)
    if total_rounds == 0:
        score += 15  # No feedback needed = excellent first build
    elif total_rounds == 1:
        score += 10  # One round = minor adjustments
    elif total_rounds <= 3:
        score += 0   # Normal
    else:
        score -= (total_rounds - 3) * 5  # Each extra round = penalty

    # User approval
    status = build_result.get("status", "")
    if status == "approved":
        score += 10
    elif status == "shipped":
        score += 5
    elif status == "shipped_with_issues":
        score -= 5
    elif status in ("built_no_server", "failed"):
        score -= 15

    # Phase failures
    failed_phases = build_result.get("phases_failed", [])
    score -= len(failed_phases) * 10

    # QA pass rate
    qa_results = build_result.get("qa_results", [])
    if qa_results:
        last_qa = qa_results[-1] if isinstance(qa_results[-1], dict) else {}
        passed = last_qa.get("passed", 0)
        failed = last_qa.get("failed", 0)
        if passed > 0 and failed == 0:
            score += 5

    return max(0, min(100, score))


def save_learned_skill(
    product_id: str,
    product_name: str,
    prd: dict,
    architecture: dict,
    build_result: dict,
    quality_score: int = -1,
) -> str:
    """
    Save a successful build as a learned skill for future reuse.
    Call this after a product pipeline completes successfully.

    Quality score is auto-computed from build outcomes unless explicitly provided.
    A learning organization measures results: fewer feedback rounds, faster QA pass,
    user approval — all contribute to a higher quality score.

    Args:
        product_id: UUID of the product
        product_name: Name of the product
        prd: The full PRD dict
        architecture: The full architecture dict
        build_result: Build outcome (phases completed, QA results, URL, feedback)
        quality_score: -1 = auto-compute (default), 0-100 = explicit

    Returns:
        Confirmation message with skill_id and computed quality score
    """
    _init_skill_tables()
    now = datetime.now(timezone.utc).isoformat()
    domain = _extract_domain(product_name, prd)
    tags = _extract_tags(product_name, prd, architecture)

    # Auto-compute quality from build outcomes
    if quality_score < 0:
        quality_score = _compute_quality_score(build_result)

    # Summarize PRD for compact storage
    prd_summary = {
        "product_name": prd.get("product_name", product_name),
        "one_liner": prd.get("one_liner", ""),
        "product_type": prd.get("product_type", ""),
        "core_features": [
            f.get("name", str(f)) if isinstance(f, dict) else str(f)
            for f in (prd.get("core_features", []) or [])
        ],
        "data_model": [
            e.get("name", str(e)) if isinstance(e, dict) else str(e)
            for e in (prd.get("data_model", []) or [])
        ],
        "tech_preferences": prd.get("tech_preferences", {}),
    }

    # Store feedback insights alongside the skill for future learning
    feedback_insights = {}
    feedback = build_result.get("feedback", {})
    if feedback:
        feedback_insights = {
            "total_rounds": feedback.get("total_rounds", 0),
            "common_issues": _extract_feedback_themes(feedback),
        }

    with _conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO learned_skills
            (skill_id, product_name, product_type, domain, tech_stack,
             prd_summary, architecture, build_phases, qa_result,
             quality_score, times_reused, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (
            product_id,
            product_name,
            prd.get("product_type", ""),
            domain,
            json.dumps(architecture.get("stack", {})),
            json.dumps(prd_summary),
            json.dumps({**architecture, "feedback_insights": feedback_insights}),
            json.dumps(build_result.get("phases_completed", [])),
            json.dumps(build_result.get("qa_results", [])),
            quality_score,
            now, now,
        ))

        # Save tags (including feedback-derived tags for better matching)
        conn.execute("DELETE FROM skill_tags WHERE skill_id = ?", (product_id,))
        # Add feedback issue categories as tags so future similar products can learn
        for issue_cat in feedback_insights.get("common_issues", {}).keys():
            tags.append(f"issue:{issue_cat}")
        for tag in set(tags):
            conn.execute(
                "INSERT INTO skill_tags (skill_id, tag) VALUES (?, ?)",
                (product_id, tag),
            )

    return (
        f"Learned skill saved: {product_name} "
        f"(domain={domain}, tags={len(tags)}, score={quality_score}, "
        f"feedback_rounds={feedback_insights.get('total_rounds', 0)})"
    )


def _extract_feedback_themes(feedback: dict) -> dict[str, int]:
    """Extract recurring issue categories from feedback loop for learning."""
    themes: dict[str, int] = {}
    for round_data in feedback.get("rounds", []):
        issues_json = round_data.get("parsed_issues", "[]")
        if isinstance(issues_json, str):
            try:
                issues = json.loads(issues_json)
            except (json.JSONDecodeError, TypeError):
                issues = []
        else:
            issues = issues_json
        for issue in issues:
            cat = issue.get("category", "general")
            themes[cat] = themes.get(cat, 0) + 1
    return themes


def update_skill_quality_from_feedback(product_id: str, feedback_result: dict) -> str:
    """
    Meta-learning: update a skill's quality score based on feedback loop outcome.

    Called AFTER the feedback loop completes to refine the skill quality.
    This is how the system learns — builds that needed many rounds get lower
    scores, builds that got approved quickly get higher scores.

    Args:
        product_id: UUID of the product/skill
        feedback_result: Feedback loop outcome dict

    Returns:
        Status message with new quality score
    """
    _init_skill_tables()

    with _conn() as conn:
        row = conn.execute(
            "SELECT quality_score FROM learned_skills WHERE skill_id = ?",
            (product_id,),
        ).fetchone()

        if not row:
            return f"Skill {product_id} not found — cannot update quality"

        old_score = row["quality_score"]
        total_rounds = feedback_result.get("total_rounds", 0)
        status = feedback_result.get("status", "")

        # Adjust quality based on feedback outcome
        adjustment = 0
        if status == "approved":
            adjustment = max(0, 10 - total_rounds * 2)  # Quick approval = bonus
        elif total_rounds >= 4:
            adjustment = -10  # Many rounds = this pattern didn't work well

        new_score = max(0, min(100, old_score + adjustment))

        conn.execute(
            "UPDATE learned_skills SET quality_score = ?, updated_at = ? WHERE skill_id = ?",
            (new_score, datetime.now(timezone.utc).isoformat(), product_id),
        )

    return f"Skill {product_id} quality updated: {old_score} → {new_score} (rounds={total_rounds}, status={status})"


# Tag type weights — domain match is worth 3x a feature match
_TAG_WEIGHTS: dict[str, float] = {
    "domain": 3.0,
    "type": 2.5,
    "tech": 2.0,
    "entity": 1.5,
    "feature": 1.0,
    "issue": 0.5,   # Past issue categories — useful but lower signal
}


def _tag_weight(tag: str) -> float:
    """Get the weight for a tag based on its type prefix."""
    prefix = tag.split(":")[0] if ":" in tag else "feature"
    return _TAG_WEIGHTS.get(prefix, 1.0)


def find_similar_skills(
    product_name: str,
    prd: dict,
    architecture: Optional[dict] = None,
    limit: int = 3,
) -> str:
    """
    Find previously successful builds similar to the current product.

    Uses WEIGHTED tag matching — a domain-matched skill with 2 tag hits
    ranks higher than a general skill with 3 feature hits. Quality score
    is factored in so high-quality patterns surface first.

    Weights: domain (3x) > type (2.5x) > tech (2x) > entity (1.5x) > feature (1x)

    Args:
        product_name: Name of the new product being built
        prd: The PRD dict for the new product
        architecture: Optional architecture dict (if available)
        limit: Max results to return (default 3)

    Returns:
        JSON string with similar past builds ranked by weighted relevance
    """
    _init_skill_tables()

    if isinstance(prd, str):
        try:
            prd = json.loads(prd)
        except (json.JSONDecodeError, TypeError):
            prd = {}
    if isinstance(architecture, str):
        try:
            architecture = json.loads(architecture)
        except (json.JSONDecodeError, TypeError):
            architecture = {}

    current_tags = _extract_tags(product_name, prd, architecture or {})

    if not current_tags:
        return json.dumps({"similar_skills": [], "message": "No tags to match against"})

    # Build a weight map for current tags
    current_tag_weights = {tag: _tag_weight(tag) for tag in current_tags}
    max_possible_score = sum(current_tag_weights.values())

    with _conn() as conn:
        placeholders = ",".join("?" * len(current_tags))
        # Fetch matching skills with their matched tags (not just count)
        rows = conn.execute(f"""
            SELECT ls.skill_id, ls.product_name, ls.product_type, ls.domain,
                   ls.tech_stack, ls.prd_summary, ls.architecture,
                   ls.quality_score, ls.times_reused,
                   GROUP_CONCAT(st.tag) as matched_tags
            FROM learned_skills ls
            JOIN skill_tags st ON ls.skill_id = st.skill_id
            WHERE st.tag IN ({placeholders})
            GROUP BY ls.skill_id
            LIMIT ?
        """, current_tags + [limit * 3]).fetchall()  # Fetch more, then rank

        scored_results = []
        for row in rows:
            row_dict = dict(row)
            for field in ("tech_stack", "prd_summary", "architecture"):
                val = row_dict.get(field, "")
                if isinstance(val, str) and val:
                    try:
                        row_dict[field] = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Compute weighted relevance score
            matched_tags = (row_dict.get("matched_tags") or "").split(",")
            weighted_match_score = sum(
                current_tag_weights.get(tag, 1.0) for tag in matched_tags if tag
            )
            relevance = weighted_match_score / max(max_possible_score, 1.0)

            # Quality bonus (0-100 → 0-0.2 range) — high-quality skills get a boost
            quality_bonus = (row_dict["quality_score"] or 0) / 500.0

            # Combined score
            final_score = relevance + quality_bonus

            scored_results.append({
                "product_name": row_dict["product_name"],
                "domain": row_dict["domain"],
                "product_type": row_dict["product_type"],
                "tech_stack": row_dict["tech_stack"],
                "prd_summary": row_dict["prd_summary"],
                "architecture": row_dict.get("architecture", {}),
                "quality_score": row_dict["quality_score"],
                "relevance_score": round(relevance, 3),
                "weighted_score": round(final_score, 3),
                "tag_matches": len([t for t in matched_tags if t]),
                "feedback_insights": (row_dict.get("architecture") or {}).get("feedback_insights", {}),
            })

        # Sort by weighted score descending, take top N
        scored_results.sort(key=lambda x: x["weighted_score"], reverse=True)
        results = scored_results[:limit]

        # Increment reuse count only for returned skills
        for row in rows:
            row_dict = dict(row)
            if any(r["product_name"] == row_dict["product_name"] for r in results):
                conn.execute(
                    "UPDATE learned_skills SET times_reused = times_reused + 1, updated_at = ? WHERE skill_id = ?",
                    (datetime.now(timezone.utc).isoformat(), row_dict["skill_id"]),
                )

    return json.dumps({
        "similar_skills": results,
        "current_tags": current_tags,
        "message": f"Found {len(results)} similar past builds" if results else "No similar builds found — this is a new domain",
    }, indent=2)


def get_skill_context(product_name: str, prd: dict) -> str:
    """
    Get actionable context from similar past builds to inject into agent prompts.

    Like a senior engineer briefing the team: "Last time we built something like this,
    here's what worked, here's what we got wrong, here's what to watch out for."

    Returns:
        A structured text block with proven patterns AND pitfalls, or empty string.
    """
    result = json.loads(find_similar_skills(product_name, prd, limit=2))
    skills = result.get("similar_skills", [])

    if not skills:
        return ""

    lines = ["## Intelligence from Similar Past Builds\n"]
    for i, skill in enumerate(skills, 1):
        score = skill.get("quality_score", 0)
        score_label = "excellent" if score >= 85 else "good" if score >= 70 else "needs improvement"
        lines.append(f"### Reference {i}: {skill['product_name']} ({score_label}, {score}/100)")
        lines.append(f"- Domain: {skill['domain']} | Type: {skill['product_type']}")

        stack = skill.get("tech_stack", {})
        if isinstance(stack, dict) and stack:
            lines.append(f"- Proven Stack: {', '.join(f'{k}={v}' for k, v in stack.items() if v)}")

        prd_sum = skill.get("prd_summary", {})
        if isinstance(prd_sum, dict):
            features = prd_sum.get("core_features", [])
            if features:
                lines.append(f"- Features that shipped: {', '.join(features[:7])}")

        # CRITICAL: Include pitfalls from feedback loop
        insights = skill.get("feedback_insights", {})
        if isinstance(insights, dict) and insights:
            rounds = insights.get("total_rounds", 0)
            common_issues = insights.get("common_issues", {})
            if rounds > 0:
                lines.append(f"- Feedback Rounds Needed: {rounds}")
            if common_issues:
                issue_list = ", ".join(
                    f"{cat} (×{count})" for cat, count in
                    sorted(common_issues.items(), key=lambda x: x[1], reverse=True)
                )
                lines.append(f"- **PITFALLS TO AVOID**: {issue_list}")
                lines.append(f"  ↳ These categories required multiple fix rounds — get them right first!")

        lines.append("")

    lines.append(
        "**Apply these patterns strategically**: use the proven stack and features as "
        "reference, but PRIORITIZE avoiding the known pitfalls. A past build that "
        "needed 3 rounds to fix visual_ui means you should nail the design system "
        "from the start.\n"
    )
    return "\n".join(lines)
