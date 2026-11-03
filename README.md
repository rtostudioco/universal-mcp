# Universal MCP 🧩

**Ecosistema modular de herramientas de IA, datos, automatización y análisis sobre el [Model Context Protocol](https://modelcontextprotocol.io).**

Universal MCP es un servidor MCP en Python cuyo núcleo (*MCP Core*) es **plenamente modular**: los módulos se **descubren e instalan automáticamente**, así que puedes añadir herramientas nuevas sin reescribir el servidor. Soporta **ambos transportes** — `stdio` (para Claude Desktop / CLI) y `streamable-http` / `sse` (para acceso remoto).

---

## ✨ Características

- 🔌 **Dos transportes**: `stdio`, `streamable-http` y `sse` seleccionables por configuración.
- 🧩 **Núcleo modular con auto-descubrimiento**: builtin + plugins externos (`MCP_PLUGIN_DIRS`) sin tocar el servidor.
- 🛡️ **Seguridad por diseño**: sandbox de archivos, SQLite solo-lectura, evaluación matemática por AST-whitelist, bloqueo anti-SSRF, ejecución de shell desactivada por defecto, secretos enmascarados.
- 📦 **31 tools listas para usar** en 6 módulos.
- ⚙️ **Configuración 100% por variables de entorno** (`MCP_*` / `.env`).
- 🧪 **Suite de pruebas completa** (pytest + pytest-asyncio).
- 📚 **Documentación de arquitectura y guía de extensión**.

## 🚀 Instalación

Requiere **Python ≥ 3.10**.

```bash
cd universal-mcp

# Opción A — uv (rápido)
uv venv .venv
uv pip install -e ".[dev]" --python .venv/bin/python

# Opción B — pip clásico
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## 🖥️ Uso

### Transporte stdio (Claude Desktop, CLI, IDEs)

```bash
.venv/bin/python -m universal_mcp
# o, tras instalar:
universal-mcp
```

Configuración de ejemplo para **Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "universal": {
      "command": "/ruta/a/universal-mcp/.venv/bin/python",
      "args": ["-m", "universal_mcp"],
      "env": {
        "MCP_LOG_LEVEL": "INFO",
        "MCP_WORKSPACE_DIR": "/ruta/a/universal-mcp/workspace"
      }
    }
  }
}
```

### Transporte streamable-http (remoto / múltiples clientes)

```bash
MCP_TRANSPORT=streamable-http MCP_HOST=127.0.0.1 MCP_PORT=8000 universal-mcp
# Endpoint: http://127.0.0.1:8000/mcp
```

### Transporte SSE (legado)

```bash
MCP_TRANSPORT=sse universal-mcp
```

## 🧰 Módulos incluidos (31 tools)

| Módulo | Tools | Descripción |
|---|---|---|
| `system` | `system_info`, `system_now`, `system_disk_usage`, `system_env_vars`, `system_run_command` | Info del host, hora por zona horaria, disco, variables de entorno (secretos enmascarados), shell opt-in. |
| `files` | `files_list_files`, `files_read_file`, `files_write_file`, `files_delete_file`, `files_search_files` | Archivos dentro del **sandbox** del workspace: listar, leer, escribir, borrar y búsqueda tipo grep (literal o regex). |
| `data` | `data_read_csv`, `data_read_json`, `data_flatten_json`, `data_sqlite_query`, `data_to_json` | CSV/JSON del sandbox, aplanado de JSON y **SQLite solo-lectura**. |
| `analysis` | `analysis_stats`, `analysis_math_eval`, `analysis_linear_regression`, `analysis_correlation`, `analysis_frequency` | Estadística descriptiva, calculadora segura (AST), regresión lineal, correlación de Pearson y frecuencias. |
| `ai` | `ai_text_stats`, `ai_summarize`, `ai_sentiment`, `ai_keywords`, `ai_extract`, `ai_slugify` | NLP local (sin APIs): métricas de texto, resumen extractivo, sentimiento ES/EN, keywords, extracción de entidades y slugs. |
| `automation` | `automation_http_request`, `automation_send_webhook`, `automation_uuid4`, `automation_timestamp`, `automation_wait` | HTTP con protección anti-SSRF, webhooks y utilidades. |

## ⚙️ Configuración (variables de entorno)

| Variable | Por defecto | Descripción |
|---|---|---|
| `MCP_SERVER_NAME` | `universal-mcp` | Nombre visible por el cliente. |
| `MCP_TRANSPORT` | `stdio` | `stdio` \| `streamable-http` \| `sse`. |
| `MCP_HOST` / `MCP_PORT` | `127.0.0.1` / `8000` | Bind de los transportes HTTP. |
| `MCP_LOG_LEVEL` | `INFO` | Nivel de log (siempre a **stderr**). |
| `MCP_DISABLED_MODULES` | *(vacío)* | Módulos a omitir, p. ej. `system,ai`. |
| `MCP_PLUGIN_DIRS` | *(vacío)* | Directorios de plugins externos. |
| `MCP_WORKSPACE_DIR` | `./workspace` | Sandbox para `files_*` y `data_*`. |
| `MCP_ENABLE_SHELL` | `false` | Habilita `system_run_command`. ⚠️ |
| `MCP_HTTP_BLOCK_PRIVATE` | `true` | Bloquea IPs privadas/loopback (anti-SSRF). |
| `MCP_HTTP_TIMEOUT` | `15` | Timeout HTTP en segundos. |
| `MCP_MAX_OUTPUT_CHARS` | `20000` | Truncado de cuerpos HTTP. |

Consulta `.env.example` para una plantilla completa.

## ➕ Añadir un módulo nuevo (sin reescribir el servidor)

**Opción 1 — módulo builtin:** crea `src/universal_mcp/modules/<nombre>/module.py`:

```python
from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext
from universal_mcp.core.utils import to_json


class WeatherModule(BaseModule):
    name = "weather"  # prefijo de las tools: weather_*

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(name="current", description="Weather for a city (demo).")
        def current(city: str) -> str:
            return to_json({"city": city, "temp_c": 21})
```

Reinicia el servidor: el registry lo detecta y registra automáticamente como `weather_current`.

**Opción 2 — plugin externo (cero cambios de código):** guarda el mismo archivo en cualquier carpeta y arranca con:

```bash
MCP_PLUGIN_DIRS=/ruta/a/mis/plugins universal-mcp
```

Guía completa: [`docs/ADDING_MODULES.md`](docs/ADDING_MODULES.md) · Ejemplo ejecutable: [`examples/plugins/hello_plugin.py`](examples/plugins/hello_plugin.py).

## 🔒 Modelo de seguridad

- **Sandbox de archivos**: `resolve_in_workspace()` valida cada ruta (incluye symlinks) contra `MCP_WORKSPACE_DIR`.
- **SQLite de solo lectura**: `PRAGMA query_only` + whitelist `SELECT/WITH/PRAGMA/EXPLAIN`.
- **Math por AST-whitelist**: sin `eval`; operaciones y funciones permitidas explícitamente.
- **Anti-SSRF**: resolución DNS + bloqueo de IPs privadas/loopback/reservadas en `automation_*`.
- **Shell opt-in**: `system_run_command` responde con error salvo `MCP_ENABLE_SHELL=true`.
- **Secretos enmascarados**: `system_env_vars` oculta valores de claves sensibles.
- **Logging a stderr**: stdout queda reservado al protocolo (crítico en stdio).

## 🧪 Pruebas

```bash
.venv/bin/pytest -v          # suite completa (~60 aserciones)
.venv/bin/ruff check .       # lint (opcional)
```

Cobertura: núcleo (config, registry, contexto, sandbox), integración del servidor (`tools/list` real vía FastMCP), y cada módulo (lógica pura + ejecución vía protocolo).

## 🗺️ Roadmap

- [ ] Hot-reload de módulos (`registry.reload()`).
- [ ] Resources y prompts builtin por módulo.
- [ ] Aislamiento por subprocess para plugins no confiables.
- [ ] Métricas (Prometheus) y traza de ejecución por tool.
- [ ] Autenticación para transporte HTTP (bearer/OAuth).

## 📖 Documentación

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — decisiones de diseño, diagramas y flujo de registro.
- [`docs/ADDING_MODULES.md`](docs/ADDING_MODULES.md) — guía paso a paso para extender.

## 📄 Licencia

MIT — consulta [`LICENSE`](LICENSE).
