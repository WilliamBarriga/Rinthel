# Instalación y validación en Ubuntu 26.04

## Estado de la revisión (2026-09-28)

Trabajo separado en `fix/ubuntu-26-04`, basado en `feature/windows-runtime`
para reutilizar los cambios multiplataforma. Su PR se revisa contra esa rama;
los cambios Ubuntu quedan separados de Windows y de host exec. `main` conserva
el estado anterior a Windows tras el PR de reparación.

Equipo observado: Ubuntu 26.04.1, x86_64, Python 3.14.4, unos 30 GiB de RAM,
8 GiB de swap, RTX 5070 Laptop con 8151 MiB de VRAM y controlador 595.91.07.
La GPU funciona. La indicación «CUDA 13.2» de `nvidia-smi` describe la capacidad
del controlador; no significa que esté instalado el compilador `nvcc`.
Faltaban Cargo/Rust, CMake, Docker y CUDA Toolkit. El usuario debe introducir
su contraseña de administrador para instalar los paquetes del sistema.

En la revisión original pasaron 174 pruebas Python y la sintaxis de los lanzadores. Se arrancó
el daemon con Python 3.14 y respondió correctamente a GET /config; se
detuvo al terminar. No se iniciaron servicios de inferencia. La
compilación Rust, el build CUDA y las conversaciones completas quedan
pendientes de instalar las dependencias: esta revisión no es un benchmark
Linux ni una validación completa de la aplicación en ejecución.

Tras separar las ramas, la suite completa del checkout Ubuntu pasó 189
pruebas. No se repitieron la ejecución del daemon ni pruebas de hardware.

## 1. Dependencias de Ubuntu

En una terminal normal (no ejecutes Rinthel como root):

```bash
sudo apt update
sudo apt install -y python3-venv build-essential curl ca-certificates git cmake pkg-config docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Cierra sesión y vuelve a entrar para que se aplique el grupo Docker. Luego:

```bash
docker info
docker compose version
```

El grupo Docker permite administrar contenedores con privilegios sobre el
host. INSTALL escribe su GID como `DOCKER_GID` en el `.env` raíz.
No mezcles los paquetes `docker.io` de Ubuntu con Docker CE. Si prefieres CE,
usa exclusivamente la [guía oficial de Docker](https://docs.docker.com/engine/install/ubuntu/).

No necesitas Node/npm en el host. El instalador usa rustup si falta Cargo.
Ubuntu 26.04 ya trae un Python compatible; no agregues deadsnakes.

## 2. CUDA para esta RTX 5070

El paquete `nvidia-cuda-toolkit` ofrecido por los repositorios Ubuntu de este
equipo era 12.4, anterior a esta GPU Blackwell. Usa el repositorio NVIDIA
para Ubuntu 26.04. La guía actual de NVIDIA soporta esta distribución con
CUDA 13.4. La rama del controlador asociada a CUDA 13.4 es R615: el 595
observado debe actualizarse para seguir esta combinación sin depender del
modo de compatibilidad entre versiones menores.

Fuentes: [CUDA Linux](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/),
[versiones CUDA/controlador](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/),
[controlador para Ubuntu](https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/ubuntu.html).

```bash
curl -fL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2604/x86_64/cuda-keyring_1.1-1_all.deb -o /tmp/cuda-keyring_1.1-1_all.deb
sudo dpkg -i /tmp/cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install linux-headers-$(uname -r)
sudo apt install nvidia-open cuda-toolkit-13-4
```

Revisa la propuesta de APT antes de aceptar, especialmente si ya tienes
paquetes NVIDIA de otro origen. Con Secure Boot activo, completa la
inscripción MOK si el instalador la solicita. Reinicia al terminar.

En una nueva terminal:

```bash
export PATH=/usr/local/cuda-13.4/bin:$PATH
nvidia-smi
nvcc --version
```

Agrega ese `export PATH=...` una sola vez al final de `~/.bashrc` para que
persista. No continúes con INSTALL si `nvidia-smi` o `nvcc` fallan. No uses
`--allow-unsupported-compiler` como solución automática.

## 3. Instalar Rinthel

Desde la carpeta donde está este README:

```bash
git branch --show-current
rinthel/install.sh --skip-launch
```

El script instala Rust si falta, crea `.venv`, instala el daemon y compila
el cliente. No descarga el modelo ni inicia los contenedores en este paso.

Linux usa el compose raíz único (ya no hay un perfil Ubuntu aparte ni
`COMPOSE_FILE`), datos en `data/` y secretos generados localmente en el
`.env` raíz. No reutilices un `.venv` o rutas absolutas de Windows. Los
archivos `.env`, `data/` y `models.local.json` están ignorados por Git.

Una instalación anterior con otro layout no se migra: el layout actual no
lee el `.env` ni los datos de otro portal. Haz un INSTALL limpio y borra a
mano lo que ya no uses en `data/` (INSTALL nunca borra nada).

Deck usa la red del host, por lo que alcanza al daemon y al modelo en
`127.0.0.1:8080` (`deck.host_address`) sin reglas iptables especiales. Los
servidores web escuchan en las interfaces del host; limita con tu firewall el
acceso desde otras máquinas si solo quieres uso local.

Comprueba la configuración sin imprimir secretos:

```bash
docker compose config --quiet
rinthel/rinthel-boot.sh
```

En la interfaz:

1. **INSTALL**: valida dependencias, compila llama.cpp upstream (ggml-org, rama `master`) con CUDA, descarga el GGUF
   del Local model por defecto (aproximadamente 22 GB) y escribe el catálogo
   inicial `models.local.json` con ese modelo activo
   ([`local-models.md`](local-models.md)). Genera en el `.env` raíz los
   secretos de la Instance, el token de host exec, `PUID`/`PGID` (tu
   usuario, con el que corre Deck) y `DOCKER_GID`, y el token de Understory
   (`AUTH_TOKEN` = `UNDERSTORY_TOKEN`) con su bundle en `data/understory`.
   Crea `rinthel.db` y el primer admin: copia la contraseña que muestra,
   no se vuelve a mostrar.
2. **BOOT**: carga el modelo y construye/inicia Understory y Deck.
3. **MONITOR**: confirma que los servicios estén disponibles.
4. Abre Deck en <http://127.0.0.1:4100> y entra como `admin` con esa
   contraseña. Si la perdiste: `python -m rinthel_tui.identity reset-admin`.
   Understory queda en <http://127.0.0.1:3800>.

Linux arranca con su Validated profile (`VALIDATED_PROFILES["linux"]` en
`rinthel_tui/config.py`). Cierra juegos u otras aplicaciones que consuman
mucha RAM/VRAM durante la primera prueba.

Deck guarda su estado (`deck.db`, el home de pi, Sesiones) en `data/deck`;
no se requieren carpetas Pi preexistentes en el host.

## 4. Uso diario y diagnóstico

```bash
rinthel/rinthel-boot.sh
```

Usa **BOOT** para iniciar servicios y **TERMINATE** para detenerlos.
`rinthel/rinthel-boot.sh --stop` detiene únicamente el daemon de control;
no detiene automáticamente los contenedores ni el modelo.

```bash
curl -f http://127.0.0.1:8080/v1/models
docker compose ps
docker compose logs --tail 60 deck understory
tail -n 60 logs/daemon.log
tail -n 60 logs/llama-server.log
```

Si Docker muestra permisos denegados, confirma que la sesión tenga el grupo
`docker`; reiniciar solo la terminal puede no aplicar el cambio. Si
instalaste Docker después de INSTALL, vuelve a correrlo para que escriba
`DOCKER_GID`. No uses
`sudo rinthel/install.sh`, porque los datos quedarían con propietario root.

Para cambiar de Local model, edita `models.local.json` y usa
`python -m rinthel_tui.models use <id>` con los servicios parados, o el
cambio del daemon desde Deck ([`local-models.md`](local-models.md)).

## Pruebas reproducibles

```bash
rinthel/.venv/bin/python -m pip install -e 'rinthel[dev]'
(cd rinthel && .venv/bin/python -m pytest -q)
bash -n rinthel/install.sh rinthel/rinthel-boot.sh
cargo test --locked --manifest-path rinthel/rinthel-client/Cargo.toml
```

`graphify` no estaba instalado en este equipo; no se regeneró el grafo.
