"""Write the fixture's stored meshes: ``components/<cid>.l<level>.glb``.

The harness serves these as cadgen's mesh store would: one GLB body per
component and viewer LOD level (``lodPolicy.js``), bound to the component's
``surfaceInput`` in ``assembly.json`` and to its ``.surf``'s digest. The two
parts are rebuilt here from ``hinge_block.py``'s shapes and meshed by cadgen's
own producer (``cadgen._internal.occt_mesh``); a part whose edges a newer
build orders differently is written in the committed ``.surf``'s ordinals,
matched by each edge's centre and length, so every id the tests use holds.

Run from the repository root with the repo's Python:

    .venv/bin/python packages/ui/src/renderers/step/__fixtures__/step/source/make_meshes.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

FIXTURE = Path(__file__).resolve().parents[1]
LEVELS = {0: (2e-3, 1.4), 1: (1.5e-3, 0.35), 2: (5e-4, 0.35), 3: (1.5e-4, 0.35)}


def shapes():
    from cadgen import build123d as bd

    return {"base": bd.Box(20, 20, 10) - bd.Cylinder(3, 20), "arm": bd.Box(10, 8, 8)}


def _match(rows, fresh, key):
    """Each fresh row's ordinal -> the committed row it is, by centre and size."""
    mapping = {}
    for row in fresh:
        best = min(rows, key=lambda other: np.abs(np.subtract(other["center"], row["center"])).max()
                   + abs(other[key] - row[key]))
        mapping[row["ord"]] = best["ord"]
    if sorted(mapping.values()) != [row["ord"] for row in rows]:
        raise SystemExit("the rebuilt part's topology is not the committed one")
    return mapping


def main() -> None:
    from cadgen._internal import occt_mesh
    from cadgen._internal.component_package import decode_display_shape, prepare_geometry_component
    from cadgen._internal.surf_container import read_surf
    from cadgen._internal.surface_extract import extract_surface_component
    from cadgen.store.meshes import decode_payload, encode_payload

    view = json.loads((FIXTURE / "assembly.json").read_text(encoding="utf-8"))
    names = {occurrence["component"]: occurrence["name"] for occurrence in view["occurrences"]}
    built = shapes()
    for cid, component in view["components"].items():
        surf = (FIXTURE / "components" / f"{cid}.surf").read_bytes()
        committed, _ = read_surf(surf)
        prepared = prepare_geometry_component(built[names[cid]])
        entry, payload = prepared["entry"], prepared["payload"]
        live = decode_display_shape(entry, payload)
        fresh, _ = read_surf(extract_surface_component(live.wrapped))
        faces = _match(committed["faces"], fresh["faces"], "area")
        if any(fresh_ord != ordinal for fresh_ord, ordinal in faces.items()):
            raise SystemExit(f"{cid}: face order changed; this generator only re-maps edges")
        edges = _match(committed["edges"], fresh["edges"], "length")
        classes = {row["ord"]: str(row.get("class") or "none") for row in committed["edges"]}
        surface_object = hashlib.sha256(surf).hexdigest()
        for level, (chord, angle) in LEVELS.items():
            body = occt_mesh.mesh_component(decode_display_shape(entry, payload).wrapped, fresh,
                                            surface_input=component["surfaceInput"], surface_object=surface_object,
                                            chord=chord, angle=angle)
            meshed = decode_payload(body)
            polylines = [(int(ordinal), meshed.edge_points[start:start + count])
                         for ordinal, start, count, _class in meshed.edges.tolist()]
            remapped = sorted(((edges[ordinal], polyline) for ordinal, polyline in polylines), key=lambda item: item[0])
            body = encode_payload(
                surface_input=component["surfaceInput"], surface_object=surface_object, chord=chord, angle=angle,
                positions=meshed.positions, normals=meshed.normals, indices=meshed.indices.astype(np.uint32),
                face_ranges=meshed.face_ranges(),
                edges=[(ordinal, classes[ordinal], polyline) for ordinal, polyline in remapped],
                bounds=meshed.cad["bounds"], scale=meshed.cad["scale"], part_color=committed.get("partColor"),
            )
            (FIXTURE / "components" / f"{cid}.l{level}.glb").write_bytes(body)
            print(cid, names[cid], f"L{level}", len(body), "bytes")


if __name__ == "__main__":
    main()
