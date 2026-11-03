"""``ModuleRegistry``: descubrimiento e instalación de módulos.

Estrategias de descubrimiento:

1. **Builtin**: recorre ``universal_mcp.modules/*`` importando cada
   ``module.py`` y recolectando las subclases de ``BaseModule``.
2. **Plugins externos**: recorre cada directorio de ``MCP_PLUGIN_DIRS``
   cargando ``*.py`` sueltos y paquetes ``<dir>/module.py``. Esto permite
   incorporar módulos nuevos **sin tocar el código del servidor**.

Un módulo defectuoso nunca derriba el servidor: se registra en el informe
de carga y se continúa con el resto.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from universal_mcp.core.base import BaseModule
from universal_mcp.core.config import Settings
from universal_mcp.core.context import ModuleContext

logger = logging.getLogger("mcp.registry")


@dataclass
class LoadedModule:
    instance: BaseModule
    source: str


@dataclass
class SkippedModule:
    name: str
    source: str
    reason: str


@dataclass
class RegistrationReport:
    loaded: list[LoadedModule] = field(default_factory=list)
    skipped: list[SkippedModule] = field(default_factory=list)


class ModuleRegistry:
    """Descubre, instancia y registra módulos en el servidor FastMCP."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._candidates: list[tuple[type[BaseModule], str]] = []
        self._discovery_skipped: list[SkippedModule] = []

    # ------------------------------------------------------------------
    # Descubrimiento
    # ------------------------------------------------------------------
    def discover(self) -> None:
        """Popula la lista de candidatos (builtin + plugins externos)."""
        self._candidates = []
        self._discovery_skipped = []
        self._discover_builtin()
        for directory in self.settings.plugin_dirs:
            self._discover_dir(Path(directory))

    def _discover_builtin(self) -> None:
        try:
            import universal_mcp.modules as pkg
        except ImportError:  # pragma: no cover
            logger.warning("No se encontró el paquete universal_mcp.modules")
            return

        for info in pkgutil.iter_modules(pkg.__path__):
            if not info.ispkg:
                continue
            target = f"{pkg.__name__}.{info.name}.module"
            try:
                mod = importlib.import_module(target)
            except ModuleNotFoundError:
                continue  # subpaquete sin module.py: se ignora en silencio
            except Exception as exc:  # módulo roto: se reporta y se sigue
                self._discovery_skipped.append(
                    SkippedModule(info.name, f"builtin:{info.name}", f"import failed: {exc}")
                )
                logger.warning("Error importando módulo builtin '%s': %s", info.name, exc)
                continue
            self._collect_classes(mod, source=f"builtin:{info.name}")

    def _discover_dir(self, directory: Path) -> None:
        if not directory.is_dir():
            self._discovery_skipped.append(
                SkippedModule(str(directory), "plugin", "plugin dir not found")
            )
            return
        for py_file in sorted(directory.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            self._load_file(py_file, source=f"plugin:{py_file.name}")
        for sub in sorted((p for p in directory.iterdir() if p.is_dir()), key=lambda p: p.name):
            module_py = sub / "module.py"
            if module_py.exists():
                self._load_file(module_py, source=f"plugin:{sub.name}/")

    def _load_file(self, path: Path, *, source: str) -> None:
        """Carga un archivo Python arbitrario y busca ``BaseModule`` en él."""
        unique = f"mcp_plugin_{path.parent.name}_{path.stem}_{abs(hash(str(path))) % 100_000}"
        spec = importlib.util.spec_from_file_location(unique, path)
        if spec is None or spec.loader is None:
            self._discovery_skipped.append(SkippedModule(path.name, source, "no importlib spec"))
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[unique] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            self._discovery_skipped.append(
                SkippedModule(path.name, source, f"import failed: {exc}")
            )
            logger.warning("Plugin '%s' no cargó: %s", path, exc)
            return
        self._collect_classes(module, source=source)

    def _collect_classes(self, module: ModuleType, *, source: str) -> None:
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseModule)
                and obj is not BaseModule
                and obj.__module__ == module.__name__
            ):
                self._candidates.append((obj, source))
                logger.debug("Módulo candidato: %s (%s)", obj.name, source)

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------
    def register_all(self, server: Any, taken_names: set[str]) -> RegistrationReport:
        """Instancia y registra los candidatos en el servidor.

        - Respeta ``MCP_DISABLED_MODULES``.
        - Rechaza nombres de módulo duplicados (gana el primero).
        - Aísla fallos: un módulo roto no afecta a los demás.
        """
        report = RegistrationReport(skipped=list(self._discovery_skipped))
        seen: set[str] = set()

        for cls, source in self._candidates:
            name = getattr(cls, "name", None) or cls.__name__

            if name in self.settings.disabled_modules:
                report.skipped.append(SkippedModule(name, source, "disabled by config"))
                continue
            if name in seen:
                report.skipped.append(SkippedModule(name, source, "duplicate module name"))
                continue

            instance: BaseModule | None = None
            try:
                instance = cls(self.settings)
                instance.setup()
                ctx = ModuleContext(server, instance, self.settings, taken_names)
                instance.register(ctx)
            except Exception as exc:
                report.skipped.append(
                    SkippedModule(name, source, f"registration failed: {exc}")
                )
                logger.warning("Módulo '%s' falló al registrarse: %s", name, exc)
                continue

            seen.add(name)
            report.loaded.append(LoadedModule(instance=instance, source=source))

        return report
