"""Pruebas de lógica pura: sandbox, matemáticas, datos y NLP."""

from __future__ import annotations

import sqlite3

import pytest

from universal_mcp.core.exceptions import SecurityViolationError, ToolExecutionError
from universal_mcp.core.sandbox import resolve_in_workspace
from universal_mcp.modules.ai import module as ai_module
from universal_mcp.modules.analysis import module as analysis_module
from universal_mcp.modules.data import module as data_module


# ----------------------------------------------------------------------
# Sandbox
# ----------------------------------------------------------------------
def test_sandbox_allows_paths_inside(tmp_path) -> None:
    target = resolve_in_workspace(tmp_path, "carpeta/archivo.txt")
    assert target == (tmp_path / "carpeta" / "archivo.txt").resolve()


def test_sandbox_blocks_relative_escape(tmp_path) -> None:
    with pytest.raises(SecurityViolationError):
        resolve_in_workspace(tmp_path, "../../etc/passwd")


def test_sandbox_blocks_absolute_escape(tmp_path) -> None:
    with pytest.raises(SecurityViolationError):
        resolve_in_workspace(tmp_path, "/etc/passwd")


def test_sandbox_blocks_symlink_escape(tmp_path) -> None:
    outside = tmp_path.parent / f"fuera_{abs(hash(str(tmp_path)))}"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SecurityViolationError):
        resolve_in_workspace(tmp_path, "link/archivo.txt")


# ----------------------------------------------------------------------
# analysis — matemáticas seguras
# ----------------------------------------------------------------------
def test_math_eval_basic() -> None:
    assert analysis_module.math_eval_impl("2 + 3 * 4") == 14
    assert analysis_module.math_eval_impl("(2 + 3) * 4") == 20
    assert analysis_module.math_eval_impl("2 ** 10") == 1024
    assert analysis_module.math_eval_impl("sqrt(16) + pi") == pytest.approx(7.1415926, abs=1e-6)


def test_math_eval_blocks_code_injection() -> None:
    with pytest.raises(ToolExecutionError):
        analysis_module.math_eval_impl("__import__('os').system('id')")
    with pytest.raises(ToolExecutionError):
        analysis_module.math_eval_impl("(lambda: 1)()")
    with pytest.raises(ToolExecutionError):
        analysis_module.math_eval_impl("'a' * 100")


def test_math_eval_blocks_huge_powers() -> None:
    with pytest.raises(ToolExecutionError):
        analysis_module.math_eval_impl("9 ** 999999")


# ----------------------------------------------------------------------
# analysis — estadística
# ----------------------------------------------------------------------
def test_stats_values() -> None:
    result = analysis_module.stats_impl([1, 2, 3, 4, 5])
    assert result["n"] == 5
    assert result["mean"] == 3
    assert result["min"] == 1 and result["max"] == 5
    assert "stdev" in result and "p75" in result


def test_stats_requires_numbers() -> None:
    with pytest.raises(ToolExecutionError):
        analysis_module.stats_impl([])


def test_linear_regression_perfect_line() -> None:
    result = analysis_module.linear_regression_impl([1, 2, 3, 4], [2, 4, 6, 8])
    assert result["slope"] == pytest.approx(2.0)
    assert result["intercept"] == pytest.approx(0.0, abs=1e-9)
    assert result["r_squared"] == pytest.approx(1.0)


def test_correlation_negative() -> None:
    result = analysis_module.correlation_impl([1, 2, 3, 4, 5], [10, 8, 6, 4, 2])
    assert result["direction"] == "negative"
    assert result["strength"] in {"perfect", "strong"}


def test_regression_length_mismatch() -> None:
    with pytest.raises(ToolExecutionError):
        analysis_module.linear_regression_impl([1, 2], [1])


# ----------------------------------------------------------------------
# data
# ----------------------------------------------------------------------
def test_flatten_json_nested() -> None:
    flat = data_module.flatten_json_impl({"a": {"b": [1, 2]}, "c": None})
    assert flat == {"a.b.0": 1, "a.b.1": 2, "c": None}


def test_sqlite_readonly(tmp_path) -> None:
    db = tmp_path / "test.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    con.close()

    with pytest.raises(SecurityViolationError):
        data_module.sqlite_query_impl(db, "DELETE FROM t", 10)
    with pytest.raises(SecurityViolationError):
        data_module.sqlite_query_impl(db, "CREATE TABLE evil (x INT)", 10)

    result = data_module.sqlite_query_impl(db, "SELECT x FROM t", 10)
    assert result["rows"] == [[1]]
    assert result["truncated"] is False


# ----------------------------------------------------------------------
# ai
# ----------------------------------------------------------------------
def test_ai_summarize_limits_sentences() -> None:
    text = ". ".join(
        f"La oración número {i} habla del sistema solar y los planetas rocosos."
        for i in range(1, 9)
    )
    result = ai_module.summarize_impl(text, max_sentences=2)
    assert result["summary_sentences"] <= 2
    assert result["original_sentences"] == 8


def test_ai_sentiment_positive_and_negative() -> None:
    positive = ai_module.sentiment_impl("I love this amazing product, excellent work!")
    assert positive["label"] == "positive"
    negative = ai_module.sentiment_impl("This is terrible, horrible and full of errors.")
    assert negative["label"] == "negative"


def test_ai_extract_emails() -> None:
    result = ai_module.extract_impl("Contacta a ana@ejemplo.com o bob@test.io", kind="emails")
    assert result["matches"] == ["ana@ejemplo.com", "bob@test.io"]


def test_ai_extract_unknown_kind() -> None:
    with pytest.raises(ToolExecutionError):
        ai_module.extract_impl("x", kind="dna")


def test_ai_slugify_accents() -> None:
    assert ai_module.slugify_impl("Café Ñandú 2024")["slug"] == "cafe-nandu-2024"


def test_ai_keywords_removes_stopwords() -> None:
    result = ai_module.keywords_impl("El perro corre y el gato duerme. El perro ladra.", top=3)
    words = [k["word"] for k in result["keywords"]]
    assert "el" not in words and "y" not in words
    assert words[0] == "perro"
