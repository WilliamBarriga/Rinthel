# Deck

Deck es el portal web de la Instance: cada Usuario entra con su Panel token y trabaja con el Agente en sus Sesiones, que corren bajo el servidor aunque se cierre el navegador. Usuario, Admin, Miembro, Panel token e Instance están en [`rinthel/GLOSSARY.md`](../rinthel/GLOSSARY.md).

## Language

**Deck**:
El portal web de la Instance y su servidor: el managed service que aloja al Agente, guarda las Sesiones en `deck.db` y deja a cada Usuario entrar con su Panel token. Los usuarios y sus contraseñas son del daemon; Deck solo pregunta.
_Avoid_: Portal a secas (lo era el portal heredado), frontend, panel.

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
