"""Dynamic registry of AI models available on the configured OpenAI-compatible endpoint.

Fetches the model list from the endpoint's /models API, filters it down to
regular (non-reasoning) text chat models, and caches the result. When the API
is unreachable or no API key is configured, a static fallback list is used, so
admin pages always render.

Input token limits are resolved from metadata rather than a hand-kept table:
first from per-model context fields some endpoints include in /models
(e.g. OpenRouter's context_length, vLLM's max_model_len), then from litellm's
public model metadata JSON, and finally from a configurable default.
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

# Community-maintained metadata with max_input_tokens for models across
# providers; refreshed daily. Override the URL to pin a fork or a mirror.
MODEL_METADATA_URL = os.environ.get(
    "MODEL_METADATA_URL",
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json",
)
MODEL_METADATA_CACHE_SECONDS = int(os.environ.get("MODEL_METADATA_CACHE_SECONDS", 86400))
METADATA_FAILURE_CACHE_SECONDS = 3600

# Final input budget for models whose limits cannot be resolved from any
# source. generate_summary() additionally retries with less content when a
# model turns out to be smaller than this, so a too-large default degrades
# gracefully instead of losing the summary.
DEFAULT_INPUT_TOKEN_LIMIT = int(os.environ.get("DEFAULT_MAX_INPUT_TOKENS", 126_500))

# Headroom subtracted from resolved context sizes so the completion has room
# to generate output, and floor for how far truncation retries may shrink.
RESERVED_OUTPUT_TOKENS = 1500
MIN_INPUT_TOKENS = 1000

_MODELS_CACHE_KEY = "feedmanager:available_models:v2"
_METADATA_CACHE_KEY = "feedmanager:model_input_limits"
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

# Context size fields that OpenAI-compatible endpoints are known to include
# in their /models responses.
_ENDPOINT_CONTEXT_FIELDS = ("context_length", "max_model_len", "context_window", "max_context_length")

# litellm modes that describe text-in/text-out models.
_TEXT_MODES = {None, "chat", "completion", "responses"}


def is_supported_chat_model(model_id):
    return not (_EXCLUDED_MODEL_RE.search(model_id) or _SNAPSHOT_RE.search(model_id))


def _as_positive_int(value):
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    value = int(value)
    return value if value > 0 else None


def _fetch_remote_models():
    """Query the /models API and return filtered chat models, newest first.

    Returns {"ids": [...], "context": {id: context_tokens}} with context sizes
    for endpoints that report them, or None when no API key is configured or
    the request fails.
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
        context = {}
        for m in models:
            for field in _ENDPOINT_CONTEXT_FIELDS:
                tokens = _as_positive_int(getattr(m, field, None))
                if tokens:
                    context[m.id] = tokens
                    break
        return {"ids": [m.id for m in models], "context": context}
    except Exception as e:
        logger.warning(f"Failed to fetch model list from {OPENAI_BASE_URL}: {e!s}")
        return None


def _get_remote_models():
    """Cached /models result, or None if unknown."""
    cached = cache.get(_MODELS_CACHE_KEY)
    if cached == _FETCH_FAILED:
        return None
    if cached is not None:
        return cached
    remote = _fetch_remote_models()
    if remote and remote["ids"]:
        cache.set(_MODELS_CACHE_KEY, remote, MODEL_LIST_CACHE_SECONDS)
        return remote
    cache.set(_MODELS_CACHE_KEY, _FETCH_FAILED, FAILURE_CACHE_SECONDS)
    return None


def get_available_model_ids():
    """Cached list of model ids available on the endpoint, or None if unknown."""
    remote = _get_remote_models()
    return remote["ids"] if remote else None


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


def _fetch_model_input_limits():
    """Download litellm's model metadata and index max input tokens by model id.

    Keys are lowercased; provider-prefixed entries ("xai/grok-2-latest") are
    additionally indexed by their bare name so ids from relays match. Returns
    None when the download fails.
    """
    try:
        proxy = OPENAI_PROXY or None
        with httpx.Client(timeout=15.0, follow_redirects=True, proxy=proxy) as client:
            response = client.get(MODEL_METADATA_URL)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch model metadata from {MODEL_METADATA_URL}: {e!s}")
        return None

    limits = {}
    bare_limits = {}
    for key, entry in data.items():
        if key == "sample_spec" or not isinstance(entry, dict):
            continue
        if entry.get("mode") not in _TEXT_MODES:
            continue
        tokens = _as_positive_int(entry.get("max_input_tokens")) or _as_positive_int(entry.get("max_tokens"))
        if not tokens:
            continue
        limits[key.lower()] = tokens
        bare = key.rsplit("/", 1)[-1].lower()
        if bare != key.lower():
            bare_limits.setdefault(bare, tokens)
    for bare, tokens in bare_limits.items():
        limits.setdefault(bare, tokens)
    return limits


def _get_model_input_limits():
    """Cached litellm metadata index, or None if unavailable."""
    cached = cache.get(_METADATA_CACHE_KEY)
    if cached == _FETCH_FAILED:
        return None
    if cached is not None:
        return cached
    limits = _fetch_model_input_limits()
    if limits:
        cache.set(_METADATA_CACHE_KEY, limits, MODEL_METADATA_CACHE_SECONDS)
        return limits
    cache.set(_METADATA_CACHE_KEY, _FETCH_FAILED, METADATA_FAILURE_CACHE_SECONDS)
    return None


def get_max_input_tokens(model):
    """Max input tokens to send to the given model before truncating.

    Resolution order: context size reported by the endpoint's /models API,
    then litellm metadata, then DEFAULT_INPUT_TOKEN_LIMIT. Resolved sizes are
    reduced by RESERVED_OUTPUT_TOKENS to leave room for the completion.
    """
    remote = _get_remote_models()
    tokens = remote["context"].get(model) if remote else None
    if not tokens:
        limits = _get_model_input_limits() or {}
        tokens = limits.get(model.lower())
    if not tokens:
        return DEFAULT_INPUT_TOKEN_LIMIT
    return max(tokens - RESERVED_OUTPUT_TOKENS, MIN_INPUT_TOKENS)
