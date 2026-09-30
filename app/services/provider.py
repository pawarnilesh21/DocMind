"""Small, bounded provider transport. Never log keys, prompts, or response bodies."""

import time
from contextlib import contextmanager
from contextvars import ContextVar

import httpx

from app.config import settings


class ProviderError(RuntimeError):
    pass


deadline = ContextVar("provider_deadline", default=None)


@contextmanager
def budget(seconds):
    token = deadline.set(time.monotonic() + seconds)
    try:
        yield
    finally:
        deadline.reset(token)


def post_json(url, *, headers, payload):
    for attempt in range(3):
        remaining = deadline.get() - time.monotonic() if deadline.get() else settings.PROVIDER_TIMEOUT_SECONDS
        if remaining <= 0:
            raise ProviderError("AI operation timed out")
        try:
            timeout = min(settings.PROVIDER_TIMEOUT_SECONDS, remaining)
            with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(10, timeout))) as client:
                response = client.post(url, headers=headers, json=payload)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise ProviderError("AI provider is temporarily unavailable")
            if response.is_error:
                provider = "Gemini" if "generativelanguage" in url else "Groq"
                raise ProviderError(f"{provider} rejected the request (HTTP {response.status_code})")
            data = response.json()
            if not isinstance(data, dict):
                raise ProviderError("AI provider returned invalid structured output")
            return data
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == 2:
                raise ProviderError("AI provider timed out") from None
            time.sleep(2**attempt)
        except ValueError:
            raise ProviderError("AI provider returned an invalid response") from None
    raise ProviderError("AI provider is unavailable")
