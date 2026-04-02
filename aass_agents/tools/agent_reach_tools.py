"""
Agent-Reach integration — multi-platform research tools for ADK agents.

Wraps Agent-Reach channels (Jina Reader, Reddit, RSS, YouTube) as ADK tool
functions so PM and architect agents can research across platforms before building.

Channels used:
  - Web (Jina Reader): Read any URL as clean markdown text (free, no API key)
  - Reddit: Search subreddits for discussions, feedback, feature ideas
  - RSS: Read RSS/Atom feeds for competitor blog updates
  - YouTube: Extract video metadata and transcripts for product research
  - GitHub: Search repos and code for existing implementations (requires gh CLI)

Based on: https://github.com/Panniantong/Agent-Reach
"""

import json
import shutil
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional


# ---------------------------------------------------------------------------
# Web — Jina Reader (read any URL as clean text)
# ---------------------------------------------------------------------------

def read_webpage(url: str) -> str:
    """
    Read any webpage and return its content as clean markdown text.
    Uses Jina Reader (free, no API key). Works with any public URL.

    Args:
        url: Full URL to read (e.g. "https://example.com/article")

    Returns:
        Clean markdown text of the page content, or error message.
    """
    jina_url = f"https://r.jina.ai/{url}"
    req = urllib.request.Request(
        jina_url,
        headers={
            "User-Agent": "agent-reach/1.0",
            "Accept": "text/plain",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            # Trim to first 5000 chars to avoid context bloat
            if len(content) > 5000:
                return content[:5000] + "\n\n[...truncated at 5000 chars]"
            return content
    except Exception as e:
        return f"Error reading {url}: {e}"


# ---------------------------------------------------------------------------
# Reddit — JSON API (search subreddits for discussions)
# ---------------------------------------------------------------------------

def search_reddit(query: str, subreddit: str = "", limit: int = 10) -> str:
    """
    Search Reddit for discussions, user feedback, and feature ideas.
    Uses Reddit's public JSON API (no auth needed).

    Args:
        query: Search terms (e.g. "shrimp farming software")
        subreddit: Optional subreddit to search within (e.g. "aquaculture")
        limit: Max results to return (default 10)

    Returns:
        JSON string with list of posts: title, subreddit, score, url, selftext preview
    """
    if subreddit:
        search_url = f"https://www.reddit.com/r/{subreddit}/search.json?q={urllib.parse.quote(query)}&restrict_sr=1&limit={limit}&sort=relevance"
    else:
        search_url = f"https://www.reddit.com/search.json?q={urllib.parse.quote(query)}&limit={limit}&sort=relevance"

    req = urllib.request.Request(
        search_url,
        headers={"User-Agent": "agent-reach/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        posts = []
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            selftext = post.get("selftext", "")
            if len(selftext) > 200:
                selftext = selftext[:200] + "..."
            posts.append({
                "title": post.get("title", ""),
                "subreddit": post.get("subreddit", ""),
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "url": f"https://reddit.com{post.get('permalink', '')}",
                "selftext": selftext,
                "created_utc": post.get("created_utc", 0),
            })
        return json.dumps(posts, indent=2)
    except Exception as e:
        return f"Error searching Reddit: {e}"


# ---------------------------------------------------------------------------
# RSS — feedparser (read RSS/Atom feeds)
# ---------------------------------------------------------------------------

def read_rss_feed(feed_url: str, limit: int = 10) -> str:
    """
    Read an RSS or Atom feed and return recent entries.
    Useful for monitoring competitor blogs, tech news, industry updates.

    Args:
        feed_url: URL of the RSS/Atom feed
        limit: Max entries to return (default 10)

    Returns:
        JSON string with list of entries: title, link, published, summary
    """
    try:
        import feedparser
    except ImportError:
        return "Error: feedparser not installed. Run: pip install feedparser"

    feed = feedparser.parse(feed_url)
    if feed.bozo and not feed.entries:
        return f"Error parsing feed: {feed.bozo_exception}"

    entries = []
    for entry in feed.entries[:limit]:
        summary = entry.get("summary", "")
        if len(summary) > 300:
            summary = summary[:300] + "..."
        entries.append({
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
            "summary": summary,
        })

    return json.dumps({
        "feed_title": feed.feed.get("title", ""),
        "feed_link": feed.feed.get("link", ""),
        "entries": entries,
    }, indent=2)


# ---------------------------------------------------------------------------
# YouTube — yt-dlp (extract video info and transcripts)
# ---------------------------------------------------------------------------

def search_youtube(query: str, limit: int = 5) -> str:
    """
    Search YouTube for videos related to a topic. Returns video metadata.
    Uses yt-dlp (must be installed). Useful for finding product demos,
    tutorials, and competitor content.

    Args:
        query: Search terms (e.g. "shrimp farm management app demo")
        limit: Max results (default 5)

    Returns:
        JSON string with list of videos: title, url, duration, view_count, description
    """
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        return "Error: yt-dlp not installed. Run: pip install yt-dlp"

    search_url = f"ytsearch{limit}:{query}"
    cmd = [
        ytdlp,
        "--dump-json",
        "--flat-playlist",
        "--no-download",
        search_url,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return f"Error: yt-dlp failed: {result.stderr.strip()}"

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                video = json.loads(line)
                desc = video.get("description", "") or ""
                if len(desc) > 200:
                    desc = desc[:200] + "..."
                videos.append({
                    "title": video.get("title", ""),
                    "url": video.get("url", video.get("webpage_url", "")),
                    "duration": video.get("duration", 0),
                    "view_count": video.get("view_count", 0),
                    "description": desc,
                    "channel": video.get("channel", video.get("uploader", "")),
                })
            except json.JSONDecodeError:
                continue

        return json.dumps(videos, indent=2)
    except subprocess.TimeoutExpired:
        return "Error: YouTube search timed out"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# GitHub — gh CLI (search repos and code)
# ---------------------------------------------------------------------------

def search_github_repos(query: str, limit: int = 10) -> str:
    """
    Search GitHub repositories for existing implementations and templates.
    Requires gh CLI (https://cli.github.com) to be installed and authenticated.

    Args:
        query: Search terms (e.g. "shrimp farm management" or "aquaculture dashboard")
        limit: Max results (default 10)

    Returns:
        JSON string with repos: name, description, stars, language, url, topics
    """
    gh = shutil.which("gh")
    if not gh:
        return "Error: gh CLI not installed. Install from https://cli.github.com"

    cmd = [
        gh, "search", "repos",
        query,
        "--limit", str(limit),
        "--json", "name,description,stargazersCount,primaryLanguage,url,repositoryTopics",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout
    except Exception as e:
        return f"Error: {e}"


def search_github_code(query: str, language: str = "", limit: int = 10) -> str:
    """
    Search GitHub code for specific implementations, patterns, or examples.
    Requires gh CLI (https://cli.github.com) to be installed and authenticated.

    Args:
        query: Code search query (e.g. "prisma schema shrimp" or "water quality monitoring")
        language: Optional language filter (e.g. "typescript", "python")
        limit: Max results (default 10)

    Returns:
        JSON string with code matches: repository, path, text_matches
    """
    gh = shutil.which("gh")
    if not gh:
        return "Error: gh CLI not installed. Install from https://cli.github.com"

    cmd = [gh, "search", "code", query, "--limit", str(limit)]
    if language:
        cmd.extend(["-l", language])
    cmd.extend(["--json", "repository,path,textMatches"])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def agent_reach_status() -> str:
    """
    Check which Agent-Reach research channels are available.
    Returns status of each channel (ok/warn/off) and what tools are needed.

    Returns:
        JSON string with channel statuses
    """
    try:
        from agent_reach.core import AgentReach
        ar = AgentReach()
        results = ar.doctor()
        # Simplify for agent consumption
        summary = {}
        for name, info in results.items():
            summary[name] = {
                "status": info["status"],
                "available": info["status"] == "ok",
            }
        return json.dumps(summary, indent=2)
    except ImportError:
        return json.dumps({"error": "agent-reach not installed"})
    except Exception as e:
        return json.dumps({"error": str(e)})
