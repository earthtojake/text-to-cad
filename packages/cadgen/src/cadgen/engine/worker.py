"""A warm worker: one process per model script, the memo living in it for its life.

The daemon starts one per script and talks to it over the worker's stdin and its
original stdout. A request is one JSON object per line: ``{"id", "op": "build", "script",
"functions", "cwd", "run", "env"}`` (``run``: the calling process's run, ``build.build``; ``env``: its
environment, ``adopt``). The answers are frames: a JSON object on one line and, when it has
``bytes``, exactly that many bytes after it. A build is answered by ``{"id", "log"}`` frames while it
builds and ``{"id", "progress"}`` frames saying where it is (``progress.py``: each stage, and each
body a build runs), then one ``{"id", "done", "rssMb"}`` (the build's reports, and the worker's
resident memory after it, in MiB) or ``{"id", "failed"}`` (with ``kind`` where it is a refusal:
``refusal``). A file the build writes is sent nowhere: a page serving it as a file reads it from
the disk, as it reads any file another program wrote. What the
model prints goes to the worker's stderr, which the daemon passes on. The worker exits when
its stdin closes: the daemon's pool closes it to retire the worker (``daemon.Pool``). Its first
frame, ``{"ready": pid, "rssMb"}``, says it is up and its resident memory then.

A worker started with ``--standby`` is the pool's standby: it loads the kernel before it says it is
ready (``load_kernel``) and builds nothing until a build takes it, when the daemon sends
``{"op": "adopt", "home"}`` -- the folder a fresh worker of that script would have started in, where
a request with no ``cwd`` runs -- and the build after it; it answers nothing to the adoption.

A ``{"id", "op": "where", "doc", "key", "kind", "ordinal"}`` request asks what made one
element of a document this worker built (``doc``, its id) (``build.made_by``): it is answered at once,
``{"id", "where": {...} | null}``, by the thread that reads the requests -- during a
build too, from the last build that named the document -- so a page asking about an
element never waits on a build.

A worker whose resident memory alone is over the workers' memory cap after a build
(``CADGEN_ENGINE_WORKER_RSS_MB``, by default a quarter of the machine's memory, which the daemon holds
all its workers to together: ``daemon.Pool.shed``) is retired: its reports say so (``retired``),
and the daemon, once it has taken the worker's documents from it (``models.Models.drain``),
closes its stdin. The daemon starts a fresh one for the next build, a restart: a model whose
xbf holds its closure unchanged is taken in seconds.

A request may carry bytes after its line (``{"bytes": N}``, the frame's form): an export of a
document the daemon holds and no worker does (``{"document", "name"}``: the whole document's xbf
bytes, which its worker made of it before it retired: a ``result`` request with ``whole``) reads
them as an on-disk xbf, so the documents worker exports, inspects and draws it, kinematics and
all, with no worker of its script started.

A ``build`` or ``export`` request carries its caller's environment (``env``), and the worker adopts it
before it runs (``adopt``): its ``os.environ`` becomes the caller's, but for what started this
interpreter (``daemon.RESTARTS``, which a request shares with its worker or is given another) and
what the worker set for itself. A run is the script in its caller's environment, as under
``python SCRIPT``; the worker is the interpreter, kept warm across them.

A ``{"id", "op": "save", "ident", "script", "name", "generation"}`` request asks for a document
this worker built as the engine's cache keeps it (``cache``): the whole document's xbf bytes
(``document.to_bytes``), answered ``{"id", "saved": {"ident", "generation"}, "bytes"}`` and the
bytes, or ``{"id", "saved": {"ident", "generation", "error"}}``. It is never on the run path: the
worker does it only when no other request waits (a request that comes meanwhile waits for the one
serialisation), and it answers no ``done``. A ``result`` request with ``document``
reads the bytes after its line (the cache's file) as ``export`` does a held document's: its
structure and shape bytes, as a built document's.

A build runs with the cyclic collector off, and the worker collects once it is idle: the memo
keeps every live result of the last builds, millions of objects, and a full collection walks
all of them -- a second on a large model, paid inside whichever call allocates when it falls
due. It is paid after the worker has answered and no request has come for ``COLLECT_IDLE``
seconds, so a script calling its models one after another (each call a request) never waits
on the collection its last call left; the worker says it collected (``{"collected": seconds}``).
Only a worker over its memory cap after a build collects first, inside the build's answer, and
measures again: the cap judges what the worker holds, not the cycles it has yet to collect.
"""

from __future__ import annotations

import gc
import json
import os
import queue
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable


# How long the worker waits for a next request, once it has answered, before it collects.
COLLECT_IDLE = 0.5
# A build on a worker whose kernel is not loaded (a fresh worker, or one that came before the
# standby was ready) loads it first (``kernel``); a load still going after this many seconds is said
# to the caller, once (a ``{"id", "notice"}`` frame): the operating system's first look at a fresh
# installation's native libraries (macOS checks each once) takes up to about 50 s, where a load
# it has already looked at takes 2 to 3.
KERNEL_PATIENCE = 5.0
KERNEL_NOTICE = "loading the CAD kernel for the first time in this environment, up to a minute"
# --- the worker's memory cap ----------------------------------------------------------------------


def resident_mb() -> float | None:
    """This process's resident memory now, in MiB; None where the platform will not say."""
    try:
        if sys.platform == "darwin":
            import ctypes

            class Info(ctypes.Structure):  # mach_task_basic_info
                _fields_ = [("virtual_size", ctypes.c_uint64), ("resident_size", ctypes.c_uint64),
                            ("resident_size_max", ctypes.c_uint64), ("user_time", ctypes.c_uint32 * 2),
                            ("system_time", ctypes.c_uint32 * 2), ("policy", ctypes.c_int32),
                            ("suspend_count", ctypes.c_int32)]

            system = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
            info, count = Info(), ctypes.c_uint32(ctypes.sizeof(Info) // 4)
            task = ctypes.c_uint32.in_dll(system, "mach_task_self_")
            if system.task_info(task, 20, ctypes.byref(info), ctypes.byref(count)) != 0:  # MACH_TASK_BASIC_INFO
                return None
            return info.resident_size / 2**20
        if sys.platform.startswith("linux"):
            with open("/proc/self/statm", encoding="ascii") as handle:
                return int(handle.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2**20
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):  # PROCESS_MEMORY_COUNTERS
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]

            counters = Counters()
            counters.cb = ctypes.sizeof(Counters)
            # Typed: the current process's pseudo-handle is -1, a HANDLE; passed as a C int the call
            # fails, and a Windows worker had no memory cap.
            current = ctypes.windll.kernel32.GetCurrentProcess
            current.restype = wintypes.HANDLE
            info = ctypes.windll.psapi.GetProcessMemoryInfo
            info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            info.restype = wintypes.BOOL
            if not info(current(), ctypes.byref(counters), counters.cb):
                return None
            return counters.WorkingSetSize / 2**20
    except Exception:  # noqa: BLE001 - a platform that will not say has no cap
        return None
    return None


def _physical_mb() -> float | None:
    try:
        if sys.platform == "darwin":
            import ctypes

            system = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
            size, length = ctypes.c_uint64(0), ctypes.c_size_t(8)
            if system.sysctlbyname(b"hw.memsize", ctypes.byref(size), ctypes.byref(length), None, 0) == 0:
                return size.value / 2**20
            return None
        if os.name == "nt":  # no sysconf: GlobalMemoryStatusEx's ullTotalPhys
            import ctypes
            from ctypes import wintypes

            class Status(ctypes.Structure):  # MEMORYSTATUSEX
                _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                            *((name, ctypes.c_uint64) for name in (
                                "ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
                                "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual"))]

            status = Status()
            status.dwLength = ctypes.sizeof(Status)
            ask = ctypes.windll.kernel32.GlobalMemoryStatusEx
            ask.argtypes, ask.restype = [ctypes.POINTER(Status)], wintypes.BOOL
            return status.ullTotalPhys / 2**20 if ask(ctypes.byref(status)) else None
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**20
    except (AttributeError, OSError, ValueError):
        return None


def rss_cap_mb() -> float | None:
    """The resident memory the daemon's workers, its standby and its render processes may hold
    together (``daemon.Pool.shed``), and so one of them alone after a build or a frame:
    ``CADGEN_ENGINE_WORKER_RSS_MB`` (``0`` for no cap), else a quarter of the machine's memory, at
    least 2 GiB. None: no cap."""
    given = os.environ.get("CADGEN_ENGINE_WORKER_RSS_MB", "").strip()
    if given:
        try:
            value = float(given)
        except ValueError:
            value = -1.0
        if value >= 0:
            return value or None
    physical = _physical_mb()
    return None if physical is None else max(physical / 4, 2048.0)


def retirement(reports: list[dict[str, Any]], resident: float | None = None) -> bool:
    """After a build: this worker's resident memory (``resident``, else measured now) against its
    cap. Over it, each report says so (``retired``) and the worker is retired: the daemon drains
    and stops it once it has answered, and the next build is a fresh worker's -- a restart, which
    takes a model's xbf when nothing changed."""
    resident, cap = resident if resident is not None else resident_mb(), rss_cap_mb()
    if resident is None or cap is None or resident <= cap:
        return False
    for report in reports:
        report["retired"] = (f"the worker held {resident:.0f} MB after the build, over its {cap:.0f} MB cap "
                             "(CADGEN_ENGINE_WORKER_RSS_MB): the next build starts a fresh one")
    return True


def resident_after_build() -> float | None:
    """This worker's resident memory after a build (``resident_mb``), measured again after a
    collection where it is over the cap: the cycles the build and the uncollected ones before it
    left are not what the worker holds. Under the cap nothing is collected here: that is paid
    once the worker is idle (the module docstring)."""
    resident, cap = resident_mb(), rss_cap_mb()
    if resident is not None and cap is not None and resident > cap:
        gc.collect()
        resident = resident_mb()
    return resident


def load_kernel() -> None:
    """The kernel loaded, as a standby loads it before it is ready: OCP's native libraries and
    build123d imported, the engine's kernel layer with them (imported, never installed: a build
    installs it in its run's environment, ``build._build``), and one shape made. A fresh
    worker pays this in its first build; the operating system's first look at a fresh
    installation's native libraries (macOS checks each once) is paid here, while nobody waits."""
    import build123d
    import OCP.TopoDS  # noqa: F401
    from cadgen.engine import runtime

    runtime.check_native(runtime.compatibility())
    from cadgen.engine.kernel import determinism, history, memo, trace  # noqa: F401

    build123d.Box(1, 1, 1)
    global _KERNEL_LOADED
    _KERNEL_LOADED = True


_KERNEL_LOADED = False


def kernel(say: Callable[[str], None]) -> None:
    """The kernel loaded before a build of this worker, unless it is (``load_kernel``): a load that
    takes longer than ``KERNEL_PATIENCE`` is said once, while it goes on (``KERNEL_NOTICE``), and
    a warm worker says nothing."""
    if _KERNEL_LOADED:
        return
    told = threading.Timer(KERNEL_PATIENCE, say, (KERNEL_NOTICE,))
    told.daemon = True
    told.start()
    try:
        load_kernel()
    finally:
        told.cancel()
        told.join()  # gone before the build: a profile records every thread's calls (``profiling``)


def kept() -> dict[str, str]:
    """What of this worker's environment no run's replaces (``adopt``): what started its
    interpreter (``daemon.RESTARTS``; the engine's own folder is on its PYTHONPATH) and what it
    set for itself."""
    from cadgen.engine.daemon import BYTECODE, RESTARTS

    return {name: os.environ[name] for name in (*RESTARTS, *BYTECODE, "CADGEN_ENGINE_WORKER") if name in os.environ}


def adopt(environment: dict[str, str] | None, own: dict[str, str]) -> None:
    """A run's environment (its caller's) as ``os.environ``, but for ``own`` (``kept``); a
    request with none leaves it as it is. Only what differs is set or unset."""
    if not environment:
        return
    from cadgen.engine.daemon import BYTECODE, RESTARTS

    # The worker's bytecode is the daemon's (``daemon.bytecode``), never a run's.
    wanted = {name: value for name, value in environment.items() if name not in (*RESTARTS, *BYTECODE, "CADGEN_ENGINE_WORKER")}
    wanted.update(own)
    for name in [name for name in os.environ if name not in wanted]:
        del os.environ[name]
    for name, value in wanted.items():
        if os.environ.get(name) != value:
            os.environ[name] = value


def _neutral_folder() -> str:
    """Where an idle worker stands: the engine's folder on POSIX when it is this user's alone,
    else the temporary folder (``main``)."""
    from cadgen.engine import daemon

    folder = daemon.state_dir()
    if not daemon.WINDOWS and folder.is_dir() and daemon.folder_refusal(folder) is None:
        return str(folder)
    return tempfile.gettempdir()


def _export(request: dict[str, Any], log: Callable[[str], None]) -> dict[str, Any]:
    """An ``export`` request: the document -- one this worker holds (``held``: a document named
    by its id, read as it is and never built), a ``Model`` this program built first (its own
    explicit call), or a file (read as a file, a declared one too, whichever model's build wrote
    it; a mesh file read as its triangles, no kernel loaded) -- written
    to each destination, and drawn into ``draw``'s
    PNG where the request has one (``{"out", option: value}``, the snapshot verb's: a
    model's picture is drawn from the document in this worker's memory). Answers what was
    written."""
    from cadgen.engine import build as engine_build
    from cadgen.engine import export

    source_spec = request["source"]
    built: list[dict[str, Any]] = []
    if "id" in source_spec:
        # The daemon names a held document's worker or bytes (``Daemon.document``); in this process, none is.
        raise export.ExportRefused(f"no document {source_spec['id']} is held in this process: a document id is "
                                   "the engine's, read through its server")
    if "document" in source_spec:
        source = engine_build.held_source(request.get("payload") or b"", str(source_spec.get("name") or "document"),
                                          origin=source_spec.get("origin"))
    elif (request.get("expected") or source_spec.get("held")) and "script" in source_spec:
        source = engine_build.held(Path(source_spec["script"]), source_spec.get("function"))
        if source is None:
            raise export.ExportRefused("The viewed model is no longer held. Reopen it before exporting."
                                       if request.get("expected") else
                                       f"{source_spec.get('function')} is no longer held: run the program that "
                                       "builds it again")
    elif "script" in source_spec:
        # ``daemon=False`` alone (``api._called``): a model named by its function, built here, cold.
        script = Path(source_spec["script"])
        function = source_spec.get("function")
        # Built as it declares, its children as theirs (law 10); the exports are this request's.
        reports = engine_build.build(script, [function] if function else None, log=log,
                                     cwd=Path(request["cwd"]) if request.get("cwd") else None)
        if len(reports) != 1:
            raise engine_build.BuildError(f"{script.name} defines {len(reports)} models: export one of them")
        built = reports
        if not reports[0].get("ok"):
            return {"reports": reports, "files": []}
        function = reports[0]["source"]["name"]
        source = engine_build.held(script.resolve(), function)
        if source is None:
            xbf = next((path for path, row in reports[0]["files"].items() if row.get("kind") == "xbf"), None)
            if xbf is None:
                raise engine_build.BuildError(f"{function} of {script.name}: the build left no document")
            source = export.Source.read(xbf)
    else:
        # A file path is the file: read as a file document, whichever model's build declared it.
        from cadgen.engine.progress import say

        path = Path(source_spec["path"])
        clock = time.perf_counter()
        say("read", detail=path.name)
        source = export.Source.read(path)
        log(f"read {path.name} in {time.perf_counter() - clock:.2f}s")
    if source.path is not None:
        for destination in request["destinations"]:  # every one, before anything is written
            why = export.refused(source.path, destination)
            if why:
                raise export.ExportRefused(why)
    if request.get("expected") and "document" not in source_spec:
        from cadgen.engine.export.viewer import check
        check(source, request["expected"])  # a held document's revision is the daemon's to check
    files = []
    for index, destination in enumerate(request["destinations"]):
        from cadgen.engine.progress import say

        clock = time.perf_counter()
        target = Path(destination)
        # Each destination written, counted of them all (``progress.py``: an export's ``write``).
        say("write", detail=target.name, count=[index, len(request["destinations"])])
        before = _stat(target)
        if request.get("original"):
            from cadgen.engine.export.viewer import original
            size = original(source, target, request["expected"])
        else:
            size = export.translate(source, None, target)
        seconds = time.perf_counter() - clock
        # A file that held these bytes already is left as it was (``atomic_replace.put``): unchanged.
        files.append({"path": str(target), "kind": export.kind_of(target), "bytes": size,
                      "seconds": round(seconds, 4), "written": before is None or _stat(target) != before})
    drawn = None
    if request.get("draw"):
        from cadgen.engine import snapshot

        options = dict(request["draw"])
        out = Path(options.pop("out"))
        clock = time.perf_counter()
        drawn = snapshot.draw(source, out, **options)
        files.append({"path": str(out), "kind": "png", "bytes": drawn["bytes"],
                      "seconds": round(time.perf_counter() - clock, 4)})
    if request.get("draw_still"):
        from cadgen.engine.snapshot import Still, _occt

        options = request["draw_still"]
        out = Path(options["out"])
        drawn = _occt(source.path or out.with_suffix(".xbf"), out, Still.from_json(options["still"]),
                      False, source, time.perf_counter())
    return {"reports": built, "files": files, "drawn": drawn}


def job_progress(send: Callable[[dict[str, Any]], None], request: dict[str, Any], *,
                 cwd: str | None = None) -> Any:
    """An ``export`` request's progress (``progress.py``), each frame to ``send``: a snapshot's for a
    request that draws (``draw``, ``draw_still``), an export's otherwise, named for what it is of --
    a model as its report names it (``script::function``), a held document by its name, a file by
    its name -- and the files it writes (its destinations, or its picture)."""
    from cadgen.engine.progress import Progress

    source = request["source"]
    drawing = request.get("draw") or request.get("draw_still")
    said = Progress(send, kind="snapshot" if drawing else "export", script=source.get("script"),
                    cwd=cwd or request.get("cwd"))
    if source.get("script"):
        said.job = said.name(source["script"], source.get("function"))
    elif source.get("path"):
        said.job = Path(source["path"]).name
    else:
        said.job = str(source.get("name") or source.get("id") or "")
    said.outputs = [str(drawing["out"])] if drawing else [str(path) for path in request.get("destinations") or []]
    return said


def _stat(path: Path) -> tuple[int, int, int] | None:
    try:
        found = path.stat()
    except OSError:
        return None
    return found.st_ino, found.st_size, found.st_mtime_ns


def _result(request: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    """A ``result`` request: the document of a model this worker built, as its structure and each
    part's shape bytes (``[key, size]`` in ``shapes``, the bytes after the line in order)."""
    from cadgen.engine import build as engine_build
    from cadgen.engine import runtime

    runtime.check_native(runtime.compatibility())
    if request.get("document"):
        # The engine's cache file of a document no worker holds: read as a held document's bytes are.
        source = engine_build.held_source(request.get("payload") or b"", str(request.get("name") or "document"))
    else:
        source = engine_build.held(Path(request["script"]), request["name"])
    if source is None:
        raise engine_build.BuildError(f"no model named {request['name']!r} is built in this worker")
    keys = [prototype["key"] for prototype in source.structure["prototypes"]]
    data = [source.shape_data(key) for key in keys]
    from cadgen.engine import previous

    _writer, closure = previous.read_record(source.xcaf)

    answer = {"compatibility": runtime.compatibility(),
              "structure": source.structure, "closure": json.loads(closure) if closure else None,
              "shapes": [[key, len(part)] for key, part in zip(keys, data)],
              "placements": [[list(path), matrix] for path, matrix in source.locals().items()]}
    if request.get("whole"):
        # The drain's: the whole document as the xbf bytes ``@xbf`` writes, after the shapes -- for
        # one taken from the engine's cache, the bytes it was taken with (a read is never written).
        from cadgen.engine import document

        whole = (None if request.get("document") else engine_build.taken(Path(request["script"]), request["name"])) \
            or document.to_bytes(source.xcaf, source.shapes.values())
        answer["xbf"] = len(whole)
        data.append(whole)
    return answer, b"".join(data)


def _save(request: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    """A ``save`` request: the document of a model this worker built, as the xbf bytes the engine's
    cache keeps (``document.to_bytes``, the drain's bytes)."""
    from cadgen.engine import build as engine_build
    from cadgen.engine import document

    header = {"ident": request.get("ident"), "generation": request.get("generation")}
    taken = engine_build.taken(Path(request["script"]), request["name"])
    if taken is not None:
        return header, taken  # taken from the cache: those bytes, never the read document written again
    source = engine_build.held(Path(request["script"]), request["name"])
    if source is None:
        return {**header, "error": f"no model named {request['name']!r} is built in this worker"}, b""
    return header, document.to_bytes(source.xcaf, source.shapes.values())


def refusal(error: BaseException) -> dict[str, str]:
    """A refusal's type, carried beside its words: a ``ValueError`` (an ``ExportRefused``, a
    ``SnapshotRefused``, a ``KinematicsError``, ...) answered as ``kind``, ``module:name``, so the
    caller raises it as that type (``api._failed``) and a refused export or snapshot is refused the
    same through the daemon as in the caller's own process (``daemon=False``). Anything else is
    no refusal: its words alone."""
    if not isinstance(error, ValueError):
        return {}
    kind = type(error)
    return {"kind": f"{kind.__module__}:{kind.__qualname__}"}

def main() -> int:
    os.environ["CADGEN_ENGINE_WORKER"] = "1"
    protocol = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)  # the model's prints go where the daemon reads logs from
    sys.stdout = sys.stderr
    # The daemon's requests come on a handle of the worker's own, and standard input is the null
    # device. On Windows a thread blocked reading a pipe holds every other call on that pipe --
    # GetFileType, which a DLL's C runtime asks of the standard handles as the DLL loads (numpy's
    # OpenBLAS, say) -- so a model's first import would wait for the daemon's next request, which
    # waits for the build: a worker that never builds. And a model reading its input reads none
    # of the protocol.
    asked = os.fdopen(os.dup(0), "rb")
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    os.close(null)
    sys.stdin = open(os.devnull, encoding="utf-8")  # noqa: SIM115 - standard input, for the worker's life

    lock = threading.Lock()

    def send(message: dict[str, Any], payload: bytes = b"") -> None:
        if payload:
            message = {**message, "bytes": len(payload)}
        with lock:  # a frame is whole: the build's thread and the reader's both send
            protocol.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
            if payload:
                protocol.write(payload)
            protocol.flush()

    from cadgen.engine.build import BuildError, build, made_by
    from cadgen.engine.profiling import quiet
    from cadgen.engine.progress import Progress, building

    def progress(ident: Any, **where: Any) -> Progress:
        """A build request's progress, each frame sent as ``{"id", "progress"}`` (``progress.py``)."""
        return Progress(lambda frame: send({"id": ident, "progress": frame}), **where)

    requests: "queue.Queue[dict[str, Any] | None]" = queue.Queue()

    def read() -> None:
        """Every request as it comes: a ``where`` answered here and now, the rest queued
        for the build loop."""
        try:
            for line in asked:
                if not line.strip():
                    continue
                with quiet():  # a request read while a build is profiled waits for the profile (``profiling``)
                    request = json.loads(line)
                    if request.get("bytes"):
                        request["payload"] = asked.read(int(request["bytes"]))
                    if request.get("op") == "where":
                        try:
                            found = made_by(request["doc"], request["key"], request["kind"], int(request["ordinal"]))
                        except Exception:  # noqa: BLE001 - a question it cannot answer is answered with nothing
                            found = None
                        send({"id": request.get("id"), "where": found})
                    else:
                        requests.put(request)
        finally:
            requests.put(None)

    # A request runs in its folder (its ``cwd``, else the one this worker started in: its script's),
    # so a model's relative reads resolve as before; between requests the worker stands in the
    # engine's own folder where it is this user's alone (``daemon.folder_refusal``), else the
    # temporary folder, so an idle worker holds no project folder open (on Windows, a folder a
    # process stands in cannot be renamed or deleted) and never stands in a folder others write.
    home, neutral = os.getcwd(), _neutral_folder()
    os.chdir(neutral)
    from cadgen.engine import runtime

    snapshot = runtime.dependencies()
    if sys.pycache_prefix is not None:
        # Reinstallation can preserve source size/mtime. A restarted worker uses the new
        # installation's bytecode folder before importing its kernel or project dependencies.
        sys.pycache_prefix = str(Path(sys.pycache_prefix) / "workers" / snapshot[:24])
        os.environ["PYTHONPYCACHEPREFIX"] = sys.pycache_prefix
    own = kept()

    def leave() -> None:
        try:
            os.chdir(neutral)
        except OSError:
            pass

    if "--standby" in sys.argv[1:]:
        load_kernel()
    resident = resident_mb()
    execution = runtime.describe()
    send({"ready": os.getpid(), "rssMb": None if resident is None else round(resident), "execution": execution})
    gc.disable()
    threading.Thread(target=read, daemon=True).start()
    owed = False  # a collection, since the last request answered
    deferred: list[dict[str, Any]] = []  # saves, done when no other request waits
    while True:
        if deferred and requests.empty():
            request = deferred.pop(0)
        elif owed:
            try:
                request = requests.get(timeout=COLLECT_IDLE)
            except queue.Empty:
                clock = time.perf_counter()
                gc.collect()  # idle: the cycles the last builds left
                owed = False
                send({"collected": round(time.perf_counter() - clock, 4)})
                continue
        else:
            request = requests.get()
        if request is None:
            break
        ident = request.get("id")
        op = request.get("op")
        if op == "save":
            if not requests.empty():
                deferred.append(request)  # never on the run path: after what waits
                continue
            try:
                header, payload = _save(request)
            except BaseException as error:  # noqa: BLE001 - a save never fails the worker
                header, payload = {"ident": request.get("ident"), "generation": request.get("generation"),
                                   "error": f"{type(error).__name__}: {error}"}, b""
            send({"id": ident, "saved": header}, payload)
            owed = True
            continue
        if op in ("export", "result"):
            try:
                adopt(request.get("env"), own)
                cwd = request.get("cwd")
                os.chdir(cwd or home)
                if op == "export":
                    # An export's frames, or a snapshot's for a request that draws (``job_progress``).
                    said = job_progress(lambda frame: send({"id": ident, "progress": frame}), request, cwd=cwd)
                    with building(said):
                        done = _export(request, lambda text: send({"id": ident, "log": text}))
                    said.attach(done.get("reports") or [])
                    resident = resident_after_build()
                    if done.get("reports"):
                        retirement(done["reports"], resident)  # said in its reports; the daemon retires it
                    send({"id": ident, "done": done, "rssMb": None if resident is None else round(resident)})
                else:
                    answer, payload = _result(request)
                    send({"id": ident, "done": answer}, payload)
            except (BuildError, ValueError, OSError) as error:
                send({"id": ident, "failed": str(error), **refusal(error)})
            except BaseException as error:  # noqa: BLE001 - the worker answers every request
                send({"id": ident, "failed": "".join(traceback.format_exception(type(error), error,
                                                                                error.__traceback__))})
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    return 1
            finally:
                leave()
            owed = True
            continue
        if op == "adopt":
            home = str(request.get("home") or home)  # the standby, taken: its script's folder from now on
            continue
        if op != "build":
            send({"id": ident, "failed": f"unknown request {op!r}"})
            continue
        try:
            requested = runtime.validate(request.get("execution"))
            if requested != execution or runtime.describe() != execution:
                raise ValueError("the worker's Python environment changed; restart the selected engine before building again")
            adopt(request.get("env"), own)
            cwd = request.get("cwd")
            os.chdir(cwd or home)
            script = Path(request["script"])
            # Where the build is, frame by frame; each report holds its model's last.
            said = progress(ident, script=script, cwd=cwd)
            with building(said):
                said.load()
                kernel(lambda text: send({"id": ident, "notice": text}))
                reports = build(script, request.get("functions") or None,
                                log=lambda text: send({"id": ident, "log": text}), cwd=Path(cwd) if cwd else None,
                                verify=bool(request.get("verify")), profile=bool(request.get("profile")),
                                run=request.get("run"), cache=request.get("cache"))
            said.attach(reports)
            resident = resident_after_build()
            retirement(reports, resident)  # said in its reports: the daemon drains it, then retires it
            # Its memory now, which the daemon's status shows (``rssMb``).
            send({"id": ident, "done": reports, "rssMb": None if resident is None else round(resident)})
        except BuildError as error:
            send({"id": ident, "failed": str(error)})
        except BaseException as error:  # noqa: BLE001 - the worker answers every request
            send({"id": ident, "failed": "".join(traceback.format_exception(type(error), error, error.__traceback__))})
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                return 1
        finally:
            leave()
        owed = True  # answered: the cycles the build left, collected once idle
    return 0


if __name__ == "__main__":
    sys.exit(main())
