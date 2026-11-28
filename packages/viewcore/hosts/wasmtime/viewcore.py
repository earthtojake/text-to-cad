"""Python host of the view core (viewcore.wasm) on wasmtime.

    core = Core("dist/viewcore.wasm")        # compiles once (cache=path keeps the serialized module)
    doc = core.open_xbf(open("m.xbf", "rb").read(), "m")
    doc.structure(); doc.mesh(0); doc.fact(0, "face", 1); doc.close()

Every Core holds one Store and one instance (one thread): use one Core per thread/process, or `Pool` for batches.
Errors raise `ViewCoreError` carrying vc_last_error's text. A call the module faults on (a trap: bytes OCCT reads out
of bounds) raises it too, and the Core starts a fresh instance of the same compiled module: a Doc opened before refuses
from then on. The module needs WebAssembly's 128-bit SIMD (wasmtime has it on by default).
"""
from __future__ import annotations

import json
import os
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import wasmtime

KINDS = {"face": 0, "edge": 1, "vertex": 2}


class ViewCoreError(RuntimeError):
    pass


def _i32(v: int) -> int:
    """An unsigned 32-bit value as wasm's i32 argument."""
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v >= 1 << 31 else v


def _int32(value, what: str) -> int:
    """A signed 32-bit argument (an ordinal, a part's place): a whole number in range, never one wrapped."""
    if isinstance(value, bool) or not isinstance(value, int) or not -(1 << 31) <= value < 1 << 31:
        raise ViewCoreError(f"{what} is not a 32-bit whole number: {value!r}")
    return value


# The least WebAssembly module with a 128-bit SIMD instruction: an engine that cannot validate it cannot run the core.
SIMD_PROBE = bytes([0, 97, 115, 109, 1, 0, 0, 0, 1, 5, 1, 96, 0, 1, 123, 3, 2, 1, 0, 10, 22, 1, 20, 0, 253, 12]
                   + [0] * 16 + [11])


def make_engine() -> wasmtime.Engine:
    cfg = wasmtime.Config()
    cfg.wasm_exceptions = True
    return wasmtime.Engine(cfg)


def compile_module(engine: wasmtime.Engine, path, cache: str | None = None) -> wasmtime.Module:
    path = Path(path)
    if cache:
        c = Path(cache)
        if c.exists() and c.stat().st_mtime >= path.stat().st_mtime:
            try:
                return wasmtime.Module.deserialize_file(engine, str(c))
            except Exception:
                pass
        module = wasmtime.Module.from_file(engine, str(path))
        c.write_bytes(module.serialize())
        return module
    return wasmtime.Module.from_file(engine, str(path))


class Core:
    def __init__(self, path, *, engine: wasmtime.Engine | None = None, module: wasmtime.Module | None = None,
                 cache: str | None = None):
        t = time.perf_counter()
        self.engine = engine or make_engine()
        try:
            wasmtime.Module.validate(self.engine, SIMD_PROBE)
        except wasmtime.WasmtimeError:
            raise ViewCoreError("this wasmtime has no 128-bit SIMD, which the view core needs") from None
        self.module = module or compile_module(self.engine, path, cache)
        self.compile_s = time.perf_counter() - t
        self.generation = 0  # a Doc opened in another generation is gone with the instance it lived in
        self._instantiate()

    def _instantiate(self):
        t = time.perf_counter()
        self.store = wasmtime.Store(self.engine)
        linker = wasmtime.Linker(self.engine)
        linker.define_wasi()
        wasi = wasmtime.WasiConfig()
        wasi.inherit_stderr()
        self.store.set_wasi(wasi)
        self.instance = linker.instantiate(self.store, self.module)
        self._x = self.instance.exports(self.store)
        self.memory = self._x["memory"]
        init = self._x.get("_initialize")
        if init is not None:
            init(self.store)
        self.instantiate_s = time.perf_counter() - t
        self._len = self._call("vc_alloc", 4)  # the out-length cell, reused
        abi = self.abi_version
        if abi != 4:
            raise ViewCoreError(f"unsupported ABI version {abi}")

    # -- plumbing -----------------------------------------------------------------------------------------------
    def _call(self, name, *args):
        return self._raw(name, *[_i32(a) for a in args])

    def _raw(self, name, *args):
        """A call into the module as it is; a trap starts a fresh instance and is refused."""
        try:
            r = self._x[name](self.store, *args)
        except wasmtime.Trap as trap:
            self.generation += 1
            self._instantiate()
            raise ViewCoreError(f"the view core faulted in {name} ({trap.message.splitlines()[0] if trap.message else 'a trap'}) "
                                "and was started again; documents opened before are let go") from None
        return None if r is None else r & 0xFFFFFFFF

    def _read(self, ptr: int, n: int) -> bytes:
        return self.memory.read(self.store, ptr, ptr + n)

    def _cstr(self, ptr: int) -> str:
        if not ptr:
            return ""
        out = bytearray()
        step = 256
        at = ptr
        size = self.memory.data_len(self.store)
        while at < size:
            chunk = self.memory.read(self.store, at, min(at + step, size))
            i = chunk.find(b"\0")
            if i >= 0:
                out += chunk[:i]
                break
            out += chunk
            at += step
        return out.decode("utf-8", "replace")

    @property
    def abi_version(self) -> int:
        return self._call("vc_abi_version")

    @property
    def occt_version(self) -> str:
        return self._cstr(self._call("vc_occt_version"))

    def last_error(self) -> str:
        return self._cstr(self._call("vc_last_error"))

    def _fail(self, what: str):
        raise ViewCoreError(f"{what}: {self.last_error() or 'unknown error'}")

    def _result(self, what: str, name: str, *args) -> bytes:
        """Call a vc_* function that returns a core buffer and writes its length to the out pointer."""
        ptr = self._call(name, *args, self._len)
        if not ptr:
            self._fail(what)
        n = struct.unpack("<I", self._read(self._len, 4))[0]
        data = self._read(ptr, n)
        self._call("vc_free", ptr)
        return data

    def open_xbf(self, data: bytes, stem: str = "") -> "Doc":
        """Open an .xbf's bytes; ``stem`` names the document where its file does not (the file's stem)."""
        n = len(data)
        name = stem.encode()
        ptr = self._call("vc_alloc", n + len(name))
        if not ptr and n:
            self._fail("vc_alloc")
        try:
            self.memory.write(self.store, data + name, ptr)
            h = self._call("vc_open_xbf", ptr, n, ptr + n, len(name))
        finally:
            self._call("vc_free", ptr)
        if not h:
            self._fail("vc_open_xbf")
        return Doc(self, h)

    def open_shape(self, data: bytes) -> "Doc":
        """A part's canonical shape bytes opened by themselves (the engine's pool jobs): a Doc of one part, index 0."""
        ptr = self._call("vc_alloc", len(data))
        if not ptr and data:
            self._fail("vc_alloc")
        try:
            self.memory.write(self.store, data, ptr)
            h = self._call("vc_open_shape", ptr, len(data))
        finally:
            self._call("vc_free", ptr)
        if not h:
            self._fail("vc_open_shape")
        return Doc(self, h)

    def render(self, scene: dict, payloads: list[bytes] | tuple = ()) -> bytes:
        """A still drawn in software (``vc_render``): ``scene`` as include/viewcore.h says it, ``payloads`` the
        buffers it names by their place in this list. Width x height RGBA bytes, sRGB, the top row first; or a PNG
        where the scene's ``format`` is ``"png"``."""
        text = json.dumps({**scene, "payloads": [len(p) for p in payloads]}, separators=(",", ":")).encode()
        blob = b"".join(payloads)
        ptr = self._call("vc_alloc", len(text) + len(blob))
        if not ptr:
            self._fail("vc_alloc")
        try:
            self.memory.write(self.store, text + blob, ptr)
            return self._result("vc_render", "vc_render", ptr, len(text), ptr + len(text), len(blob))
        finally:
            self._call("vc_free", ptr)

    def memory_bytes(self) -> int:
        return self.memory.data_len(self.store)


# The exports the core writes, by cad's kind name (``export.KINDS``), each its vc_* function.
EXPORTS = {"step": "vc_step", "stl": "vc_stl", "threemf": "vc_3mf", "glb": "vc_glb"}


class Doc:
    def __init__(self, core: Core, handle: int):
        self.core, self.handle, self.generation = core, handle, core.generation

    @property
    def h(self) -> int:
        """The handle, where the document still lives (not closed, not let go with a faulted instance)."""
        if not self.handle:
            raise ViewCoreError("the document is closed")
        if self.generation != self.core.generation:
            raise ViewCoreError("the document was let go when the core faulted: open it again")
        return self.handle

    def _j(self, what, name, *args):
        return json.loads(self.core._result(what, name, self.h, *args))

    def structure(self) -> dict:
        return self._j("vc_structure", "vc_structure")

    def export(self, kind: str) -> bytes:
        """The whole document as a file, as ``cad export`` writes it: ``kind`` one of ``EXPORTS``."""
        name = EXPORTS[kind]
        return self.core._result(name, name, self.h)

    def shape_bytes(self, part: int) -> bytes:
        return self.core._result("vc_shape_bytes", "vc_shape_bytes", self.h, _int32(part, "a part"))

    def mesh(self, part: int) -> bytes:
        return self.core._result("vc_mesh", "vc_mesh", self.h, _int32(part, "a part"))

    def mesh_at(self, part: int, tolerance: float | None = None, angle: float | None = None) -> bytes:
        """The part meshed to an export's own ceilings (mm, degrees), never kept: ``mesh_shape(..., tolerance, angle)``."""
        ptr = self.core._raw("vc_mesh_at", self.h, _int32(part, "a part"), float(tolerance or 0.0), float(angle or 0.0),
                             _i32(self.core._len))
        if not ptr:
            self.core._fail("vc_mesh_at")
        n = struct.unpack("<I", self.core._read(self.core._len, 4))[0]
        data = self.core._read(ptr, n)
        self.core._call("vc_free", ptr)
        return data

    def unmeshed(self, part: int) -> dict:
        """The faces the part's last mesh left without triangles: ``{ordinal: what was said of it}``."""
        found = self._j("vc_unmeshed", "vc_unmeshed", _int32(part, "a part"))
        return {int(ordinal): text for ordinal, text in found.items()}

    def table_bytes(self, part: int, unmeshed=()) -> bytes:
        """The part's whole table with the caller's unmeshed ordinals checked: ``Topology.elements(unmeshed)``."""
        ordinals = struct.pack(f"<{len(unmeshed)}i", *(_int32(o, "an unmeshed ordinal") for o in unmeshed))
        ptr = self.core._call("vc_alloc", len(ordinals))
        try:
            self.core.memory.write(self.core.store, ordinals, ptr)
            return self.core._result("vc_table", "vc_table", self.h, _int32(part, "a part"), ptr, len(unmeshed))
        finally:
            self.core._call("vc_free", ptr)

    def fact_bytes(self, part: int, kind, ordinal: int) -> bytes:
        k = KINDS[kind] if isinstance(kind, str) else kind
        if k not in (0, 1, 2):
            raise ViewCoreError(f"no kind {kind!r}: face, edge or vertex")
        return self.core._result("vc_fact", "vc_fact", self.h, _int32(part, "a part"), k, _int32(ordinal, "an ordinal"))

    def fact(self, part: int, kind, ordinal: int) -> dict:
        return json.loads(self.fact_bytes(part, kind, ordinal))

    def groups_bytes(self, part: int) -> bytes:
        return self.core._result("vc_groups", "vc_groups", self.h, _int32(part, "a part"))

    def groups(self, part: int) -> dict:
        return json.loads(self.groups_bytes(part))

    def elements_bytes(self, part: int) -> bytes:
        return self.core._result("vc_elements", "vc_elements", self.h, _int32(part, "a part"))

    def elements(self, part: int) -> dict:
        return json.loads(self.elements_bytes(part))

    def measure_bytes(self, part: int) -> bytes:
        return self.core._result("vc_measure", "vc_measure", self.h, _int32(part, "a part"))

    def measure(self, part: int) -> dict:
        return json.loads(self.measure_bytes(part))

    def close(self):
        if self.handle and self.generation == self.core.generation:
            self.core._call("vc_close", self.handle)
        self.handle = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class Pool:
    """N independent Core instances (each with its own Store, sharing one compiled module) for parallel batch work.

        pool = Pool(path, 4); results = pool.map(lambda core, item: ..., items)
    Wasmtime releases the GIL while wasm runs, so threads give real parallelism.
    """

    def __init__(self, path, n: int = 4, cache: str | None = None):
        engine = make_engine()
        module = compile_module(engine, path, cache)
        self.cores = [Core(path, engine=engine, module=module) for _ in range(n)]
        self._exec = ThreadPoolExecutor(n)

    def map(self, fn, items):
        items = list(items)
        n = len(self.cores)
        def run(i):
            core = self.cores[i]
            return [(j, fn(core, items[j])) for j in range(i, len(items), n)]
        out = [None] * len(items)
        for part in self._exec.map(run, range(n)):
            for j, r in part:
                out[j] = r
        return out
