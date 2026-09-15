# Troubleshooting

> [!NOTE]
> **"error: no se encontró .venv/bin/python"** al correr `rinthel-boot.sh` —
> no creaste el venv, o lo estás corriendo desde otro directorio. Creá el
> venv en la raíz del repo (ver `README.md` → Instalación).

> [!TIP]
> **Puerto ocupado** — BOOT no relanza `llama-server` si ya hay algo
> escuchando en `RINTHEL_LLAMA_PORT` (default `8080`); usa RELOAD o
> TERMINATE primero, o cambiá el puerto en `.env`.

> [!WARNING]
> **"llama-server murió al instante"** — casi siempre un flag inválido o el
> modelo/bin no existen de verdad; revisá el log en `RINTHEL_LLAMA_LOG_PATH`
> (default `logs/llama-server.log`).

> [!WARNING]
> **`CUDA error: out of memory` en el primer request real** (no al arrancar
> el server, sí en cuanto llega el primer prompt de tamaño normal) — casi
> siempre es la ventana de contexto (`-c`) o el expert-cache pidiendo más
> VRAM de la que hay libre. Ver
> [`02-hardware-optimization.md`](02-hardware-optimization.md) para el
> margen de seguridad de 900 MiB y qué flag bajar primero.

> [!NOTE]
> **Modelo/binario no encontrado** — la app avisa por stderr al arrancar
> pero no bloquea el menú; ajustá `RINTHEL_LLAMA_BIN`/`RINTHEL_LLAMA_MODEL_PATH`
> en `.env`.

> [!IMPORTANT]
> **Docker daemon inactivo** — la fase de BOOT lo detecta y corta con
> instrucciones (`sudo systemctl start docker`) antes de tocar nada más.
