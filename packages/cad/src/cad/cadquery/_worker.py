"""The CadQuery worker: a CadQuery script's warm process, beside the engine's kernel workers.

The daemon starts one per script (``cad_server.engine.services.CADQUERY``) in the Python the script was run
with -- the environment of ``cad[cadquery]`` that ``cad run`` made, whose contract names its kernel
``cadquery`` (``cad.engine.contract.kernel_here``) -- and keeps it between runs, so the CadQuery memo
(``_memo``) that lives in it makes an edit cost what it changed. It speaks the worker protocol
(``cad.engine.frames``: ``ready``, then an answer per request, progress frames between) with one difference
from the kernel's worker (``cad.engine.worker``): it holds no document. A ``build`` runs each ``@model``
function of the script under the memo and answers, per model, the report a kernel worker's build answers --
``ok``, ``model``, ``id``, ``source``, ``memo`` (the run's hits and misses), ``bodies``, ``timings``, ``closure``
(the script's and its modules' digests) -- with the result as a portable description (``portable``: the
bridge's header and dump, ``cad.cadquery._bridge.portable``) in place of a document; the daemon has its
documents worker make the document of it and holds it whole (``models.Models.embody``), so the pages,
exports, snapshots and the cache read what the daemon holds, and nothing is ever asked of this worker but
builds (``result``, ``save`` and ``export`` are refused by name, ``where`` has no answer: no trace is kept).

A child model a body calls (``Model.__call__`` inside the run) is run here too, under the same memo, and its
value handed to the body (``api.Document.inside``); it is no document of its own in this worker. A model
with file decorators is refused: a CadQuery model declares no file, its files are exports of its document.
A body that returns anything but a CadQuery ``Workplane``, ``Shape``, ``Sketch`` or ``Assembly`` fails its
report, naming what it returned.
"""

from __future__ import annotations

import base64
import gc
import hashlib
import json
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from cad.engine import frames

__all__ = ["build", "main"]


def _digest(path: Path) -> str | None:
    try:
        return hashlib.blake2b(path.read_bytes(), digest_size=16).hexdigest()
    except OSError:
        return None


def _project(script: Path) -> Path:
    """The folder the script's own modules live under: the root of its package where it is in one (the folder
    above the topmost ``__init__.py``, ``model.module_of``), else its folder."""
    from cad.engine.model import module_of

    _name, _package, root = module_of(script)
    return Path(root) if root is not None else Path(script).resolve().parent


def _library_roots() -> tuple[str, ...]:
    """Where no file is the project's own code or data, however the project's folder contains it: the
    interpreter's folders (its prefixes and every site-packages, so an environment ``cad run`` made under the
    project -- a cache folder inside it -- is the libraries', never the script's own modules, which a load
    would forget and a closure digest) and the library."""
    import site

    import cad

    roots = [root for root in (sys.prefix, sys.base_prefix, sys.exec_prefix) if root]
    try:
        roots.extend(site.getsitepackages())
    except AttributeError:  # a virtualenv's site module may lack it
        pass
    roots.extend(path for path in sys.path if path.rstrip(os.sep).endswith(("site-packages", "dist-packages")))
    user = site.getusersitepackages() if hasattr(site, "getusersitepackages") else None
    if user:
        roots.append(user)
    roots.append(str(Path(cad.__file__).resolve().parent.parent))
    return tuple(dict.fromkeys(os.path.normcase(os.path.realpath(root)) + os.sep for root in roots))


def _own_modules(script: Path) -> dict[str, str]:
    """The script's own modules a build loaded, by file: every module whose file lies under the script's
    project (``_project``) and not under the interpreter's folders or the library (``_library_roots``), the
    script itself apart, with its digest. Read after a body ran, so a module the body imported inside itself
    counts."""
    project = os.path.normcase(os.path.realpath(_project(script))) + os.sep
    libraries = _library_roots()
    own = str(Path(script).resolve())
    found: dict[str, str] = {}
    for module in list(sys.modules.values()):
        file = getattr(module, "__file__", None)
        if not isinstance(file, str) or not file.endswith(".py"):
            continue
        real = os.path.normcase(os.path.realpath(file))
        if not real.startswith(project) or real.startswith(libraries) or "__pycache__" in real:
            continue
        resolved = str(Path(file).resolve())
        if resolved == own:
            continue
        digest = _digest(Path(file))
        if digest is not None:
            found[resolved] = digest
    return found


# Every file a build of this worker found to be a script's own module (``_own_modules``): forgotten before the
# next load, wherever that script is, so no module of a folder built before stands in for one of the same name.
_OWN_SEEN: set[str] = set()


def _forget_own(script: Path) -> None:
    """Every module of the script's own a build loaded, forgotten, so the next load reads the code as it is
    on disk now (the kernel's ``build.load_script`` does the same through its trace, which this environment
    has no kernel for): the modules under the script's project, and every own module a build here found
    before (``_OWN_SEEN``)."""
    files = set(_own_modules(script)) | _OWN_SEEN | {str(Path(script).resolve())}
    for name, module in list(sys.modules.items()):
        file = getattr(module, "__file__", None)
        if isinstance(file, str) and str(Path(file).resolve()) in files:
            sys.modules.pop(name, None)


def _load(script: Path) -> Any:
    """The script as a fresh module, as the kernel's worker loads one (``cad.engine.build.load_script``): a
    script inside a package by its dotted name, a loose one by its stem, its folder last on the path
    (``model.seat``), no bytecode written; a script that would bear the library's name refused."""
    import importlib
    import importlib.util

    from cad.engine.build import LIBRARY_NAMES, BuildError
    from cad.engine.model import module_of, seat

    _forget_own(script)
    importlib.invalidate_caches()
    name, package, root = module_of(script)
    if name.partition(".")[0] in LIBRARY_NAMES:
        raise BuildError(f"{script} would be imported as {name}, under the library's own name "
                         f"{name.partition('.')[0]!r}: rename it")
    seat(script, root)
    sys.dont_write_bytecode = True
    if package is not None:
        sys.modules.pop(name, None)
        module = importlib.import_module(name)
        found = getattr(module, "__file__", None)
        if not found or Path(found).resolve() != Path(script).resolve():
            raise BuildError(f"{script} is module {name} of its package, but importing {name} finds {found}")
        return module
    spec = importlib.util.spec_from_file_location(name, script)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot load {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


# The files a body opens, heard while a body runs (``_hear``: an audit hook, installed once a process, which
# does nothing while no body runs): the body's inputs, held to their bytes in its closure, as the kernel
# worker holds a body's reads.
_OPENED: list[list[str] | None] = [None]
_HOOKED: list[bool] = []


def _heard(event: str, args: tuple) -> None:
    opened = _OPENED[0]
    if opened is None or event != "open" or not args:
        return
    path = args[0]
    if isinstance(path, (str, bytes, os.PathLike)):
        try:
            opened.append(os.path.abspath(os.fsdecode(path)))
        except (TypeError, ValueError):
            pass


def _hear() -> None:
    if not _HOOKED:
        sys.addaudithook(_heard)
        _HOOKED.append(True)


# Where no file is an input: the interpreter's folders and the library (what a body imports, never its data),
# bytecode, the system's virtual files (``/proc``, ``/sys``, ``/dev``: what a thread pool or a clock reads), and
# the person's cache folders (what a library keeps for itself: a font index, a compiled kernel).
_VIRTUAL = ("/proc/", "/sys/", "/dev/")


def _caches() -> tuple[str, ...]:
    home = Path.home()
    named = [os.environ.get("XDG_CACHE_HOME") or str(home / ".cache"), str(home / "Library" / "Caches"),
             os.environ.get("LOCALAPPDATA") or ""]
    return tuple(os.path.normcase(os.path.realpath(folder)) + os.sep for folder in named if folder)


def _inputs(opened: list[str], script: Path, modules: dict[str, str]) -> dict[str, str]:
    """The files a body opened that are its inputs, by digest: regular files outside the interpreter's folders
    and the library (``_library_roots``), the system's virtual files and the person's caches, that are not the
    script or a module it imported (those are the closure's modules)."""
    outside = (*_library_roots(), *_caches(), *_VIRTUAL)
    code = {str(Path(script).resolve()), *modules}
    found: dict[str, str] = {}
    for path in dict.fromkeys(opened):
        real = os.path.normcase(os.path.realpath(path))
        if real.startswith(outside) or "__pycache__" in real:
            continue
        resolved = str(Path(path).resolve())
        if resolved in code or resolved in found or not os.path.isfile(resolved):
            continue
        digest = _digest(Path(resolved))
        if digest is not None:
            found[resolved] = digest
    return found


def _kernel() -> str:
    import importlib.metadata

    found = []
    for name in ("cadquery", "cadquery-ocp", "cadquery-ocp-novtk"):
        try:
            found.append(f"{name} {importlib.metadata.version(name)}")
        except importlib.metadata.PackageNotFoundError:
            continue
    return ", ".join(found) or "cadquery"


def _closure(script: Path, name: str, modules: dict[str, str], inputs: dict[str, str]) -> dict[str, Any]:
    """What this build is made of: the script's digest, its own modules' (those the body imported inside it
    too: read after the body ran), the files the body opened (``inputs``), CadQuery's build and the function,
    keyed together; the record a report carries (``located``'s shape) and the document's main label holds
    (``portable.closure_record``). An edit to any of them is another key, so another revision."""
    digest = _digest(script)
    key = hashlib.blake2b(json.dumps([str(script), name, digest, sorted(modules.items()), sorted(inputs.items()),
                                      _kernel()]).encode(), digest_size=16).hexdigest()
    return {"script": str(script), "digest": digest, "modules": modules, "inputs": inputs, "key": key,
            "kernel": _kernel()}


class _Context:
    """What a child model's call inside a body gets (``cad.engine.model._CONTEXT.build``): its function run
    here, under the same memo run, its value in a handle (``api.Document.inside``)."""

    def __init__(self) -> None:
        self.stack: list[str] = []

    def child(self, model: Any) -> Any:
        from cad.engine import api

        identity = f"{model.script}::{model.name}"
        if identity in self.stack:
            raise RecursionError(f"{identity} calls itself")
        self.stack.append(identity)
        try:
            return api.Document.inside(model, model.function())
        finally:
            self.stack.pop()

    @staticmethod
    def memo(marked: Any, args: tuple, kwargs: dict) -> Any:
        """A ``@memo`` function called in a body: run as it is; the CadQuery memo keys the kernel calls under it."""
        return marked.function(*args, **kwargs)


def build(request: dict[str, Any], send: Any) -> list[dict[str, Any]]:
    """A ``build`` request: the script's models (``functions``, or every one it defines) run under the
    memo, one report each (see the module)."""
    from cad.cadquery import _bridge, _memo
    from cad.engine import model as declaring
    from cad.engine.build import BuildError
    from cad.engine.model import models_in
    from cad.engine.progress import Progress, building

    script = Path(request["script"]).resolve()
    cwd = Path(request["cwd"]) if request.get("cwd") else None
    shown = os.path.relpath(script, cwd) if cwd is not None else str(script)
    said = Progress(lambda frame: send({"id": request.get("id"), "progress": frame}), script=script, cwd=cwd)
    with building(said):  # closed after: no held frame's timer sends one past the answer
        return _build(request, script, cwd, shown, said)


def _build(request: dict[str, Any], script: Path, cwd: Path | None, shown: str, said: Any) -> list[dict[str, Any]]:
    from cad.cadquery import _bridge, _memo
    from cad.engine import model as declaring
    from cad.engine.build import BuildError
    from cad.engine.model import models_in
    from cad.registry import producer_for

    started = time.perf_counter()
    _memo.install()
    _hear()
    said.load()
    declaring._MODELS.clear()
    declaring._NAMES.clear()
    declaring._FINGERPRINTS.clear()
    try:
        module = _load(script)
    except BuildError:
        raise
    except Exception as error:  # noqa: BLE001 - the model's own error, reported
        return [{"ok": False, "model": shown, "error": f"{type(error).__name__}: {error}",
                 "raised": traceback.format_exc()}]
    loaded = time.perf_counter() - started
    models = models_in(vars(module), script)
    wanted = request.get("functions")
    if wanted:
        by_name = {model.name: model for model in models}
        missing = [name for name in wanted if name not in by_name]
        if missing:
            raise BuildError(f"{shown} defines no model {', '.join(missing)}"
                             + (f"; it defines {', '.join(by_name)}" if by_name else "; it defines none"))
        models = [by_name[name] for name in wanted]
    elif not models:
        raise BuildError(f"{shown} defines no model")
    declared = sorted({model.explicit_name for model in models_in(vars(module), script) if model.explicit_name is not None})
    reports: list[dict[str, Any]] = []
    context = _Context()
    declaring._CONTEXT.build = context
    try:
        for model in models:
            name = f"{shown}::{model.name}"
            identity = f"{model.script}::{model.name}"
            said.plan(model, [])
            said.body(model)
            source = {**model.source, "declares": declared}
            if model.outputs:
                kinds = ", ".join(f"@{output.kind}" for output in model.outputs)
                reports.append({"ok": False, "model": name, "id": model.id, "source": source, "kernel": "cadquery",
                                "error": f"{model.name} is declared by {kinds}: a CadQuery model declares no file "
                                         "(@model alone); its files are exports of its document (cad model export)"})
                continue
            body_started = time.perf_counter()
            _OPENED[0] = []  # the files the body opens, heard while it runs and no longer
            try:
                try:
                    with _memo.run() as run:
                        value = model.function()
                finally:
                    opened, _OPENED[0] = _OPENED[0] or [], None
                producer = producer_for("model", value, where=f"model {identity}")
                if not producer.portable:
                    raise TypeError(f"model {identity} returned {type(value).__name__}: a CadQuery model returns a "
                                    "CadQuery Workplane, Shape, Sketch or Assembly")
                header, data = _bridge.portable(value, model.name)
            except Exception as error:  # noqa: BLE001 - the model's own error, reported
                reports.append({"ok": False, "model": name, "id": model.id, "source": source, "kernel": "cadquery",
                                "error": f"{type(error).__name__}: {error}", "raised": traceback.format_exc()})
                continue
            body = time.perf_counter() - body_started
            # What the body is made of, read after it ran: the modules it imported, inside the body too, and
            # the files it opened, each by its bytes.
            modules = _own_modules(script)
            _OWN_SEEN.update(modules)
            inputs = _inputs(opened, script, modules)
            header["closure"] = _closure(script, model.name, modules, inputs)
            fallbacks = {identity.rpartition(os.sep)[2]: list(run.unkeyable)} if run.unkeyable else {}
            reports.append({
                "ok": True, "model": name, "id": model.id, "source": source, "kernel": "cadquery",
                "memo": {"hits": run.tally.get("hits", 0), "misses": run.tally.get("misses", 0),
                         "unkeyable": run.tally.get("unkeyable", 0)},
                "bodies": {identity: "run"},
                "timings": {"load": round(loaded, 4), "body": round(body, 4), "total": round(loaded + body, 4)},
                "retention": {"keys": 0.0, "reads": {}, "fallbacks": fallbacks},
                "closure": {"key": header["closure"]["key"],
                            "modules": [[path, digest] for path, digest in sorted(modules.items())],
                            "inputs": [["file", path, digest] for path, digest in sorted(inputs.items())]},
                "files": {},
                "portable": {"header": header, "bytes": base64.b64encode(data).decode("ascii")}})
    finally:
        declaring._CONTEXT.build = None
        _OPENED[0] = None
    said.attach(reports)
    return reports


def main() -> int:
    import tempfile

    from cad.engine.worker import adopt, kept, request_cap, resident_after_build, resident_mb, retirement, stand

    os.environ["CAD_ENGINE_WORKER"] = "1"
    protocol = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)  # the model's prints go where the daemon reads logs from
    sys.stdout = sys.stderr
    asked = os.fdopen(os.dup(0), "rb")
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    os.close(null)
    sys.stdin = open(os.devnull, encoding="utf-8")  # noqa: SIM115 - standard input, for the worker's life
    lock = threading.Lock()

    def send(message: dict[str, Any], payload: bytes = b"") -> None:
        with lock:
            frames.write(protocol, message, payload)

    requests: "queue.Queue[dict[str, Any] | None]" = queue.Queue()

    def read() -> None:
        try:
            for line in asked:
                if not line.strip():
                    continue
                request = json.loads(line)
                if request.get("bytes"):
                    request["payload"] = asked.read(int(request["bytes"]))
                if request.get("op") == "where":
                    send({"id": request.get("id"), "where": None})  # no trace: a CadQuery document names no feature
                else:
                    requests.put(request)
        finally:
            requests.put(None)

    home = os.getcwd()
    own = kept()
    resident = resident_mb()
    send({"ready": os.getpid(), "rssMb": None if resident is None else round(resident)})
    threading.Thread(target=read, daemon=True).start()
    while True:
        request = requests.get()
        if request is None:
            break
        ident, op = request.get("id"), request.get("op")
        if op == "build":
            try:
                adopt(request.get("env"), own)
                stand(request.get("cwd"), home, tempfile.gettempdir())
                reports = build(request, send)
                cap = request_cap(request)
                resident = resident_after_build(cap)
                retire = retirement(reports, resident, cap)
                send({"id": ident, "done": reports, "rssMb": None if resident is None else round(resident),
                      **({"retire": True} if retire else {})})
            except Exception as error:  # noqa: BLE001 - said to the daemon, as the kernel's worker says it
                send({"id": ident, "failed": f"{type(error).__name__}: {error}"})
            finally:
                stand(None, home, tempfile.gettempdir())
                gc.collect()
        elif op == "save":
            send({"id": ident, "saved": {"ident": request.get("ident"), "generation": request.get("generation"),
                                         "error": "the CadQuery worker holds no document: the engine holds it whole"}})
        elif op in ("result", "export"):
            send({"id": ident, "failed": f"the CadQuery worker holds no document to answer a {op} with: the engine "
                                         "holds what it built"})
        else:
            send({"id": ident, "failed": f"the CadQuery worker answers no {op!r}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
