"""Marketing tools — open-source backends for the marketing agent team."""

import os
import httpx
from google.adk.tools import tool
from typing import Optional


# ── Trending Topics (Google Trends via pytrends) ──────────────────────────────

@tool
def get_trending_topics(keyword: str, region: str = "US", timeframe: str = "today 3-m") -> dict:
    """
    Get trending related topics and queries for a keyword using Google Trends.

    Args:
        keyword: Seed keyword or topic to research
        region: Two-letter country code (default 'US')
        timeframe: Time range — 'today 1-m', 'today 3-m', 'today 12-m', 'today 5-y'

    Returns:
        dict with rising queries, top queries, and related topics
    """
    try:
        from pytrends.request import TrendReq

        pt = TrendReq(hl="en-US", tz=360)
        pt.build_payload([keyword], cat=0, timeframe=timeframe, geo=region)

        related_queries = pt.related_queries()
        related_topics = pt.related_topics()

        rising_queries = []
        top_queries = []
        rising_topics = []

        if keyword in related_queries:
            rq = related_queries[keyword]
            if rq.get("rising") is not None:
                rising_queries = rq["rising"].head(10).to_dict("records")
            if rq.get("top") is not None:
                top_queries = rq["top"].head(10).to_dict("records")

        if keyword in related_topics:
            rt = related_topics[keyword]
            if rt.get("rising") is not None:
                rising_topics = rt["rising"].head(5).to_dict("records")

        return {
            "keyword": keyword,
            "region": region,
            "timeframe": timeframe,
            "rising_queries": rising_queries,
            "top_queries": top_queries,
            "rising_topics": rising_topics,
        }

    except ImportError:
        # Fallback: use DuckDuckGo to find trending content
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(f"{keyword} trends 2025", max_results=8):
                results.append({"query": r.get("title"), "snippet": r.get("body"), "link": r.get("href")})
        return {
            "keyword": keyword,
            "note": "pytrends not installed — using DuckDuckGo fallback",
            "results": results,
        }

    except Exception as e:
        return {"keyword": keyword, "error": str(e), "rising_queries": [], "top_queries": []}


# ── Competitor Content Analysis ────────────────────────────────────────────────

@tool
def search_competitor_content(
    competitor_domain: str,
    topic: Optional[str] = None,
    content_type: str = "blog",
) -> dict:
    """
    Find competitor content on a specific topic using DuckDuckGo site search.

    Args:
        competitor_domain: Competitor website domain (e.g., 'hubspot.com')
        topic: Topic to search for within their content (optional)
        content_type: 'blog', 'case-study', 'guide', 'landing-page' (default: 'blog')

    Returns:
        dict with competitor content pieces, titles, and snippets
    """
    from duckduckgo_search import DDGS

    query_parts = [f"site:{competitor_domain}"]
    if topic:
        query_parts.append(topic)
    if content_type == "case-study":
        query_parts.append("case study customer story")
    elif content_type == "guide":
        query_parts.append("guide how to")
    elif content_type == "landing-page":
        query_parts.append("pricing features")

    query = " ".join(query_parts)
    results = []

    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=10):
            results.append({
                "title": r.get("title"),
                "snippet": r.get("body"),
                "url": r.get("href"),
                "domain": competitor_domain,
            })

    return {
        "competitor": competitor_domain,
        "topic": topic,
        "content_type": content_type,
        "results": results,
        "count": len(results),
    }


# ── RSS Feed Monitor ───────────────────────────────────────────────────────────

@tool
def fetch_rss_feed(feed_url: str, max_items: int = 10) -> dict:
    """
    Fetch and parse an RSS/Atom feed to monitor competitor or industry content.

    Args:
        feed_url: Full URL of the RSS or Atom feed
        max_items: Maximum number of items to return (default 10)

    Returns:
        dict with feed title and list of recent items
    """
    try:
        import feedparser
        feed = feedparser.parse(feed_url)

        items = []
        for entry in feed.entries[:max_items]:
            items.append({
                "title": entry.get("title", ""),
                "summary": entry.get("summary", "")[:300],
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "author": entry.get("author", ""),
            })

        return {
            "feed_title": feed.feed.get("title", feed_url),
            "feed_url": feed_url,
            "items": items,
            "count": len(items),
        }

    except ImportError:
        return {"error": "feedparser not installed. Run: pip install feedparser", "feed_url": feed_url}
    except Exception as e:
        return {"error": str(e), "feed_url": feed_url}


# ── Audience Community Search ──────────────────────────────────────────────────

@tool
def search_audience_communities(
    persona_description: str,
    platform: str = "all",
) -> dict:
    """
    Find online communities where the target ICP persona is active.
    Searches Reddit, LinkedIn groups, Slack communities, and forums.

    Args:
        persona_description: Description of the ICP (e.g., 'VP Sales mid-market SaaS')
        platform: 'reddit', 'linkedin', 'slack', or 'all' (default: 'all')

    Returns:
        dict with community names, descriptions, and links
    """
    from duckduckgo_search import DDGS

    communities = []

    platform_queries = {
        "reddit": f"site:reddit.com {persona_description} community subreddit",
        "linkedin": f"site:linkedin.com/groups {persona_description}",
        "slack": f"{persona_description} slack community group workspace",
        "forum": f"{persona_description} forum community discussion board",
    }

    target_platforms = (
        list(platform_queries.keys()) if platform == "all" else [platform]
    )

    with DDGS() as ddgs:
        for plat in target_platforms:
            query = platform_queries.get(plat, f"{persona_description} {plat} community")
            for r in ddgs.text(query, max_results=4):
                communities.append({
                    "platform": plat,
                    "title": r.get("title"),
                    "description": r.get("body"),
                    "link": r.get("href"),
                })

    return {
        "persona": persona_description,
        "communities": communities,
        "count": len(communities),
    }
