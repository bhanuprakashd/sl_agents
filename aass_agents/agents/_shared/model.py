"""
Smart model factory with per-agent cost optimization.

All agents call get_model(tier) instead of reading MODEL_ID directly.
Supports 3 tiers to balance cost vs capability:

  FAST  — cheap, high-throughput (research, simple extraction, logging)
  STD   — balanced (most agents, orchestration, feature building)
  DEEP  — maximum capability (architecture, complex reasoning, review)

Tier mapping:
  Gemini:     fast=gemini-2.0-flash, std=gemini-2.0-flash, deep=gemini-2.5-pro
  OpenRouter: fast=MODEL_ID_FAST or MODEL_ID, std=MODEL_ID, deep=MODEL_ID_DEEP or MODEL_ID
  LiteLLM:    same as OpenRouter

Gemini 3 Flash thinking_level support:
  When using gemini-3-flash (native or via OpenRouter), each tier maps to a
  thinking_level for fine-grained cost/quality control:
    FAST → thinking_level="minimal"
    STD  → thinking_level="medium"
    DEEP → thinking_level="high"

Environment variables:
  MODEL_ID       — default model for all tiers (required)
  MODEL_ID_FAST  — override for fast tier (optional, falls back to MODEL_ID)
  MODEL_ID_DEEP  — override for deep tier (optional, falls back to MODEL_ID)
"""

import os
import asyncio
import time
import random
import logging
from collections import deque
from threading import Lock

_log = logging.getLogger(__name__)

_LITELLM_PREFIXES = ("openrouter/", "litellm/", "anthropic/", "mistral/", "groq/", "together_ai/", "nvidia_nim/", "openai/")

# ── Retry config for malformed function calls ─────────────────────────────────
_MALFORMED_MAX_RETRIES = int(os.getenv("MALFORMED_MAX_RETRIES", "5"))
_MALFORMED_BASE_DELAY = float(os.getenv("MALFORMED_BASE_DELAY", "3.0"))
_MALFORMED_MAX_DELAY = float(os.getenv("MALFORMED_MAX_DELAY", "60.0"))


def _is_malformed_function_call_error(exc: Exception) -> bool:
    """Check if an exception is caused by a MALFORMED_FUNCTION_CALL from the provider."""
    msg = str(exc).lower()
    return "malformed_function_call" in msg or (
        "invalid response object" in msg and "finish_reason" in msg
    )


def _jittered_backoff(attempt: int) -> float:
    """Exponential backoff with full jitter: uniform [0, min(cap, base * 2^attempt)]."""
    delay = min(_MALFORMED_MAX_DELAY, _MALFORMED_BASE_DELAY * (2 ** attempt))
    return random.uniform(0, delay)

# ── Rate limiter ────────────────────────────────────────────────────────────
_MAX_RPM = int(os.getenv("MAX_RPM", "38"))
_request_timestamps: deque[float] = deque()
_rate_lock = Lock()


def _wait_for_rate_limit():
    """Block until we're under the RPM limit. Thread-safe."""
    with _rate_lock:
        now = time.time()
        # Purge timestamps older than 60s
        while _request_timestamps and _request_timestamps[0] < now - 60:
            _request_timestamps.popleft()
        if len(_request_timestamps) >= _MAX_RPM:
            wait = 60 - (now - _request_timestamps[0]) + 0.1
            if wait > 0:
                time.sleep(wait)
            # Purge again after sleeping
            now = time.time()
            while _request_timestamps and _request_timestamps[0] < now - 60:
                _request_timestamps.popleft()
        _request_timestamps.append(time.time())


def _fix_reasoning_content(response):
    """Map reasoning_content → content for thinking models (GLM4, Kimi, etc.)."""
    if not hasattr(response, "choices"):
        return response
    for choice in response.choices:
        msg = getattr(choice, "message", None)
        if msg is None:
            continue
        if not msg.content:
            reasoning = getattr(msg, "reasoning_content", None)
            if not reasoning:
                psf = getattr(msg, "provider_specific_fields", None)
                if psf and isinstance(psf, dict):
                    reasoning = psf.get("reasoning_content")
            if reasoning:
                msg.content = reasoning
    return response


def _configure_rate_limit():
    """Install rate limiting, reasoning_content fix, and cost tracking on litellm."""
    try:
        import litellm
        litellm.num_retries = 5
        litellm.retry_after = 8
        litellm.request_timeout = 300  # 5 min per LLM call

        _original_completion = litellm.completion

        def _rate_limited_completion(*args, **kwargs):
            last_exc = None
            for attempt in range(_MALFORMED_MAX_RETRIES + 1):
                _wait_for_rate_limit()
                start_ms = int(time.time() * 1000)
                try:
                    resp = _original_completion(*args, **kwargs)
                    resp = _fix_reasoning_content(resp)
                    duration_ms = int(time.time() * 1000) - start_ms
                    try:
                        from tools.cost_tracker import track_response
                        model_id = kwargs.get("model", "") or (args[0] if args else "")
                        track_response(resp, str(model_id), duration_ms)
                    except Exception:
                        pass
                    return resp
                except Exception as exc:
                    last_exc = exc
                    if _is_malformed_function_call_error(exc) and attempt < _MALFORMED_MAX_RETRIES:
                        delay = _jittered_backoff(attempt)
                        _log.warning(
                            "MALFORMED_FUNCTION_CALL (attempt %d/%d), retrying in %.1fs: %s",
                            attempt + 1, _MALFORMED_MAX_RETRIES, delay, exc,
                        )
                        time.sleep(delay)
                        continue
                    raise
            raise last_exc  # unreachable but satisfies type checkers

        litellm.completion = _rate_limited_completion

        _original_acompletion = litellm.acompletion

        async def _rate_limited_acompletion(*args, **kwargs):
            last_exc = None
            for attempt in range(_MALFORMED_MAX_RETRIES + 1):
                _wait_for_rate_limit()
                start_ms = int(time.time() * 1000)
                try:
                    resp = await _original_acompletion(*args, **kwargs)
                    resp = _fix_reasoning_content(resp)
                    duration_ms = int(time.time() * 1000) - start_ms
                    try:
                        from tools.cost_tracker import track_response
                        model_id = kwargs.get("model", "") or (args[0] if args else "")
                        track_response(resp, str(model_id), duration_ms)
                    except Exception:
                        pass
                    return resp
                except Exception as exc:
                    last_exc = exc
                    if _is_malformed_function_call_error(exc) and attempt < _MALFORMED_MAX_RETRIES:
                        delay = _jittered_backoff(attempt)
                        _log.warning(
                            "MALFORMED_FUNCTION_CALL async (attempt %d/%d), retrying in %.1fs: %s",
                            attempt + 1, _MALFORMED_MAX_RETRIES, delay, exc,
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise
            raise last_exc

        litellm.acompletion = _rate_limited_acompletion
    except ImportError:
        pass


_configure_rate_limit()

# Tier constants
FAST = "fast"
STD = "std"
DEEP = "deep"


def _resolve_model_id(tier: str = STD) -> str:
    """Resolve the model ID string for a given tier."""
    base = os.getenv("MODEL_ID", "gemini-2.0-flash")

    if tier == FAST:
        return os.getenv("MODEL_ID_FAST", base)
    elif tier == DEEP:
        return os.getenv("MODEL_ID_DEEP", base)
    return base


_THINKING_MODELS = ("glm4", "kimi-k2", "deepseek-r1", "qwq")

# ── Gemini 3 Flash thinking_level per tier ───────────────────────────────────
_GEMINI3_THINKING_LEVELS = {
    FAST: "minimal",
    STD: "medium",
    DEEP: "high",
}

_GEMINI3_FLASH_PATTERNS = ("gemini-3-flash", "gemini-3.0-flash", "gemini-3.1-flash")


def _is_gemini3_flash(model_id: str) -> bool:
    """Check if the model is a Gemini 3 Flash variant."""
    lower = model_id.lower()
    return any(p in lower for p in _GEMINI3_FLASH_PATTERNS)


def _needs_thinking_disabled(model_id: str) -> bool:
    """Check if a model uses reasoning_content and needs thinking disabled for ADK."""
    lower = model_id.lower()
    return any(t in lower for t in _THINKING_MODELS)


def _make_model(model_id: str, tier: str = STD):
    """Create the appropriate model object (string for Gemini, LiteLlm for OpenRouter)."""
    if any(model_id.startswith(p) for p in _LITELLM_PREFIXES):
        try:
            from google.adk.models.lite_llm import LiteLlm  # ADK >= 1.27
        except ImportError:
            from google.adk.lite_llm import LiteLlm          # ADK < 1.27
        kwargs = {}
        if _needs_thinking_disabled(model_id):
            kwargs["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": False}
            }
        elif _is_gemini3_flash(model_id):
            thinking_level = _GEMINI3_THINKING_LEVELS.get(tier, "medium")
            kwargs["extra_body"] = {"thinking_level": thinking_level}
            _log.info("Gemini 3 Flash tier=%s → thinking_level=%s", tier, thinking_level)
        return LiteLlm(model=model_id, **kwargs)

    # Native Gemini model string — append thinking config via generate_content_config
    if _is_gemini3_flash(model_id):
        thinking_level = _GEMINI3_THINKING_LEVELS.get(tier, "medium")
        _log.info("Gemini 3 Flash (native) tier=%s → thinking_level=%s", tier, thinking_level)
        # For native Gemini, ADK passes the model string; thinking_level is set
        # via GenerateContentConfig at the agent level. Return a dict so callers
        # can extract the config if needed, but fall back to string for compat.
    return model_id


def get_model(tier: str = STD):
    """
    Get the model for an agent, optimized by tier.

    Args:
        tier: One of "fast", "std", "deep"
              - "fast" — cheap, high-throughput (PM research, logging, simple tools)
              - "std"  — balanced (most agents, orchestration, CRUD features)
              - "deep" — maximum capability (architecture, complex reasoning)

    Returns:
        Model string (Gemini) or LiteLlm instance (OpenRouter/LiteLLM)

    Usage:
        # In agent definition:
        from agents._shared.model import get_model, FAST, STD, DEEP

        pm_agent = Agent(model=get_model(FAST), ...)      # research is cheap
        architect = Agent(model=get_model(DEEP), ...)      # design needs reasoning
        builder = Agent(model=get_model(STD), ...)         # most work
    """
    model_id = _resolve_model_id(tier)
    return _make_model(model_id, tier)
