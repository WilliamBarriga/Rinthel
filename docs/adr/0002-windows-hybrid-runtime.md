# Windows usa procesos nativos para el modelo y Docker Desktop en bridge para Deck

En Windows el cliente, el daemon y `llama-server` corren nativos, y Deck y
Understory como contenedores Linux en Docker Desktop. Esta frontera conserva
CUDA y el acceso al sistema de archivos del host sin portar dos aplicaciones
web; WSL completo y un despliegue exclusivamente nativo se descartaron porque
duplicaban capas o exigían reescribir componentes ya funcionales.

Deck no usa la red de host en Windows: la de Docker Desktop exige opt-in,
cuenta iniciada y no funciona con Enhanced Container Isolation
(https://docs.docker.com/engine/network/drivers/host/). Corre en bridge, con su
puerto publicado solo en `127.0.0.1`, y llega al daemon y a `llama-server` por
`host.docker.internal`, el camino validado. La diferencia con Linux vive en un
override trackeado, `compose/windows.override.yaml`, que INSTALL elige con
`COMPOSE_FILE` en el `.env` raíz; no hay parcheo textual del compose. El
override también pone `deck.db` en `DELETE`, quita `PUID`/`PGID`/`DOCKER_GID` y
une Deck a dos redes de usuario: la de Understory (`understory:3800`) y la del
browser de la Instance (`deck-browser`, CDP y vista por nombre de contenedor).

Toda URL que el daemon entrega a Deck (llama, voz, hostexecd) se arma con
`deck.host_address`, cuyo default depende de la Platform (`127.0.0.1` en Linux,
`host.docker.internal` en Windows); Deck nunca reescribe URLs. La excepción es
Understory, que en Windows va por nombre en la red compartida. Voz, host-exec
y tailscale son solo de Linux.

El argv de `llama-server` del Validated profile no cambia con Deck: el cambio
es del cliente, no de la inferencia, así que no pide benchmark nuevo; cualquier
cambio de ese argv sí lo pide.
