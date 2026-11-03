"""Contrato ``BaseModule``: la clase que todo módulo debe implementar.

Añadir un módulo nuevo = crear una clase que herede de ``BaseModule`` y
exponga ``name`` + ``register()``. El registry la descubre y registra sola:
**nunca hay que reescribir el servidor**.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:  # evita dependencias circulares en tiempo de ejecución
    from universal_mcp.core.config import Settings
    from universal_mcp.core.context import ModuleContext


class BaseModule(ABC):
    """Clase base para todos los módulos de Universal MCP.

    Atributos de clase:

    - ``name``:        identificador único (prefijo de las tools del módulo).
    - ``description``: descripción humana del módulo.
    - ``version``:     versión semántica del módulo.
    """

    name: ClassVar[str]
    description: ClassVar[str] = ""
    version: ClassVar[str] = "0.1.0"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings
        self.logger = logging.getLogger(f"mcp.modules.{self.name}")

    # ------------------------------------------------------------------
    @abstractmethod
    def register(self, ctx: ModuleContext) -> None:
        """Registra tools / resources / prompts usando ``ctx``.

        Ejemplo::

            def register(self, ctx: ModuleContext) -> None:
                @ctx.tool(name="ping", description="Responde 'pong'.")
                def ping() -> str:
                    return "pong"
        """

    # Hooks opcionales del ciclo de vida ---------------------------------
    def setup(self) -> None:  # noqa: B027 — hook opcional por diseño
        """Se ejecuta tras instanciar el módulo, antes de ``register``."""

    def teardown(self) -> None:  # noqa: B027 — hook opcional por diseño
        """Se ejecuta al apagar el servidor (liberar recursos, etc.)."""
