"""
Browser automation tools — Playwright-based, stealth-enabled, CAPTCHA-aware.

Provides ADK tool functions for autonomous web interaction:
  - navigate_and_read    : fetch page content as clean text (JS-rendered)
  - browser_screenshot   : capture full-page screenshot
  - browser_click        : click an element by CSS selector or text
  - browser_fill_form    : fill and optionally submit a form
  - browser_extract_links: extract all hyperlinks from a page
  - browser_crawl        : recursive site crawler (BFS, same-domain)
  - browser_run_script   : execute JavaScript in the page context
  - browser_solve_captcha: solve CAPTCHA via CapSolver API (requires CAPSOLVER_API_KEY)

Requirements:
  pip install playwright playwright-stealth capsolver
  playwright install chromium
"""

import json
import os
import time
import urllib.parse
from collections import deque
from pathlib import Path
from typing import Optional

# ── lazy imports so missing deps surface as clear errors at call time ─────────

def _get_playwright_sync():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        raise ImportError(
            "playwright not installed. Run: pip install playwright && playwright install chromium"
        )


def _apply_stealth(page) -> None:
    """Apply playwright-stealth if available; silently skip if not installed."""
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(page)
    except ImportError:
        pass  # stealth optional — degrades gracefully


# ── Shared browser context factory ───────────────────────────────────────────

def _new_browser(playwright, headless: bool = True):
    """Launch a stealth-configured Chromium browser."""
    return playwright.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ],
    )


def _new_context(browser):
    """Create a browser context with realistic headers."""
    return browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="America/New_York",
        java_script_enabled=True,
        accept_downloads=False,
    )


# ── Tools ─────────────────────────────────────────────────────────────────────

def navigate_and_read(url: str, wait_seconds: float = 2.0) -> str:
    """
    Navigate to a URL with a real browser (JS-rendered) and return the page
    content as clean text. Works on pages that block simple HTTP scrapers.

    Args:
        url: Full URL to visit (e.g. "https://example.com/pricing")
        wait_seconds: Seconds to wait after load for dynamic content (default 2)

    Returns:
        Page text content (up to 8000 chars) or error message.
    """
    sync_playwright = _get_playwright_sync()
    try:
        with sync_playwright() as pw:
            browser = _new_browser(pw)
            context = _new_context(browser)
            page = context.new_page()
            _apply_stealth(page)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            text = page.inner_text("body")
            browser.close()
        text = text.strip()
        if len(text) > 8000:
            text = text[:8000] + "\n\n[...truncated at 8000 chars]"
        return text
    except Exception as exc:
        return f"Error navigating to {url}: {exc}"


def browser_screenshot(url: str, output_path: Optional[str] = None) -> str:
    """
    Take a full-page screenshot of a URL and save it to disk.

    Args:
        url: URL to screenshot
        output_path: File path to save PNG (default: auto-generated in /tmp)

    Returns:
        Absolute path to the saved screenshot, or error message.
    """
    sync_playwright = _get_playwright_sync()
    if output_path is None:
        ts = int(time.time())
        output_path = str(Path(os.environ.get("TMPDIR", "/tmp")) / f"screenshot_{ts}.png")
    try:
        with sync_playwright() as pw:
            browser = _new_browser(pw)
            context = _new_context(browser)
            page = context.new_page()
            _apply_stealth(page)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(1.5)
            page.screenshot(path=output_path, full_page=True)
            browser.close()
        return output_path
    except Exception as exc:
        return f"Error taking screenshot of {url}: {exc}"


def browser_click(url: str, selector: str, wait_seconds: float = 1.5) -> str:
    """
    Navigate to a URL and click an element identified by CSS selector or visible text.
    Returns the page content after the click.

    Args:
        url: URL to navigate to
        selector: CSS selector (e.g. "button#submit") or text selector (e.g. "text=Sign In")
        wait_seconds: Seconds to wait after click for page to update

    Returns:
        Page text content after click, or error message.
    """
    sync_playwright = _get_playwright_sync()
    try:
        with sync_playwright() as pw:
            browser = _new_browser(pw)
            context = _new_context(browser)
            page = context.new_page()
            _apply_stealth(page)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.click(selector, timeout=10_000)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            text = page.inner_text("body").strip()
            browser.close()
        if len(text) > 6000:
            text = text[:6000] + "\n\n[...truncated]"
        return text
    except Exception as exc:
        return f"Error clicking '{selector}' on {url}: {exc}"


def browser_fill_form(url: str, fields: dict, submit_selector: Optional[str] = None) -> str:
    """
    Fill form fields on a page and optionally submit.

    Args:
        url: URL with the form
        fields: Dict mapping CSS selector → value
                e.g. {"input[name='email']": "test@example.com", "input[name='password']": "secret"}
        submit_selector: CSS selector for submit button (optional — skip to just fill without submitting)

    Returns:
        Page text content after submission, or error message.
    """
    sync_playwright = _get_playwright_sync()
    try:
        with sync_playwright() as pw:
            browser = _new_browser(pw)
            context = _new_context(browser)
            page = context.new_page()
            _apply_stealth(page)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            for selector, value in fields.items():
                page.fill(selector, str(value), timeout=8_000)
                time.sleep(0.3)  # human-like delay between field fills

            if submit_selector:
                page.click(submit_selector, timeout=8_000)
                time.sleep(2.0)

            text = page.inner_text("body").strip()
            browser.close()
        if len(text) > 6000:
            text = text[:6000] + "\n\n[...truncated]"
        return text
    except Exception as exc:
        return f"Error filling form on {url}: {exc}"


def browser_extract_links(url: str, same_domain_only: bool = True) -> str:
    """
    Extract all hyperlinks from a page.

    Args:
        url: URL to extract links from
        same_domain_only: Only return links on the same domain (default True)

    Returns:
        JSON array of unique URLs found on the page, or error message.
    """
    sync_playwright = _get_playwright_sync()
    try:
        base_domain = urllib.parse.urlparse(url).netloc
        with sync_playwright() as pw:
            browser = _new_browser(pw)
            context = _new_context(browser)
            page = context.new_page()
            _apply_stealth(page)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            hrefs = page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => e.href)"
            )
            browser.close()

        # Normalize and deduplicate
        links = []
        seen = set()
        for href in hrefs:
            href = href.strip()
            if not href or href.startswith("javascript:") or href.startswith("mailto:"):
                continue
            parsed = urllib.parse.urlparse(href)
            if same_domain_only and parsed.netloc and parsed.netloc != base_domain:
                continue
            # Strip fragment
            clean = urllib.parse.urlunparse(parsed._replace(fragment=""))
            if clean and clean not in seen:
                seen.add(clean)
                links.append(clean)

        return json.dumps(links[:200])  # cap at 200 links
    except Exception as exc:
        return f"Error extracting links from {url}: {exc}"


def browser_crawl(
    start_url: str,
    max_pages: int = 20,
    same_domain_only: bool = True,
    include_text: bool = True,
) -> str:
    """
    Recursively crawl a website starting from start_url using BFS.
    Returns a summary of all pages visited with their text content.

    Args:
        start_url: Starting URL for the crawl
        max_pages: Maximum number of pages to visit (default 20, max 50)
        same_domain_only: Stay within the same domain (default True)
        include_text: Include page text in output (default True)

    Returns:
        JSON object mapping URL → {title, text} for each visited page, or error.
    """
    max_pages = min(max_pages, 50)  # hard cap
    sync_playwright = _get_playwright_sync()
    base_domain = urllib.parse.urlparse(start_url).netloc

    visited = {}
    queue = deque([start_url])
    seen_urls = {start_url}

    try:
        with sync_playwright() as pw:
            browser = _new_browser(pw)
            context = _new_context(browser)
            page = context.new_page()
            _apply_stealth(page)

            while queue and len(visited) < max_pages:
                url = queue.popleft()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    time.sleep(0.8)

                    title = page.title()
                    text = ""
                    if include_text:
                        text = page.inner_text("body").strip()
                        if len(text) > 2000:
                            text = text[:2000] + "...[truncated]"

                    visited[url] = {"title": title, "text": text}

                    # Discover next links
                    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                    for href in hrefs:
                        href = href.strip()
                        if not href or href.startswith("javascript:") or href.startswith("mailto:"):
                            continue
                        parsed = urllib.parse.urlparse(href)
                        if same_domain_only and parsed.netloc and parsed.netloc != base_domain:
                            continue
                        clean = urllib.parse.urlunparse(parsed._replace(fragment=""))
                        if clean and clean not in seen_urls:
                            seen_urls.add(clean)
                            queue.append(clean)

                except Exception as page_err:
                    visited[url] = {"title": "", "text": f"Error: {page_err}"}

            browser.close()

        return json.dumps({
            "pages_visited": len(visited),
            "start_url": start_url,
            "results": visited,
        }, indent=2)

    except Exception as exc:
        return f"Error crawling {start_url}: {exc}"


def browser_run_script(url: str, script: str) -> str:
    """
    Navigate to a URL and execute JavaScript in the page context.
    Useful for extracting structured data, triggering UI actions, or reading page state.

    Args:
        url: URL to navigate to
        script: JavaScript to execute (must return a JSON-serializable value)
                e.g. "document.title" or "Array.from(document.querySelectorAll('h2')).map(h=>h.textContent)"

    Returns:
        JSON-serialized result of the script, or error message.
    """
    sync_playwright = _get_playwright_sync()
    try:
        with sync_playwright() as pw:
            browser = _new_browser(pw)
            context = _new_context(browser)
            page = context.new_page()
            _apply_stealth(page)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(1.0)
            result = page.evaluate(script)
            browser.close()
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        return f"Error running script on {url}: {exc}"


def browser_solve_captcha(url: str, captcha_type: str = "recaptcha_v2") -> str:
    """
    Navigate to a URL that has a CAPTCHA and solve it automatically via CapSolver.
    Requires CAPSOLVER_API_KEY environment variable.

    Supported captcha_type values: recaptcha_v2, recaptcha_v3, hcaptcha, turnstile

    Args:
        url: URL containing the CAPTCHA
        captcha_type: Type of CAPTCHA to solve (default: recaptcha_v2)

    Returns:
        JSON with {solved: bool, token: str, page_text: str} or error message.
    """
    api_key = os.environ.get("CAPSOLVER_API_KEY")
    if not api_key:
        return json.dumps({
            "solved": False,
            "error": "CAPSOLVER_API_KEY not set. Add it to your .env to enable CAPTCHA solving.",
        })

    try:
        import capsolver
    except ImportError:
        return json.dumps({
            "solved": False,
            "error": "capsolver not installed. Run: pip install capsolver",
        })

    sync_playwright = _get_playwright_sync()

    # Map type to CapSolver task type
    _task_map = {
        "recaptcha_v2": capsolver.RecaptchaV2Task,
        "recaptcha_v3": capsolver.RecaptchaV3Task,
        "hcaptcha": capsolver.HCaptchaTask,
        "turnstile": capsolver.TurnstileTask,
    }
    task_cls = _task_map.get(captcha_type)
    if task_cls is None:
        return json.dumps({"solved": False, "error": f"Unknown captcha_type: {captcha_type}. Use: {list(_task_map)}"})

    try:
        capsolver.api_key = api_key

        with sync_playwright() as pw:
            browser = _new_browser(pw, headless=False)  # some CAPTCHAs need visible browser
            context = _new_context(browser)
            page = context.new_page()
            _apply_stealth(page)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(1.5)

            # Extract site key from page
            site_key = page.evaluate(
                """() => {
                    const el = document.querySelector('[data-sitekey]')
                         || document.querySelector('[data-site-key]')
                         || document.querySelector('.g-recaptcha');
                    return el ? (el.getAttribute('data-sitekey') || el.getAttribute('data-site-key')) : null;
                }"""
            )

            if not site_key:
                browser.close()
                return json.dumps({"solved": False, "error": "Could not find CAPTCHA site key on page."})

            # Solve via CapSolver
            solution = capsolver.solve(task_cls(websiteURL=url, websiteKey=site_key))
            token = solution.get("gRecaptchaResponse") or solution.get("token", "")

            # Inject token into page
            page.evaluate(f"""
                (token) => {{
                    const el = document.getElementById('g-recaptcha-response')
                            || document.querySelector('[name="g-recaptcha-response"]');
                    if (el) el.value = token;
                    // Trigger callback if registered
                    if (window.grecaptcha && window.grecaptcha.getResponse) {{
                        try {{ window.onRecaptchaSuccess && window.onRecaptchaSuccess(token); }} catch(e) {{}}
                    }}
                }}
            """, token)

            time.sleep(1.0)
            page_text = page.inner_text("body").strip()[:4000]
            browser.close()

        return json.dumps({"solved": True, "token": token[:80] + "...", "page_text": page_text})

    except Exception as exc:
        return json.dumps({"solved": False, "error": str(exc)})
