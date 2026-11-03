"""Pruebas del ModuleRegistry: descubrimiento builtin, plugins y aislamiento."""

from __future__ import annotations

from universal_mcp.core.config import Settings
from universal_mcp.core.registry import ModuleRegistry

PLUGIN_SOURCE = '''
from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext
from universal_mcp.core.utils import to_json


class HelloPlugin(BaseModule):
    name = "hello_plugin"
    description = "Plugin de ejemplo cargado desde un directorio externo."
    version = "1.0.0"

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(name="ping", description="Responde 'pong' desde el plugin.")
        def ping() -> str:
            return to_json({"reply": "pong"})
'''

BROKEN_SOURCE = "esto no es python válido (((("


def _builtin_names(registry: ModuleRegistry) -> set[str]:
    registry.discover()
    return {cls.name for cls, _source in registry._candidates}


def test_builtin_discovery_finds_six_modules(settings: Settings) -> None:
    assert {"system", "files", "data", "analysis", "ai", "automation"} <= _builtin_names(
        ModuleRegistry(settings)
    )


def test_plugin_dir_missing_is_reported(settings: Settings) -> None:
    registry = ModuleRegistry(settings)
    registry.settings.plugin_dirs = ["/ruta/inexistente"]
    registry.discover()
    assert any(s.reason == "plugin dir not found" for s in registry._discovery_skipped)


async def test_disabled_modules_are_skipped(settings: Settings) -> None:
    from universal_mcp.core.server import UniversalMCPServer

    settings.disabled_modules = ["system"]
    srv = UniversalMCPServer(settings)
    report = srv.load_modules()

    loaded = {m.instance.name for m in report.loaded}
    assert "system" not in loaded
    assert any(s.name == "system" and s.reason == "disabled by config" for s in report.skipped)
    assert not any(name.startswith("system_") for name in srv.tool_names)


async def test_external_plugin_is_loaded(settings: Settings, tmp_path) -> None:
    from universal_mcp.core.server import UniversalMCPServer

    (tmp_path / "hello_plugin.py").write_text(PLUGIN_SOURCE, encoding="utf-8")
    settings.plugin_dirs = [tmp_path]

    srv = UniversalMCPServer(settings)
    report = srv.load_modules()

    assert "hello_plugin" in {m.instance.name for m in report.loaded}
    assert "hello_plugin_ping" in srv.tool_names


async def test_broken_plugin_does_not_break_server(settings: Settings, tmp_path) -> None:
    from universal_mcp.core.server import UniversalMCPServer

    (tmp_path / "broken.py").write_text(BROKEN_SOURCE, encoding="utf-8")
    settings.plugin_dirs = [tmp_path]

    srv = UniversalMCPServer(settings)
    report = srv.load_modules()

    assert any(
        s.source == "plugin:broken.py" and s.reason.startswith("import failed")
        for s in report.skipped
    )
    assert len(report.loaded) >= 6  # los builtin siguen vivos


async def test_duplicate_module_names_first_wins(settings: Settings, tmp_path) -> None:
    from universal_mcp.core.server import UniversalMCPServer

    (tmp_path / "one.py").write_text(PLUGIN_SOURCE, encoding="utf-8")
    (tmp_path / "two.py").write_text(
        PLUGIN_SOURCE.replace("HelloPlugin", "HelloPluginTwo"), encoding="utf-8"
    )
    settings.plugin_dirs = [tmp_path]

    srv = UniversalMCPServer(settings)
    report = srv.load_modules()

    assert len([m for m in report.loaded if m.instance.name == "hello_plugin"]) == 1
    assert any(
        s.name == "hello_plugin" and s.reason == "duplicate module name" for s in report.skipped
    )
