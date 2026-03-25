# sales-adk-agents/tools/http_tools.py
"""
HTTP smoke-test utilities for verifying deployed services.
"""
import time
import httpx

_TIMEOUT = 30


def check_url(url: str, expected_status: int = 200) -> dict:
    """
    GET a URL and return {ok, status_code, latency_ms, error}.
    Does not raise on HTTP errors — returns ok=False instead.
    """
    start = time.monotonic()
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.get(url)
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "ok": r.status_code == expected_status,
            "status_code": r.status_code,
            "latency_ms": latency_ms,
            "error": None,
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "ok": False,
            "status_code": None,
            "latency_ms": latency_ms,
            "error": str(exc),
        }


def wait_for_url(url: str, timeout: int = 120, interval: int = 5) -> dict:
    """
    Poll a URL until it returns 200 or timeout expires.
    Returns final check_url result.
    """
    deadline = time.time() + timeout
    last_result: dict = {}
    while time.time() < deadline:
        last_result = check_url(url)
        if last_result["ok"]:
            return last_result
        time.sleep(interval)
    last_result["error"] = last_result.get("error") or f"Timed out after {timeout}s"
    return last_result


def smoke_test(urls: list[str]) -> list[dict]:
    """
    Run check_url against a list of URLs. Returns list of results.
    Each result includes the url field added.
    """
    results = []
    for url in urls:
        result = check_url(url)
        result["url"] = url
        results.append(result)
    return results


def health_check(base_url: str) -> dict:
    """
    Check the /health endpoint of a deployed backend.
    Returns {ok, status_code, latency_ms, error}.
    """
    url = base_url.rstrip("/") + "/health"
    return check_url(url)


def auth_smoke_test(base_url: str) -> dict:
    """
    POST to /api/auth/register with a dummy user.
    Accepts 200, 201 (created), or 409 (already exists) as passing.
    Returns {ok, status_code, latency_ms, error}.
    """
    url = base_url.rstrip("/") + "/api/auth/register"
    start = time.monotonic()
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.post(url, json={"email": "smoke@test.local", "password": "smoketest123"})
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "ok": r.status_code in (200, 201, 409),
            "status_code": r.status_code,
            "latency_ms": latency_ms,
            "error": None,
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "ok": False,
            "status_code": None,
            "latency_ms": latency_ms,
            "error": str(exc),
        }
