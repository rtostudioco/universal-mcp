"""Fixtures y helpers compartidos por la suite de pruebas."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from universal_mcp.core.config import Settings


@pytest.fixture(autouse=True)
def _clean_mcp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla los tests de variables MCP_* presentes en el entorno del host."""
    for key in [k for k in os.environ if k.startswith("MCP_")]:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def settings(tmp_path) -> Settings:
    """Settings herméticas: workspace efímero, sin plugins ni módulos desactivados."""
    config = Settings(
        workspace_dir=tmp_path / "workspace",
        plugin_dirs=[],
        disabled_modules=[],
        enable_shell=False,
    )
    config.ensure_dirs()
    return config


@pytest.fixture()
async def server(settings: Settings):
    """Servidor Universal MCP con todos los módulos builtin cargados."""
    from universal_mcp.core.server import UniversalMCPServer

    srv = UniversalMCPServer(settings)
    srv.load_modules()
    return srv


async def call_tool_result(server, name: str, arguments: dict[str, Any] | None = None) -> str:
    """Ejecuta una tool a través del protocolo MCP y devuelve el texto.

    Normaliza las distintas formas de retorno del SDK (lista de bloques,
    tupla o CallToolResult).
    """
    result = await server.mcp.call_tool(name, arguments or {})
    if isinstance(result, tuple):
        result = result[0]
    if hasattr(result, "content"):
        content = result.content
    else:
        content = result
    return "\n".join(getattr(block, "text", "") for block in content)


async def call_json(server, name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Ejecuta una tool y parsea su respuesta JSON."""
    return json.loads(await call_tool_result(server, name, arguments))
