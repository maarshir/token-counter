"""Точный подсчёт входных токенов через API Anthropic (эндпоинт count_tokens).

Запрос бесплатный, но нужен ключ, и у него есть свой лимит частоты.
Считает ровно то, что модель увидит на входе: системный промпт и сообщение.
"""

import os

import httpx

COUNT_URL = "https://api.anthropic.com/v1/messages/count_tokens"
API_VERSION = "2023-06-01"


class CountError(RuntimeError):
    """Подсчёт через API не удался."""


def count_tokens(
    text: str,
    model: str,
    system: str | None = None,
    client: httpx.Client | None = None,
    api_key: str | None = None,
    timeout: float = 30.0,
) -> int:
    """Возвращает input_tokens, как их посчитает модель для такого запроса."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise CountError("Для точного подсчёта нужна переменная окружения ANTHROPIC_API_KEY")

    payload = {"model": model, "messages": [{"role": "user", "content": text}]}
    if system:
        payload["system"] = system
    headers = {"x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json"}

    own = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        response = client.post(COUNT_URL, json=payload, headers=headers)
    except httpx.RequestError as err:
        raise CountError(f"Сеть: {err}") from None
    finally:
        if own:
            client.close()

    if response.status_code != 200:
        # Текст ошибки обрезаем: в логи и консоль не нужно тащить весь ответ
        raise CountError(f"{response.status_code}: {response.text[:200]}")
    try:
        tokens = response.json()["input_tokens"]
    except (ValueError, KeyError, TypeError):
        raise CountError(f"Неожиданный ответ: {response.text[:200]}") from None
    if not isinstance(tokens, int):
        raise CountError(f"Неожиданный ответ: {response.text[:200]}")
    return tokens
