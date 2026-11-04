"""Pruebas de seguridad y fiabilidad (v0.2):

- Anti-SSRF por hop: cada destino de redirección se re-valida.
- Rollback de registro parcial (un módulo que falla a medias no deja tools).
- Ciclo de vida: ``shutdown()`` ejecuta ``teardown()`` en orden inverso.
- Permisos por herramienta (``MCP_ALLOWED_TOOLS`` / ``MCP_BLOCKED_TOOLS``).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from universal_mcp.core.config import Settings
from universal_mcp.core.context import tool_matches_policy
from universal_mcp.core.exceptions import SecurityViolationError, ToolExecutionError
from universal_mcp.modules.automation import module as automation_module

# IP literal pública: evita DNS en los tests (1.1.1.1 es anycast público).
PUBLIC = "http://1.1.1.1"


def _client_factory(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[..., httpx.Client]:
    def factory(**kwargs: Any) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

    return factory


# ----------------------------------------------------------------------
# assert_public_host (validación de URL)
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "gopher://example.com",
        "http://",  # sin hostname
    ],
)
def test_assert_public_host_blocks_bad_schemes(url: str) -> None:
    with pytest.raises(SecurityViolationError):
        automation_module.assert_public_host(url, block_private=True)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9/x",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.0.9/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://224.0.0.1/",
    ],
)
def test_assert_public_host_blocks_private_literals(url: str) -> None:
    with pytest.raises(SecurityViolationError, match="SSRF"):
        automation_module.assert_public_host(url, block_private=True)


@pytest.mark.parametrize("url", ["http://1.1.1.1/", "http://8.8.8.8:53/dns-query"])
def test_assert_public_host_allows_public_literals(url: str) -> None:
    automation_module.assert_public_host(url, block_private=True)  # no debe lanzar


# ----------------------------------------------------------------------
# request_with_redirect_guard (anti-SSRF por hop)
# ----------------------------------------------------------------------
def test_redirect_to_private_is_blocked() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1:9/secret"})

    with pytest.raises(SecurityViolationError, match="SSRF"):
        automation_module.request_with_redirect_guard(
            f"{PUBLIC}/start", client_factory=_client_factory(handler)
        )
    # El hop privado nunca llegó a solicitarse.
    assert requested == [f"{PUBLIC}/start"]


def test_redirect_chain_relative_location_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a":
            return httpx.Response(302, headers={"Location": "b"})  # relativa
        return httpx.Response(200, text="final")

    response = automation_module.request_with_redirect_guard(
        f"{PUBLIC}/a", client_factory=_client_factory(handler)
    )
    assert response.status_code == 200
    assert response.text == "final"


def test_too_many_redirects_raise() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": f"{PUBLIC}/loop"})

    with pytest.raises(ToolExecutionError, match="redirecciones"):
        automation_module.request_with_redirect_guard(
            f"{PUBLIC}/loop",
            max_redirects=3,
            client_factory=_client_factory(handler),
        )


def test_303_downgrades_post_to_get_and_drops_body() -> None:
    seen: list[tuple[str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.content))
        if request.url.path == "/start":
            return httpx.Response(303, headers={"Location": "/done"})
        return httpx.Response(200, text="ok")

    response = automation_module.request_with_redirect_guard(
        f"{PUBLIC}/start",
        method="POST",
        content='{"a":1}',
        client_factory=_client_factory(handler),
    )
    assert response.status_code == 200
    assert seen == [("POST", b'{"a":1}'), ("GET", b"")]


def test_307_preserves_method_and_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(307, headers={"Location": "/echo"})
        return httpx.Response(200, json={"method": request.method, "body": request.content.decode()})

    response = automation_module.request_with_redirect_guard(
        f"{PUBLIC}/start",
        method="POST",
        content="payload-1",
        client_factory=_client_factory(handler),
    )
    assert response.status_code == 200
    assert response.json() == {"method": "POST", "body": "payload-1"}


def test_redirect_to_non_http_scheme_blocked() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "file:///etc/passwd"})

    with pytest.raises(SecurityViolationError):
        automation_module.request_with_redirect_guard(
            f"{PUBLIC}/start", client_factory=_client_factory(handler)
        )


def test_redirect_without_location_is_returned() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302)

    response = automation_module.request_with_redirect_guard(
        f"{PUBLIC}/start", client_factory=_client_factory(handler)
    )
    assert response.status_code == 302


# ----------------------------------------------------------------------
# Política de permisos (pura)
# ----------------------------------------------------------------------
def test_tool_matches_policy_semantics() -> None:
    assert tool_matches_policy("files_read_file", [], []) is True  # sin allowlist
    assert tool_matches_policy("files_read_file", ["data_*"], []) is False
    assert tool_matches_policy("data_read_csv", ["data_*"], []) is True
    assert tool_matches_policy("system_run_command", ["system_*"], ["system_run*"]) is False
    assert tool_matches_policy("system_info", ["system_*"], ["system_run*"]) is True
    assert tool_matches_policy("system_info", [], ["system_*"]) is False  # blocked gana


# ----------------------------------------------------------------------
# Permisos por herramienta (servidor completo)
# ----------------------------------------------------------------------
async def test_blocked_tools_glob_are_not_registered(settings: Settings) -> None:
    from universal_mcp.core.server import UniversalMCPServer

    settings.blocked_tools = ["files_*", "system_run_command"]
    srv = UniversalMCPServer(settings)
    report = srv.load_modules()

    names = srv.tool_names
    assert not any(name.startswith("files_") for name in names)
    assert "system_run_command" not in names
    assert "system_info" in names and "data_read_csv" in names  # el resto sigue vivo
    blocked = {t.name for t in report.blocked_tools}
    assert "system_run_command" in blocked
    assert any(name.startswith("files_") for name in blocked)


async def test_allowed_tools_allowlist(settings: Settings) -> None:
    from universal_mcp.core.server import UniversalMCPServer

    settings.allowed_tools = ["data_*"]
    srv = UniversalMCPServer(settings)
    srv.load_modules()

    names = srv.tool_names
    assert names == {
        "data_read_csv",
        "data_read_json",
        "data_flatten_json",
        "data_sqlite_query",
        "data_to_json",
    }


async def test_blocked_beats_allowed(settings: Settings) -> None:
    from universal_mcp.core.server import UniversalMCPServer

    settings.allowed_tools = ["system_*"]
    settings.blocked_tools = ["system_run_command"]
    srv = UniversalMCPServer(settings)
    srv.load_modules()

    names = srv.tool_names
    assert "system_run_command" not in names
    assert "system_info" in names


async def test_runtime_guard_blocks_blocked_tool(server) -> None:
    """El guard en runtime falla aunque la tool siga registrada."""
    server.settings.blocked_tools.append("system_info")
    registered = server.mcp._tool_manager._tools["system_info"].fn
    with pytest.raises(SecurityViolationError, match="política de permisos"):
        registered()


async def test_blocked_tool_inside_plugin_is_reported(settings: Settings, tmp_path) -> None:
    from universal_mcp.core.server import UniversalMCPServer

    (tmp_path / "pluginx.py").write_text(
        "from universal_mcp.core.base import BaseModule\n"
        "from universal_mcp.core.context import ModuleContext\n"
        "class PluginX(BaseModule):\n"
        "    name = 'pluginx'\n"
        "    def register(self, ctx: ModuleContext) -> None:\n"
        "        @ctx.tool(name='hi')\n"
        "        def hi() -> str:\n"
        "            return 'hola'\n",
        encoding="utf-8",
    )
    settings.plugin_dirs = [tmp_path]
    settings.blocked_tools = ["pluginx_hi"]
    srv = UniversalMCPServer(settings)
    report = srv.load_modules()

    assert "pluginx_hi" not in srv.tool_names
    assert "pluginx" in {m.instance.name for m in report.loaded}  # el módulo sigue vivo
    assert [t.name for t in report.blocked_tools] == ["pluginx_hi"]


# ----------------------------------------------------------------------
# Rollback de registro parcial
# ----------------------------------------------------------------------
PARTIAL_SOURCE = '''
from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext


class PartialModule(BaseModule):
    name = "partial"
    description = "Registra una tool y luego explota."

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(name="ok_tool", description="quedó a medias")
        def ok_tool() -> str:
            return "x"
        raise RuntimeError("boom después de registrar 1 tool")
'''


async def test_partial_registration_is_rolled_back(settings: Settings, tmp_path) -> None:
    from universal_mcp.core.server import UniversalMCPServer

    (tmp_path / "partial.py").write_text(PARTIAL_SOURCE, encoding="utf-8")
    settings.plugin_dirs = [tmp_path]

    srv = UniversalMCPServer(settings)
    report = srv.load_modules()

    skipped = [s for s in report.skipped if s.name == "partial"]
    assert skipped and "registration failed" in skipped[0].reason
    assert "rolled back" in skipped[0].reason

    # La tool a medias NO queda viva (ni en el server ni en tool_names).
    assert "partial_ok_tool" not in srv.tool_names
    tools = await srv.mcp.list_tools()
    assert "partial_ok_tool" not in {t.name for t in tools}
    # Los builtin siguen intactos.
    assert "system_info" in srv.tool_names


# ----------------------------------------------------------------------
# Ciclo de vida (shutdown → teardown inverso)
# ----------------------------------------------------------------------
LIFECYCLE_SOURCE = '''
from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext

STATE = {"order": []}


class LCOne(BaseModule):
    name = "lc_one"

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(name="noop")
        def noop() -> str:
            return "ok"

    def teardown(self) -> None:
        STATE["order"].append("lc_one")


class LCTwo(BaseModule):
    name = "lc_two"

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(name="noop")
        def noop() -> str:
            return "ok"

    def teardown(self) -> None:
        STATE["order"].append("lc_two")
        raise RuntimeError("teardown explotó a propósito")


class LCThree(BaseModule):
    name = "lc_three"

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(name="noop")
        def noop() -> str:
            return "ok"

    def teardown(self) -> None:
        STATE["order"].append("lc_three")
'''


async def test_shutdown_calls_teardown_in_reverse_and_tolerates_failures(
    settings: Settings, tmp_path
) -> None:
    from universal_mcp.core.server import UniversalMCPServer

    (tmp_path / "lifecycle.py").write_text(LIFECYCLE_SOURCE, encoding="utf-8")
    settings.plugin_dirs = [tmp_path]

    srv = UniversalMCPServer(settings)
    srv.load_modules()
    assert "lc_two_noop" in srv.tool_names  # preload: registrado

    srv.shutdown()  # no debe lanzar pese al teardown roto de lc_two

    # Recupera el estado compartido del plugin (mismo módulo en sys.modules).
    plugin_module = next(
        (
            mod
            for mod in sys.modules.values()
            if getattr(mod, "__name__", "").startswith("mcp_plugin_") and hasattr(mod, "STATE")
        ),
        None,
    )
    assert plugin_module is not None
    order = plugin_module.STATE["order"]

    assert order == ["lc_three", "lc_two", "lc_one"]  # inverso; fallo no corta

    srv.shutdown()  # idempotente
    assert plugin_module.STATE["order"] == ["lc_three", "lc_two", "lc_one"]
