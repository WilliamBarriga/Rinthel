# Servicios configurables: instalación + boot-time toggle/params

## Contexto

Los últimos commits (`refactor(badge): derive service badges from service
registry`, `refactor(config): declarative field-based env loading`,
`refactor: extract generic service management from phases.py`) más los
cambios sin commitear en `config.py`/`managed_service.py`/`specs.py` vienen
generalizando el lifecycle de Rinthel hacia un registro declarativo: cada
servicio (llama-server, whisper, tts, Understory, Pithagoras) es una instancia
de `LocalProcessService`/`DockerComposeService` en `services.py`, y
`BOOT_PHASES`/`DOWN_PHASES`/`RELOAD_*_PHASES` se arman iterando esas dos
listas — agregar/sacar un servicio ahí ya alcanza para que las 4 secuencias
lo reflejen.

Lo que falta, y es lo que pide Tarkark, es extender **el mismo patrón** a dos
lugares que hoy siguen hardcodeados:

1. **`[0] INSTALL`** (`specs.INSTALL_PHASES`) es una lista fija de 6 fases,
   sin relación con el registro de servicios — no hay forma de elegir qué
   instalar.
2. **No existe ningún flag "enabled"** por servicio. `LOCAL_SERVICES`/
   `DOCKER_SERVICES` se iteran siempre completos; no hay manera de decir
   "esta vez no levantes whisper" sin comentar código.

Decisiones ya confirmadas con Tarkark:

- **Un solo flag `enabled` por servicio**, no dos separados: si no lo instalo
  no lo booteo, pero puedo cambiarlo en cualquier momento después (instalarlo
  más tarde, o dejar de bootear algo ya instalado) desde una pantalla, no
  editando `.env` a mano.
- **Los 5 servicios son igual de configurables**, incluido llama-server (sin
  caso especial "el core no se apaga").
- Quiere una **pantalla interactiva en la TUI** (no solo documentar vars de
  entorno) para tildar servicios y ajustar sus parámetros.
- El plan se ejecuta **por fases, en sesiones separadas** — cada fase debe
  quedar en un estado consistente (tests en verde, sin romper lo anterior)
  antes de pasar a la siguiente.

El objetivo final: agregar o quitar un servicio del setup de alguien — o
cambiar si corre este boot — debe sentirse tan simple como ya lo es agregar
un servicio nuevo al código (una entrada en un registro), tanto para Tarkark
como para cualquiera que clone el repo.

## Fases

Cada fase es un commit (o pocos commits) autocontenido. Se puede parar entre
fases sin dejar el repo en un estado roto — la fase N no depende de que la
N+1 exista todavía.

---

### Fase 1 — `enabled` como campo declarativo (config.py)

Reusar el mecanismo `Field`/`_ENTRIES` que ya existe — no es un mecanismo
nuevo, es una fila más por servicio:

```python
Field("enabled", "RINTHEL_LLAMA_ENABLED", bool, True)
Field("enabled", "RINTHEL_WHISPER_ENABLED", bool, True)
Field("enabled", "RINTHEL_TTS_ENABLED", bool, True)
Field("enabled", "RINTHEL_UNDERSTORY_ENABLED", bool, True)
Field("enabled", "RINTHEL_PITHAGORAS_ENABLED", bool, True)
```

Un atributo `enabled: bool` más en cada dataclass (`LlamaConfig`,
`WhisperConfig`, `TTSConfig`, `UnderstoryConfig`, `PithagorasConfig`).
Default `True` en los 5 — instalaciones existentes no cambian de
comportamiento sin tocar nada.

**Archivos:** `rinthel_tui/config.py`, `.env.example` (documentar las 5 vars
nuevas, comentadas por default).

**Tests:** `tests/test_config.py` — default `enabled=True` sin `.env`,
override por env var a `false` para cada servicio.

**Verificación de la fase:** `pytest tests/test_config.py` en verde;
`default_config()` sigue funcionando igual sin `.env`.

---

### Fase 2 — `enabled_of` en el registro de servicios

Mismo patrón que `port_of`/`ready_url_of`: un campo más en `_ServiceBase`
(`managed_service.py`):

```python
enabled_of: Callable[[RinthelConfig], bool] = lambda cfg: True
```

y en `services.py`, cada instancia lo fija a su sub-config correspondiente
(`enabled_of=lambda cfg: cfg.whisper.enabled`, etc.) — cero lógica nueva, solo
una closure más por servicio, igual que las que ya existen.

**Archivos:** `rinthel_tui/lifecycle/managed_service.py`,
`rinthel_tui/lifecycle/services.py`.

**Tests:** `tests/lifecycle/test_managed_service.py` — un `_ServiceBase`/
`LocalProcessService` de prueba con `enabled_of` custom se resuelve bien
contra un `cfg` dado.

**Verificación de la fase:** depende de Fase 1 (usa `cfg.<servicio>.enabled`).
`pytest tests/lifecycle/test_managed_service.py` en verde; nada más cambia
de comportamiento todavía (BOOT/DOWN/RELOAD siguen ignorando el flag hasta
Fase 3).

---

### Fase 3 — Filtrar BOOT/DOWN/RELOAD por `enabled_of` (specs.py)

`BOOT_PHASES`/`DOWN_PHASES`/`RELOAD_SHUTDOWN_PHASES`/`RELOAD_BOOT_PHASES`/
`RELOAD_REBUILD_PHASES` hoy son constantes de módulo calculadas al importar
(antes de tener un `cfg` real). Pasan a ser funciones de `cfg`:

```python
def boot_phases(cfg: RinthelConfig) -> list[PhaseSpec]:
    local = [s for s in services.LOCAL_SERVICES if s.enabled_of(cfg)]
    docker = [s for s in services.DOCKER_SERVICES if s.enabled_of(cfg)]
    return [
        PhaseSpec("◈ DOCKER", phases.phase_check_docker),
        *[spec for svc in local for spec in (_spawn_spec(svc), _wait_spec(svc))],
        *[spec for svc in docker for spec in (_up_spec(svc), _wait_spec(svc))],
    ]
```

Mismo criterio para `down_phases(cfg)` y para las 3 tandas de RELOAD (la
renumeración `_renumbered` ya depende de longitudes calculadas en runtime, así
que solo hay que mover ese cálculo adentro de una función que reciba `cfg`).

Consumidores a actualizar (mecánico, sin cambio de lógica):
`tui/screens/menu.py` (`specs.BOOT_PHASES` → `specs.boot_phases(CONFIG)`, etc.),
`tui/screens/reload.py` (`_GROUPS` pasa a calcularse con `CONFIG` al entrar a
la pantalla), `scripts/test_phases.py` (el dict `PHASE_LISTS` pasa a
construirse con `cfg` ya cargado).

**Archivos:** `rinthel_tui/lifecycle/specs.py`, `rinthel_tui/tui/screens/menu.py`,
`rinthel_tui/tui/screens/reload.py`, `scripts/test_phases.py`.

**Tests:** `tests/lifecycle/test_specs.py` (nuevo) — `boot_phases`/
`down_phases` excluyen un servicio con `enabled=False`; RELOAD renumera bien
cuando hay servicios deshabilitados (sin saltos en `[i/N]`).

**Verificación de la fase:** depende de Fases 1-2. `pytest` completo en
verde; `.venv/bin/python scripts/test_phases.py list` sigue imprimiendo bien;
con `RINTHEL_TTS_ENABLED=false` en `.env`, correr la TUI real y confirmar que
`[1] BOOT`/`[3] TERMINATE` ya no tocan TTS ni muestran su badge en pantalla.
Esta fase ya es útil y usable por sí sola aunque no exista todavía la
pantalla de configuración (se puede probar editando `.env` a mano).

---

### Fase 4 — Generalizar INSTALL en unidades por servicio (install.py)

Hoy `phase_install_preflight` es la única fase compartida; las otras 5 se
agrupan naturalmente en 3 "unidades instalables": llama.cpp (clone+build+
descarga modelo), Pithagoras (clone+config), Understory (scaffold+config).
Whisper y TTS **no tienen fase de instalación hoy** (sus binarios se
compilan a mano fuera del repo, ver README) — su `enabled` solo afecta
BOOT/DOWN/RELOAD (ya cubierto en Fase 3), no INSTALL. Esto se documenta
explícitamente para que no sea sorpresa.

Nuevo tipo pequeño en `install.py` (mismo espíritu que `PhaseSpec`):

```python
@dataclass(frozen=True, kw_only=True)
class InstallUnit:
    label: str
    enabled_of: Callable[[RinthelConfig], bool]
    steps: tuple[tuple[str, PhaseFn], ...]  # (label del paso, función de fase)

LLAMA_INSTALL = InstallUnit(
    label="LLAMA.CPP + modelo",
    enabled_of=lambda cfg: cfg.llama.enabled,
    steps=(
        ("LLAMA.CPP — clone", phase_install_clone_llamacpp),
        ("LLAMA.CPP — build CUDA (native)", phase_install_build_llamacpp),
        ("MODELO GGUF — descarga", phase_install_download_model),
    ),
)
PITHAGORAS_INSTALL = InstallUnit(..., steps=(("PITHAGORAS — clone + configurar", phase_install_setup_pithagoras),))
UNDERSTORY_INSTALL = InstallUnit(..., steps=(("UNDERSTORY — scaffold + configurar", phase_install_setup_understory),))
INSTALL_UNITS: list[InstallUnit] = [LLAMA_INSTALL, PITHAGORAS_INSTALL, UNDERSTORY_INSTALL]
```

`specs.install_phases(cfg)` pasa a: preflight siempre primero, después los
`steps` de cada `InstallUnit` con `enabled_of(cfg)` verdadero, numerados
dinámicamente (`[i/N]`) igual que ya hace `_renumbered` para RELOAD.

**Archivos:** `rinthel_tui/lifecycle/install.py`, `rinthel_tui/lifecycle/specs.py`,
`rinthel_tui/tui/screens/menu.py` (usar `specs.install_phases(CONFIG)`),
`scripts/test_phases.py`.

**Tests:** `tests/lifecycle/test_install.py` — `INSTALL_UNITS` con una unidad
deshabilitada se excluye de `install_phases(cfg)` y el resto renumera bien.

**Verificación de la fase:** depende de Fase 1 (usa `.enabled`). `pytest` en
verde; con `RINTHEL_PITHAGORAS_ENABLED=false`, `[0] INSTALL` en la TUI real
no debe correr `phase_install_setup_pithagoras` ni numerar sus fases.

---

### Fase 5 — Helper genérico para escribir `.env` (reusar, no duplicar)

`install.py::_write_env_from_example` ya sabe patchear un `.env` preservando
comentarios — es exactamente lo que necesita la pantalla de configuración
(Fase 6) para guardar cambios en el `.env` de la raíz del repo. Se generaliza
a una función reusable (mismo archivo o un módulo chico nuevo, ej.
`rinthel_tui/env_file.py` — decidir en implementación según qué quede más
limpio):

```python
def update_env_file(path: Path, overrides: dict[str, str], *, seed_from: Path | None = None) -> None:
    """Si `path` no existe, lo siembra desde `seed_from` (ej. .env.example);
    después aplica `overrides` preservando el resto del archivo tal cual
    (comentarios incluidos), igual que _write_env_from_example."""
```

`install.py` pasa a llamar a este helper en vez de tener su propia copia de
la lógica (los tests existentes de `_write_env_from_example` migran al
helper nuevo, mismo contrato).

**Archivos:** `rinthel_tui/config.py` o `rinthel_tui/env_file.py` (nuevo),
`rinthel_tui/lifecycle/install.py`.

**Tests:** migrar/adaptar los tests actuales de
`test_write_env_from_example_overrides_keys_and_keeps_rest` y
`test_write_env_from_example_does_not_touch_comment_lines_with_equals` al
helper nuevo, más un caso nuevo: `path` no existe todavía y se siembra desde
`seed_from`.

**Verificación de la fase:** depende de nada nuevo (independiente de Fases
1-4, se puede hacer en paralelo si hace falta). `pytest` en verde;
`phase_install_setup_pithagoras`/`phase_install_setup_understory` siguen
generando `.env` idéntico a antes (regresión cero).

---

### Fase 6 — Pantalla `[N] CONFIGURAR` (settings screen)

Un solo menú nuevo, disponible siempre (no forzado antes de INSTALL — si
nadie la toca, todo sigue instalándose/booteando igual que hoy: default
`enabled=True` en los 5). Diseño genérico, no una fila hardcodeada por
servicio:

- Lista los 5 servicios de `services.LOCAL_SERVICES + services.DOCKER_SERVICES`
  (mismo registro que ya alimenta BOOT/badges) con un checkbox de `enabled`
  usando `display_name`/`menu_label` que ya tienen.
- Al seleccionar un servicio, muestra sus campos editables iterando la
  entrada correspondiente de `config._ENTRIES` (mismo dato que ya maneja
  `validate()`) — un input de texto por `Field` (bool → checkbox, el resto →
  texto), sin una pantalla hecha a mano por campo. Esto es lo que hace que
  "configurar parámetros" sea genérico y no una lista fija de 3 campos que
  hay que ampliar a mano cada vez que se agregue un `Field` nuevo.
- "Guardar" arma un dict `{env_var: valor}` con lo tocado y llama a
  `update_env_file(repo_root / ".env", overrides, seed_from=repo_root / ".env.example")`
  (Fase 5).
- Los cambios aplican en la **próxima ejecución** de Rinthel (mismo modelo que
  ya tiene `.env` hoy: se carga una sola vez al importar `config.py`) — se
  muestra un aviso tipo "cambios guardados — reiniciá Rinthel para
  aplicarlos", sin intentar un hot-reload de `CONFIG` (que además es un
  dataclass `frozen`, no se puede mutar in-place). Esto es consistente con
  cómo se pidió la feature ("en los siguientes boots").

**Archivos:** `rinthel_tui/tui/screens/settings.py` (nuevo). Wiring en
`menu.py`: una entrada más en `_build_options` (ej. `[8] CONFIGURAR --
Servicios activos y parámetros`), reordenando `EXIT` a `[9]`.

**Tests:** cobertura de la lógica de guardado (armar el dict de overrides a
partir de la selección) independiente de Textual, si es practicable separar
esa función de la screen; si no, prueba manual (ver verificación).

**Verificación de la fase:** depende de Fases 1-3 y 5. Prueba manual en la
TUI real: entrar a `[N] CONFIGURAR`, destildar un servicio, guardar,
verificar que `.env` quedó con `RINTHEL_<SVC>_ENABLED=false` sin romper el
resto del archivo, reiniciar la TUI y confirmar que `[0] INSTALL`/`[1] BOOT`
ya no tocan ese servicio ni su badge aparece.

---

### Fase 7 — Documentación

Actualizar `README.md`:
- Tabla de INSTALL: aclarar que ahora es "por unidad habilitada", no fijo.
- Sección Configuración: documentar `RINTHEL_<SERVICIO>_ENABLED` y la pantalla
  `[N] CONFIGURAR`.
- Nota explícita: whisper/tts no tienen fase de INSTALL — su binario se arma
  a mano; `enabled` en esos dos solo controla BOOT/DOWN/RELOAD.
- Actualizar diagrama de flujo del menú (nueva entrada CONFIGURAR).

**Archivos:** `README.md`.

**Verificación de la fase:** lectura cruzada contra el comportamiento real
tras Fases 1-6.

## Archivos afectados (resumen global)

- `rinthel_tui/config.py` — Fase 1 (+ Fase 5 si el helper vive acá).
- `rinthel_tui/lifecycle/managed_service.py` — Fase 2.
- `rinthel_tui/lifecycle/services.py` — Fase 2.
- `rinthel_tui/lifecycle/specs.py` — Fases 3-4.
- `rinthel_tui/lifecycle/install.py` — Fases 4-5.
- `rinthel_tui/env_file.py` (nuevo, si no queda en config.py) — Fase 5.
- `rinthel_tui/tui/screens/menu.py` — Fases 3-4 (rewiring) y 6 (nueva entrada).
- `rinthel_tui/tui/screens/reload.py` — Fase 3.
- `rinthel_tui/tui/screens/settings.py` (nuevo) — Fase 6.
- `scripts/test_phases.py` — Fases 3-4.
- `.env.example` — Fase 1.
- `README.md` — Fase 7.
- `tests/test_config.py`, `tests/lifecycle/test_managed_service.py`,
  `tests/lifecycle/test_specs.py` (nuevo), `tests/lifecycle/test_install.py`
  — una fase por archivo, como se detalla arriba.

## Verificación de punta a punta (al cerrar todas las fases)

1. `pytest` completo en verde.
2. `.venv/bin/python scripts/test_phases.py list` construye todas las listas
   sin error.
3. Con todo en default (`enabled=True` en los 5, sin tocar `.env`), `[0]
   INSTALL`/`[1] BOOT`/`[2] RELOAD`/`[3] TERMINATE` en la TUI real se
   comportan idéntico a hoy — cero regresión para quien no toca nada.
4. Con `RINTHEL_TTS_ENABLED=false` en `.env`: `[1] BOOT` no la levanta, su
   badge no aparece, `[0] INSTALL` (que igual no la tocaba) sigue sin
   tocarla.
5. Con `RINTHEL_PITHAGORAS_ENABLED=false`: `[0] INSTALL` no clona/configura
   Pithagoras y renumera bien el resto de las fases; `[1] BOOT`/`[3]
   TERMINATE` la excluyen.
6. Desde `[N] CONFIGURAR`: destildar/tildar servicios y cambiar un parámetro
   (ej. puerto), guardar, reiniciar Rinthel, confirmar que `.env` refleja los
   cambios y que el comportamiento en INSTALL/BOOT los respeta.
