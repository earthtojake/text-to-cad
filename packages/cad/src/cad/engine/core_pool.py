"""The engine's pool jobs on the view core: the kernel's reading side compiled to WebAssembly by itself.

Where the engine's kernel is the WebAssembly one (``places.kernel``: ``wasm``) and its kernel folder carries the
view core's job server (``core``: a program that speaks the frames below on its standard streams), the meshing and
reading pools are a ``CorePool``: the jobs the core answers -- a part meshed, its table, its measures, an element's
facts, an ``.xbf`` read -- go to a process of that server, a few hundred megabytes that is ready in a fraction of a
second, and answer what the engine's own job answers. What it does not answer -- a foreign file read (STEP, DXF, a
robot's description), a structure posed -- goes to a kernel process as before (``kernel_pool.KernelPool``), started
only for the first such job.

A frame, both ways: 8 bytes, the length of the rest (big-endian); 4 bytes, the header's length; the header, one JSON
object; then the payloads end to end, their lengths the header's ``payloads``. A request is ``{"id", "job", ...}``;
its answer ``{"id", "ok": true, ...}`` or ``{"id", "ok": false, "error"}``: what the core refuses (bytes that are no
shape, an ordinal the part has not) is the job's error, a ``ValueError`` in its words, and the process goes on.
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
from pathlib import Path
from typing import Any, Callable

from cad.engine.kernel_pool import KernelPool, _Job

__all__ = ["PROCESSES", "CorePool", "request"]

# The most processes one pool holds: each is a small host, and meshing is what a page waits for.
PROCESSES = 4
_SIZES = struct.Struct(">QI")
# The pools' first jobs, which load a kernel process's kernel: the core's process is ready as it starts.
_WARMERS = {"_ready": True, "int": 0}


def _text(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def request(fn: Callable, args: tuple) -> tuple[dict[str, Any], list[bytes], Callable[[dict[str, Any], list[bytes]], Any]] | None:
    """The core's job for the engine's ``fn(*args)`` (one of ``serve``'s pool jobs, told by its name): its header,
    its payloads, and what makes ``fn``'s own answer of the core's; None for a job the core does not answer."""
    name = getattr(fn, "__name__", "")
    if name in _WARMERS:
        return {"job": "about"}, [], lambda _head, _payloads: _WARMERS[name]
    if getattr(fn, "__module__", "") != "cad.engine.serve":
        return None
    if name == "_timed" and isinstance(args[0], (bytes, bytearray, memoryview)):
        return ({"job": "mesh"}, [bytes(args[0])],
                lambda head, payloads: (payloads[0], {int(ordinal): why for ordinal, why in head["unmeshed"].items()},
                                        float(head["seconds"])))
    if name == "_table":
        key, data, unmeshed, measure = (*args, (), False)[:4] if len(args) < 4 else args
        return ({"job": "table", "key": key, "unmeshed": [int(ordinal) for ordinal in unmeshed], "measure": bool(measure)},
                [bytes(data)],
                lambda _head, payloads: (payloads[0], json.loads(payloads[1]) if measure else None))
    if name == "_measured":
        (batch,) = args
        keys = [key for key, _data in batch]
        return ({"job": "measured", "keys": keys}, [bytes(data) for _key, data in batch],
                lambda _head, payloads: [(key, json.loads(found)) for key, found in zip(keys, payloads)])
    if name == "_topology_fact":
        key, data, method, given = args
        if method not in ("face", "edge", "vertex", "groups", "elements", "measured"):
            return None
        return ({"job": "fact", "key": key, "method": method, "args": [list(one) if isinstance(one, tuple) else one
                                                                          for one in given]},
                [bytes(data)], lambda _head, payloads: json.loads(payloads[0]))
    if name == "_read_document" and str(args[0]).lower().endswith(".xbf"):
        path = str(args[0])
        return {"job": "read_xbf", "path": path}, [], lambda head, payloads: _document(path, head, payloads)
    return None


def _document(path: str, head: dict[str, Any], payloads: list[bytes]) -> tuple:
    """``serve._read_document``'s answer from the core's: the structure as ``document.Loaded.structure`` makes it
    (its path as it was asked, its version of the file's time and size, colours as tuples), the file's version,
    and each part's shape bytes and name by its key."""
    read = json.loads(payloads[0])
    version = (int(head["version"][0]), int(head["version"][1]))
    structure = {"name": read.pop("name", Path(path).stem), "path": str(Path(path).resolve()),
                 "version": f"{version[0]}-{version[1]}"}
    for dropped in ("path", "version", "tessellation", "closure"):
        read.pop(dropped, None)
    structure.update(read)
    for prototype in structure.get("prototypes") or ():
        _colours(prototype, "color")
        for ordinal, colour in (prototype.get("faceColors") or {}).items():
            if isinstance(colour, list):
                prototype["faceColors"][ordinal] = tuple(colour)
    for instance in structure.get("instances") or ():
        _colours(instance, "color")
    parts = head["parts"]
    return (structure, version, {part["key"]: shape for part, shape in zip(parts, payloads[1:])},
            {part["key"]: part["name"] for part in parts})


def _colours(holder: dict[str, Any], name: str) -> None:
    if isinstance(holder.get(name), list):
        holder[name] = tuple(holder[name])


class CorePool(KernelPool):
    """``workers`` processes of the view core's job server at most (``PROCESSES`` at most), each started for the
    first job no started one is free for and kept; ``program``: what starts one (the kernel folder's own
    launcher); ``kernel``: what makes the kernel pool for the jobs the core does not answer, called for the first
    of them."""

    MOST = PROCESSES

    def __init__(self, workers: int, program: str, kernel: Callable[[], Any]) -> None:
        super().__init__(workers, program, [])
        self._kernel, self._others = kernel, None
        self._asked = 0

    def submit(self, fn: Callable, /, *args: Any) -> Any:
        if request(fn, args) is None:
            with self._wake:
                if self._stopped:
                    raise RuntimeError("cannot schedule new futures after shutdown")
                if self._others is None:
                    self._others = self._kernel()
                others = self._others
            return others.submit(fn, *args)
        return super().submit(fn, *args)

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        super().shutdown(wait, cancel_futures=cancel_futures)
        if self._others is not None:
            self._others.shutdown(wait, cancel_futures=cancel_futures)

    def terminate_workers(self) -> None:
        super().terminate_workers()
        if self._others is not None:
            self._others.terminate_workers()

    def _start(self) -> subprocess.Popen:
        from cad.engine import places

        return subprocess.Popen([self.python], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=dict(os.environ),
                                **places.windowless())

    def _ask(self, child: subprocess.Popen, job: _Job) -> tuple[str, Any]:
        header, payloads, answered = request(job.fn, job.args)  # type: ignore[misc] - asked in ``submit``
        self._asked += 1
        head = _text({**header, "id": self._asked, "payloads": [len(payload) for payload in payloads]})
        child.stdin.write(_SIZES.pack(4 + len(head) + sum(map(len, payloads)), len(head)))
        child.stdin.write(head)
        for payload in payloads:
            child.stdin.write(payload)
        child.stdin.flush()
        sizes = child.stdout.read(_SIZES.size)
        if len(sizes) < _SIZES.size:
            raise EOFError
        length, head_length = _SIZES.unpack(sizes)
        body = child.stdout.read(length - 4)
        if len(body) < length - 4:
            raise EOFError
        said = json.loads(body[:head_length])
        if not said.get("ok"):
            return "failed", ValueError(str(said.get("error") or "the view core refused the job"))
        found, at = [], head_length
        for size in said.get("payloads") or ():
            found.append(body[at:at + size])
            at += size
        return "done", answered(said, found)
