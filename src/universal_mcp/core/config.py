"""Configuración central por variables de entorno (prefijo ``MCP_``).

Acepta listas como JSON (``["a","b"]``) o separadas por comas (``a,b``),
para que el uso desde Claude Desktop (JSON) y desde shell (comas) sea cómodo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _parse_list(value: Any) -> list[Any]:
    """Convierte un valor de entorno en lista: acepta JSON o 'a,b,c'."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            pass
    return [item.strip() for item in text.split(",") if item.strip()]


class Settings(BaseSettings):
    """Ajustes globales del servidor Universal MCP."""

    model_config = SettingsConfigDict(
        env_prefix="MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Identidad y transporte -------------------------------------------
    server_name: str = "universal-mcp"
    transport: Literal["stdio", "streamable-http", "sse"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000

    # --- Observabilidad ----------------------------------------------------
    log_level: str = "INFO"

    # --- Carga de módulos --------------------------------------------------
    # NoDecode: acepta JSON (["a","b"]) Y listas por comas ("a,b") del entorno.
    disabled_modules: Annotated[list[str], NoDecode] = Field(default_factory=list)
    plugin_dirs: Annotated[list[Path], NoDecode] = Field(default_factory=list)

    # --- Sandbox y seguridad ------------------------------------------------
    workspace_dir: Path = Path("./workspace")
    enable_shell: bool = False
    http_block_private: bool = True
    http_timeout: float = 15.0
    max_output_chars: int = 20_000

    @field_validator("disabled_modules", "plugin_dirs", mode="before")
    @classmethod
    def _coerce_lists(cls, value: Any) -> list[Any]:
        return _parse_list(value)

    def ensure_dirs(self) -> None:
        """Crea el workspace si no existe y fija su ruta absoluta."""
        self.workspace_dir = Path(self.workspace_dir).expanduser().resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
