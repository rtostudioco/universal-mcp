"""Módulo ``data`` — lectura de datos: CSV, JSON, aplanado y SQLite.

Las rutas se resuelven dentro del sandbox del workspace y SQLite opera en
modo solo-lectura (``PRAGMA query_only`` + whitelist SELECT/WITH/PRAGMA/EXPLAIN).
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext
from universal_mcp.core.exceptions import MCPError, SecurityViolationError, ToolExecutionError
from universal_mcp.core.sandbox import resolve_in_workspace
from universal_mcp.core.utils import clamp, to_json

_MAX_JSON_BYTES = 10 * 1024 * 1024  # 10 MB


# ----------------------------------------------------------------------
# Implementaciones puras
# ----------------------------------------------------------------------
def flatten_json_impl(data: Any, separator: str = ".") -> dict[str, Any]:
    out: dict[str, Any] = {}

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict) and value:
            for key, sub in value.items():
                walk(f"{prefix}{separator}{key}" if prefix else str(key), sub)
        elif isinstance(value, list) and value:
            for index, sub in enumerate(value):
                walk(f"{prefix}{separator}{index}" if prefix else str(index), sub)
        else:
            out[prefix] = value

    walk("", data)
    return out


def read_csv_impl(path: Path, limit: int, delimiter: str) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        columns = list(reader.fieldnames or [])
        rows: list[dict[str, Any]] = []
        total = 0
        for row in reader:
            total += 1
            if len(rows) < limit:
                rows.append(row)
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "total_rows": total,
        "truncated": total > len(rows),
    }


_ALLOWED_SQL_PREFIXES = {"SELECT", "WITH", "PRAGMA", "EXPLAIN"}


def sqlite_query_impl(db_path: Path, sql: str, limit: int) -> dict[str, Any]:
    if not db_path.is_file():
        raise ToolExecutionError(f"Base de datos no encontrada: {db_path.name}")
    statement = sql.strip().rstrip(";")
    first_word = statement.split(None, 1)[0].upper() if statement else ""
    if first_word not in _ALLOWED_SQL_PREFIXES:
        raise SecurityViolationError(
            "Solo se permiten consultas de lectura (SELECT/WITH/PRAGMA/EXPLAIN)."
        )
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA query_only = ON")
        cursor = connection.execute(statement)
        cap = int(clamp(limit, 1, 1000))
        rows = cursor.fetchmany(cap + 1)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        truncated = len(rows) > cap
        return {
            "columns": columns,
            "rows": [list(row) for row in rows[:cap]],
            "row_count": len(rows[:cap]),
            "truncated": truncated,
        }
    except sqlite3.Error as exc:
        raise ToolExecutionError(f"Error SQLite: {exc}") from exc
    finally:
        connection.close()


# ----------------------------------------------------------------------
# Registro de tools
# ----------------------------------------------------------------------
class DataModule(BaseModule):
    name = "data"
    description = "Lectura de CSV/JSON, aplanado de estructuras y SQLite de solo lectura."

    def _resolve(self, path: str) -> Path:
        base = self.settings.workspace_dir if self.settings else Path("./workspace")
        return resolve_in_workspace(base, path)

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(
            name="read_csv",
            description="Read a CSV file from the sandbox. Returns columns, sample rows and totals.",
        )
        def read_csv(path: str, limit: int = 50, delimiter: str = ",") -> str:
            try:
                target = self._resolve(path)
                return to_json(
                    read_csv_impl(target, int(clamp(limit, 1, 1000)), delimiter[:1] or ",")
                )
            except MCPError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})
            except (OSError, UnicodeDecodeError, csv.Error) as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})

        @ctx.tool(
            name="read_json",
            description="Read and parse a JSON file from the sandbox (max 10 MB).",
        )
        def read_json(path: str) -> str:
            try:
                target = self._resolve(path)
                if not target.is_file():
                    return to_json({"error": f"No es un archivo: {path}"})
                if target.stat().st_size > _MAX_JSON_BYTES:
                    return to_json({"error": "Archivo JSON demasiado grande (>10 MB)"})
                return to_json(json.loads(target.read_text(encoding="utf-8")))
            except MCPError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})
            except json.JSONDecodeError as exc:
                return to_json({"error": f"JSON inválido: {exc}"})

        @ctx.tool(
            name="flatten_json",
            description=(
                "Flatten nested JSON objects/arrays into a single-level dict with dotted keys. "
                "Pass data as a JSON value."
            ),
        )
        def flatten_json(data: Any, separator: str = ".") -> str:
            try:
                return to_json(flatten_json_impl(data, separator[:3] or "."))
            except Exception as exc:  # noqa: BLE001
                return to_json({"error": str(exc), "type": type(exc).__name__})

        @ctx.tool(
            name="sqlite_query",
            description=(
                "Run a READ-ONLY SQL query (SELECT/WITH) against a SQLite file in the sandbox. "
                "Writes and DDL are blocked."
            ),
        )
        def sqlite_query(path: str, sql: str, limit: int = 100) -> str:
            try:
                target = self._resolve(path)
                return to_json(sqlite_query_impl(target, sql, limit))
            except MCPError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})

        @ctx.tool(
            name="to_json",
            description="Serialize any JSON-serializable data into a pretty JSON string.",
        )
        def to_json_tool(data: Any, indent: int = 2) -> str:
            try:
                return to_json(data, indent=int(clamp(indent, 0, 8)))
            except Exception as exc:  # noqa: BLE001
                return to_json({"error": str(exc), "type": type(exc).__name__})
