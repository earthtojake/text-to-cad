"""Run the view core on .xbf files under wasmtime and write what it answers, in bench/reference.py's layout.

    python tools/smoke.py [--wasm dist/viewcore.wasm | --native libviewcore.so] [--picks 100] OUT_DIR FILE.xbf [...]

Per document, in OUT_DIR/<file stem>/: structure.json, timing.json, parts/<index>/{key, shape.bin, mesh.xbm,
elements.json, groups.json, measure.json}. Parts sharing a key hold the same files, as the reference's do. timing.json
holds seconds per stage (module compile and instantiate, open, structure, then shape bytes, mesh, elements and measure
summed over the distinct keys), vc_fact's median latency over random picks (all, a part's first, later ones) and the
instance's memory at the end. One thread, one instance per document.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import struct
import sys
import time
from pathlib import Path

import wasmtime

HERE = Path(__file__).resolve().parent.parent


class Core:
    def __init__(self, wasm: Path):
        t = time.perf_counter()
        config = wasmtime.Config()
        config.wasm_exceptions = True
        self.engine = wasmtime.Engine(config)
        module = wasmtime.Module.from_file(self.engine, str(wasm))
        self.compile_s = time.perf_counter() - t
        t = time.perf_counter()
        linker = wasmtime.Linker(self.engine)
        linker.define_wasi()
        self.store = wasmtime.Store(self.engine)
        wasi = wasmtime.WasiConfig()
        wasi.inherit_stdout()
        wasi.inherit_stderr()
        self.store.set_wasi(wasi)
        self.instance = linker.instantiate(self.store, module)
        self.exports = self.instance.exports(self.store)
        self.exports["_initialize"](self.store)
        self.memory = self.exports["memory"]
        self.instantiate_s = time.perf_counter() - t
        self.out_len = self.call("vc_alloc", 4)

    def call(self, name, *args):
        return self.exports[name](self.store, *args)

    def error(self) -> str:
        at = self.call("vc_last_error")
        data = self.memory.read(self.store, at, at + 4096)
        return bytes(data[: data.index(0)]).decode()

    def result(self, name, *args) -> bytes:
        at = self.call(name, *args, self.out_len)
        if not at:
            raise RuntimeError(f"{name}{args}: {self.error()}")
        size = struct.unpack("<I", bytes(self.memory.read(self.store, self.out_len, self.out_len + 4)))[0]
        data = bytes(self.memory.read(self.store, at, at + size))
        self.call("vc_free", at)
        return data

    def open(self, data: bytes, stem: str = "") -> int:
        name = stem.encode()
        at = self.call("vc_alloc", len(data) + len(name))
        self.memory.write(self.store, data + name, at)
        handle = self.call("vc_open_xbf", at, len(data), at + len(data), len(name))
        self.call("vc_free", at)
        if not handle:
            raise RuntimeError(f"vc_open_xbf: {self.error()}")
        return handle


class NativeCore:
    """The same ABI from a native shared library (tools/native.sh): the core's C++ on the native kernel, to tell a
    difference of the port from one of WebAssembly."""

    def __init__(self, library: Path):
        import ctypes

        t = time.perf_counter()
        self.lib = ctypes.CDLL(str(library))
        self.compile_s, self.instantiate_s = 0.0, time.perf_counter() - t
        self.ctypes = ctypes
        u32p = ctypes.POINTER(ctypes.c_uint32)
        for name in ("vc_structure", "vc_shape_bytes", "vc_mesh", "vc_fact", "vc_groups", "vc_elements", "vc_measure"):
            getattr(self.lib, name).restype = ctypes.c_void_p
        self.lib.vc_last_error.restype = ctypes.c_char_p
        self.lib.vc_free.argtypes = [ctypes.c_void_p]
        self.out_len = ctypes.c_uint32()
        self.u32p = u32p

    def call(self, name, *args):
        return getattr(self.lib, name)(*args)

    def error(self) -> str:
        return self.lib.vc_last_error().decode()

    def result(self, name, *args) -> bytes:
        at = getattr(self.lib, name)(*args, self.ctypes.byref(self.out_len))
        if not at:
            raise RuntimeError(f"{name}{args}: {self.error()}")
        data = self.ctypes.string_at(at, self.out_len.value)
        self.lib.vc_free(self.ctypes.c_void_p(at))
        return data

    def open(self, data: bytes, stem: str = "") -> int:
        name = stem.encode()
        handle = self.lib.vc_open_xbf(data, len(data), name, len(name))
        if not handle:
            raise RuntimeError(f"vc_open_xbf: {self.error()}")
        return handle


def dump(core, path: Path, out: Path, picks: int) -> dict:
    timing = {"compile_s": core.compile_s, "instantiate_s": core.instantiate_s}
    data = path.read_bytes()
    t = time.perf_counter(); doc = core.open(data, path.stem); timing["open_s"] = time.perf_counter() - t
    t = time.perf_counter(); structure = core.result("vc_structure", doc); timing["structure_s"] = time.perf_counter() - t
    out.mkdir(parents=True, exist_ok=True)
    (out / "structure.json").write_bytes(structure)
    prototypes = json.loads(structure)["prototypes"]
    stages = {"shape_bytes_s": 0.0, "mesh_s": 0.0, "elements_s": 0.0, "measure_s": 0.0}
    done: dict[str, Path] = {}
    counts = []
    for prototype in prototypes:
        index = prototype["index"]
        folder = out / "parts" / str(index)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "key").write_text(prototype["key"])
        if prototype["key"] in done:
            for name in ("shape.bin", "mesh.xbm", "elements.json", "groups.json", "measure.json"):
                (folder / name).write_bytes((done[prototype["key"]] / name).read_bytes())
            continue
        for stage, name, file in (("shape_bytes_s", "vc_shape_bytes", "shape.bin"), ("mesh_s", "vc_mesh", "mesh.xbm"),
                                  ("elements_s", "vc_elements", "elements.json"), ("measure_s", "vc_measure", "measure.json")):
            t = time.perf_counter(); body = core.result(name, doc, index); stages[stage] += time.perf_counter() - t
            (folder / file).write_bytes(body)
        (folder / "groups.json").write_bytes(core.result("vc_groups", doc, index))
        elements = json.loads((folder / "elements.json").read_bytes())
        counts.append((index, len(elements["faces"]), len(elements["edges"]), len(elements["vertices"])))
        done[prototype["key"]] = folder
    timing.update(stages)
    # A pick: one element's facts, on a part already asked once (its topology read), random parts and elements.
    rng = random.Random(1)
    cold, warm, seen = [], [], set()  # a part's first pick reads its topology from the bytes; later ones do not
    for _ in range(picks):
        index, faces, edges, vertices = rng.choice(counts)
        kind = rng.choice([k for k, n in ((0, faces), (1, edges), (2, vertices)) if n])
        ordinal = rng.randint(1, (faces, edges, vertices)[kind])
        t = time.perf_counter(); core.result("vc_fact", doc, index, kind, ordinal)
        (warm if index in seen else cold).append(time.perf_counter() - t)
        seen.add(index)
    if cold or warm:
        timing["fact_median_s"] = statistics.median(cold + warm)
    if cold:
        timing["fact_cold_median_s"] = statistics.median(cold)
    if warm:
        timing["fact_warm_median_s"] = statistics.median(warm)
    core.call("vc_close", doc)
    if isinstance(core, Core):  # the instance's linear memory at its peak (wasm memory never shrinks)
        timing["memory_mb"] = core.memory.data_len(core.store) / 2**20
    timing = {k: round(v, 6) for k, v in timing.items()}
    timing.update(parts=len(prototypes), keys=len(done), instances=len(json.loads(structure)["instances"]))
    (out / "timing.json").write_text(json.dumps(timing))
    return {"file": path.name, **timing}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--wasm", type=Path, default=HERE / "dist" / "viewcore.wasm")
    parser.add_argument("--native", type=Path, help="a native build of the core (tools/native.sh) instead")
    parser.add_argument("--picks", type=int, default=100)
    parser.add_argument("out", type=Path)
    parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    for name in args.files:
        core = NativeCore(args.native) if args.native else Core(args.wasm)  # a fresh instance per document, so each one's timings start cold
        print(json.dumps(dump(core, name.resolve(), args.out / name.stem, args.picks)), flush=True)
