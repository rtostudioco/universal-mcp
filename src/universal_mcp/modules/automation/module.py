"""Módulo ``automation`` — HTTP, webhooks y utilidades.

Seguridad anti-SSRF:
- Solo esquemas http/https.
- Con ``MCP_HTTP_BLOCK_PRIVATE=true`` (por defecto) se resuelve el host y se
  bloquean IPs privadas, loopback, link-local, reservadas y multicast.
- Timeouts acotados y cuerpos de respuesta truncados.
"""

from __future__ import annotations

import ipaddress
import socket
import time
import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext
from universal_mcp.core.exceptions import MCPError, SecurityViolationError, ToolExecutionError
from universal_mcp.core.utils import clamp, to_json

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_MAX_WAIT_SECONDS = 60.0


# ----------------------------------------------------------------------
# Seguridad y utilidades puras
# ----------------------------------------------------------------------
def assert_public_host(url: str, block_private: bool) -> None:
    """Valida esquema y, si aplica, que el host no apunte a redes privadas."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SecurityViolationError("Solo se permiten URLs http/https.")
    host = parsed.hostname
    if not host:
        raise SecurityViolationError("La URL no tiene hostname.")
    if not block_private:
        return

    candidates: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    try:
        candidates.append(ipaddress.ip_address(host))
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except OSError as exc:
            raise SecurityViolationError(f"No se pudo resolver el host {host!r}: {exc}") from exc
        for info in infos:
            try:
                candidates.append(ipaddress.ip_address(info[4][0]))
            except ValueError:  # pragma: no cover
                continue

    for ip in candidates:
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or getattr(ip, "is_unspecified", False)
        ):
            raise SecurityViolationError(
                f"Dirección privada/reservada bloqueada (anti-SSRF): {ip}"
            )


# ----------------------------------------------------------------------
# Registro de tools
# ----------------------------------------------------------------------
class AutomationModule(BaseModule):
    name = "automation"
    description = "Peticiones HTTP seguras, webhooks y utilidades de automatización."

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(
            name="http_request",
            description=(
                "Perform an HTTP request (GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS). "
                "Private/internal hosts are blocked by default (anti-SSRF). Body is truncated."
            ),
        )
        def http_request(
            url: str,
            method: str = "GET",
            headers: dict[str, str] | None = None,
            body: str | None = None,
            json_body: dict[str, Any] | None = None,
            timeout: float | None = None,
        ) -> str:
            try:
                settings = self.settings
                assert_public_host(url, settings.http_block_private if settings else True)
                method_upper = method.upper()
                if method_upper not in _ALLOWED_METHODS:
                    raise ToolExecutionError(f"Método no soportado: {method_upper}")
                default_timeout = settings.http_timeout if settings else 15.0
                resolved_timeout = clamp(timeout if timeout is not None else default_timeout, 0.1, 60.0)
                with httpx.Client(follow_redirects=True, timeout=resolved_timeout) as client:
                    response = client.request(
                        method_upper,
                        url,
                        headers=dict(headers or {}),
                        content=body if json_body is None else None,
                        json=json_body,
                    )
                max_chars = settings.max_output_chars if settings else 20_000
                response_text = response.text
                return to_json(
                    {
                        "url": str(response.url),
                        "status": response.status_code,
                        "ok": response.is_success,
                        "elapsed_ms": int(response.elapsed.total_seconds() * 1000),
                        "content_type": response.headers.get("content-type"),
                        "body": response_text[:max_chars],
                        "body_truncated": len(response_text) > max_chars,
                    }
                )
            except MCPError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})
            except httpx.HTTPError as exc:
                return to_json({"error": f"HTTP request failed: {exc}", "type": "HTTPError"})

        @ctx.tool(
            name="send_webhook",
            description="POST a JSON payload to a webhook URL (adds X-Webhook-Secret header if provided).",
        )
        def send_webhook(url: str, payload: dict[str, Any], secret: str | None = None) -> str:
            try:
                settings = self.settings
                assert_public_host(url, settings.http_block_private if settings else True)
                webhook_headers = {"X-Webhook-Secret": secret} if secret else {}
                with httpx.Client(
                    follow_redirects=True,
                    timeout=settings.http_timeout if settings else 15.0,
                ) as client:
                    response = client.post(url, json=payload, headers=webhook_headers)
                return to_json(
                    {
                        "url": str(response.url),
                        "status": response.status_code,
                        "ok": response.is_success,
                        "response": response.text[:1000],
                    }
                )
            except MCPError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})
            except httpx.HTTPError as exc:
                return to_json({"error": f"HTTP request failed: {exc}", "type": "HTTPError"})

        @ctx.tool(name="uuid4", description="Generate a random UUID v4 string.")
        def uuid4() -> str:
            return to_json({"uuid": str(uuid_lib.uuid4())})

        @ctx.tool(name="timestamp", description="Current time: unix epoch and ISO-8601 UTC.")
        def timestamp() -> str:
            return to_json(
                {
                    "epoch": time.time(),
                    "iso_utc": datetime.now(timezone.utc).isoformat(),
                }
            )

        @ctx.tool(
            name="wait",
            description="Sleep for N seconds (0.01–60). Useful for polling and retries.",
        )
        def wait(seconds: float = 1.0) -> str:
            waited = clamp(seconds, 0.01, _MAX_WAIT_SECONDS)
            time.sleep(waited)
            return to_json({"waited_seconds": waited})
