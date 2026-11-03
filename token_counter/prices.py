"""Таблица цен: загрузка, проверка и поиск модели по имени."""

import difflib
import json
import os
import re
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

DEFAULT_PRICES = Path(__file__).with_name("prices.json")

# Переменная окружения со своим файлом цен: цены меняются чаще, чем код,
# и обновлять их должно быть можно без правки пакета.
PRICES_ENV = "TOKEN_COUNTER_PRICES"

# claude-haiku-4-5-20251001 и claude-haiku-4-5 это одна модель и одна цена.
DATE_SUFFIX = re.compile(r"-\d{8}$")

MILLION = Decimal(1_000_000)

# Через сколько дней после сверки цену стоит проверить заново
STALE_DAYS = 30


class PriceError(ValueError):
    """Файл цен сломан или модели в нём нет."""


@dataclass(frozen=True)
class LongPrompt:
    """Цены для длинного промпта: у части моделей весь запрос дороже, если промпт длиннее порога."""
    threshold: int          # до этого числа токенов промпта включительно действует обычная цена
    input: Decimal
    output: Decimal
    cache_write: Decimal | None
    cache_read: Decimal | None


@dataclass(frozen=True)
class Price:
    model: str
    provider: str
    input: Decimal          # за миллион входных токенов
    output: Decimal         # за миллион выходных
    cache_write: Decimal | None  # запись в кэш промпта, если поставщик его считает отдельно
    cache_read: Decimal | None   # чтение из кэша промпта
    checked: str            # дата сверки с источником
    source: str             # откуда взята цена
    long_prompt: LongPrompt | None = None  # цены выше порога длины промпта, если они есть


def _money(value, model: str, field: str, optional: bool = False) -> Decimal | None:
    if value is None and optional:
        return None
    # float не принимаем: 0.1 во float это уже не 0.1, а деньги считаем точно
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise PriceError(f"{model}: поле {field} должно быть строкой с числом, например \"3.75\"")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise PriceError(f"{model}: в поле {field} не число: {value!r}") from None
    if not number.is_finite() or number < 0:
        raise PriceError(f"{model}: в поле {field} недопустимое значение: {value!r}")
    return number


def _long_prompt(value, model: str) -> LongPrompt | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise PriceError(f"{model}: long_prompt должен быть словарём с threshold и ценами")
    threshold = value.get("threshold")
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold <= 0:
        raise PriceError(f"{model}: long_prompt.threshold должен быть целым числом больше нуля")
    return LongPrompt(
        threshold=threshold,
        input=_money(value.get("input"), model, "long_prompt.input"),
        output=_money(value.get("output"), model, "long_prompt.output"),
        cache_write=_money(value.get("cache_write"), model, "long_prompt.cache_write", optional=True),
        cache_read=_money(value.get("cache_read"), model, "long_prompt.cache_read", optional=True),
    )


def parse_prices(data: dict) -> dict[str, Price]:
    """Проверяет содержимое файла цен и превращает его в словарь Price."""
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, dict) or not models:
        raise PriceError("В файле цен нет раздела models или он пустой")

    prices = {}
    for name, row in models.items():
        if not isinstance(row, dict):
            raise PriceError(f"{name}: ожидался словарь с ценами")
        for field in ("provider", "checked", "source"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise PriceError(f"{name}: не заполнено поле {field}")
        prices[name] = Price(
            model=name,
            provider=row["provider"],
            input=_money(row.get("input"), name, "input"),
            output=_money(row.get("output"), name, "output"),
            cache_write=_money(row.get("cache_write"), name, "cache_write", optional=True),
            cache_read=_money(row.get("cache_read"), name, "cache_read", optional=True),
            checked=row["checked"],
            source=row["source"],
            long_prompt=_long_prompt(row.get("long_prompt"), name),
        )
    return prices


def load_prices(path: str | Path | None = None) -> dict[str, Price]:
    """Читает таблицу цен: явный путь, иначе TOKEN_COUNTER_PRICES, иначе встроенная."""
    path = Path(path or os.environ.get(PRICES_ENV) or DEFAULT_PRICES)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PriceError(f"Нет файла цен: {path}") from None
    except json.JSONDecodeError as err:
        raise PriceError(f"Файл цен {path} не читается как JSON: {err}") from None
    return parse_prices(data)


def find_price(model: str, prices: dict[str, Price]) -> Price:
    """Ищет цену модели. Дату в конце имени отбрасывает, при опечатке подсказывает."""
    if model in prices:
        return prices[model]
    short = DATE_SUFFIX.sub("", model)
    if short in prices:
        return prices[short]

    close = difflib.get_close_matches(short, list(prices), n=1, cutoff=0.6)
    hint = f" Может быть, {close[0]}?" if close else ""
    raise PriceError(
        f"Нет цены для модели {model}.{hint} "
        f"Известные: {', '.join(sorted(prices))}. "
        f"Свою таблицу можно указать через --prices или {PRICES_ENV}."
    )


def price_for_prompt(price: Price, prompt_tokens: int) -> Price:
    """Цена, по которой считается весь запрос с промптом такой длины.

    Длина промпта по правилу Anthropic: все входные токены вместе с записью
    в кэш и чтением из него, выходные не считаются. Ровно на пороге ещё
    обычная цена, выше порога весь запрос, включая ответ, идёт по второй.
    """
    long = price.long_prompt
    if long is None or prompt_tokens <= long.threshold:
        return price
    return replace(price, input=long.input, output=long.output,
                   cache_write=long.cache_write, cache_read=long.cache_read, long_prompt=None)


def _checked_date(price: Price) -> date | None:
    try:
        return date.fromisoformat(price.checked)
    except (TypeError, ValueError):
        return None


def is_stale(price: Price, today: date, days: int = STALE_DAYS) -> bool:
    """Цена сверена больше days дней назад или дата сверки неизвестна. days=0 выключает проверку."""
    if days <= 0:
        return False
    checked = _checked_date(price)
    return checked is None or (today - checked).days > days


def stale_warning(price: Price, today: date, days: int = STALE_DAYS) -> str | None:
    """Строка предупреждения для устаревшей цены или None, если цена свежая."""
    if not is_stale(price, today, days):
        return None
    checked = _checked_date(price)
    if checked is None:
        return f"Цена {price.model} без даты сверки: проверьте по {price.source}"
    return (f"Цена {price.model} сверена {checked:%d.%m.%Y}, больше {days} дней назад: "
            f"проверьте по {price.source}")
