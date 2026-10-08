"""Write the fixture's selector tables: ``components/<cid>.selectors.json``.

The harness serves these as cadgen's surface request does (the ready row's
``selectors``, read through the store route): one table per component, as
``cadgen._internal.selector_table`` builds it from the part's exact BREP and
its SURF. The two parts are rebuilt here from ``hinge_block.py``'s shapes; a
part whose edges a newer build orders differently is written in the committed
``.surf``'s ordinals, matched as ``make_meshes.py`` matches them, so every id
the tests use holds and the tables name the committed meshes' edges.

Run from the repository root with the repo's Python, after ``make_meshes.py``
when the parts are rebuilt, or whenever the table's schema or scheme moves:

    .venv/bin/python packages/ui/src/renderers/step/__fixtures__/step/source/make_selectors.py
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1]


def _remap_edges(table: dict, mapping: dict[int, int]) -> dict:
    """The table with its edge rows in the committed ordinals (``mapping``: fresh -> committed)."""
    columns = table["tables"]["edgeColumns"]
    at = {name: columns.index(name) for name in ("id", "localId", "ordinal", "vertexStart", "vertexCount", "chain")}
    relations = table["relations"]
    rows = sorted(table["edges"], key=lambda row: mapping[row[at["ordinal"]]])
    fresh_row_of = {row[at["ordinal"]] - 1: index for index, row in enumerate(rows)}
    edge_vertex_rows: list[int] = []
    chains: dict[int, int] = {}
    for row in rows:
        ordinal = mapping[row[at["ordinal"]]]
        start, count = row[at["vertexStart"]], row[at["vertexCount"]]
        row[at["vertexStart"]] = len(edge_vertex_rows)
        edge_vertex_rows.extend(relations["edgeVertexRows"][start:start + count])
        row[at["ordinal"]] = ordinal
        row[at["localId"]] = f"e{ordinal}"
        row[at["id"]] = f"o1.e{ordinal}"
        if row[at["chain"]] is not None:
            row[at["chain"]] = chains.setdefault(row[at["chain"]], len(chains) + 1)
    relations["edgeVertexRows"] = edge_vertex_rows
    relations["faceEdgeRows"] = [fresh_row_of[row] for row in relations["faceEdgeRows"]]
    vertex_columns = table["tables"]["vertexColumns"]
    v_start, v_count = vertex_columns.index("edgeStart"), vertex_columns.index("edgeCount")
    remapped = []
    for vertex in table["vertices"]:
        start, count = vertex[v_start], vertex[v_count]
        vertex[v_start] = len(remapped)
        remapped.extend(sorted(fresh_row_of[row] for row in relations["vertexEdgeRows"][start:start + count]))
    relations["vertexEdgeRows"] = remapped
    table["edges"] = rows
    return table


def main() -> None:
    from cadgen._internal.component_package import decode_display_shape, prepare_geometry_component
    from cadgen._internal.selector_table import build_selector_table, read_selector_table, selector_table_bytes
    from cadgen._internal.surface_extract import extract_surface_component, read_surf

    from make_meshes import _match, shapes

    view = json.loads((FIXTURE / "assembly.json").read_text(encoding="utf-8"))
    names = {occurrence["component"]: occurrence["name"] for occurrence in view["occurrences"]}
    built = shapes()
    for cid in view["components"]:
        committed, _ = read_surf((FIXTURE / "components" / f"{cid}.surf").read_bytes())
        prepared = prepare_geometry_component(built[names[cid]])
        live = decode_display_shape(prepared["entry"], prepared["payload"])
        fresh, _ = read_surf(extract_surface_component(live.wrapped))
        faces = _match(committed["faces"], fresh["faces"], "area")
        if any(fresh_ord != ordinal for fresh_ord, ordinal in faces.items()):
            raise SystemExit(f"{cid}: face order changed; this generator only re-maps edges")
        edges = _match(committed["edges"], fresh["edges"], "length")
        table = _remap_edges(build_selector_table(live.wrapped, fresh), edges)
        payload = selector_table_bytes(table)
        read_selector_table(payload)
        (FIXTURE / "components" / f"{cid}.selectors.json").write_bytes(payload + b"\n")
        print(cid, names[cid], len(payload), "bytes", table["stats"])


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
