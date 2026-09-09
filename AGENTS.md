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
