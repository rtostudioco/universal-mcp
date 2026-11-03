"""Jerarquía de excepciones del proyecto.

Todas las tools capturan ``MCPError`` y la convierten en una respuesta JSON
con ``{"error": ..., "type": ...}`` para que el cliente LLM pueda reaccionar
sin romper la sesión MCP.
"""

from __future__ import annotations


class MCPError(Exception):
    """Error base de Universal MCP."""


class ConfigError(MCPError):
    """Configuración inválida o incompleta."""


class ModuleLoadError(MCPError):
    """Un módulo no pudo cargarse o registrarse."""

    def __init__(self, module_name: str, reason: str) -> None:
        self.module_name = module_name
        self.reason = reason
        super().__init__(f"Module '{module_name}' failed to load: {reason}")


class DuplicateToolError(MCPError):
    """Dos módulos (o dos registros) intentan usar el mismo nombre de tool."""


class SecurityViolationError(MCPError):
    """Se intentó una operación prohibida por la política de seguridad
    (escapar del sandbox, acceso a IPs privadas, shell deshabilitado, etc.)."""


class ToolExecutionError(MCPError):
    """Error controlado durante la ejecución de una tool."""
