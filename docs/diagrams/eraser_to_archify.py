"""Compile an Eraser.io-style DSL into Archify's JSON IR.

The one authoring entrypoint for diagrams in this repo: readable Eraser
syntax (https://docs.eraser.io/docs/syntax) in, valid `schema_version: 1`
Archify architecture IR out, ready for `archify render`/`archify validate`.
Layout/sizing logic lives in `_ir_builder.py`; this file is only the DSL
parser + CLI.

    colorMode: pastel
    styleMode: shadow
    direction: right

    Outlook [icon: mail]
    PC Usuario [icon: monitor]

    Red Local [icon: network] {
      Servidor API {
        API [icon: server]
        PostgreSQL [icon: database]
      }
    }

    PC Usuario > Outlook: envia correo
    API <> Outlook: lee correos (Graph API)

Supported subset: directive lines (`key: value`), node lines
(`Name [icon: x, label: "y"]`), brace groups (`Name [icon: x] {` ... `}`,
nesting allowed), and connections `A > B: label` / `A < B: label` /
`A <> B: label`. `colorMode`/`styleMode` have no exact Archify equivalent
(recorded as a comment in the output, not a real field) — `direction: down`
transposes rows/cols on a best-effort basis, `direction: right` (default)
needs no transform.

Node icons are matched against Archify's bundled brand catalogue
(`archify brands --json`) first — e.g. `icon: postgresql` gets the real
PostgreSQL logo — and fall back to a small keyword -> componentType table
for generic icons like `mail`, `monitor`, `server`, `database`, `network`.

Two small extensions beyond stock Eraser syntax, needed because Archify's
legend is typed (frontend/backend/database/cloud/security/messagebus/
external) and stock Eraser has no equivalent field:
  - `Name [icon: x, type: database]` forces the componentType when no brand
    or generic icon keyword infers the right one (e.g. Slack has no bundled
    logo: `Slack [icon: slack, type: external]`).
  - `Name [icon: x, row: 0, col: 2]` pins grid placement when the automatic
    layering picks a bad spot — same escape hatch `archify validate`
    diagnostics ask for; leave it off unless validate complains.
  - A connection may end in `{style: dashed, labelDy: -20}` — passed through
    to the Archify connection (`style` maps to `variant`; `fromSide`,
    `toSide`, `labelDy`, `labelDx`, `labelSegment` supported directly).

Usage:
    .venv/bin/python docs/diagrams/eraser_to_archify.py \\
        docs/diagrams/mail-integration.eraser \\
        docs/diagrams/out/mail-integration.architecture.json \\
        --title "Mail/Bots Integration" [--validate]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _ir_builder import ARCHIFY_BIN, STYLE_TO_VARIANT, TYPE_MAP, build_ir  # noqa: E402

GENERIC_ICON_TYPE = {
    "mail": "external", "inbox": "external", "email": "external",
    "external": "external", "saas": "external", "chat": "external",
    "monitor": "frontend", "desktop": "frontend", "laptop": "frontend",
    "user": "frontend", "client": "frontend", "browser": "frontend",
    "server": "backend", "api": "backend", "function": "backend",
    "database": "database", "db": "database", "storage": "database",
    "network": "security", "router": "security", "firewall": "security",
    "vpn": "security", "lock": "security", "shield": "security",
    "cloud": "cloud",
    "queue": "messagebus", "bus": "messagebus", "kafka": "messagebus",
}

BRAND_CATEGORY_TYPE = {
    "collaboration": "external", "cloud": "cloud", "framework": "frontend",
    "engineering": "backend", "ai": "backend", "data": "database",
    "channel": "external", "language": "backend", "business": "external",
}

ARROW_RE = re.compile(r"^(.+?)\s+(<>|<|>)\s+(.+)$")
ATTRS_RE = re.compile(r"^(.*?)\s*(?:\[(.*)\])?\s*$")
EDGE_TAIL_RE = re.compile(r"^(.*?)\s*(?:\{(.*)\})?\s*$")

# Numeric edge attrs, cast from the DSL's plain strings.
EDGE_NUMERIC_KEYS = {"labelDy", "labelDx", "labelSegment", "width"}


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    return slug or "node"


def parse_attrs(raw: str | None) -> dict:
    if not raw:
        return {}
    attrs = {}
    for part in re.findall(r'([a-zA-Z_]+)\s*:\s*("(?:[^"\\]|\\.)*"|[^,]+)', raw):
        key, val = part
        val = val.strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        attrs[key.strip()] = val
    return attrs


def load_brand_catalogue() -> dict[str, tuple[str, str]]:
    """id/alias/title (lowercased) -> (brand_id, componentType)."""
    if not ARCHIFY_BIN.exists():
        return {}
    try:
        out = subprocess.run(
            ["node", str(ARCHIFY_BIN), "brands", "--json"],
            capture_output=True, text=True, check=True, timeout=15,
        ).stdout
        data = json.loads(out)
    except Exception as exc:  # pragma: no cover - best-effort enrichment
        print(f"warning: could not load archify brand catalogue ({exc})", file=sys.stderr)
        return {}
    lookup: dict[str, tuple[str, str]] = {}
    for mark in data.get("marks", []):
        ctype = BRAND_CATEGORY_TYPE.get(mark["category"], "backend")
        for key in [mark["id"], mark["title"], *mark.get("aliases", [])]:
            lookup[key.strip().lower()] = (mark["id"], ctype)
    return lookup


def resolve_type_and_brand(
    name: str, icon: str | None, brands: dict, explicit_type: str | None = None
) -> tuple[str, str | None]:
    brand = None
    inferred_type = None
    for candidate in filter(None, [icon, name]):
        hit = brands.get(candidate.strip().lower())
        if hit:
            inferred_type, brand = hit[1], hit[0]
            break
    if explicit_type:
        return TYPE_MAP.get(explicit_type, explicit_type), brand
    if inferred_type:
        return inferred_type, brand
    if icon and icon.lower() in GENERIC_ICON_TYPE:
        return GENERIC_ICON_TYPE[icon.lower()], brand
    return "backend", brand


def parse_edge_attrs(raw: str | None) -> dict:
    """`{style: dashed, labelDy: -20}` -> connection-ready keys."""
    out: dict = {}
    for key, val in parse_attrs(raw).items():
        if key == "style":
            variant = STYLE_TO_VARIANT.get(val)
            if variant:
                out["variant"] = variant
        elif key in EDGE_NUMERIC_KEYS:
            out[key] = float(val) if "." in val else int(val)
        else:
            out[key] = val  # variant, fromSide, toSide, route, id passed through as-is
    return out


class Container:
    def __init__(self, node_dict: dict, group_dict: dict):
        self.nodes = node_dict
        self.groups = group_dict


def parse_eraser(text: str, brands: dict) -> tuple[dict, dict]:
    directives: dict[str, str] = {}
    root_nodes: dict = {}
    root_groups: dict = {}
    edges: list[dict] = []
    stack = [Container(root_nodes, root_groups)]
    seen_names: dict[str, str] = {}

    def register(name: str) -> str:
        node_id = slugify(name)
        seen_names[name] = node_id
        return node_id

    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue

        if line == "}":
            if len(stack) > 1:
                stack.pop()
            continue

        arrow = ARROW_RE.match(line)
        if arrow and not line.endswith("{"):
            left, op, rest = arrow.groups()
            tail_match = EDGE_TAIL_RE.match(rest)
            main_part, edge_attrs_raw = tail_match.group(1), tail_match.group(2)
            to_part, _, label = main_part.partition(":")
            from_name, to_name, label = left.strip(), to_part.strip(), label.strip()
            from_id = seen_names.get(from_name, slugify(from_name))
            to_id = seen_names.get(to_name, slugify(to_name))
            if op == "<":
                from_id, to_id = to_id, from_id
            conn = {"from": from_id, "to": to_id}
            if label:
                conn["label"] = label
            conn.update(parse_edge_attrs(edge_attrs_raw))
            edges.append(conn)
            if op == "<>":
                edges.append({"from": to_id, "to": from_id})
            continue

        is_group = line.endswith("{")
        body = line[:-1].strip() if is_group else line
        m = ATTRS_RE.match(body)
        name = m.group(1).strip()
        attrs = parse_attrs(m.group(2))

        if is_group:
            node_dict: dict = {}
            group_dict: dict = {}
            stack[-1].groups[register(name) + "_grp"] = {
                "label": attrs.get("label", name),
                "nodes": node_dict,
                "groups": group_dict,
            }
            stack.append(Container(node_dict, group_dict))
            continue

        if len(stack) == 1 and ":" in body and "[" not in body:
            key, _, val = body.partition(":")
            directives[key.strip()] = val.strip()
            continue

        ctype, brand = resolve_type_and_brand(name, attrs.get("icon"), brands, attrs.get("type"))
        node_id = register(name)
        spec = {"label": attrs.get("label", name), "archify_type": ctype}
        if brand:
            spec["brand"] = brand
        if "row" in attrs and "col" in attrs:
            spec["row"], spec["col"] = int(attrs["row"]), int(attrs["col"])
        stack[-1].nodes[node_id] = spec

    doc = {"diagram": directives.get("title", "Diagram"), "nodes": root_nodes, "groups": root_groups, "edges": edges}
    return directives, doc


def _spread_parallel_labels(connections: list[dict]) -> None:
    """`A <> B` becomes 2 connections, and several such pairs can share a
    corridor — stack their labels instead of letting them collide (same
    fix `archify validate` would suggest via labelDy)."""
    from collections import defaultdict

    groups: dict[frozenset, list[dict]] = defaultdict(list)
    for conn in connections:
        if "label" in conn and "labelDy" not in conn:
            groups[frozenset((conn["from"], conn["to"]))].append(conn)
    for conns in groups.values():
        if len(conns) < 2:
            continue
        for i, conn in enumerate(conns):
            sign = -1 if i % 2 == 0 else 1
            conn["labelDy"] = sign * (45 + 20 * (i // 2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("eraser_path", type=Path)
    ap.add_argument("out_path", type=Path)
    ap.add_argument("--title", help="overrides meta.title (default: source filename)")
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()

    brands = load_brand_catalogue()
    directives, doc = parse_eraser(args.eraser_path.read_text(), brands)
    if args.title:
        doc["diagram"] = args.title
    elif doc["diagram"] == "Diagram":
        doc["diagram"] = args.eraser_path.stem.replace("-", " ").replace("_", " ").title()

    ir = build_ir(doc)
    _spread_parallel_labels(ir["connections"])

    if directives.get("direction") == "down":
        for c in ir["components"]:
            c["row"], c["col"] = c["col"], c["row"]
        layout = ir["layout"]
        layout["cols"] = max((c["col"] for c in ir["components"]), default=0) + 1
        layout["gapX"], layout["gapY"] = layout["gapY"], layout["gapX"]
        layout["cellW"], layout["cellH"] = layout["cellH"], 64

    if directives.get("colorMode") or directives.get("styleMode"):
        print(
            f"note: Archify has no colorMode/styleMode equivalent "
            f"(ignored: {directives.get('colorMode')}/{directives.get('styleMode')}); "
            f"pick meta.visual_preset by hand if you want a different look "
            f"(classic/signal-flow/blueprint/editorial).",
            file=sys.stderr,
        )

    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    args.out_path.write_text(json.dumps(ir, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {args.out_path}")

    if args.validate:
        if not ARCHIFY_BIN.exists():
            print(f"error: archify CLI not found at {ARCHIFY_BIN}", file=sys.stderr)
            sys.exit(1)
        subprocess.run(["node", str(ARCHIFY_BIN), "validate", "architecture", str(args.out_path)], check=False)


if __name__ == "__main__":
    main()
