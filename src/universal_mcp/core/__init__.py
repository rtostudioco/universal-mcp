"""Núcleo modular de Universal MCP.

Componentes:
- ``config``: configuración por variables de entorno (pydantic-settings).
- ``base``:   contrato ``BaseModule`` que implementan todos los módulos.
- ``context``: ``ModuleContext``, API de registro con prefijado automático.
- ``registry``: descubrimiento e instanciación de módulos builtin y plugins.
- ``server``: ``UniversalMCPServer``, integración con FastMCP (SDK oficial).
- ``sandbox``: aislamiento de rutas dentro del workspace.
- ``exceptions``: jerarquía de errores del dominio.
"""
