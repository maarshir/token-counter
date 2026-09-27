from token_counter.estimate import estimate_tokens


def test_empty_text_is_zero():
    assert estimate_tokens("").tokens == 0
    assert estimate_tokens("   \n\t").tokens == 0


def test_english_about_four_chars_per_token():
    e = estimate_tokens("abcd" * 25)  # 100 латинских букв
    assert e.tokens == 25
    assert e.latin == 100


def test_cyrillic_counts_heavier_than_latin_of_same_length():
    assert estimate_tokens("а" * 100).tokens > estimate_tokens("a" * 100).tokens


def test_whitespace_is_not_counted():
    assert estimate_tokens("abcd abcd").tokens == estimate_tokens("abcdabcd").tokens


def test_punctuation_and_emoji_are_a_token_each():
    e = estimate_tokens("!?🙂")
    assert e.other == 3 and e.tokens == 3


def test_classes_are_counted_separately():
    e = estimate_tokens("вода water 300!")
    assert (e.cyrillic, e.latin, e.digits, e.other) == (4, 5, 3, 1)
    assert e.approximate is True


def test_rounds_up():
    assert estimate_tokens("a").tokens == 1
