"""Sandbox de rutas: toda tool de archivos queda confinada al workspace."""

from __future__ import annotations

from pathlib import Path

from universal_mcp.core.exceptions import SecurityViolationError


def resolve_in_workspace(base: Path, relative: str | Path) -> Path:
    """Resuelve ``relative`` dentro de ``base`` y garantiza que no escape.

    Lanza :class:`SecurityViolationError` si la ruta (incluyendo symlinks)
    apunta fuera del workspace.
    """
    root = Path(base).resolve()
    target = (root / str(relative)).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise SecurityViolationError(
            f"Ruta fuera del sandbox del workspace: {relative!r} "
            f"(workspace: {root})"
        ) from None
    return target
