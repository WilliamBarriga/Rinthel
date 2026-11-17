# ADRs

- [0001](0001-daemon-protocol-shape.md): protocolo daemon↔cliente: un WebSocket de telemetría y REST bloqueante para comandos.
- [0002](0002-windows-hybrid-runtime.md): Windows corre cliente, daemon y `llama-server` nativos, y los portales en Docker Desktop.
- [0004](0004-puertos-y-adaptadores.md): puertos y adaptadores: el dominio del daemon no conoce procesos, red ni Docker; `lifecycle` pone el host detrás de un `Host` de ocho puertos, `monitoring` un puerto por fuente, y la capa HTTP se compone por área.
- [0005](0005-politica-de-pruebas.md): política de pruebas: una prueba cruza el interface, no parchea privados, stdlib ni constantes; fallos y tiempo viven en el doble.
