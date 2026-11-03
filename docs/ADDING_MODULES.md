# Guía: añadir módulos nuevos a Universal MCP

El propósito central del proyecto: **incorporar herramientas sin reescribir el
servidor**. Hay dos caminos, ambos sin tocar el núcleo.

---

## Opción 1 — Módulo builtin (parte del paquete)

### Paso 1: crea la carpeta del módulo

```
src/universal_mcp/modules/<tu_modulo>/
├── __init__.py      # vacío
└── module.py        # aquí vive tu módulo
```

### Paso 2: implementa la clase

```python
# src/universal_mcp/modules/weather/module.py
from __future__ import annotations

from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext
from universal_mcp.core.utils import to_json


class WeatherModule(BaseModule):
    name = "weather"          # prefijo de tus tools → weather_*
    description = "Consultas del clima (demo)."
    version = "0.1.0"

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(
            name="current",                       # → weather_current
            description="Current weather for a city name.",
        )
        def current(city: str, units: str = "metric") -> str:
            # self.settings: Settings | None  (acceso a la configuración global)
            # self.logger:   logging.Logger   (log a stderr)
            data = {"city": city, "temp_c": 21.5, "units": units}
            return to_json(data)
```

### Paso 3: reinicia el servidor

El `ModuleRegistry` lo descubre y registra automáticamente:

```bash
.venv/bin/python -m universal_mcp
# ... Módulos cargados (7): ... weather(builtin:weather)
# Tools registradas en total: 32
```

---

## Opción 2 — Plugin externo (cero cambios en el repo)

Guarda el mismo archivo en cualquier carpeta (p. ej. `~/mis-plugins/tiempo.py`)
y arranca apuntando el directorio:

```bash
MCP_PLUGIN_DIRS=~/mis-plugins .venv/bin/python -m universal_mcp
```

El registry acepta en cada directorio de plugins:
- archivos `*.py` sueltos (se ignoran los que empiezan por `_`),
- subcarpetas con `module.py` dentro.

Ejemplo ejecutable: [`examples/plugins/hello_plugin.py`](../examples/plugins/hello_plugin.py)
→ prueba con `MCP_PLUGIN_DIRS=examples/plugins`.

---

## Contrato completo de `BaseModule`

```python
class BaseModule(ABC):
    name: ClassVar[str]              # OBLIGATORIO: prefijo único del módulo
    description: ClassVar[str] = ""  # humano, para docs
    version: ClassVar[str] = "0.1.0"

    def __init__(self, settings: Settings | None) -> None:
        self.settings = settings     # Settings globales (MCP_*)
        self.logger = logging.getLogger(f"mcp.modules.{self.name}")

    @abstractmethod
    def register(self, ctx: ModuleContext) -> None: ...

    def setup(self) -> None: ...     # opcional: tras instanciar, antes de register
    def teardown(self) -> None: ...  # opcional: al apagar el servidor
```

### API de `ModuleContext`

| Método | Uso |
|---|---|
| `ctx.tool(name=None, description=None, **kw)` | Decorador de **tool**. El nombre se prefija `modulo_name`. Detecta colisiones → `DuplicateToolError`. |
| `ctx.prompt(name=None, description=None, **kw)` | Decorador de **prompt** reutilizable (también prefijado). |
| `ctx.resource(uri, name=None, description=None, **kw)` | Decorador de **resource** (URI a tu elección, p. ej. `weather://current`). |
| `ctx.settings` | `Settings` globales del servidor. |
| `ctx.logger` / `self.logger` | Logger del módulo (stderr). |

## Convenciones y buenas prácticas

1. **Las tools devuelven `str` JSON** (`to_json(...)`) — salidas estructuradas y fáciles de leer para el LLM.
2. **Errores como datos**: captura `MCPError` y devuelve `{"error": ..., "type": ...}` en lugar de propagar.
3. **Lógica pura testeable**: implementa `*_impl()` a nivel de módulo y deja que la tool sea una envoltura fina (así lo hacen todos los builtin).
4. **Escribe docstrings/descriptions en inglés** pensadas para el LLM cliente: qué hace, parámetros, límites.
5. **Seguridad primero**: cualquier acceso a disco usa `resolve_in_workspace`; HTTP usa `assert_public_host` (ver `automation/module.py`).
6. **Nombre de módulo único y corto**, en singular si es posible (`weather`, no `weather_tools`).

## Plantilla copiable (mínima)

```python
from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext
from universal_mcp.core.utils import to_json


class MiModulo(BaseModule):
    name = "mi_modulo"

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(name="hola", description="Dice hola a alguien.")
        def hola(nombre: str) -> str:
            return to_json({"saludo": f"¡Hola, {nombre}!"})
```

## Controlar qué módulos se cargan

```bash
MCP_DISABLED_MODULES=system,ai .venv/bin/python -m universal_mcp   # por comas
MCP_DISABLED_MODULES='["system","ai"]' universal-mcp               # o JSON
```

## Probar tu módulo

```python
# tests/test_mi_modulo.py
import pytest
from universal_mcp.modules.weather import module as weather_module


def test_impl():
    assert weather_module.mi_logica_impl(...) == ...
```

Ejecuta: `.venv/bin/pytest -v`. Para verlo en el servidor real:
`.venv/bin/python -m universal_mcp` y usa tu cliente MCP favorito.
