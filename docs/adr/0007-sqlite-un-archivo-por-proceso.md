# SQLite: un archivo por proceso y borrado de usuario con `retire-sessions` antes

La Instance guarda su estado relacional en SQLite, **un archivo por proceso**. El daemon es dueño de `data/rinthel.db`, que solo tiene identidad (`users`, `refresh_tokens`). Deck es dueño de `data/deck/deck.db` (Sesiones, canvases, ajustes) y guarda el id de usuario como texto opaco, sin clave foránea: los dos archivos nunca se referencian.

Pesó que el daemon corre nativo en Windows y Deck en un contenedor Linux: un mismo archivo abierto desde los dos lados va contra los requisitos de bloqueo de SQLite. Una API interna para que Deck escriba a través del daemon lo haría depender del daemon en cada escritura.

## El archivo del daemon

- **Journal de rollback (`DELETE`), no WAL:** el Python de Windows trae una SQLite afectada por el bug de WAL-reset entre hilos, y solo el daemon abre este archivo.
- **Una conexión por operación**, autocommit explícito, `PRAGMA foreign_keys = ON` y `busy_timeout` al abrir (`rinthel/rinthel_tui/database.py`). Ninguna conexión se comparte entre hilos.
- **`BEGIN IMMEDIATE` en toda escritura.** `Identity.transaction()` toma el lock de escritura del archivo al empezar: la guarda de último admin cuenta los admins activos sin que otro escritor entre hasta el `COMMIT`.
- **Tablas `STRICT`.** SQLite menor a 3.37 hace fallar el arranque con un error claro.
- **Migraciones por `PRAGMA user_version`:** una tupla ordenada de scripts SQL, solo se agregan al final. Cada una corre con su cambio de versión en una sola transacción. Las aplica el arranque del daemon antes de armar la app, y también INSTALL y `reset-admin`. Un archivo con versión mayor que la que conoce el código hace fallar el arranque, sin escribir nada. Sin detección de deriva por checksum.
- **Sin `UnitOfWork` ni puerto de base de datos en el `Host`:** los casos de uso de usuarios usan `Identity.transaction()`.

## Borrar un usuario

El borrado cruza los dos archivos sin transacción común:

1. El daemon mira la guarda (a sí mismo, último admin) sin escribir nada.
2. Llama a Deck `POST /api/agent/retire-sessions` con el secreto de servicio y `X-Rinthel-User-Id`. Es idempotente.
3. Solo si Deck contestó, borra al usuario en una transacción propia (sus refresh tokens se van en cascada), con la guarda otra vez.

Si Deck falla (caído, 5xx o rechazo), el borrado aborta con 502 `sessions_not_retired` y un mensaje claro para el admin; el usuario sigue y el reintento termina el trabajo. Con Deck deshabilitado no hay Sesiones que retirar y el paso 2 se salta. Un fallo después del retiro deja al usuario vivo y sin Sesiones, que es un estado seguro.

## Consecuencias

- Cada puerto con estado tiene adapter SQLite y doble en memoria, y los dos pasan la misma suite de contrato sobre un archivo temporal (`rinthel/tests/identity/`, `rinthel/tests/database/`). Las pruebas HTTP del daemon corren `create_app` sobre una raíz temporal con `rinthel.db` real.
- Un dato que necesite atomicidad entre identidad y Deck no entra sin rever esta decisión.

## Opciones descartadas

- **Un archivo compartido:** daemon Windows nativo y contenedor Linux sobre el mismo archivo.
- **API interna (Deck escribe por el daemon):** Deck dependería del daemon en cada escritura.
- **WAL en el daemon:** el bug de WAL-reset del SQLite que trae Python en Windows.
