"""The view core's answers to the engine's pool jobs, held against the engine's own job code.

    python tools/pool_parity.py [--node NODE] [--wasm dist/viewcore.wasm] [--native LIB.so] [--picks 12]
                                [--exports] [--json OUT.json] FILE.xbf [...]

Run with cad's environment (the reference side is cad's Python on the native kernel: ``document.Loaded``,
``mesh.mesh_shape``, ``mesh.Topology``, ``export.translate``). Two cores are asked the same jobs, each where given:

  --native LIB.so   the core built natively (tools/native.sh), called through its C ABI. The port's own test: every
                    answer must be the engine's bytes.
  the Node host     hosts/node/serve.mjs on the WebAssembly module, spoken to in frames as the engine would. Its
                    answers may differ from the native kernel's only as the module is known to: triangles split
                    otherwise inside faces (a mesh's index table alone), and floats in the last places.

Per file: the reading job (structure, version, each part's shape bytes and name), then per distinct part its mesh
and unmeshed faces, its table (with the mesh's unmeshed faces) and measure, its groups, ``--picks`` seeded facts of
each kind, a batch of measures, and for a few parts a mesh at an export's own ceilings; with ``--exports`` the four
files an export writes. One line per file and core, then the totals; ``--json`` writes every difference found.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import random
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare import diff, mesh as read_mesh  # noqa: E402  (the quick comparison's readers)

KINDS = {"face": 0, "edge": 1, "vertex": 2}
EXPORTS = {"step": (".step", "vc_step"), "stl": (".stl", "vc_stl"), "threemf": (".3mf", "vc_3mf"), "glb": (".glb", "vc_glb")}


class Host:
    """hosts/node/serve.mjs, one process: a job is a frame out and a frame back."""

    def __init__(self, node: str, wasm: Path) -> None:
        started = time.perf_counter()
        self.process = subprocess.Popen([node, str(HERE / "hosts/node/serve.mjs"), str(wasm)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE)
        self.ids = 0
        self.about = self.job("about")[0]
        self.start_s = time.perf_counter() - started

    def job(self, name: str, payloads: tuple = (), **header) -> tuple[dict, list[bytes]]:
        self.ids += 1
        head = json.dumps({"id": self.ids, "job": name, **header, "payloads": [len(p) for p in payloads]}).encode()
        body = struct.pack(">I", len(head)) + head + b"".join(payloads)
        self.process.stdin.write(struct.pack(">Q", len(body)) + body)
        self.process.stdin.flush()
        (length,) = struct.unpack(">Q", self._read(8))
        answer = self._read(length)
        (head_length,) = struct.unpack(">I", answer[:4])
        found = json.loads(answer[4:4 + head_length])
        if found.get("id") != self.ids:
            raise RuntimeError(f"{name}: the answer is of job {found.get('id')}, not {self.ids}")
        if not found.get("ok"):
            raise RuntimeError(f"{name}: {found.get('error')}")
        parts, at = [], 4 + head_length
        for size in found["payloads"]:
            parts.append(answer[at:at + size])
            at += size
        return found, parts

    def _read(self, count: int) -> bytes:
        data = self.process.stdout.read(count)
        if len(data) < count:
            raise EOFError("the host ended")
        return data

    def close(self) -> None:
        self.job("close")
        self.process.stdin.close()
        self.process.wait(30)

    # The jobs, as the comparison asks them.
    def read_xbf(self, path: Path):
        head, parts = self.job("read_xbf", path=str(path))
        return json.loads(parts[0]), (int(head["version"][0]), head["version"][1]), head["parts"], parts[1:]

    def mesh(self, data: bytes, tolerance=None, angle=None):
        head, parts = self.job("mesh", (data,), tolerance=tolerance, angle=angle)
        return parts[0], {int(k): v for k, v in head["unmeshed"].items()}

    def table(self, key: str, data: bytes, unmeshed: tuple, measure: bool):
        _head, parts = self.job("table", (data,), key=key, unmeshed=list(unmeshed), measure=measure)
        return parts[0], (parts[1] if measure else None)

    def fact(self, key: str, data: bytes, method: str, args: list):
        return self.job("fact", (data,), key=key, method=method, args=args)[1][0]

    def measured(self, batch: list):
        return self.job("measured", tuple(data for _key, data in batch), keys=[key for key, _data in batch])[1]

    def export(self, path: Path, kind: str) -> bytes:
        return self.job("export", path=str(path), format=kind)[1][0]


class Native:
    """The core as a shared library (tools/native.sh): the same jobs through its C ABI."""

    def __init__(self, library: Path) -> None:
        started = time.perf_counter()
        self.lib = lib = ctypes.CDLL(str(library))
        for name in ("vc_structure", "vc_shape_bytes", "vc_mesh", "vc_mesh_at", "vc_unmeshed", "vc_fact", "vc_groups",
                     "vc_table", "vc_measure", "vc_step", "vc_stl", "vc_3mf", "vc_glb"):
            getattr(lib, name).restype = ctypes.c_void_p
        lib.vc_mesh_at.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double,
                                   ctypes.POINTER(ctypes.c_uint32)]
        lib.vc_last_error.restype = ctypes.c_char_p
        lib.vc_free.argtypes = [ctypes.c_void_p]
        self.out = ctypes.c_uint32()
        self.about = {"abi": lib.vc_abi_version()}
        self.start_s = time.perf_counter() - started
        self.kept: dict[str, int] = {}

    def _result(self, name: str, *args) -> bytes:
        at = getattr(self.lib, name)(*args, ctypes.byref(self.out))
        if not at:
            raise RuntimeError(f"{name}: {self.lib.vc_last_error().decode()}")
        data = ctypes.string_at(at, self.out.value)
        self.lib.vc_free(ctypes.c_void_p(at))
        return data

    def _shape(self, data: bytes, key: str | None = None) -> int:
        if key is not None and key in self.kept:
            return self.kept[key]
        handle = self.lib.vc_open_shape(data, len(data))
        if not handle:
            raise RuntimeError(f"vc_open_shape: {self.lib.vc_last_error().decode()}")
        if key is not None:
            self.kept[key] = handle
        return handle

    def close(self) -> None:
        for handle in self.kept.values():
            self.lib.vc_close(handle)

    def read_xbf(self, path: Path):
        data, stem = path.read_bytes(), path.stem.encode()
        handle = self.lib.vc_open_xbf(data, len(data), stem, len(stem))
        if not handle:
            raise RuntimeError(f"vc_open_xbf: {self.lib.vc_last_error().decode()}")
        self.document = handle
        structure = json.loads(self._result("vc_structure", handle))
        stat = path.stat()
        listed = [{"key": p["key"], "name": p["name"]} for p in structure["prototypes"]]
        shapes = [self._result("vc_shape_bytes", handle, p["index"]) for p in structure["prototypes"]]
        return structure, (stat.st_mtime_ns, stat.st_size), listed, shapes

    def mesh(self, data: bytes, tolerance=None, angle=None):
        handle = self._shape(data)
        try:
            if tolerance is None and angle is None:
                body = self._result("vc_mesh", handle, 0)
            else:
                body = self._result("vc_mesh_at", handle, 0, float(tolerance or 0.0), float(angle or 0.0))
            said = json.loads(self._result("vc_unmeshed", handle, 0))
        finally:
            self.lib.vc_close(handle)
        return body, {int(k): v for k, v in said.items()}

    def table(self, key: str, data: bytes, unmeshed: tuple, measure: bool):
        handle = self._shape(data, key)
        ordinals = (ctypes.c_int32 * len(unmeshed))(*unmeshed)
        table = self._result("vc_table", handle, 0, ordinals, len(unmeshed))
        return table, (self._result("vc_measure", handle, 0) if measure else None)

    def fact(self, key: str, data: bytes, method: str, args: list):
        handle = self._shape(data, key)
        if method in KINDS:
            return self._result("vc_fact", handle, 0, KINDS[method], args[0])
        return self._result({"groups": "vc_groups", "measured": "vc_measure"}[method], handle, 0)

    def measured(self, batch: list):
        return [self._result("vc_measure", self._shape(data, key), 0) for key, data in batch]

    def export(self, _path: Path, kind: str) -> bytes:
        return self._result(EXPORTS[kind][1], self.document)


def compact(value) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def mesh_difference(ref: bytes, got: bytes) -> str:
    """How two XBM2 buffers differ, by table: "" for nothing but how triangles are split inside faces."""
    a, b = read_mesh(ref), read_mesh(got)
    notes = []
    if (a["magic"], a["version"], a["deflections"]) != (b["magic"], b["version"], b["deflections"]):
        notes.append("header")
    if list(a["faces"][0::3]) != list(b["faces"][0::3]):
        notes.append("face ordinals")
    if a["edges"] != b["edges"]:
        notes.append("edge table")
    if a["points"] != b["points"]:
        notes.append("edge points")
    if a["vertices"] != b["vertices"]:
        notes.append("vertices")
    if a["counts"][1] != b["counts"][1]:
        notes.append(f"triangles {a['counts'][1] // 3} -> {b['counts'][1] // 3}")
    return ", ".join(notes)


def check(core, name: str, path: Path, picks: int, exports: bool, out: Path | None) -> dict:
    from cad.engine.document import Loaded
    from cad.engine.mesh import Topology, mesh_shape, shape_bytes

    found: dict = {"file": path.name, "core": name, "parts": 0, "differences": []}
    count: dict[str, list[int]] = {}

    def tally(what: str, same: bool, note: str = "") -> None:
        held = count.setdefault(what, [0, 0])
        held[0] += 1
        held[1] += same
        if not same and len(found["differences"]) < 200:
            found["differences"].append(f"{what}: {note}")

    loaded = Loaded(path)
    # As JSON holds it: the engine's own structure keeps a colour as a tuple, which a wire gives back as a list.
    reference = json.loads(json.dumps(loaded.structure()))
    structure, version, listed, shapes = core.read_xbf(path)
    # The engine's structure is the core's with where the file is, and without what the server adds itself.
    as_engine = {"name": structure["name"], "path": str(loaded.path), "version": f"{version[0]}-{version[1]}",
                 **{k: v for k, v in structure.items() if k not in ("name", "tessellation", "closure")}}
    tally("structure", as_engine == reference, "; ".join(diff(reference, as_engine, 0.0, 0.0, ordered=False)[:3]))
    tally("version", tuple(version) == tuple(loaded.version), f"{version} != {loaded.version}")
    engine_shapes = {p.key: shape_bytes(p.shape, read=True) for p in loaded.prototypes}
    tally("names", [(p["key"], p["name"]) for p in listed] == [(p.key, p.name) for p in loaded.prototypes])
    for part, data in zip(listed, shapes):
        tally("shape bytes", engine_shapes.get(part["key"]) == data, part["key"])

    random.seed(20261128)
    batch = []
    for at, (key, data) in enumerate(engine_shapes.items()):
        found["parts"] += 1
        meshed = mesh_shape(data, parallel=False)
        body, said = core.mesh(data)
        want = meshed.to_bytes()
        if body != want:
            how = mesh_difference(want, body)
            tally("mesh", False, f"{key}: {how or 'triangles split otherwise'}")
            tally("mesh but for triangle splits", not how, f"{key}: {how}")
        else:
            tally("mesh", True)
            tally("mesh but for triangle splits", True)
        tally("unmeshed", said == meshed.unmeshed, f"{key}: {said} != {meshed.unmeshed}")
        unmeshed = tuple(sorted(meshed.unmeshed))
        topology = Topology(data)
        table = topology.elements(unmeshed)
        measure = topology.measured()
        got_table, got_measure = core.table(key, data, unmeshed, True)
        tally("table", got_table == compact(table), f"{key}")
        if got_table != compact(table):
            near = diff(table, json.loads(got_table), 1e-6, 1e-9)
            tally("table within 1e-6", not near, f"{key}: {near[:2]}")
        same = json.loads(got_measure) == measure and got_measure == compact(measure)
        tally("measure", same, f"{key}: {diff(measure, json.loads(got_measure), 0.0, 0.0)[:2]}")
        if not same:
            tally("measure within 1e-12", not diff(measure, json.loads(got_measure), 1e-12, 1e-12), key)
        tally("groups", core.fact(key, data, "groups", []) == compact(table["groups"]), key)
        for kind, plural in (("face", "faces"), ("edge", "edges"), ("vertex", "vertices")):
            total = len(table[plural])
            for ordinal in sorted(random.sample(range(1, total + 1), min(picks, total))):
                want_fact = getattr(topology, kind)(ordinal)
                got = core.fact(key, data, kind, [ordinal])
                same = got == compact(want_fact)
                tally(f"{kind} fact", same, f"{key} {kind} {ordinal}")
                if not same:
                    tally(f"{kind} fact within 1e-6", not diff(want_fact, json.loads(got), 1e-6, 1e-9), f"{key} {kind} {ordinal}")
        batch.append((key, data))
        if at < 3:  # an export's own ceilings, on the first parts
            fine = mesh_shape(data, parallel=False, tolerance=0.01, angle=10.0)
            fine_body, fine_said = core.mesh(data, 0.01, 10.0)
            if fine_body != fine.to_bytes():
                how = mesh_difference(fine.to_bytes(), fine_body)
                tally("mesh at 0.01 mm, 10 deg", False, f"{key}: {how or 'triangles split otherwise'}")
            else:
                tally("mesh at 0.01 mm, 10 deg", True)
            tally("unmeshed at 0.01 mm", fine_said == fine.unmeshed, key)
    measures = core.measured(batch)
    tally("measured batch", all(json.loads(got) == Topology(data).measured() for got, (_key, data) in
                                zip(measures, batch[:8])), "a batch's measure")
    if exports:
        from cad.engine.export import translate

        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            for kind, (suffix, _fn) in EXPORTS.items():
                target = Path(folder) / f"{path.stem}{suffix}"
                translate(path, None, target)
                got = core.export(path, kind)
                tally(f"export {kind}", got == target.read_bytes(), f"{len(got)} bytes against {target.stat().st_size}")
                if out is not None:
                    (out / f"{name}-{path.stem}{suffix}").write_bytes(got)
    found["checks"] = {what: f"{same}/{asked}" for what, (asked, same) in count.items()}
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--node", default="node")
    parser.add_argument("--wasm", type=Path, default=HERE / "dist/viewcore.wasm")
    parser.add_argument("--native", type=Path)
    parser.add_argument("--no-host", action="store_true", help="ask the native library alone")
    parser.add_argument("--picks", type=int, default=12)
    parser.add_argument("--exports", action="store_true")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--keep", type=Path, help="a folder for the exports each core wrote")
    args = parser.parse_args()
    cores = []
    if args.native:
        cores.append(("native", Native(args.native)))
    if not args.no_host:
        cores.append(("node", Host(args.node, args.wasm)))
    if args.keep:
        args.keep.mkdir(parents=True, exist_ok=True)
    reports, totals = [], {}
    for path in args.files:
        for name, core in cores:
            report = check(core, name, path.resolve(), args.picks, args.exports, args.keep)
            reports.append(report)
            print(json.dumps({k: v for k, v in report.items() if k != "differences"}), flush=True)
            for what, said in report["checks"].items():
                same, asked = map(int, said.split("/"))
                held = totals.setdefault(name, {}).setdefault(what, [0, 0])
                held[0] += same
                held[1] += asked
    for name, core in cores:
        core.close()
        print(name, json.dumps({what: f"{same}/{asked}" for what, (same, asked) in totals[name].items()}))
    if args.json:
        args.json.write_text(json.dumps(reports, indent=1))
    exact = all(same == asked for what, (same, asked) in totals.get("native", {}).items())
    sys.exit(0 if exact else 1)


if __name__ == "__main__":
    main()
