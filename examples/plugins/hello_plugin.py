"""Plugin externo de ejemplo para Universal MCP.

Demuestra que se pueden añadir módulos **sin tocar el código del servidor**:

    MCP_PLUGIN_DIRS=examples/plugins .venv/bin/python -m universal_mcp

Tras arrancar, el cliente MCP verá la tool ``hello_plugin_ping``.
"""

from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext
from universal_mcp.core.utils import to_json


class HelloPlugin(BaseModule):
    name = "hello_plugin"
    description = "Plugin de ejemplo cargado desde un directorio externo."
    version = "1.0.0"

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(name="ping", description="Responde 'pong' desde el plugin externo.")
        def ping() -> str:
            return to_json({"reply": "pong", "module": self.name, "version": self.version})

        @ctx.tool(name="echo", description="Devuelve el mensaje recibido (plugin externo).")
        def echo(message: str) -> str:
            return to_json({"echo": message})
