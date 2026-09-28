# token-counter

[![Тесты](https://github.com/maarshir/token-counter/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/maarshir/token-counter/actions/workflows/tests.yml)

Считает, сколько стоит запрос к языковой модели: по токенам из ответа API или по тексту промпта ещё до отправки. Для тех, кто гоняет промпты пачками и хочет знать траты в деньгах, а не в токенах.

```text
$ python -m token_counter cost --model claude-sonnet-4-6 --input 1200 --output 300 --times 1000
Модель: claude-sonnet-4-6 (цены на 2026-09-27)
  вход              $0.0036
  выход             $0.0045
  итого             $0.0081
  за 1000 запросов  $8.10
```

Это настоящий вывод программы. Вход, выход, запись в кэш промпта и чтение из него считаются по своим ценам, у каждой цены в таблице есть дата сверки и ссылка на источник.

## Установка

```bash
pip install "token-counter @ git+https://github.com/maarshir/token-counter"
token-counter models
```

Нужен Python 3.10+. Таблица цен ставится вместе с пакетом. Для разработки: `git clone`, затем `pip install -r requirements.txt`.

## Использование

```bash
# таблица цен с датами и источниками
token-counter models

# стоимость по токенам из ответа API
token-counter cost --model claude-haiku-4-5 --input 5000 --output 800 --cache-read 20000

# прикидка по тексту промпта (файл, --text или стандартный ввод), без сети и без ключа
token-counter estimate --model claude-sonnet-4-6 --file prompt.txt --output 512 --times 100

# точное число входных токенов через бесплатный count_tokens Anthropic (нужен ANTHROPIC_API_KEY в окружении)
token-counter estimate --model claude-sonnet-4-6 --file prompt.txt --exact
```

Без установки те же команды работают как `python -m token_counter ...` из папки репозитория.

Из кода:

```python
from token_counter import Usage, cost, find_price, format_usd, load_prices

price = find_price("claude-sonnet-4-6", load_prices())
usage = Usage.from_api(response_json["usage"])       # ответ Anthropic
# usage = Usage.from_openai(response_json["usage"])  # Groq и другие OpenAI-совместимые API
print(format_usd(cost(usage, price).total))
```

Сейчас в таблице четыре модели Anthropic и две открытые модели на Groq, цены сверены 27.09.2026. Свою таблицу можно подложить через `--prices` или `TOKEN_COUNTER_PRICES`. Имя модели с датой в конце (`claude-haiku-4-5-20251001`) находит ту же цену, при опечатке программа подсказывает похожее имя.

## Что было непросто

- **Деньги нельзя считать во float.** Цены лежат в JSON строками и читаются в `Decimal`; число без кавычек загрузчик отклоняет, потому что оно уже прошло через float. 10 000 одинаковых запросов дают ровно 0.0105, во float получалось 0.010500000000000956.
- **Мелкие суммы не должны превращаться в $0.00.** От доллара и выше два знака, ниже до шести знаков без лишних нулей.
- **Прикидка токенов без токенизатора.** Точное число знает только токенизатор модели, а работать нужно без сети. Прикидка идёт по классам символов с запасом в большую сторону и честно помечена «≈»; для точного числа есть `--exact`.
- **Кэш промпта в двух форматах посчитан по-разному.** У Anthropic кэш приходит отдельными полями, а у OpenAI и Groq уже входит в `prompt_tokens`. Без отдельного `Usage.from_openai` кэш посчитался бы дважды.

Подробнее о решениях и выборе технологий: [docs/решения.md](docs/решения.md).

## Что дальше

- Предупреждение, если дата сверки цен слишком старая.
- Больше моделей в таблице.
- Точный подсчёт без сети там, где токенизатор открыт и лицензия позволяет положить его рядом.

Тесты: `pytest`, сеть в них подменена, ключ не нужен.

Может работать в связке с [promptdiff](https://github.com/maarshir/promptdiff-): тот показывает через token-counter цену каждого варианта промпта.
