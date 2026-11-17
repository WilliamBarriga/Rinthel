#!/usr/bin/env bash
# Architecture diagrams (docs/diagrams/*.dg) with rinthel-arch as the tool.
#
#   scripts/diagrams.sh validate [--strict]   validate the Model and the Views
#   scripts/diagrams.sh build                 write docs/diagrams/.diagrams/
#   scripts/diagrams.sh dev [--port N]        live viewer (127.0.0.1:4173)
#
# The tool comes from the submodule docs/diagrams/.tool (pinned to a commit).
# DIAGRAMS_HOME=/path/to/rinthel-arch uses a local clone instead, without
# reinstalling or rebuilding if it is already built.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="$repo/docs/diagrams"
home="${DIAGRAMS_HOME:-$workspace/.tool}"
bin="$home/packages/cli/dist/bin.js"

if [[ ! -f "$home/package.json" ]]; then
  echo "Missing tool: git submodule update --init docs/diagrams/.tool (or set DIAGRAMS_HOME)" >&2
  exit 2
fi

if [[ ! -f "$bin" ]]; then
  echo "Building rinthel-arch in $home (pnpm install && pnpm build)..." >&2
  (cd "$home" && pnpm install --frozen-lockfile && pnpm build)
fi

cmd="${1:?usage: scripts/diagrams.sh <validate|build|dev> [args]}"
shift
exec node "$bin" "$cmd" --workspace "$workspace" "$@"
