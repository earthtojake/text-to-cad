"""Run the view core under wasmtime on .xbf files and write its outputs in reference.py's layout.

    python dump_core.py OUT_DIR [--wasm dist/viewcore.wasm] [--picks 100] [--cache FILE] FILE.xbf [...]
    (with a Python that has wasmtime installed: `pip install wasmtime`)

OUT_DIR/<stem>/: structure.json (the core's bytes as they came), timing.json, parts/<index>/{key, shape.bin, mesh.xbm,
elements.json, groups.json, measure.json} (the core's bytes as they came). Parts sharing a key are computed once (as
reference.py does) and their files copied. timing.json: compile_s, instantiate_s, open_s, structure_s, shape_bytes_s,
mesh_s, elements_s, groups_s, measure_s, pick_median_s / pick_p95_s / picks (vc_fact latency, seeded random
face/edge picks), peak_rss_mb (this process, so far), wasm_memory_mb, parts, keys, instances.
"""
import argparse, hashlib, json, random, resource, statistics, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hosts" / "wasmtime"))
from viewcore import Core  # noqa: E402

HERE = Path(__file__).resolve().parent


def dump(core: Core, path: Path, out: Path, picks: int) -> dict:
    timing = {"compile_s": core.compile_s, "instantiate_s": core.instantiate_s}
    data = path.read_bytes()
    t = time.perf_counter(); doc = core.open_xbf(data); timing["open_s"] = time.perf_counter() - t
    t = time.perf_counter(); sbytes = core._result("vc_structure", "vc_structure", doc.handle); timing["structure_s"] = time.perf_counter() - t
    structure = json.loads(sbytes)
    out.mkdir(parents=True, exist_ok=True)
    (out / "structure.json").write_bytes(sbytes)
    stages = dict(shape_bytes_s=0.0, mesh_s=0.0, elements_s=0.0, groups_s=0.0, measure_s=0.0)
    done: dict[str, Path] = {}
    facts_pool = []  # (part, kind, ordinal) candidates
    for proto in structure["prototypes"]:
        i, key = proto["index"], proto["key"]
        folder = out / "parts" / str(i)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "key").write_text(key)
        if key in done:
            for name in ("shape.bin", "mesh.xbm", "elements.json", "groups.json", "measure.json"):
                (folder / name).write_bytes((done[key] / name).read_bytes())
            continue
        t = time.perf_counter(); shape = doc.shape_bytes(i); stages["shape_bytes_s"] += time.perf_counter() - t
        if hashlib.blake2b(shape, digest_size=16).hexdigest() != key:
            print(f"  warning: part {i} blake2b(shape) != key", file=sys.stderr)
        (folder / "shape.bin").write_bytes(shape)
        t = time.perf_counter(); mesh = doc.mesh(i); stages["mesh_s"] += time.perf_counter() - t
        (folder / "mesh.xbm").write_bytes(mesh)
        t = time.perf_counter(); el = doc.elements_bytes(i); stages["elements_s"] += time.perf_counter() - t
        (folder / "elements.json").write_bytes(el)
        t = time.perf_counter(); gr = doc.groups_bytes(i); stages["groups_s"] += time.perf_counter() - t
        (folder / "groups.json").write_bytes(gr)
        t = time.perf_counter(); ms = doc.measure_bytes(i); stages["measure_s"] += time.perf_counter() - t
        (folder / "measure.json").write_bytes(ms)
        done[key] = folder
        elj = json.loads(el)
        facts_pool += [(i, "face", int(o)) for o in elj.get("faces", {})] + [(i, "edge", int(o)) for o in elj.get("edges", {})]
    timing.update(stages)
    lat = []
    rng = random.Random(0)
    for part, kind, ordinal in (rng.choices(facts_pool, k=picks) if facts_pool else []):
        t = time.perf_counter(); doc.fact_bytes(part, kind, ordinal); lat.append(time.perf_counter() - t)
    if lat:
        lat.sort()
        timing.update(pick_median_s=statistics.median(lat), pick_p95_s=lat[min(len(lat) - 1, int(0.95 * len(lat)))], picks=len(lat))
    timing.update(parts=len(structure["prototypes"]), keys=len(done), instances=len(structure["instances"]),
                  wasm_memory_mb=round(core.memory_bytes() / 2**20, 1),
                  peak_rss_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1))
    doc.close()
    timing = {k: (round(v, 5) if isinstance(v, float) else v) for k, v in timing.items()}
    (out / "timing.json").write_text(json.dumps(timing))
    return timing


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("files", nargs="+")
    ap.add_argument("--wasm", default=str(HERE.parent / "dist" / "viewcore.wasm"))
    ap.add_argument("--picks", type=int, default=100)
    ap.add_argument("--cache", help="serialized compiled module file (speeds repeat runs; compile_s then measures deserialize)")
    a = ap.parse_args()
    for f in a.files:
        core = Core(a.wasm, cache=a.cache)  # a fresh instance per file: its own memory and timings
        p = Path(f)
        r = dump(core, p.resolve(), Path(a.out) / p.stem, a.picks)
        print(json.dumps({"file": p.name, **r}), flush=True)
