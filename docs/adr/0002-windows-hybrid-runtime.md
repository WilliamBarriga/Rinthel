# Windows usa procesos nativos para el modelo y Docker Desktop para los portales

En Windows se decidió ejecutar el cliente, el daemon y `llama-server` de forma
nativa, mientras Understory y Pithagoras permanecen como contenedores Linux en
Docker Desktop. Esta frontera conserva CUDA y el acceso al sistema de archivos
del host sin portar dos aplicaciones web, a cambio de publicar sus puertos solo
en loopback y usar `host.docker.internal` para que Pithagoras alcance el modelo;
WSL completo y un despliegue exclusivamente nativo se descartaron porque
duplicaban capas o exigían reescribir componentes ya funcionales.
