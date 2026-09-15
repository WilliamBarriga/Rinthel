# Hardware & Inference Tuning

Por qué los flags de `llama-server` en `.env.example` valen lo que valen.
Todos parten de la misma restricción: el modelo (35B parámetros totales, ~23
GB en disco cuantizado) no entra completo en la VRAM disponible. Cada flag de
esta lista existe para exprimir velocidad sin cruzar el margen de seguridad
de VRAM — no son defaults arbitrarios de `llama.cpp`, son el resultado de
tuning empírico contra este hardware puntual.

Hardware de referencia: GPU NVIDIA de 8 GB VRAM, CPU de 8 núcleos físicos,
~32 GB RAM. Si tu GPU tiene más VRAM, gran parte de este tuning (`--n-cpu-moe`
sobre todo) se puede relajar — ver la sección de cada flag.

## El umbral de seguridad: 900 MiB de VRAM libre

Regla que gobierna casi todas las decisiones de abajo: bajo carga real, hay
que mantener **al menos 900 MiB de VRAM libre**. Por debajo de eso, el
overflow a memoria compartida vía PCIe es silencioso — no hay error en el
log, solo una caída de tokens/segundo que parece un problema de otro lado.
Cada flag que toca VRAM se midió contra este piso.

## Modelo y cuantización

**Qwen3.6-35B-A3B-MTP**, quant `UD-Q4_K_XL` (unsloth, 22.85 GB en disco).
MoE de 35B parámetros totales / 3B activos por token, 256 expertos,
arquitectura híbrida (Gated DeltaNet + atención — solo 10 de 40 capas usan
atención con KV cache tradicional, el resto es atención lineal), contexto
nativo 262144. La quant `UD-Q4_K_XL` es la que unsloth recomienda para
setups de ~24 GB de VRAM+RAM combinados; es el punto donde el modelo entra
en este hardware sin degradar demasiado la calidad de salida.

## `--n-cpu-moe 60` — split GPU/CPU de los expertos MoE

Cuántas capas de expertos corren en CPU en vez de GPU. Bajar el número mueve
más cómputo a GPU (prefill más rápido) pero sube el uso de VRAM: en 8 GB, el
techo real lo pone la VRAM libre bajo carga, no la velocidad de cómputo. `60`
es el valor estable con el expert-cache activo (siguiente sección) y
contexto de `131072` sin quedarse sin memoria. Con más VRAM disponible, este
número se puede bajar para ganar velocidad de prefill.

## `--spec-type none` — MTP apagado

El gguf trae MTP (multi-token prediction, decodificación especulativa)
horneado, pero encenderlo (`--spec-type draft-mtp`) reproduce un **OOM real
bajo sesión larga** en este hardware — confirmado reproducible, no un
fantasma de una corrida puntual. MTP en `llama.cpp` tiene además dos
limitaciones propias, aparte del OOM: no soporta `--parallel` > 1 ni
`--mmproj`. Se deja apagado hasta tener margen de VRAM de sobra para
sostenerlo en sesiones largas.

## Expert cache (`--moe-cache-profile` + `--moe-cache-slots 16`)

Un perfil de ruteo MoE (qué expertos se activan más seguido, capturado de
antemano corriendo el modelo con carga real) usado para mantener esos
expertos precargados y "calientes" en VRAM en vez de recargarlos por
request. Con 16 slots: **+121% de velocidad de prefill** (prompt tokens/s)
a costa de dejar la VRAM libre mínima bajo carga real en **~308 MiB** — por
debajo del umbral de seguridad de 900 MiB de arriba. Es un trade-off
aceptado a propósito por la ganancia de velocidad, no un descuido: implica
que no hay margen para una sesión más agresiva o un contexto más largo que
los ya probados. Si algo empieza a fallar con `CUDA error: out of memory`
bajo uso normal, este es el primer sospechoso — bajar `--moe-cache-slots` o
subir `--n-cpu-moe` recupera margen a costa de velocidad.

## `-c 131072` — ventana de contexto

El contexto nativo del modelo es 262144, pero a ese tamaño no entra en VRAM
junto con el resto de esta config. `131072` es el techo probado estable con
el expert-cache activo — subirlo sin bajar `--n-cpu-moe` o desactivar el
cache va a terminar en el mismo OOM del umbral de arriba.

## `--threads 8` / `--threads-batch 7`

Pensado para una CPU de 8 núcleos físicos: `--threads` usa los 8 para
generación, `--threads-batch` se deja en 7 durante el prefill batched para
no saturar el núcleo que también sostiene el resto del sistema (Docker
stacks, la TUI, etc.) mientras el modelo procesa el prompt.

## `--no-sched-async-cpu`

Desactiva el scheduling asíncrono de CPU de `llama.cpp`. Forma parte de la
config vigente verificada en producción; su aporte aislado a la velocidad no
está medido con precisión (se descartó como explicación de otra brecha de
VRAM entre builds, pero eso no confirma ni descarta un efecto propio). No
tocar sin volver a medir antes/después.

## Si tenés más VRAM que 8 GB

El orden de prioridad para relajar este tuning: subir `--n-cpu-moe` menos
agresivo primero (más capas a GPU, gana prefill), después evaluar prender
`--spec-type draft-mtp` (gana velocidad de generación, pero solo si hay
margen de sobra para sesiones largas), y recién al final subir
`--moe-cache-slots` más allá de 16 (gana prefill adicional, cuesta VRAM
directo). Cambiar más de uno a la vez hace imposible saber cuál causó qué si
algo empieza a fallar.
