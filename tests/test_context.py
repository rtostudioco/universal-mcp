"""Pruebas del ModuleContext: prefijado automático y detección de colisiones."""

from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP

from universal_mcp.core.base import BaseModule
from universal_mcp.core.config import Settings
from universal_mcp.core.context import ModuleContext
from universal_mcp.core.exceptions import DuplicateToolError


class _DummyModule(BaseModule):
    name = "dummy"
    description = "módulo de prueba"

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(name="dup", description="primera")
        def first() -> str:
            return "1"

        @ctx.tool(name="dup", description="segunda")
        def second() -> str:
            return "2"


def test_duplicate_tool_names_are_rejected() -> None:
    mcp = FastMCP("test")
    module = _DummyModule(Settings())
    taken: set[str] = set()
    ctx = ModuleContext(mcp, module, module.settings, taken)

    with pytest.raises(DuplicateToolError):
        module.register(ctx)

    # la primera sí quedó registrada antes del choque
    assert "dummy_dup" in taken


def test_tool_names_are_prefixed() -> None:
    mcp = FastMCP("test")
    module = _DummyModule(Settings())
    taken: set[str] = set()
    ctx = ModuleContext(mcp, module, module.settings, taken)

    @ctx.tool(name="saludo", description="x")
    def saludo() -> str:
        return "hola"

    assert "dummy_saludo" in taken


def test_bare_decorator_usage() -> None:
    mcp = FastMCP("test")
    module = _DummyModule(Settings())
    ctx = ModuleContext(mcp, module, module.settings, set())

    @ctx.tool
    def ping() -> str:
        return "pong"

    assert "dummy_ping" in ctx._taken
