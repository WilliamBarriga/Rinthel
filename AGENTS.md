# AGENTS.md — Rinthel-general

> Instrucciones para el CLI `pi` en este repo — tanto corriendo directo en
> el host como cuando lo levanta Pithagoras (mismo agente, mismo skill).
> graphify ya está instalado como skill de proyecto
> (`.pi/agent/skills/graphify/`, via `graphify pi install --project`).

## Graphify en este repo

`graphify-out/graph.json` ya existe (construido por Claude Code). Tratar
cualquier pregunta de arquitectura o relaciones del código como una query a
ese grafo primero (`graphify query "..."`), no como exploración manual
archivo por archivo.

**Permitido:**
- `graphify query "..."`, `graphify query "..." --dfs`, `graphify path "A" "B"`, `graphify explain "X"`
- `graphify update .` — refresco incremental, solo AST, sin costo LLM.
  Correr después de que `pi` edite código acá, para que el grafo no quede
  desactualizado.

**No permitido sin confirmación explícita del usuario:**
- `graphify extract`, `graphify cluster-only`, o el pipeline completo
  `/graphify` — reconstruyen clusters y renombran comunidades (gastan LLM
  y pueden pisar `.graphify_labels.json` ya curado). Esa tarea sigue
  siendo de una sesión de Claude Code, mismo patrón que ya establece
  `~/CodeBase/AGENTS.md` para el resto del workspace.

Regla general heredada de `~/CodeBase/AGENTS.md`: cambios que tocan varios
archivos o requieren entender la arquitectura completa del repo siguen
siendo tarea de Claude Code, no de `pi`.

## Archify en este repo

CLI en `/workspaces/archify-pkg/archify/bin/archify.mjs`. Para mapear
arquitectura de un repo: generar JSON IR con los componentes y conexiones,
validar con `archify validate`, renderizar con `archify render`.

**Comandos basicos:**
- `archify validate <type> <input.json>` — validacion schema + layout
- `archify inspect <type> <input.json>` — ver JSON parseado con rutas
- `archify render <type> <input.json> [output.html]` — genera HTML interactivo
- `archify compare architecture <base.json> <head.json>` — diff entre snapshots
- `archify check <output.html>` — valida un HTML ya generado

**Tipos de diagrama:** architecture, workflow, sequence, dataflow, lifecycle

**No permitido sin confirmacion explicita del usuario:**
- `archify compare` en repos grandes (genera diff pesado con LLM)
- Generar JSON IR manualmente para repos > 50 archivos (mejor usar graphify primero)

**Flujo tipico:**
1. Usar `graphify query` para entender la arquitectura del repo
2. Generar JSON IR con los componentes clave (no todos, solo los relevantes)
3. `archify validate` → `archify render` → HTML interactivo
