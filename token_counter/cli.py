"""Командная строка: python -m token_counter <команда>."""

import argparse
import sys
from pathlib import Path

from .anthropic_count import CountError, count_tokens
from .cost import Usage, cost, format_usd
from .estimate import estimate_tokens
from .prices import PriceError, find_price, load_prices


def _read_text(args) -> str:
    if args.text is not None:
        return args.text
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if sys.stdin.isatty():
        raise SystemExit("Нужен текст: --text, --file или через стандартный ввод")
    return sys.stdin.read()


def cmd_models(args, out) -> int:
    prices = load_prices(args.prices)
    print("Цены в долларах за миллион токенов", file=out)
    print(f"{'модель':<22} {'поставщик':<10} {'вход':>7} {'выход':>7} {'кэш-запись':>11} {'кэш-чтение':>11}  сверено", file=out)
    for p in sorted(prices.values(), key=lambda p: (p.provider, p.model)):
        cw = str(p.cache_write) if p.cache_write is not None else "-"
        cr = str(p.cache_read) if p.cache_read is not None else "-"
        print(f"{p.model:<22} {p.provider:<10} {p.input!s:>7} {p.output!s:>7} {cw:>11} {cr:>11}  {p.checked}", file=out)
    sources = sorted({p.source for p in prices.values()})
    print("\nИсточники: " + ", ".join(sources), file=out)
    return 0


def _print_cost(c, n: int, out) -> None:
    rows = [("вход", c.input), ("выход", c.output), ("запись в кэш", c.cache_write), ("чтение из кэша", c.cache_read)]
    for name, value in rows:
        if value:
            print(f"  {name:<17} {format_usd(value)}", file=out)
    print(f"  {'итого':<17} {format_usd(c.total)}", file=out)
    if n > 1:
        print(f"  {'за ' + str(n) + ' запросов':<17} {format_usd(c.times(n).total)}", file=out)


def cmd_cost(args, out) -> int:
    price = find_price(args.model, load_prices(args.prices))
    usage = Usage(args.input, args.output, args.cache_write, args.cache_read)
    print(f"Модель: {price.model} (цены на {price.checked})", file=out)
    _print_cost(cost(usage, price), args.times, out)
    return 0


def cmd_estimate(args, out) -> int:
    price = find_price(args.model, load_prices(args.prices))
    text = _read_text(args)

    if args.exact:
        if price.provider != "anthropic":
            raise CountError("Точный подсчёт через API есть только для моделей Anthropic")
        tokens = count_tokens(text, args.model)
        print(f"Входных токенов: {tokens} (точно, count_tokens API)", file=out)
    else:
        tokens = estimate_tokens(text).tokens
        print(f"Входных токенов: ≈{tokens} (грубая оценка без токенизатора, с запасом)", file=out)

    print(f"Модель: {price.model} (цены на {price.checked}), ответ до {args.output} токенов", file=out)
    _print_cost(cost(Usage(tokens, args.output), price), args.times, out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="token_counter", description="Подсчёт токенов и стоимости запросов к моделям")
    parser.add_argument("--prices", help="свой файл цен в формате prices.json (или переменная TOKEN_COUNTER_PRICES)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("models", help="таблица цен")

    p = sub.add_parser("cost", help="стоимость по известному числу токенов")
    p.add_argument("--model", required=True)
    p.add_argument("--input", type=int, default=0, help="входные токены")
    p.add_argument("--output", type=int, default=0, help="выходные токены")
    p.add_argument("--cache-write", type=int, default=0, help="токены, записанные в кэш промпта")
    p.add_argument("--cache-read", type=int, default=0, help="токены, прочитанные из кэша промпта")
    p.add_argument("--times", type=int, default=1, help="сколько таких запросов")

    p = sub.add_parser("estimate", help="прикинуть токены и стоимость по тексту")
    p.add_argument("--model", required=True)
    src = p.add_mutually_exclusive_group()
    src.add_argument("--text")
    src.add_argument("--file")
    p.add_argument("--output", type=int, default=0, help="сколько токенов ответа закладывать (например, max_tokens)")
    p.add_argument("--times", type=int, default=1, help="сколько таких запросов")
    p.add_argument("--exact", action="store_true", help="точно через count_tokens API Anthropic (нужен ANTHROPIC_API_KEY)")
    return parser


COMMANDS = {"models": cmd_models, "cost": cmd_cost, "estimate": cmd_estimate}


def main(argv=None, out=None) -> int:
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args, out)
    except (PriceError, CountError, ValueError, OSError) as err:
        print(f"Ошибка: {err}", file=sys.stderr)
        return 1
