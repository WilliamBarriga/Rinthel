# Rinthel

Rinthel administra una infraestructura local de IA como un conjunto coordinado de servicios. Su lenguaje distingue las intenciones del usuario de los mecanismos concretos con los que cada servicio se ejecuta.

## Language

**Managed service**:
Una capacidad de infraestructura que Rinthel controla como una sola unidad de ciclo de vida: Llama, Understory o Pithagoras.
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
Combinación versionada de modelo y parámetros que conserva estabilidad y rendimiento medidos en una clase concreta de hardware.
_Avoid_: Valor por defecto, configuración universal.
