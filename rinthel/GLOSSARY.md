# Rinthel

Rinthel administra una infraestructura local de IA como un conjunto coordinado de servicios. Su lenguaje distingue las intenciones del usuario de los mecanismos concretos con los que cada servicio se ejecuta.

## Language

**Managed service**:
Una capacidad de infraestructura que Rinthel controla como una sola unidad de ciclo de vida: Llama, Understory, Deck o Pithagoras.
_Avoid_: Proceso, contenedor; son mecanismos de ejecución, no la capacidad administrada.

**Install**:
Preparación idempotente de las fuentes, binarios, modelos y configuración que una managed service necesita antes de poder arrancar.
_Avoid_: Boot, setup manual.

**Boot** / **Terminate**:
Intenciones opuestas del ciclo de vida: Boot lleva las managed services habilitadas a estado disponible; Terminate intenta llevarlas a estado detenido.
_Avoid_: Start/stop, up/down.

**Reload**:
Reemplazo coordinado del estado en ejecución mediante Terminate seguido de Boot y reconstrucción de los servicios que lo requieran.
_Avoid_: Restart; Reload expresa el ciclo completo administrado por Rinthel.

**Lifecycle plan**:
Lo que corre un comando de ciclo de vida entero (Install, Boot, Terminate, Reload): tandas ordenadas de unidades, una por managed service, y una política de fallo que dice si corta en la primera unidad que falla o sigue con las que quedan.
_Avoid_: Script, secuencia de fases.

**Instance**:
Una instalación de Rinthel: su raíz, el `.env` único que es fuente de verdad de su configuración y sus secretos, y los directorios `data/` y `logs/`.
_Avoid_: Repo, checkout, despliegue.

**Service outcome**:
Resultado de una managed service dentro de una operación de ciclo de vida: indica éxito o fallo y aporta un mensaje comprensible para la persona usuaria.

**Telemetry stream**:
Flujo identificado de observaciones en vivo sobre servicios, recursos o actividad durante una operación.
_Avoid_: Evento, actualización; cada stream conserva una identidad y significado propios.

**Knowledge workspace**:
Carpeta controlada por la persona usuaria que Pithagoras expone al agente como fuente documental local.
_Avoid_: Entrenamiento, índice RAG; el agente consulta archivos, no modifica los pesos del modelo.

**Grounded response**:
Respuesta limitada a fuentes del knowledge workspace que separa hechos confirmados, históricos, experimentos, propuestas e información ausente.
_Avoid_: Respuesta creativa, conocimiento general.

**Validated profile**:
Combinación versionada de modelo y parámetros que conserva estabilidad y rendimiento medidos en una clase concreta de hardware. Hay a lo sumo uno por Platform.
_Avoid_: Valor por defecto, configuración universal.

**Platform**:
El sistema anfitrión en el que corre la Instance: Linux o Windows. Decide qué managed services se pueden habilitar y qué Validated profile aplica.
_Avoid_: Perfil (es Validated profile), entorno, OS.

**Capability**:
Tipo de trabajo que la Instance sirve con un modelo: generar texto, transcribir voz o sintetizar voz. Cada Capability tiene a lo sumo un modelo activo a la vez.
_Avoid_: Tarea, rol, proveedor.

**Local model**:
Modelo declarado en el catálogo de la Instance que puede servir una Capability. El admin elige cuál está activo, y ese modelo lo comparten todas las Sesiones.
_Avoid_: Perfil (es Validated profile), proveedor.

**Instance browser**:
El único browser que maneja el Agente. Hay uno por Instance, lo administra el Admin y solo lo usan las Sesiones de un Admin, compartido entre ellas.
_Avoid_: Browser personal, browser del agente.

**Usuario**:
Una persona con cuenta en la Instance: nombre de usuario, contraseña y un rol, `admin` o `miembro`. Vive en `rinthel.db`, el archivo del daemon. Puede estar deshabilitado: no entra, y sus Panel tokens dejan de servir.
_Avoid_: Cuenta, cliente, operador (el operador usa la TUI con el secreto de servicio, sin usuario).

**Admin**:
Usuario con rol `admin`. Administra a los demás usuarios desde Deck (crear, editar, deshabilitar, borrar, cambiar contraseñas, incluida la propia). La Instance nunca queda sin un Admin activo, y un Admin no puede deshabilitarse, borrarse ni quitarse el rol a sí mismo. El primero lo crea INSTALL; si se pierde su contraseña, `reset-admin` por CLI local es la única recuperación.
_Avoid_: Root, superusuario, dueño.

**Miembro**:
Usuario con rol `miembro`. Trabaja en sus propias Sesiones de Deck y no administra usuarios ni edita su propia cuenta.
_Avoid_: Usuario común, invitado, staff.

**Panel token**:
La credencial con que un Usuario entra a Deck: un access token (JWT firmado con `RINTHEL_PANEL_SECRET`, dura un día) y un refresh token que rota en cada uso (dura 30 días; se guarda solo su hash). Logout y deshabilitar al Usuario revocan los refresh. El token no es la autoridad: el rol y si el Usuario sigue activo se leen de `rinthel.db` en cada request.
_Avoid_: Sesión (es una conversación con el Agente), cookie, API key.
