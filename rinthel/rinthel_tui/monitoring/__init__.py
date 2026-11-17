"""Telemetría: los Telemetry streams de ``/ws/monitor`` (GPU/VRAM, CPU/RAM,
contenedores, el log de llama-server y el estado de los Local models y de los
managed services).

Forma de ADR 0004: ``domain/`` es el Monitor, el sobre ``{type, data}``, los
tipos de cada muestra y un puerto por fuente, sin importar infraestructura;
``adapters/`` los implementa sobre ``nvidia-smi``, psutil, ``docker compose``,
el filesystem y HTTP, y en memoria. ``create_app`` es el único que elige los
adapters; ``api/ws/`` solo sirve el flujo."""
