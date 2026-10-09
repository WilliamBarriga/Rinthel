# Orden de integración de los PR de runtime

Estado preparado el 2026-10-03. `main` conserva el árbol anterior a la
adaptación Windows, mediante el revert del PR #2; no se reescribió historial.

| PR | Rama | Base para revisión | Alcance |
|---|---|---|---|
| #1 | feature/rinthel-host-exec | main | Host exec y sus correcciones |
| #3 | feature/windows-runtime | main | Runtime Windows y perfiles por plataforma |
| #5 | fix/ubuntu-26-04 | feature/windows-runtime | Bootstrap y Compose Ubuntu |
| #6 | feature/local-model-picker | fix/ubuntu-26-04 | Selector local Ubuntu |

Las bases apiladas muestran solo el cambio de cada trabajo. Al integrar un
padre en `main`, cambia la base del siguiente PR a `main` antes de integrarlo.
Así cada funcionalidad conserva su PR y su revisión. El PR #4 ya quedó
incorporado en la rama del #1; no fue un merge a `main`.

## Secuencia

1. WilliamBarriga revisa #1 y decide su integración. Es el autor de ese PR,
   por lo que GitHub no permite solicitarle una aprobación formal sobre su
   propio PR. La revisión de #5 y #6 sí está solicitada a WilliamBarriga.
2. Actualiza la rama Windows con `main` después de integrar #1. Conserva
   los dos flujos del instalador: reparación del proveedor Windows y
   aprovisionamiento del token host exec, incluyendo instalaciones existentes.
   Valida Windows nativo antes de completar #3, que permanece en borrador.
3. Tras integrar #3, cambia la base de #5 a `main` y sincroniza su rama.
   Conserva el parser dotenv del lanzador con soporte tanto para el puerto
   del daemon como para el de hostexecd. El perfil Ubuntu detecta el overlay
   de host exec cuando ambos módulos están presentes.
4. Tras integrar #5, cambia la base de #6 a `main` y sincroniza su rama.
   Conserva los errores del picker existente junto con el nuevo selector
   local y la configuración aislada de los tests MTP.
5. Elimina las ramas de cada PR únicamente después de su integración y de
   verificar que sus commits quedaron accesibles en la rama destino.

## Resoluciones ya probadas en un checkout aislado

- `rinthel_tui/lifecycle/install.py`: el `.env` existente conserva secretos;
  Windows actualiza su proveedor; el token host exec se prepara sin un
  retorno anticipado que omita esa preparación. Ubuntu reutiliza su perfil.
- `rinthel-boot.sh`: el parser dotenv recibe el nombre de variable y el
  valor por defecto para ambos daemons, validando el rango del puerto.
- `tests/lifecycle/test_install.py`: se aíslan `REPO_ROOT` y `COMPOSE_FILE`
  y se conservan las regresiones de ambas funcionalidades.
- `pithagoras/web/src/components/ComposerBar.tsx`: se mantienen `pickError`
  y `hasLocalPicker`, la limpieza del error al abrir el picker y la selección
  del botón correspondiente.
- `tests/daemon/test_config_endpoint.py`: el snapshot incluye archivos
  temporales de modelo/binario y el estado MTP controlado por el test.

El checkout combinado pasó 227 pruebas Python, build de servidor/frontend,
tests del portal y sintaxis Bash. Compose confirmó el token compartido y el
montaje explícito de solo lectura de la extensión en el perfil Ubuntu.
Las revisiones independientes Standards y Spec no dejaron bloqueos pendientes.

## Validación pendiente

Estos resultados se obtuvieron en Linux. No sustituyen una instalación nueva
con Docker ni una carga real en GPU. Windows requiere ejecutar sus scripts y
comprobar INSTALL, BOOT y MONITOR en el equipo de referencia. El selector
requiere una prueba real de cambio y restauración de modelos en Ubuntu.
No se cambiaron las mediciones ni los valores validados del perfil Windows.
