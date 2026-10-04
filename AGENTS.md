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

