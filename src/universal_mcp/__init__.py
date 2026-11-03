"""Universal MCP — ecosistema modular de herramientas de IA, datos, automatización y análisis.

El núcleo (`universal_mcp.core`) descubre y registra módulos automáticamente,
sin necesidad de tocar el servidor cuando el proyecto evoluciona.
"""

from __future__ import annotations

import importlib
from typing import Any

__version__ = "0.1.0"

_LAZY_EXPORTS: dict[str, str] = {
    "Settings": "universal_mcp.core.config",
    "UniversalMCPServer": "universal_mcp.core.server",
    "BaseModule": "universal_mcp.core.base",
    "ModuleRegistry": "universal_mcp.core.registry",
    "ModuleContext": "universal_mcp.core.context",
}

__all__ = [*(_LAZY_EXPORTS.keys()), "__version__"]


def __getattr__(name: str) -> Any:  # PEP 562 — lazy imports
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(target)
    return getattr(module, name)
