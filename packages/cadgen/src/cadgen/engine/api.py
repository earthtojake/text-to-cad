"""The engine's verbs as functions, one per command; ``cli`` is a thin argparse over them.

    export(source, *destinations) -> list[Written]
    snapshot(source, out, *, display=None, camera=None, grid=False, preview=False, pose=None,
             width=None, height=None, annotation=None, measurements=None) -> Drawn
    snapshot(source=None, *, job, the same flags) -> list[Drawn]
    serve(source, port=0) -> Served
    inspect(source, ref=None) -> Facts (the build closure without a ref)
    status() / stop() / daemon()

Every one goes through the daemon (``client``), so the warm worker of the script or of the
document does the work and keeps what it made in memory for the next call. No verb builds
source text: a script's models build when called by the script (``python model.py``), each call
returning the document's handle (``Document``), or from Python by ``Model.build()`` (``build_script``,
the debug seam), a ``Report``. ``hand_over`` makes a document of a shape a program holds
(``model(shape, name=...)``). Each verb takes a handle, a document id or a file path. A build writes the model as its
joints place it, and ``export`` writes that document as it is: a posed or partial file is a
function in the model's code. A picture, and the state a mechanism is drawn in, are
``snapshot``'s, never cached.

The engine counts nothing. After each build, ``export`` and ``snapshot`` it calls every
function in ``observers``, in the verb's thread, with one plain dict of what the verb did
(``_facts``): kinds, counts, times, the warm worker's part, and an error's type and frames --
never a name, a path or a message of the person's but the frames' files as Python has them. An
observer that raises is passed over, and the verb returns or raises as it would have. cadgen's
telemetry is one, appended by cadgen's own ``__init__`` (law 3: nothing here imports it).
"""

from __future__ import annotations

import base64
import functools
import json
import math
import os
import re
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar, cast

__all__ = ["Document", "Drawn", "EngineError", "Facts", "Report", "Served", "Written", "export", "hand_over",
           "observers", "serve", "server", "snapshot", "status", "stop", "inspect"]

class EngineError(RuntimeError):
    """A request the engine refused or could not run: its words."""


def _files(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every file a model's build wrote or kept: the model's own, then each child model's
    (``child_models``, the models its run ran, each of which writes its own files)."""
    found = dict(report.get("files") or {})
    for child in (report.get("child_models") or {}).values():
        found.update(child.get("files") or {})
    return found


@dataclass
class Report:
    """A build of one script: each model's report (``models``), in order; each holds the
    reports of the child models its run ran (``child_models``), each of which wrote its own
    files."""

    models: list[dict[str, Any]]
    wall: float = 0.0
    fresh: bool | None = None  # whether the worker was started for it; None built in this process

    @property
    def ok(self) -> bool:
        return all(report.get("ok") for report in self.models)

    @property
    def files(self) -> dict[str, dict[str, Any]]:
        return {path: row for report in self.models for path, row in _files(report).items()}

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.models)

    def __len__(self) -> int:
        return len(self.models)


@dataclass
class Written:
    """One file an export wrote, or found holding its bytes already and left as it was
    (``written`` False)."""

    path: Path
    kind: str
    bytes: int
    seconds: float
    written: bool = True


@dataclass
class Drawn:
    """A snapshot: the PNG and what the page drew (``report``)."""

    path: Path
    width: int
    height: int
    report: dict[str, Any]


@dataclass
class Served:
    url: str
    port: int


Facts = dict


_UNSET: Any = object()


class Document:
    """A document's handle: what a model call returns, never a bare shape and never a report.

    ``id`` and ``url`` (its page, where the engine serves it; None for a child inside the body that
    builds it, which has no page yet), ``name``, ``shape`` and the verbs ``export(*paths)`` and
    ``snapshot(out, **picture_options)``, which are ``export(handle, ...)`` and ``snapshot(handle,
    ...)``. ``shape`` is the built result as a build123d compound tree -- every assembly a
    ``Compound`` of its components, every part placed, named, coloured and given its material as the
    document has them -- transferred into this process from the engine that holds the document,
    and the kernel loaded, on its first access, never before. A child's handle, inside the body that
    calls it, holds the result itself: ``.shape`` is the shape this process made. A shape handed
    over (``hand_over``) holds the shape it was given. ``report`` is the build's report of it."""

    def __init__(self, name: str, script: Path, report: dict[str, Any], cwd: Path, *, shape: Any = _UNSET,
                 inside: bool = False) -> None:
        self.name = name
        self.script = Path(script)
        self.report = report
        self.cwd = Path(cwd)
        self._shape = shape
        self._inside = inside

    @classmethod
    def inside(cls, model: Any, shape: Any) -> "Document":
        """A child's handle inside the build that runs it: its id, and its result in this process."""
        report = {"ok": True, "id": model.id, "source": {"script": str(model.script), "name": model.name}}
        return cls(model.name, model.script, report, Path.cwd(), shape=shape, inside=True)

    @property
    def id(self) -> str:
        return str(self.report["id"])

    @property
    def url(self) -> str | None:
        return self.report.get("url")

    @property
    def ok(self) -> bool:
        return bool(self.report.get("ok"))

    @property
    def files(self) -> dict[str, dict[str, Any]]:
        """Every file the build wrote or kept: the model's, then each child model's."""
        return _files(self.report)

    def __repr__(self) -> str:
        return f"<document {self.name} {self.id}>"

    @property
    def shape(self) -> Any:
        if self._shape is _UNSET:
            from cadgen.engine.mechanism import TRANSFERRED

            shape = self._transferred().shape()
            shape.__dict__[TRANSFERRED] = self.name  # no joints came with it: ``posed`` says to pass the handle
            self._shape = shape
        return self._shape

    def _transferred(self) -> Any:
        """The document as the engine holds it, asked by its id (``result``): its structure and each
        part's shape bytes, as an ``export.Source`` of this process. Nothing is built."""
        from cadgen.engine.export import Source

        answer = _ask({"op": "result", "id": self.id, "cwd": str(self.cwd)})
        payload = base64.b64decode(answer.get("payload") or "")
        done = answer["done"]
        shapes, at = {}, 0
        for key, size in done["shapes"]:
            shapes[key] = payload[at:at + size]
            at += size
        placements = {tuple(path): matrix for path, matrix in done.get("placements") or ()}
        return Source(done["structure"], shapes, live=False, local_placements=placements)

    def _outside(self, verb: str) -> None:
        if self._inside:
            raise TypeError(f"{verb} of {self.name}: the body that calls it is building it; {verb} the "
                            "document the model call returns, once the build is done")

    def export(self, *destinations: Any) -> list[Written]:
        """``export(handle, *destinations)``: the document written to each destination."""
        self._outside("export")
        return _said(_exporting(self, destinations), destinations)

    def snapshot(self, out: Any, *, display: Any = None, camera: Any = None, grid: bool = False,
                 preview: bool = False, pose: Any = None, width: int | None = None, height: int | None = None,
                 size_profile: str | None = None, daemon: bool = True, annotation: Any = None,
                 measurements: Any = None) -> Drawn:
        """``snapshot(handle, out, ...)``: the document drawn into ``out`` (a ``.png``); every option is
        the ``snapshot`` verb's, about the picture (law 22)."""
        self._outside("snapshot")
        return cast(Drawn, snapshot(self, out, display=display, camera=camera, grid=grid, preview=preview,
                                    pose=pose, width=width, height=height, size_profile=size_profile, daemon=daemon,
                                    annotation=annotation, measurements=measurements))


def _handed_bytes(shape: Any, name: str, animations: Any) -> bytes:
    """A shape handed over as the bytes of its document (``document.to_bytes``), made in this
    process: its parts, names, colours, materials, placements and the declarations on it -- joints,
    mechanism states, sequences, couplings -- and its animations (``animations=``: the ``animation()``
    builders, each on the shape or a shape below it)."""
    import build123d as bd

    from cadgen.engine import document
    from cadgen.engine.animations import ANIMATIONS, Animation

    if not isinstance(shape, bd.Shape):
        raise TypeError(f"model() takes a function to declare, or a build123d shape and its name=; "
                        f"not {type(shape).__name__}")
    if shape.__dict__.get("_wrapped") is None:
        raise ValueError(f"model(shape, name={name!r}): the shape is empty")
    given = list(animations or [])
    if given:
        below: list[Any] = []
        stack = [shape]
        while stack:
            node = stack.pop()
            below.append(node)
            stack.extend(getattr(node, "children", None) or ())
        for found in given:
            if not isinstance(found, Animation):
                raise TypeError(f"animations= takes animation() builders, not {type(found).__name__}")
            if not any(node is found.assembly for node in below) or \
                    found.name not in (found.assembly.__dict__.get(ANIMATIONS) or {}):
                raise ValueError(f"animation {found.name!r} is on no shape of {name!r}: make it on the shape handed "
                                 "over, or on a part of it")
    tree = document.collect(shape, name)
    for part in tree.parts:
        part.shape = document.direct(part.shape)
        part.key = document.geometry_key(part.shape)
    document.merge(tree)
    doc = document.to_xcaf(tree, document.Kept())
    return document.to_bytes(doc, [part.shape for part in tree.parts])


def hand_over(shape: Any, name: Any, *, animations: Any = None, frame: Any = None) -> Document:
    """``model(shape, name=...)``: a document made of a shape this program holds -- from a script or a
    REPL, no function, no body -- handed to the engine, which holds it as a drained document is (in
    memory, and in its cache), serves its page and exports it, and records that a program it did not
    run showed it: there is no command that builds it again. Its id is ``ids.derived_id`` of the
    calling script (``frame``'s file), or the working folder where there is none, and ``name``. The handle's ``shape`` is ``shape`` itself."""
    from cadgen.engine import model as declaring
    from cadgen.engine.ids import canonical, check_name, derived_id

    if getattr(declaring._CONTEXT, "build", None) is not None:
        raise TypeError("model(shape, name=...) hands a shape over from a script or a REPL; a model's body returns "
                        "its shape, and calls its children")
    if name is None:
        raise TypeError("model(shape, name=...): a shape handed over takes its document's name")
    check_name(name)
    filename = frame.f_code.co_filename if frame is not None else ""
    scope = canonical(filename if filename and os.path.isfile(filename) else os.getcwd())
    ident = derived_id(scope, name)
    data = _handed_bytes(shape, name, animations)
    answer = _ask({"op": "shape", "id": ident, "name": name, "scope": scope, "program": _program(),
                   "cwd": os.getcwd(), "xbf": base64.b64encode(data).decode("ascii")})
    report = {"ok": True, "model": name, "id": ident, "url": (answer.get("done") or {}).get("url"),
              "source": {"script": scope, "name": name}, "kind": "shape", "bytes": len(data)}
    if frame is not None and frame.f_globals.get("__name__") == "__main__":
        print(f"{name}: handed over ({len(data) / 1e6:.1f} MB)")
        print(f"  id: {ident}")
        if report["url"]:
            print(f"  view: {report['url']}")
        sys.stdout.flush()  # read now, as a model call's report is (``cli._reported``)
    return Document(name, Path(scope), report, Path.cwd(), shape=shape)


# --- reaching the daemon ---------------------------------------------------------------------


def _ask(message: dict[str, Any], on_log: Callable[[dict[str, Any]], None] | None = None,
         on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    from cadgen.engine.client import environment, request

    answer = request({**message, "env": environment()}, on_log or (lambda _message: None), on_progress=on_progress)
    if answer is None:
        raise EngineError("no engine daemon")
    _heard("worker", answer.get("worker"))
    if "failed" in answer:
        raise _failed(answer)
    return answer


def _failed(answer: dict[str, Any]) -> Exception:
    """What a request that failed in the engine raises here: a refusal as the type it was raised
    as there (``worker.refusal``: an ``ExportRefused``, a ``SnapshotRefused``, a ``KinematicsError``,
    any ``ValueError`` of the engine's), so a caller tells it from a failure as it does with
    ``daemon=False`` and the CLI exits 2 for it; anything else an ``EngineError``, its words."""
    import importlib

    text = str(answer["failed"])
    module, _, name = str(answer.get("kind") or "").partition(":")
    kind: Any = None
    if module == "builtins" or module == "cadgen.engine" or module.startswith("cadgen.engine."):
        try:
            kind = getattr(importlib.import_module(module), name, None)
        except ImportError:
            kind = None
    if not (isinstance(kind, type) and issubclass(kind, ValueError)):
        return EngineError(text) if not module else ValueError(text)
    try:
        error = kind(text)
    except TypeError:  # a refusal whose type takes more than its words
        error = ValueError(text)
    for key in ("state", "rebuild"):  # a document not held: what it is, and what builds it again
        if key in answer and hasattr(error, key):
            setattr(error, key, answer[key])
    error._engine_refusal = True  # type: ignore[attr-defined]  # the worker's, not this process's (``_error``)
    return error


def _program() -> str | None:
    """The program this process runs, ``__main__``'s file: what a document it builds names as the
    command that builds it again (``models.Models.missing``); None where it has no file."""
    found = getattr(sys.modules.get("__main__"), "__file__", None)
    return os.path.abspath(found) if isinstance(found, str) and os.path.isfile(found) else None


_RUN: list[str] = []


def _run() -> str:
    """This process's run: its pid and a token of its own (a pid is used again), made on its
    first build; a forked child makes its own. The worker serves one run's calls of a script
    from one load while its files stand as they were (``build.build``)."""
    if not _RUN or not _RUN[0].startswith(f"{os.getpid()}:"):
        _RUN[:] = [f"{os.getpid()}:{os.urandom(8).hex()}"]
    return _RUN[0]


def _built(script: Path, functions: list[str] | None, *, verify: bool = False, profile: bool = False,
           log: Callable[[str], None] | None = None, daemon: bool = True,
           progress: Any = None) -> tuple[list[dict[str, Any]], Any, float]:
    """One build of a script's models in the warm worker that holds it, or in this process: its reports, whether the worker was started for it, and its wall time. Where
    the build is goes, frame by frame, to ``progress`` (``progress.py``): by default a bar on
    stderr when it is a terminal and nowhere when it is not; ``False`` nowhere; a callable takes
    each frame. Each model's report holds its last (``progress``)."""
    from cadgen.engine import progress as progressing
    from cadgen.engine.build import BuildError

    frames, bar = progressing.sink(progress)
    shown = log or (lambda _text: None)
    if bar is not None:
        shown = bar.around(shown)  # a line of the log goes above the bar
    cwd = Path.cwd()
    started = time.perf_counter()
    try:
        if not daemon:
            from cadgen.engine import build as engine_build

            said = progressing.Progress(frames or (lambda _frame: None), script=script, cwd=cwd)
            try:
                with progressing.building(said):
                    said.load()
                    reports = engine_build.build(script, functions, log=shown, cwd=cwd, verify=verify,
                                                 profile=profile)
            except BuildError as error:
                raise EngineError(str(error)) from None
            said.attach(reports)
            fresh = None
        else:
            def told(text: str) -> None:
                print(text, file=sys.stderr)

            waiting = bar.around(told) if bar is not None else told

            def relay(message: dict[str, Any]) -> None:
                if message.get("stream") in ("waiting", "notice"):  # said whoever logs: behind a build of
                    # this script, or the worker's first load of the kernel (``worker.kernel``)
                    waiting(message["log"])
                    return
                shown(message["log"] if message.get("stream") == "model" else f"  {message['log']}")

            order = {"op": "build", "script": str(script), "functions": functions,
                     "cwd": str(cwd), "verify": verify, "profile": profile, "run": _run(), "program": _program()}
            answer = _ask(order, relay, frames)
            reports, fresh = answer["done"], answer.get("worker", {}).get("fresh")
    finally:
        if bar is not None:
            bar.close()
    return reports, fresh, time.perf_counter() - started


def build_script(script: Path, functions: list[str] | None = None, *, verify: bool = False, profile: bool = False,
                 log: Callable[[str], None] | None = None, daemon: bool = True, progress: Any = None) -> Report:
    """A script's models -- ``functions``, or every one it defines -- each built as its
    decorators declare, and every child model each calls as its own declare (law 10): what
    explicit ``Model.build()`` requests ask. A script takes no file
    flags: its decorators are the whole definition of what it writes (law 11). ``progress`` as
    ``_built`` has it."""
    reports, fresh, wall = _built(Path(script).resolve(), functions, verify=verify, log=log, daemon=daemon,
                                  progress=progress, profile=profile)
    return Report(reports, round(wall, 4), fresh)


def _source(source: Any) -> dict[str, Any]:
    """What an export or a snapshot reads: a document's handle (``Document``) or its id (``{"id"}``:
    the document the engine holds, read as it is and never built), a ``Model`` this Python program
    names (``daemon=False`` only: built in this process, cold; through the engine the model is
    called first, ``_called``), or an on-disk document's or mesh file's path."""
    from cadgen.engine.export import MESHES, SOURCES, ExportRefused
    from cadgen.engine.ids import is_id
    from cadgen.engine.model import Model

    if isinstance(source, Model):
        return {"script": str(source.script), "function": source.name}
    if isinstance(source, Document):
        return {"id": source.id}
    text = os.fspath(source)
    if is_id(text):
        return {"id": text}
    path = Path(text).resolve()
    if path.suffix.lower() not in SOURCES + MESHES:
        # A script is the commonest such source: its run makes the document, and prints its id.
        run = (f"; run `cadgen run {text}` first, then export its document by id"
               if path.suffix.lower() == ".py" else "")
        raise ExportRefused(f"{path.name} is no document: an export reads an .xbf, a .step, a mesh "
                            f"({', '.join(MESHES)}) or a document id{run}")
    if not path.is_file():
        raise ExportRefused(f"no document {path}")
    return {"path": str(path)}


def export(source: Any, *destinations: Any,
           log: Callable[[str], None] | None = None, daemon: bool = True,
           progress: Callable[[dict], None] | None = None) -> list[Written]:
    """Write a document to each destination, its kind from its suffix (``.xbf``, ``.step``,
    ``.glb``, ``.stl``, ``.3mf``, and ``.dxf`` of a planar document): the document of an
    ``.xbf``, of a ``.step`` read into one, of a handle (``Document``) or a document id (the one the
    engine holds, never built), or of a ``Model`` (called first, as this program's own call of it builds it); or a mesh file (``.glb``,
    ``.stl``, ``.3mf``) to the other two mesh kinds, each file holding what its format carries,
    with no CAD kernel loaded (a mesh has no B-rep: no xbf, STEP or DXF is made from one). Several
    destinations read the document once. The file holds what the code built: no option selects a part or a state
    (``README``, the law of options). ``daemon=False`` does it in this process, cold. A GLB
    carries every configuration sequence the document defines, as a clip. A call the program's own
    code makes (``python exports.py``) says each file, as ``cadgen export`` does. Where the export is
    goes, frame by frame, to ``progress`` (``progress.py``: its ``read`` of a file source, each
    destination's ``write``), as ``_built`` takes it: by default a bar on stderr when it is a
    terminal and nowhere when it is not, ``False`` nowhere, a callable each frame."""
    from cadgen.engine import progress as progressing

    frames, bar = progressing.sink(progress)
    if bar is not None:
        log = bar.around(log or (lambda _text: None))  # a line of the log goes above the bar
    try:
        return _said(_exporting(source, destinations, log, daemon, frames), destinations)
    finally:
        if bar is not None:
            bar.close()


def _said(written: list[Written], destinations: tuple) -> list[Written]:
    """``written``, a line said of each file when the call is the program's own (the first frame
    outside this module, past the verb's observer, is ``__main__``'s), as a model call's report is
    said (``Model.__call__``)."""
    frame = sys._getframe(1)
    while frame is not None and frame.f_globals.get("__name__") == __name__:
        frame = frame.f_back
    if frame is not None and frame.f_globals.get("__name__") == "__main__":
        from cadgen.engine.cli import said_written

        said_written(written, destinations)
    return written


def _exporting(source: Any, destinations: tuple, log: Callable[[str], None] | None = None, daemon: bool = True,
               progress: Callable[[dict], None] | None = None) -> list[Written]:
    from cadgen.engine.export import ExportRefused, kind_of

    if not destinations:
        raise ExportRefused("export names at least one destination")
    resolved = [Path(os.fspath(destination)).resolve() for destination in destinations]
    for destination in resolved:
        kind_of(destination)
    source = _called(source, daemon)
    spec = _source(source)
    if "path" in spec:
        from cadgen.engine.export import refused

        for destination in resolved:  # every one, before anything is written
            why = refused(spec["path"], destination)
            if why:
                raise ExportRefused(why)
    cwd = str(source.cwd) if isinstance(source, Document) else os.getcwd()
    shown = log or (lambda _text: None)
    order = {"op": "export", "source": spec, "destinations": [str(path) for path in resolved], "cwd": cwd}
    done = _exported(order, spec, shown, daemon, progress)
    return [Written(Path(row["path"]), row["kind"], row["bytes"], row["seconds"], row.get("written", True))
            for row in done["files"]]


def _called(source: Any, daemon: bool) -> Any:
    """A ``Model`` source through the engine is its call's document: the model is built as a call
    of it builds -- its run, its program, the engine's cache and the served documents with it, so
    an unchanged model is taken from its key or replayed by the program's one memo pass -- and the
    export or the snapshot reads that document by its handle. Any other source as it is."""
    from cadgen.engine.model import Model

    return source() if daemon and isinstance(source, Model) else source


def _exported(order: dict[str, Any], spec: dict[str, Any], shown: Callable[[str], None], daemon: bool,
              progress: Callable[[dict], None] | None = None) -> dict:
    """An ``export`` request answered by the worker that holds the document (``worker._export``), or
    in this process (``daemon=False``); its progress frames to ``progress`` where one is given
    (``progress.py``: the worker's over its pipe, this process's as its own job)."""
    if daemon:
        done = _ask(order, lambda message: shown(message["log"]), progress)["done"]
    else:
        from cadgen.engine import progress as progressing
        from cadgen.engine.build import BuildError
        from cadgen.engine.worker import _export, job_progress

        said = job_progress(progress or (lambda _frame: None), order)
        try:
            with progressing.building(said):
                done = _export(order, shown)
        except BuildError as error:
            raise EngineError(str(error)) from None
    _heard("reports", done.get("reports"))
    failed = [report for report in done.get("reports") or [] if not report.get("ok")]
    if failed:
        raise EngineError(failed[0].get("error") or f"the build of {failed[0].get('model')} failed")
    return done


def snapshot(source: Any = None, out: Any = None, *, job: Any = None, display: Any = None, camera: Any = None,
             grid: bool = False, preview: bool = False, pose: Any = None, width: int | None = None,
             height: int | None = None, size_profile: str | None = None, daemon: bool = True, annotation: Any = None,
             measurements: Any = None, progress: Any = None) -> Drawn | list[Drawn]:
    """Draw a document (``.xbf``, ``.step``, or a document id: the one the engine holds) or a mesh
    file (``.glb``, ``.stl``, ``.3mf``) into ``out`` (a ``.png``) as the viewer draws it: one
    picture, a ``Drawn``. A ``Model`` is called first, as the program's own call of it builds it:
    the document drawn is the one the engine then holds, whether or not an xbf of it is on disk. ``annotation`` (the viewer's
    annotation: its file's path, its object, or the Quick Edit packet that carries it) and
    ``measurements`` are drawn over the model; ``camera="authored"`` draws it from the view the
    annotation's ink was drawn in, which the packet holds. ``out`` a folder (a path ending in a
    separator, or one that is there) is given a name inside it, the source's stem and the time
    (``snapshot.picture_path``). A snapshot refused or failed leaves the file at ``out`` as it
    was (``snapshot.write_png``).

    ``job`` in place of ``out`` is every picture a job names (``cadgen snapshot --job``), a list of
    ``Drawn``: a Quick Edit packet (the ``.snapshot.json`` the viewer writes, its path or its
    object), a job or a list of jobs, each job a view drawn as it was -- its camera, display, hidden
    and isolated parts, pose, the packet's ink and dimensions -- at its output settings, into each
    of its outputs (``snapshot.job_pictures``). ``source`` is then drawn in place of every job's
    input; a flag given overrides every job. Every request is checked before anything renders, and
    a picture that fails writes none of the job's, leaving every output as it was.

    Where each picture is goes, frame by frame, to ``progress`` (``progress.py``: ``scene`` while the
    document is served, meshed and its scene made, ``draw`` while the frame is drawn, ``write`` as
    the picture is written), as ``export`` takes it: by default a bar on stderr when it is a
    terminal and nowhere when it is not, ``False`` nowhere, a callable each frame."""
    from cadgen.engine import progress as progressing

    frames, bar = progressing.sink(progress)
    try:
        return _pictured(source, out, job=job, display=display, camera=camera, grid=grid, preview=preview, pose=pose,
                         width=width, height=height, size_profile=size_profile, daemon=daemon, annotation=annotation,
                         measurements=measurements, progress=frames)
    finally:
        if bar is not None:
            bar.close()


def _pictured(source: Any, out: Any, *, job: Any, display: Any, camera: Any, grid: bool, preview: bool, pose: Any,
              width: int | None, height: int | None, size_profile: str | None, daemon: bool, annotation: Any,
              measurements: Any, progress: Callable[[dict], None] | None) -> Drawn | list[Drawn]:
    """``snapshot``, its frames to ``progress`` (a callable, or None for nowhere)."""
    if job is not None:
        if out is not None:
            raise TypeError("snapshot() takes out or job, not both: a job's outputs name its pictures")
        return _job(job, source, display=display, camera=camera, grid=grid, preview=preview, pose=pose, width=width,
                    height=height, size_profile=size_profile, daemon=daemon, annotation=annotation,
                    measurements=measurements, progress=progress)
    if source is None or out is None:
        raise TypeError(f"snapshot() missing required argument: {'source' if source is None else 'out'!r}")
    from cadgen.engine import snapshot as drawing

    out = drawing.picture_path(out, source)
    return _snapshot(source, out, display=display, camera=camera, grid=grid, preview=preview, pose=pose,
                     width=width, height=height, size_profile=size_profile, daemon=daemon, annotation=annotation,
                     measurements=measurements, progress=progress)


def _snapshot(source: Any, out: Path, *, display: Any, camera: Any, grid: bool, preview: bool, pose: Any,
              width: int | None, height: int | None, size_profile: str | None, daemon: bool, annotation: Any,
              measurements: Any, progress: Callable[[dict], None] | None = None) -> Drawn:
    from cadgen.engine import snapshot as drawing
    from cadgen.engine.ids import is_id
    from cadgen.engine.model import Model

    if isinstance(source, (Model, Document)) or is_id(os.fspath(source)):
        if out.suffix.lower() != ".png":
            raise drawing.SnapshotRefused(f"a snapshot is a .png; {out.name} is not one")
        drawing.options(display, camera, grid, width, height, size_profile)  # refused here, before any build
        drawing.parse_annotation(annotation)  # refused here, before any build
        source = _called(source, daemon)
        spec = _source(source)
        if isinstance(annotation, (str, Path)) and not str(annotation).lstrip().startswith("{"):
            annotation = str(Path(annotation).expanduser().resolve())  # read in the worker, beside its packets
        draw = {"out": str(out), "display": display, "camera": camera, "grid": grid, "preview": preview,
                "pose": drawing.parse_pose(pose) if isinstance(pose, str) else pose, "width": width,
                "height": height, "size_profile": size_profile, "annotation": annotation,
                "measurements": drawing.parse_measurements(measurements)}
        order = {"op": "export", "source": spec, "destinations": [], "draw": draw,
                 "cwd": str(source.cwd) if isinstance(source, Document) else os.getcwd()}
        found = _exported(order, spec, lambda _text: None, daemon, progress)["drawn"]
        if "id" in spec:
            found["document"] = spec["id"]  # what was drawn, by the id it was named by
        return Drawn(out, found["width"], found["height"], found)
    shown, framed, size = drawing.options(display, camera, grid, width, height, size_profile,
                                          board=Path(os.fspath(source)).suffix.lower() == ".kicad_pcb")
    found = drawing.snapshot(Path(os.fspath(source)), out, display=shown, camera=framed, preview=preview,
                             size=None if width is None and height is None and size_profile is None else size,
                             daemon=daemon, pose=drawing.parse_pose(pose) if isinstance(pose, str) else pose,
                             annotation=drawing.parse_annotation(annotation),
                             measurements=drawing.parse_measurements(measurements), annotation_source=annotation,
                             progress=progress)
    return Drawn(out, found["width"], found["height"], found)


def _job(job: Any, source: Any, *, display: Any, camera: Any, grid: bool, preview: bool, pose: Any,
         width: int | None, height: int | None, size_profile: str | None, daemon: bool, annotation: Any,
         measurements: Any, progress: Callable[[dict], None] | None = None) -> list[Drawn]:
    """``snapshot(job=...)``: every picture the job names (see ``snapshot``)."""
    from cadgen.engine import snapshot as drawing

    _heard("source", os.fspath(source) if source is not None else drawing.job_input(job))
    pictures = drawing.job_pictures(job, source, display=display, camera=camera, grid=grid, preview=preview, pose=pose,
                                    width=width, height=height, size_profile=size_profile, annotation=annotation,
                                    measurements=measurements)
    return [Drawn(Path(found["output"]), found["width"], found["height"], found)
            for found in drawing.draw_pictures(pictures, daemon=daemon, progress=progress)]


def _document(source: Any, verb: str, named: str | None = None) -> Path | str:
    """The document ``serve`` or ``inspect`` reads: a document id as it is, or an on-disk
    ``.xbf`` or STEP by its canonical path; anything else is no document, refused by name
    (``ValueError``)."""
    from cadgen.engine.addresses import key

    path = key(os.fspath(source))
    if isinstance(path, Path):
        if path.suffix.lower() not in (".xbf", ".step", ".stp"):
            raise ValueError(f"{named or os.fspath(source)} is no document: {verb} reads an .xbf, a .step or a document id")
        if not path.is_file():
            raise ValueError(f"no document {named or source}")
    return path


def serve(source: Any, port: int = 0, three: str | None = None) -> Served:
    """Serve a document (``.xbf``, ``.step``, or a document id the engine holds) from the daemon;
    its page's URL, ``/<id>``."""
    from cadgen.engine.addresses import key

    path = _document(source, "serve")
    if three is None:
        from cadgen.engine.serve import find_three

        found = find_three()
        three = str(found) if found else None
    answer = _ask({"op": "serve", "path": str(path), "port": port, "three": three})
    return Served(answer["url"], answer["port"])


def inspect(source: Any, ref: str | None = None, *, query: str | None = None, progress: Any = None) -> Facts | list[Facts]:
    """What a ref names in a document (``refs``: ``hand/finger.2/face 7``, ``base/f:...``, a
    copied ``/abs/kit.xbf#...`` line) and what made it. An element answers what the kernel
    measures of it -- its points placed where its occurrence stands, in the document's frame --
    with its canonical ``ref``, its occurrence's ``path`` and, of a model's document, ``made_by``
    (a file names no model); a part or an assembly
    its volume and its mass: each part's volume times its material's density, summed
    (``cli.weighed``), its world bounds and a part's placement (``_placed``). One answer per selector (a list for several). Without ``ref``, the build
    closure the xbf holds (``previous``): its engine, libraries, source, modules, inputs and
    key, read from the file alone. A ref that names nothing, or several things, is refused by
    name (``refs.RefError``). No query builds a missing model or writes its declared
    outputs. ``query="build"`` returns file metadata/closure or live build metadata;
    ``query="geometry"`` requires a ref, and ``query="closure"`` accepts none.
    ``query="summary"`` (``cadgen inspect DOC`` with no ref) is ``{"summary", "closure"}``:
    what the document holds at a glance (``_summary``), and its closure, as the engine holds it; of
    a GLB, ``{"mesh"}``: its nodes, meshes and animations, from its JSON alone (``_mesh``).
    ``query="structure"`` is the summary without bounds, volume or mass and requests no measurements.
    No form meshes anything. A part's volume and box are cached by geometry key and measured in
    batches. The summary's measurement goes, frame by frame, to ``progress`` (``progress.py``:
    ``inspect-measure``, ``measure``, counted as the engine tells each part's facts in), as ``export``
    takes it -- by default a bar on stderr when it is a terminal and nowhere when it is not,
    ``False`` nowhere, a callable each frame."""
    from cadgen.engine import progress as progressing

    frames, bar = progressing.sink(progress)
    try:
        return _inspected(source, ref, query, frames)
    finally:
        if bar is not None:
            bar.close()


def _inspected(source: Any, ref: str | None, query: str | None, progress: Callable[[dict], None] | None) -> Facts | list[Facts]:
    """``inspect``, its summary's frames to ``progress`` (a callable, or None for nowhere)."""
    from urllib.parse import quote

    from cadgen.engine import refs
    from cadgen.engine.cli import weighed

    from cadgen.engine.addresses import key, split

    named = os.fspath(source).partition("#")[0]
    source, embedded_ref = split(source)
    if ref is not None and embedded_ref is not None and ref != embedded_ref:
        raise EngineError("source reference and ref disagree")
    ref = ref if ref is not None else embedded_ref
    query = query or ("geometry" if ref is not None else "closure")
    if query not in ("closure", "geometry", "build", "summary", "structure"):
        raise EngineError("query is closure, geometry, build, summary or structure")
    if (query == "geometry") != (ref is not None):
        raise EngineError("only a geometry query requires a reference")
    mesh = key(os.fspath(source))
    if isinstance(mesh, Path) and mesh.suffix.lower() in (".glb", ".stl", ".3mf"):
        return _mesh(mesh, named, query)
    path = _document(source, "inspect", named)
    if query == "build":
        if not isinstance(path, Path):
            found = _ask({"op": "document", "id": path})["document"]  # a model's: its live record
            if "path" not in found:
                return {"file": None, "live": _ask({"op": "model_info", "id": path})["model"]}
            path = Path(found["path"])
        from cadgen.engine import previous

        stat = path.stat()
        _writer, closure = previous.scan(path)
        return {"file": {"path": str(path), "bytes": stat.st_size, "modifiedAt": stat.st_mtime},
                "live": None, "closure": json.loads(closure) if closure else None}
    if ref is None and isinstance(path, Path) and query == "closure":
        from cadgen.engine import previous

        if path.suffix.lower() in (".step", ".stp"):
            raise EngineError(_no_closure(path))
        writer, found = previous.scan(path)
        if found is None:
            raise EngineError(f"{path.name} holds no build closure"
                              + (f" (written by {writer})" if writer else ": no engine wrote it"))
        return json.loads(found)
    if ref is not None:
        refs.parse(ref)  # refuse invalid refs before serving
    ident = _ask({"op": "serve", "path": str(path)})["doc"]

    def get(route: str, counted: Callable[[int, int, str], None] | None = None) -> Any:
        # Read through the engine's door, never its loopback port: a sandboxed shell has the one.
        # ``counted``: a read of the parts' facts hears each part's as the engine has it (``Server.measure``).
        heard = None if counted is None else (lambda said: counted(said["done"], said["total"], said["key"]))
        read = _ask({"op": "read", "route": f"/api/doc/{ident}{route}", **({"progress": True} if heard else {})},
                    on_progress=heard)
        if 200 <= read["status"] < 300:
            return json.loads(read["body"])
        try:
            said = json.loads(read["body"]).get("error")
        except ValueError:
            said = None
        raise refs.RefError(said or f"HTTP {read['status']}")

    structure = get("")
    if query in ("summary", "structure"):
        return {"summary": _summary(structure, path, get, ident, progress, measured=query == "summary"),
                "closure": structure.get("closure")}
    if ref is None:
        if not structure.get("closure"):
            raise EngineError(f"{source} holds no build closure")
        return structure["closure"]
    found: list[Facts] = []
    hits = refs.resolve_structure(structure, ref, path)
    # Every part a part's or an assembly's ref weighs, measured in one read (its facts by key).
    weighs = sorted({structure["prototypes"][node.payload["prototype"]]["key"]
                     for hit in hits if hit.kind is None for node in hit.node.parts()})
    measured = get("/volumes?keys=" + ",".join(quote(key, safe="") for key in weighs)) if weighs else {}
    volumes = {key: facts["volume"] for key, facts in measured.items()}
    boxes = {key: facts.get("box") for key, facts in measured.items()}
    for hit in hits:
        if hit.kind is None:
            found.append({**weighed(structure, hit, volumes), **_placed(structure, hit, boxes)})
            continue
        prototype = structure["prototypes"][hit.node.payload["prototype"]]
        matrix = structure["instances"][hit.node.payload["instance"]]["matrix"]
        try:
            facts = get(f"/part/{prototype['key']}/{hit.kind}/{hit.ordinal}")
        except refs.RefError as error:  # an ordinal past the part's elements
            raise refs.RefError(str(error).replace("the part", hit.path or os.path.basename(str(path)), 1)) from None
        found.append({"ref": hit.ref, "path": hit.path, "part": prototype["name"],
                      "key": prototype["key"], "kind": hit.kind, "ordinal": hit.ordinal, "name": hit.name,
                      **refs.placed_facts(facts, matrix)})
    return found[0] if len(found) == 1 else found


def _mesh(path: Path, named: str, query: str) -> Facts:
    """``inspect`` of a mesh file: a GLB's nodes, meshes and animations, each with its duration, read
    from its JSON alone (``{"mesh": ...}``, without a ref); an STL's or a 3MF's, and any ref or
    closure of a mesh, refused in words. A mesh has no B-rep, so no ref names a face of it, and no
    build closure: only an .xbf carries one."""
    if not path.is_file():
        raise ValueError(f"no document {named}")
    if query not in ("summary", "structure") or path.suffix.lower() != ".glb":
        said = (f"`cadgen inspect {path.name}` alone tells its nodes, meshes and animations, and "
                f"`cadgen viewer {path.name}` shows it" if path.suffix.lower() == ".glb" else
                f"inspect reads nothing more of it: `cadgen viewer {path.name}` shows it, and the document it was "
                "exported from, inspected, tells the rest")
        raise ValueError(f"{path.name} is a mesh: it has no B-rep for a ref to name and no build closure (only an "
                         f".xbf carries one); {said}")
    from cadgen.engine.formats.gltf import _chunks

    gltf, _binary = _chunks(path)
    accessors = gltf.get("accessors") or []
    animations = []
    for at, animation in enumerate(gltf.get("animations") or []):
        ends = [(accessors[sampler["input"]].get("max") or [0.0])[0] for sampler in animation.get("samplers") or []
                if isinstance(sampler, dict) and isinstance(sampler.get("input"), int) and sampler["input"] < len(accessors)]
        animations.append({"name": animation.get("name") or f"animation {at + 1}",
                           "duration": float(max(ends, default=0.0))})
    return {"mesh": {"name": path.name, "path": str(path), "nodes": len(gltf.get("nodes") or []),
                     "meshes": len(gltf.get("meshes") or []), "animations": animations}}


def _placed(structure: dict[str, Any], hit: Any, boxes: dict[str, Any]) -> dict[str, Any]:
    """Where the occurrence a ref names stands, in the document's frame: its world ``bounds`` (each
    part's box, as the engine measured it, placed where its occurrence stands; None with no
    geometry), and for a part its ``placement`` -- the origin and axes of its instance's matrix, as
    the structure holds it (an assembly's own placement the structure does not hold). Nothing is built or measured again."""
    from cadgen.engine.refs import placed_facts

    def clean(values: list[float]) -> list[float]:
        return [round(value, 9) + 0.0 for value in values]

    low, high = [math.inf] * 3, [-math.inf] * 3
    nodes = hit.node.parts()
    for node in nodes:
        instance = structure["instances"][node.payload["instance"]]
        box = boxes.get(structure["prototypes"][instance["prototype"]]["key"])
        if box:
            box = placed_facts({"box": box}, instance["matrix"])["box"]
            low = [min(a, b) for a, b in zip(low, box["min"])]
            high = [max(a, b) for a, b in zip(high, box["max"])]
    found: dict[str, Any] = {"bounds": None if low[0] == math.inf else
                             {"min": clean(low), "max": clean(high), "size": clean([b - a for a, b in zip(low, high)])}}
    if hit.node.part:
        m = structure["instances"][hit.node.payload["instance"]]["matrix"]
        found["placement"] = {"origin": clean(m[12:15]), "x": clean(m[0:3]), "y": clean(m[4:7]), "z": clean(m[8:11])}
    return found


def _no_closure(path: Path) -> str:
    """Why a STEP holds no build closure: the format carries none (an xbf does, law 1), whoever wrote
    it -- cadgen's own export among them -- and what to inspect instead."""
    return (f"{path.name} holds no build closure: a STEP file carries none, only an .xbf does; inspect the model's "
            f"document by its id for its closure, or name a ref in the file (cadgen inspect {path.name} REF)")


def couplings_of(kinematics: dict[str, Any]) -> list[dict[str, Any]]:
    """The mechanism's couplings as ``inspect`` lists them: each by its name, its kind -- a
    ``screw_pair`` couples one cylindrical joint, a ``rack_and_pinion_pair`` revolute and prismatic
    joints, a ``gear_pair`` revolute ones -- its joints with each one's ratio (degrees or
    millimetres per unit of the coupling's value), and, of two joints, the second's to the first's
    (``ratio``). Its joints move only through it: the coupling's name is what poses them."""
    types = {pair.get("label"): pair.get("type") for pair in kinematics.get("pairs") or []}
    found = []
    for name, coupling in (kinematics.get("couplings") or {}).items():
        joints: dict[str, list[float]] = {}
        for label, _index, ratio in coupling.get("terms") or []:
            joints.setdefault(label, []).append(ratio)
        kinds = {types.get(label) for label in joints}
        kind = ("screw_pair" if kinds == {"cylindrical"} else
                "rack_and_pinion_pair" if {"revolute", "prismatic"} <= kinds else "gear_pair")
        rows = [{"name": label, "ratio": ratios[0] if len(ratios) == 1 else ratios} for label, ratios in joints.items()]
        first, *rest = [row["ratio"] for row in rows]
        ratio = rest[0] / first if len(rest) == 1 and isinstance(first, float) and isinstance(rest[0], float) and first \
            else None
        found.append({"name": name, "kind": kind, "joints": rows, "ratio": ratio, "range": coupling.get("range")})
    return found


def _summary(structure: dict[str, Any], path: Path | str, get: Callable[..., Any], ident: str,
             progress: Callable[[dict], None] | None = None, *, measured: bool = True) -> dict[str, Any]:
    """What a served document holds, at a glance (``cadgen inspect DOC``): its name and id; its
    state -- a model's (``live``, ``held``, ...: ``ModelDocuments.state``), where the engine holds
    it and whether its cache has it, or ``file`` for a file's document; its parts (occurrences,
    distinct parts, the root's name); its bounds and volume, each part's (``.../volumes``: the
    engine's facts of every part, kept by geometry key and measured together) placed where its
    occurrences stand; its materials and their masses, where any part has one; its joints,
    mechanism states, configuration sequences and animations; and a model's declared files.
    Nothing is built. Not ``measured`` (``query="structure"``): no bounds, volume or masses, and
    nothing measured for them -- the lists alone."""
    from cadgen.engine.refs import placed_facts

    model = None
    if not isinstance(path, Path):
        from cadgen.engine.client import request

        answer = request({"op": "model_info", "id": str(path)}, start=False) or {}
        model = answer.get("model")
    if model is not None:
        state = {"state": model.get("state"), "held": model.get("held"), "cached": bool(model.get("cached")),
                 "builtAt": model.get("builtAt"), "script": (model.get("source") or {}).get("script")}
    else:
        state = {"state": "file", "path": str(path) if isinstance(path, Path) else structure.get("path")}
    prototypes, instances = structure.get("prototypes") or [], structure.get("instances") or []
    each: dict[str, dict[str, Any]] = {}
    if measured:
        from cadgen.engine.progress import Progress

        # Each distinct part counted as the engine has its facts -- held already, or as the pool
        # answers -- told by the read itself (``.../volumes``, ``counted``): never a count of its own.
        names: dict[str, str] = {}
        for prototype in prototypes:
            names.setdefault(prototype["key"], str(prototype.get("name") or ""))
        said = Progress(progress or (lambda _frame: None), kind="inspect-measure", job=str(structure.get("name") or ident))
        said.stage("measure", count=[0, len(names)])
        heard = None if progress is None else (lambda done, total, key: said.counted(done, total, detail=names.get(key, "")))
        each = get("/volumes", heard) if prototypes else {}
        said.close()
    low, high, volume = [math.inf] * 3, [-math.inf] * 3, 0.0
    materials: dict[str, dict[str, Any]] = {}
    unweighed: list[str] = []
    for instance in instances:
        prototype = prototypes[instance["prototype"]]
        facts = each[prototype["key"]] if measured else {}
        volume += facts.get("volume") or 0.0
        if facts.get("box"):
            box = placed_facts({"box": facts["box"]}, instance["matrix"])["box"]
            low = [min(a, b) for a, b in zip(low, box["min"])]
            high = [max(a, b) for a, b in zip(high, box["max"])]
        material = prototype.get("material")
        if not material:
            unweighed.append(instance["path"])
            continue
        row = materials.setdefault(material["name"], {"name": material["name"], "density": material.get("density"),
                                                      "parts": [], "mass": None})
        row["parts"].append(instance["path"])
        if measured and material.get("density") is not None:
            row["mass"] = (row["mass"] or 0.0) + (facts.get("volume") or 0.0) * 1e-9 * material["density"]
    bounds = None if low[0] == math.inf else {"min": low, "max": high, "size": [b - a for a, b in zip(low, high)]}
    kinematics = structure.get("kinematics") or {}
    built = kinematics.get("asBuilt") or {}
    joints = [{"name": pair.get("label"), "type": pair.get("type"), "range": pair.get("limits"),
               "units": pair.get("units"), "asBuilt": built.get(pair.get("label"))}
              for pair in kinematics.get("pairs") or []]
    weighed = [row["mass"] for row in materials.values() if row["mass"] is not None]
    found = {
        "name": structure.get("name"), "id": ident, "state": state,
        "parts": {"occurrences": len(instances), "distinct": len(prototypes), "root": (structure.get("tree") or {}).get("name")},
        "bounds": bounds, "volume": volume,
        "materials": list(materials.values()), "mass": sum(weighed) if weighed else None,
        "unweighed": unweighed if materials else [],
        "joints": joints,
        "couplings": couplings_of(kinematics),
        "states": [{"name": name, "values": values} for name, values in (kinematics.get("configurations") or {}).items()],
        "sequences": [{"name": name, "duration": motion.get("duration")}
                      for name, motion in (kinematics.get("motions") or {}).items()],
        "animations": structure.get("animations") or [],
        "files": list((model or {}).get("files") or []),
    }
    if not measured:
        # The lists alone: nothing was measured, so there are no bounds, volume or masses (never a zero).
        for name in ("bounds", "volume", "mass"):
            del found[name]
        found["materials"] = [{key: value for key, value in row.items() if key != "mass"} for row in found["materials"]]
    return found


def status() -> dict[str, Any] | None:
    """The daemon's workers and served documents; None when no daemon runs."""
    from cadgen.engine.client import request

    return request({"op": "status"}, start=False)


def stop() -> bool:
    """Stop the daemon, and wait until it is gone. False when none was running."""
    from cadgen.engine.client import request, wait_gone

    if request({"op": "stop"}, start=False) is None:
        return False
    if not wait_gone():
        raise EngineError("the engine daemon did not exit")
    return True


def delete(documents: Any) -> list[dict[str, Any]]:
    """``cadgen delete``: documents deleted, each by the one deletion the home's Delete is too
    (``models.delete``): what the engine holds of it, when one runs (never started for it), then its
    record and its document in the engine's cache. Each of ``documents`` is a document's id, a model's
    script or a shape's home (every document recorded of it), or a CAD file's path a page opened; the
    person's own files are never touched. One that names nothing recorded is refused (``ValueError``),
    naming each, before anything is deleted. What was deleted, ``{"id", "name", "kind"}`` each, in
    the order named."""
    from cadgen.engine import registry as registering
    from cadgen.engine.client import request
    from cadgen.engine.ids import canonical, file_id, is_id
    from cadgen.engine.models import delete as deleting

    held = registering.current()
    idents: list[str] = []
    unknown: list[str] = []
    listed: list[dict[str, Any]] | None = None
    for named in [str(document) for document in documents]:
        found: list[str] = []
        if held is not None and is_id(named):
            found = [named] if held.get(named) is not None else []
        elif held is not None:
            path = canonical(os.path.abspath(os.path.expanduser(named)))
            record = held.get(file_id(path))
            if record is not None and record.get("kind") == "file":
                found = [record["id"]]
            else:
                listed = held.list() if listed is None else listed
                found = sorted(row["id"] for row in listed if row.get("kind") != "file"
                               and canonical(registering.home(held, row)) == path)
        if not found:
            unknown.append(named)
        idents.extend(ident for ident in found if ident not in idents)
    if unknown:
        raise ValueError(f"no document is recorded for {', '.join(unknown)}: name a document's id, a model's "
                         "script or a CAD file a page opened (`cadgen status` lists the documents); nothing "
                         "was deleted")
    answer = request({"op": "delete", "ids": idents}, start=False)
    if answer is not None:
        if not answer.get("ok"):
            raise EngineError(str(answer.get("failed") or answer.get("error") or answer))
        return list(answer.get("deleted") or [])
    return [found for found in (deleting(held, ident) for ident in idents) if found is not None]


def server() -> int:
    """Run the engine server in this process (`cadgen server`)."""
    from cadgen.engine.daemon import main

    return main([])


# --- what each verb did, told to its observers ------------------------------------------------
#
# ``observers``: functions called after each build, export and snapshot with the verb's facts (``_facts``):
#
#     verb      "build", "export" or "snapshot"
#     ok        it did all it was asked
#     seconds   its wall time here
#     program   ``python model.py`` asked (``model._run_as_program``)
#     models    each model a build reported, or the one an export or a snapshot of a script built first:
#               {ok, cached (its xbf taken whole: ``cache.used``), children (models it called), parts,
#               files (the kinds it wrote or kept)}
#     worker    the warm worker's part: {fresh (started for it; None when no answer said), retired (over
#               its memory cap after it), died (its exit status, when it died under the work; else None)}
#     error     why it failed, or None: {type (the error's class, ``module.Name`` or a builtin's name; None
#               when no error says), frames ([{file, line, function}], innermost last), engine (raised in
#               the engine's own code, or its worker's), refused (the engine refused the request by name),
#               here (raised in this process, as against told by the daemon or a report)}
#     source    export, snapshot: what it read -- "xbf", "step", "glb", "stl", "threemf", "dxf", "urdf",
#               "sdf", "srdf", "model" (a script's model) or "other"
#     found     snapshot: the source file is there (a model's always is)
#     outputs   export: each destination, {kind, seconds (None for one not written)}
#     pose      snapshot: a pose was asked for
#
# The facts of a verb another verb runs are its caller's: only the outermost one tells.

observers: list[Callable[[dict[str, Any]], None]] = []

_HEARD = threading.local()  # what the daemon's answers said while a verb ran in this thread (``_heard``)
_ENGINE = os.path.dirname(os.path.abspath(__file__)) + os.sep
_SUFFIXES = {".xbf": "xbf", ".step": "step", ".stp": "step", ".glb": "glb", ".stl": "stl", ".3mf": "threemf",
             ".dxf": "dxf", ".urdf": "urdf", ".sdf": "sdf", ".srdf": "srdf", ".kicad_pcb": "kicad_pcb"}
_FRAME = re.compile(r'  File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<function>\S.*)')
_TYPE = re.compile(r"(?P<type>[A-Za-z_][A-Za-z0-9_.]*)(?::|$)")
_DIED = re.compile(r"exited \((?P<status>-?\d+)\) during the build")  # the daemon's word (``daemon.Worker.build``)
_TRACEBACK = "Traceback (most recent call last):"
# The engine's refusals, by module and name: a verb that raised one has imported its module already.
_REFUSALS = (("cadgen.engine.build", "BuildError"), ("cadgen.engine.export", "ExportRefused"),
             ("cadgen.engine.snapshot", "SnapshotRefused"))

_Verb = TypeVar("_Verb", bound=Callable[..., Any])


def _heard(name: str, value: Any) -> None:
    """Something the daemon answered while a verb runs in this thread: kept for its facts."""
    heard = getattr(_HEARD, "facts", None)
    if heard is not None and value is not None:
        heard[name] = value


def _observed(verb: str, function: _Verb) -> _Verb:
    """``function``, telling ``observers`` what it did as it returns or raises."""

    @functools.wraps(function)
    def observed(*args: Any, **kwargs: Any) -> Any:
        if not observers or getattr(_HEARD, "facts", None) is not None:
            return function(*args, **kwargs)
        _HEARD.facts = heard = {}
        started = time.perf_counter()
        try:
            result = function(*args, **kwargs)
        except BaseException as error:
            _HEARD.facts = None
            _tell(verb, args, kwargs, heard, None, error, time.perf_counter() - started)
            raise
        _HEARD.facts = None
        _tell(verb, args, kwargs, heard, result, None, time.perf_counter() - started)
        return result

    return cast(_Verb, observed)


def _tell(verb: str, args: tuple, kwargs: dict[str, Any], heard: dict[str, Any], result: Any,
          error: BaseException | None, seconds: float) -> None:
    try:
        found = _facts(verb, args, kwargs, heard, result, error, seconds)
    except Exception:  # noqa: BLE001 - facts that cannot be made are not told
        return
    for observer in list(observers):
        try:
            observer(found)
        except Exception:  # noqa: BLE001 - an observer never fails the verb it observes
            pass


def _facts(verb: str, args: tuple, kwargs: dict[str, Any], heard: dict[str, Any], result: Any,
           error: BaseException | None, seconds: float) -> dict[str, Any]:
    """What one verb did (the table above), from its arguments, what it returned or raised, and what the
    daemon's answers said meanwhile (``_heard``)."""
    from cadgen.engine import model

    if verb == "build":
        reports = result.models if isinstance(result, Report) else []
    else:
        reports = list(heard.get("reports") or [])
    worker = {"fresh": (heard.get("worker") or {}).get("fresh"),
              "retired": any(report.get("retired") for report in reports), "died": None}
    found: dict[str, Any] = {
        "verb": verb, "ok": error is None and all(report.get("ok") for report in reports),
        "seconds": round(seconds, 4), "program": bool(getattr(model._CONTEXT, "program", False)),
        "models": [_model(report) for report in reports], "worker": worker,
        "error": _error(error, reports, worker)}
    if verb in ("export", "snapshot"):
        # A job's is the file it draws, which it says as it starts (``snapshot(job=)``).
        source = heard.get("source") or (args[0] if args else kwargs.get("source"))
        found["source"] = _kind(source)
    if verb == "snapshot":
        found["pose"] = kwargs.get("pose") is not None
    if verb == "export":
        if error is None:
            found["outputs"] = [{"kind": row.kind, "seconds": row.seconds} for row in result]
        else:
            found["outputs"] = [{"kind": _SUFFIXES.get(Path(os.fspath(path)).suffix.lower(), "other"),
                                 "seconds": None} for path in args[1:]]
    if verb == "snapshot":
        found["found"] = found["source"] == "model" or Path(os.fspath(source)).is_file()
    return found


def _kind(source: Any) -> str:
    from cadgen.engine.model import Model

    if isinstance(source, (Model, Document)):
        return "model"
    from cadgen.engine.ids import is_id

    text = os.fspath(source)
    if is_id(text):
        return "model"  # a document by its id
    return _SUFFIXES.get(Path(text).suffix.lower(), "other")


def _model(report: dict[str, Any]) -> dict[str, Any]:
    return {"ok": bool(report.get("ok")), "cached": bool((report.get("cache") or {}).get("used")),
            "children": len(report.get("children") or {}), "parts": int(report.get("parts") or 0),
            "files": sorted({str(row.get("kind")) for row in (report.get("files") or {}).values() if row.get("kind")})}


def _error(error: BaseException | None, reports: list[dict[str, Any]], worker: dict[str, Any]) -> dict[str, Any] | None:
    """Why a verb failed: the first failed report's error -- a body's (the model's frames, ``build``), or
    a file the engine could not write (``trace``, the engine's) -- else what the verb raised: the worker's
    own error as it answered it, a worker that died under the work (``worker["died"]``), a refusal, or an
    error raised here."""
    told = {"engine": True, "refused": False, "here": False}
    failed = next((report for report in reports if not report.get("ok")), None)
    if failed is not None:
        trace = failed.get("trace")
        return {**_read(trace or failed.get("error") or ""), **told, "engine": bool(trace)}
    if error is None:
        return None
    if isinstance(error, EngineError):
        text = str(error)
        died = _DIED.search(text)
        if died:
            worker["died"] = int(died["status"])
            return {"type": None, "frames": [], **told}
        if _TRACEBACK in text:
            return {**_read(text), **told}
        return {"type": None, "frames": [], **told, "refused": text != "no engine daemon"}
    if getattr(error, "_engine_refusal", False):  # the worker's refusal, raised here as its type (``_failed``)
        kind = type(error)
        return {"type": kind.__qualname__ if kind.__module__ == "builtins" else f"{kind.__module__}.{kind.__qualname__}",
                "frames": [], **told, "refused": True}
    refusals = tuple(kind for kind in (getattr(sys.modules.get(module), name, None) for module, name in _REFUSALS)
                     if isinstance(kind, type))
    frames = [{"file": frame.f_code.co_filename, "line": int(line or 0), "function": frame.f_code.co_name}
              for frame, line in traceback.walk_tb(error.__traceback__)]
    kind = type(error)
    return {"type": kind.__qualname__ if kind.__module__ == "builtins" else f"{kind.__module__}.{kind.__qualname__}",
            "frames": frames, "engine": bool(frames) and os.path.abspath(frames[-1]["file"]).startswith(_ENGINE),
            "refused": isinstance(error, refusals), "here": True}


def _read(text: str) -> dict[str, Any]:
    """The last error a traceback's text shows (``traceback.format_exception``'s, the model's own frames'
    from ``build``, or the error's line alone): its type's name and its frames, innermost last."""
    kind, frames, expecting = None, [], True
    for line in text.splitlines():
        if line.startswith("Traceback ("):  # a block, or the next one of a chain
            kind, frames, expecting = None, [], True
            continue
        frame = _FRAME.fullmatch(line)
        if frame is not None:
            frames.append({"file": frame["file"], "line": int(frame["line"]), "function": frame["function"].strip()})
            expecting = True
        elif expecting and line and not line[0].isspace():  # the error's own line, after its frames
            named = _TYPE.match(line)
            kind, expecting = named["type"] if named else None, False
    return {"type": kind, "frames": frames}


# A script's models build here (law 11: ``python model.py``, ``Model.build()``): a build too.
build_script = _observed("build", build_script)
export = _observed("export", export)
snapshot = _observed("snapshot", snapshot)
