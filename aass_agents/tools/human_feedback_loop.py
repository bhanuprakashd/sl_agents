"""
Human-in-the-Loop Feedback System — intelligent iterative refinement.

Philosophy: GET IT RIGHT THE FIRST TIME.
  - Before building: inject forge skills + past feedback patterns into prompts
  - AI-powered critic: Claude reads actual project files + PRD to find real gaps
  - Human feedback is the LAST resort, not the primary quality mechanism
  - Each loop iteration should resolve everything, not chip away slowly

After each build iteration completes and the app is live at localhost,
the system:
  1. Runs an AI self-critique (Claude reads project files vs PRD)
  2. Applies a pre-flight fix pass if issues found (before even showing to human)
  3. Presents the polished result to human
  4. If human has feedback, combines it with AI analysis for targeted rebuild
  5. Loops until approved — but the goal is approval on iteration 1

Tables:
  feedback_rounds: per-round raw feedback, analysis, plan, and outcome
"""

import json
import os
import re
import sqlite3
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "product_pipeline.db")

# ──────────────────── Weighted Keyword Intelligence ────────────────────
#
# Every keyword has a POLARITY (complaint vs compliment), INTENSITY (how
# severe), and CATEGORY.  A senior UX researcher doesn't just detect "bad"
# — they understand degree, context, and implicit dissatisfaction.

# Polarity: negative intensity (higher = worse).  Positive words get negative values.
_NEGATIVE_SIGNALS: dict[str, float] = {
    # Critical (1.0) — app is non-functional
    "broken": 1.0, "crash": 1.0, "doesn't work": 1.0, "not working": 1.0,
    "fail": 1.0, "exception": 1.0, "blank": 1.0, "white screen": 1.0,
    "500": 1.0, "fatal": 1.0, "unusable": 1.0, "completely wrong": 1.0,
    # High (0.75) — significant quality issue
    "error": 0.75, "bug": 0.75, "wrong": 0.75, "missing": 0.75,
    "ugly": 0.75, "terrible": 0.75, "horrible": 0.75, "awful": 0.75,
    "404": 0.75, "incorrect": 0.75, "messed up": 0.75,
    # Medium (0.5) — noticeable but not blocking
    "bad": 0.5, "poor": 0.5, "confusing": 0.5, "slow": 0.5,
    "weird": 0.5, "off": 0.5, "unclear": 0.5, "inconsistent": 0.5,
    "hard to": 0.5, "can't find": 0.5, "doesn't look": 0.5,
    "not great": 0.5, "needs work": 0.5, "not right": 0.5,
    # Low (0.25) — minor complaints
    "could be better": 0.25, "slightly": 0.25, "a bit": 0.25,
    "minor": 0.25, "small issue": 0.25, "nitpick": 0.25,
}

_POSITIVE_SIGNALS: dict[str, float] = {
    "good": 0.5, "great": 0.75, "nice": 0.5, "love": 0.75,
    "perfect": 1.0, "excellent": 1.0, "well done": 0.75,
    "better": 0.5, "improved": 0.5, "fixed": 0.5,
    "clean": 0.5, "smooth": 0.5, "beautiful": 0.75,
}

_APPROVAL_PHRASES = frozenset([
    "approved", "looks good", "ship it", "done", "perfect",
    "great", "love it", "lgtm", "accept", "good to go",
    "looks great", "well done", "excellent", "all good",
    "no changes", "nothing to change", "satisfied",
])

# ── Category keywords with POLARITY and SEVERITY ────────────────────
# Each entry: (keyword, is_complaint: bool, base_severity: str)
# is_complaint=True means this keyword signals a problem (not a neutral mention)

_CATEGORY_SIGNALS: dict[str, list[tuple[str, bool, str]]] = {
    "visual_ui": [
        # Complaint signals (is_complaint=True)
        ("ugly", True, "high"), ("bad color", True, "high"), ("bad design", True, "high"),
        ("hard to read", True, "high"), ("low contrast", True, "high"),
        ("looks terrible", True, "critical"), ("looks awful", True, "critical"),
        ("misaligned", True, "medium"), ("cluttered", True, "medium"),
        ("too small", True, "medium"), ("too big", True, "medium"),
        ("cramped", True, "medium"), ("no spacing", True, "medium"),
        # Neutral mentions (is_complaint=False) — only flagged if near negative context
        ("color", False, "medium"), ("colour", False, "medium"),
        ("font", False, "medium"), ("layout", False, "medium"),
        ("spacing", False, "medium"), ("alignment", False, "medium"),
        ("design", False, "medium"), ("theme", False, "medium"),
        ("css", False, "medium"), ("style", False, "medium"),
        ("icon", False, "medium"), ("logo", False, "medium"),
        ("border", False, "medium"), ("shadow", False, "medium"),
        ("animation", False, "medium"), ("hover", False, "medium"),
    ],
    "functionality": [
        ("broken", True, "critical"), ("doesn't work", True, "critical"),
        ("not working", True, "critical"), ("crash", True, "critical"),
        ("500", True, "critical"), ("exception", True, "critical"),
        ("blank page", True, "critical"), ("white screen", True, "critical"),
        ("error", True, "high"), ("bug", True, "high"),
        ("404", True, "high"), ("fail", True, "high"),
        ("undefined", True, "high"), ("null", True, "high"),
        ("empty page", True, "high"), ("missing", True, "medium"),
    ],
    "content": [
        ("lorem", True, "high"), ("ipsum", True, "high"),
        ("placeholder", True, "high"), ("dummy", True, "medium"),
        ("fake data", True, "medium"), ("sample data", True, "medium"),
        ("text", False, "low"), ("copy", False, "low"),
        ("label", False, "low"), ("heading", False, "low"),
    ],
    "performance": [
        ("freezes", True, "critical"), ("hang", True, "critical"),
        ("slow", True, "high"), ("lag", True, "high"),
        ("timeout", True, "high"), ("takes forever", True, "high"),
        ("loading", False, "medium"), ("spinner", False, "medium"),
    ],
    "ux": [
        ("confusing", True, "high"), ("hard to find", True, "high"),
        ("can't find", True, "high"), ("where is", True, "high"),
        ("not intuitive", True, "high"), ("unclear", True, "medium"),
        ("too many clicks", True, "medium"), ("hidden", True, "medium"),
        ("navigation", False, "medium"), ("flow", False, "medium"),
        ("mobile", False, "medium"), ("responsive", False, "medium"),
        ("scroll", False, "low"),
    ],
    "feature_gap": [
        ("should have", True, "high"), ("missing feature", True, "high"),
        ("no way to", True, "high"), ("can't do", True, "high"),
        ("unable to", True, "high"), ("expected", True, "medium"),
        ("need", True, "medium"), ("want", True, "medium"),
        ("add", False, "medium"),
    ],
}

# Severity ordering for comparisons
_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _compute_sentiment_score(text: str) -> tuple[float, float]:
    """
    Compute weighted negative and positive scores.

    Returns (negative_score, positive_score) where each is 0.0-1.0+ weighted.
    A senior researcher weighs "completely broken" heavier than "slightly off".
    """
    neg_score = 0.0
    pos_score = 0.0

    for phrase, weight in _NEGATIVE_SIGNALS.items():
        if re.search(r'\b' + re.escape(phrase) + r'\b', text):
            neg_score += weight

    for phrase, weight in _POSITIVE_SIGNALS.items():
        if re.search(r'\b' + re.escape(phrase) + r'\b', text):
            # Check if positive word is negated (within 15-char prefix window)
            idx = text.find(phrase)
            if idx >= 0:
                prefix = text[max(0, idx - 15):idx]
                if re.search(r"\b(not|don'?t|doesn'?t|no|never|isn'?t|wasn'?t)\b", prefix):
                    neg_score += weight  # Negated positive = negative
                else:
                    pos_score += weight

    return neg_score, pos_score


# ─────────────────────────── DB Layer ───────────────────────────

def _db_path() -> str:
    return os.environ.get("PRODUCT_DB_PATH", _DEFAULT_DB)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init_feedback_table() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback_rounds (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id       TEXT    NOT NULL,
                round_number     INTEGER NOT NULL,
                raw_feedback     TEXT    NOT NULL,
                parsed_issues    TEXT,
                inferred_gaps    TEXT,
                self_critique    TEXT,
                improvement_plan TEXT,
                build_output     TEXT,
                user_sentiment   TEXT,
                duration_s       REAL,
                created_at       TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_product
            ON feedback_rounds(product_id)
        """)


def save_feedback_round(
    product_id: str,
    round_number: int,
    raw_feedback: str,
    parsed_issues: list[dict[str, Any]],
    inferred_gaps: list[dict[str, Any]],
    self_critique: list[dict[str, Any]],
    improvement_plan: list[dict[str, Any]],
    build_output: str,
    user_sentiment: str,
    duration_s: float = 0.0,
) -> str:
    """Persist one feedback round for learning and audit."""
    _init_feedback_table()
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO feedback_rounds
               (product_id, round_number, raw_feedback, parsed_issues,
                inferred_gaps, self_critique, improvement_plan,
                build_output, user_sentiment, duration_s, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                product_id, round_number, raw_feedback,
                json.dumps(parsed_issues), json.dumps(inferred_gaps),
                json.dumps(self_critique), json.dumps(improvement_plan),
                build_output[:2000] if build_output else "",
                user_sentiment, duration_s, now,
            ),
        )
    return f"Feedback round {round_number} saved for {product_id}"


def get_feedback_history(product_id: str, limit: int = 50) -> str:
    """Return all feedback rounds for a product as JSON."""
    _init_feedback_table()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT round_number, raw_feedback, parsed_issues,
                      inferred_gaps, self_critique, improvement_plan,
                      user_sentiment, duration_s, created_at
               FROM feedback_rounds
               WHERE product_id = ?
               ORDER BY round_number ASC
               LIMIT ?""",
            (product_id, limit),
        ).fetchall()

    rounds = []
    for row in rows:
        r = dict(row)
        for key in ("parsed_issues", "inferred_gaps", "self_critique", "improvement_plan"):
            try:
                r[key] = json.loads(r[key]) if r[key] else []
            except (json.JSONDecodeError, TypeError):
                r[key] = []
        rounds.append(r)

    return json.dumps({"product_id": product_id, "rounds": rounds}, indent=2)


def get_feedback_patterns(limit: int = 20) -> str:
    """
    Aggregate common feedback patterns across ALL products.

    Returns the most frequently reported issue categories and descriptions
    so future builds can preemptively address them.
    """
    _init_feedback_table()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT parsed_issues FROM feedback_rounds
               WHERE user_sentiment != 'approved'
               ORDER BY created_at DESC
               LIMIT 200""",
        ).fetchall()

    category_counts: dict[str, int] = {}
    example_issues: dict[str, list[str]] = {}
    for row in rows:
        try:
            issues = json.loads(row["parsed_issues"]) if row["parsed_issues"] else []
        except (json.JSONDecodeError, TypeError):
            continue
        for issue in issues:
            cat = issue.get("category", "unknown")
            desc = issue.get("description", "")
            category_counts[cat] = category_counts.get(cat, 0) + 1
            if cat not in example_issues:
                example_issues[cat] = []
            if len(example_issues[cat]) < 3 and desc:
                example_issues[cat].append(desc)

    patterns = sorted(
        [
            {"category": cat, "count": count, "examples": example_issues.get(cat, [])}
            for cat, count in category_counts.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )[:limit]

    return json.dumps({"patterns": patterns}, indent=2)


# ──────────────────── Feedback Analysis Engine ────────────────────

def classify_user_sentiment(raw_feedback: str) -> str:
    """
    Classify feedback as approved / positive / mixed / negative.

    Uses weighted scoring — intensity matters. "Slightly off" is not the same
    as "completely broken". A senior UX researcher reads between the lines.
    """
    text = raw_feedback.strip().lower()
    if not text:
        return "approved"  # empty input = no complaints

    neg_score, pos_score = _compute_sentiment_score(text)

    # Strong negative signal overrides everything
    if neg_score >= 0.75:
        if pos_score >= 0.5:
            return "mixed"  # "the nav is good but colors are terrible"
        return "negative"

    # Mild negative — check if also positive (mixed) or weak negative
    if neg_score > 0:
        if pos_score >= neg_score:
            return "mixed"  # Equal or more positive than negative
        return "negative"

    # No negative signals — check for explicit approval phrases
    for phrase in _APPROVAL_PHRASES:
        if " " in phrase:
            if phrase in text:
                return "approved"
        else:
            if re.search(r'\b' + re.escape(phrase) + r'\b', text):
                idx = text.find(phrase)
                prefix = text[max(0, idx - 15):idx]
                if not re.search(r"\b(not|don'?t|doesn'?t|no|never|isn'?t)\b", prefix):
                    return "approved"

    # Strong positive with no negatives = effectively approved (user is satisfied)
    if pos_score >= 1.0:
        return "approved"

    # Moderate positive without explicit approval
    if pos_score >= 0.5:
        return "positive"

    # Has content but no recognizable signals — assume complaint
    return "negative"


def parse_explicit_feedback(raw_feedback: str) -> list[dict[str, str]]:
    """
    Extract structured issues from raw feedback with polarity awareness.

    A senior PM doesn't treat "I like the color" the same as "color is ugly".
    Only flags neutral keywords as issues when they appear in negative context.
    Returns list of {category, description, severity, source, confidence}.
    """
    text = raw_feedback.strip().lower()
    if not text:
        return []

    # Overall polarity of the feedback (used for neutral keyword disambiguation)
    neg_score, pos_score = _compute_sentiment_score(text)
    overall_negative = neg_score > pos_score

    issues: list[dict[str, str]] = []
    matched: dict[str, str] = {}  # category → highest severity

    for category, signals in _CATEGORY_SIGNALS.items():
        for keyword, is_complaint, severity in signals:
            if keyword not in text:
                continue

            if is_complaint:
                # Direct complaint — always flag
                existing_sev = matched.get(category, "low")
                if _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK.get(existing_sev, 0):
                    matched[category] = severity
            elif overall_negative:
                # Neutral keyword BUT feedback is overall negative — likely a complaint
                existing_sev = matched.get(category, "low")
                # Downgrade severity since we're inferring complaint from context
                contextual_sev = "medium" if severity in ("high", "critical") else "low"
                if _SEVERITY_RANK.get(contextual_sev, 0) > _SEVERITY_RANK.get(existing_sev, 0):
                    matched[category] = contextual_sev

    if not matched:
        if overall_negative:
            matched["general"] = "medium"
        else:
            return []  # Positive feedback with no complaint keywords — not an issue

    for category, severity in matched.items():
        confidence = "high" if any(
            kw in text for kw, is_c, _ in _CATEGORY_SIGNALS.get(category, []) if is_c
        ) else "medium"
        issues.append({
            "category": category,
            "description": raw_feedback.strip(),
            "severity": severity,
            "source": "explicit",
            "confidence": confidence,
        })

    return issues


def _detect_product_type(prd: str) -> str:
    """
    Detect product type from PRD text for domain-aware inference.

    A smart QA lead knows that a dashboard app needs data-viz checks,
    e-commerce needs checkout flow checks, SaaS needs onboarding checks.
    """
    text = (prd or "").lower()
    type_signals: dict[str, list[str]] = {
        "dashboard": ["dashboard", "analytics", "chart", "metric", "report", "monitor", "visualization"],
        "ecommerce": ["shop", "cart", "checkout", "product listing", "payment", "order", "store"],
        "saas": ["subscription", "onboarding", "billing", "tenant", "plan", "pricing", "saas"],
        "content_platform": ["blog", "article", "cms", "publish", "editor", "post"],
        "marketplace": ["marketplace", "listing", "buyer", "seller", "listing"],
        "social": ["profile", "feed", "follow", "post", "comment", "community"],
        "management": ["manage", "crud", "inventory", "task", "project", "schedule", "farm"],
        "form_heavy": ["form", "survey", "registration", "input", "submit", "wizard"],
    }
    for ptype, keywords in type_signals.items():
        matches = sum(1 for kw in keywords if kw in text)
        if matches >= 2:
            return ptype
    return "general"


def infer_implicit_gaps(
    explicit_issues: list[dict[str, str]],
    prd: str = "",
) -> list[dict[str, str]]:
    """
    Infer broader issues from explicit feedback — product-type-aware.

    A smart QA lead doesn't apply blanket rules. They know that if a DASHBOARD
    app has color problems, the charts probably have readability issues too.
    But they won't check checkout flows for a dashboard.
    """
    if not explicit_issues:
        return []

    categories = {issue["category"] for issue in explicit_issues}
    product_type = _detect_product_type(prd)
    inferred: list[dict[str, str]] = []

    # ── Universal inference rules (always relevant) ──────────────
    _universal_rules: dict[str, list[str]] = {
        "visual_ui": [
            "Review entire visual design system: color palette, spacing, typography consistency",
        ],
        "functionality": [
            "Verify all form submissions work end-to-end with validation",
            "Check all navigation links resolve correctly (no dead links)",
        ],
        "content": [
            "Replace ALL placeholder/dummy content with realistic domain-specific data",
        ],
        "performance": [
            "Add loading skeletons for async data fetches",
        ],
        "ux": [
            "Review full navigation flow — every page reachable within 2 clicks",
        ],
        "feature_gap": [
            "Cross-check ALL features listed in original PRD — flag any not yet implemented",
        ],
    }

    # ── Product-type-specific inference rules ──────────────
    _product_rules: dict[str, dict[str, list[str]]] = {
        "dashboard": {
            "visual_ui": [
                "Verify chart/graph colors are distinguishable and colorblind-safe",
                "Check data table readability: row striping, column alignment, number formatting",
            ],
            "functionality": [
                "Verify data refresh/polling works without memory leaks",
                "Test filter and date-range controls update all dependent charts",
            ],
            "ux": [
                "Ensure KPI cards are scannable at a glance with proper number formatting",
            ],
        },
        "ecommerce": {
            "visual_ui": [
                "Check product image grid consistency and zoom functionality",
            ],
            "functionality": [
                "Test complete checkout flow: cart → address → payment → confirmation",
                "Verify cart persists across page navigation and browser refresh",
            ],
            "ux": [
                "Ensure product search and filter work with zero-results fallback",
            ],
        },
        "saas": {
            "functionality": [
                "Verify onboarding flow covers all required setup steps",
                "Test subscription/billing integration end-to-end",
            ],
            "ux": [
                "Check that free-trial vs paid features are clearly distinguished",
            ],
        },
        "management": {
            "visual_ui": [
                "Verify data tables are sortable with active column indicator",
            ],
            "functionality": [
                "Test all CRUD operations complete without errors or data loss",
                "Verify cascading deletes and referential integrity",
            ],
            "ux": [
                "Check bulk-action workflows (select multiple → action) are intuitive",
            ],
        },
        "form_heavy": {
            "functionality": [
                "Test all form validations: required fields, format checks, error messages",
                "Verify multi-step form state persists when navigating back",
            ],
            "ux": [
                "Ensure form error messages appear inline next to the relevant field",
                "Check tab-order and keyboard navigation through all form fields",
            ],
        },
    }

    for cat in categories:
        # Apply universal rules
        for desc in _universal_rules.get(cat, []):
            inferred.append({
                "category": cat,
                "description": desc,
                "severity": "medium",
                "source": "inferred",
            })
        # Apply product-type-specific rules
        product_specific = _product_rules.get(product_type, {}).get(cat, [])
        for desc in product_specific:
            inferred.append({
                "category": cat,
                "description": desc,
                "severity": "medium",
                "source": "inferred",
            })

    return inferred


def self_critique_against_prd(
    prd: str,
    build_url: str,
    qa_report: str,
) -> list[dict[str, str]]:
    """
    Static fallback: check PRD features against QA report.

    Used when AI critique is unavailable. For real analysis, use
    run_ai_critique() which reads actual project files.
    """
    gaps: list[dict[str, str]] = []

    prd_data: dict[str, Any] = {}
    try:
        prd_data = json.loads(prd) if prd.strip().startswith("{") else {}
    except (json.JSONDecodeError, TypeError):
        pass

    qa_lower = (qa_report or "").lower()
    features = prd_data.get("core_features", [])
    if isinstance(features, list):
        for feature in features:
            feature_name = feature if isinstance(feature, str) else feature.get("name", "")
            if feature_name and feature_name.lower() not in qa_lower:
                gaps.append({
                    "category": "prd_gap",
                    "description": f"Feature '{feature_name}' from PRD not verified in QA report",
                    "severity": "high",
                    "source": "self_critique",
                })

    common_gaps = [
        "Verify error states: what happens when API fails, network is down, or data is empty",
        "Check loading states: all async operations should show progress indicators",
        "Verify form validation: required fields, format checks, user-friendly error messages",
        "Check empty states: what does each page look like with zero data",
    ]
    for desc in common_gaps:
        gaps.append({
            "category": "quality",
            "description": desc,
            "severity": "low",
            "source": "self_critique",
        })

    return gaps


# ─────────────────── AI-Powered Critic ───────────────────

_SKIP_DIRS = frozenset([
    "node_modules", ".next", ".nuxt", "dist", "build", ".output",
    "__pycache__", ".git", ".svelte-kit", ".vercel", ".turbo",
    "coverage", ".cache", "vendor", "target",
])

# File importance ranking — higher priority files are read first
_FILE_PRIORITY: list[tuple[str, int]] = [
    # Entry points & layouts (most important)
    ("index.html", 100), ("app.html", 100), ("layout.tsx", 95), ("layout.jsx", 95),
    ("page.tsx", 90), ("page.jsx", 90), ("App.tsx", 90), ("App.jsx", 90),
    ("App.vue", 90), ("App.svelte", 90), ("main.ts", 85), ("main.js", 85),
    ("app.ts", 85), ("app.js", 85), ("app.py", 85), ("server.py", 85),
    # Config (understanding the stack)
    ("package.json", 80), ("tailwind.config.js", 70), ("tailwind.config.ts", 70),
    # Styles
    ("globals.css", 75), ("styles.css", 75), ("app.css", 75), ("index.css", 75),
]


def _file_importance(fpath: Path, project_path: Path) -> int:
    """Score a file's importance for AI review. Higher = read first."""
    name = fpath.name
    for pattern_name, score in _FILE_PRIORITY:
        if name == pattern_name:
            return score

    # Heuristic scoring by extension and location
    ext = fpath.suffix.lower()
    rel = str(fpath.relative_to(project_path))
    score = 30  # base

    # Extension bonus
    ext_scores = {".html": 25, ".tsx": 20, ".jsx": 20, ".vue": 20, ".svelte": 20,
                  ".css": 15, ".ts": 15, ".js": 15, ".py": 15}
    score += ext_scores.get(ext, 0)

    # Shallow depth bonus (closer to root = more important)
    depth = len(fpath.relative_to(project_path).parts)
    score += max(0, 15 - depth * 3)

    # Route/page/component keywords
    if any(kw in rel.lower() for kw in ["page", "route", "layout", "component", "view"]):
        score += 10

    return score


def _read_project_files(project_dir: str, max_chars: int = 15000) -> str:
    """
    Read key source files from the project for AI analysis.

    Like a senior code reviewer, reads the MOST IMPORTANT files first:
    entry points, layouts, pages, then styles, then config. Truncates
    at file boundaries (never mid-file) to preserve coherent context.
    """
    project_path = Path(project_dir)
    if not project_path.exists():
        return "(project directory not found)"

    # Collect all candidate files
    candidates: list[tuple[Path, int]] = []
    for fpath in project_path.rglob("*"):
        if fpath.is_dir():
            continue
        # Skip junk directories
        if any(skip in fpath.parts for skip in _SKIP_DIRS):
            continue
        # Skip hidden files
        if fpath.name.startswith("."):
            continue
        # Only source files
        if fpath.suffix.lower() not in (
            ".html", ".tsx", ".jsx", ".vue", ".svelte", ".ts", ".js",
            ".css", ".scss", ".json", ".py", ".rb", ".go", ".rs",
        ):
            continue
        # Skip large generated files
        try:
            size = fpath.stat().st_size
            if size > 100_000:  # >100KB is likely generated
                continue
        except OSError:
            continue

        importance = _file_importance(fpath, project_path)
        candidates.append((fpath, importance))

    # Sort by importance descending
    candidates.sort(key=lambda x: x[1], reverse=True)

    collected: list[str] = []
    total_chars = 0

    for fpath, importance in candidates:
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        header = f"\n--- {fpath.relative_to(project_path)} (importance:{importance}) ---\n"
        file_block = header + content

        # Never truncate mid-file — either include fully or skip
        if total_chars + len(file_block) > max_chars:
            # If we haven't collected anything yet, include truncated first file
            if not collected and len(content) > 200:
                collected.append(header + content[:max_chars - 100] + "\n...(truncated)")
                break
            continue  # Skip this file, try smaller ones

        collected.append(file_block)
        total_chars += len(file_block)

    return "\n".join(collected) if collected else "(no source files found)"


def run_ai_critique(
    project_dir: str,
    prd: str,
    build_url: str,
    human_feedback: str = "",
) -> list[dict[str, str]]:
    """
    AI-powered critique: Claude reads actual project files against PRD.

    This is the REAL critic. Like a senior product reviewer at a top company:
    - Reads the actual source code (prioritized by importance)
    - Compares against PRD requirements systematically
    - Understands what the HUMAN meant (not just what they said)
    - Returns structured, actionable issues with confidence levels
    - Domain-aware: knows what matters for THIS type of product
    """
    from tools.claude_code_tools import _run_claude

    source_code = _read_project_files(project_dir)
    product_type = _detect_product_type(prd)

    feedback_section = ""
    if human_feedback:
        feedback_section = f"""
## Human Feedback (HIGHEST PRIORITY)
The user reviewed the live app and said:
"{human_feedback}"

Your job: understand what they MEANT, not just what they said.
- If they say "colors are bad" → they care about the ENTIRE visual experience
- If they mention one bug → check for similar bugs in related features
- If they say "confusing" → review the entire information architecture
- Think: what would this person ALSO complain about if they kept using the app?
"""

    # Domain-aware review focus
    domain_focus: dict[str, str] = {
        "dashboard": (
            "- Verify all charts/graphs render with real data (no empty states unless data truly empty)\n"
            "- Check number formatting (commas, decimals, currency symbols, percentage signs)\n"
            "- Verify KPI cards show meaningful metrics with proper units\n"
            "- Test date-range/filter controls actually update all dependent visualizations"
        ),
        "ecommerce": (
            "- Test complete purchase flow: browse → cart → checkout → confirmation\n"
            "- Verify product images, prices, and descriptions are realistic\n"
            "- Check cart state persistence across page navigation\n"
            "- Verify payment form validation and error handling"
        ),
        "management": (
            "- Test all CRUD operations for every entity (create, read, update, delete)\n"
            "- Verify data tables: sorting, filtering, pagination all work\n"
            "- Check that forms validate all required fields with clear error messages\n"
            "- Test cascading operations (delete parent → what happens to children?)"
        ),
        "form_heavy": (
            "- Test every form field: validation, error messages, required/optional indication\n"
            "- Verify multi-step forms preserve state when navigating back\n"
            "- Check all dropdown options are populated with realistic values\n"
            "- Test keyboard navigation and tab order through all forms"
        ),
    }
    extra_focus = domain_focus.get(product_type, "")
    domain_section = f"\n## Domain-Specific Checks ({product_type} app):\n{extra_focus}\n" if extra_focus else ""

    critique_prompt = f"""You are a senior product reviewer at a world-class technology company.
You review products before they ship to real users. Your standards are extremely high.

The app is running at {build_url}. Read the source code below and compare against the PRD.

{feedback_section}

## PRD / Requirements:
{prd[:4000] if prd else "(no PRD provided)"}
{domain_section}
## Source Code:
{source_code}

## Review Protocol
For each issue, output ONE LINE in this exact format:
ISSUE|<severity>|<category>|<confidence>|<description with file reference>

Severity: critical (blocks shipping), high (must fix), medium (should fix)
Category: functionality, visual_ui, ux, content, feature_gap, performance, quality
Confidence: high (verified in code), medium (likely based on patterns), low (suspected)

## What to Look For (in priority order):
1. FUNCTIONALITY: Features in the PRD that are missing or incomplete in the code
2. BROKEN: Errors, dead links, missing error handling, empty API responses
3. CONTENT: Placeholder/lorem/dummy data that should be realistic domain data
4. UX: Confusing navigation, missing feedback (loading/error/empty states)
5. VISUAL: Inconsistent styling, poor contrast, broken layouts
6. DATA: Wrong units, labels, or formats for the domain
{f"7. HUMAN FEEDBACK: Everything the user mentioned, plus related issues" if human_feedback else ""}

## DO NOT Flag:
- Code style or architecture preferences
- Things that demonstrably work correctly
- Theoretical performance issues without evidence in the code
- Missing tests or documentation

Output ONLY issue lines. If the app genuinely meets all PRD requirements with no issues:
APPROVED|none|none|high|No significant issues found
"""

    result = _run_claude(project_dir, critique_prompt, timeout=300)

    if not result.get("ok"):
        return self_critique_against_prd(prd, build_url, "")

    # Robust parsing — extract ISSUE lines from potentially messy output
    issues: list[dict[str, str]] = []
    output = result.get("output", "")

    for line in output.strip().split("\n"):
        line = line.strip()

        # Handle APPROVED at any point
        if "APPROVED|" in line:
            # Only trust if it's the primary output (not buried in explanation)
            if line.startswith("APPROVED|") or line.startswith("APPROVED"):
                return []

        if "ISSUE|" not in line:
            continue

        # Extract the ISSUE portion even if there's prefix text
        issue_start = line.index("ISSUE|")
        issue_line = line[issue_start:]
        parts = issue_line.split("|")

        if len(parts) >= 5:
            # New format: ISSUE|severity|category|confidence|description
            severity = parts[1].strip().lower()
            category = parts[2].strip().lower()
            confidence = parts[3].strip().lower()
            description = "|".join(parts[4:]).strip()  # Handle pipes in description

            # Validate severity
            if severity not in ("critical", "high", "medium"):
                severity = "medium"
            # Validate category
            valid_cats = {"functionality", "visual_ui", "ux", "content",
                          "feature_gap", "performance", "quality"}
            if category not in valid_cats:
                category = "quality"

            issues.append({
                "category": category,
                "description": description,
                "severity": severity,
                "confidence": confidence,
                "source": "ai_critique",
            })
        elif len(parts) >= 4:
            # Legacy format: ISSUE|severity|category|description
            issues.append({
                "category": parts[2].strip().lower(),
                "description": parts[3].strip(),
                "severity": parts[1].strip().lower(),
                "confidence": "medium",
                "source": "ai_critique",
            })

    return issues


def get_prebuild_quality_context(product_name: str, prd: str) -> str:
    """
    Build a quality context block from forge skills + past feedback patterns.

    Injected into build prompts BEFORE building so the first iteration
    already avoids known pitfalls. This is how we minimize feedback loops.
    """
    sections: list[str] = []

    # 1. Get learned skills from similar past builds
    try:
        from tools.skill_memory import get_skill_context
        skill_ctx = get_skill_context(product_name, prd if isinstance(prd, dict) else {})
        if skill_ctx:
            sections.append(skill_ctx)
    except Exception:
        pass

    # 2. Get common feedback patterns to preemptively avoid
    try:
        patterns_json = get_feedback_patterns(limit=10)
        patterns = json.loads(patterns_json).get("patterns", [])
        if patterns:
            lines = ["## Common Issues to Preemptively Avoid\n"]
            lines.append("Past builds frequently received human feedback about these issues.")
            lines.append("Address ALL of them proactively in this build:\n")
            for p in patterns:
                examples = "; ".join(p.get("examples", [])[:2])
                lines.append(f"- **{p['category']}** (reported {p['count']}x): {examples}")
            lines.append("")
            sections.append("\n".join(lines))
    except Exception:
        pass

    if not sections:
        return ""

    return "\n".join(sections)


def generate_improvement_plan(
    explicit: list[dict[str, str]],
    inferred: list[dict[str, str]],
    self_critique: list[dict[str, str]],
    prior_rounds: list[dict[str, Any]],
    max_items: int = 10,
) -> list[dict[str, Any]]:
    """
    Merge all analysis sources into a prioritized, deduplicated improvement plan.

    Escalates issues that appeared in prior rounds but weren't fixed.
    Caps at max_items to avoid overwhelming the rebuild prompt.
    """
    # Collect recurring categories from prior rounds
    prior_categories: dict[str, int] = {}
    for pr in prior_rounds:
        issues = pr.get("parsed_issues", [])
        if isinstance(issues, str):
            try:
                issues = json.loads(issues)
            except (json.JSONDecodeError, TypeError):
                issues = []
        for issue in issues:
            cat = issue.get("category", "")
            prior_categories[cat] = prior_categories.get(cat, 0) + 1

    # Combine all items with priority scoring
    all_items: list[dict[str, Any]] = []

    severity_score = {"critical": 100, "high": 75, "medium": 50, "low": 25}
    source_score = {"explicit": 50, "ai_critique": 45, "inferred": 20, "self_critique": 10}

    for item in explicit + inferred + self_critique:
        score = severity_score.get(item.get("severity", "medium"), 50)
        score += source_score.get(item.get("source", ""), 0)

        # Escalate recurring issues
        cat = item.get("category", "")
        if cat in prior_categories:
            recurrence = prior_categories[cat]
            score += recurrence * 30  # big boost for repeat issues
            if item.get("severity") != "critical":
                item = {**item, "severity": "high"}  # escalate

        all_items.append({**item, "_score": score})

    # Deduplicate by category (keep highest scored per category)
    seen_cats: dict[str, dict[str, Any]] = {}
    for item in sorted(all_items, key=lambda x: x["_score"], reverse=True):
        cat = item.get("category", "unknown")
        if cat not in seen_cats:
            seen_cats[cat] = item
        else:
            # Merge descriptions if same category but different source
            existing = seen_cats[cat]
            if item.get("source") != existing.get("source"):
                merged_desc = existing["description"]
                new_desc = item["description"]
                if new_desc not in merged_desc:
                    seen_cats[cat] = {
                        **existing,
                        "description": f"{merged_desc}. Additionally: {new_desc}",
                    }

    # Sort by score, cap, add priority numbers
    plan = sorted(seen_cats.values(), key=lambda x: x.get("_score", 0), reverse=True)
    plan = plan[:max_items]

    result = []
    for i, item in enumerate(plan, 1):
        result.append({
            "priority": i,
            "category": item.get("category", "general"),
            "description": item.get("description", ""),
            "severity": item.get("severity", "medium"),
            "source": item.get("source", "unknown"),
        })

    return result


# ─────────────────── Prompt Builder ───────────────────

def build_targeted_prompt(
    plan: list[dict[str, Any]],
    build_url: str,
    prd: str,
    round_number: int = 1,
    max_rounds: int = 5,
) -> str:
    """
    Build a focused Claude CLI prompt for targeted improvements.

    Prompt intensity increases with each round — later rounds demand
    more thoroughness since we're running out of iterations.
    """
    items_text = "\n".join(
        f"{item['priority']}. [{item['category'].upper()}] (severity: {item['severity']}) "
        f"{item['description']}"
        for item in plan
    )

    prd_summary = prd[:2000] if prd else "(no PRD available)"

    # Progressive urgency — later rounds get stricter instructions
    rounds_left = max(max_rounds - round_number, 0)
    if rounds_left <= 1:
        urgency = (
            "CRITICAL: This is one of the LAST iterations. The human has already "
            "given feedback multiple times. You MUST resolve EVERY issue completely "
            "this time. Do not leave partial fixes. Think like a senior developer "
            "doing a final quality pass before shipping to a paying customer."
        )
    elif rounds_left <= 2:
        urgency = (
            "IMPORTANT: The human has already reviewed this app and found issues. "
            "Fix every listed issue thoroughly. Also look for any OTHER issues "
            "you notice while fixing — fix those too. Aim for zero complaints."
        )
    else:
        urgency = (
            "Fix the listed issues carefully. Also self-reflect: as you read the "
            "code, if you notice anything else that looks wrong or incomplete, "
            "fix that too."
        )

    return f"""IMPORTANT: This is an EXISTING project in the current directory.
Read ALL existing files first to understand current state.
Do NOT recreate or overwrite files — only MODIFY what needs fixing.
Preserve all working functionality. Do NOT break anything that already works.

{urgency}

The app is currently running at {build_url}.
Iteration {round_number}/{max_rounds} — {rounds_left} rounds remaining.

## Issues to Fix (in priority order):

{items_text}

## Self-Reflection Requirement:
After fixing the listed issues, re-read the modified files and ask yourself:
- Does this look like a professional, polished app?
- Would a real user be satisfied with this?
- Are there obvious issues I can see that weren't in the list?
If yes, fix them now. Don't wait for the next round.

## Original Requirements (for reference):
{prd_summary}

## Rules:
- Fix ALL listed issues completely, not partially.
- Preserve all working functionality — zero regressions.
- After making changes, restart the dev server so the fixes are live.
- Think like a human reviewer: would YOU approve this app?
"""


# ─────────────────── Console Interaction ───────────────────

def _print_header(
    round_number: int,
    max_rounds: int,
    build_url: str,
    iteration_summary: str = "",
    preflight_summary: str = "",
) -> None:
    """Print a clean feedback prompt header."""
    print(f"\n{'=' * 64}")
    print(f"  ITERATION {round_number}/{max_rounds} — Review the app")
    print(f"{'=' * 64}")
    print(f"  App URL: {build_url}")
    if preflight_summary:
        print(f"  AI Pre-flight: {preflight_summary}")
    if iteration_summary:
        print(f"  Changes: {iteration_summary}")
    print(f"{'─' * 64}")
    print("  Review the app in your browser, then:")
    print("    - Describe what needs improvement")
    print("    - Or type 'approved' / 'looks good' to accept")
    print(f"{'─' * 64}")


def collect_feedback(
    product_id: str,
    build_url: str,
    round_number: int,
    max_rounds: int,
    iteration_summary: str = "",
    preflight_summary: str = "",
) -> str:
    """Collect feedback from user via console input."""
    _print_header(round_number, max_rounds, build_url, iteration_summary, preflight_summary)
    try:
        feedback = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        feedback = "approved"
    return feedback


# ─────────────────── Main Feedback Loop ───────────────────

_DEFAULT_MAX_ROUNDS = 5


def _ask_max_rounds() -> int:
    """Ask the user how many feedback rounds they want."""
    print(f"\n{'─' * 64}")
    print(f"  How many feedback rounds? (default: {_DEFAULT_MAX_ROUNDS})")
    print("    - Enter a number (e.g. 3, 5, 10)")
    print(f"    - Press Enter for default ({_DEFAULT_MAX_ROUNDS})")
    print(f"{'─' * 64}")
    try:
        raw = input("  Rounds> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return _DEFAULT_MAX_ROUNDS

    if not raw:
        return _DEFAULT_MAX_ROUNDS

    try:
        n = int(raw)
        return max(n, 1)
    except ValueError:
        return _DEFAULT_MAX_ROUNDS


def run_feedback_loop(
    product_id: str,
    project_name: str,
    build_url: str,
    prd: str = "",
    qa_report: str = "",
    max_rounds: int = 0,
) -> str:
    """
    Run the human-in-the-loop feedback loop with AI-powered self-reflection.

    Design philosophy: GET IT RIGHT FIRST, minimize loops.

    Before showing to human:
      - Runs AI critique (Claude reads project files vs PRD)
      - Auto-fixes issues found (pre-flight pass)
      - Only THEN presents to human

    Each round gets progressively smarter:
      - Round 1: AI pre-flight + human review
      - Round 2-3: AI critique includes human's prior feedback patterns
      - Round 4-5: Maximum urgency — "last chance" thoroughness

    Args:
        product_id: UUID for tracking
        project_name: Folder name under claude_works/
        build_url: Current localhost URL of the running app
        prd: Original PRD text/JSON for self-critique
        qa_report: QA test results for gap analysis
        max_rounds: 0 = ask user (default 5), >0 = fixed cap

    Returns:
        JSON string with feedback loop results
    """
    from tools.claude_code_tools import _run_claude, _detect_url, CLAUDE_WORKS_ROOT

    project_dir = str(CLAUDE_WORKS_ROOT / project_name)
    current_url = build_url

    # Ask user how many rounds
    if max_rounds <= 0:
        max_rounds = _ask_max_rounds()

    _init_feedback_table()

    print(f"\n  Feedback loop: {max_rounds} rounds max (goal: approve on round 1)")

    # ── AI Pre-Flight Critique (before showing to human) ──────────
    print(f"\n  Running AI pre-flight critique...")
    preflight_issues = run_ai_critique(project_dir, prd, current_url)
    preflight_summary = ""

    if preflight_issues:
        print(f"  AI found {len(preflight_issues)} issues — auto-fixing before human review...")

        preflight_plan = [
            {"priority": i + 1, **issue}
            for i, issue in enumerate(preflight_issues[:8])
        ]
        preflight_prompt = build_targeted_prompt(
            preflight_plan, current_url, prd,
            round_number=0, max_rounds=max_rounds,
        )

        try:
            from tools.build_progress import log_build_phase
            log_build_phase(product_id, "preflight_fix", "running", "AI pre-flight auto-fix")
        except Exception:
            pass

        fix_result = _run_claude(project_dir, preflight_prompt, timeout=600)
        new_url = _detect_url(fix_result.get("output", ""))
        if new_url:
            current_url = new_url

        if fix_result.get("ok"):
            preflight_summary = f"Auto-fixed {len(preflight_issues)} AI-detected issues"
            print(f"  Pre-flight fixes applied")
        else:
            preflight_summary = "AI critique ran but auto-fix had issues"
            print(f"  Pre-flight fix had issues, proceeding to human review")

        try:
            from tools.build_progress import log_build_phase
            log_build_phase(product_id, "preflight_fix", "completed", preflight_summary)
        except Exception:
            pass
    else:
        preflight_summary = "AI found no issues — app looks good"
        print(f"  AI critique: no issues found. App looks ready for human review.")

    # ── Human Feedback Loop ───────────────────────────────────────

    result = {
        "status": "in_progress",
        "rounds_completed": 0,
        "max_rounds": max_rounds,
        "preflight_issues": len(preflight_issues),
        "url": current_url,
        "feedback_summary": [],
    }

    for round_number in range(1, max_rounds + 1):
        round_start = time.time()

        # Open browser
        try:
            webbrowser.open(current_url)
        except Exception:
            pass

        try:
            from tools.build_progress import log_build_phase
            log_build_phase(
                product_id, f"feedback_{round_number}",
                "starting", f"Awaiting human review (round {round_number}/{max_rounds})",
            )
        except Exception:
            pass

        # Build iteration summary
        iteration_summary = ""
        if round_number > 1:
            prev = result["feedback_summary"][-1]
            iteration_summary = (
                f"Round {round_number - 1}: applied {len(prev.get('plan', []))} fixes "
                f"({prev.get('ai_issues', 0)} AI + {prev.get('explicit_count', 0)} human)"
            )

        # Collect human feedback
        raw_feedback = collect_feedback(
            product_id, current_url, round_number, max_rounds,
            iteration_summary,
            preflight_summary if round_number == 1 else "",
        )

        sentiment = classify_user_sentiment(raw_feedback)

        if sentiment == "approved":
            duration = time.time() - round_start
            save_feedback_round(
                product_id=product_id,
                round_number=round_number,
                raw_feedback=raw_feedback,
                parsed_issues=[],
                inferred_gaps=[],
                self_critique=[],
                improvement_plan=[],
                build_output="",
                user_sentiment="approved",
                duration_s=duration,
            )
            result["status"] = "approved"
            result["rounds_completed"] = round_number
            result["url"] = current_url

            print(f"\n  Build approved after {round_number} iteration(s)!")
            print(f"  Final URL: {current_url}\n")
            break

        # ── Intelligent Analysis (AI + keyword + inference) ───────
        print(f"\n  Round {round_number}/{max_rounds} — analyzing...")

        # 1. AI critique with human feedback context (the REAL critic)
        print(f"  Running AI critique (reads code + PRD + your feedback)...")
        ai_issues = run_ai_critique(
            project_dir, prd, current_url,
            human_feedback=raw_feedback,
        )

        # 2. Fast keyword parse (supplements AI, catches obvious things)
        explicit = parse_explicit_feedback(raw_feedback)

        # 3. Infer implicit gaps from explicit feedback (product-type-aware)
        inferred = infer_implicit_gaps(explicit, prd=prd)

        # 4. Load prior rounds for escalation
        prior_rounds: list[dict[str, Any]] = []
        try:
            history = json.loads(get_feedback_history(product_id))
            prior_rounds = history.get("rounds", [])
        except (json.JSONDecodeError, TypeError):
            pass

        # 5. Combine AI issues + explicit + inferred into unified plan
        #    AI issues are treated as high-confidence (they read the code)
        all_explicit = explicit + [
            {**issue, "source": "explicit"} if issue.get("source") == "ai_critique" else issue
            for issue in ai_issues
        ]
        plan = generate_improvement_plan(all_explicit, inferred, [], prior_rounds)

        # Show plan
        print(f"  AI found {len(ai_issues)} code issues + {len(explicit)} from your feedback + {len(inferred)} inferred")
        print(f"  Improvement plan ({len(plan)} items):")
        for item in plan:
            icon = {"critical": "!!", "high": "! ", "medium": "- ", "low": "  "}.get(item["severity"], "- ")
            source_tag = f" [{item['source']}]" if item.get("source") == "ai_critique" else ""
            print(f"    {icon}{item['priority']}. [{item['category']}]{source_tag} {item['description'][:75]}")

        # ── Targeted Rebuild with progressive urgency ─────────────
        rounds_left = max_rounds - round_number
        print(f"\n  Rebuilding... ({rounds_left} rounds remaining after this)")

        prompt = build_targeted_prompt(
            plan, current_url, prd,
            round_number=round_number, max_rounds=max_rounds,
        )

        try:
            from tools.build_progress import log_build_phase
            log_build_phase(
                product_id, f"feedback_rebuild_{round_number}",
                "running", f"Applying {len(plan)} improvements (round {round_number})",
            )
        except Exception:
            pass

        rebuild_result = _run_claude(project_dir, prompt, timeout=600)

        build_output = rebuild_result.get("output", "")
        new_url = _detect_url(build_output)
        if new_url:
            current_url = new_url

        duration = time.time() - round_start

        # Save
        save_feedback_round(
            product_id=product_id,
            round_number=round_number,
            raw_feedback=raw_feedback,
            parsed_issues=explicit,
            inferred_gaps=inferred,
            self_critique=ai_issues,  # AI critique stored here
            improvement_plan=plan,
            build_output=build_output[:2000],
            user_sentiment=sentiment,
            duration_s=duration,
        )

        result["feedback_summary"].append({
            "round": round_number,
            "sentiment": sentiment,
            "explicit_count": len(explicit),
            "ai_issues": len(ai_issues),
            "inferred_count": len(inferred),
            "plan": plan,
            "rebuild_ok": rebuild_result.get("ok", False),
            "duration_s": round(duration, 1),
        })

        try:
            from tools.build_progress import log_build_phase
            status = "completed" if rebuild_result.get("ok") else "failed"
            log_build_phase(
                product_id, f"feedback_rebuild_{round_number}",
                status, f"Round {round_number} rebuild done",
            )
        except Exception:
            pass

        if rebuild_result.get("ok"):
            print(f"  Rebuild complete ({round(duration, 1)}s)\n")
        else:
            print(f"  Rebuild had issues: {rebuild_result.get('error', 'unknown')}")
            print(f"  Continuing...\n")

        result["rounds_completed"] = round_number
        result["url"] = current_url

    else:
        result["status"] = "max_rounds_reached"
        print(f"\n  Reached maximum {max_rounds} feedback rounds.")
        print(f"  Final URL: {current_url}\n")

    result["total_rounds"] = result["rounds_completed"]
    return json.dumps(result, indent=2)
