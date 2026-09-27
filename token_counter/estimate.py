"""Грубая оценка числа токенов по тексту, без сети и без токенизатора.

Точное число токенов знает только токенизатор конкретной модели. У Anthropic
он не опубликован, у OpenAI словари токенизатора скачиваются из сети при первом
запуске. Поэтому здесь честная прикидка по классам символов, которая нужна,
чтобы заранее понять порядок трат, а не чтобы выставлять счёт.

Коэффициенты подобраны грубо и не откалиброваны на настоящем токенизаторе.
Выбраны с запасом в большую сторону: для бюджета лучше переоценить, чем недооценить.
Для точного числа есть count_tokens (запрос к API Anthropic, нужен ключ) или
поле usage в ответе модели.
"""

import math
from dataclasses import dataclass

# Сколько символов в среднем приходится на один токен.
# Про английский текст OpenAI пишет «около 4 символов на токен».
# Кириллица режется на токены заметно мельче, берём с запасом.
LATIN_PER_TOKEN = 4.0
CYRILLIC_PER_TOKEN = 2.5
DIGITS_PER_TOKEN = 2.0


@dataclass(frozen=True)
class Estimate:
    tokens: int
    latin: int
    cyrillic: int
    digits: int
    other: int
    approximate: bool = True


def _is_cyrillic(ch: str) -> bool:
    return "Ѐ" <= ch <= "ӿ"


def estimate_tokens(text: str) -> Estimate:
    """Прикидывает число токенов по тексту.

    Пробелы и переносы строк отдельно не считаются: токенизаторы обычно
    приклеивают пробел к следующему слову. Знаки препинания, эмодзи,
    иероглифы и прочее считаются по токену на символ, это верхняя граница.
    """
    latin = cyrillic = digits = other = 0
    for ch in text:
        if ch.isspace():
            continue
        if ch.isascii() and ch.isalpha():
            latin += 1
        elif ch.isdigit():
            digits += 1
        elif _is_cyrillic(ch):
            cyrillic += 1
        else:
            other += 1

    raw = latin / LATIN_PER_TOKEN + cyrillic / CYRILLIC_PER_TOKEN + digits / DIGITS_PER_TOKEN + other
    tokens = math.ceil(raw) if text.strip() else 0
    return Estimate(tokens=tokens, latin=latin, cyrillic=cyrillic, digits=digits, other=other)
