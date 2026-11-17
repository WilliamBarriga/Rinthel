# Deck

Deck es el portal web de la Instance: cada Usuario entra con su Panel token y trabaja con el Agente en sus Sesiones, que corren bajo el servidor aunque se cierre el navegador. Usuario, Admin, Miembro, Panel token e Instance están en [`rinthel/GLOSSARY.md`](../rinthel/GLOSSARY.md).

## Language

**Deck**:
El portal web de la Instance y su servidor: el managed service que aloja al Agente, guarda las Sesiones en `deck.db` y deja a cada Usuario entrar con su Panel token. Los usuarios y sus contraseñas son del daemon; Deck solo pregunta.
_Avoid_: Portal a secas, frontend, panel.

**Sesión**:
La unidad de trabajo de Deck: un directorio de trabajo, una conversación con el Agente y su historial de eventos. Es de uno de dos tipos: **tarea** (`task`, abierta sobre un workspace que elige su dueño) o **agente** (`agent`, el chat en la casa del Agente). Tiene un dueño, el Usuario que la abrió; la corrida la posee el servidor, no la pestaña del navegador.
_Avoid_: Chat, conversación a secas, Panel token (la sesión de login no es una Sesión).

**Agente**:
pi corriendo dentro de una Sesión de Deck, con las herramientas que el rol de su dueño le permite.
_Avoid_: Bot, asistente.

**Host de pi**:
El proceso Node de Deck, que aloja a pi y sirve el portal. Es dueño de las Sesiones y de `deck.db`; la identidad, el ciclo de vida y la ruta a los modelos son del daemon.
_Avoid_: Backend, servidor a secas.

**Credencial de servicio**:
Cómo el daemon habla con `/api` de Deck sin cookie: los encabezados `X-Rinthel-Service-Secret` y `X-Rinthel-User-Id`. Abre una sola ruta, `POST /api/agent/retire-sessions`, que el daemon llama antes de borrar a un Usuario: retira todas sus Sesiones, de los dos tipos, y es idempotente. Actúa como un Miembro con ese id, nunca Admin. Quien lleva el secreto se juzga solo por él (se descartan sus cookies) y todo lo que no despeje es un 401, igual que sin credencial.
_Avoid_: API key, token de servicio.

**Encuadre de staff**:
Lo que el Agente lee una sola vez, en el primer prompt de toda Sesión con dueño, sea `task` o `agent`: el nombre y el rol de su dueño, o, si escribe un Admin en una Sesión ajena, que la Sesión actúa por su dueño y el Admin solo supervisa. Informa al Agente; no calibra confianza.
_Avoid_: Encuadre de Grupo.

**Guard**:
La política que corre en toda Sesión, en cada resultado y cada llamada a una herramienta. Envuelve como no confiable lo que trae palabras ajenas (comandos de red en `bash` o `rinthel_host_exec`, MCP, el browser propio de la Sesión, la respuesta de un subagent) antes de que el modelo lo lea, y deja la Sesión contaminada. Decide solo, con reglas fijas, sin aprobaciones ni reglas por usuario. Cada llamada que revisa queda como evento `portal_guard` (`allow` o `deny`) en el historial de su Sesión; el transcript muestra los rechazos. No hay otro registro.
_Avoid_: Registro del Guard (ya no existe), filtro, sandbox (el Guard limita lo que hace un turno, no lo aísla del sistema).

**Sesión contaminada**:
Una Sesión que leyó palabras ajenas. Lo es para siempre: la marca se guarda en `deck.db` y sobrevive a relanzar la Sesión, reiniciar Deck o perder el archivo de pi; al arrancar, la Sesión cuenta como contaminada hasta que el Guard la reconstruye. Pierde del todo host-exec, `subagent` y la escritura en Memoria, y se le rechazan las formas peligrosas de una llamada (publicar, subir datos, programar trabajo, escribir en el PATH, leer credenciales, reescribir los archivos propios del Agente).
_Avoid_: Sesión sucia, taint a secas.

**Slot de la Sesión**:
El estado del Local model que Deck guarda por Sesión en el disco de `llama-server` (`data/deck/llama-slots`): se restaura antes de cada llamada al modelo y se guarda después, así volver a una Sesión no relee todo su historial. Es de un dueño, un Local model y una Sesión; se va con la Sesión y, pasado el tope de bytes, se borra el usado hace más tiempo.
_Avoid_: Caché de sesión, KV cache a secas.

**Canvas**:
Un documento que el Agente escribe para la persona dentro de una Sesión; la persona lo lee, lo descarga y no lo edita. Es de uno de dos tipos: `markdown` (texto) o `ui` (una interfaz armada con un catálogo cerrado de componentes: encabezados, texto, tablas, tarjetas, botones y campos de formulario). Vive en memoria hasta que se guarda en `deck.db`. En un `ui`, filtrar y rellenar campos es local al navegador; la única acción que sale es «preguntar al agente».
_Avoid_: Artefacto, página, documento a secas.

**Preguntar al agente** (`askAgent`):
La acción de un Canvas `ui` que deja un mensaje en la Sesión. El clic no inicia un turno: el Agente lo lee junto con el siguiente prompt de la persona.
_Avoid_: Llamar herramienta (un Canvas ya no ejecuta herramientas).

**SOUL de la Instance**:
El `SOUL.md` que dice quién es el Agente para todos los Miembros: sus Sesiones lo cargan como su SOUL, de solo lectura, y solo el Admin lo edita. INSTALL la siembra con una plantilla, porque una SOUL vacía deja al Agente sin identidad. El Admin conserva además un `SOUL.md` propio, en su casa del Agente, para sus Sesiones.
_Avoid_: SOUL global, SOUL de la empresa.

**Apariencia**:
Cómo se ve Deck: el estilo de distribución, la densidad, la lectura y los paneles, que cada Usuario elige y guarda (con hasta diez perfiles). La **Marca** (nombre, logo, paleta y tema base) es de toda la Instance y solo la cambia el Admin.
_Avoid_: Tema a secas, skin.
