import json
from decimal import Decimal

import pytest

from token_counter.prices import PriceError, find_price, load_prices, parse_prices


def row(**over):
    base = {"provider": "x", "input": "1", "output": "2", "cache_write": None, "cache_read": None,
            "checked": "2026-09-27", "source": "https://example.com"}
    base.update(over)
    return base


def test_builtin_table_loads_and_every_model_has_source_and_date():
    prices = load_prices()
    assert "claude-sonnet-4-6" in prices  # модель по умолчанию в promptdiff
    for p in prices.values():
        assert p.source.startswith("https://")
        assert len(p.checked) == 10
        assert p.input > 0 and p.output > 0


def test_prices_are_exact_decimals():
    p = parse_prices({"models": {"m": row(input="0.075")}})["m"]
    assert p.input == Decimal("0.075")


def test_float_price_is_rejected():
    with pytest.raises(PriceError, match="строкой"):
        parse_prices({"models": {"m": row(input=0.1)}})


@pytest.mark.parametrize("bad", ["abc", "-1", "NaN", True])
def test_bad_price_is_rejected(bad):
    with pytest.raises(PriceError):
        parse_prices({"models": {"m": row(output=bad)}})


def test_missing_source_is_rejected():
    with pytest.raises(PriceError, match="source"):
        parse_prices({"models": {"m": row(source="")}})


def test_empty_table_is_rejected():
    with pytest.raises(PriceError):
        parse_prices({"models": {}})
    with pytest.raises(PriceError):
        parse_prices([])


def test_date_suffix_is_ignored():
    prices = load_prices()
    assert find_price("claude-haiku-4-5-20251001", prices).model == "claude-haiku-4-5"


def test_typo_gets_a_hint():
    with pytest.raises(PriceError, match="claude-sonnet-4-6"):
        find_price("claude-sonet-4-6", load_prices())


def test_custom_file_via_env(tmp_path, monkeypatch):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"models": {"my-model": row()}}), encoding="utf-8")
    monkeypatch.setenv("TOKEN_COUNTER_PRICES", str(path))
    assert list(load_prices()) == ["my-model"]


def test_broken_file_gives_clear_error(tmp_path):
    path = tmp_path / "p.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(PriceError, match="JSON"):
        load_prices(path)
    with pytest.raises(PriceError, match="Нет файла"):
        load_prices(tmp_path / "nope.json")
