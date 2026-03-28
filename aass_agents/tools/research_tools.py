"""Research tools for the lead-researcher agent — all open-source backends."""

import os
import httpx
from typing import Optional


def _relevance_score(company_name: str, results: list[dict]) -> list[dict]:
    """
    Output verification: filter and score results by relevance to company_name.
    Drops results with no mention of the company in title or snippet.
    Adds a 'relevance' flag to each result.
    """
    name_lower = company_name.lower().split()[0]  # use first word to handle "Acme Corp" → "acme"
    verified = []
    for r in results:
        text = f"{r.get('title', '')} {r.get('snippet', '') or r.get('body', '')}".lower()
        r["relevance"] = "confirmed" if name_lower in text else "unverified"
        verified.append(r)
    # Sort: confirmed results first
    verified.sort(key=lambda x: 0 if x["relevance"] == "confirmed" else 1)
    return verified


# ── Web Search (DuckDuckGo — no API key required) ────────────────────────────

def search_company_web(company_name: str, query_suffix: str = "") -> dict:
    """
    Search the web for company information using DuckDuckGo (no API key needed).

    Args:
        company_name: Name of the company to research
        query_suffix: Additional search terms (e.g., "funding news", "tech stack")

    Returns:
        dict with search results and snippets
    """
    from ddgs import DDGS

    query = f"{company_name} {query_suffix}".strip()
    results = []

    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=8):
            results.append({
                "title": r.get("title"),
                "snippet": r.get("body"),
                "link": r.get("href"),
                "date": None,
            })

    verified = _relevance_score(company_name, results)
    confirmed_count = sum(1 for r in verified if r["relevance"] == "confirmed")
    return {
        "query": query,
        "results": verified,
        "verification": {
            "total": len(verified),
            "confirmed_relevant": confirmed_count,
            "warning": None if confirmed_count >= 3 else f"Only {confirmed_count} results confirmed relevant — treat others as unverified",
        },
    }


def search_news(company_name: str, days_back: int = 180) -> dict:
    """
    Search for recent news about a company using DuckDuckGo News (no API key needed).

    Args:
        company_name: Company to search news for
        days_back: Recency filter: 7, 30, 90, or 180 days (approximated to d/w/m)

    Returns:
        dict with news articles sorted by recency
    """
    from ddgs import DDGS

    # Map days_back to DDG timelimit: d=day, w=week, m=month, y=year
    if days_back <= 7:
        timelimit = "w"
    elif days_back <= 30:
        timelimit = "m"
    else:
        timelimit = "y"

    articles = []
    with DDGS() as ddgs:
        for r in ddgs.news(company_name, max_results=10, timelimit=timelimit):
            articles.append({
                "title": r.get("title"),
                "snippet": r.get("body"),
                "source": r.get("source"),
                "date": r.get("date"),
                "link": r.get("url"),
            })

    # Verification: flag articles that don't mention the company
    verified = _relevance_score(company_name, articles)
    confirmed_count = sum(1 for a in verified if a["relevance"] == "confirmed")
    return {
        "company": company_name,
        "articles": verified,
        "verification": {
            "total": len(verified),
            "confirmed_relevant": confirmed_count,
            "warning": None if confirmed_count >= 2 else "Few confirmed news articles — signals may be limited",
        },
    }


# ── Company Enrichment (OpenCorporates + DuckDuckGo) ─────────────────────────

def enrich_company(domain: str) -> dict:
    """
    Enrich company firmographic data using OpenCorporates (open, free tier)
    plus a DuckDuckGo description fallback.

    Args:
        domain: Company website domain (e.g., 'stripe.com')

    Returns:
        dict with enriched company data
    """
    from ddgs import DDGS

    company_name = domain.split(".")[0].capitalize()
    result: dict = {"domain": domain, "name": company_name}

    # 1. OpenCorporates — free company registry data
    try:
        oc_response = httpx.get(
            "https://api.opencorporates.com/v0.4/companies/search",
            params={"q": company_name, "per_page": 1},
            timeout=10,
        )
        if oc_response.status_code == 200:
            companies = oc_response.json().get("results", {}).get("companies", [])
            if companies:
                co = companies[0].get("company", {})
                result.update({
                    "registered_name": co.get("name"),
                    "jurisdiction": co.get("jurisdiction_code"),
                    "company_number": co.get("company_number"),
                    "incorporation_date": co.get("incorporation_date"),
                    "company_type": co.get("company_type"),
                    "opencorporates_url": co.get("opencorporates_url"),
                })
    except Exception:
        pass

    # 2. DuckDuckGo Instant Answer — description and summary
    try:
        with DDGS() as ddgs:
            answers = list(ddgs.answers(company_name))
            if answers:
                result["description"] = answers[0].get("text", "")
    except Exception:
        pass

    # 3. DuckDuckGo search for tech stack signals from job postings
    try:
        with DDGS() as ddgs:
            tech_results = list(ddgs.text(
                f"{company_name} site:linkedin.com OR site:builtwith.com tech stack",
                max_results=3,
            ))
            result["tech_signals"] = [r.get("body", "") for r in tech_results]
    except Exception:
        result["tech_signals"] = []

    return result


# ── Contact Finder (GitHub + DuckDuckGo LinkedIn search) ─────────────────────

def find_contacts(company_domain: str, title_filter: Optional[str] = None) -> dict:
    """
    Find decision-maker contacts using GitHub API (open) and DuckDuckGo
    LinkedIn profile search — no paid API required.

    Args:
        company_domain: Company website domain
        title_filter: Target title keyword (e.g., 'VP Sales', 'CTO')

    Returns:
        dict with list of matching contacts
    """
    from ddgs import DDGS

    company_name = company_domain.split(".")[0]
    default_titles = ["VP Sales", "Director Sales", "CRO", "VP Marketing", "CEO", "CTO", "Head of Revenue"]
    targets = [title_filter] if title_filter else default_titles

    contacts = []

    # 1. DuckDuckGo LinkedIn search for each target title
    try:
        with DDGS() as ddgs:
            for title in targets[:3]:  # limit to 3 title searches
                query = f'site:linkedin.com/in "{company_name}" "{title}"'
                for r in ddgs.text(query, max_results=3):
                    name = r.get("title", "").split(" - ")[0].strip()
                    snippet = r.get("body", "")
                    if name and company_name.lower() in snippet.lower():
                        contacts.append({
                            "name": name,
                            "title": title,
                            "linkedin": r.get("href"),
                            "snippet": snippet,
                            "source": "linkedin_search",
                        })
    except Exception:
        pass

    # 2. GitHub API — find org members who may be technical decision makers
    github_token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    try:
        response = httpx.get(
            f"https://api.github.com/orgs/{company_name}/members",
            headers=headers,
            params={"per_page": 10},
            timeout=10,
        )
        if response.status_code == 200:
            for member in response.json():
                # Fetch user profile for name/bio
                profile_resp = httpx.get(
                    member.get("url", ""),
                    headers=headers,
                    timeout=8,
                )
                if profile_resp.status_code == 200:
                    p = profile_resp.json()
                    contacts.append({
                        "name": p.get("name") or p.get("login"),
                        "title": p.get("bio", ""),
                        "github": p.get("html_url"),
                        "email": p.get("email"),
                        "source": "github",
                    })
    except Exception:
        pass

    # Deduplicate by name
    seen = set()
    unique = []
    for c in contacts:
        key = (c.get("name") or "").lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(c)

    return {"company_domain": company_domain, "contacts": unique[:10]}


# ── Deep Research (DeerFlow LangGraph API) ───────────────────────────────────

DEERFLOW_URL = os.environ.get("DEERFLOW_URL", "http://localhost:2026")
_DEERFLOW_TIMEOUT = 120


def deep_research(query: str) -> dict:
    """
    Run a deep multi-step research query via DeerFlow.
    Returns a synthesized report with citations.
    Falls back to DuckDuckGo web search if DeerFlow is unavailable.

    Args:
        query: Research question or topic to investigate in depth

    Returns:
        dict with 'report' (full synthesized text), 'source', and 'query'
    """
    import json as _json

    try:
        with httpx.Client(timeout=_DEERFLOW_TIMEOUT) as client:
            # Step 1: create thread
            thread_resp = client.post(f"{DEERFLOW_URL}/api/langgraph/threads", json={})
            thread_resp.raise_for_status()
            thread_id = thread_resp.json()["thread_id"]

            # Step 2: stream run and collect SSE
            payload = {
                "assistant_id": "lead_agent",
                "input": {"messages": [{"role": "human", "content": query}]},
                "stream_mode": ["values"],
            }
            report = ""
            with client.stream(
                "POST",
                f"{DEERFLOW_URL}/api/langgraph/threads/{thread_id}/runs/stream",
                json=payload,
            ) as stream:
                for line in stream.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        event = _json.loads(data_str)
                        messages = event.get("messages", [])
                        if messages:
                            content = messages[-1].get("content", "")
                            if isinstance(content, str) and content:
                                report = content
                    except _json.JSONDecodeError:
                        continue

        return {"report": report, "source": "deerflow", "query": query}

    except Exception as exc:
        # Fallback: DuckDuckGo
        try:
            from ddgs import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=8):
                    results.append({"title": r.get("title"), "snippet": r.get("body"), "link": r.get("href")})
            return {"report": _json.dumps(results), "source": "duckduckgo_fallback", "query": query,
                    "fallback_reason": str(exc)}
        except Exception as fallback_exc:
            return {"error": f"DeerFlow unavailable ({exc}); fallback also failed ({fallback_exc})", "query": query}
