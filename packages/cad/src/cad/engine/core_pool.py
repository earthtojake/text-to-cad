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

Each job has a deadline by its kind (``SECONDS``): a host that has not answered by then -- a job that never ends on
input it cannot handle, which would hold every job behind it, since a host serves one at a time --, one that answers
what is no frame, and one whose module trapped (``TRAPS``: its instance may be damaged) is killed and waited for
(``exchange``, ``HostFailed``), and the job answered in one line; the next job starts another host, which is sent what
the last kept (each job carries its part's bytes; the stills' meshes by key, ``render.core.Core``).
"""

from __future__ import annotations

import json
import os
import re
import select
import struct
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from cad.engine.kernel_pool import KernelPool, _Job

__all__ = ["PROCESSES", "SECONDS", "TRAPS", "CorePool", "HostEnded", "HostFailed", "exchange", "request"]

# The most processes one pool holds: each is a small host, and meshing is what a page waits for.
PROCESSES = 4
_SIZES = struct.Struct(">QI")
# The pools' first jobs, which load a kernel process's kernel: the core's process is ready as it starts.
_WARMERS = {"_ready": True, "int": 0}
#: How long a job of each kind may take the host, in seconds: many times what the largest part or picture measured
#: takes on a loaded machine (a 249-part assembly's every part meshed in seconds, a Preview at full size 1.5 s).
SECONDS = {"about": 30.0, "mesh": 300.0, "table": 120.0, "measured": 120.0, "fact": 60.0, "read_xbf": 300.0,
           "export": 300.0, "render": 120.0, "forget": 30.0, "close": 10.0}
#: What a host says when its WebAssembly module trapped: its instance may be damaged, so the host is started afresh.
TRAPS = re.compile(r"RuntimeError|memory access out of bounds|unreachable|signature mismatch|call stack|out of memory|"
                   r"integer overflow|divide by zero", re.IGNORECASE)
# A frame no host writes: longer than this is garbage (the host passes a longer one over itself).
_LONGEST = 1 << 34


class HostFailed(Exception):
    """The view core's job server stopped answering in time, answered what is no frame, or ended: it has been killed
    and waited for. Its words are the job's answer, in one line."""


class HostEnded(HostFailed):
    """The view core's job server ended during a job (its pipe closed): waited for."""


def _killed(child: subprocess.Popen) -> None:
    """``child`` killed (by its process) and waited for, its pipes closed."""
    try:
        child.kill()
    except OSError:
        pass
    try:
        child.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass
    for stream in (child.stdin, child.stdout):
        try:
            if stream is not None:
                stream.close()
        except OSError:
            pass


def _write(fd: int, frame: bytes, deadline: float | None) -> None:
    view = memoryview(frame)
    while view:
        if deadline is not None:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([], [fd], [], left)[1]:
                raise TimeoutError
        try:
            view = view[os.write(fd, view[:1 << 16]):]
        except BlockingIOError:
            continue


def _read(fd: int, count: int, deadline: float | None) -> bytes:
    found = bytearray()
    while len(found) < count:
        if deadline is not None:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([fd], [], [], left)[0]:
                raise TimeoutError
        chunk = os.read(fd, min(count - len(found), 1 << 20))
        if not chunk:
            raise EOFError
        found += chunk
    return bytes(found)


def exchange(child: subprocess.Popen, header: dict[str, Any], payloads: list[bytes],
             seconds: float | None = None) -> tuple[dict[str, Any], list[bytes]]:
    """``header`` (with its ``payloads``) asked of the host ``child`` and its answer read, within ``seconds`` (by the
    job's kind, ``SECONDS``): the answer's header and payloads, a refusal (``ok`` false) among them. ``HostFailed``,
    the host killed and waited for, where it is late, ends, or answers what is no frame. Where pipes cannot be waited
    on with a deadline (Windows), the job has none."""
    job = str(header.get("job"))
    seconds = SECONDS.get(job, 120.0) if seconds is None else seconds
    head = _text({**header, "payloads": [len(payload) for payload in payloads]})
    frame = b"".join([_SIZES.pack(4 + len(head) + sum(map(len, payloads)), len(head)), head, *payloads])
    deadline = None if os.name == "nt" else time.monotonic() + seconds
    try:
        written, reading = child.stdin.fileno(), child.stdout.fileno()
        child.stdin.flush()
        if deadline is not None:
            os.set_blocking(written, False)
        _write(written, frame, deadline)
        length, head_length = _SIZES.unpack(_read(reading, _SIZES.size, deadline))
        if length < 4 or head_length > length - 4 or length > _LONGEST:
            raise ValueError("no frame")
        body = _read(reading, length - 4, deadline)
        said = json.loads(body[:head_length])
        if not isinstance(said, dict):
            raise ValueError("no frame")
        found, at = [], head_length
        for size in said.get("payloads") or ():
            found.append(body[at:at + int(size)])
            at += int(size)
        if at > len(body):
            raise ValueError("no frame")
        return said, found
    except TimeoutError:
        _killed(child)
        raise HostFailed(f"the view core took longer than {seconds:g} s for its {job} job, and was stopped: ask "
                         "again (a smaller picture, or fewer parts, is sooner)") from None
    except (EOFError, BrokenPipeError, ConnectionError):
        _killed(child)
        raise HostEnded(f"the view core's job server ended during its {job} job") from None
    except (ValueError, TypeError, struct.error):  # json's errors are ValueErrors
        _killed(child)
        raise HostFailed(f"the view core's job server answered its {job} job with what is no answer, and was "
                         "stopped") from None


def trapped(child: subprocess.Popen, said: dict[str, Any]) -> str | None:
    """Where the host refused a job because its module trapped (``TRAPS``): the host killed and waited for, and the
    job's answer in one line; else None."""
    error = str(said.get("error") or "")
    if said.get("ok") or not TRAPS.search(error):
        return None
    _killed(child)
    return f"the view core failed its {said.get('job') or 'job'} ({error.splitlines()[0] if error else 'a trap'}), " \
           "and was started afresh: ask again"


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
        """The job asked of ``child`` (``exchange``): its answer; a host that was late, garbled or trapped is killed
        here (the pool's next job starts another) and the job refused in one line."""
        header, payloads, answered = request(job.fn, job.args)  # type: ignore[misc] - asked in ``submit``
        self._asked += 1
        try:
            said, found = exchange(child, {**header, "id": self._asked}, payloads)
        except HostEnded:
            raise EOFError from None  # a process that died fails its job alone, as a kernel process's does
        except HostFailed as failed:
            return "failed", ValueError(str(failed))
        broken = trapped(child, said)
        if broken is not None:
            return "failed", ValueError(broken)
        if not said.get("ok"):
            return "failed", ValueError(str(said.get("error") or "the view core refused the job"))
        return "done", answered(said, found)
