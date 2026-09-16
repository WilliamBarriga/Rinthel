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

## Matt Pocock Skills

Installed in `.pi/agent/skills/`. These are project skills you can invoke directly.

### grill-me
A relentless interview to sharpen a plan or design before building. Use when starting any new feature or change. Calls the "grilling" skill internally.

### wayfinder
Plans large work (more than one agent session) as a shared map of decision tickets in `.scratch/` (local markdown, no GitHub needed). Ticket types: research, prototype, grilling, task. Uses blocking via `Blocked by: NN` lines.

### domain-modeling
Builds and sharpens the project's domain model. Creates CONTEXT.md (glossary) and ADRs. Use when discussing codebase terminology or recording decisions. Integrates with Understory — store CONTEXT.md and ADRs as persistent concepts.

### research
Investigates questions against primary sources (official docs, source code, specs). Writes findings as a Markdown file in the repo. Use when you need facts from authoritative sources. Complements wayfinder's `research` ticket type.

### codebase-design
Shared vocabulary for designing deep modules (small interface + lots of implementation). Terms: module, interface, depth, seam, adapter, leverage, locality. Use when designing interfaces, finding deepening opportunities, or making code more testable. Referenced by wayfinder for architecture tickets.

**Note:** These skills are editable. Hack around with them and make them your own.
