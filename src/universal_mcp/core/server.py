"""``UniversalMCPServer``: fachada principal del proyecto.

Compone: Settings → FastMCP (SDK oficial) → ModuleRegistry → módulos.
Soporta ``stdio``, ``streamable-http`` y ``sse`` con el mismo núcleo.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from universal_mcp.core.config import Settings
from universal_mcp.core.registry import ModuleRegistry, RegistrationReport

logger = logging.getLogger("mcp.server")

INSTRUCTIONS = """Universal MCP: ecosistema modular de herramientas de IA, datos,
automatización y análisis. Las tools van prefijadas por módulo:

- system_*     → información y utilidades del host (tiempo, disco, entorno).
- files_*      → operaciones de archivos dentro de un sandbox (workspace).
- data_*       → lectura CSV/JSON, aplanado de JSON y consultas SQLite (solo lectura).
- analysis_*   → estadística, evaluación matemática segura y regresión lineal.
- ai_*         → análisis de texto local: resumen, sentimiento, keywords, extracción.
- automation_* → peticiones HTTP, webhooks y utilidades (uuid, timestamp).

Prefiere la tool más específica y revisa los parámetros con el schema de cada tool.
"""


class UniversalMCPServer:
    """Servidor MCP con núcleo modular y soporte de múltiples transportes."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.mcp = FastMCP(
            self.settings.server_name,
            instructions=INSTRUCTIONS,
            host=self.settings.host,
            port=self.settings.port,
        )
        self.registry = ModuleRegistry(self.settings)
        self.report: RegistrationReport | None = None
        self._tool_names: set[str] = set()

    # ------------------------------------------------------------------
    def load_modules(self) -> RegistrationReport:
        """Descubre e instala todos los módulos disponibles."""
        self.registry.discover()
        self.report = self.registry.register_all(self.mcp, self._tool_names)

        loaded = ", ".join(
            f"{m.instance.name}({m.source})" for m in self.report.loaded
        )
        logger.info("Módulos cargados (%d): %s", len(self.report.loaded), loaded or "—")
        for skipped in self.report.skipped:
            logger.warning(
                "Módulo omitido: %s [%s] — %s",
                skipped.name,
                skipped.source,
                skipped.reason,
            )
        logger.info("Tools registradas en total: %d", len(self._tool_names))
        return self.report

    # ------------------------------------------------------------------
    @property
    def tool_names(self) -> set[str]:
        """Nombres finales de las tools registradas (con prefijo)."""
        return set(self._tool_names)

    def run(self) -> None:
        """Arranca el servidor con el transporte configurado (bloquea)."""
        logger.info(
            "Iniciando universal-mcp | transporte=%s host=%s puerto=%s",
            self.settings.transport,
            self.settings.host,
            self.settings.port,
        )
        self.mcp.run(transport=self.settings.transport)
