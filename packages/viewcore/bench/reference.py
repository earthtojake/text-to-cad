"""Reference outputs of cad's own engine for an .xbf: what the view core must answer, written to a folder.

    python reference.py OUT_DIR FILE.xbf [...]   (with cad's environment: `uv run python ...` in the repo)

Per document, in OUT_DIR/<file stem>/:
  structure.json            the subset of document.Loaded.structure() the core answers (viewcore.h)
  timing.json               seconds per stage, one thread, this process
  parts/<index>/key         the file's geometry key for the part
  parts/<index>/shape.bin   mesh.shape_bytes(shape, read=True); blake2b-128 of it is the key
  parts/<index>/mesh.xbm    mesh.mesh_shape(bytes, parallel=False).to_bytes()
  parts/<index>/elements.json, groups.json, measure.json   Topology(bytes).elements(), .groups(), mesh.measured(bytes)
Parts are numbered by document.Loaded.prototypes; parts sharing a key hold the same files.
"""
import hashlib, json, os, sys, time
from pathlib import Path

STRUCTURE_PROTOTYPE = ("index", "key", "name", "color", "faceNames", "edgeNames", "vertexNames", "faceColors")
STRUCTURE_INSTANCE = ("prototype", "path", "matrix", "color")


def dump(path: Path, out: Path) -> dict:
    from cad.engine.document import Loaded
    from cad.engine.mesh import Topology, measured, mesh_shape, shape_bytes

    timing = {}
    t = time.perf_counter()
    loaded = Loaded(path)
    structure = loaded.structure()
    timing["read_s"] = time.perf_counter() - t
    subset = {"prototypes": [{k: p.get(k) for k in STRUCTURE_PROTOTYPE} for p in structure["prototypes"]],
              "instances": [{k: i.get(k) for k in STRUCTURE_INSTANCE} for i in structure["instances"]]}
    out.mkdir(parents=True, exist_ok=True)
    (out / "structure.json").write_text(json.dumps(subset, separators=(",", ":")))
    done: dict[str, Path] = {}
    stages = {"shape_bytes_s": 0.0, "mesh_s": 0.0, "elements_s": 0.0, "measure_s": 0.0}
    for prototype in loaded.prototypes:
        folder = out / "parts" / str(prototype.index)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "key").write_text(prototype.key)
        if prototype.key in done:  # same geometry: same answers
            for name in ("shape.bin", "mesh.xbm", "elements.json", "groups.json", "measure.json"):
                (folder / name).write_bytes((done[prototype.key] / name).read_bytes())
            continue
        t = time.perf_counter(); data = shape_bytes(prototype.shape, read=True); stages["shape_bytes_s"] += time.perf_counter() - t
        assert hashlib.blake2b(data, digest_size=16).hexdigest() == prototype.key, "key is not blake2b of the shape bytes"
        (folder / "shape.bin").write_bytes(data)
        t = time.perf_counter(); body = mesh_shape(data, parallel=False).to_bytes(); stages["mesh_s"] += time.perf_counter() - t
        (folder / "mesh.xbm").write_bytes(body)
        t = time.perf_counter(); topology = Topology(data); elements = topology.elements(); stages["elements_s"] += time.perf_counter() - t
        (folder / "elements.json").write_text(json.dumps(elements, separators=(",", ":")))
        (folder / "groups.json").write_text(json.dumps(elements["groups"], separators=(",", ":")))
        t = time.perf_counter(); facts = measured(data); stages["measure_s"] += time.perf_counter() - t
        (folder / "measure.json").write_text(json.dumps(facts, separators=(",", ":")))
        done[prototype.key] = folder
    timing.update(stages)
    timing = {k: round(v, 4) for k, v in timing.items()}
    timing.update(parts=len(loaded.prototypes), keys=len(done), instances=len(structure["instances"]))
    (out / "timing.json").write_text(json.dumps(timing))
    return {"file": path.name, **timing}


if __name__ == "__main__":
    root = Path(sys.argv[1])
    for name in sys.argv[2:]:
        print(json.dumps(dump(Path(name).resolve(), root / Path(name).stem)), flush=True)
