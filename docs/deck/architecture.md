# Deck: architecture

How Deck's pieces fit is drawn in [`docs/diagrams/deck.dg`](../diagrams/deck.dg)
(views `deck-servidor` and `deck-web`); what Deck reads and keeps is in
[configuration](configuration.md). This page holds what the map cannot say.

## Subagents

An admin's Agent can hand a task to a child agent with the `subagent` tool. A
child is a pi session of its own inside Deck's process, with an isolated
context, kept in memory and gone once it answers. The tool is an inline
factory of Deck (`deck/server/src/pi/subagents/`); nothing is installed into
pi for it.

**Who gets it.** Only a Session whose owner is an admin, decided by its
`ToolProfile` when the Session starts, and asked again on every call: an owner
who is no longer an admin, or an identity that does not answer, is refused. A
member's Session never has it. A tainted Session loses it outright, and a
child's answer is untrusted content: it reaches the parent inside the Guard's
envelope and taints the Session.

**Modes.** One child at a time per Session, since the Instance runs one Local
model:

- single: `{ agent, task }`
- chain: `{ chain: [{ agent, task }] }`, each step gets the previous answer as
  `{previous}`; the chain stops at a failed step
- tasks: `{ tasks: [{ agent, task }] }`, independent, one after another;
  `variants: true` presents them as alternatives

Optional on the call or per item: `skills` (looked up by name in the Session's
`.pi/skills` and `.agents/skills`, then in the agentDir's `skills/`; loaded on
demand, or pasted whole with `inlineSkills: true`) and `persona` (a role for
this task, meant for `custom`). At most 8 items per call; each answer is capped
at 50 KB.

**The child.** It uses its parent's Local model through the parent's model
access: the same Session proxy URL, so it shares (and overwrites) the
Session's slot. The slot is held one HTTP request at a time, not for a whole
agent turn, so parent and child never wait on each other. The child runs with
a Guard of its own and loads the agentDir's packages, but never has what a
tainted Session loses (`subagent`, host exec, Memoria writes) nor
`ask_user_question`; an installed package that registers one of those is not
loaded in it. A child stops at its timeout or turn limit, whichever comes
first, and when the parent's turn is aborted.

### Agent types

The image carries these, next to the factory
(`deck/server/src/pi/subagents/agents/`):

| Type | What it does | Tools |
| --- | --- | --- |
| `scout` | Quick reconnaissance of a codebase; returns compressed context for another agent | read, grep, find, ls, bash, web_search, source_check, fetch_content |
| `planner` | Turns context and requirements into an implementation plan; changes nothing | read, grep, find, ls, web_search, source_check, fetch_content |
| `researcher` | Web and document research with cited sources; changes nothing | read, grep, find, ls, web_search, source_check, fetch_content |
| `worker` | General-purpose developer with full capabilities | read, write, edit, grep, find, ls, bash, web_search, source_check, fetch_content |
| `reviewer` | Code review for quality, security and maintainability; bash read-only | read, grep, find, ls, bash, web_search, source_check, fetch_content |
| `debugger` | Reproduces a bug and finds its root cause; does not fix it | read, grep, find, ls, bash |
| `builder` | Runs builds, tests and checks, and reports; does not change code | read, grep, find, ls, bash |
| `writer` | Drafts and edits documentation and other text | read, write, edit, grep, find, ls |
| `custom` | Generic agent whose role is the call's `persona` | read, grep, find, ls, bash |

`web_search`, `source_check` and `fetch_content` exist only when a package that
provides them is installed in Deck's agentDir; without it those agents work
with the rest.

An agent type is a Markdown file: frontmatter with `name` and `description`
(required), `tools` (pi's allowlist for the child; absent, pi's defaults),
`thinking`, `skills`, `timeout` (seconds) and `maxTurns`, and the agent's
prompt as the body. A local model is slow, so no agent goes below 1200 s or 60
turns whatever its frontmatter says.

**Adding or replacing one.** Drop a file into `agents/` of Deck's agentDir on
the volume (`data/deck/home/.pi/agent/agents/`). It joins the image's types;
one with an image type's name replaces it, and Deck logs the replacement
(`[subagents] agent "<name>": <volume file> replaces the image's <image file>`)
when an admin's Session starts. Files are read again on every call. A
project's `.pi/agents` is never read.

## Memoria

The Memoria is what the Instance remembers between Sessions, kept in
Understory: one per Instance, shared by its admins. An admin's Agent reaches
it with three fixed tools, an inline factory of Deck
(`deck/server/src/pi/memoria/`) that calls Understory's MCP endpoint (`POST
/mcp`, stateless, one JSON reply) directly; no MCP adapter or `mcp.json` is
installed in pi for it.

| Tool | Understory tool | What it does |
| --- | --- | --- |
| `understory_memory_query` | `memory_query` | Asks a question; an agent inside Understory searches and answers with cited paths |
| `understory_memory_add` | `memory_add` | Records new knowledge |
| `understory_memory_update` | `memory_update` | Changes existing knowledge |

`memory_status` and `memory_maintain` are left out.

**Who gets it.** Only a Session whose owner is an admin, and only when Deck
has `UNDERSTORY_TOKEN`; the role is asked again on every call and an owner who
is no longer an admin, or an identity that does not answer, is refused. A
member's Session never has it.

**The Guard.** Reading the Memoria is not untrusted content: the Session stays
clean. A tainted Session keeps the query but loses `add` and `update`, so only
clean Sessions write the Memoria. A subagent's child gets the query alone.

**Where it is.** The daemon hands the URL in its routing
(`GET /model-provider/routing`, `understory_url`), per Platform:
`http://127.0.0.1:3800` on Linux, `http://understory:3800` on Windows (a
network Deck and Understory share); `null` when Understory is off. Deck reads
it on every call and presents `UNDERSTORY_TOKEN` as a bearer token.

**When Understory fails.** Registering the tools never reaches Understory, so
neither Deck's start nor a Session's waits on it. A call that cannot reach it,
a token it refuses, Understory off, or a write it could not make is an error
result for the Agent, and the Session goes on. A call may take up to 40
minutes (a query runs a model inside Understory); past that it is dropped with
an error.
