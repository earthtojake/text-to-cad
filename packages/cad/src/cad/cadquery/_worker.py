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


def _own_modules(script: Path) -> dict[str, str]:
    """The script's own modules a build loaded, by file: every module whose file lies outside the
    interpreter's folders and the library, with its digest."""
    roots = {os.path.normcase(os.path.realpath(root)) for root in (sys.prefix, sys.base_prefix) if root}
    import cad

    library = os.path.normcase(os.path.realpath(Path(cad.__file__).resolve().parent.parent))
    found: dict[str, str] = {}
    for module in list(sys.modules.values()):
        file = getattr(module, "__file__", None)
        if not isinstance(file, str) or not file.endswith(".py"):
            continue
        real = os.path.normcase(os.path.realpath(file))
        if real.startswith(library) or any(real.startswith(root) for root in roots):
            continue
        if Path(real) == Path(os.path.realpath(script)):
            continue
        digest = _digest(Path(file))
        if digest is not None:
            found[str(Path(file).resolve())] = digest
    return found


def _forget_own(script: Path) -> None:
    """Every module of the script's own a build loaded, forgotten, so the next load reads the code as it is
    on disk now (the kernel's ``build.load_script`` does the same through its trace, which this environment
    has no kernel for): the modules whose files lie outside the interpreter's folders and the library."""
    files = set(_own_modules(script)) | {str(Path(script).resolve())}
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


def _kernel() -> str:
    import importlib.metadata

    found = []
    for name in ("cadquery", "cadquery-ocp", "cadquery-ocp-novtk"):
        try:
            found.append(f"{name} {importlib.metadata.version(name)}")
        except importlib.metadata.PackageNotFoundError:
            continue
    return ", ".join(found) or "cadquery"


def _closure(script: Path, name: str, modules: dict[str, str]) -> dict[str, Any]:
    """What this build is made of: the script's and its own modules' digests, CadQuery's build and the
    function, keyed; the record a report carries (``located``'s shape) and the document's main label holds
    (``portable.closure_record``)."""
    digest = _digest(script)
    key = hashlib.blake2b(json.dumps([str(script), name, digest, sorted(modules.items()), _kernel()]).encode(),
                          digest_size=16).hexdigest()
    return {"script": str(script), "digest": digest, "modules": modules, "key": key, "kernel": _kernel()}


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
    from cad.engine.progress import Progress
    from cad.registry import producer_for

    script = Path(request["script"]).resolve()
    cwd = Path(request["cwd"]) if request.get("cwd") else None
    shown = os.path.relpath(script, cwd) if cwd is not None else str(script)
    said = Progress(lambda frame: send({"id": request.get("id"), "progress": frame}), script=script, cwd=cwd)
    started = time.perf_counter()
    _memo.install()
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
    modules = _own_modules(script)
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
            try:
                with _memo.run() as run:
                    value = model.function()
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
            header["closure"] = _closure(script, model.name, modules)
            fallbacks = {identity.rpartition(os.sep)[2]: list(run.unkeyable)} if run.unkeyable else {}
            reports.append({
                "ok": True, "model": name, "id": model.id, "source": source, "kernel": "cadquery",
                "memo": {"hits": run.tally.get("hits", 0), "misses": run.tally.get("misses", 0),
                         "unkeyable": run.tally.get("unkeyable", 0)},
                "bodies": {identity: "run"},
                "timings": {"load": round(loaded, 4), "body": round(body, 4), "total": round(loaded + body, 4)},
                "retention": {"keys": 0.0, "reads": {}, "fallbacks": fallbacks},
                "closure": {"key": header["closure"]["key"],
                            "modules": [[path, digest] for path, digest in sorted(modules.items())], "inputs": []},
                "files": {},
                "portable": {"header": header, "bytes": base64.b64encode(data).decode("ascii")}})
    finally:
        declaring._CONTEXT.build = None
    said.attach(reports)
    return reports


def main() -> int:
    from cad.engine.worker import adopt, kept, request_cap, resident_after_build, resident_mb, retirement

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
                os.chdir(request.get("cwd") or home)
                reports = build(request, send)
                cap = request_cap(request)
                resident = resident_after_build(cap)
                retire = retirement(reports, resident, cap)
                send({"id": ident, "done": reports, "rssMb": None if resident is None else round(resident),
                      **({"retire": True} if retire else {})})
            except Exception as error:  # noqa: BLE001 - said to the daemon, as the kernel's worker says it
                send({"id": ident, "failed": f"{type(error).__name__}: {error}"})
            finally:
                os.chdir(home)
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
