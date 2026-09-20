# Architecture diagrams

The diagrams in this repo are written in a variant of
[Eraser](https://docs.eraser.io/docs/syntax)'s DSL (`*.eraser`) and
compiled to interactive HTML with [Archify](https://github.com/tt-a1i/archify).

To get started right away: [`QUICKSTART.md`](QUICKSTART.md). For the full
syntax of the supported subset: [`SYNTAX.md`](SYNTAX.md).

## Requirements

- Node.js (to run Archify) — already on PATH on this host.
- The Archify package at `~/archify-pkg` (outside this repo). If it's not
  there: clone/unpack that package into the user's home; the path is
  hardcoded in `_ir_builder.py::ARCHIFY_BIN`.
- Python stdlib only — no `pip install` needed to compile.

## Workflow

```bash
# 1. Compile the .eraser into Archify's JSON IR, validating geometry/labels
.venv/bin/python docs/diagrams/eraser_to_archify.py \
    docs/diagrams/rinthel-runtime.eraser \
    docs/diagrams/out/rinthel-runtime.architecture.json \
    --validate

# 2. If validate raises no errors, render to self-contained HTML
node ~/archify-pkg/archify/bin/archify.mjs render architecture \
    docs/diagrams/out/rinthel-runtime.architecture.json \
    docs/diagrams/out/rinthel-runtime.html
```

Open the resulting `.html` in a browser — it's interactive (zoom, hover,
legend) and looks far better than a Graphviz PNG.

## Writing a new diagram

Base syntax (subset of real Eraser):

```
title: My Diagram
direction: right

Node A [icon: server]
Node B [icon: postgresql]

Group {
  Node C [icon: docker]
}

Node A > Node B: makes a query
Node A <> Node B: bidirectional
```

- `icon:` first tries to match Archify's real brand catalog
  (`node ~/archify-pkg/archify/bin/archify.mjs brands`) — if the node's
  name or icon matches something like `postgresql`, `docker`, `github`,
  `python`, `discord`, `telegram`, the real logo shows up. If it doesn't
  match, it falls back to a small table of generic words (`mail`,
  `monitor`, `server`, `database`, `network`, `cloud`, `queue`...).
- `{ }` nests groups (translated to Archify `boundaries`, a region type).
- `A > B`, `A < B`, `A <> B` are the three connection forms. `<>`
  generates two connections (Archify has no native single bidirectional
  arrow).

### Two extensions over real Eraser

Archify needs a typed `componentType`
(frontend/backend/database/cloud/security/messagebus/external) for its
legend, which real Eraser doesn't have. Hence:

- `Node [icon: x, type: database]` — forces the type when neither the
  brand nor the generic icon infers it well (e.g. Slack has no logo in
  the bundled catalog — `Slack [icon: slack, type: external]`).
- `Node [icon: x, row: 0, col: 2]` — pins the grid cell when automatic
  layering (rank by topological distance from the edges) picks wrong.
  Leave it out unless `--validate` complains.
- A connection can end with `{style: dashed, labelDy: -20}` — passed
  straight through to Archify's connection (`style` maps to `variant`;
  it also supports `fromSide`, `toSide`, `route`, `labelDx`,
  `labelSegment`).

## When `--validate` complains

Archify doesn't do real auto-layout — it places nodes on a grid
(`row`/`col`) and routes automatically, but routing/labels can overlap
with dense topologies (columns with many stacked nodes, connections
spanning several columns). `--validate` prints exact diagnostics with the
coordinate and a suggested fix (`labelDy +54` / `labelAt [x, y]` / etc.)
— iterate like this:

1. See which connection/node the diagnostic points at (**careful**: for
   connections with a default label, sometimes the label overlapping a
   box belongs to *another* nearby connection, not the "obvious" one —
   confirm the exact `from`/`to` pair in the message before touching
   anything).
2. If it's a label overlapping a box: `{labelDy: N}` with the suggested
   value.
3. If it's a connection crossing an unrelated node: move that node with
   an explicit `row`/`col`, or try `{route: orthogonal-v}` /
   `{fromSide: ..., toSide: ...}`.
4. Repeat `--validate` until 0 errors. Warnings (`composition standard: N
   warnings`) are optional, non-blocking.

## Files

```
docs/diagrams/
├── _ir_builder.py               # shared logic: dict -> Archify IR
├── eraser_to_archify.py         # DSL parser + CLI (the only entrypoint)
├── rinthel-monorepo-structure.eraser # source: subtrees, forks, upstreams
├── rinthel-runtime.eraser        # source: runtime architecture
├── rinthel-install-sources.eraser # source: where INSTALL pulls things from
├── examples/
│   └── mail-integration.eraser   # syntax example, not Rinthel-specific
└── out/                          # generated — *.architecture.json + *.html
```

`out/` can be regenerated at any time with the workflow above; it's
versioned the same way the PNGs used to be, so links from
`docs/01-system-overview.md` work without having to run anything.
