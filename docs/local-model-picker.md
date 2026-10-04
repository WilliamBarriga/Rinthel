# Selector de modelos locales (Ubuntu)

En el portal, abre un chat y pulsa el nombre del modelo junto al cuadro de mensajes. Elige Qwen 3.6 o Nemotron y espera a que termine la carga. No hace falta reinstalar ni cerrar el portal. El cambio se aplica a los chats locales de esta instalación; espera a que terminen las respuestas antes de cambiar.

El catálogo se guarda en `model-profiles.local.json` (rutas de esta máquina). El portal necesita `RINTHEL_DAEMON_URL` y comparte `PORTAL_SECRET` con el daemon. El servicio valida el secreto, permite únicamente perfiles del catálogo y rechaza archivos ausentes o demasiado pequeños. Si una carga falla, intenta restaurar el modelo anterior y no guarda el modelo fallido.

Después de instalar Ubuntu, copia `model-profiles.example.json` a
`model-profiles.local.json` y sustituye las rutas por tus archivos GGUF.
El archivo local y las copias de `.env` están ignorados por Git. Cada perfil
acepta parámetros de inferencia llama y caché MoE como strings, un nombre opcional
`RINTHEL_MODEL_NAME` y un mínimo opcional `RINTHEL_MODEL_MIN_BYTES`. El daemon
registra todos los modelos del catálogo en el proveedor local de Pi y conserva
los demás proveedores. También valida el encabezado GGUF antes de detener el
modelo actual. La comprobación de tamaño y encabezado no sustituye una carga
real ni verifica que la descarga esté completa; establece un mínimo apropiado
para cada archivo.

Los perfiles no cambian puertos, ejecutables, logs ni activación de servicios.
El daemon verifica el binario antes de detener el modelo y exige que el puerto
quede libre antes de iniciar su reemplazo. Si el servidor anterior no se
detiene, rechaza el cambio sin guardar la configuración nueva.

Para seleccionar offline, detén los servicios con TERMINATE y el daemon con
`./rinthel-boot.sh --stop`, y ejecuta `.venv/bin/python select-model.py <clave>`.
El script rechaza puertos activos, conserva una copia local del `.env` y
reutiliza el registro de proveedores y la escritura de configuración.

La implementación actual está integrada en el perfil Ubuntu de Rinthel normal. No cambia el despliegue Windows ni Rinthel Corp. El archivo Qwen incluye MTP; su aceleración permanece desactivada en el perfil local.
