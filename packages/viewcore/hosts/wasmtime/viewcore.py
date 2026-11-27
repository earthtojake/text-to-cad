"""Python host of the view core (viewcore.wasm) on wasmtime.

    core = Core("dist/viewcore.wasm")        # compiles once (cache=path keeps the serialized module)
    doc = core.open_xbf(open("m.xbf", "rb").read(), "m")
    doc.structure(); doc.mesh(0); doc.fact(0, "face", 1); doc.close()

Every Core holds one Store and one instance (one thread): use one Core per thread/process, or `Pool` for batches.
Errors raise `ViewCoreError` carrying vc_last_error's text.
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
        self.module = module or compile_module(self.engine, path, cache)
        self.compile_s = time.perf_counter() - t
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
        if abi != 2:
            raise ViewCoreError(f"unsupported ABI version {abi}")

    # -- plumbing -----------------------------------------------------------------------------------------------
    def _call(self, name, *args):
        r = self._x[name](self.store, *[_i32(a) for a in args])
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

    def memory_bytes(self) -> int:
        return self.memory.data_len(self.store)


class Doc:
    def __init__(self, core: Core, handle: int):
        self.core, self.handle = core, handle

    def _j(self, what, name, *args):
        return json.loads(self.core._result(what, name, self.handle, *args))

    def structure(self) -> dict:
        return self._j("vc_structure", "vc_structure")

    def shape_bytes(self, part: int) -> bytes:
        return self.core._result("vc_shape_bytes", "vc_shape_bytes", self.handle, part)

    def mesh(self, part: int) -> bytes:
        return self.core._result("vc_mesh", "vc_mesh", self.handle, part)

    def fact_bytes(self, part: int, kind, ordinal: int) -> bytes:
        k = KINDS[kind] if isinstance(kind, str) else kind
        return self.core._result("vc_fact", "vc_fact", self.handle, part, k, ordinal)

    def fact(self, part: int, kind, ordinal: int) -> dict:
        return json.loads(self.fact_bytes(part, kind, ordinal))

    def groups_bytes(self, part: int) -> bytes:
        return self.core._result("vc_groups", "vc_groups", self.handle, part)

    def groups(self, part: int) -> dict:
        return json.loads(self.groups_bytes(part))

    def elements_bytes(self, part: int) -> bytes:
        return self.core._result("vc_elements", "vc_elements", self.handle, part)

    def elements(self, part: int) -> dict:
        return json.loads(self.elements_bytes(part))

    def measure_bytes(self, part: int) -> bytes:
        return self.core._result("vc_measure", "vc_measure", self.handle, part)

    def measure(self, part: int) -> dict:
        return json.loads(self.measure_bytes(part))

    def close(self):
        if self.handle:
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
