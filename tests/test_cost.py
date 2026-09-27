from decimal import Decimal

import pytest

from token_counter.cost import Usage, cost, format_usd
from token_counter.prices import PriceError, parse_prices

PRICES = parse_prices({"models": {
    "a": {"provider": "anthropic", "input": "3", "output": "15", "cache_write": "3.75", "cache_read": "0.30",
          "checked": "2026-09-27", "source": "https://example.com"},
    "g": {"provider": "groq", "input": "0.15", "output": "0.60", "cache_write": None, "cache_read": None,
          "checked": "2026-09-27", "source": "https://example.com"},
}})


def test_simple_cost():
    c = cost(Usage(1200, 300), PRICES["a"])
    assert c.input == Decimal("0.0036")
    assert c.output == Decimal("0.0045")
    assert c.total == Decimal("0.0081")


def test_no_float_drift_on_many_small_requests():
    # 10 000 запросов по 7 токенов по 0.15 за миллион: во float набегает ошибка
    one = cost(Usage(7, 0), PRICES["g"])
    assert one.times(10_000).total == Decimal("0.0105")


def test_cache_tokens_priced_separately():
    c = cost(Usage(100, 0, cache_write_tokens=1000, cache_read_tokens=10_000), PRICES["a"])
    assert c.cache_write == Decimal("0.00375")
    assert c.cache_read == Decimal("0.003")
    assert c.total == Decimal("0.00705")


def test_cache_tokens_without_cache_price_fail_loudly():
    with pytest.raises(PriceError, match="кэш"):
        cost(Usage(10, 10, cache_read_tokens=5), PRICES["g"])
    # а без таких токенов всё считается
    assert cost(Usage(10, 10), PRICES["g"]).total > 0


def test_usage_from_api_dict():
    u = Usage.from_api({"input_tokens": 12, "output_tokens": 5,
                        "cache_creation_input_tokens": None, "cache_read_input_tokens": 40})
    assert u == Usage(12, 5, 0, 40)


def test_usage_sum():
    assert Usage(1, 2) + Usage(3, 4, 5, 6) == Usage(4, 6, 5, 6)


@pytest.mark.parametrize("bad", [-1, 1.5, "10", True])
def test_usage_rejects_bad_numbers(bad):
    with pytest.raises(ValueError):
        Usage(input_tokens=bad)


def test_times_rejects_negative():
    with pytest.raises(ValueError):
        cost(Usage(1, 1), PRICES["a"]).times(-1)


@pytest.mark.parametrize("amount, text", [
    ("0", "$0.00"),
    ("0.0081", "$0.0081"),
    ("0.000014", "$0.000014"),
    ("0.0000004", "$0.00"),
    ("0.1", "$0.10"),
    ("8.1", "$8.10"),
    ("12.345", "$12.35"),
])
def test_format_usd(amount, text):
    assert format_usd(Decimal(amount)) == text
