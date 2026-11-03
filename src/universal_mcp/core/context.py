"""``ModuleContext``: la API que cada módulo recibe para registrarse.

Aplica automáticamente el prefijo ``<modulo>_<tool>`` a los nombres de
tools y prompts y detecta colisiones, de modo que módulos independientes
escritos por personas distintas nunca chocan entre sí.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from universal_mcp.core.exceptions import DuplicateToolError

if TYPE_CHECKING:
    from universal_mcp.core.base import BaseModule
    from universal_mcp.core.config import Settings


class ModuleContext:
    """Envoltura con fachada de registro para un módulo concreto."""

    def __init__(
        self,
        server: Any,
        module: BaseModule,
        settings: Settings,
        taken_names: set[str],
    ) -> None:
        self._server = server
        self._module = module
        self.settings = settings
        self._taken = taken_names

    # ------------------------------------------------------------------
    @property
    def module_name(self) -> str:
        return self._module.name

    @property
    def logger(self) -> logging.Logger:
        return self._module.logger

    # ------------------------------------------------------------------
    def _prefixed(self, name: str) -> str:
        final = f"{self._module.name}_{name}"
        if final in self._taken:
            raise DuplicateToolError(
                f"La tool '{final}' ya fue registrada (conflicto con otro módulo/registro)."
            )
        self._taken.add(final)
        return final

    def tool(
        self,
        name: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> Callable[..., Any]:
        """Decorador para registrar una **tool**.

        Usos equivalentes::

            @ctx.tool
            def ping() -> str: ...

            @ctx.tool(name="ping", description="...")
            def ping() -> str: ...
        """

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            final = self._prefixed(name or fn.__name__)
            return self._server.tool(name=final, description=description, **kwargs)(fn)

        if callable(name):  # uso sin paréntesis: @ctx.tool
            fn, name = name, None
            return decorate(fn)
        return decorate

    def prompt(
        self,
        name: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> Callable[..., Any]:
        """Decorador para registrar un **prompt** reutilizable."""

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            final = self._prefixed(name or fn.__name__)
            return self._server.prompt(name=final, description=description, **kwargs)(fn)

        if callable(name):
            fn, name = name, None
            return decorate(fn)
        return decorate

    def resource(
        self,
        uri: str,
        name: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> Callable[..., Any]:
        """Decorador para registrar un **resource** (el URI no se prefija:
        cada módulo define su propio esquema, p. ej. ``data://``)."""
        return self._server.resource(uri, name=name, description=description, **kwargs)
