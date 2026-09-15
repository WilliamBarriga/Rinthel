"""Shared core: nodes/groups/edges (as plain dicts) -> Archify architecture IR.

Internal to this directory — not a CLI. `eraser_to_archify.py` is the only
authoring entrypoint; it parses the Eraser DSL into the dict shape this
module expects and calls `build_ir()`. Kept separate only so the IR/layout
logic (grid layering, label sizing, escape hatches) isn't buried inside the
DSL parser.

Expected doc shape:

    {
      "diagram": "Title",
      "nodes": {id: {"label": ..., "type": ..., ["archify_type", "brand",
                      "tag", "row", "col"]}},
      "groups": {id: {"label": ..., "nodes": {...}, "groups": {...}}},
      "edges": [{"from": id, "to": id | [id, ...], "label": ...,
                  ["style", "variant", "fromSide", "toSide", "route", "via",
                   "labelAt", "labelDx", "labelDy", "labelSegment", "width"]}],
    }
"""

from __future__ import annotations

import sys
from pathlib import Path

# Our friendly `type:` vocabulary -> Archify's componentType enum
# (frontend, backend, database, cloud, security, messagebus, external).
TYPE_MAP = {
    "client": "frontend",
    "external": "external",
    "process": "backend",
    "server": "backend",
    "container": "cloud",
    "storage": "database",
    "network": "security",
    "channel": "external",
    "system": "security",
    # Archify's own componentType enum, accepted as-is too.
    "frontend": "frontend",
    "backend": "backend",
    "database": "database",
    "cloud": "cloud",
    "security": "security",
    "messagebus": "messagebus",
}

STYLE_TO_VARIANT = {
    "dashed": "dashed",
    "dotted": "dashed",  # Archify's variant enum has no separate "dotted"
}

ARCHIFY_BIN = Path.home() / "archify-pkg" / "archify" / "bin" / "archify.mjs"


def component_type(node: dict) -> str:
    if "archify_type" in node:
        return node["archify_type"]
    t = node.get("type", "backend")
    mapped = TYPE_MAP.get(t)
    if mapped is None:
        print(f"warning: unknown type '{t}', defaulting to 'backend'", file=sys.stderr)
        return "backend"
    return mapped


def split_label(raw: str) -> tuple[str, str | None]:
    if "\n" not in raw:
        return raw, None
    head, rest = raw.split("\n", 1)
    return head, rest.replace("\n", " · ")


def mask_width(text: str) -> float:
    """Archify's measured-label rule: ~6.5px/ASCII char + 13px, CJK counts double."""
    units = sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)
    return 6.5 * units + 13


def box_size(label: str, sublabel: str | None) -> list[int]:
    widest = max(mask_width(label), mask_width(sublabel) if sublabel else 0)
    width = max(120, int(widest) + 24)  # padding so text never touches the border
    return [width, 60]


def collect(node_map: dict, group_map: dict, group_path: tuple[str, ...], order: list, boundaries: list) -> None:
    """Walk nested nodes/groups, filling `order` (component dicts) and `boundaries`."""
    for node_id, spec in (node_map or {}).items():
        label, sublabel = split_label(spec["label"])
        comp = {
            "id": node_id,
            "type": component_type(spec),
            "label": label,
            "_group_path": group_path,
        }
        if sublabel:
            comp["sublabel"] = sublabel
        if "tag" in spec:
            comp["tag"] = spec["tag"]
        if "brand" in spec:
            comp["brand"] = spec["brand"]
        comp["size"] = box_size(label, sublabel)
        if "row" in spec and "col" in spec:
            comp["_row_override"] = (spec["row"], spec["col"])
        order.append(comp)

    for group_id, group_spec in (group_map or {}).items():
        child_path = group_path + (group_id,)
        wraps: list[str] = []
        collect(group_spec.get("nodes"), group_spec.get("groups"), child_path, order, boundaries)
        for c in order:
            if child_path == c["_group_path"][: len(child_path)]:
                wraps.append(c["id"])
        if wraps:
            boundaries.append(
                {
                    "kind": group_spec.get("kind", "region"),
                    "label": group_spec["label"],
                    "wraps": wraps,
                }
            )


def assign_columns(component_ids: list[str], edges: list[dict]) -> dict[str, int]:
    """Longest-path layering over the DAG obtained by dropping back-edges."""
    adj: dict[str, list[str]] = {cid: [] for cid in component_ids}
    for e in edges:
        if e["from"] in adj and e["to"] in adj:
            adj[e["from"]].append(e["to"])

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {cid: WHITE for cid in component_ids}
    dag_adj: dict[str, list[str]] = {cid: [] for cid in component_ids}

    def dfs(u: str) -> None:
        color[u] = GRAY
        for v in adj[u]:
            if color[v] == WHITE:
                dag_adj[u].append(v)
                dfs(v)
            elif color[v] == BLACK:
                dag_adj[u].append(v)
            # GRAY target == back-edge, dropped from the DAG used for ranking
        color[u] = BLACK

    for cid in component_ids:
        if color[cid] == WHITE:
            dfs(cid)

    rank: dict[str, int] = {}

    def longest(u: str, stack: set) -> int:
        if u in rank:
            return rank[u]
        preds = [p for p in component_ids if u in dag_adj[p] and p != u]
        preds = [p for p in preds if p not in stack]
        if not preds:
            rank[u] = 0
        else:
            rank[u] = 1 + max(longest(p, stack | {u}) for p in preds)
        return rank[u]

    for cid in component_ids:
        longest(cid, set())
    return rank


def build_ir(doc: dict) -> dict:
    order: list[dict] = []
    boundaries: list[dict] = []
    collect(doc.get("nodes"), doc.get("groups"), (), order, boundaries)

    # Passed straight through to the connection when the auto-router needs a
    # nudge (see Archify's `clean-flow` diagnostics) — same escape-hatch
    # spirit as overriding a Terraform module's defaults.
    PASSTHROUGH_EDGE_KEYS = (
        "fromSide", "toSide", "route", "via",
        "labelAt", "labelDx", "labelDy", "labelSegment", "width", "id",
    )

    raw_edges = doc.get("edges", [])
    edges: list[dict] = []
    for e in raw_edges:
        targets = e["to"] if isinstance(e["to"], list) else [e["to"]]
        for t in targets:
            conn = {"from": e["from"], "to": t}
            if "label" in e:
                conn["label"] = e["label"].replace("\n", " · ")
            variant = e.get("variant") or STYLE_TO_VARIANT.get(e.get("style", ""))
            if variant:
                conn["variant"] = variant
            for key in PASSTHROUGH_EDGE_KEYS:
                if key in e:
                    conn[key] = e[key]
            edges.append(conn)

    component_ids = [c["id"] for c in order]
    cols = assign_columns(component_ids, edges)
    for c in order:
        if "_row_override" in c:
            cols[c["id"]] = c["_row_override"][1]  # explicit col wins over the ranked one

    reserved: dict[int, set[int]] = {}
    for c in order:
        if "_row_override" in c:
            row, col = c["_row_override"]
            reserved.setdefault(col, set()).add(row)

    row_counter: dict[int, int] = {}

    def next_free_row(col: int) -> int:
        row = row_counter.get(col, 0)
        while row in reserved.get(col, set()):
            row += 1
        row_counter[col] = row + 1
        return row

    # keep components from the same group contiguous within a column
    order_sorted = sorted(order, key=lambda c: (cols[c["id"]], c["_group_path"]))
    for comp in order_sorted:
        col = cols[comp["id"]]
        comp["col"] = col
        if "_row_override" in comp:
            comp["row"] = comp["_row_override"][0]
            del comp["_row_override"]
        else:
            comp["row"] = next_free_row(col)
        del comp["_group_path"]

    max_col = max(cols.values(), default=0)
    cell_w = max((c["size"][0] for c in order_sorted), default=170)

    ir = {
        "schema_version": 1,
        "diagram_type": "architecture",
        "meta": {"title": doc["diagram"]},
        "layout": {
            "mode": "grid",
            "origin": [40, 80],
            "cols": max_col + 1,
            "gapX": 100,
            "gapY": 90,
            "cellW": cell_w,
            "cellH": 64,
        },
        "components": order_sorted,
        "boundaries": boundaries,
        "connections": edges,
    }
    return ir
