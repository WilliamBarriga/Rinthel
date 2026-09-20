# Instalación en Windows 11

Rinthel puede ejecutar de forma nativa el cliente, el daemon y
`llama-server`. Understory y Pithagoras siguen siendo contenedores Linux y
requieren Docker Desktop.

## Requisitos

1. Windows 11 actualizado, WSL 2 y el controlador NVIDIA.
2. Python 3.13 o posterior, desde la [documentación oficial](https://docs.python.org/3.13/using/windows.html).
3. Rust mediante [rustup](https://www.rust-lang.org/tools/install).
4. [CMake](https://cmake.org/download/) y Visual Studio Build Tools 2022 con el componente "Desktop
   development with C++".
5. [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads) compatible con el controlador instalado.
6. [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) con el backend WSL 2 y contenedores Linux.

En una máquina sin WSL, abre PowerShell como administrador, ejecuta
`wsl --install` y reinicia cuando Windows lo solicite. Esta activación es un
cambio del sistema operativo y se hace una sola vez.

Después de instalar herramientas, abre una terminal PowerShell nueva para
que los cambios de `PATH` sean visibles.

## Bootstrap

Desde la raíz del repositorio:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

El script crea un entorno virtual en `.venv`, instala el daemon, compila
`rinthel.exe`, crea una configuración local `.env` si todavía no existe y
abre la TUI. No sobrescribe una configuración existente. La configuración
nueva incluye el perfil Windows validado de
[`02-hardware-optimization.md`](02-hardware-optimization.md).

En la TUI, ejecuta `INSTALL` para validar CUDA/Docker, compilar llama.cpp,
descargar el modelo y preparar Pithagoras/Understory. La descarga del modelo
es de aproximadamente 22 GB.

Mientras compila o descarga, abre otra PowerShell en la raíz y ejecuta:

```powershell
.\install-status.ps1 -Watch
```

`INSTALL COMPLETO` significa que existen el servidor, el modelo y las
configuraciones de Pithagoras y Understory. Cierra ese monitor con `Ctrl+C`;
no detiene la instalación principal.

## Uso diario

```powershell
.\rinthel-boot.ps1
```

Para detener únicamente el daemon persistente:

```powershell
.\rinthel-boot.ps1 -Stop
```

El daemon queda en segundo plano cuando se cierra la TUI. En el siguiente uso
normal no es necesario repetir `INSTALL`: ejecuta `rinthel-boot.ps1` y usa
`BOOT` solamente cuando alguno de los tres servicios esté detenido.

Pithagoras queda en `http://127.0.0.1:4100`. En Windows, su contenedor se
comunica con `llama-server` mediante `host.docker.internal`; el instalador
registra el proveedor `local-llm` y monta su `models.json` como solo lectura.
Las contraseñas y tokens permanecen en los `.env` locales y nunca deben
añadirse al repositorio.

## Diagnóstico rápido

```powershell
python --version
cargo --version
cmake --version
nvcc --version
docker info
nvidia-smi
```

Si `docker info` falla, abre Docker Desktop y espera a que termine de
iniciar. Si `nvcc` no aparece, confirma que CUDA Toolkit agregó su carpeta
`bin` al `PATH` o define `CUDA_PATH`.

Usa PowerShell de 64 bits. El bootstrap rechaza explícitamente PowerShell
`(x86)`, porque los binarios, rutas y herramientas de compilación requeridos
son de 64 bits. Si la política bloquea los scripts, aplica solamente a la
terminal actual:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Si Pithagoras muestra `No API key found for openrouter`, confirma que
`llama-server`, Pithagoras y Understory estén `ONLINE` en `MONITOR`, y vuelve
a ejecutar `INSTALL` para reparar de forma idempotente el proveedor local sin
reemplazar secretos.
