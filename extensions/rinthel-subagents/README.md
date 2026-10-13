# rinthel-subagents (Pithagoras)

Tool `subagent`, siempre en serie. Un subagente = una AgentSession en el mismo proceso.

| Archivo | Rol |
|---|---|
| `index.ts` | entrada: registra la tool |
| `tool.ts` | la tool y sus 3 modos (single / chain / tasks) |
| `runner.ts` | corre un subagente (lock, timeout, maxTurns, tools excluidas) |
| `agents.ts` | carga `agents/*.md` (luego `~/.pi/agent/agents`, luego `.pi/agents`) |
| `skills.ts` | busca skills por nombre |
| `agents/` | scout, planner, researcher, worker, reviewer, debugger, builder, writer, custom |

Frontmatter de un agent: `name, description, tools, thinking, skills, timeout, maxTurns`.
Minimos forzados en codigo (modelo local lento): `timeout` >= 1200 s (20 min), `maxTurns` >= 60.
Skills: `skills` en la llamada, por item o en el frontmatter; se cargan bajo demanda (`inlineSkills: true` pega el SKILL.md).
`persona` adapta un agent (p. ej. `custom`). Sin sub-subagentes. Sin escritura a Understory.
Instalar en terminal: ruta del directorio en `packages` de settings.json.
Pithagoras: `RINTHEL_SUBAGENTS_EXTENSION` (lo monta `compose/*host-exec.override.yaml`); el portal la pasa al resource loader.
Seguridad: la sesion hija no carga el guard del portal. Por eso excluye `rinthel_host_exec`, escritura a Understory y `ask_user_question`, `custom` no tiene write/edit, y la salida del subagente cuenta como no confiable (taint) en la sesion padre.
