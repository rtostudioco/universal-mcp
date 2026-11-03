"""Pruebas de configuración (Settings)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from universal_mcp.core.config import Settings, _parse_list


def test_defaults() -> None:
    config = Settings()
    assert config.transport == "stdio"
    assert config.server_name == "universal-mcp"
    assert config.enable_shell is False
    assert config.http_block_private is True
    assert config.disabled_modules == []
    assert config.plugin_dirs == []
    assert config.port == 8000


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("MCP_PORT", "9000")
    monkeypatch.setenv("MCP_SERVER_NAME", "otro-servidor")
    config = Settings()
    assert config.transport == "streamable-http"
    assert config.port == 9000
    assert config.server_name == "otro-servidor"


def test_invalid_transport_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_TRANSPORT", "websocket")
    with pytest.raises(ValidationError):
        Settings()


def test_parse_list_variants() -> None:
    assert _parse_list("a,b ,c") == ["a", "b", "c"]
    assert _parse_list("") == []
    assert _parse_list(None) == []
    assert _parse_list('["x", "y"]') == ["x", "y"]
    assert _parse_list(["ya-lista"]) == ["ya-lista"]


def test_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_DISABLED_MODULES", "system, ai")
    assert Settings().disabled_modules == ["system", "ai"]


def test_json_env_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_PLUGIN_DIRS", '["/tmp/a", "/tmp/b"]')
    assert Settings().plugin_dirs == [Path("/tmp/a"), Path("/tmp/b")]


def test_ensure_dirs_creates_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "nuevo" / "workspace"
    config = Settings(workspace_dir=workspace)
    config.ensure_dirs()
    assert workspace.is_dir()
    assert config.workspace_dir.is_absolute()
