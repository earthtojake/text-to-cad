"""How far facts read off a part's XBM2 mesh fall from the kernel's: what a page could compute from the buffer it
already holds, instead of asking the core. Needs numpy (cad's environment).

    python tools/meshfacts.py ANSWERS_DIR [MODEL ...]     (a reference.py / smoke.py folder)

Per face: the box of its triangles' nodes against its "box", the summed triangle area against "area", the
area-weighted triangle centroids against "centroid". Per part: the nodes' box against the measure's "box", and for a
part of one solid the triangles' enclosed volume (divergence theorem) against "volume". Errors are given absolute and
relative to the part's linear deflection (the buffer's header), the tolerance the mesh is made to: the median, the
99th percentile and the worst over the distinct parts' faces.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import numpy as np

HEADER = struct.Struct("<4sI6I7I2f3I")


def read(data: bytes):
    _magic, _version, *rest = HEADER.unpack_from(data)
    counts, offsets, linear = rest[:6], rest[6:13], rest[13]

    def view(at, dtype, count, width):
        return np.frombuffer(data, dtype, count * width, offsets[at]).reshape(-1, width)

    nodes, indices, faces = counts[:3]
    return (view(0, "<f4", nodes, 3).astype(np.float64), view(2, "<u4", indices, 1).ravel(),
            view(3, "<u4", faces, 3), linear)


def main(root: Path, models: list[str]) -> dict:
    found = {k: [] for k in ("face_box", "face_area_rel", "face_centroid", "part_box", "part_volume_rel")}
    keys = set()
    for model in models:
        for part in (root / model / "parts").iterdir():
            key = (part / "key").read_text()
            if key in keys:
                continue
            keys.add(key)
            positions, indices, table, linear = read((part / "mesh.xbm").read_bytes())
            elements = json.loads((part / "elements.json").read_bytes())
            measure = json.loads((part / "measure.json").read_bytes())
            tri = positions[indices.reshape(-1, 3)]
            cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            areas = 0.5 * np.linalg.norm(cross, axis=1)
            centers = tri.mean(axis=1)
            for ordinal, first, count in table:
                fact = elements["faces"][str(int(ordinal))]
                if not count:
                    continue
                t = slice(first // 3, (first + count) // 3)
                nodes = positions[indices[first:first + count]]
                if fact["box"]:
                    error = max(np.abs(nodes.min(0) - fact["box"]["min"]).max(), np.abs(nodes.max(0) - fact["box"]["max"]).max())
                    found["face_box"].append((error, error / linear))
                area = areas[t].sum()
                rel = abs(area - fact["area"]) / fact["area"] if fact["area"] else 0.0
                found["face_area_rel"].append((rel, None))
                if area:
                    centroid = (centers[t] * areas[t, None]).sum(0) / area
                    error = np.abs(centroid - fact["centroid"]).max()
                    found["face_centroid"].append((error, error / linear))
            if measure["box"] and len(positions):
                error = max(np.abs(positions.min(0) - measure["box"]["min"]).max(), np.abs(positions.max(0) - measure["box"]["max"]).max())
                found["part_box"].append((error, error / linear))
            if measure["solids"] == 1 and measure["volume"]:
                volume = abs(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6)
                rel = abs(volume - measure["volume"]) / measure["volume"]
                found["part_volume_rel"].append((rel, None))
    report = {}
    for name, values in found.items():
        errors = np.array([v[0] for v in values])
        entry = {"n": len(values), "p50": float(np.percentile(errors, 50)), "p99": float(np.percentile(errors, 99)),
                 "max": float(errors.max())}
        if values and values[0][1] is not None:
            scaled = np.array([v[1] for v in values])
            entry.update(p50_deflections=float(np.percentile(scaled, 50)), p99_deflections=float(np.percentile(scaled, 99)),
                         max_deflections=float(scaled.max()))
        report[name] = entry
    return report


if __name__ == "__main__":
    root = Path(sys.argv[1])
    names = sys.argv[2:] or sorted(p.name for p in root.iterdir() if (p / "parts").exists())
    print(json.dumps(main(root, names), indent=1))
