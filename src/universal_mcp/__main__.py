"""Punto de entrada CLI: ``python -m universal_mcp`` o ``universal-mcp``.

Lee la configuración desde variables de entorno / `.env`, descubre los
módulos disponibles y arranca el servidor con el transporte configurado.
"""

from __future__ import annotations

import sys

from universal_mcp.core.config import Settings
from universal_mcp.core.logging import setup_logging
from universal_mcp.core.server import UniversalMCPServer


def main() -> int:
    settings = Settings()
    setup_logging(settings.log_level)
    settings.ensure_dirs()

    server = UniversalMCPServer(settings)
    server.load_modules()

    try:
        server.run()
    except KeyboardInterrupt:
        print("\n universal-mcp: apagado limpio.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
