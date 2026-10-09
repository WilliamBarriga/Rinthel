# AGENTS.md — Rinthel-general

> Instructions for the `pi` CLI in this repo — both running directly on
> the host and when Pithagoras launches it (same agent, same skill).
> graphify is already installed as a project skill
> (`.pi/agent/skills/graphify/`, via `graphify pi install --project`).

## Graphify in this repo

`graphify-out/graph.json` already exists. Treat any question about
architecture or code relationships as a query against that graph first
(`graphify query "..."`), not as manual file-by-file exploration.

**Allowed:**
- `graphify query "..."`, `graphify query "..." --dfs`, `graphify path "A" "B"`, `graphify explain "X"`
- `graphify update .` — incremental refresh, AST-only, no LLM cost. Run
  this after `pi` edits code here, so the graph doesn't go stale.

**Not allowed without explicit user confirmation:**
- `graphify extract`, `graphify cluster-only`, or the full `/graphify`
  pipeline — these rebuild clusters and rename communities (spend LLM
  budget and can overwrite the already-curated `.graphify_labels.json`).

## Windows runtime

For changes to Windows installation, Docker Desktop networking, the local
model provider, or inference tuning, read `docs/04-windows-installation.md`
and `docs/05-windows-validation.md` first. Preserve the validated Windows
profile unless the change includes a new benchmark on the reference hardware;
record new measurements in the validation document and keep machine-local
paths, passwords, tokens, and `.env` files out of Git.

## Understory (MCP Memory) — Tool Usage

All memory operations go through the `understory` MCP server. Use atomic
queries — one concept at a time, never bulk parallel calls.

| Tool | Key Parameters | Notes |
|------|---------------|-------|
| `understory_memory_query` | `question` (string) | Natural-language question. Keep it focused — one fact or concept per call. |
| `understory_memory_update` | `instruction` (string), `concept` (string, optional) | Correct or add info to an existing concept. `concept` narrows scope. |
| `understory_memory_add` | `content` (free-form string) | Add new knowledge. Use only when the concept doesn't exist yet. |
| `understory_memory_status` | *(none)* | Check memory health, segment counts, OKF status. |
| `understory_memory_maintain` | *(none)* | Health-check and repair the knowledge graph. |

**Rules:**
- Prefer `memory_update` over `memory_add` when the concept already exists.
- Ask before adding new memory concepts not already covered.
- Query atomically — 5 small searches beat 1 giant query.
- Kaomoji lexicon lives in Understory: query by category (cold, shrug,
glitch, alert, approval) before picking tone markers.

