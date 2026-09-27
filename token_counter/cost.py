"""Стоимость запроса по числу токенов."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .prices import MILLION, Price, PriceError


@dataclass(frozen=True)
class Usage:
    """Сколько токенов ушло. Поля как в usage у Anthropic API, для OpenAI-формата есть from_openai.

    input_tokens у Anthropic не включает токены, записанные в кэш промпта
    и прочитанные из него, они приходят отдельными полями и стоят по-разному.
    """
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    def __post_init__(self):
        for name in ("input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} должно быть целым числом не меньше нуля, а не {value!r}")

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
        )

    @classmethod
    def from_api(cls, usage: dict) -> "Usage":
        """Из словаря usage, как его возвращает Anthropic API."""
        return cls(
            input_tokens=usage.get("input_tokens") or 0,
            output_tokens=usage.get("output_tokens") or 0,
            cache_write_tokens=usage.get("cache_creation_input_tokens") or 0,
            cache_read_tokens=usage.get("cache_read_input_tokens") or 0,
        )

    @classmethod
    def from_openai(cls, usage: dict) -> "Usage":
        """Из usage в формате OpenAI Chat Completions (так отвечают OpenAI, Groq и другие
        совместимые API).

        Здесь всё наоборот, чем у Anthropic: prompt_tokens уже включает токены,
        прочитанные из кэша промпта, а сами они лежат в prompt_tokens_details.cached_tokens.
        Чтобы не заплатить за них дважды, вычитаем их из обычного входа.
        Записи в кэш отдельно не бывает. Токены рассуждений у моделей с рассуждением
        входят в completion_tokens и оплачиваются как выход.
        """
        prompt = usage.get("prompt_tokens") or 0
        details = usage.get("prompt_tokens_details") or {}
        cached = details.get("cached_tokens") or 0
        if cached > prompt:
            raise ValueError(f"cached_tokens ({cached}) больше prompt_tokens ({prompt})")
        return cls(
            input_tokens=prompt - cached,
            output_tokens=usage.get("completion_tokens") or 0,
            cache_read_tokens=cached,
        )


@dataclass(frozen=True)
class Cost:
    model: str
    input: Decimal
    output: Decimal
    cache_write: Decimal
    cache_read: Decimal

    @property
    def total(self) -> Decimal:
        return self.input + self.output + self.cache_write + self.cache_read

    def times(self, n: int) -> "Cost":
        """Та же стоимость, умноженная на число одинаковых запросов."""
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise ValueError(f"число запросов должно быть целым не меньше нуля, а не {n!r}")
        return Cost(self.model, self.input * n, self.output * n, self.cache_write * n, self.cache_read * n)


def _part(tokens: int, price_per_million: Decimal | None, model: str, what: str) -> Decimal:
    if tokens == 0:
        return Decimal(0)
    if price_per_million is None:
        # Молча посчитать по цене обычного входа было бы враньём в отчёте
        raise PriceError(f"{model}: в таблице нет цены для {what}, а такие токены есть")
    return tokens * price_per_million / MILLION


def cost(usage: Usage, price: Price) -> Cost:
    """Считает стоимость без округления. Округляем только при выводе."""
    return Cost(
        model=price.model,
        input=_part(usage.input_tokens, price.input, price.model, "входа"),
        output=_part(usage.output_tokens, price.output, price.model, "выхода"),
        cache_write=_part(usage.cache_write_tokens, price.cache_write, price.model, "записи в кэш"),
        cache_read=_part(usage.cache_read_tokens, price.cache_read, price.model, "чтения из кэша"),
    )


def format_usd(amount: Decimal) -> str:
    """Деньги для человека: копеечные суммы не превращаются в $0.00.

    От доллара и выше два знака после точки, меньше доллара до шести,
    лишние нули в конце убираются, но минимум два знака остаётся.
    """
    if amount >= 1:
        return f"${amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
    text = f"{amount.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP):f}"
    whole, frac = text.split(".")
    frac = frac.rstrip("0").ljust(2, "0")
    return f"${whole}.{frac}"
