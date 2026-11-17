# Architecture map

The architecture of Rinthel lives here as code: the `*.dg` files are the Model
(nodes, groups, edges) and the Views, written with
[rinthel-arch](https://github.com/WilliamBarriga/Rinthel-arch). The `.dg` text is
the only editable source; what is generated in `.diagrams/` is git-ignored.
The map describes the target state of the Instance: a daemon with identity in
SQLite, Local models served by `llama-server`, and Deck with its own SQLite file.

## Reading order

Open it with `scripts/diagrams.sh dev` and go to `http://127.0.0.1:4173/#p=<view>`.
In architecture Views, a click on a linked Group opens its detail.

| # | View | Type | What it explains |
| --- | --- | --- | --- |
| 1 | `instancia` | architecture | One Instance: actors, daemon, Deck, Understory, managed services and Docker |
| 2 | `modelos-locales` | architecture | `llama-server`, the optional voice services and the Local model switch |
| 3 | `ciclo-de-vida` | architecture | Boot, Terminate, Reload and Install: Client, API, plans and Host ports |
| 4 | `daemon-modulos` | architecture | The daemon modules and their dependencies |
| 5 | `daemon-api` | architecture | The routes per area and who calls them |
| 6 | `deck-servidor`, `deck-web` | architecture | Deck inside: Sessions, pi host, Guard, store, daemon client and screens |
| 7 | `understory-detalle` | architecture | Memory over MCP for admin Sessions |
| 8 | `datos`, `er-identidad`, `er-deck` | architecture / ER | `rinthel.db` and `deck.db`: tables, keys and the one reference between them |

## Files

| File | What it holds |
| --- | --- |
| `especificacion.dg` | Node types and the `rinthel` Theme |
| `sistema.dg` | The Instance, its actors, managed services, Docker and external systems |
| `daemon.dg` | The daemon: API per area, identity, models, lifecycle, monitoring, config |
| `deck.dg` | Deck web and server, pi host, Guard, store |
| `understory.dg` | Understory |
| `datos.dg` | SQLite: `rinthel.db` (identity) and `deck.db` (Deck) |
| `conexiones.dg` | Edges between files (Deck, daemon, SQLite, models, outside) |
| `vistas.dg` | All the Views |
| `fuentes/` | DejaVu fonts (and their license) used by the Theme |

## Tool

`rinthel-arch` enters as a submodule pinned to a commit in `docs/diagrams/.tool`
(https URL). It is not an npm package: it is built on first use.

```bash
git submodule update --init docs/diagrams/.tool   # once

scripts/diagrams.sh validate --strict   # 0 errors and 0 warnings before a commit
scripts/diagrams.sh build               # writes docs/diagrams/.diagrams/
scripts/diagrams.sh dev                 # live viewer
```

The first run does `pnpm install && pnpm build` inside the submodule (heavy).
When you bump the submodule, delete `docs/diagrams/.tool/packages/cli/dist` so
the script rebuilds. To use your own, already built clone of rinthel-arch:

```bash
DIAGRAMS_HOME=/path/to/rinthel-arch scripts/diagrams.sh validate --strict
```

## Maintenance rule

A change that touches a module, a port, a route or a table updates its `.dg`
in the same change and passes `scripts/diagrams.sh validate --strict` by hand
before the commit. There is no CI and no tracked hook for this: the check is
manual. If what the Instance promises changes (a new service, a new
Capability), update `sistema.dg` and the `instancia` View too.
