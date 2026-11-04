"""``ModuleContext``: la API que cada módulo recibe para registrarse.

Aplica automáticamente el prefijo ``<modulo>_<tool>`` a los nombres de
tools y prompts y detecta colisiones, de modo que módulos independientes
escritos por personas distintas nunca chocan entre sí.

Además aplica la **política de permisos por herramienta** definida en
``Settings`` (``MCP_ALLOWED_TOOLS`` / ``MCP_BLOCKED_TOOLS``):

- Una tool no permitida **no se registra** (y se reporta en
  ``RegistrationReport.blocked_tools``): el resto del módulo sigue vivo.
- Las tools registradas llevan un *guard* en runtime: si la política
  cambia en caliente o la tool se invoca por una vía alternativa, la
  llamada falla con :class:`SecurityViolationError`.
"""

from __future__ import annotations

import fnmatch
import functools
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from universal_mcp.core.exceptions import DuplicateToolError, SecurityViolationError

if TYPE_CHECKING:
    from universal_mcp.core.base import BaseModule
    from universal_mcp.core.config import Settings


@dataclass
class BlockedTool:
    """Tool rechazada por la política de permisos."""

    name: str
    source: str
    reason: str = "blocked by tool policy"


def tool_matches_policy(name: str, allowed: list[str], blocked: list[str]) -> bool:
    """Decide si ``name`` pasa la política (globs, ``blocked`` gana).

    - Si coincide con algún patrón de ``blocked`` → False.
    - Si ``allowed`` está vacío → True (sin allowlist).
    - En otro caso, debe coincidir con algún patrón de ``allowed``.
    """
    for pattern in blocked:
        if pattern and fnmatch.fnmatchcase(name, pattern):
            return False
    if not allowed:
        return True
    return any(pattern and fnmatch.fnmatchcase(name, pattern) for pattern in allowed)


class ModuleContext:
    """Envoltura con fachada de registro para un módulo concreto."""

    def __init__(
        self,
        server: Any,
        module: BaseModule,
        settings: Settings,
        taken_names: set[str],
        *,
        source: str = "builtin",
        blocked_sink: list[BlockedTool] | None = None,
    ) -> None:
        self._server = server
        self._module = module
        self.settings = settings
        self._taken = taken_names
        self._source = source
        self.blocked_tools: list[BlockedTool] = blocked_sink if blocked_sink is not None else []
        self._blocked_set: set[str] = set()

    # ------------------------------------------------------------------
    @property
    def module_name(self) -> str:
        return self._module.name

    @property
    def logger(self) -> logging.Logger:
        return self._module.logger

    # ------------------------------------------------------------------
    def _permitted(self, final: str) -> bool:
        settings = self.settings
        allowed = list(getattr(settings, "allowed_tools", []) or [])
        blocked = list(getattr(settings, "blocked_tools", []) or [])
        return tool_matches_policy(final, allowed, blocked)

    def _skip_blocked(self, final: str) -> bool:
        """Devuelve True si ``final`` está bloqueada (y lo reporta una vez)."""
        if self._permitted(final):
            return False
        if final not in self._blocked_set:
            self._blocked_set.add(final)
            self.blocked_tools.append(BlockedTool(name=final, source=self._source))
            self.logger.warning(
                "Tool '%s' bloqueada por la política de permisos "
                "(MCP_ALLOWED_TOOLS/MCP_BLOCKED_TOOLS): no se registra.",
                final,
            )
        return True

    def _runtime_guard(self, final: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Envuelve ``fn`` re-verificando la política en cada invocación.

        Conserva la firma tipada (``__signature__`` explícito) para que la
        generación de esquemas de FastMCP no cambie.
        """

        @functools.wraps(fn)
        def guarded(*args: Any, **kwargs: Any) -> Any:
            if not self._permitted(final):
                raise SecurityViolationError(
                    f"Tool '{final}' bloqueada por la política de permisos "
                    "(MCP_ALLOWED_TOOLS/MCP_BLOCKED_TOOLS)."
                )
            return fn(*args, **kwargs)

        guarded.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
        return guarded

    def _prefixed(self, name: str) -> str:
        final = f"{self._module.name}_{name}"
        if final in self._taken:
            raise DuplicateToolError(
                f"La tool '{final}' ya fue registrada (conflicto con otro módulo/registro)."
            )
        self._taken.add(final)
        return final

    # ------------------------------------------------------------------
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

        Si la política de permisos bloquea la tool, se devuelve la función
        sin registrarla (el módulo sigue cargando el resto de sus tools).
        """

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            final = f"{self._module.name}_{name or fn.__name__}"
            if self._skip_blocked(final):
                return fn
            final_name = self._prefixed(name or fn.__name__)
            return self._server.tool(name=final_name, description=description, **kwargs)(
                self._runtime_guard(final_name, fn)
            )

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
        """Decorador para registrar un **prompt** reutilizable.

        Los prompts también respetan la política (a nivel de registro).
        """

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            final = f"{self._module.name}_{name or fn.__name__}"
            if self._skip_blocked(final):
                return fn
            final_name = self._prefixed(name or fn.__name__)
            return self._server.prompt(name=final_name, description=description, **kwargs)(fn)

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
        cada módulo define su propio esquema, p. ej. ``data://``).

        Los resources son de solo lectura por diseño; la política de
        permisos se aplica a tools y prompts.
        """
        return self._server.resource(uri, name=name, description=description, **kwargs)
