"""Módulo ``system`` — información y utilidades del host.

Tools: system_info, system_now, system_disk_usage, system_env_vars,
system_run_command (deshabilitada por defecto; requiere MCP_ENABLE_SHELL=true).
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext
from universal_mcp.core.utils import clamp, to_json

_MASK_SUBSTRINGS = ("KEY", "TOKEN", "SECRET", "PASS", "CREDENTIAL", "API")


# ----------------------------------------------------------------------
# Implementaciones puras (testeables sin servidor)
# ----------------------------------------------------------------------
def info_impl() -> dict[str, Any]:
    uname = platform.uname()
    return {
        "system": uname.system,
        "node": uname.node,
        "release": uname.release,
        "machine": uname.machine,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "cpu_count": os.cpu_count(),
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "cwd": os.getcwd(),
    }


def now_impl(tz_name: str = "UTC") -> dict[str, Any]:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        return {
            "error": f"Zona horaria desconocida: {tz_name!r}",
            "fallback": datetime.now(timezone.utc).isoformat(),
        }
    current = datetime.now(tz)
    return {
        "iso": current.isoformat(),
        "timezone": str(tz),
        "utc_offset": str(current.utcoffset()),
        "epoch": current.timestamp(),
    }


def disk_usage_impl(path: str = ".") -> dict[str, Any]:
    usage = shutil.disk_usage(path)
    return {
        "path": str(Path(path).resolve()),
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "percent_used": round(usage.used / usage.total * 100, 1) if usage.total else None,
    }


def env_vars_impl(prefix: str = "") -> dict[str, Any]:
    variables: dict[str, str] = {}
    for key in sorted(os.environ):
        if prefix and not key.startswith(prefix):
            continue
        if any(marker in key.upper() for marker in _MASK_SUBSTRINGS):
            variables[key] = "***"
        else:
            variables[key] = os.environ[key]
    return {
        "count": len(variables),
        "variables": variables,
        "note": "Los valores de claves que contienen KEY/TOKEN/SECRET/PASS/CREDENTIAL/API se ocultan.",
    }


def run_command_impl(command: str, timeout: int = 10) -> dict[str, Any]:
    proc = subprocess.run(  # noqa: S602 — protegido por MCP_ENABLE_SHELL
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=clamp(timeout, 1, 120),
    )
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


# ----------------------------------------------------------------------
# Registro de tools
# ----------------------------------------------------------------------
class SystemModule(BaseModule):
    name = "system"
    description = "Información y utilidades del sistema host."

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(
            name="info",
            description="Get host system information: OS, python, CPUs, hostname, cwd.",
        )
        def info() -> str:
            return to_json(info_impl())

        @ctx.tool(
            name="now",
            description="Current date/time in a given IANA timezone (e.g. 'America/Bogota', 'UTC').",
        )
        def now(tz: str = "UTC") -> str:
            return to_json(now_impl(tz))

        @ctx.tool(
            name="disk_usage",
            description="Disk usage statistics (total/used/free bytes and percent) for a path.",
        )
        def disk_usage(path: str = ".") -> str:
            return to_json(disk_usage_impl(path))

        @ctx.tool(
            name="env_vars",
            description="List environment variables (optionally by prefix). Secret-looking values are masked.",
        )
        def env_vars(prefix: str = "") -> str:
            return to_json(env_vars_impl(prefix))

        @ctx.tool(
            name="run_command",
            description=(
                "Execute a shell command on the host. DISABLED unless the server was started "
                "with MCP_ENABLE_SHELL=true. Use with extreme caution."
            ),
        )
        def run_command(command: str, timeout: int = 10) -> str:
            if not (self.settings and self.settings.enable_shell):
                return to_json(
                    {
                        "error": "La ejecución de comandos está deshabilitada "
                        "(arranca el servidor con MCP_ENABLE_SHELL=true para activarla).",
                        "enabled": False,
                    }
                )
            try:
                return to_json(run_command_impl(command, timeout))
            except subprocess.TimeoutExpired:
                return to_json({"error": f"El comando excedió {timeout}s"})
            except Exception as exc:  # noqa: BLE001 — respuesta controlada
                return to_json({"error": str(exc), "type": type(exc).__name__})
