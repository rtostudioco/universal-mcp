"""Módulo ``analysis`` — estadística, matemáticas seguras y regresión.

- ``analysis_math_eval`` evalúa expresiones aritméticas con un AST whitelist
  (sin ``eval`` genérico → sin riesgo de ejecución de código).
- ``analysis_stats`` / ``correlation`` / ``linear_regression`` usan la
  librería estándar (``statistics`` + álgebra manual).
"""

from __future__ import annotations

import ast
import math
import operator
import statistics
from collections import Counter
from typing import Any

from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext
from universal_mcp.core.exceptions import ToolExecutionError
from universal_mcp.core.utils import to_json

# ----------------------------------------------------------------------
# Evaluador matemático seguro (AST whitelist)
# ----------------------------------------------------------------------
_BINOPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_FUNCS: dict[str, Any] = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "exp": math.exp,
    "abs": abs,
    "floor": math.floor,
    "ceil": math.ceil,
    "round": round,
    "min": min,
    "max": max,
    "pow": pow,
}

_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
}

_MAX_POW_EXPONENT = 1000
_MAX_RESULT = 1e15


def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ToolExecutionError(f"Constante no numérica: {node.value!r}")
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(float(right)) > _MAX_POW_EXPONENT:
            raise ToolExecutionError("Exponente demasiado grande (máx. 1000).")
        return _BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCS
        and not node.keywords
    ):
        return _FUNCS[node.func.id](*[_eval_node(arg) for arg in node.args])
    raise ToolExecutionError(f"Elemento de expresión no permitido: {type(node).__name__}")


def math_eval_impl(expression: str) -> float:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ToolExecutionError(f"Expresión inválida: {exc}") from exc
    result = _eval_node(tree)
    if isinstance(result, complex):
        raise ToolExecutionError("El resultado no es un número real válido.")
    try:
        numeric = float(result)
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError("El resultado no es numérico.") from exc
    if math.isnan(numeric):
        raise ToolExecutionError("El resultado no es un número real válido.")
    if abs(numeric) > _MAX_RESULT:
        raise ToolExecutionError("Resultado demasiado grande.")
    return numeric


# ----------------------------------------------------------------------
# Estadística
# ----------------------------------------------------------------------
def stats_impl(numbers: list[float]) -> dict[str, Any]:
    if not numbers:
        raise ToolExecutionError("Proporciona al menos un número.")
    values = [float(n) for n in numbers]
    count = len(values)
    result: dict[str, Any] = {
        "n": count,
        "sum": sum(values),
        "mean": sum(values) / count,
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
        "median": statistics.median(values),
    }
    if count > 1:
        result["stdev"] = statistics.stdev(values)
        result["variance"] = statistics.variance(values)
        quantiles = statistics.quantiles(values, n=20)
        result["p25"] = quantiles[4]
        result["p50"] = quantiles[9]
        result["p75"] = quantiles[14]
        result["p90"] = quantiles[17]
    return result


def _pearson_parts(x: list[float], y: list[float]) -> tuple[float, float, float | None]:
    if len(x) != len(y):
        raise ToolExecutionError("x e y deben tener la misma longitud.")
    if len(x) < 2:
        raise ToolExecutionError("Se necesitan al menos 2 puntos.")
    n = len(x)
    mean_x, mean_y = sum(x) / n, sum(y) / n
    sxy = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True))
    sxx = sum((a - mean_x) ** 2 for a in x)
    syy = sum((b - mean_y) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return 0.0, mean_y, None
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    r = sxy / math.sqrt(sxx * syy)
    return slope, intercept, r


def linear_regression_impl(x: list[float], y: list[float]) -> dict[str, Any]:
    slope, intercept, r = _pearson_parts(x, y)
    return {
        "slope": slope,
        "intercept": intercept,
        "r": r,
        "r_squared": r * r if r is not None else None,
        "n": len(x),
        "equation": f"y = {slope:.6g}·x + {intercept:.6g}",
    }


def correlation_impl(x: list[float], y: list[float]) -> dict[str, Any]:
    _slope, _intercept, r = _pearson_parts(x, y)
    if r is None:
        raise ToolExecutionError("No se puede calcular correlación (varianza cero).")
    magnitude = abs(r)
    strength = (
        "perfect"
        if magnitude >= 0.99
        else "strong"
        if magnitude >= 0.7
        else "moderate"
        if magnitude >= 0.4
        else "weak"
    )
    return {
        "pearson_r": round(r, 6),
        "r_squared": round(r * r, 6),
        "direction": "positive" if r > 0 else "negative",
        "strength": strength,
        "n": len(x),
    }


def frequency_impl(items: list[str], top: int = 20) -> dict[str, Any]:
    counter = Counter(str(item) for item in items)
    limit = max(1, min(int(top), 100))
    return {
        "unique": len(counter),
        "most_common": [
            {"item": item, "count": count}
            for item, count in counter.most_common(limit)
        ],
    }


# ----------------------------------------------------------------------
# Registro de tools
# ----------------------------------------------------------------------
class AnalysisModule(BaseModule):
    name = "analysis"
    description = "Estadística descriptiva, evaluación matemática segura y regresión lineal."

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(
            name="stats",
            description=(
                "Descriptive statistics for a list of numbers: n, sum, mean, median, "
                "min/max, stdev, variance and percentiles (p25/p50/p75/p90)."
            ),
        )
        def stats(numbers: list[float]) -> str:
            try:
                return to_json(stats_impl(numbers))
            except ToolExecutionError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})

        @ctx.tool(
            name="math_eval",
            description=(
                "Safely evaluate an arithmetic expression: + - * / // % **, parentheses, "
                "sqrt/sin/cos/tan/log/exp/abs/floor/ceil/round/min/max and pi/e/tau. "
                "No code execution."
            ),
        )
        def math_eval(expression: str) -> str:
            try:
                return to_json({"expression": expression, "result": math_eval_impl(expression)})
            except ToolExecutionError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})

        @ctx.tool(
            name="linear_regression",
            description=(
                "Fit y = slope·x + intercept by least squares. Returns slope, intercept, "
                "r, r_squared and the equation string."
            ),
        )
        def linear_regression(x: list[float], y: list[float]) -> str:
            try:
                return to_json(linear_regression_impl(x, y))
            except ToolExecutionError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})

        @ctx.tool(
            name="correlation",
            description="Pearson correlation coefficient (r, r², direction, strength).",
        )
        def correlation(x: list[float], y: list[float]) -> str:
            try:
                return to_json(correlation_impl(x, y))
            except ToolExecutionError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})

        @ctx.tool(
            name="frequency",
            description="Count occurrences of each item and return the most common ones.",
        )
        def frequency(items: list[str], top: int = 20) -> str:
            return to_json(frequency_impl(items, top))
