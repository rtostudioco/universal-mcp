"""Módulo ``automation`` — HTTP, webhooks y utilidades.

Seguridad anti-SSRF:
- Solo esquemas http/https.
- Con ``MCP_HTTP_BLOCK_PRIVATE=true`` (por defecto) se resuelve el host y se
  bloquean IPs privadas, loopback, link-local, reservadas y multicast.
- **Cada hop de redirección se re-valida**: ``follow_redirects=False`` y un
  bucle manual comprueba el destino de cada salto (incluye Location
  relativas), evitando el bypass clásico 302 → 169.254.169.254.
- Timeouts acotados y cuerpos de respuesta truncados.
"""

from __future__ import annotations

import ipaddress
import socket
import time
import uuid as uuid_lib
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext
from universal_mcp.core.exceptions import MCPError, SecurityViolationError, ToolExecutionError
from universal_mcp.core.utils import clamp, to_json

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_MAX_WAIT_SECONDS = 60.0
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 5


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


def _downgraded_method(method: str, status: int) -> str:
    """Método efectivo tras una redirección (301/302/303 degradan a GET)."""
    if status in (301, 302, 303) and method not in ("GET", "HEAD"):
        return "GET"
    return method


def request_with_redirect_guard(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    content: str | None = None,
    json_body: dict[str, Any] | None = None,
    block_private: bool = True,
    timeout: float = 15.0,
    max_redirects: int = _MAX_REDIRECTS,
    client_factory: Callable[..., httpx.Client] = httpx.Client,
) -> httpx.Response:
    """HTTP con guard anti-SSRF en **cada** hop de redirección.

    - Valida el destino con :func:`assert_public_host` antes de cada
      petición (URL original y todos los ``Location`` intermedios,
      absolutos o relativos).
    - ``follow_redirects=False``: httpx nunca sigue saltos por su cuenta.
    - 301/302/303 degradan a GET y sueltan el cuerpo; 307/308 conservan
      método y cuerpo.
    - ``client_factory`` existe para tests (transporte simulado).
    """
    current_url = url
    current_method = method.upper()
    current_content = content
    current_json = json_body
    hops = 0

    while True:
        # Validación por hop: original y cada redirección (anti-SSRF).
        assert_public_host(current_url, block_private)
        with client_factory(follow_redirects=False, timeout=timeout) as client:
            response = client.request(
                current_method,
                current_url,
                headers=dict(headers or {}),
                content=current_content,
                json=current_json,
            )

        if response.status_code not in _REDIRECT_STATUSES:
            return response
        if hops >= max_redirects:
            raise ToolExecutionError(
                f"Demasiadas redirecciones (>{max_redirects}) solicitando {url!r}"
            )

        location = response.headers.get("location")
        if not location:
            return response  # 3xx sin Location: se devuelve tal cual
        current_url = urljoin(current_url, location)  # resuelve relativas
        current_method = _downgraded_method(current_method, response.status_code)
        if current_method == "GET":
            current_content, current_json = None, None
        hops += 1


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
                "Private/internal hosts are blocked by default (anti-SSRF), including "
                "redirect targets: every hop is re-validated. Body is truncated."
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
                method_upper = method.upper()
                if method_upper not in _ALLOWED_METHODS:
                    raise ToolExecutionError(f"Método no soportado: {method_upper}")
                block_private = settings.http_block_private if settings else True
                default_timeout = settings.http_timeout if settings else 15.0
                resolved_timeout = clamp(
                    timeout if timeout is not None else default_timeout, 0.1, 60.0
                )
                response = request_with_redirect_guard(
                    url,
                    method=method.upper(),
                    headers=dict(headers or {}),
                    content=body if json_body is None else None,
                    json_body=json_body,
                    block_private=block_private,
                    timeout=resolved_timeout,
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
            description=(
                "POST a JSON payload to a webhook URL (adds X-Webhook-Secret header if "
                "provided). Redirect targets are re-validated (anti-SSRF)."
            ),
        )
        def send_webhook(url: str, payload: dict[str, Any], secret: str | None = None) -> str:
            try:
                settings = self.settings
                webhook_headers = {"X-Webhook-Secret": secret} if secret else {}
                response = request_with_redirect_guard(
                    url,
                    method="POST",
                    headers=webhook_headers,
                    json_body=payload,
                    block_private=settings.http_block_private if settings else True,
                    timeout=settings.http_timeout if settings else 15.0,
                )
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
