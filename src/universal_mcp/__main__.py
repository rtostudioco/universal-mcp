"""Punto de entrada CLI: ``python -m universal_mcp`` o ``universal-mcp``.

Lee la configuración desde variables de entorno / `.env`, descubre los
módulos disponibles y arranca el servidor con el transporte configurado.

Ciclo de vida: el apagado (SIGINT/SIGTERM/atexit) invoca ``shutdown()``,
que ejecuta el ``teardown()`` de cada módulo en orden inverso.
"""

from __future__ import annotations

import atexit
import signal
import sys
import threading

from universal_mcp.core.config import Settings
from universal_mcp.core.logging import setup_logging
from universal_mcp.core.server import UniversalMCPServer


def main() -> int:
    settings = Settings()
    setup_logging(settings.log_level)
    settings.ensure_dirs()

    server = UniversalMCPServer(settings)
    server.load_modules()

    atexit.register(server.shutdown)

    def _on_terminate(signum: int, _frame: object) -> None:
        # SIGTERM/SIGHUP: apagado ordenado y salida limpia.
        server.shutdown()
        raise SystemExit(0)

    if threading.current_thread() is threading.main_thread():
        for sig_name in ("SIGTERM", "SIGHUP"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                signal.signal(sig, _on_terminate)

    try:
        server.run()
    except KeyboardInterrupt:
        server.shutdown()
        print("\n universal-mcp: apagado limpio.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
