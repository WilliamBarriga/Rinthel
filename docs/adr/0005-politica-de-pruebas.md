# Política de pruebas: una prueba cruza el interface y no parchea la implementación

Una prueba cruza el **interface** del module que prueba. No parchea funciones ni constantes privadas del module, ni globales de la stdlib (`asyncio`, `shutil`, `urllib`, `os`), ni una función pública de otro module que un puerto o un doble ya reemplaza. Lo que varía entra por un puerto con un **Doble**, o por un parámetro inyectado. Se hace así para que renombrar o partir una función privada no rompa ninguna prueba y un cambio de comportamiento sí. Completa [ADR 0004](0004-puertos-y-adaptadores.md) con lo que ese ADR no dice: qué no se parchea.

Las phases de `lifecycle/` llaman a procesos, sockets, HTTP y `docker compose` por el `Host` y sus puertos, que son el seam: el parche no lo es.

## Reglas para aplicar

1. **No se parchea lo que no es interface.** Quedan prohibidos: privados del module bajo prueba (`_run`, `_http_ok`), globales de la stdlib (`asyncio.create_subprocess_exec`, `asyncio.sleep`, `shutil.which`, `urllib.request.urlopen`, `os.replace`) y funciones públicas de otro module cuando existe un puerto o un doble que lo reemplaza.
2. **Lo que varía entra por un parámetro o un puerto.** Una constante parcheada pasa a ser un parámetro con default o una variable de entorno que el código ya lee (el audit log de `hostexecd` sale de `RINTHEL_INSTANCE_ROOT`). Los puntos de entrada reciben sus dependencias: `daemon.run(instance, cfg, create_app=...)`.
3. **Fallos e instantes viven en el doble.** Cada doble inyecta fallos con `fail_next(op, exc)`, donde `op` es el nombre del método del puerto; es un solo mecanismo, `rinthel_tui/faults.py`. Hay un solo `ManualClock`, con `sleep` y `now`, que se inyecta. Nunca se parchea un método de un doble, y los `sleep` reales se reemplazan por el reloj.
4. **Mensajes.**
   - Es contrato el texto que el admin ve en una respuesta HTTP o en la TUI, y los códigos de error del protocolo ([ADR 0001](0001-daemon-protocol-shape.md)).
   - El texto de un log no es contrato.
   - El texto de `PhaseReport` no es contrato mientras sea texto libre: se afirma sobre el estado resultante, la cantidad (`len(report.errors) == 1`) o una subcadena estable.
5. **Comandos.** Se afirma la intención (`compose.up(service)`), no el argv. El argv exacto se prueba solo en la prueba del adapter real, contra un `FakeRunner` que graba comandos. La excepción deliberada es el argv de `llama-server`, que se fija entero porque es el Validated profile: cambiarlo pide un benchmark.
6. **El orden como contrato** se prueba con dobles que comparten un `log` de eventos (`tests/lifecycle/fakes.py::fake_host`).

## Niveles

- **Suites de contrato por puerto**: adapter real y doble pasan la misma suite. La pata real que necesita Docker se saltea si no hay Docker con la imagen ya bajada, salvo con `RINTHEL_REQUIRE_DOCKER_TESTS=1`; nunca toca los proyectos compose de la Instance.
- **Superficie HTTP/WS del daemon** vía `create_app` sobre una Instance en `tmp_path`, con el `Host` de dobles y la telemetría en memoria (`tests/daemon/`).
- **JSON de `tests/protocol_fixtures/`**: el contrato daemon↔TUI, compartido por la prueba HTTP del daemon y la del cliente Rust.
- **Guardias como pruebas normales**: la tabla de imports y esta política.

## Aplicación

`rinthel/tests/test_patching_policy.py` recorre el AST de `tests/` y falla si hay un `monkeypatch.setattr` o `patch()` contra un nombre `_privado`, contra una constante o contra un global de la stdlib (`asyncio`, `shutil`, `os`, `urllib`, `socket`, `time`). No marca `setenv`, `chdir` ni `delitem`. La lista de topes por archivo (`FROZEN`) está vacía: un parche nuevo no entra. La regla sobre funciones públicas de otro module no tiene guardia (el AST no distingue una función pública de un puerto); la hace cumplir la revisión.

## Considered Options

- **Solo regla, sin guardia:** descartada. Nada impediría que los parches vuelvan.
- **Lista de excepciones sin tope:** descartada. Un archivo exento no baja nunca.
- **Una sección dentro de ADR 0004:** descartada. Tiene decisiones propias y un ADR separado se reemplaza sin reescribir el otro.
