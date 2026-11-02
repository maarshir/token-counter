from datetime import date

import pytest

from token_counter import cli
from token_counter.prices import find_price, is_stale, load_prices, parse_prices, stale_warning

SOURCE = "https://example.com/pricing"


def price(checked="2026-10-01"):
    row = {"provider": "x", "input": "1", "output": "2", "checked": checked, "source": SOURCE}
    return parse_prices({"models": {"m": row}})["m"]


def test_fresh_price_is_not_stale():
    assert not is_stale(price(), date(2026, 10, 15))
    assert stale_warning(price(), date(2026, 10, 15)) is None


def test_exactly_30_days_is_not_stale_yet():
    assert not is_stale(price(), date(2026, 10, 31))


def test_31_days_is_stale_and_warning_names_date_and_source():
    assert is_stale(price(), date(2026, 11, 1))
    warning = stale_warning(price(), date(2026, 11, 1))
    assert warning == f"Цена m сверена 01.10.2026, больше 30 дней назад: проверьте по {SOURCE}"


def test_threshold_is_configurable():
    assert is_stale(price(), date(2026, 10, 9), days=7)
    assert not is_stale(price(), date(2026, 11, 20), days=60)


def test_zero_days_turns_check_off():
    assert not is_stale(price("2020-01-01"), date(2026, 11, 1), days=0)


def test_unknown_check_date_counts_as_stale():
    p = price("когда-то")
    assert is_stale(p, date(2026, 10, 2))
    assert "без даты сверки" in stale_warning(p, date(2026, 10, 2))


def test_library_functions_print_nothing(capsys):
    prices = load_prices()
    find_price("claude-sonnet-4-6", prices)
    is_stale(prices["claude-sonnet-4-6"], date(2030, 1, 1))
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


# Командная строка: «сегодня» подменяем, чтобы тесты не зависели от даты запуска

FAR_FUTURE = date(2030, 1, 1)


@pytest.fixture
def today(monkeypatch):
    def set_today(day):
        monkeypatch.setattr(cli, "_today", lambda: day)
    return set_today


def run(capsys, *argv):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cost_warns_in_stderr_and_keeps_stdout(capsys, today):
    args = ("cost", "--model", "claude-sonnet-4-6", "--input", "1200", "--output", "300")
    today(FAR_FUTURE)
    code, old_out, err = run(capsys, *args)
    assert code == 0
    assert err.count("\n") == 1
    assert "claude-sonnet-4-6 сверена" in err and "больше 30 дней назад" in err

    today(FAR_FUTURE)
    _, out_off, err_off = run(capsys, *args, "--stale-days", "0")
    assert err_off == ""
    assert out_off == old_out


def test_cost_with_fresh_prices_is_silent(capsys, today):
    checked = date.fromisoformat(load_prices()["claude-sonnet-4-6"].checked)
    today(checked)
    code, _, err = run(capsys, "cost", "--model", "claude-sonnet-4-6", "--input", "10")
    assert code == 0 and err == ""


def test_estimate_warns_too(capsys, today):
    today(FAR_FUTURE)
    code, out, err = run(capsys, "estimate", "--model", "claude-haiku-4-5", "--text", "abcd", "--stale-days", "45")
    assert code == 0 and "≈1" in out
    assert "больше 45 дней назад" in err


def test_models_marks_stale_rows(capsys, today):
    today(FAR_FUTURE)
    _, out, _ = run(capsys, "models")
    assert "давно, сверьте" in out
    today(FAR_FUTURE)
    _, out, _ = run(capsys, "models", "--stale-days", "0")
    assert "давно" not in out


def test_negative_stale_days_is_rejected(capsys):
    with pytest.raises(SystemExit):
        cli.main(["models", "--stale-days", "-1"])
    assert "от 0" in capsys.readouterr().err
