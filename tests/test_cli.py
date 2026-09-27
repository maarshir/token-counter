import io
import subprocess
import sys

import pytest

from token_counter import cli


def run(*argv):
    out = io.StringIO()
    code = cli.main(list(argv), out=out)
    return code, out.getvalue()


def test_models_lists_prices_and_sources():
    code, text = run("models")
    assert code == 0
    assert "claude-sonnet-4-6" in text
    assert "https://platform.claude.com/docs/en/about-claude/pricing" in text


def test_cost():
    code, text = run("cost", "--model", "claude-sonnet-4-6", "--input", "1200", "--output", "300", "--times", "1000")
    assert code == 0
    assert "$0.0081" in text
    assert "за 1000 запросов" in text and "$8.10" in text


def test_unknown_model_is_error_not_traceback(capsys):
    code, _ = run("cost", "--model", "gpt-nope", "--input", "1")
    assert code == 1
    assert "Нет цены" in capsys.readouterr().err


def test_negative_tokens_is_error(capsys):
    code, _ = run("cost", "--model", "claude-sonnet-4-6", "--input", "-5")
    assert code == 1
    assert "input_tokens" in capsys.readouterr().err


def test_estimate_marks_result_as_approximate():
    code, text = run("estimate", "--model", "claude-haiku-4-5", "--text", "abcd" * 10, "--output", "100")
    assert code == 0
    assert "≈10" in text and "оценка" in text


def test_estimate_from_file(tmp_path):
    f = tmp_path / "prompt.txt"
    f.write_text("abcd" * 8, encoding="utf-8")
    code, text = run("estimate", "--model", "claude-haiku-4-5", "--file", str(f))
    assert code == 0 and "≈8" in text


def test_exact_only_for_anthropic(capsys):
    code, _ = run("estimate", "--model", "openai/gpt-oss-20b", "--text", "x", "--exact")
    assert code == 1
    assert "Anthropic" in capsys.readouterr().err


def test_exact_uses_count_tokens(monkeypatch):
    monkeypatch.setattr(cli, "count_tokens", lambda text, model: 77)
    code, text = run("estimate", "--model", "claude-haiku-4-5", "--text", "x", "--exact")
    assert code == 0 and "77 (точно" in text


def test_python_m_entry_point():
    done = subprocess.run([sys.executable, "-m", "token_counter", "models"], capture_output=True, text=True)
    assert done.returncode == 0
    assert "claude-haiku-4-5" in done.stdout
