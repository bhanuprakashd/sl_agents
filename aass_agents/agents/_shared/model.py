"""
Shared model factory.

All agents call get_model() instead of reading MODEL_ID directly.
Supports Gemini models (string) and OpenRouter/LiteLLM models.

  GEMINI (default):
    MODEL_ID=gemini-2.0-flash

  OpenRouter via LiteLLM:
    MODEL_ID=openrouter/nvidia/nemotron-3-super-120b-a12b:free
    OPENROUTER_API_KEY=sk-or-v1-...
"""

import os

_LITELLM_PREFIXES = ("openrouter/", "litellm/", "anthropic/", "mistral/", "groq/", "together_ai/")


def get_model():
    model_id = os.getenv("MODEL_ID", "gemini-2.0-flash")
    if any(model_id.startswith(p) for p in _LITELLM_PREFIXES):
        # Lazy import avoids namespace-package issues in pytest's importlib mode
        try:
            from google.adk.models.lite_llm import LiteLlm  # ADK >= 1.27
        except ImportError:
            from google.adk.lite_llm import LiteLlm          # ADK < 1.27
        return LiteLlm(model=model_id)
    return model_id
