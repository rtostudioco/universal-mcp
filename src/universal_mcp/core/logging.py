"""Logging estructurado hacia **stderr**.

Importante: en transporte stdio, stdout está reservado al protocolo MCP,
por lo que *todo* log debe ir a stderr para no corromper la sesión.
"""

from __future__ import annotations

import logging
import sys

_NOISY_LOGGERS = (
    "uvicorn.access",
    "uvicorn.error",
    "mcp.server.streamable_http_manager",
    "mcp.server.lowlevel.server",
)


def setup_logging(level: str = "INFO", *, quiet_uvicorn: bool = True) -> None:
    """Configura el logging raíz hacia stderr."""
    resolved = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=resolved,
        stream=sys.stderr,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    if quiet_uvicorn:
        for name in _NOISY_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)
