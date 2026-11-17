# Reparto daemon / host de pi: Node es dueño de las Sesiones y del Guard, el daemon de la identidad, el ciclo de vida y las rutas

Deck no vive dentro del daemon: pi es un paquete Node, así que un runtime Node hay en cada Instance pase lo que pase. El proceso Node de Deck (el host de pi) tiene lo que está pegado a pi; el daemon tiene lo que es de la Instance entera. Pesó que llevar todo al daemon obligaba a reescribir las extensiones que dependen del SDK de pi, sin callback desde RPC, y que llevar todo a Node daba dos fuentes de verdad para la identidad.

## La regla

Va en **Node (el host de pi)** solo lo que:

- (a) tiene que correr dentro del proceso de pi o necesita su SDK;
- (b) depende de una librería del ecosistema JS/npm; o
- (c) toca directamente un recurso local que Node ya maneja (CDP del browser de la Instance, los workspaces).

Todo lo demás va en el **daemon**: identidad, ciclo de vida de los managed services y rutas a los modelos locales. Ante la duda, daemon. Node nunca es dueño de un dato que otro componente también necesite. Cada ticket nuevo que ponga algo en Node dice cuál de (a), (b) o (c) aplica.

## Reparto

| Función | Dueño | Regla |
| --- | --- | --- |
| pi (SDK) y sus extensiones inline: Guard, proveedor del Local model, host-exec, `subagent`, Memoria | Node | (a) |
| Sesiones, su historial de eventos (`events`), SSE con replay, canvases, slots por Sesión | Node (`deck.db`) | (a) |
| `SessionTaint` (la marca de Sesión contaminada) | Node (`deck.db`, tabla `session_taint`) | (a) |
| Executor `host` (el único) | Node | (a) |
| Usuarios, roles, Panel token | daemon (`rinthel.db`) | identidad |
| Ciclo de vida de los managed services, catálogo y Local model activo, ruta a los modelos | daemon | ciclo de vida |

## El Guard

- **Decide solo, en Node.** Corre en toda Sesión: el executor `container` salió y toda Sesión corre en `host`, con el Guard inline. Las reglas son fijas (`RULES`); no hay reglas por usuario ni aprobaciones puntuales.
- **Sin Registro.** El daemon no guarda los intentos y no hay ruta para hacerlo. Cada llamada que el Guard revisa queda como evento `portal_guard` (`allow` o `deny`) en el historial de su Sesión, en `deck.db`; el transcript muestra los rechazos. No hay vista que cruce Sesiones. La regla «bloquear si el registro no responde» desapareció con el Registro.
- **Taint persistido.** Leer palabras ajenas (comandos de red en `bash` o `rinthel_host_exec`, MCP, el browser propio, la respuesta de un subagent) contamina la Sesión para siempre: la marca va a `deck.db`, no al archivo de pi. Al arrancar el pi de una Sesión, el Guard la da por contaminada hasta reconstruirla desde la marca o, si no hay, desde todas las entradas del archivo de pi. Si la marca no se puede escribir, la Sesión en curso sigue contaminada; si no se puede leer, arranca contaminada.
- **Rama de taint antes de `RULES`.** Una Sesión contaminada pierde del todo `rinthel_host_exec`, su historial, `subagent` y la escritura en Memoria, sea cual sea el comando.

## Contratos entre los dos

- Node llama al daemon con la credencial de servicio y las policies por ruta ([ADR 0003](0003-policy-de-acceso-por-ruta.md)); el daemon llama a Node solo para `retire-sessions` ([ADR 0007](0007-sqlite-un-archivo-por-proceso.md)).
- Node llama directo a los modelos locales con la ruta que da el daemon ([ADR 0008](0008-deck-directo-a-los-modelos-locales.md)).
- Cada proceso tiene su archivo SQLite y sus migraciones; nada del Guard ni de las Sesiones vive en `rinthel.db`.

## Consecuencias

- `SessionTaint` tiene puerto en el `PortalStore` y su suite de contrato contra SQLite y el doble en memoria.
- Un dato que el daemon necesite de una Sesión (por ejemplo, saber si está contaminada) se pide a Deck; no se copia.

## Opciones descartadas

- **Registro del Guard en el daemon:** duplicaba en el daemon lo que el historial de la Sesión ya guarda, y volvía al daemon una dependencia de cada llamada a herramienta.
- **Taint en memoria:** relanzar la Sesión o reiniciar Deck la dejaba limpia.
- **Taint solo en el archivo de pi:** un archivo de pi perdido dejaba la Sesión limpia.
- **Todo en el daemon / todo en Node:** reescribir las extensiones del SDK, o dos fuentes de verdad para la identidad.
