# Deck va directo a los modelos locales; el daemon solo da la ruta y los slots viven en Deck

La Instance tiene un Local model activo por Capability (`llm`, `stt`, `tts`), compartido por todas las Sesiones; solo el admin lo cambia. El daemon es dueño del catálogo, del modelo activo y del managed service que lo sirve. Deck es dueño de las Sesiones y de lo que pasa en cada llamada al modelo.

Pesó que un passthrough en el daemon obligaba a un Audit de modelos que quedó fuera de alcance, sumaba un salto de red en cada token y partía en dos procesos la lógica de una llamada (slots, progreso, cambio de modelo).

## La ruta

- `GET /model-provider/routing` (policy `service`) devuelve, por Capability con un Local model que puede correr, `url` (armada con `deck.host_address` y el puerto del managed service), `model`, `context_window` y `reasoning_format`. Sin usuario: un modelo por Instance.
- El `SessionProxy` de Deck da a cada Sesión una URL propia no adivinable en loopback; el pi de la Sesión llama ahí con una clave ficticia. En **cada llamada** el proxy vuelve a leer la ruta y reenvía directo a `llama-server`, pidiendo `return_progress` para mostrar el avance del prefill.
- La ventana de contexto con la que pi planifica la compactación viene de la ruta, no de una constante. El formato de razonamiento también.

## El cambio de Local model

- El admin cambia el modelo desde Deck (composer y ajustes). Deck rechaza con `409 turns_in_flight` mientras alguna de sus Sesiones está generando; si no, reenvía a `POST /models/activate`, que corre el cambio (kill, spawn, ready, rollback) bajo el lock global del lifecycle y puede rechazar con su propio `409` (`lifecycle_busy`, `turns_in_flight` si `llama-server` está procesando).
- Una Sesión se entera en su llamada siguiente: la ruta trae otro `model`, el proxy contesta `409 wrong_model` y pasa la Sesión a la ruta nueva; el proveedor de pi cambia de modelo (`setModel`, el historial es de pi) y reintenta el turno una vez, como un solo turno.
- Sin Local model activo la llamada es `503` con el motivo.

## Los slots

- `llama-server` arranca con `--slot-save-path data/deck/llama-slots`, fuera del Validated profile (no toca valores de inferencia). Deck ve ese directorio en su volumen.
- Antes de cada llamada el proxy restaura el slot de la Sesión (`POST /slots/0?action=restore`) y, si la llamada terminó bien, lo guarda (`action=save`). El nombre es un hash de dueño + Sesión y otro del modelo: la misma Sesión de otro dueño u otro modelo es otro slot, y borrar la Sesión borra los de todos sus modelos.
- **El lock es por petición HTTP, no por turno de agente.** Un subagent comparte el `Model` y la URL de su padre, y llama en medio del turno del padre: con el lock por turno el hijo esperaría al padre para siempre. Se acepta que el hijo pise el slot del padre.
- Los slots guardados tienen tope de bytes (`DECK_SLOTS_MAX_GB`): al pasarse se borran los usados hace más tiempo, nunca el recién guardado. Un fallo del caché nunca falla la llamada: el turno hace el prefill entero.

## Consecuencias

- El daemon no tiene `SessionSlots`, `SlotStore`, passthrough ni `DELETE /model-provider/sessions/:id/slot`.
- La voz (`stt`, `tts`, solo Linux) sigue el mismo camino: ruta del daemon, llamada directa desde Deck al managed service (`whisper-server`, `audiocpp-server`). El cambio y el apagado (`POST /models/off`) usan el mismo lock global.
- Las pruebas del server de Deck corren el proxy contra un `llama-server` falso por HTTP real y un daemon falso; la del cliente de pi, contra los mismos (`deck/tests/session-proxy.test.mts`, `deck/tests/chat.test.mts`).

## Opciones descartadas

- **Passthrough en el daemon:** exigía Audit de modelos y un salto extra por token.
- **Que cada Sesión elija su modelo:** varios modelos a la vez no entran en la memoria del hardware de referencia; uno por Instance alcanza.
- **Lock por turno de agente:** bloquea al subagent detrás de su padre.
