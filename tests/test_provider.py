from unittest.mock import MagicMock, Mock

import httpx
import pytest

from app.services import provider
from app.services.provider import ProviderError, post_json


def transport(monkeypatch, responses):
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.side_effect = responses
    monkeypatch.setattr(provider.httpx, "Client", Mock(return_value=client))
    monkeypatch.setattr(provider.time, "sleep", Mock())
    return client


def test_retry_only_transient_failures(monkeypatch):
    client = transport(
        monkeypatch, [httpx.Response(429), httpx.Response(503), httpx.Response(200, json={"ok": True})]
    )
    assert post_json("https://example.test", headers={}, payload={}) == {"ok": True}
    assert client.post.call_count == 3


def test_permanent_failure_is_not_retried(monkeypatch):
    client = transport(monkeypatch, [httpx.Response(401)])
    with pytest.raises(ProviderError):
        post_json("https://example.test", headers={}, payload={})
    assert client.post.call_count == 1


def test_invalid_response_rejected(monkeypatch):
    transport(monkeypatch, [httpx.Response(200, json=[])])
    with pytest.raises(ProviderError):
        post_json("https://example.test", headers={}, payload={})


def test_expired_budget_never_calls_provider(monkeypatch):
    client = transport(monkeypatch, [])
    with provider.budget(-1), pytest.raises(ProviderError):
        post_json("https://example.test", headers={}, payload={})
    client.post.assert_not_called()
