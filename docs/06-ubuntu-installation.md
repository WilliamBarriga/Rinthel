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

Tras separar las ramas, la suite completa del checkout Ubuntu pasó 186
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
host. El portal necesita el socket Docker para sus complementos gestionados.
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
./install.sh --skip-launch
```

La rama debe ser `fix/ubuntu-26-04`. El script instala Rust si falta,
crea `.venv`, prepara la configuración Linux y compila el cliente.
No descarga el modelo ni inicia los contenedores en este paso.

El perfil Linux usa `COMPOSE_FILE=docker-compose.ubuntu.yml` en `.env`,
datos en `data/`, secretos generados localmente y el proveedor `local-llm`.
No reutilices un `.venv` o rutas absolutas de Windows. El instalador conserva
los valores existentes en `.env`; revisa ese archivo si lo copiaste de otra
máquina. Los archivos `.env` y `data/` están ignorados por Git.

Ambos contenedores usan `network_mode: host`, por lo que alcanzan al modelo
en `127.0.0.1:8080` sin reglas iptables especiales. Los servidores web
escuchan en las interfaces del host; limita con tu firewall el acceso desde
otras máquinas si solo quieres uso local. El perfil no activa VPN ni voz.

Comprueba la configuración sin imprimir secretos:

```bash
docker compose config --quiet
./rinthel-boot.sh
```

En la interfaz:

1. **INSTALL**: valida dependencias, compila el fork CUDA y descarga el GGUF
   (aproximadamente 22 GB). Deja que la descarga termine: la lógica antigua
   puede confundir una descarga interrumpida con un archivo completo.
2. **BOOT**: carga el modelo y construye/inicia Understory y Pithagoras.
3. **MONITOR**: confirma que los tres servicios estén disponibles.
4. Abre <http://127.0.0.1:4100>. La contraseña está en `PORTAL_PASSWORD` del
   `.env` local. Understory queda en <http://127.0.0.1:3800>.

El perfil conserva los valores de inferencia validados en Windows como
punto de partida, sin afirmar el mismo rendimiento en Linux. Cierra juegos
u otras aplicaciones que consuman mucha RAM/VRAM durante la primera prueba.

En Pithagoras, para conectar las herramientas de memoria, abre **Settings →
MCP**, instala `pi-mcp-adapter` si el portal lo solicita, y añade un servidor
HTTP con URL `http://127.0.0.1:3800/mcp` y `bearerTokenEnv` igual a
`UNDERSTORY_TOKEN`. Inicia una sesión nueva después de configurarlo. Los
paquetes se instalan en el volumen persistente del portal: no se requieren
carpetas Pi preexistentes en el host.

## 4. Uso diario y diagnóstico

```bash
./rinthel-boot.sh
```

Usa **BOOT** para iniciar servicios y **TERMINATE** para detenerlos.
`./rinthel-boot.sh --stop` detiene únicamente el daemon de control;
no detiene automáticamente los contenedores ni el modelo.

```bash
curl -f http://127.0.0.1:8080/v1/models
docker compose ps
docker compose logs --tail 60 portal understory
tail -n 60 logs/daemon.log
tail -n 60 logs/llama-server.log
```

Si Docker muestra permisos denegados, confirma que la sesión tenga el grupo
`docker`; reiniciar solo la terminal puede no aplicar el cambio. Ejecuta de
nuevo `./install.sh --skip-launch` después de instalar Docker para registrar
su GID real. No uses `sudo ./install.sh`, porque los datos quedarían con
propietario root.

Si cambias el puerto del modelo o su ruta en CONFIGURAR, ejecuta de nuevo
`./install.sh --skip-launch`, detén el daemon con `--stop` y vuelve a abrirlo;
así se actualizan `models.json` y las variables que heredan los contenedores.

## Pruebas reproducibles

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
bash -n install.sh rinthel-boot.sh
cargo test --locked --manifest-path rinthel-client/Cargo.toml
```

`graphify` no estaba instalado en este equipo; no se regeneró el grafo.
