"""Serving documents over HTTP: the structure as JSON, each part as one binary buffer.

``GET /api/docs`` lists the documents served, each by its id (``ids``: a file's ``file_id``,
a model's ``model_id``, by which every map here is keyed); ``GET /api/doc/<id>`` is one document's
structure (``document.Loaded.structure``): its parts with their names, keys, colours,
materials and element names, its instances with world matrices, its tree, and its version, and
for each part already meshed the faces its mesher left without triangles
(``unmeshed``) with ``BRepCheck``'s verdict on each (``unmeshedCheck``);
``GET /api/doc/<id>/version?after=V&progress=N&wait=S`` answers ``{"version", "patch",
"building", "failed", "progress"}`` once the version is not ``V``, or the count ``progress`` is
not ``N`` (without ``progress=``, the version alone is waited on), or after ``S`` seconds:
``building`` is the last progress frame of the build writing the document now (``progress.py``;
null when none is), ``failed`` the last build of it that failed (``{"model", "error",
"progress"}``: its error and where it was; null once one succeeds or another begins), and
``progress`` a count that moves whenever either does (``building``, ``built``), which the page
sends back to wait for the next; ``GET /api/doc/<id>/part/<key>`` is one part's tessellation
(``mesh.Mesh.to_bytes``), held in memory by the part's geometry key, so a part that two
documents, two versions of one document or ten instances share is meshed once;
``GET /api/doc/<id>/part/<key>/face|edge|vertex/<ordinal>`` is what the kernel measures
of that element, now (``mesh.Topology``), and ``made_by``: the element's name, the feature
that made it, its operation, and the function, file and line of that feature's call,
asked of the worker that built the document (``provenance``) -- never read from a file, so
a document served cold, with no live worker that built it, answers null;
``GET /api/doc/<id>/part/<key>/groups`` is how a pick of one face or edge grows (each face's
tangent group, each edge's chain: ``mesh.Topology.groups``); ``.../volume`` the part's volume
in cubic millimetres, what its mass is weighed from (``mesh.Topology.volume``); ``POST /api/doc/<id>/mesh`` meshes every part
not held yet, in parallel, and answers how long that took. ``POST /api/doc/<id>/pose``
with ``{"pose": NAME | {joint or coupling: value}}`` serves the document at that pose under an id of
its own (``<id>~<digest>``): its structure's instances where the mechanism places them,
every other route the document's; what the pose names wrong is refused by name (400).
The structure carries the document's mechanism as ``kinematics`` (``mechanism.block``),
from which a page poses it itself. ``GET /api/look`` is the look the regular display modes
draw a document in (``render/look.py``), which a page lights and dresses its scene by, and
``GET /api/look/environment`` the image its environment is. ``/`` is a page that shows
one (``page/``), with three.js served from a ``node_modules`` folder (``--three``, or the
nearest one above the working directory).

**The document stays in memory.** A document is read from its file once, when it is first
served. After that a model's worker hands the daemon each build's document as a patch
(``patch``): its structure, the buffers of the parts the worker meshed, and the shape
bytes of parts the daemon holds no shape for; the document is replaced in memory and the
page, waiting on the version, is answered at once. The file is read again only when some
other process rewrote it: its modification time and size are compared when the version
is asked for, except while a build is writing it (``hold``).

**A STEP is read in a reader process, held by its bytes.** OCCT's XCAF reader works in many
times the memory of what it makes and its allocator keeps most of it, so the server never
parses a ``.step``/``.stp`` itself: a reader process of its own does (``_read_foreign``, one
read per process, the next one started and warm meanwhile) and answers the structure and each
part's shape bytes, which are all the server keeps. The read is held by the file's bytes
(``FOREIGN_HELD`` of them): the same bytes served again -- the file touched, copied, or put
back -- are not parsed again while the server lives, and their parts' keys (and so their
meshes) are the same. A STEP is read outside the server's lock, so every other document is
served meanwhile; one rewritten while it is served is read again in the background, and the
page keeps the old version until the new one is in. Its structure says how long the parse
took and which process made it (``read``).

Meshing runs off the request's thread (``Mesher``): by default on a pool of processes
started with the first page or view (``warm``) or the first mesh, topology or pose asked, and
kept warm, each handed one part's shape bytes; or ``inline``
(``CADGEN_ENGINE_MESH=inline``, or ``?mode=inline``), one part after another on one thread,
each spread over the kernel's own threads. A document's parts go to the pool largest
first, by their shape bytes (of face count, bounding diagonal and bytes, the bytes
predicted a part's mesh time best), and a part of ``PARALLEL_BYTES`` or more is meshed
with the kernel's face parallelism inside its pool process. When a page asks for a
document's structure, every part not held is sent to the pool at once, so the page's part
requests join meshes already running.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import itertools
import json
import math
import mimetypes
import os
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from cadgen.engine.access import allow_origin
from cadgen.engine.render.look import LOOK

__all__ = ["MeshCache", "NotHeld", "PARALLEL_BYTES", "Pressure", "Served", "Server", "find_three", "memory_budget"]

from cadgen.engine.addresses import document_id, key as document_key
from cadgen.engine.ids import canonical, file_id, is_id

PAGE = Path(__file__).resolve().parent / "page"
# A part whose shape bytes reach this is meshed with the kernel's face parallelism inside
# its pool process: measured one part at a time on two large documents, parts above it
# meshed 1.1-1.5x faster with it and parts below it no faster, some slower. (A whole
# document on the pool moved within the noise of a loaded machine either way: what sets
# its wall is its largest part, often one face the kernel cannot split.)
PARALLEL_BYTES = 500_000
# How long a version request waits for a new version at most, in seconds.
WAIT_LIMIT = 60.0
# A pose request's body at most, in bytes, and how many posed ids the engine keeps (the most
# recently made; an older one's page asks again): a pose is a name or a few joint values.
POSE_BODY_LIMIT = 64 << 10
POSES_HELD = 1024
# A page remains connected between successive version reads, including a suspended poll.
LIVE = 90.0
# A file this engine did not write, read by a reader process (the module docstring).
FOREIGN = (".step", ".stp")
# How many STEP reads are held by their bytes: a read a served document holds stays in memory
# with it whatever this says; past it, the least recently served read goes.
FOREIGN_HELD = 8


def find_three(start: Path | None = None) -> Path | None:
    """The ``three`` package folder: ``CADGEN_ENGINE_THREE``, else the nearest
    ``node_modules/three`` above ``start`` (the working directory) or above this file."""
    override = os.environ.get("CADGEN_ENGINE_THREE")
    if override:
        return Path(override)
    for base in (Path(start or os.getcwd()).resolve(), Path(__file__).resolve()):
        for folder in (base, *base.parents):
            candidate = folder / "node_modules" / "three"
            if (candidate / "build" / "three.module.js").is_file():
                return candidate
    return None


class MeshCache:
    """Part tessellations in memory, by geometry key; with each, the faces its mesher left
    without triangles and why. On its own (a worker's, a render process's) the least recently
    used is dropped past ``cap`` bytes. The daemon's server holds it under its one memory budget
    instead (``cap`` None, ``Server.trim``), told of every buffer put (``grown``)."""

    def __init__(self, cap: int | None = 2 << 30) -> None:
        self.cap = cap
        self.items: "OrderedDict[str, bytes]" = OrderedDict()
        self.notes: dict[str, dict[int, str]] = {}
        self.size = 0
        self.lock = threading.Lock()
        self.pending: dict[str, concurrent.futures.Future] = {}
        self.grown: Callable[[], None] | None = None

    def get(self, key: str) -> bytes | None:
        with self.lock:
            found = self.items.get(key)
            if found is not None:
                self.items.move_to_end(key)
            return found

    def keys(self) -> list[str]:
        with self.lock:
            return list(self.items)

    def unmeshed(self, key: str) -> dict[int, str] | None:
        """The faces of a held part its mesher left without triangles, by ordinal: their
        ``BRepCheck`` verdicts. None for a part not held."""
        with self.lock:
            return self.notes.get(key) if key in self.items else None

    def drop(self, keys: Any) -> None:
        """Forget these parts' tessellations (``POST .../mesh?drop=1``: mesh them again)."""
        with self.lock:
            for key in keys:
                found = self.items.pop(key, None)
                self.notes.pop(key, None)
                if found is not None:
                    self.size -= len(found)

    def put(self, key: str, data: bytes, unmeshed: dict[int, str] | None = None) -> None:
        with self.lock:
            if key in self.items:
                self.items.move_to_end(key)
                return
            self.items[key] = data
            self.notes[key] = dict(unmeshed or {})
            self.size += len(data)
            while self.cap is not None and self.size > self.cap and len(self.items) > 1:
                old, dropped = self.items.popitem(last=False)
                self.notes.pop(old, None)
                self.size -= len(dropped)
        grown = self.grown
        if grown is not None:
            grown()

    def oldest(self) -> list[str]:
        """The keys held, the least recently used first."""
        with self.lock:
            return list(self.items)

    def evict(self, key: str) -> int:
        """Forget one part's tessellation: the bytes it held."""
        with self.lock:
            found = self.items.pop(key, None)
            self.notes.pop(key, None)
            if found is None:
                return 0
            self.size -= len(found)
            return len(found)


# The process's one mesh cache: the daemon's server serves from it, and in a worker the
# build's patch, its exports and a snapshot it draws all take a part's buffer from it.
MESHES = MeshCache()


# --- the memory budget ---------------------------------------------------------------------
#
# Everything the daemon holds -- every served document's structure, shape bytes and data, and
# the tessellations -- is held under one budget (the engine's **Document lifetime**). Past it,
# what is held is evicted down to ``TRIM`` of it; on the operating system's memory-pressure
# signal, down to the low-water mark, ``LOW_WATER`` of it.

TRIM = 0.8
LOW_WATER = 0.5
# How often the pressure signal is asked, in seconds.
PRESSURE_PERIOD = 2.0


def _cgroup_limit() -> int | None:
    """The memory limit of this process's cgroup (v2), in bytes; None where it has none."""
    try:
        with open("/proc/self/cgroup", encoding="utf-8") as handle:
            group = next((line.split(":", 2)[2].strip() for line in handle if line.startswith("0::")), None)
        if group is None:
            return None
        with open(f"/sys/fs/cgroup{group}/memory.max", encoding="utf-8") as handle:
            text = handle.read().strip()
    except (OSError, IndexError):
        return None
    return int(text) if text.isdigit() else None


def memory_budget() -> int:
    """The daemon's memory budget, in bytes: ``CADGEN_ENGINE_MEMORY_MB``, else a quarter of the
    machine's physical memory (of its cgroup's limit, when that is less), else 4 GiB where neither
    can be read."""
    try:
        given = float(os.environ.get("CADGEN_ENGINE_MEMORY_MB", "").strip() or 0)
    except ValueError:
        given = 0.0
    if given > 0:
        return int(given * 2**20)
    from cadgen.engine.worker import _physical_mb

    physical = _physical_mb()
    total = None if physical is None else int(physical * 2**20)
    limit = _cgroup_limit() if sys.platform.startswith("linux") else None
    if limit is not None:
        total = limit if total is None else min(total, limit)
    return total // 4 if total else 4 << 30


class Pressure:
    """The operating system's memory-pressure signal, polled (``under``): macOS's
    ``kern.memorystatus_vm_pressure_level`` (``sysctlbyname``: 1 normal, 2 warning, 4 critical),
    Windows' low-memory resource notification (``CreateMemoryResourceNotification``, asked with
    ``QueryMemoryResourceNotification``), Linux's pressure stall information (the cgroup's
    ``memory.pressure``, else ``/proc/pressure/memory``: ``some avg10`` past ``PSI_SOME``). None of
    them anywhere else, or unreadable: never under pressure, and the budget alone applies.
    ``simulate`` is the test hook: it answers in place of the system's signal and wakes the poller."""

    PSI_SOME = 10.0

    def __init__(self) -> None:
        self.simulated: bool | None = None
        self.wake = threading.Event()
        self._windows: Any = None

    def simulate(self, under: bool | None) -> None:
        self.simulated = under
        self.wake.set()

    def under(self) -> bool:
        if self.simulated is not None:
            return self.simulated
        try:
            if sys.platform == "darwin":
                return self._darwin()
            if os.name == "nt":
                return self._windows_low()
            if sys.platform.startswith("linux"):
                return self._linux()
        except (AttributeError, OSError, ValueError):
            return False
        return False

    @staticmethod
    def _darwin() -> bool:
        import ctypes

        system = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        level, length = ctypes.c_int(0), ctypes.c_size_t(ctypes.sizeof(ctypes.c_int))
        if system.sysctlbyname(b"kern.memorystatus_vm_pressure_level", ctypes.byref(level), ctypes.byref(length),
                               None, 0) != 0:
            return False
        return level.value >= 2

    def _windows_low(self) -> bool:
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.windll.kernel32
        if self._windows is None:
            kernel.CreateMemoryResourceNotification.argtypes = [ctypes.c_int]
            kernel.CreateMemoryResourceNotification.restype = wintypes.HANDLE
            kernel.QueryMemoryResourceNotification.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
            kernel.QueryMemoryResourceNotification.restype = wintypes.BOOL
            self._windows = kernel.CreateMemoryResourceNotification(0) or False  # LowMemoryResourceNotification
        if not self._windows:
            return False
        state = wintypes.BOOL(0)
        return bool(kernel.QueryMemoryResourceNotification(self._windows, ctypes.byref(state))) and bool(state.value)

    def _linux(self) -> bool:
        paths = []
        try:
            with open("/proc/self/cgroup", encoding="utf-8") as handle:
                group = next((line.split(":", 2)[2].strip() for line in handle if line.startswith("0::")), None)
            if group:
                paths.append(f"/sys/fs/cgroup{group}/memory.pressure")
        except (OSError, IndexError):
            pass
        paths.append("/proc/pressure/memory")
        for path in paths:
            try:
                with open(path, encoding="utf-8") as handle:
                    for line in handle:
                        if line.startswith("some "):
                            fields = dict(item.split("=", 1) for item in line.split()[1:])
                            return float(fields.get("avg10", 0)) > self.PSI_SOME
            except OSError:
                continue
        return False


class NotHeld(ValueError):
    """A document the engine knows but no longer holds: its ``state`` (``evicted``, ``expired``)
    and the command that builds it again (``rebuild``), which the engine never runs."""

    def __init__(self, text: str, state: str = "evicted", rebuild: str | None = None) -> None:
        super().__init__(text)
        self.state, self.rebuild = state, rebuild

    def payload(self) -> dict[str, Any]:
        return {"error": str(self), "state": self.state, "rebuild": self.rebuild}


# --- the pools ---------------------------------------------------------------------------
#
# The kernel's mesher holds the interpreter's lock for the whole of a call (measured: ten
# threads mesh no faster than one), so parts are meshed in parallel two ways: ``inline``,
# one part after another, each call spreading that part's faces over the kernel's own
# threads; or ``processes``, a pool started on its first job or ``Server.warm`` -- never
# with the server, which every build starts -- and kept warm, each job one
# part's shape handed over as the kernel's binary shape bytes -- no process reads a
# document, so a large document costs its parts' bytes, not one read per process.


def _timed(shape: Any, parallel: bool) -> tuple[bytes, dict[int, str], float]:
    """One part meshed (a shape, or its ``mesh.shape_bytes``): its buffer, its unmeshed
    faces, and the seconds it took. A pool process's job."""
    from cadgen.engine.mesh import mesh_shape

    started = time.perf_counter()
    found = mesh_shape(shape, parallel=parallel)
    return found.to_bytes(), found.unmeshed, time.perf_counter() - started


def exit_with_parent() -> None:
    """A pool process's start (meshing, reading): it exits once the process that started it is
    gone, however that one ended -- ``cadgen stop``, a signal, a crash -- so no pool process
    outlives its engine (or its worker) holding the kernel's memory."""
    import multiprocessing

    parent = multiprocessing.parent_process()
    if parent is None:
        return

    def watch() -> None:
        parent.join()
        os._exit(0)

    threading.Thread(target=watch, name="cadgen-parent-watch", daemon=True).start()


def _ready() -> bool:
    """A pool process's first job: import the kernel, so the first part waits on nothing."""
    import cadgen.engine.mesh  # noqa: F401

    return True


MODES = ("inline", "processes")


class Mesher:
    def __init__(self, mode: str | None = None, workers: int | None = None) -> None:
        self.mode = mode or os.environ.get("CADGEN_ENGINE_MESH", "processes")
        if self.mode not in MODES:
            raise ValueError(f"CADGEN_ENGINE_MESH is one of {', '.join(MODES)}")
        self.workers = workers or max(1, (os.cpu_count() or 2))
        # One thread runs inline meshing: the kernel's threads are its parallelism.
        self._inline = concurrent.futures.ThreadPoolExecutor(1, thread_name_prefix="mesh")
        self._processes: concurrent.futures.ProcessPoolExecutor | None = None
        self.lock = threading.Lock()

    def processes(self) -> concurrent.futures.ProcessPoolExecutor:
        """The pool, started on its first use: a build serves its document with no page open,
        and a pool started then would hold ``workers`` kernels nobody asked for."""
        with self.lock:
            if self._processes is not None and getattr(self._processes, "_broken", False):
                self._processes.shutdown(wait=False, cancel_futures=True)  # a child died; rebuild on next use
                self._processes = None
            if self._processes is None:
                import multiprocessing

                self._processes = concurrent.futures.ProcessPoolExecutor(
                    self.workers, mp_context=multiprocessing.get_context("spawn"), initializer=exit_with_parent)
                for _ in range(self.workers):
                    self._processes.submit(_ready)
            return self._processes

    def submit(self, data: bytes, mode: str | None = None) -> concurrent.futures.Future:
        """One part meshed from its ``shape_bytes``: a future of its buffer, its unmeshed
        faces and the seconds it took."""
        if (mode or self.mode) == "processes":
            return self.processes().submit(_timed, data, len(data) >= PARALLEL_BYTES)
        return self._inline.submit(_timed, data, True)

    def stop(self) -> None:
        self._inline.shutdown(wait=False, cancel_futures=True)
        if self._processes is not None:
            self._processes.shutdown(wait=False, cancel_futures=True)


def _triangles(data: bytes) -> int:
    from cadgen.engine.mesh_format import HEADER

    return HEADER.unpack_from(data)[3] // 3


# Kernel jobs return only serializable values. Daemon request threads never own kernel objects.
_TOPOLOGIES: OrderedDict = OrderedDict()


def shape_bytes(shape, **kwargs):
    # Only worker jobs and the standalone snapshot server can own live shapes.
    from cadgen.engine.mesh import shape_bytes as encode
    return encode(shape, **kwargs)


def _read_document(path: str) -> tuple:
    from cadgen.engine.document import Loaded

    loaded = Loaded(Path(path))
    return (loaded.structure(), loaded.version,
            {p.key: shape_bytes(p.shape, read=True) for p in loaded.prototypes},
            {p.key: p.name for p in loaded.prototypes})


def _topology_fact(key: str, data: bytes, method: str, args: tuple) -> Any:
    from cadgen.engine.mesh import Topology

    found = _TOPOLOGIES.get(key)
    if found is None:
        found = _TOPOLOGIES[key] = Topology(data)
    _TOPOLOGIES.move_to_end(key)
    while len(_TOPOLOGIES) > 32:
        _TOPOLOGIES.popitem(last=False)
    return getattr(found, method)(*args)


class _RemoteTopology:
    def __init__(self, pool, key: str, data: bytes) -> None:
        self.pool, self.key, self.data = pool, key, data

    def __getattr__(self, method: str):
        if method not in {"face", "edge", "vertex", "groups", "volume"}:
            raise AttributeError(method)
        return lambda *args: self.pool.submit(_topology_fact, self.key, self.data, method, args).result()


def _pose_structure(structure: dict, pose: Any) -> dict:
    from cadgen.engine.mechanism import posed_structure

    return posed_structure(structure, pose)


# --- a STEP's reader process ----------------------------------------------------------------


def _reader_ready() -> None:
    """A reader process's start: the kernel and the reader imported, so its read waits on nothing."""
    exit_with_parent()
    import cadgen.engine.document  # noqa: F401
    import cadgen.engine.mesh  # noqa: F401


def _read_foreign(path: str, digest: str) -> dict[str, Any]:
    """A STEP read into a document in a reader process (the module docstring): its structure,
    each part's shape bytes by a key made from the file's bytes (``digest``) and the part's label,
    whether the document is named by the file's stem (several free shapes), the seconds the read
    took and the process that made it. A reader process's job."""
    from OCP.TDF import TDF_LabelSequence
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    from cadgen.engine.document import Loaded

    started = time.perf_counter()
    loaded = Loaded(Path(path))
    keys = {p.key: f"step-{digest[:20]}-{p.entry}" for p in loaded.prototypes}
    structure = loaded.structure()
    structure["prototypes"] = [{**prototype, "key": keys[prototype["key"]]} for prototype in structure["prototypes"]]
    shapes = {keys[p.key]: shape_bytes(p.shape, read=True) for p in loaded.prototypes}
    free = TDF_LabelSequence()
    XCAFDoc_DocumentTool.ShapeTool_s(loaded.doc.Main()).GetFreeShapes(free)
    return {"structure": structure, "shapes": shapes, "stem": free.Length() != 1,
            "seconds": round(time.perf_counter() - started, 4), "process": os.getpid()}


def _digest(path: Path) -> str:
    """The file's bytes, digested: what a STEP's read is held by."""
    found = hashlib.blake2b(digest_size=20)
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            found.update(chunk)
    return found.hexdigest()


# --- the documents -----------------------------------------------------------------------


@dataclass
class Served:
    """One document as the server holds it: its structure (no meshing facts), its
    version, the file state it reflects, and each part's shape by key -- a live shape when
    the document was read from its file, the shape's bytes when a worker sent it."""

    ident: str
    path: Path | str
    structure: dict[str, Any]
    stat: tuple | None
    shapes: dict[str, Any]
    names: dict[str, str]
    patch: dict[str, Any] | None = None
    data: dict[str, bytes] = field(default_factory=dict)  # shape bytes made from live shapes
    # A model's whole document, as the xbf bytes its worker made of it before it retired (the
    # drain): what an export, a snapshot or an inspection of it reads once no worker holds it.
    xbf: bytes | None = None
    _size: int | None = field(default=None, repr=False, compare=False)

    @property
    def version(self) -> str:
        return self.structure["version"]

    @property
    def size(self) -> int:
        """The bytes it holds, as the memory budget counts them: its structure as JSON, its shape
        bytes, the bytes made from its live shapes (a live shape itself is not counted) and its
        whole document's xbf bytes (its animations' record among them)."""
        if self._size is None:
            self._size = (len(json.dumps(self.structure, separators=(",", ":"), default=str))
                          + sum(len(shape) for shape in self.shapes.values() if isinstance(shape, (bytes, bytearray)))
                          + sum(len(made) for made in self.data.values()) + len(self.xbf or b""))
        return self._size

    def shape_data(self, key: str) -> bytes | None:
        """A part's shape bytes: made once from the shape its file read gave."""
        found = self.shapes.get(key)
        if found is None or isinstance(found, (bytes, bytearray)):
            return found
        made = self.data.get(key)
        if made is None:
            made = self.data[key] = shape_bytes(found, read=True)
            self._size = None
        return made


def _stat(path: Path | str) -> tuple | None:
    if isinstance(path, str):
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


# --- the server --------------------------------------------------------------------------


def reachable_host(host: str) -> str:
    """Where a client on this machine reaches a listener bound on ``host``, as a URL spells it.

    A wildcard bind (every interface: ``0.0.0.0``, ``""``, ``::``) is reached at loopback: a
    browser refuses to open ``http://0.0.0.0:...``. The bind itself is unchanged."""
    if host in ("", "0.0.0.0"):
        return "127.0.0.1"
    if host == "::":
        return "[::1]"
    return f"[{host}]" if ":" in host else host


class Server:
    def __init__(self, port: int = 0, three: str | None = None, touch: Callable[[], None] = lambda: None,
                 host: str = "127.0.0.1", mesh_mode: str | None = None,
                 provenance: Callable[[str, str, str, int], dict[str, Any] | None] | None = None,
                 cache: MeshCache | None = None, isolated: bool = False, http_factory=None,
                 budget: int | None = None) -> None:
        # Every document by its id (``ids``): a file's ``file_id``, a model's ``model_id``. A model
        # registered but not opened yet is a loader (its name, its load and its version) until
        # a page asks for it.
        self.served: dict[str, Served] = {}
        self.model_loaders: dict[str, tuple[str, Callable, int]] = {}
        # Every on-disk file a page or a launcher opened, by its id: its canonical path (``remember``).
        # Process memory only: what a page's ``/<id>`` names and an evicted file is read again
        # from, under the same id; never a record on disk.
        self.files: dict[str, str] = {}
        self.model_versions: dict[str, int] = {}
        self.model_locks: dict[str, threading.Lock] = {}
        # The daemon's server and a worker's snapshot serve from the process's one cache
        # (``MESHES``); a server of its own (a test's) holds its own.
        self.cache = cache if cache is not None else MeshCache()
        # The one memory budget (bytes) over the documents and the tessellations held, or None:
        # a server of its own (a worker's snapshot, a test's) keeps the cache's own cap.
        self.budget = budget
        self.used: dict[str, int] = {}  # each served document's last use, for least recently used
        self.uses = itertools.count(1)
        self.trim_lock = threading.Lock()
        self.evictions = 0
        self.pressure = Pressure()
        self.stopping = threading.Event()
        # What the engine knows of a document it no longer holds (``NotHeld.payload``), else None.
        self.lost: Callable[[str], dict[str, Any] | None] = lambda _ident: None
        # A document id this server does not hold yet, taken up from the engine's cache where it has
        # it (``models.Models.adopt``): registered, and read when it is asked for.
        self.revive: Callable[[str], None] = lambda _ident: None
        # Whether a model document no worker holds was built from code that changed since
        # (``models.Models.stale``): ``{"text", "changes", "rebuild"}``, said in its structure, or None.
        self.stale: Callable[[str], dict[str, Any] | None] = lambda _ident: None
        # Each model document whose cache file is at the version held (``cache``): read again from
        # disk when evicted, it is in the budget's first tier with the files.
        self.on_disk: dict[str, Any] = {}
        if budget is not None:
            self.cache.cap = None
            self.cache.grown = self._grown
        self.isolated = isolated
        self.mesher = Mesher("processes" if isolated else mesh_mode,
                             workers=1 if isolated and (mesh_mode or os.environ.get("CADGEN_ENGINE_MESH")) == "inline" else None)
        self.three = Path(three) if three else find_three()
        self.touch = touch
        self.clients_active = lambda: False
        self.on_close = lambda: None
        self.provenance = provenance
        self.load_lock = threading.RLock()
        self.held: dict[str, int] = {}
        self.changed = threading.Condition()
        self.watch_lock = threading.Lock()
        self.watchers: dict[str, int] = {}
        self.synced: dict[str, float] = {}
        self.generation = 0
        self.topologies: "OrderedDict[str, Any]" = OrderedDict()
        self.topology_lock = threading.Lock()
        # A document served at a pose (``POST /api/doc/<id>/pose``): its id, the document's and the pose.
        self.poses: OrderedDict[str, tuple[str, Any]] = OrderedDict()  # at most POSES_HELD
        # STEP reads (the module docstring): held by the file's bytes, each read once however
        # many ask for it at a time, by a reader process started on the first.
        self.foreign: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        self.foreign_reads: dict[str, concurrent.futures.Future] = {}
        self.foreign_lock = threading.Lock()
        self.reader: concurrent.futures.ProcessPoolExecutor | None = None
        # A served STEP being read again in the background, and one whose file could not be read
        # as it stands (by its state): it is read again once the file changes.
        self.rereading: set[str] = set()
        self.unreadable: dict[str, tuple | None] = {}
        # Per served document (its id), its build: the last progress frame of the build writing it
        # now, the last build of it that failed, and a count that moves with either (``build_of``).
        self.builds: dict[str, dict[str, Any]] = {}
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802
                server.touch()
                server.route(self, "GET")

            def do_POST(self) -> None:  # noqa: N802
                server.touch()
                server.route(self, "POST")

        try:
            self.http = (http_factory(self, host, port) if http_factory is not None
                         else ThreadingHTTPServer((host, port), Handler))
        except BaseException:
            self.mesher.stop()  # a listener that could not bind leaves no meshing pool behind
            raise
        self.http.daemon_threads = True
        self.port = self.http.server_address[1]
        self.url = f"http://{reachable_host(host)}:{self.port}"
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        if self.budget is not None:
            threading.Thread(target=self._pressured, name="cadgen-memory-pressure", daemon=True).start()

    def _pressured(self) -> None:
        """The pressure poller: each ``PRESSURE_PERIOD`` (or when woken), the system's signal; under
        pressure, what is held is evicted down to the low-water mark."""
        while not self.stopping.is_set():
            self.pressure.wake.wait(PRESSURE_PERIOD)
            self.pressure.wake.clear()
            if self.stopping.is_set():
                return
            if self.pressure.under():
                self.trim(int(self.budget * LOW_WATER))

    def warm(self) -> None:
        """The processes a first document waits on, started now (a viewer's launch and an app's
        view ask it): the meshing pool, and a STEP reader when none has read
        yet -- a reader takes one read and goes, so a no-op takes the first and the one a read
        takes starts warm meanwhile."""
        if self.mesher.mode == "processes":
            self.mesher.processes()
        with self.foreign_lock:
            started = self.reader is not None
        if not started:
            self._readers().submit(int)

    def stop(self) -> None:
        self.stopping.set()
        self.pressure.wake.set()
        if self.thread is not None:  # shutdown waits for a loop that runs
            self.http.shutdown()
        self.http.server_close()
        self.on_close()
        self.mesher.stop()
        with self.foreign_lock:
            reader, self.reader = self.reader, None
        if reader is not None:
            reader.shutdown(wait=False, cancel_futures=True)

    # --- documents -------------------------------------------------------------------

    def add(self, path: Path) -> str:
        """Serve the document at ``path`` (or a live model's id): its id."""
        path = document_key(path)
        ident = document_id(path)
        if isinstance(path, str):
            if not self.holds(ident):
                raise ValueError(f"no document {path} is held")
            return ident
        self.remember(path)
        if path.suffix.lower() in FOREIGN:
            # Read outside the lock: a STEP's read is long, and every other document is served
            # meanwhile. Two first opens of one file share its one read (``_foreign``).
            with self.load_lock:
                if ident in self.served:
                    return ident
            served = self._read(ident, path)  # a document that cannot be read is the caller's error
            with self.load_lock:
                if ident not in self.served:
                    self.served[ident] = served
                    self.used[ident] = next(self.uses)
            self._grown(ident)
            return ident
        with self.load_lock:
            if ident not in self.served:
                self.served[ident] = self._read(ident, path)  # a document that cannot be read is the caller's error
                self.used[ident] = next(self.uses)
        self._grown(ident)
        return ident

    def put(self, path: Path | str, structure: dict[str, Any], shapes: dict[str, Any], *, grow: bool = True) -> str:
        """Serve a document held in memory (a build's, which a worker draws), at ``path`` (a
        file, or a model's id): its structure and each part's shape (or shape bytes) by
        key. No file is read for it. Its id."""
        path = document_key(path)
        ident = document_id(path)
        with self.load_lock:
            self.served[ident] = Served(ident, path, structure, _stat(path), dict(shapes),
                                        {p["key"]: p["name"] for p in structure["prototypes"]})
            self.used[ident] = next(self.uses)
        self._changed()
        if grow:
            self._grown(ident)
        return ident

    def keep(self, ident: str, structure: dict[str, Any], shapes: dict[str, Any], version: int,
             xbf: bytes) -> None:
        """A model's document, version ``version``, held from now on whatever becomes of its worker
        (the daemon's drain: ``models.Models.drain``): its served structure and shapes, and the whole
        document as ``xbf`` bytes, its animations' record with it. Evicted, all of it goes."""
        lock = self.model_locks.setdefault(ident, threading.Lock())
        with lock:
            with self.load_lock:
                doc = self.served[self.put(ident, structure, shapes, grow=False)]
                doc.xbf, doc._size = xbf, None  # counted again, its xbf bytes with it
                self.model_versions[ident] = version
        self._grown()

    def has(self, ident: str, version: int, whole: bool = False) -> bool:
        """Whether a model's document is held at ``version`` (``whole``: with its xbf bytes)."""
        with self.load_lock:
            found = self.served.get(ident)
            return (found is not None and self.model_versions.get(ident) == version
                    and (not whole or found.xbf is not None))

    def holds(self, ident: str) -> bool:
        """Whether a document of this id is served, or registered to be (a live model's), or is a
        file this server read once, read again when asked (``document``)."""
        return ident in self.served or ident in self.model_loaders or ident in self.files

    def path_of(self, ident: str) -> Path | str:
        """The path of a file served, or the id of a model served or registered."""
        with self.load_lock:
            found = self.served.get(ident)
            if found is not None:
                return found.path
            if ident in self.model_loaders:
                return ident
            raise KeyError(ident)

    def remember(self, path: Path | str) -> str:
        """An on-disk file a page or a launcher opens, known by its id from now on: its id."""
        found = canonical(path)
        ident = file_id(found)
        with self.load_lock:
            self.files[ident] = found
        return ident

    def file_of(self, ident: str) -> str | None:
        """The canonical path of the on-disk file of id ``ident`` this server knows, else None."""
        with self.load_lock:
            found = self.files.get(ident)
            served = self.served.get(ident)
        if found is None and served is not None and not isinstance(served.path, str):
            found = str(served.path)
        return found

    def register_model(self, ident: str, label: str, load: Callable, version: int) -> str:
        """A live model's document, by its id, opened on demand: ``load`` asks its worker.
        ``label`` names it (its function's name)."""
        with self.load_lock:
            self.model_loaders[ident] = (label, load, version)
            self.model_locks.setdefault(ident, threading.Lock())
        self._changed()
        return ident

    def forget_model(self, ident: str) -> None:
        with self.load_lock:
            self.served.pop(ident, None)
            self.model_loaders.pop(ident, None)
            self.model_versions.pop(ident, None)
            self.used.pop(ident, None)
            self.on_disk.pop(ident, None)
        self._changed()

    def listing(self, every: bool = False) -> list[dict[str, Any]]:
        """The documents served, each its id and path; ``every``: with each the bytes it holds, and
        the files it read and evicted too (``state`` ``held`` or ``evicted``)."""
        with self.load_lock:
            if not every:
                return [{"id": ident, "path": str(doc.path)} for ident, doc in self.served.items()]
            found = [{"id": ident, "path": str(doc.path), "state": "held", "bytes": doc.size}
                     for ident, doc in self.served.items()]
            found += [{"id": ident, "path": path, "state": "evicted", "bytes": 0}
                      for ident, path in self.files.items() if ident not in self.served]
            return found

    def memory(self) -> dict[str, Any]:
        """What the budget counts: the documents' bytes, the tessellations' and the budget's."""
        with self.load_lock:
            documents = sum(doc.size for doc in self.served.values())
        return {"budget": self.budget, "documents": documents, "meshes": self.cache.size,
                "evictions": self.evictions}

    # --- the memory budget -------------------------------------------------------------

    def holding(self) -> int:
        """The bytes held under the budget: every served document's and every tessellation's."""
        with self.load_lock:
            documents = sum(doc.size for doc in self.served.values())
        return documents + self.cache.size

    def _grown(self, spare: str | None = None) -> None:
        """Something was put: past the budget, what is held is evicted (``trim``), never ``spare``
        (the document being served now)."""
        if self.budget is not None and self.holding() > self.budget:
            self.trim(int(self.budget * TRIM), spare)

    def _tier(self, ident: str) -> int:
        """A document's eviction tier: 0 one the engine reads again itself -- a file, or a model
        document whose cache file is at the version held (``on_disk``) -- 1 everything else."""
        doc = self.served.get(ident)
        if doc is not None and isinstance(doc.path, Path) and ident not in self.model_loaders:
            return 0
        version = self.on_disk.get(ident)
        return 0 if version is not None and version == self.model_versions.get(ident) else 1

    def trim(self, target: int, spare: str | None = None) -> list[str]:
        """Evict until what is held is ``target`` bytes or less (the engine's **Document
        lifetime**): tessellations first, least recently used first, then documents -- files the
        engine reads again itself, then every other, least recently used first within each --
        never a document a page watches, nor its tessellations, nor ``spare``. The ids evicted."""
        evicted: list[str] = []
        with self.trim_lock:
            watched = self.watched()
            with self.load_lock:
                kept = {ident for ident in watched if ident in self.served}
                if spare is not None:
                    kept.add(spare)
                spared = {key for ident in kept if ident in self.served for key in self.served[ident].shapes}
            total = self.holding()
            for key in self.cache.oldest():
                if total <= target:
                    break
                if key not in spared:
                    total -= self.cache.evict(key)
            with self.load_lock:
                order = sorted((ident for ident in self.served if ident not in kept),
                               key=lambda ident: (self._tier(ident), self.used.get(ident, 0)))
                for ident in order:
                    if total <= target:
                        break
                    doc = self.served.pop(ident)
                    self.model_versions.pop(ident, None)
                    self.used.pop(ident, None)
                    self.evictions += 1
                    total -= doc.size
                    evicted.append(ident)
                if evicted:
                    # A STEP read is held by its bytes for the documents served of it: theirs go with them.
                    with self.foreign_lock:
                        self.foreign.clear()
        if evicted:
            self._changed()
        return evicted

    def versions(self) -> dict[str, str]:
        """Every served document's id and the version served of it."""
        with self.load_lock:
            return {ident: doc.version for ident, doc in self.served.items()}

    def served_keys(self) -> dict[str, list[str]]:
        """Every served document's id and the keys of the parts it holds: what a build of it
        changed is what these lack."""
        with self.load_lock:
            return {ident: sorted(doc.shapes) for ident, doc in self.served.items()}

    def shape_keys(self) -> list[str]:
        """The keys of every part whose shape a served document holds."""
        with self.load_lock:
            return sorted({key for doc in self.served.values() for key, shape in doc.shapes.items() if shape is not None})

    def _read(self, ident: str, path: Path) -> Served:
        if path.suffix.lower() in FOREIGN:
            return self._read_step(ident, path)
        if self.isolated:
            try:
                structure, version, shapes, names = self._readers().submit(_read_document, str(path)).result()
            except concurrent.futures.BrokenExecutor:  # the reader died mid-read
                with self.foreign_lock:
                    self.reader = None  # the next read starts a reader afresh
                raise ValueError(f"the reader exited reading {path.name}") from None
            return Served(ident, path, structure, version, shapes, names)
        from cadgen.engine.document import Loaded

        loaded = Loaded(path)
        return Served(ident, path, loaded.structure(), loaded.version, {p.key: p.shape for p in loaded.prototypes},
                      {p.key: p.name for p in loaded.prototypes})

    def _read_step(self, ident: str, path: Path) -> Served:
        """A STEP served: its read (``_foreign``), named and versioned as this file."""
        read, stat = self._foreign(path)
        structure = {**read["structure"], "path": str(path), "version": f"{stat[0]}-{stat[1]}",
                     "read": {"seconds": read["seconds"], "process": read["process"]}}
        if read["stem"]:  # several free shapes: the document is named by its file
            structure["name"] = path.stem
            structure["tree"] = {**structure["tree"], "name": path.stem}
        return Served(ident, path, structure, stat, dict(read["shapes"]),
                      {prototype["key"]: prototype["name"] for prototype in structure["prototypes"]})

    def _readers(self) -> concurrent.futures.ProcessPoolExecutor:
        """The reader processes: one at a time, each gone after its read (with what the parse
        left in its memory), the next started and warm meanwhile."""
        with self.foreign_lock:
            if self.reader is not None and getattr(self.reader, "_broken", False):
                self.reader.shutdown(wait=False, cancel_futures=True)  # a child died; it serves no one now
                self.reader = None
            if self.reader is None:
                import multiprocessing

                self.reader = concurrent.futures.ProcessPoolExecutor(
                    1, mp_context=multiprocessing.get_context("spawn"), initializer=_reader_ready, max_tasks_per_child=1)
            return self.reader

    def _foreign(self, path: Path) -> tuple[dict[str, Any], tuple]:
        """The read of the STEP at ``path`` and the file state it is of: held by the file's
        bytes, else read by a reader process -- once, however many ask for it meanwhile."""
        stat = _stat(path)
        if stat is None:
            raise FileNotFoundError(f"no document {path}")
        digest = _digest(path)
        with self.foreign_lock:
            found = self.foreign.get(digest)
            if found is not None:
                self.foreign.move_to_end(digest)
                return found, stat
            reading = self.foreign_reads.get(digest)
            owner = reading is None
            if owner:
                reading = self.foreign_reads[digest] = concurrent.futures.Future()
        if not owner:
            return reading.result(), stat
        try:
            try:
                read = self._readers().submit(_read_foreign, str(path), digest).result()
            except concurrent.futures.BrokenExecutor:  # the reader died mid-read
                with self.foreign_lock:
                    self.reader = None  # the next read starts a reader afresh
                raise ValueError(f"the STEP reader exited reading {path.name}") from None
        except BaseException as error:
            with self.foreign_lock:
                self.foreign_reads.pop(digest, None)
            reading.set_exception(error)
            raise
        with self.foreign_lock:
            self.foreign_reads.pop(digest, None)
            if _stat(path) == stat:  # held only when the bytes read are the bytes digested
                self.foreign[digest] = read
                while len(self.foreign) > FOREIGN_HELD:
                    self.foreign.popitem(last=False)
        reading.set_result(read)
        return read, stat

    def document(self, ident: str) -> Served:
        """The document as the server holds it, read from its file again only when some
        other process rewrote the file (and no build is writing it now). A STEP is read
        again in the background (the module docstring): until it is in, this is the last."""
        if ident in self.model_loaders:
            # No kernel work on the HTTP thread: the loader asks the owning worker, and one no
            # worker holds any more says so (``NotHeld``): nothing is run to bring it back.
            with self.model_locks[ident]:
                _label, load, version = self.model_loaders[ident]
                with self.load_lock:
                    doc = self.served.get(ident) if self.model_versions.get(ident) == version else None
                    if doc is not None:
                        self.used[ident] = next(self.uses)
                if doc is None:
                    # Its structure and shapes; and, read from the engine's cache, its xbf bytes third.
                    loaded = load()
                    structure, shapes = loaded[0], loaded[1]
                    with self.load_lock:  # held at its version before it can be evicted
                        doc = self.served[self.put(ident, structure, shapes, grow=False)]
                        if len(loaded) > 2:
                            doc.xbf, doc._size = loaded[2], None
                        self.model_versions[ident] = version
                    self._grown(ident)
            return doc
        if ident not in self.served and ident in self.files:
            self.add(Path(self.files[ident]))  # an evicted file, read again: reading runs no code
        with self.load_lock:
            doc = self.served[ident]
            self.used[ident] = next(self.uses)
            if self.held.get(ident):
                return doc
            stat = _stat(doc.path)
            if stat is None or stat == doc.stat:
                return doc
            if doc.path.suffix.lower() in FOREIGN:
                if ident not in self.rereading and self.unreadable.get(ident, ()) != stat:
                    self.rereading.add(ident)
                    threading.Thread(target=self._reread, args=(ident, doc, stat), daemon=True).start()
                return doc
            doc = self.served[ident] = self._read(ident, doc.path)
        self._changed()
        self._grown(ident)
        return doc

    def _reread(self, ident: str, doc: Served, stat: tuple) -> None:
        """A served STEP whose file changed, read again and put in place of ``doc``: the page
        waiting on the version is answered then. A file that cannot be read as it stands (a
        writer midway, garbage) is tried again once it changes."""
        fresh = None
        try:
            fresh = self._read(ident, doc.path)
        except Exception:  # noqa: BLE001 - the page keeps the version it has
            pass
        with self.load_lock:
            self.rereading.discard(ident)
            if fresh is None:
                self.unreadable[ident] = stat
            else:
                self.unreadable.pop(ident, None)
                if self.served.get(ident) is doc:
                    self.served[ident] = fresh
        self._changed()

    def _ids(self, texts: Any) -> list[str]:
        """The served documents among ``texts`` (ids or paths), by id."""
        found = []
        for text in texts:
            try:
                ident = document_id(text)
            except (OSError, ValueError):
                continue
            if self.holds(ident):
                found.append(ident)
        return found

    def hold(self, documents: list[str]) -> list[str]:
        """Documents a build is writing (ids or paths): their files are not read again until
        ``release``. The ids held."""
        with self.load_lock:
            held = self._ids(documents)
            for ident in held:
                self.held[ident] = self.held.get(ident, 0) + 1
        return held

    def release(self, held: list[str]) -> None:
        with self.load_lock:
            for ident in held:
                left = self.held.get(ident, 0) - 1
                if left > 0:
                    self.held[ident] = left
                else:
                    self.held.pop(ident, None)
        self._changed()

    def _changed(self) -> None:
        with self.changed:
            self.generation += 1
            self.changed.notify_all()

    def patch(self, header: dict[str, Any], payload: bytes, arrived: float) -> dict[str, Any] | None:
        """A worker's document for one served path (see the module docstring): the new
        structure in place of the old, the buffers it brought held, its shapes kept; every
        part neither held nor brought is sent to the pool. Returns what it did, or None for
        a path not served."""
        started = time.perf_counter()
        path = document_key(header["path"])
        ident = file_id(path)
        if ident not in self.served:
            return None
        view = memoryview(payload)
        at = 0
        for key, size, unmeshed in header.get("meshes") or []:
            self.cache.put(key, bytes(view[at:at + size]), {int(o): text for o, text in unmeshed.items()})
            at += size
        brought: dict[str, bytes] = {}
        for key, size in header.get("shapes") or []:
            brought[key] = bytes(view[at:at + size])
            at += size
        structure = header["structure"]
        mtime, _sep, size = structure["version"].partition("-")
        with self.load_lock:
            old = self.served[ident]
            shapes: dict[str, Any] = {}
            names: dict[str, str] = {}
            for prototype in structure["prototypes"]:
                key = prototype["key"]
                shapes[key] = brought.get(key) or old.shapes.get(key) or self._shape(key)
                names[key] = prototype["name"]
            data = {key: made for key, made in old.data.items() if key in shapes}
            doc = self.served[ident] = Served(ident, path, structure, (int(mtime), int(size)), shapes, names, None, data)
            self.used[ident] = next(self.uses)
            applied = time.perf_counter()
            doc.patch = {"worker": header.get("timings") or {}, "arrived": arrived, "applied": time.time(),
                         "seconds": round(applied - started, 4), "meshes": len(header.get("meshes") or []),
                         "shapes": len(brought), "bytes": len(payload)}
        self._changed()
        self._grown(ident)
        self.prefetch(doc)
        return doc.patch

    def _shape(self, key: str) -> Any:
        for doc in self.served.values():
            found = doc.shapes.get(key)
            if found is not None:
                return found
        return None

    def shape_of(self, doc: Served, key: str) -> Any:
        """A part's shape bytes, from the document, or -- for one no process sent -- from
        its file, read once to fill every shape it lacks."""
        found = doc.shape_data(key)
        if found is None:
            with self.load_lock:
                read = self._read(doc.ident, doc.path)
                for missing, shape in read.shapes.items():
                    doc.shapes.setdefault(missing, shape)
                    if doc.shapes[missing] is None:
                        doc.shapes[missing] = shape
                doc._size = None
            found = doc.shape_data(key)
        if found is None:
            raise KeyError(f"no shape for part {key}")
        return found

    def structure(self, doc: Served) -> dict[str, Any]:
        """The document's structure, each part held with the faces its mesher left
        without triangles (``unmeshed``, ordinals) and ``BRepCheck``'s verdict on each."""
        found = dict(doc.structure)
        found["prototypes"] = prototypes = []
        for prototype in doc.structure["prototypes"]:
            unmeshed = self.cache.unmeshed(prototype["key"])
            if unmeshed is not None:
                prototype = {**prototype, "unmeshed": sorted(unmeshed),
                             "unmeshedCheck": {str(ordinal): text for ordinal, text in sorted(unmeshed.items())}}
            prototypes.append(prototype)
        return found

    def building(self, frame: dict[str, Any]) -> None:
        """A build's progress frame (``progress.py``): each served document among its
        ``outputs`` is being built, as the frame says, and its pages are woken."""
        with self.load_lock:
            hit = self._ids(frame.get("outputs") or [])
            for ident in hit:
                state = self.builds.setdefault(ident, {"building": None, "failed": None, "progress": 0})
                state.update(building=frame, failed=None, progress=state["progress"] + 1)
        if hit:
            self._changed()

    def built(self, outcomes: dict[str, dict[str, Any] | None]) -> None:
        """Builds that answered: per document they wrote (a path, or a model's id), None when its
        model built, else what failed (``{"model", "error", "progress"}``). Those served are built
        no longer; their pages are woken."""
        hit = False
        with self.load_lock:
            for text, failed in outcomes.items():
                for ident in self._ids([text]):
                    state = self.builds.setdefault(ident, {"building": None, "failed": None, "progress": 0})
                    state.update(building=None, failed=failed, progress=state["progress"] + 1)
                    hit = True
        if hit:
            self._changed()

    def build_of(self, ident: str) -> dict[str, Any]:
        """A served document's build, by its id: ``building``, ``failed`` and their ``progress`` count."""
        with self.load_lock:
            return dict(self.builds.get(ident) or {"building": None, "failed": None, "progress": 0})

    def wait(self, ident: str, after: str | None, seconds: float, progress: int | None = None) -> Served:
        """The document once its version is not ``after``, or its build's ``progress`` count is
        not ``progress`` (when given), or after ``seconds``."""
        with self.watch_lock:
            self.watchers[ident] = self.watchers.get(ident, 0) + 1
            self.synced[ident] = time.monotonic()
        try:
            return self._wait(ident, after, seconds, progress)
        finally:
            with self.watch_lock:
                left = self.watchers[ident] - 1
                if left:
                    self.watchers[ident] = left
                else:
                    del self.watchers[ident]
                self.synced[ident] = time.monotonic()
            self.touch()

    def sync(self, document: str) -> None:
        """A connected app's heartbeat (its document's id, path or address), even when its
        document version has not changed."""
        for ident in self._ids([document]):
            with self.watch_lock:
                self.synced[ident] = time.monotonic()
            self.touch()

    def watched(self) -> set[str]:
        """The ids of documents with an outstanding version read or a sync in the last LIVE seconds.

        This lock is independent of document loading and the worker pool: retirement must
        not wait for a document's reader, nor take their locks in the opposite order.
        """
        now = time.monotonic()
        with self.watch_lock:
            self.synced = {ident: at for ident, at in self.synced.items() if now - at < LIVE}
            return set(self.watchers) | self.synced.keys()

    def _wait(self, ident: str, after: str | None, seconds: float, progress: int | None) -> Served:
        deadline = time.monotonic() + seconds
        while True:
            generation = self.generation
            doc = self.document(ident)
            left = deadline - time.monotonic()
            if after is None or doc.version != after or left <= 0 or (
                    progress is not None and self.build_of(ident)["progress"] != progress):
                return doc
            with self.changed:
                # Woken by a patch, a release or a build's progress; the file is looked at twice a second.
                self.changed.wait_for(lambda: self.generation != generation, timeout=min(left, 0.5))

    def topology(self, key: str, data: bytes) -> Any:
        """A part's ``mesh.Topology``, for its facts: a few held, for the process's convenience."""
        if self.isolated:
            return _RemoteTopology(self.mesher.processes(), key, data)
        from cadgen.engine.mesh import Topology

        with self.topology_lock:
            found = self.topologies.get(key)
            if found is not None:
                self.topologies.move_to_end(key)
                return found
        found = Topology(data)
        with self.topology_lock:
            self.topologies[key] = found
            while len(self.topologies) > 32:
                self.topologies.popitem(last=False)
        return found

    # --- meshing ---------------------------------------------------------------------

    def _submit(self, key: str, data: bytes, mode: str | None) -> concurrent.futures.Future:
        """The part's mesh, running or started: a future of its buffer, unmeshed faces and
        seconds, whose result is held as soon as it is ready."""
        with self.cache.lock:
            future = self.cache.pending.get(key)
            if future is not None:
                return future
            future = self.cache.pending[key] = self.mesher.submit(data, "processes" if self.isolated else mode)

        def settle(done: concurrent.futures.Future) -> None:
            if not done.cancelled() and done.exception() is None:
                buffer, unmeshed, _seconds = done.result()
                self.cache.put(key, buffer, unmeshed)
            with self.cache.lock:
                if self.cache.pending.get(key) is done:
                    del self.cache.pending[key]

        future.add_done_callback(settle)
        return future

    def _jobs(self, doc: Served) -> list[tuple[str, bytes]]:
        """The document's parts not held, each once, largest first."""
        jobs = {}
        for key in doc.shapes:
            if key not in jobs and self.cache.get(key) is None:
                jobs[key] = self.shape_of(doc, key)
        return sorted(jobs.items(), key=lambda item: -len(item[1]))

    def prefetch(self, doc: Served) -> None:
        """Send every part of the document not held to the mesher, largest first, now."""
        for key, data in self._jobs(doc):
            self._submit(key, data, None)

    def mesh_all(self, doc: Served, mode: str | None) -> dict[str, Any]:
        """Mesh every part of a document not held yet, all at once, largest first."""
        started = time.perf_counter()
        jobs = self._jobs(doc)
        futures = {key: self._submit(key, data, mode) for key, data in jobs}
        timings = []
        total_bytes = triangles = unmeshed_faces = 0
        for key, future in futures.items():
            data, unmeshed, seconds = future.result()
            total_bytes += len(data)
            triangles += _triangles(data)
            unmeshed_faces += len(unmeshed)
            timings.append((seconds, doc.names.get(key, key)))
        timings.sort(reverse=True)
        each = [seconds for seconds, _name in timings]
        return {"parts": len(doc.shapes), "meshed": len(futures), "seconds": round(time.perf_counter() - started, 4),
                "bytes": total_bytes, "triangles": triangles, "unmeshed": unmeshed_faces,
                "mode": mode or self.mesher.mode, "workers": self.mesher.workers,
                "per_part": {"sum": round(sum(each), 4), "max": round(each[0], 4) if each else 0.0,
                             "median": round(each[len(each) // 2], 4) if each else 0.0,
                             "slowest": [[name, round(seconds, 4)] for seconds, name in timings[:5]]}}

    # --- routes ----------------------------------------------------------------------

    def route(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        parsed = urlparse(handler.path)
        parts = [unquote(part) for part in parsed.path.removeprefix("/").split("/")] if parsed.path != "/" else []
        query = parse_qs(parsed.query)
        try:
            post = len(parts) == 4 and parts[:2] == ["api", "doc"] and parts[3] in ("pose", "mesh")
            if method not in (("POST",) if post else ("GET", "HEAD")):
                handler.send_response(405)
                handler.send_header("Allow", "POST" if post else "GET, HEAD")
                handler.send_header("Content-Type", "application/json")
                body = json.dumps({"error": "Method not allowed"}).encode()
                handler.send_header("Content-Length", str(len(body)))
                handler.end_headers()
                if handler.command != "HEAD":
                    handler.wfile.write(body)
                return
            if not parts or (len(parts) == 1 and is_id(parts[0])):
                return self.file(handler, PAGE / "index.html")  # ``/<id>``: the document's page
            if parts[0] == "page" and len(parts) == 2:
                return self.file(handler, PAGE / parts[1])
            if parts[0] == "three" and self.three is not None:
                target = (self.three / "/".join(parts[1:])).resolve()
                if self.three.resolve() in target.parents:
                    return self.file(handler, target)
            if parts == ["api", "docs"]:
                return self.json(handler, self.listing())
            if parts == ["api", "look"]:
                return self.json(handler, LOOK.json())
            if parts == ["api", "look", "environment"]:
                return self.send(handler, 200, LOOK.environment_path.read_bytes(), "image/vnd.radiance")
            ident, pose = self.poses.get(parts[2], (parts[2], None)) if len(parts) >= 3 else ("", None)
            if parts[:2] == ["api", "doc"] and ident and not self.holds(ident) and is_id(ident):
                self.revive(ident)  # a document the engine's cache holds, after a restart
            if parts[:2] == ["api", "doc"] and ident and not self.holds(ident):
                lost = self.lost(ident)  # a document the engine knows but holds no more: what rebuilds it
                if lost is not None:
                    return self.send(handler, 404, json.dumps(lost).encode(), "application/json")
            if parts[:2] == ["api", "doc"] and self.holds(ident):
                if len(parts) == 4 and parts[3] == "version":
                    after = (query.get("after") or [None])[0]
                    seconds = float((query.get("wait") or ["0"])[0] or 0)
                    if not math.isfinite(seconds):  # a NaN would never time out, an infinity never end
                        raise ValueError("wait is a number of seconds")
                    seconds = min(max(seconds, 0.0), WAIT_LIMIT)
                    given = (query.get("progress") or [""])[0]
                    doc = self.wait(ident, after, seconds, int(given) if given.isdigit() else None)
                    build = self.build_of(ident)
                    return self.json(handler, {"version": doc.version, "patch": doc.patch, **build})
                doc = self.document(ident)
                if len(parts) == 3:
                    self.prefetch(doc)  # a page is about to ask for every part
                    found = self.posed(doc, pose)
                    stale = self.stale(ident) if ident in self.model_loaders else None
                    return self.json(handler, {**found, "stale": stale} if stale else found)
                if len(parts) == 4 and parts[3] == "pose" and method == "POST":
                    return self.pose(handler, doc)
                if len(parts) >= 5 and parts[3] == "part":
                    key = parts[4]
                    if key not in doc.shapes:
                        return self.error(handler, 404, "no such part")
                    if len(parts) == 5:
                        return self.part(handler, doc, key)
                    if len(parts) == 7 and parts[5] in ("face", "edge", "vertex") and parts[6].isdigit():
                        return self.fact(handler, doc, key, parts[5], int(parts[6]))
                    if len(parts) == 6 and parts[5] == "groups":
                        return self.json(handler, self.topology(key, self.shape_of(doc, key)).groups())
                    if len(parts) == 6 and parts[5] == "volume":
                        return self.json(handler, self.topology(key, self.shape_of(doc, key)).volume())
                if len(parts) == 4 and parts[3] == "mesh" and method == "POST":
                    mode = (query.get("mode") or [None])[0]
                    if mode is not None and mode not in MODES:
                        return self.error(handler, 400, f"mode is one of {', '.join(MODES)}")
                    if (query.get("drop") or ["0"])[0] == "1":
                        self.cache.drop(doc.shapes)
                    return self.json(handler, self.mesh_all(doc, mode))
            self.error(handler, 404, "not found")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except NotHeld as error:  # its worker gone and its bytes evicted: the command that builds it again
            self.send(handler, 404, json.dumps(error.payload()).encode(), "application/json")
        except ValueError as error:  # a pose refused by name (``mechanism.KinematicsError``), a body not JSON
            self.error(handler, 400, str(error))
        except Exception as error:  # noqa: BLE001 - a request's failure is its answer
            self.error(handler, 500, f"{type(error).__name__}: {error}")

    def posed(self, doc: Served, pose: Any) -> dict[str, Any]:
        """The document's structure, at ``pose`` where one is given: its instances where the
        mechanism places them there (``mechanism.posed_structure``)."""
        structure = self.structure(doc)
        if pose is None:
            return structure
        if self.isolated:
            return self.mesher.processes().submit(_pose_structure, structure, pose).result()
        return _pose_structure(structure, pose)

    def pose(self, handler: BaseHTTPRequestHandler, doc: Served) -> None:
        """``POST /api/doc/<id>/pose`` with ``{"pose": NAME | {joint or coupling: value}}``: the
        document served at that pose under an id of its own, its parts the document's. An unknown
        configuration, joint or coupling, a value out of range and a mechanism that is not a tree
        are refused by name (400) before the id exists."""
        try:
            length = int(handler.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("a pose request's Content-Length is a number") from None
        if not 0 <= length <= POSE_BODY_LIMIT:
            raise ValueError(f"a pose request is at most {POSE_BODY_LIMIT} bytes")
        try:
            pose = json.loads(handler.rfile.read(length) or b"{}").get("pose")
        except (json.JSONDecodeError, AttributeError):
            raise ValueError("a pose request is {\"pose\": a configuration's name or {joint: value}}") from None
        if not isinstance(pose, (str, dict)):
            raise ValueError("a pose is a configuration's name or an object of joint values")
        posed = self.posed(doc, pose)
        if "kinematics" not in posed:
            raise ValueError("the document has no joints to pose")
        digest = hashlib.blake2b(json.dumps(pose, sort_keys=True).encode(), digest_size=6).hexdigest()
        ident = f"{doc.ident}~{digest}"
        self.poses[ident] = (doc.ident, pose)
        self.poses.move_to_end(ident)
        while len(self.poses) > POSES_HELD:
            self.poses.popitem(last=False)
        self.json(handler, {"id": ident, "url": f"{self.url}/api/doc/{ident}", **posed["kinematics"]["pose"]})

    def part(self, handler: BaseHTTPRequestHandler, doc: Served, key: str) -> None:
        data = self.cache.get(key)
        if data is None:
            data = self._submit(key, self.shape_of(doc, key), None).result()[0]
        self.send(handler, 200, data, "application/octet-stream", cache=True)

    def fact(self, handler: BaseHTTPRequestHandler, doc: Served, key: str, kind: str, ordinal: int) -> None:
        """What the kernel measures of one face, edge or vertex of a part, now."""
        topology = self.topology(key, self.shape_of(doc, key))
        try:
            found = getattr(topology, kind)(ordinal)
        except KeyError as error:
            return self.error(handler, 404, str(error.args[0]))
        if kind == "face":
            unmeshed = self.cache.unmeshed(key)
            found["meshed"] = None if unmeshed is None else ordinal not in unmeshed
        found["made_by"] = self.made_by(doc, key, kind, ordinal)
        self.json(handler, found)

    def made_by(self, doc: Served, key: str, kind: str, ordinal: int) -> dict[str, Any] | None:
        """What made the element, from the worker that built the document (``provenance``),
        when the name it gives is the one the served document holds: None for a document
        no live worker built, or whose served version that worker's last build is not."""
        if self.provenance is None:
            return None
        try:
            found = self.provenance(doc.ident, key, kind, ordinal)
        except Exception:  # noqa: BLE001 - provenance never fails the facts
            return None
        prototype = next((p for p in doc.structure["prototypes"] if p["key"] == key), None)
        if not found or prototype is None or prototype.get(f"{kind}Names", {}).get(str(ordinal)) != found.get("name"):
            return None
        return found

    # --- responses -------------------------------------------------------------------

    def file(self, handler: BaseHTTPRequestHandler, path: Path) -> None:
        if not path.is_file():
            return self.error(handler, 404, "not found")
        kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".js":
            kind = "text/javascript"
        self.send(handler, 200, path.read_bytes(), kind)

    def json(self, handler: BaseHTTPRequestHandler, payload: Any) -> None:
        self.send(handler, 200, json.dumps(payload, separators=(",", ":")).encode(), "application/json")

    def error(self, handler: BaseHTTPRequestHandler, status: int, text: str) -> None:
        self.send(handler, status, json.dumps({"error": text}).encode(), "application/json")

    def send(self, handler: BaseHTTPRequestHandler, status: int, data: bytes, kind: str, *, cache: bool = False) -> None:
        handler.send_response(status)
        handler.send_header("Content-Type", kind)
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "max-age=31536000, immutable" if cache else "no-store")
        allow_origin(handler)  # a page on this machine reads documents from here directly (access.py)
        handler.end_headers()
        if handler.command != "HEAD":
            handler.wfile.write(data)
