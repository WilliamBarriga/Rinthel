# Validación de Rinthel en Windows

Este documento registra el punto reproducible alcanzado el 2026-09-20. No es
una promesa de rendimiento para cualquier PC: es evidencia de una máquina,
un modelo y un perfil concretos.

## Máquina de referencia

| Componente | Valor observado |
|---|---|
| Sistema | Windows 11, PowerShell de 64 bits, Docker Desktop con contenedores Linux |
| CPU | AMD Ryzen 7 260, 8 núcleos / 16 hilos |
| RAM visible | 31.31 GiB |
| GPU | NVIDIA GeForce RTX 5070 Laptop GPU |
| VRAM | 8151 MiB |
| NPU | AMD XDNA, hasta 16 TOPS, detectada pero no usada por `llama.cpp` CUDA |
| Modelo | Qwen3.6-35B-A3B UD-Q4_K_XL, 21.28 GiB |

La configuración exacta está en
[`02-hardware-optimization.md`](02-hardware-optimization.md). Los archivos
locales viven por defecto bajo `%USERPROFILE%\Rinthel-data`; ninguna ruta de
usuario, contraseña ni token forma parte del repositorio.

## Arquitectura validada

- Cliente Ratatui, daemon FastAPI y `llama-server.exe`: procesos nativos de
  Windows.
- Understory y Pithagoras: contenedores Linux en Docker Desktop.
- `llama-server`: `127.0.0.1:8080` en el host.
- Understory: `127.0.0.1:3800`.
- Pithagoras: `127.0.0.1:4100`.
- Pithagoras alcanza el modelo mediante
  `http://host.docker.internal:8080/v1` y el proveedor `local-llm`.

El adaptador de Windows reemplaza `network_mode: host` por un puerto publicado
en loopback, prepara permisos persistentes de `/data`, hace opcional
`TS_AUTHKEY` y conserva los secretos existentes. Estas transformaciones son
idempotentes.

## Problemas resueltos

1. Rechazo temprano de PowerShell x86 y detección robusta de Python 3.13.
2. Descubrimiento de CMake instalado con Visual Studio y de CUDA mediante
   `CUDA_PATH` o las rutas estándar.
3. Compilación multi-configuración de `llama.cpp` en `Release` y localización
   correcta de `llama-server.exe`.
4. Arranque persistente del daemon con pidfile, ventana oculta y logs locales.
5. Terminación multiplataforma de servicios por puerto mediante `psutil`.
6. Comprobación de Docker Desktop con `docker info`, sin depender de
   `systemctl`.
7. Transporte WebSocket declarado como dependencia de runtime.
8. Proveedor local de Pithagoras conectado al modelo del host, eliminando la
   dependencia accidental de OpenRouter.
9. Monitor independiente `install-status.ps1` para compilación, descarga y
   finalización.

## Rendimiento observado

Se realizaron cinco consultas documentales y una corrección de guardrails en
una sesión de Pithagoras. El contexto acumulado llegó a 15,526 tokens sin error
de CUDA ni pérdida del documento.

| Prueba | Salida | Tiempo | Velocidad aproximada | Calidad revisada |
|---|---:|---:|---:|---:|
| Lectura y resumen | 878 tokens | 28.1 s | 32.6 tok/s | 9/10 |
| Catálogo y precios | 1031 tokens | 31.0 s | 33.2 tok/s | 8.5/10 |
| Datos ausentes y márgenes | 866 tokens | 26.4 s | 32.8 tok/s | 10/10 |
| Respuesta comercial | 1282 tokens | 40.5 s | 31.7 tok/s | 9.5/10 |
| Vigencia y contradicciones | 1349 tokens | 42.5 s | 31.7 tok/s | 9/10 |
| Corrección con guardrail | 1828 tokens | 55.6 s | 32.9 tok/s | 10/10 |

Promedio revisado: 9.3/10 de calidad y aproximadamente 32.5 tokens/s. La
calidad es una evaluación humana de estas pruebas, no una métrica universal.

### Carga controlada

Una generación directa de 420 tokens tomó 13.994 s (30.0 tok/s), con doce
muestras de hardware:

| Recurso | Promedio | Pico o mínimo relevante |
|---|---:|---:|
| CPU | 59.5% | 74.5% pico |
| RAM usada | 29.47 GiB | 29.57 GiB pico; 1.74 GiB libre mínimo |
| Working set de `llama-server` | — | 17.03 GiB pico |
| GPU | 39.9% | 81% pico |
| VRAM usada | 7341 MiB | 551 MiB libre mínimo |
| Temperatura GPU | — | 58 C pico |
| Potencia GPU | — | 45.04 W pico |

La NPU aparece como `NPU Compute Accelerator Device`, pero este servidor se
compiló con CUDA y no le asigna trabajo. Sus 16 TOPS no se suman a la VRAM ni
a la capacidad CUDA.

## Casos de uso validados

- Consulta de una base de conocimiento local con citas de sección.
- Recuperación de catálogo, precios, estados y datos históricos.
- Rechazo de cálculos cuando faltan costos o variables.
- Borradores comerciales sin inventar envío, tiempos ni condiciones.
- Detección de contradicciones entre precios vigentes e históricos.
- Separación de catálogo activo, validación, experimento y propuesta.

El mismo patrón puede aplicarse a una pyme, una operación de movilidad laboral
o un estudio jurídico: cada organización mantiene su propio knowledge
workspace y sus reglas. En dominios legales o migratorios, las respuestas son
apoyo documental y requieren revisión profesional; no sustituyen asesoría
jurídica ni una decisión oficial.

## Guardrail recomendado

```text
No conviertas inferencias en hechos confirmados.

Distingue siempre entre:
- Catálogo formal.
- Producto en validación.
- Concepto experimental.
- Información histórica.
- Información no documentada.
- Propuesta o recomendación creada por ti.

Si una acción parece razonable pero no está expresamente indicada en la base
de conocimiento, identifícala como “Propuesta”, no como política vigente.
```

La prueba posterior demostró que este guardrail corrigió una inferencia previa
sobre el canal para cotizaciones de envío y la convirtió explícitamente en una
propuesta.

## Límites pendientes

- No se ha llenado ni validado el contexto completo de 65,536 tokens.
- El margen de RAM y VRAM es reducido; aumentar contexto, batch, MTP o cache de
  expertos requiere un benchmark aislado.
- Una respuesta fluida puede contener una inferencia incorrecta. Los flujos que
  prometen precios, logística, requisitos legales o acciones externas deben
  conservar revisión humana.
