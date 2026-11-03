"""Módulo ``files`` — operaciones de archivos dentro de un sandbox.

Toda ruta se resuelve contra ``MCP_WORKSPACE_DIR`` y se valida con
:func:`universal_mcp.core.sandbox.resolve_in_workspace`: es imposible leer
o escribir fuera del workspace (incluye symlinks).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext
from universal_mcp.core.exceptions import MCPError
from universal_mcp.core.sandbox import resolve_in_workspace
from universal_mcp.core.utils import clamp, to_json

_MAX_FILE_SCAN_BYTES = 2 * 1024 * 1024  # 2 MB por archivo en búsquedas
_MAX_FILES_SCANNED = 800


class FilesModule(BaseModule):
    name = "files"
    description = "Lectura/escritura/búsqueda de archivos en un sandbox (workspace)."

    # ------------------------------------------------------------------
    def _resolve(self, path: str) -> Path:
        base = self.settings.workspace_dir if self.settings else Path("./workspace")
        return resolve_in_workspace(base, path)

    def _workspace_root(self) -> Path:
        base = self.settings.workspace_dir if self.settings else Path("./workspace")
        return Path(base).resolve()

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(
            name="list_files",
            description="List files/folders in the sandboxed workspace (relative paths only).",
        )
        def list_files(path: str = ".") -> str:
            try:
                target = self._resolve(path)
            except MCPError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})
            if not target.exists():
                return to_json({"error": f"Ruta no encontrada: {path}"})
            entries: list[dict[str, Any]] = []
            for child in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name)):
                try:
                    stat = child.stat()
                    entries.append(
                        {
                            "name": child.name,
                            "type": "dir" if child.is_dir() else "file",
                            "size": stat.st_size if child.is_file() else None,
                            "modified": datetime.fromtimestamp(
                                stat.st_mtime, tz=timezone.utc
                            ).isoformat(),
                        }
                    )
                except OSError:
                    continue
            return to_json({"path": path, "count": len(entries), "entries": entries})

        @ctx.tool(
            name="read_file",
            description="Read a UTF-8 text file from the sandbox (max_bytes caps the output).",
        )
        def read_file(path: str, max_bytes: int = 65_536) -> str:
            try:
                target = self._resolve(path)
                if not target.is_file():
                    return to_json({"error": f"No es un archivo: {path}"})
                cap = int(clamp(max_bytes, 1, 1_000_000))
                with target.open("rb") as fh:
                    raw = fh.read(cap + 1)
                return to_json(
                    {
                        "path": path,
                        "content": raw[:cap].decode("utf-8", errors="replace"),
                        "truncated": len(raw) > cap,
                        "bytes": target.stat().st_size,
                    }
                )
            except MCPError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})

        @ctx.tool(
            name="write_file",
            description="Write/append UTF-8 text to a file in the sandbox. Creates parent folders.",
        )
        def write_file(path: str, content: str, append: bool = False) -> str:
            try:
                target = self._resolve(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                data = content.encode("utf-8")
                with target.open("ab" if append else "wb") as fh:
                    fh.write(data)
                return to_json(
                    {"path": path, "bytes_written": len(data), "append": append}
                )
            except MCPError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})

        @ctx.tool(
            name="delete_file",
            description="Delete a file (never a directory) from the sandbox.",
        )
        def delete_file(path: str) -> str:
            try:
                target = self._resolve(path)
                if not target.exists():
                    return to_json({"error": f"No existe: {path}"})
                if target.is_dir():
                    return to_json(
                        {"error": "Solo se pueden borrar archivos, no directorios."}
                    )
                target.unlink()
                return to_json({"deleted": path})
            except MCPError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})

        @ctx.tool(
            name="search_files",
            description=(
                "Grep-like text search across sandbox files. Supports literal or regex queries. "
                "Returns matching file paths with line numbers."
            ),
        )
        def search_files(
            query: str,
            path: str = ".",
            glob_pattern: str = "**/*",
            regex: bool = False,
            max_results: int = 50,
        ) -> str:
            try:
                root = self._resolve(path)
                pattern = re.compile(query if regex else re.escape(query))
            except MCPError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})
            except re.error as exc:
                return to_json({"error": f"Regex inválida: {exc}"})

            limit = int(clamp(max_results, 1, 200))
            matches: list[dict[str, Any]] = []
            scanned = 0
            truncated = False
            workspace_root = self._workspace_root()
            for candidate in sorted(root.rglob(glob_pattern)):
                if len(matches) >= limit or scanned >= _MAX_FILES_SCANNED:
                    truncated = True
                    break
                if not candidate.is_file() or candidate.stat().st_size > _MAX_FILE_SCAN_BYTES:
                    continue
                try:
                    if b"\x00" in candidate.read_bytes()[:4096]:
                        continue  # binario
                    scanned += 1
                    with candidate.open("r", encoding="utf-8", errors="replace") as fh:
                        for lineno, line in enumerate(fh, start=1):
                            if pattern.search(line):
                                matches.append(
                                    {
                                        "path": str(
                                            candidate.relative_to(workspace_root)
                                        ),
                                        "line": lineno,
                                        "text": line.strip()[:200],
                                    }
                                )
                                if len(matches) >= limit:
                                    truncated = True
                                    break
                except OSError:
                    continue
            return to_json(
                {
                    "query": query,
                    "regex": regex,
                    "matches": matches,
                    "match_count": len(matches),
                    "truncated": truncated,
                }
            )
