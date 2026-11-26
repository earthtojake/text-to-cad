"""Quick parity check of the core's answers (tools/smoke.py's folder) against cad's (bench/reference.py's folder).

    python tools/compare.py REF_DIR OUT_DIR [MODEL ...]

Per model, one line per check, with the first differences found. The tolerances are the prototype's parity bar:
structure equal (matrices within 1e-9); shape bytes identical; XBM2 face table ordinals and order equal and index
counts reported, edge table identical, edge points and vertices within 1e-5, header deflections equal; elements and
groups equal but floats within 1e-6 relative (1e-9 absolute near zero); measures' floats within 1e-9 relative.
Standard library only.
"""
from __future__ import annotations

import json
import math
import struct
import sys
from array import array
from pathlib import Path

HEADER = struct.Struct("<4sI6I7I2f3I")


def close(a: float, b: float, rel: float, absolute: float) -> bool:
    return a == b or abs(a - b) <= max(rel * max(abs(a), abs(b)), absolute)


def diff(a, b, rel: float, absolute: float, path: str = "", found: list | None = None) -> list:
    """Where two JSON values differ: strings, ints, keys and lengths exactly, floats by tolerance."""
    found = [] if found is None else found
    if len(found) > 5:
        return found
    if isinstance(a, dict) and isinstance(b, dict):
        if list(a) != list(b):
            found.append(f"{path}: keys {sorted(set(a) ^ set(b))[:6]} or order")
        for k in a:
            if k in b:
                diff(a[k], b[k], rel, absolute, f"{path}/{k}", found)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            found.append(f"{path}: length {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, rel, absolute, f"{path}[{i}]", found)
    elif isinstance(a, float) or isinstance(b, float):
        if type(a) not in (int, float) or type(b) not in (int, float) or not close(a, b, rel, absolute):
            found.append(f"{path}: {a!r} != {b!r}")
    elif a != b or type(a) is not type(b):
        found.append(f"{path}: {a!r} != {b!r}")
    return found


def mesh(data: bytes) -> dict:
    magic, version, *rest = HEADER.unpack_from(data)
    counts, offsets, deflections = rest[:6], rest[6:13], rest[13:15]

    def view(at: int, code: str, count: int) -> array:
        values = array(code)
        values.frombytes(data[offsets[at]: offsets[at] + 4 * count])
        return values

    nodes, indices, faces, edges, points, vertices = counts
    return {"magic": magic, "version": version, "counts": counts, "deflections": deflections,
            "faces": view(3, "I", 3 * faces), "edges": view(4, "I", 4 * edges), "points": view(5, "f", 3 * points),
            "vertices": view(6, "f", 4 * vertices), "positions": view(0, "f", 3 * nodes), "indices": view(2, "I", indices)}


def compare_mesh(ref: bytes, out: bytes) -> tuple[bool, str]:
    a, b = mesh(ref), mesh(out)
    notes, ok = [], True
    if (a["magic"], a["version"], a["deflections"]) != (b["magic"], b["version"], b["deflections"]):
        ok = False
        notes.append(f"header {a['deflections']} != {b['deflections']}")
    fa, fb = a["faces"], b["faces"]
    if list(fa[0::3]) != list(fb[0::3]):
        ok = False
        notes.append("face ordinals differ")
    counts = [(int(fa[i]), fa[i + 2], fb[i + 2]) for i in range(0, min(len(fa), len(fb)), 3) if fa[i + 2] != fb[i + 2]]
    if counts:
        notes.append(f"{len(counts)} faces' index counts differ (ordinal, ref, core): {counts[:4]}")
    if a["edges"] != b["edges"]:
        ok = False
        notes.append("edge table differs")
    for name in ("points", "vertices"):
        x, y = a[name], b[name]
        if len(x) != len(y):
            ok = False
            notes.append(f"{name}: {len(x)} != {len(y)}")
            continue
        worst = max((abs(p - q) for p, q in zip(x, y)), default=0.0)
        if worst > 1e-5:
            ok = False
            notes.append(f"{name} differ by up to {worst:g}")
    same_triangles = a["positions"] == b["positions"] and a["indices"] == b["indices"]
    notes.append(f"nodes {a['counts'][0]}/{b['counts'][0]} indices {a['counts'][1]}/{b['counts'][1]}"
                 + (" (identical)" if same_triangles else ""))
    return ok, "; ".join(notes)


def compare(ref: Path, out: Path) -> dict:
    report = {"model": ref.name}
    sa, sb = json.loads((ref / "structure.json").read_bytes()), json.loads((out / "structure.json").read_bytes())
    found = diff(sa, sb, 0.0, 1e-9)
    report["structure"] = "ok" if not found else found
    shape, meshes, elements, measures = [], [], [], []
    for part in sorted((ref / "parts").iterdir(), key=lambda p: int(p.name)):
        other = out / "parts" / part.name
        if (part / "shape.bin").read_bytes() != (other / "shape.bin").read_bytes():
            shape.append(part.name)
        ok, note = compare_mesh((part / "mesh.xbm").read_bytes(), (other / "mesh.xbm").read_bytes())
        meshes.append((part.name, ok, note))
        for name in ("elements.json", "groups.json"):
            found = diff(json.loads((part / name).read_bytes()), json.loads((other / name).read_bytes()), 1e-6, 1e-9)
            if found:
                elements.append((part.name, name, found))
        found = diff(json.loads((part / "measure.json").read_bytes()), json.loads((other / "measure.json").read_bytes()),
                     1e-9, 1e-12)
        if found:
            measures.append((part.name, found))
    report["shape_bytes"] = "identical" if not shape else f"differ in parts {shape[:10]}"
    bad = [m for m in meshes if not m[1]]
    triangulated = [m for m in meshes if "identical" not in m[2]]
    report["mesh"] = {"parts": len(meshes), "failing": bad[:5], "other_triangles": len(triangulated),
                      "notes": [m for m in triangulated if "index counts differ" in m[2]][:5]}
    report["elements_groups"] = "ok" if not elements else elements[:5]
    report["measure"] = "ok" if not measures else measures[:5]
    return report


if __name__ == "__main__":
    ref_root, out_root = Path(sys.argv[1]), Path(sys.argv[2])
    names = sys.argv[3:] or sorted(p.name for p in out_root.iterdir() if (p / "structure.json").exists())
    for name in names:
        print(json.dumps(compare(ref_root / name, out_root / name)), flush=True)
