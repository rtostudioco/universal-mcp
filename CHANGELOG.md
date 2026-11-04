# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y [SemVer](https://semver.org/lang/es/).

## [0.2.0] — Security & Reliability

Release de estabilización: cierra la superficie de seguridad pendiente y
endurece el núcleo antes de sumar funcionalidad nueva.

### Seguridad

- **Anti-SSRF por hop en redirecciones** (`automation_http_request`,
  `automation_send_webhook`): `follow_redirects=False` + bucle manual que
  re-valida **cada destino** con `assert_public_host()` (Location absolutas y
  relativas, límite de 5 saltos, degradación 301/302/303 → GET y descarte de
  cuerpo; 307/308 conservan método y cuerpo). Elimina el bypass clásico
  `302 → http://169.254.169.254/` y reduce el DNS rebinding (re-validación por
  salto).
- **Permisos por herramienta**: nuevas variables `MCP_ALLOWED_TOOLS` y
  `MCP_BLOCKED_TOOLS` (globs sobre el nombre final, `blocked` siempre gana).
  - Registro: una tool no permitida **no se registra** y se reporta en
    `RegistrationReport.blocked_tools`; el resto del módulo sigue vivo.
  - Runtime: las tools registradas llevan un guard que lanza
    `SecurityViolationError` si la política las bloquea.

### Fiabilidad

- **Sin registro parcial**: si un módulo falla a mitad de registro, las
  tools/prompts/resources que dejó a medias se **revierten** (rollback vía
  snapshot del estado interno de FastMCP + `remove_tool`) y sus nombres
  quedan libres; el motivo queda en el `RegistrationReport` con
  `rolled back N item(s)`.
- **Ciclo de vida completo**: `UniversalMCPServer.shutdown()` invoca
  `teardown()` de cada módulo en **orden inverso** al de carga, es
  idempotente y tolerante a fallos individuales. Conectado a
  `SIGTERM`/`SIGHUP`/`SIGINT` y `atexit` en el entrypoint CLI.
- **Tests de seguridad y fallos**: suite ampliada de 46 → 75 pruebas
  (`tests/test_security.py`): redirecciones maliciosas (privada, esquema no
  HTTP, bucle, 303/307), política de permisos (globs, allowlist, blocked
  gana, guard runtime), rollback parcial y ciclo de vida (orden inverso,
  idempotencia, teardown roto).

### Compatibilidad

- **CI con Python 3.13**: la matriz de GitHub Actions ahora prueba
  3.10 / 3.11 / 3.12 / 3.13.
- Documentación: modelo de seguridad ampliado (README) y notas de ciclo de
  vida / permisos en `docs/ARCHITECTURE.md` y `docs/ADDING_MODULES.md`.

### Notas

- Los plugins externos siguen **desactivados por defecto** (`MCP_PLUGIN_DIRS`
  vacío) y se ejecutan in-process: úsalos solo con código de confianza.

## [0.1.0] — Lanzamiento inicial

- Núcleo modular con auto-descubrimiento (builtin + plugins externos).
- 6 módulos builtin, 31 tools: `system`, `files`, `data`, `analysis`, `ai`,
  `automation`.
- Transportes `stdio`, `streamable-http` y `sse` sobre FastMCP (SDK oficial).
- Seguridad: sandbox de archivos, SQLite solo-lectura, math AST-whitelist,
  bloqueo anti-SSRF directo, shell opt-in, secretos enmascarados.
- Configuración por variables de entorno (`MCP_*`).
- Suite de pruebas (46) + CI (pytest + ruff, Python 3.10–3.12).
