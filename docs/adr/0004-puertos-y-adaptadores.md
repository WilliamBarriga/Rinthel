# Puertos y adaptadores: el dominio del daemon no conoce procesos, red ni Docker

El dominio de cada módulo del daemon define el interface de sus seams (el host donde corre la Instance: comandos, procesos, `docker compose`, sondeos, directorios de datos; las fuentes de telemetría del Monitor) y `subprocess`, `socket`, `urllib`, `psutil`, `nvidia-smi` y el filesystem son adapters intercambiables detrás. Se hace así para cambiar la infraestructura sin tocar el dominio: el adapter Windows de `Processes` y `Probe` entra por la raíz de composición, sin `os.name` en el dominio. El vocabulario (module, interface, seam, adapter, depth) es el de la skill `codebase-design`.

Cada módulo con regla en `rinthel/tests/import_table.py` (`lifecycle`, `monitoring`, `identity`, `models`) tiene la misma forma; `api`, `install`, `config`, `instance`, `database` y los demás de `UNGUARDED` son composición o infraestructura compartida:

- **`domain/`** define el puerto como un `Protocol`, sus tipos y sus errores, y la regla que los usa.
- **`adapters/`** trae el adapter real y, donde conviene, uno en memoria.
- **Suite de contrato por puerto:** el adapter real y el doble pasan la misma suite (`rinthel/tests/lifecycle/test_*_contract.py`, `rinthel/tests/monitoring/test_*_contract.py`); el resto de las pruebas corre el dominio contra el doble. Todo adapter nuevo nace con su contrato.
- **Guardia de imports:** `rinthel/tests/test_import_table.py` recorre con un solo helper AST la tabla `import_table.py` (módulo → imports permitidos, con motivo en cada excepción; un módulo nuevo es una fila, y una fila de un módulo que ya no existe falla) y falla si un `domain/` importa infraestructura (`fastapi`, `httpx`, `sqlite3`, `subprocess`, `psutil`, `os`, `pathlib`…) o un adapter. `lifecycle/domain` arma rutas (`pathlib`) y además tiene prohibidos `socket`, `urllib`, `shutil` y `time`, que tienen su puerto.

## `lifecycle`: el `Host` de ocho puertos

`lifecycle/domain/host.py` define el `Host`, una dataclass congelada con los ocho puertos del host. Toda phase lo recibe primero: `fn(host, report, **kwargs)`.

- `Runner`: comando → rc y salida. Un comando que no existe es rc 127, no una excepción.
- `Processes`: lanzar procesos de larga vida (devuelve un `ProcessHandle` opaco), pararlos, y `stop_listeners(port, force=)`, que para a quien escuche en un puerto lo haya lanzado o no este proceso (así matan las phases: por puerto, no por PID guardado). El adapter POSIX usa psutil, sin depender de `fuser`.
- `Compose`: intenciones sobre un servicio de `docker compose`; el argv vive en un solo adapter.
- `Probe`: puerto abierto, URL que responde 2xx.
- `Clock`: el reloj neutral de `rinthel_tui/clock.py` (`SystemClock`, `ManualClock`).
- `HostInfo`: `platform()` (`linux` o `windows`, ver **Platform**), `which`, `find_nvcc`, `cpu_count`, `sha256`.
- `PackageRegistry`: la última versión publicada de un paquete npm.
- `DataDirs`: crea un directorio de datos para `uid`:`gid` y devuelve su dueño (un bind mount que Docker autocrea es de `root`).

No hay puerto de base de datos en el `Host`: la migración de `rinthel.db` es del arranque del daemon. No hay puerto de filesystem general: clonar, compilar y descargar son comandos sobre `Runner`, y las pruebas usan `tmp_path` real. Las phases de dominio (`domain/phases/`) reciben un `LocalProcessSpec` o un `DockerComposeSpec` ya armados y no conocen `RinthelConfig`; las definiciones de `lifecycle/services.py` los arman con `spec(cfg)` al construir el plan. Las phases de INSTALL (`lifecycle/install.py`) quedan fuera de la guardia: reciben una tarea (`install_tasks.py`), pero tocan el `.env` de la Instance. `lifecycle/composition.py::real_host()` es el único lugar que elige los adapters reales.

## `monitoring`: un puerto por fuente

El Monitor mezcla los Telemetry streams de `/ws/monitor` (`docker_status`, `gpu_sample`, `cpu_ram_sample`, `log_line`, `models_status`). Cada fuente es un puerto (`GpuSensor`, `HostSensor`, `ContainerStatus`, `ServiceLog`, `ModelsSensor`) con su adapter real y uno en memoria. `models_status` reporta solo lo que la Instance corre en su Platform: el adapter real decide qué Capability y qué managed service se omiten, y el cliente no suma filas propias.

## La capa HTTP: composición por área

`rinthel_tui/api/` es composición, no dominio, y se parte por área (`config`, `ws`, `lifecycle`, `secrets`, `identity`, `models`). Un área es un paquete con sus `dtos.py`, su `routes.py` y, si tiene estado, un `compose.py`. `create_app` es la lista ordenada de áreas: elige los adapters (`api/adapters.py::Adapters`, el único lugar que lo hace dentro de la app), llama a `compose` de cada área, vuelca el estado en `app.state` e incluye los routers; no construye módulos de dominio (`tests/daemon/test_create_app_areas.py`). Las rutas piden estado con `Depends(state("<atributo>"))`. Un área nueva (identidad, Local models) se suma igual: su paquete, su fila en `create_app` y, si trae dominio, su fila en la tabla de imports.

## Consecuencias

- Un adapter nuevo (Windows, SQLite) no toca el dominio ni las phases: se elige en la composición y pasa la suite del puerto.
- Las pruebas no parchean: lo que varía entra por el doble del puerto ([ADR 0005](0005-politica-de-pruebas.md)).
- El cierre de recursos es de la composición: los puertos no declaran `close()`.
