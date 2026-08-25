"""Dynamic registry of AI models available on the configured OpenAI-compatible endpoint.

Fetches the model list from the endpoint's /models API, filters it down to
regular (non-reasoning) text chat models, and caches the result. When the API
is unreachable or no API key is configured, a static fallback list is used, so
admin pages always render.

The models API does not expose context-window sizes, so per-model input token
limits are maintained here as a prefix table over known model families.
"""

import logging
import os
import re

from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

import httpx
from openai import OpenAI

logger = logging.getLogger("feed_logger")

OPENAI_PROXY = getattr(settings, "OPENAI_PROXY", os.environ.get("OPENAI_PROXY"))
OPENAI_API_KEY = getattr(settings, "OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY"))
OPENAI_BASE_URL = getattr(settings, "OPENAI_BASE_URL", os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))

# How long a successful /models fetch is cached; failures are cached for
# FAILURE_CACHE_SECONDS so a down endpoint doesn't block every admin page load.
MODEL_LIST_CACHE_SECONDS = int(os.environ.get("OPENAI_MODEL_LIST_CACHE_SECONDS", 3600))
FAILURE_CACHE_SECONDS = 300

_CACHE_KEY = "feedmanager:available_model_ids"
_FETCH_FAILED = "__fetch_failed__"

# Static fallback used when the models API is unavailable (no API key, network
# error, or an endpoint that doesn't implement /models).
FALLBACK_MODEL_CHOICES = [
    ("gpt-5-mini", "GPT-5 Mini"),
    ("gpt-5-nano", "GPT-5 Nano"),
    ("gpt-5", "GPT-5"),
    ("gpt-4.1-mini", "GPT-4.1 Mini"),
    ("gpt-4.1-nano", "GPT-4.1 Nano"),
    ("gpt-4.1", "GPT-4.1"),
    ("gpt-4o-mini", "GPT-4o Mini"),
    ("gpt-4o", "GPT-4o"),
    ("gpt-4-turbo", "GPT-4 Turbo"),
    ("gpt-3.5-turbo", "GPT-3.5 Turbo"),
]

# Models that are not regular text chat models: embeddings, audio/speech,
# image/video, moderation, tool-specialized variants, o-series reasoning
# models, Responses-API-only "pro" reasoning tiers, and legacy completions.
_EXCLUDED_MODEL_RE = re.compile(
    r"(?:"
    r"^o\d"
    r"|embed|whisper|tts|audio|realtime|transcribe"
    r"|image|dall-e|sora|moderation|search|codex|computer-use|deep-research"
    r"|instruct|davinci|babbage"
    r"|-pro(?:$|-)"
    r")"
)

# Dated snapshots like gpt-4o-2024-08-06 or gpt-3.5-turbo-0125; the undated
# alias is kept instead.
_SNAPSHOT_RE = re.compile(r"-\d{4}(?:-\d{2}-\d{2})?$")


def is_supported_chat_model(model_id):
    return not (_EXCLUDED_MODEL_RE.search(model_id) or _SNAPSHOT_RE.search(model_id))


def _fetch_remote_model_ids():
    """Query the /models API and return filtered chat model ids, newest first.

    Returns None when no API key is configured or the request fails.
    """
    if not OPENAI_API_KEY:
        return None
    client_params = {"api_key": OPENAI_API_KEY, "timeout": 10.0, "max_retries": 0}
    if OPENAI_BASE_URL:
        client_params["base_url"] = OPENAI_BASE_URL
    if OPENAI_PROXY:
        client_params["http_client"] = httpx.Client(proxy=OPENAI_PROXY, timeout=10.0)
    try:
        client = OpenAI(**client_params)
        models = [m for m in client.models.list() if is_supported_chat_model(m.id)]
        models.sort(key=lambda m: (-(m.created or 0), m.id))
        return [m.id for m in models]
    except Exception as e:
        logger.warning(f"Failed to fetch model list from {OPENAI_BASE_URL}: {e!s}")
        return None


def get_available_model_ids():
    """Cached list of model ids available on the endpoint, or None if unknown."""
    cached = cache.get(_CACHE_KEY)
    if cached == _FETCH_FAILED:
        return None
    if cached is not None:
        return cached
    model_ids = _fetch_remote_model_ids()
    if model_ids:
        cache.set(_CACHE_KEY, model_ids, MODEL_LIST_CACHE_SECONDS)
        return model_ids
    cache.set(_CACHE_KEY, _FETCH_FAILED, FAILURE_CACHE_SECONDS)
    return None


def get_base_model_choices():
    """Model choices without sentinel options, ending with 'Other'."""
    model_ids = get_available_model_ids()
    choices = [(model_id, model_id) for model_id in model_ids] if model_ids else list(FALLBACK_MODEL_CHOICES)
    return [*choices, ("other", _("Other (specify below)"))]


def get_global_model_choices():
    """Choices for AppSetting global model fields, with the 'None' kill switch."""
    return [("none", _("None - Disable AI Features Globally")), *get_base_model_choices()]


def get_model_choices():
    """Choices for per-feed model fields, defaulting to the global setting."""
    return [("use_global", _("Use Global Setting")), *get_base_model_choices()]


# Max input tokens by model family, matched by longest prefix first. Values
# are the documented input limits minus a safety margin for prompt overhead.
# The /models API doesn't expose these, so they are maintained by hand.
_MODEL_INPUT_TOKEN_LIMITS = [
    ("gpt-5-chat", 127_800),  # 128K context
    ("gpt-5", 271_500),  # 400K context = 272K input + 128K output
    ("gpt-4.1", 1_047_376),  # ~1M context
    ("chatgpt-4o", 127_800),  # 128K context
    ("gpt-4o", 127_800),  # 128K context
    ("gpt-4-turbo", 127_800),  # 128K context
    ("gpt-4-32k", 32_300),  # 32K context
    ("gpt-4", 8_000),  # 8K context
    ("gpt-3.5-turbo", 16_200),  # 16K context
]

DEFAULT_INPUT_TOKEN_LIMIT = 127_800


def get_max_input_tokens(model):
    """Max input tokens to send to the given model before truncating."""
    for prefix, limit in _MODEL_INPUT_TOKEN_LIMITS:
        if model.startswith(prefix):
            return limit
    return DEFAULT_INPUT_TOKEN_LIMIT
