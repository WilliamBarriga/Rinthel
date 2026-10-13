# Ejecución en el host: instalación y revisión

Esta funcionalidad corresponde al PR de host exec. Windows permanece en un
PR independiente; aquí no se cambian sus perfiles ni sus mediciones.

## Preparación

En Linux, `rinthel-boot.sh` prepara el token antes de arrancar los daemons.
La fase INSTALL de Pithagoras usa el mismo módulo:
`rinthel_tui.install.host_exec.prepare_host_exec(repo_root, portal_dir)`.

El módulo conserva un token existente, copia el valor faltante al otro
`.env` y genera un secreto solo cuando no hay ninguno. Si los valores
existentes difieren, detiene la preparación sin imprimirlos ni rotarlos.
También respeta un token exportado y rechaza conflictos con los archivos.
BOOT no crea un `.env` incompleto de Pithagoras; INSTALL conserva la
responsabilidad de generar sus demás secretos.

Pithagoras arranca sin token, con host exec deshabilitado. Después de
configurarlo, reinicia el portal para que su entorno reciba el secreto.
Los tokens y los `.env` son locales y nunca se incluyen en Git.

Cuando también está instalado el perfil Ubuntu, este usa el overlay
`compose/ubuntu-host-exec.override.yaml` para montar la extensión explícita
y pasar el token al portal. La selección queda en el `.env` raíz mediante
`COMPOSE_FILE=docker-compose.ubuntu.yml:compose/ubuntu-host-exec.override.yaml`.
El bootstrap Ubuntu detecta ambos módulos y conserva los secretos; los
checkouts que solo contienen Ubuntu mantienen su Compose independiente.

Al actualizar desde una versión que arrancaba hostexecd sin token, detén
primero los daemons lanzados por el script con `./rinthel-boot.sh --stop`.
Después ejecuta `./rinthel-boot.sh` para preparar el secreto y arrancarlos
con el entorno nuevo. Recrea el portal con
`docker compose up -d --force-recreate portal`: un simple restart de Docker
no actualiza las variables de entorno del contenedor.

## Extensión y Compose

El Compose raíz combina cada subtree con su override antes de importarlo.
`include` no fusiona recursos con el mismo nombre declarados después de
importarlos: la combinación debe hacerse mediante una lista `path`, como
describe la [documentación de Docker](https://docs.docker.com/reference/compose-file/include/).

`compose/host-exec.override.yaml` monta la extensión del repositorio como
solo lectura y declara su ruta en `RINTHEL_HOST_EXEC_EXTENSION`. Ambos overlays
montan también `rinthel-subagents` y declaran `RINTHEL_SUBAGENTS_EXTENSION`;
si esa ruta falta, el portal solo omite la tool `subagent`.
Pithagoras la entrega explícitamente al resource loader de Pi; no requiere
un `settings.json` personal ni una instalación manual. Si existe token y
la ruta configurada no puede cargarse con el guard, la sesión falla al
iniciar, en vez de continuar sin protección.

`compose/understory.override.yaml` conserva el bridge, la subnet y el alias
de host existentes. La nueva composición conserva los contextos de build
y las rutas relativas de los subtrees.

## Estado de contaminación

El módulo `SessionTaint` concentra la clasificación y la reconstrucción.
Ante contenido no confiable, el guard guarda un custom entry en el archivo
de sesión de Pi. Ese entry no se envía al modelo y sobrevive a recargas y
compactación. Al iniciar o reabrir una sesión, se reconstruye el estado
desde sus entries, incluyendo resultados históricos anteriores al marker.

La contaminación se conserva para toda la conversación, aunque se navegue
a otra rama de su árbol. Una conversación nueva y limpia conserva acceso a
host exec. Si falla la persistencia, la sesión actual sigue bloqueada.

## Alcance de delegación

La delegación a subagentes vive en `extensions/rinthel-subagents/`; reemplaza
al motor experimental `rinthel-agents`, cuya implementación se conserva en el
commit `94e1a1d84b6e8e0deac43d3875d55f0509cc8c31`. Cada subagente corre en su
propia sesión, donde el guard del portal no está cargado. Por eso la extensión
excluye `rinthel_host_exec`, la escritura a Understory y `ask_user_question`
de esas sesiones, y el guard sigue tratando como no confiables los resultados
de subagentes instaladas por otros paquetes.

## Validación

```bash
python -m pytest -q
cd pithagoras
npm run build -w server
npm test -w server
```

Las pruebas de instalación usan archivos temporales. La comprobación de
Compose usa `config --no-interpolate` y no arranca contenedores. La prueba
de carga usa el SDK real con un directorio Pi limpio; las de contaminación
cubren la reapertura de un archivo real, historiales anteriores, cambios
de sesión, compactación y errores de persistencia.
