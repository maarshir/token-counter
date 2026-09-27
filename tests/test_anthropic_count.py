import json

import httpx
import pytest

from token_counter.anthropic_count import COUNT_URL, CountError, count_tokens


def client_with(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_sends_system_and_message_and_returns_tokens():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"input_tokens": 42})

    n = count_tokens("привет", "claude-haiku-4-5", system="ты помощник", client=client_with(handler), api_key="k")
    assert n == 42
    assert seen["url"] == COUNT_URL
    assert seen["key"] == "k"
    assert seen["body"] == {"model": "claude-haiku-4-5", "system": "ты помощник",
                            "messages": [{"role": "user", "content": "привет"}]}


def test_no_system_field_when_not_given():
    def handler(request):
        assert "system" not in json.loads(request.content)
        return httpx.Response(200, json={"input_tokens": 1})

    assert count_tokens("x", "m", client=client_with(handler), api_key="k") == 1


def test_no_key_is_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(CountError, match="ANTHROPIC_API_KEY"):
        count_tokens("x", "m")


def test_api_error_is_reported():
    client = client_with(lambda r: httpx.Response(401, text="invalid x-api-key"))
    with pytest.raises(CountError, match="401"):
        count_tokens("x", "m", client=client, api_key="k")


def test_unexpected_answer_is_reported():
    client = client_with(lambda r: httpx.Response(200, json={"tokens": 5}))
    with pytest.raises(CountError, match="Неожиданный"):
        count_tokens("x", "m", client=client, api_key="k")


def test_network_error_is_reported():
    def handler(request):
        raise httpx.ConnectError("нет сети")

    with pytest.raises(CountError, match="Сеть"):
        count_tokens("x", "m", client=client_with(handler), api_key="k")
