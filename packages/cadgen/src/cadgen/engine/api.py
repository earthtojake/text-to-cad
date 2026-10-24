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
    """One file an export wrote."""

    path: Path
    kind: str
    bytes: int
    seconds: float


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
        report = {"ok": True, "id": model.id, "source": {"script": str(model.script), "name": model.name},
                  "store": model.store}
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
            self._shape = self._transferred().shape()
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
        return Source(done["structure"], shapes, live=False)

    def _outside(self, verb: str) -> None:
        if self._inside:
            raise TypeError(f"{verb} of {self.name}: the body that calls it is building it; {verb} the "
                            "document the model call returns, once the build is done")

    def export(self, *destinations: Any) -> list[Written]:
        """``export(handle, *destinations)``: the document written to each destination."""
        self._outside("export")
        return export(self, *destinations)

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


def hand_over(shape: Any, name: Any, *, key: str | None = None, animations: Any = None, frame: Any = None) -> Document:
    """``model(shape, name=...)``: a document made of a shape this program holds -- from a script or a
    REPL, no function, no body -- handed to the engine, which holds it as a drained document is (in
    memory, and in its cache), serves its page and exports it, and records that a program it did not
    run showed it: there is no command that builds it again. Its id is ``ids.derived_id`` of the
    calling script (``frame``'s file), or the working folder where there is none, and ``name``; or
    ``ids.key_id`` of ``key``. The handle's ``shape`` is ``shape`` itself."""
    from cadgen.engine import model as declaring
    from cadgen.engine.ids import canonical, check_key, check_name, derived_id, key_id

    if getattr(declaring._CONTEXT, "build", None) is not None:
        raise TypeError("model(shape, name=...) hands a shape over from a script or a REPL; a model's body returns "
                        "its shape, and calls its children")
    if name is None:
        raise TypeError("model(shape, name=...): a shape handed over takes its document's name")
    check_name(name)
    filename = frame.f_code.co_filename if frame is not None else ""
    scope = canonical(filename if filename and os.path.isfile(filename) else os.getcwd())
    if key is not None:
        declaring.claim(check_key(key), f"{scope}::{name}")
    ident = key_id(key) if key is not None else derived_id(scope, name)
    data = _handed_bytes(shape, name, animations)
    answer = _ask({"op": "shape", "id": ident, "name": name, "scope": scope, "key": key, "program": _program(),
                   "cwd": os.getcwd(), "xbf": base64.b64encode(data).decode("ascii")})
    report = {"ok": True, "model": name, "id": ident, "url": (answer.get("done") or {}).get("url"),
              "source": {"script": scope, "name": name}, "store": "shape", "key": key, "bytes": len(data)}
    if frame is not None and frame.f_globals.get("__name__") == "__main__":
        print(f"{name}: handed over ({len(data) / 1e6:.1f} MB)")
        print(f"  id: {ident}")
        if report["url"]:
            print(f"  view: {report['url']}")
    return Document(name, Path(scope), report, Path.cwd(), shape=shape)


# --- reaching the daemon ---------------------------------------------------------------------


def _ask(message: dict[str, Any], on_log: Callable[[dict[str, Any]], None] | None = None,
         on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    from cadgen.engine.client import request

    answer = request({**message, "env": dict(os.environ)}, on_log or (lambda _message: None), on_progress=on_progress)
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

    bar = progressing.Bar() if progress is None else None
    frames = bar.frame if bar is not None else (progress or None)
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
            def relay(message: dict[str, Any]) -> None:
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
    names (built first), or an on-disk document's or mesh file's path."""
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
        raise ExportRefused(f"{path.name} is no document: an export reads an .xbf, a .step, a mesh "
                            f"({', '.join(MESHES)}) or a document id")
    if not path.is_file():
        raise ExportRefused(f"no document {path}")
    return {"path": str(path)}


def export(source: Any, *destinations: Any,
           log: Callable[[str], None] | None = None, daemon: bool = True,
           progress: Callable[[dict], None] | None = None) -> list[Written]:
    """Write a document to each destination, its kind from its suffix (``.xbf``, ``.step``,
    ``.glb``, ``.stl``, ``.3mf``, and ``.dxf`` of a planar document): the document of an
    ``.xbf``, of a ``.step`` read into one, of a handle (``Document``) or a document id (the one the
    engine holds, never built), or of a ``Model`` (built first: this program's own call); or a mesh file (``.glb``,
    ``.stl``, ``.3mf``) to the other two mesh kinds, each file holding what its format carries,
    with no CAD kernel loaded (a mesh has no B-rep: no xbf, STEP or DXF is made from one). Several
    destinations read the document once. The file holds what the code built: no option selects a part or a state
    (``README``, the law of options). ``daemon=False`` does it in this process, cold. A GLB
    carries every configuration sequence the document defines, as a clip."""
    from cadgen.engine.export import ExportRefused, kind_of

    if not destinations:
        raise ExportRefused("export names at least one destination")
    resolved = [Path(os.fspath(destination)).resolve() for destination in destinations]
    for destination in resolved:
        kind_of(destination)
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
    return [Written(Path(row["path"]), row["kind"], row["bytes"], row["seconds"]) for row in done["files"]]


def _exported(order: dict[str, Any], spec: dict[str, Any], shown: Callable[[str], None], daemon: bool,
              progress: Callable[[dict], None] | None = None) -> dict:
    """An ``export`` request answered by the worker that holds the document (``worker._export``)."""
    if daemon:
        done = _ask(order, lambda message: shown(message["log"]), progress)["done"]
    else:
        from cadgen.engine.build import BuildError
        from cadgen.engine.worker import _export

        try:
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
             measurements: Any = None) -> Drawn | list[Drawn]:
    """Draw a document (``.xbf``, ``.step``, or a document id: the one the engine holds) or a mesh
    file (``.glb``, ``.stl``, ``.3mf``) into ``out`` (a ``.png``) as the viewer draws it: one
    picture, a ``Drawn``. A ``Model`` is built first: the document drawn is the one its worker
    holds in memory, whether or not an xbf of it is on disk. ``annotation`` (the viewer's
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
    a picture that fails writes none of the job's, leaving every output as it was."""
    if job is not None:
        if out is not None:
            raise TypeError("snapshot() takes out or job, not both: a job's outputs name its pictures")
        return _job(job, source, display=display, camera=camera, grid=grid, preview=preview, pose=pose, width=width,
                    height=height, size_profile=size_profile, daemon=daemon, annotation=annotation,
                    measurements=measurements)
    if source is None or out is None:
        raise TypeError(f"snapshot() missing required argument: {'source' if source is None else 'out'!r}")
    from cadgen.engine import snapshot as drawing

    out = drawing.picture_path(out, source)
    return _snapshot(source, out, display=display, camera=camera, grid=grid, preview=preview, pose=pose,
                     width=width, height=height, size_profile=size_profile, daemon=daemon, annotation=annotation,
                     measurements=measurements)


def _snapshot(source: Any, out: Path, *, display: Any, camera: Any, grid: bool, preview: bool, pose: Any,
              width: int | None, height: int | None, size_profile: str | None, daemon: bool, annotation: Any,
              measurements: Any) -> Drawn:
    from cadgen.engine import snapshot as drawing
    from cadgen.engine.ids import is_id
    from cadgen.engine.model import Model

    if isinstance(source, (Model, Document)) or is_id(os.fspath(source)):
        if out.suffix.lower() != ".png":
            raise drawing.SnapshotRefused(f"a snapshot is a .png; {out.name} is not one")
        spec = _source(source)
        drawing.options(display, camera, grid, width, height, size_profile)  # refused here, before any build
        drawing.parse_annotation(annotation)  # refused here, before any build
        if isinstance(annotation, (str, Path)) and not str(annotation).lstrip().startswith("{"):
            annotation = str(Path(annotation).expanduser().resolve())  # read in the worker, beside its packets
        draw = {"out": str(out), "display": display, "camera": camera, "grid": grid, "preview": preview,
                "pose": drawing.parse_pose(pose) if isinstance(pose, str) else pose, "width": width,
                "height": height, "size_profile": size_profile, "annotation": annotation,
                "measurements": drawing.parse_measurements(measurements)}
        order = {"op": "export", "source": spec, "destinations": [], "draw": draw,
                 "cwd": str(source.cwd) if isinstance(source, Document) else os.getcwd()}
        found = _exported(order, spec, lambda _text: None, daemon)["drawn"]
        return Drawn(out, found["width"], found["height"], found)
    shown, framed, size = drawing.options(display, camera, grid, width, height, size_profile)
    found = drawing.snapshot(Path(os.fspath(source)), out, display=shown, camera=framed, preview=preview,
                             size=None if width is None and height is None and size_profile is None else size,
                             daemon=daemon, pose=drawing.parse_pose(pose) if isinstance(pose, str) else pose,
                             annotation=drawing.parse_annotation(annotation),
                             measurements=drawing.parse_measurements(measurements), annotation_source=annotation)
    return Drawn(out, found["width"], found["height"], found)


def _job(job: Any, source: Any, *, display: Any, camera: Any, grid: bool, preview: bool, pose: Any,
         width: int | None, height: int | None, size_profile: str | None, daemon: bool, annotation: Any,
         measurements: Any) -> list[Drawn]:
    """``snapshot(job=...)``: every picture the job names (see ``snapshot``)."""
    from cadgen.engine import snapshot as drawing

    _heard("source", os.fspath(source) if source is not None else drawing.job_input(job))
    pictures = drawing.job_pictures(job, source, display=display, camera=camera, grid=grid, preview=preview, pose=pose,
                                    width=width, height=height, size_profile=size_profile, annotation=annotation,
                                    measurements=measurements)
    return [Drawn(Path(found["output"]), found["width"], found["height"], found)
            for found in drawing.draw_pictures(pictures, daemon=daemon)]


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


def inspect(source: Any, ref: str | None = None, *, query: str | None = None) -> Facts | list[Facts]:
    """What a ref names in a document (``refs``: ``hand/finger.2/face 7``, ``base/f:...``, a
    copied ``/abs/kit.xbf#...`` line) and what made it. An element answers what the kernel
    measures of it -- its points placed where its occurrence stands, in the document's frame --
    with its canonical ``ref``, its occurrence's ``path`` and ``made_by``; a part or an assembly
    its volume and its mass: each part's volume times its material's density, summed
    (``cli.weighed``). One answer per selector (a list for several). Without ``ref``, the build
    closure the xbf holds (``previous``): its engine, libraries, source, modules, inputs and
    key, read from the file alone. A ref that names nothing, or several things, is refused by
    name (``refs.RefError``). No query builds a missing model or writes its declared
    outputs. ``query="build"`` returns file metadata/closure or live build metadata;
    ``query="geometry"`` requires a ref, and ``query="closure"`` accepts none."""
    import urllib.error
    import urllib.request

    from cadgen.engine import refs
    from cadgen.engine.cli import weighed

    from cadgen.engine.addresses import key, split

    named = os.fspath(source).partition("#")[0]
    source, embedded_ref = split(source)
    if ref is not None and embedded_ref is not None and ref != embedded_ref:
        raise EngineError("source reference and ref disagree")
    ref = ref if ref is not None else embedded_ref
    query = query or ("geometry" if ref is not None else "closure")
    if query not in ("closure", "geometry", "build"):
        raise EngineError("query is closure, geometry or build")
    if (query == "geometry") != (ref is not None):
        raise EngineError("only a geometry query requires a reference")
    path = _document(source, "inspect", named)
    if query == "build":
        if not isinstance(path, Path):
            found = _ask({"op": "document", "id": path})["document"]  # a model's live record says stale
            if "path" not in found:
                return {"file": None, "live": _ask({"op": "model_info", "id": path})["model"]}
            path = Path(found["path"])
        from cadgen.engine import previous

        stat = path.stat()
        _writer, closure = previous.scan(path)
        return {"file": {"path": str(path), "bytes": stat.st_size, "modifiedAt": stat.st_mtime},
                "live": None, "closure": json.loads(closure) if closure else None}
    if ref is None and isinstance(path, Path):
        from cadgen.engine import previous

        writer, found = previous.scan(path)
        if found is None:
            raise EngineError(f"{path.name} holds no build closure"
                              + (f" (written by {writer})" if writer else ": no engine wrote it"))
        return json.loads(found)
    if ref is not None:
        refs.parse(ref)  # refuse invalid refs before serving
    answer = _ask({"op": "serve", "path": str(path)})
    base = answer["url"].rsplit("/", 1)[0]
    ident = answer["doc"]

    def get(route: str) -> Any:
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{base}/api/doc/{ident}{route}",
                    headers={"Authorization": "Bearer " + answer.get("token", "")}), timeout=300) as response:  # noqa: S310
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            try:
                said = json.loads(error.read()).get("error")
            except ValueError:
                said = None
            raise refs.RefError(said or str(error)) from None

    structure = get("")
    if ref is None:
        if not structure.get("closure"):
            raise EngineError(f"{source} holds no build closure")
        # A model held with no worker whose code changed since it was built says so (``stale``).
        return {**structure["closure"], "stale": structure["stale"]} if structure.get("stale") else structure["closure"]
    found: list[Facts] = []
    volumes: dict[str, float] = {}
    for hit in refs.resolve_structure(structure, ref, path):
        if hit.kind is None:
            for key in sorted({structure["prototypes"][node.payload["prototype"]]["key"] for node in hit.node.parts()}):
                if key not in volumes:
                    volumes[key] = get(f"/part/{key}/volume")["volume"]
            found.append(weighed(structure, hit, volumes))
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
             ".dxf": "dxf", ".urdf": "urdf", ".sdf": "sdf", ".srdf": "srdf"}
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
