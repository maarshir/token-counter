"""Цена по длине промпта: выше порога весь запрос стоит дороже (Claude Haiku 5.5)."""

import io
from datetime import date
from decimal import Decimal

import pytest

from token_counter import cli
from token_counter.cost import Usage, cost
from token_counter.prices import (PriceError, find_price, is_stale, load_prices, parse_prices,
                                  price_for_prompt, stale_warning)

HAIKU = "claude-haiku-5-5"


def haiku():
    return find_price(HAIKU, load_prices())


def row(**over):
    base = {"provider": "x", "input": "1", "output": "2", "checked": "2026-11-02", "source": "https://example.com",
            "long_prompt": {"threshold": 10, "input": "3", "output": "4"}}
    base.update(over)
    return base


def test_haiku_5_5_prices_in_table():
    p = haiku()
    assert p.provider == "anthropic" and p.checked == "2026-11-02"
    assert (p.input, p.output, p.cache_write, p.cache_read) == (
        Decimal("0.10"), Decimal("0.50"), Decimal("0.125"), Decimal("0.01"))
    long = p.long_prompt
    assert long.threshold == 100_000
    assert (long.input, long.output, long.cache_write, long.cache_read) == (
        Decimal("0.50"), Decimal("2.50"), Decimal("0.625"), Decimal("0.05"))


def test_exactly_threshold_is_still_base_price():
    c = cost(Usage(input_tokens=100_000, output_tokens=1_000), haiku())
    assert c.input == Decimal("0.01") and c.output == Decimal("0.0005")


def test_one_token_over_threshold_prices_whole_request_higher():
    c = cost(Usage(input_tokens=100_001, output_tokens=1_000), haiku())
    assert c.input == Decimal("100001") * Decimal("0.50") / Decimal(1_000_000)
    assert c.output == Decimal("0.0025")  # ответ тоже по второй цене


def test_threshold_counts_cache_tokens_but_not_output():
    p = haiku()
    over = Usage(input_tokens=50_000, cache_write_tokens=30_000, cache_read_tokens=20_001)
    c = cost(over, p)
    assert c.cache_write == Decimal("30000") * Decimal("0.625") / Decimal(1_000_000)
    assert c.cache_read == Decimal("20001") * Decimal("0.05") / Decimal(1_000_000)

    # большой ответ длину промпта не увеличивает
    under = cost(Usage(input_tokens=60_000, output_tokens=90_000), p)
    assert under.output == Decimal("90000") * Decimal("0.50") / Decimal(1_000_000)


def test_models_without_long_prompt_are_unchanged():
    p = find_price("claude-sonnet-4-6", load_prices())
    assert p.long_prompt is None
    assert price_for_prompt(p, 10_000_000) is p
    assert cost(Usage(1_000_000, 1_000_000), p).total == Decimal(18)


def test_long_price_keeps_model_date_and_source():
    p = haiku()
    long = price_for_prompt(p, 200_000)
    assert (long.model, long.checked, long.source) == (p.model, p.checked, p.source)
    assert long.input == Decimal("0.50") and long.long_prompt is None


@pytest.mark.parametrize("bad", [0, -1, "100", True, None])
def test_bad_threshold_is_rejected(bad):
    with pytest.raises(PriceError, match="threshold"):
        parse_prices({"models": {"m": row(long_prompt={"threshold": bad, "input": "3", "output": "4"})}})


def test_long_prompt_prices_are_validated():
    with pytest.raises(PriceError, match="long_prompt.output"):
        parse_prices({"models": {"m": row(long_prompt={"threshold": 10, "input": "3", "output": 0.5})}})
    with pytest.raises(PriceError, match="словарём"):
        parse_prices({"models": {"m": row(long_prompt=[1])}})


def test_long_prompt_without_cache_price_fails_loudly():
    p = parse_prices({"models": {"m": row(cache_read="0.1")}})["m"]
    assert cost(Usage(input_tokens=5, cache_read_tokens=5), p).cache_read > 0
    with pytest.raises(PriceError, match="чтения из кэша"):
        cost(Usage(input_tokens=5, cache_read_tokens=6), p)


def test_stale_warning_works_for_haiku_5_5():
    p = haiku()
    assert not is_stale(p, date(2026, 11, 3))
    assert "claude-haiku-5-5 сверена 02.11.2026" in stale_warning(p, date(2030, 1, 1))


def run(*argv):
    out = io.StringIO()
    code = cli.main(list(argv), out=out)
    return code, out.getvalue()


def test_models_shows_second_row():
    code, text = run("models", "--stale-days", "0")
    assert code == 0
    assert "промпт > 100 000" in text
    lines = text.splitlines()
    i = next(n for n, line in enumerate(lines) if line.startswith(HAIKU))
    assert "промпт > 100 000" in lines[i + 1] and "2.50" in lines[i + 1]


def test_cost_cli_says_when_long_price_applies():
    _, text = run("cost", "--model", HAIKU, "--input", "100000", "--output", "1000", "--stale-days", "0")
    assert "повышенной" not in text and "$0.0105" in text
    _, text = run("cost", "--model", HAIKU, "--input", "90000", "--cache-read", "10001", "--output", "1000",
                  "--stale-days", "0")
    assert "Промпт длиннее 100 000 токенов" in text and "$0.048" in text


def test_estimate_uses_same_choice():
    long_text = "word " * 400_004  # 1 600 016 латинских букв, около 400 000 токенов
    _, text = run("estimate", "--model", HAIKU, "--text", long_text, "--output", "100", "--stale-days", "0")
    assert "Промпт длиннее" in text
    _, text = run("estimate", "--model", HAIKU, "--text", "abcd", "--output", "100", "--stale-days", "0")
    assert "Промпт длиннее" not in text
