"""A build: a script's models run, their results made documents, and the files they
declare written -- in this process, with the memo this process holds.

``build(script, functions)`` loads the script afresh (its own first-party modules
too: an edit anywhere in the model's code is read; one run's later calls reuse a load
whose files stand, ``_Load``), runs each model named, or every
model the script defines, in one memo run, and then, outside the run, makes each
result a document (``document.collect``), names its parts' elements from the run's
history, writes the xbf when its content changed, and writes the exports in order:
those files and nothing else. Every model that ran writes its files: each target, and
then each child model its run ran, from the child's own document (its result as its body
returned it, its closure its own script's), once a build, its report under the target's
(``child_models``). A model whose body raises reports the error with the model's own
frames and leaves its files as they were.

What this process remembers between builds is in memory only: per part ``TShape``,
its element names and its geometry key; per model, the document it last wrote, kept
(``document.Kept``). A part a warm build hands back unchanged (the memo's hit is the same
object) is neither named nor keyed again; a document whose every part, placement, name
and colour is what the file already holds is not touched or rewritten; and any other
document is the kept one patched, only its changed prototypes made again.

Before a model's body runs or is replayed, its xbf is asked (``previous``): an xbf holding
the key the model has now is what the body would make, and the body is not run, nor any
file written. A warm worker asks its own record of the document it built and left as it
stands; a body the memo could replay is replayed only when a file of the model's last
build here moved or is gone.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import sys
import time
import traceback
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cadgen.engine.addresses import document_id
from cadgen.engine.ids import canonical, file_id

__all__ = ["BuildError", "build", "load_script"]


class BuildError(Exception):
    """A request the build cannot run: no such script, no such model."""


@dataclass
class _Written:
    signature: tuple
    stats: dict[str, tuple | None]
    # The document as written, kept in memory: the next build patches it (``document.Kept``).
    kept: Any = None
    # The build closure the file holds (``previous.manifest``, as text), or None.
    record: str | None = None
    # Per derived file this process wrote: the document's signature and the kind it was
    # written with, and its stat as written. The same three again: the file is kept.
    files: dict[str, tuple] | None = None
    # The tree the kept document was made from: what a derived file is translated from.
    tree: Any = None


@dataclass
class _Named:
    """What a build made of one part ``TShape``: its element names, its geometry key, the
    shape the document holds of it; the functions its names come from, each with its
    skeleton then (``sources.skeleton``); a number that changes whenever its names do;
    and the provenance of each feature its names hold (``made_by``)."""

    names: Any
    key: str
    shape: Any
    refs: dict[tuple[str, str], str | None]
    token: int
    features: dict[str, dict[str, Any]]


# Per part TShape, what a build made of it (``_Named``), the most recently used last.
_PARTS: "OrderedDict[Any, _Named]" = OrderedDict()
_PARTS_HELD = 1 << 16
_TOKENS = __import__("itertools").count(1)
# Per model: the document this process last wrote, kept to be patched by the next build,
# and each declared file as it left it.
_WRITTEN: dict[str, _Written] = {}
# Per document this process last built (its id: each xbf's, and its model's): per part key, what
# the build made of the part -- what ``made_by`` answers from. In memory only: provenance
# is served while this process lives, never written.
_BUILT: dict[str, dict[str, _Named]] = {}
# Per model, the functions its last run in this process ran or replayed, apart from their
# arguments: a model calling one a verification found impure is not taken from its file.
_FAMILIES: dict[str, frozenset[str]] = {}


def _first_party_modules() -> list[str]:
    """The modules of the model's own a build loaded: each by its file, and a namespace package
    (a folder with no ``__init__.py``, which has no file) by its folders. Forgetting the package
    too is what imports its modules again: ``from lib import empennage`` takes the attribute a
    package still holds before it imports anything."""
    from cadgen.engine.kernel.trace import first_party_file

    return [name for name, module in list(sys.modules.items())
            if name != "__main__" and (first_party_file(getattr(module, "__file__", None) or "")
                                       or _first_party_namespace(module))]


def _uncached_said(call: str, count: int) -> str:
    """What a call a body ran uncached does to it, and the remedy (``retention.fallbacks``)."""
    times = f"{count} call{'' if count == 1 else 's'}"
    if call.startswith("OCCT's "):
        return (f"runs {call} uncached ({times}): it is never retained; use build123d's operation for it, "
                "or an engine reader (read_step, read_xbf, read_mesh)")
    return (f"runs {call} uncached ({times}) on a shape no keyed call made (OCCT called past build123d, say): it is "
            "never retained; make that shape with build123d's operation, read it with an engine reader, or make it in "
            "a @memo function of values that returns it as made")


def _first_party_namespace(module: Any) -> bool:
    """Whether ``module`` is a namespace package whose every folder is the model's own: under no
    library root (``trace._library_roots``)."""
    if getattr(module, "__file__", None) is not None:
        return False
    try:
        folders = [Path(folder).resolve() for folder in getattr(module, "__path__", None) or ()]
    except (OSError, RuntimeError, TypeError):
        return False
    if not folders:
        return False
    from cadgen.engine.kernel.trace import _library_roots

    roots = _library_roots()
    return all(not any(root == folder or root in folder.parents for root in roots) for folder in folders)


class _SourceOnlyLoader(importlib.machinery.SourceFileLoader):
    """A first-party module compiled from the bytes on disk, never from a ``.pyc``: CPython
    takes a ``__pycache__`` file as current by the source's whole-second mtime and its size,
    so two same-length edits inside one second -- an agent's edit loop -- would run the first
    edit's bytecode while the closure keys the second's source."""

    def get_code(self, fullname: str) -> Any:
        path = self.get_filename(fullname)
        return compile(self.get_data(path), path, "exec", dont_inherit=True)


class _FirstPartyFromSource(importlib.abc.MetaPathFinder):
    """Every first-party module (``trace.first_party_file``) through ``_SourceOnlyLoader``.
    It asks the path finder itself, never the rest of ``sys.meta_path`` (two finders that
    each ask the other would hand one lookup back and forth), and answers nothing else."""

    def find_spec(self, fullname: str, path: Any, target: Any = None) -> Any:
        from cadgen.engine.kernel.trace import first_party_file

        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if (spec is None or type(spec.loader) is not importlib.machinery.SourceFileLoader or not spec.origin
                or not first_party_file(spec.origin)):
            return None
        spec.loader = _SourceOnlyLoader(spec.loader.name, spec.loader.path)
        return spec


def _from_source() -> None:
    """The model's code runs from its source: no bytecode written for anything a build
    imports, none read for a first-party module. Once per process, first on the meta path."""
    sys.dont_write_bytecode = True
    if not any(isinstance(finder, _FirstPartyFromSource) for finder in sys.meta_path):
        sys.meta_path.insert(0, _FirstPartyFromSource())


def _say(stage: str, *args: Any) -> None:
    """Say a stage of this process's build (``progress``: ``Progress.plan``, ``body``, ``named``,
    ``stage``, ``writing``) where it begins; nothing outside a build, and never a failure."""
    from cadgen.engine import progress

    said = progress.current()
    if said is None:
        return
    try:
        getattr(said, stage)(*args)
    except Exception:  # noqa: BLE001 - saying where a build is never fails it
        pass


def _plan_said(model: Any, plan: list) -> None:
    _say("plan", model, [str(target.path) for target in plan])


def load_script(script: Path) -> Any:
    """The script as a fresh module, after every first-party module a previous build loaded is
    forgotten: the model's code as it is on disk now, imported as Python imports it. Its
    folder comes first on the module search path (``model.seat``). A script inside a package
    (``model.module_of``) is imported by its dotted name (``proj.parts.model``), as ``python -m``
    imports it: its packages first, from their root, which the search path holds next, so a
    relative import, a module beside it by its own name and the package by its name all
    resolve. A loose script is the module its stem names. Every module of the model's own is
    compiled from its source on disk (``_from_source``): no bytecode is written or read."""
    from cadgen.engine.model import module_of, seat

    _from_source()
    for name in _first_party_modules():
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    name, package, root = module_of(script)
    seat(script, root)
    if package is not None:
        module = importlib.import_module(name)
        found = getattr(module, "__file__", None)
        if not found or Path(found).resolve() != Path(script).resolve():
            raise BuildError(f"{script} is module {name} of its package, but importing {name} finds {found}")
        return module
    spec = importlib.util.spec_from_file_location(name, script, loader=_SourceOnlyLoader(name, str(script)))
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


# --- one load per run ---------------------------------------------------------------------------
#
# ``python model.py`` calling its models one after another sends one request per call, each loading
# the script again. Within one run (``run``: the calling process's token, ``api._run``) the worker
# serves the later calls from the load it kept, as the calling process itself loaded the script
# once: only a load that made no kernel call (its module holds no shape a run made), and only after
# a build that ran nothing (each model taken from its key: no body ran, so the module is as its
# import left it), while every file the load read -- each first-party module and its folder, and
# each file or folder the import opened or listed -- stands as the load found it. Anything else
# loads again, as every build did: a later run, an edit, a verification, a build that ran a body.


@dataclass
class _Load:
    """A script's load kept for its run's later calls: the module and the models it defined, the
    first-party modules it imported, the stat of every file it read, and the build's key
    resolution (``sources.Symbols``), made against that module."""

    key: tuple
    stats: dict[str, tuple | None]
    module: Any
    models: dict[str, Any]
    loaded: set[str]
    symbols: Any = None
    resolved: dict | None = None
    others: dict | None = None


_LOAD: list[_Load] = []  # the one kept, if any
# The files a load opens or lists, heard while ``_HEARD`` is a list (``_heard``).
_HEARD: list[Any] = [None]
_HEARING = ("open", "os.listdir", "os.scandir")
_HOOKED: list[bool] = []


def _heard(event: str, args: tuple) -> None:
    heard = _HEARD[0]
    if heard is None or event not in _HEARING:
        return
    path = args[0] if args else None
    if path is None:
        path = "."
    if isinstance(path, (str, bytes, os.PathLike)):
        try:
            heard.append(os.path.abspath(os.fsdecode(path)))
        except (TypeError, ValueError):
            pass


def _hear() -> None:
    """Hear what a load opens and lists (``_heard``): once a process, an audit hook that does
    nothing while no load is heard."""
    if not _HOOKED:
        sys.addaudithook(_heard)
        _HOOKED.append(True)


def _loaded_files(script: Path, heard: list[str]) -> list[str]:
    """Every file a load read: the script, each first-party module it imported and that
    module's folder (a module added beside it is a load's change), each namespace package's
    folders, and what it opened or listed."""
    files = {str(script), str(script.parent)}
    for name in _first_party_modules():
        module = sys.modules.get(name)
        file = getattr(module, "__file__", None)
        if file:
            files.update((file, os.path.dirname(file)))
        files.update(str(folder) for folder in getattr(module, "__path__", None) or ())
    # A library's files are not the model's: a load never imports a library again (it stays in
    # ``sys.modules``), so what one reads at its import is no change a load would see.
    from cadgen.engine.kernel.trace import _library_roots

    roots = tuple(str(root) + os.sep for root in _library_roots())
    files.update(path for path in heard if not path.startswith(roots) and "__pycache__" not in path)
    return sorted(files)


def _made(run: Any) -> tuple:
    """What a run has made so far: its calls and its trace's features."""
    return (tuple(run.tally.values()), len(run.trace.features), len(run.registered), len(run.transient))


def _kept_load(key: tuple) -> _Load | None:
    """The load kept for ``key``'s run, when every file it read stands as it found it; taken, so
    a build that does not end as ``_keep_load`` keeps it leaves none kept."""
    if not _LOAD:
        return None
    kept = _LOAD.pop()
    if kept.key != key or any(_stat(Path(path)) != stat for path, stat in kept.stats.items()):
        return None
    return kept


def _model_traceback(error: BaseException) -> str:
    """The error with the model's own frames: those of its first-party files."""
    from cadgen.engine.kernel.trace import first_party_file

    frames = [frame for frame in traceback.extract_tb(error.__traceback__) if first_party_file(frame.filename)]
    lines = ["Traceback (the model's frames):\n"] + traceback.format_list(frames) if frames else []
    lines += traceback.format_exception_only(type(error), error)
    return "".join(lines).rstrip()


def build(script: Path, functions: list[str] | None = None, *, log: Callable[[str], None] = lambda _line: None,
          cwd: Path | None = None, verify: bool = False, profile: bool = False,
          run: str | None = None) -> list[dict[str, Any]]:
    """Run a build, optionally profiling this execution in its worker (or explicit cold caller).

    The profile covers the whole request, including child models and output processing.
    Each top-level report carries that same request-wide profile, never a cached profile.
    ``run`` names the calling process's run: its later calls may be served from this one's load
    (``_Load``); None loads the script afresh.
    """
    if not profile:
        return _build(script, functions, log=log, cwd=cwd, verify=verify, run_token=run)
    from cadgen.engine.profiling import Profile

    with Profile(project=Path(script).parent) as measured:
        reports = _build(script, functions, log=log, cwd=cwd, verify=verify, run_token=run)
    summary = measured.report()
    for report in reports:
        report["profile"] = summary
    return reports


def _build(script: Path, functions: list[str] | None = None, *, log: Callable[[str], None] = lambda _line: None,
          cwd: Path | None = None, verify: bool = False, run_token: str | None = None) -> list[dict[str, Any]]:
    """Build the script's models (``functions``, or every model it defines); one report
    per model, holding those of the child models its run ran, each of which wrote its own
    files (``child_models``). Raises BuildError for a script or function that is not there;
    a body that raises is its model's report (``ok`` false, ``error`` the model's traceback).

    A script's models write what their decorators declare (``Model.plan``) and nothing else:
    a script takes no file flags (law 11). Every file shows the model as its joints place it: a
    pose or a part is the ``export`` verb's, never a build's.

    ``verify``: every body the memo would replay -- a model's, a ``@memo`` call's -- runs
    instead, and its fresh result is compared with the logged one; the report's
    ``verify`` names each body checked and how it went, and a function whose result
    differs runs on every call for the worker's life (``memo.always``)."""
    from cadgen.engine import previous
    from cadgen.engine.kernel import determinism, memo
    from cadgen.engine.model import _KEYS, _MODELS, BuildContext, models_in

    script = Path(script).resolve()
    if not script.is_file():
        raise BuildError(f"no script {script}")
    determinism.install()
    memo.install()
    shown = _shown(script, cwd)
    reports: list[dict[str, Any]] = []
    started = time.perf_counter()
    # Per target: the model, its result (None: it wrote nothing), its body's seconds, and the
    # models that ran as its children whose files the build writes, each with its result.
    results: list[tuple[Any, Any, float, list]] = []
    from cadgen.engine import reader

    # One reader process for the build's STEP reads (``reader``), gone when the build is.
    with memo.run(script, program=run_token, model=tuple(functions or ())) as run, BuildContext() as context, \
            reader.session():
        run.verify = verify
        _MODELS.clear()  # the models this build defines, known by name to what its replays ran
        _KEYS.clear()  # and the keys their declarations claim (``model.claim``)
        load_key = (run_token, str(script), str(cwd))
        kept = _kept_load(load_key) if run_token and not verify else None
        fresh = None
        if kept is not None:
            from cadgen.engine.model import module_of, seat

            module = kept.module
            _MODELS.update(kept.models)
            seat(script, module_of(script)[2])
            context.loaded, context.symbols = kept.loaded, kept.symbols
            context.resolved, context.others = kept.resolved, kept.others
        else:
            _LOAD.clear()  # this load replaces the modules any kept one held
            made, began, heard = _made(run), time.time_ns(), []
            if run_token and not verify:
                _hear()
                _HEARD[0] = heard
            try:
                module = load_script(script)
            except BuildError:
                raise
            except Exception as error:  # noqa: BLE001 - the model's own error, reported
                return [{"ok": False, "model": f"{shown}", "error": _model_traceback(error)}]
            finally:
                _HEARD[0] = None
            context.loaded = set(_first_party_modules())
            if run_token and not verify and _made(run) == made:
                stats = {path: _stat(Path(path)) for path in _loaded_files(script, heard)}
                sources = [stats.get(getattr(sys.modules.get(name), "__file__", None) or "") for name in context.loaded]
                # A module edited while it loaded: the load may hold either version, so it is not kept.
                if all(stat is None or stat[0] < began for stat in sources):
                    fresh = _Load(load_key, stats, module, dict(_MODELS), context.loaded)
        loaded = time.perf_counter()
        context.base = script.parent
        context.script = script
        models = models_in(vars(module), script)
        if functions:
            by_name = {model.name: model for model in models}
            missing = [name for name in functions if name not in by_name]
            if missing:
                raise BuildError(f"{shown} defines no model {', '.join(missing)}"
                                 + (f"; it defines {', '.join(by_name)}" if by_name else "; it defines none"))
            models = [by_name[name] for name in functions]
        elif not models:
            from cadgen.engine.model import Memo

            marked = [value.name for value in vars(module).values()
                      if isinstance(value, Memo) and value.script == script]
            raise BuildError(f"{shown} defines no model" + (
                f"; {', '.join(marked)} {'is a @memo function' if len(marked) == 1 else 'are @memo functions'}: "
                "a model calls it, and it writes no file" if marked else ""))
        # Every model that runs writes its files once a build: a target its own, and a child
        # those of the first target whose run ran it.
        written = {f"{model.script}::{model.name}" for model in models}

        def ran(model: Any, before: set[str]) -> list:
            found = []
            for child, made in context.children(model, run, before):
                if f"{child.script}::{child.name}" not in written:
                    written.add(f"{child.script}::{child.name}")
                    found.append((child, made))
            return found

        for model in models:
            body_started = time.perf_counter()
            tally = dict(run.tally)
            keys_before = context.key_seconds
            run.reads.clear()
            run.unread.clear()
            run.bypassed.clear()
            try:
                if verify:
                    verdict, previous_report = {"used": False, "reason": "verifying"}, None
                else:
                    verdict, previous_report = _previous(model, context, shown, log)
            except Exception as error:  # noqa: BLE001 - the cache never fails a build: the body runs
                verdict, previous_report = {"used": False, "reason": f"the cache failed: {error}"}, None
            if previous_report is not None:
                timings = previous_report["timings"]
                timings["load"] = round(loaded - started, 4)
                timings["total"] = round(sum(value for name, value in timings.items() if name != "total"), 4)
                reports.append(previous_report)
                results.append((model, None, 0.0, []))
                continue
            verdict["seconds"] = round(time.perf_counter() - body_started, 4)
            body_started = time.perf_counter()
            before = set(run.statuses)
            context.called = {}
            _plan_said(model, model.plan())
            _say("body", model)
            try:
                result = context.root(model)
            except Exception as error:  # noqa: BLE001 - the model's own error, reported
                reports.append({"ok": False, "model": f"{shown}::{model.name}", "error": _model_traceback(error)})
                # A child that ran before the error writes its files all the same.
                results.append((model, None, 0.0, ran(model, before)))
                continue
            body = time.perf_counter() - body_started
            calls = {name: run.tally[name] - tally.get(name, 0) for name in run.tally}
            results.append((model, result, body, ran(model, before)))
            # What the bodies' keys cost (inside ``body``) and the modules each body's key
            # took by their bytes, with why.
            retention = {"keys": round(context.key_seconds - keys_before, 4),
                         "fallbacks": {name: list(reasons) for name, reasons in context.fallbacks.items()
                                       if name == model.identity or name in context.timings}}
            # The files each body this model ran or replayed read itself, its inputs by their
            # bytes; and one it read that is no regular file, which keeps it running: say which.
            retention["reads"] = {}
            for table, into in ((run.reads, None), (run.unread, "fallbacks")):
                for body_name, paths in table.items():
                    body_script, _, function = body_name.rpartition("::")
                    identity = f"{Path(body_script).name}::{function}"
                    shown_paths = [_shown(Path(path), Path(body_script).parent) for path in paths]
                    if into is None:
                        retention["reads"][identity] = shown_paths
                    else:
                        retention["fallbacks"].setdefault(identity, []).extend(
                            f"reads {path}, not a regular file: it runs on every build" for path in shown_paths)
            # A file read past the engine's readers (``memo._bypassed``): the call, which keeps
            # the body running, and the reader that would key it.
            for body_name, reads in run.bypassed.items():
                body_script, _, function = body_name.rpartition("::")
                retention["fallbacks"].setdefault(f"{Path(body_script).name}::{function}", []).extend(
                    f"reads {_shown(Path(path), Path(body_script).parent) if path else 'a file'} through {call}: "
                    "its body is never retained (any edit runs it whole); use read_step/read_xbf/read_mesh" for call, path in reads)
            # Each call a body ran uncached (``memo._ran_uncached``), which keeps it from being retained:
            # an OCCT maker no key names, or a build123d call given what no keyed call made.
            for body_name, counts in run.uncached.items():
                body_script, _, function = body_name.rpartition("::")
                retention["fallbacks"].setdefault(f"{Path(body_script).name}::{function}", []).extend(
                    _uncached_said(call, count) for call, count in sorted(counts.items()))
            reports.append({"ok": True, "model": f"{shown}::{model.name}", "memo": calls, "retention": retention,
                            "children": {name: round(seconds, 4) for name, seconds in context.timings.items()
                                         if name != model.identity},
                            "bodies": _statuses(run, f"{model.script}::{model.name}"), "cache": verdict})
            if verify:
                reports[-1]["verify"] = _verified(run, f"{model.script}::{model.name}")
            _FAMILIES[f"{model.script}::{model.name}"] = frozenset(
                _family(body) for body in previous.closure(run.keys, f"{model.script}::{model.name}"))
            context.timings.clear()
    load_seconds = loaded - started
    for report, (model, result, body, children) in zip(reports, results):
        report["id"] = model.id
        report["source"] = {"script": str(model.script), "name": model.name}
        report["store"] = model.store
        report["key"] = model.key
        if result is not None:
            report["timings"] = {"load": round(load_seconds, 4), "body": round(body, 4)}
            _written(model, result, run, report, log, model.plan(), context)
        # Each child that ran writes the files it declares, from its own document, after its
        # target's: its report is the target's, under its identity (``child_models``).
        for child, made in children:
            identity = f"{_shown(child.script, cwd)}::{child.name}"
            row = report.setdefault("child_models", {})[identity] = {"ok": True, "timings": {}}
            _written(child, made, run, row, log, child.plan(), context)
            if not row["ok"]:
                report["ok"] = False
                report.setdefault("error", f"{identity}: {row['error']}")
    _keep_load(kept or fresh, reports, context)
    return reports


def _keep_load(load: _Load | None, reports: list[dict[str, Any]], context: Any) -> None:
    """Keep the build's load for its run's next call when the build ran nothing: every model
    taken from its key (``_previous``), so no body touched the module (``_Load``)."""
    _LOAD.clear()
    if load is None or not reports or not all(
            report.get("ok") and (report.get("cache") or {}).get("used") for report in reports):
        return
    load.symbols, load.resolved, load.others = context.symbols, context.resolved, context.others
    _LOAD.append(load)


def _written(model: Any, result: Any, run: Any, report: dict[str, Any], log: Callable[[str], None], plan: list,
             context: Any) -> None:
    """``_finish``, a file that cannot be written its model's error."""
    try:
        _finish(model, result, run, report, log, plan, context)
    except Exception as error:  # noqa: BLE001 - a file that cannot be written is the build's error
        report["ok"] = False
        report["error"] = "".join(traceback.format_exception_only(type(error), error)).rstrip()
        report["trace"] = traceback.format_exc()


def _shown(script: Path, cwd: Path | None) -> str:
    """A path relative to ``cwd`` (the working folder by default), with ``/`` on every platform as
    the closure spells one, or whole where none can be: on Windows, a path on another drive than
    the folder's."""
    try:
        return Path(os.path.relpath(script, cwd or Path.cwd())).as_posix()
    except ValueError:
        return str(script)


def _finish(model: Any, result: Any, run: Any, report: dict[str, Any], log: Callable[[str], None],
            plan: list | None = None, context: Any = None) -> None:
    from cadgen.engine import document

    timings = report["timings"]
    plan = plan if plan is not None else model.plan()
    targets = [(target.kind, target.path) for target in plan]
    _plan_said(model, plan)
    _say("named", model.name)
    clock = time.perf_counter()
    from cadgen.engine.kernel import memo

    # The files the motions' functions open while they are sampled (``memo.listened``) are the
    # model's inputs, as its bodies' are: its closure holds them, so an edit of one is a change
    # the document's key sees.
    name = f"{model.script}::{model.name}"
    made_of: list = []

    def harvested(signature: tuple) -> Any:
        # The harvest made of this very result before (a replay of the body's run whose harvest
        # was kept, and the files its functions read unchanged): not sampled again.
        made_of.append(signature)
        found = memo.harvest_of(run, name, signature)
        if found is None:
            return None
        made_of.append(found[1])
        return found[0]

    with memo.motion_reads() as reads:
        tree = document.collect(result, model.name, harvested)
    checks, keyed = (made_of[1], True) if tree.reused else (reads.checks, reads.keyed)
    if not tree.reused and made_of:
        memo.keep_harvest(run, name, made_of[0], tree.harvest, checks, keyed)
    if tree.mechanism is not None or tree.animations is not None:
        report["harvest"] = "reused" if tree.reused else "run"
        cache = report.get("cache")
        if tree.reused and isinstance(cache, dict) and cache.get("reason"):
            cache["reason"] += "; the harvest reused"
    if checks or not keyed:
        found = run.keys.get(name)
        if found is not None:
            run.keys[name] = (found[0], [*found[1], *checks], found[2] and keyed, found[3])
    xbf = next((path for kind, path in targets if kind == "xbf"), None)
    if context is not None:
        from cadgen.engine import previous

        modules, unkeyable = context.modules(model)
        folder = Path(xbf).parent if xbf is not None else model.script.parent
        made = previous.manifest(run.keys, f"{model.script}::{model.name}", folder, model, modules, unkeyable,
                                 context.named(model))
        tree.closure = previous.text(made)
        report["closure"] = previous.located(made, folder)
    timings["collect"] = round(time.perf_counter() - clock, 4)
    # What the joints' harvest found inconsistent: said, and the document written all the same.
    if tree.mechanism is not None and tree.mechanism.warnings:
        report["kinematics"] = {"warnings": list(tree.mechanism.warnings)}
    clock = time.perf_counter()
    named = 0
    skeletons: dict[str, dict[str, str]] = {}
    tokens = []
    built: dict[str, _Named] = {}
    for part in tree.parts:
        tshape = part.shape.TShape()
        cached = _PARTS.get(tshape)
        if cached is None:
            names, features, refs = _names(run, part)
            written_shape = document.direct(part.shape)
            cached = _PARTS[tshape] = _Named(names, document.geometry_key(written_shape), written_shape, refs,
                                              next(_TOKENS), features)
            named += 1
            while len(_PARTS) > _PARTS_HELD:
                _PARTS.popitem(last=False)
        else:
            _PARTS.move_to_end(tshape)
            if not _current(cached.refs, skeletons):
                # The same shape, but the code its names come from now names it otherwise
                # (a variable or a function renamed, an assignment added): named again.
                names, features, refs = _names(run, part)
                if names != cached.names:
                    cached.names, cached.token = names, next(_TOKENS)
                cached.refs, cached.features = refs, features
                named += 1
        part.names, part.key, part.shape = cached.names, cached.key, cached.shape
        tokens.append(cached.token)
        built[cached.key] = cached
    document.merge(tree)
    signature = (_signature(tree), tuple(tokens), tree.closure)
    timings["names"] = round(time.perf_counter() - clock, 4)
    report["parts"] = len(tree.parts)
    report["named"] = named
    for kind, path in targets:
        if kind == "xbf":
            _BUILT[file_id(path)] = built
    _BUILT[model.id] = built
    _write(model, plan, tree, signature, report, log)
    timings["total"] = round(sum(value for name, value in timings.items() if name != "total"), 4)


def _write(model: Any, plan: list, tree: Any, signature: tuple, report: dict[str, Any],
           log: Callable[[str], None]) -> None:
    """The model's files: the xbf first -- saved, and the viewer woken with it, before any
    derived file is written -- then each derived file, translated from the document
    (``export.translate``). A file whose document and stat are what this process left is
    kept, not rewritten; the xbf is not rewritten when its bytes are the file's."""
    from cadgen.engine import document

    timings = report["timings"]
    key = f"{model.script}::{model.name}"
    remembered = _WRITTEN.get(key)
    stats = {str(target.path): _stat(target.path) for target in plan}
    files = dict((remembered.files or {}) if remembered is not None else {})
    same = remembered is not None and remembered.signature == signature

    def current(target: Any) -> bool:
        stat = stats[str(target.path)]
        if not same or stat is None:
            return False
        if target.kind == "xbf":
            return remembered.stats.get(str(target.path)) == stat
        return files.get(str(target.path)) == (signature, target.kind, stat)

    stale = [target for target in plan if not current(target)]
    written: dict[str, Any] = {}
    for target in plan:
        if target not in stale:
            written[str(target.path)] = {"kind": target.kind, "written": False, "seconds": 0.0,
                                         "bytes": stats[str(target.path)][1]}
    kept = remembered.kept if remembered is not None and remembered.kept is not None else None
    # The document is made again when it changed, when its xbf is written, or when none is
    # held: a build always leaves its document in memory, for the exports asked of it later.
    if not same or kept is None or kept.doc is None or any(target.kind == "xbf" for target in stale):
        clock = time.perf_counter()
        kept = kept if kept is not None else document.Kept()
        _say("stage", "document")
        doc = document.to_xcaf(tree, kept)
        timings["document"] = round(time.perf_counter() - clock, 4)
        report["converted"] = {"prototypes": len(tree.order), "converted": kept.converted, "patched": kept.patched}
    else:
        doc = kept.doc
    if stale:
        xbf = next((target.path for target in plan if target.kind == "xbf"), None)
        source = None
        for target in stale:
            clock = time.perf_counter()
            _say("writing", target.path)
            if target.kind == "xbf":
                # A file this process did not write as it stands -- in a fresh process, one it
                # took, one another worker wrote (a child's, which its parent's build writes
                # too) -- is compared with what it made: the same bytes are not written again.
                # A save tells the viewer before the build goes on (``worker``).
                theirs = remembered is None or remembered.kept is None or \
                    remembered.stats.get(str(target.path)) != stats[str(target.path)]
                fresh, size = document.save(doc, target.path, compare=theirs)
            else:
                from cadgen.engine import export

                if source is None:
                    source = export.Source.built(doc, tree, xbf)
                size = export.translate(source, target.kind, target.path)
                # A writer that found its bytes in the file left it there (a DXF): kept.
                now = _stat(target.path)
                fresh = now != stats[str(target.path)]
                files[str(target.path)] = (signature, target.kind, now)
            seconds = time.perf_counter() - clock
            timings[target.kind] = round(seconds, 4)
            written[str(target.path)] = {"kind": target.kind, "written": fresh, "seconds": round(seconds, 4),
                                         "bytes": size}
            log(f"{'wrote' if fresh else 'kept'} {_shown(target.path, None)} ({size / 1e6:.1f} MB) in {seconds:.2f}s")
    _WRITTEN[key] = _Written(signature, {str(target.path): _stat(target.path) for target in plan}, kept, tree.closure,
                             files, tree)
    report["files"] = {str(target.path): written[str(target.path)] for target in plan}
    report["id"] = model.id
    report["source"] = {"script": str(model.script), "name": model.name}
    report["store"] = model.store
    report["key"] = model.key


def held(script: Path | None = None, name: str | None = None, *, path: Path | None = None) -> Any:
    """The document this process last built, as an ``export.Source``: model ``name`` of
    ``script`` (any of its models when ``name`` is None and it has one), or the model whose
    xbf is ``path`` while the file is as the build left it. None when it holds none."""
    from cadgen.engine import export

    found = []
    for key, written in _WRITTEN.items():
        model_script, _sep, function = key.rpartition("::")
        xbf = next((Path(target) for target in written.stats if target.endswith(".xbf")), None)
        if path is not None:
            if xbf is None or file_id(xbf) != file_id(path):
                continue
            if _stat(xbf) != written.stats.get(str(xbf)):
                continue
        elif script is not None and (model_script != canonical(script) or (name is not None and function != name)):
            continue
        if written.kept is not None and written.tree is not None or (xbf is not None and _stat(xbf) == written.stats.get(str(xbf))):
            found.append((written, xbf))
    if len(found) != 1:
        return None
    written, xbf = found[0]
    if written.kept is None or written.tree is None:
        return export.Source.read(xbf)
    return export.Source.built(written.kept.doc, written.tree, xbf)


def _statuses(run: Any, name: str) -> dict[str, str]:
    """How each body of a model went in this build, by its identity: ``run``, ``replayed``."""
    from cadgen.engine import previous

    return {_identity(body): run.statuses.get(body, "run") for body in previous.closure(run.keys, name)}


def _verified(run: Any, name: str) -> dict[str, Any]:
    """A verifying build's finding for one model: each body of it the memo would have
    replayed, ``same``, ``differs: why``, or ``follows`` the bodies it called that differ;
    the mismatches (those that differ themselves); every function marked to run always."""
    from cadgen.engine import previous
    from cadgen.engine.kernel import memo

    checked = {_identity(body): run.verified[body] for body in previous.closure(run.keys, name)
               if body in run.verified}
    return {"checked": checked,
            "mismatches": sorted(body for body, found in checked.items() if found.startswith("differs")),
            "always_run": sorted(_identity(body) for body in memo.always())}


def _family(name: str) -> str:
    """A body's function, apart from the arguments a ``@memo`` call's name holds."""
    script, _, function = name.rpartition("::")
    return f"{script}::{function.partition('(')[0]}"


def _identity(name: str) -> str:
    script, _, function = name.rpartition("::")
    return f"{Path(script).name}::{function}"


def _previous(model: Any, context: Any, shown: str, log: Callable[[str], None]) -> tuple[dict, dict | None]:
    """The model's previous document asked before its body runs (``previous``): the
    verdict, and the model's report where the document is what the body would make -- the
    key the model has now is the one the document holds -- so the body is not run and the
    files are left as they are. A warm worker asks its own record of the document it built,
    as a fresh one asks the file: a body the memo could replay is not replayed when the key
    is unchanged and every file the model's last build here wrote -- its own and its child
    models' -- is as that build left it; a file moved or gone, and it is replayed, as ever."""
    from cadgen.engine import document, previous
    from cadgen.engine.kernel import memo

    targets = model.targets()
    xbf = next((Path(path) for kind, path in targets if kind == "xbf"), None)
    if xbf is None:
        return {"used": False, "reason": "the model declares no xbf"}, None
    if not memo.enabled() or os.environ.get("CADGEN_ENGINE_BODIES", "1").strip() == "0":
        return {"used": False, "reason": "retention is off"}, None
    name = f"{model.script}::{model.name}"
    clock = time.perf_counter()
    source = context.source(model)
    always = memo.always()
    impure = sorted(_identity(family) for family in _FAMILIES.get(name, ()) if family in always)
    if impure:
        return {"used": False, "reason": f"it calls {', '.join(impure)}, which a verification found impure"}, None
    stats = {str(path): _stat(path) for _kind, path in targets}
    remembered = _WRITTEN.get(name)
    if memo.replayable(name, source) and not _as_built(name, remembered, stats):
        return {"used": False, "reason": "replayed from memory"}, None
    where = "memory"
    if remembered is not None and remembered.stats == stats:
        # The file this process last wrote or took, as it left it: its record is in memory.
        text = remembered.record
        if text is None:
            return {"used": False, "reason": "its last build wrote no key"}, None
    else:
        where = "file"
        if stats[str(xbf)] is None:
            return {"used": False, "reason": "no file yet"}, None
        missing = [path for kind, path in targets if kind != "xbf" and stats[str(path)] is None]
        if missing:
            return {"used": False, "reason": f"{_shown(Path(missing[0]), xbf.parent)} is missing"}, None
        writer, text = previous.scan(xbf)
        # The format, not the release: a cadgen release that leaves the document alone keeps it.
        if document.written_format(writer) != previous.FORMAT:
            return {"used": False, "reason": f"written by {writer or 'another program'}"}, None
        if text is None:
            return {"used": False, "reason": "the file holds no key"}, None
    found = json.loads(text)
    if found.get("key") is None:
        return {"used": False, "reason": "the file holds no key"}, None
    modules, _unkeyable = context.modules(model)
    now, changes = previous.again(found, model, xbf.parent, modules, context.named(model))
    keyed = time.perf_counter()
    if now != found["key"]:
        changes = changes or ["its closure changed"]
        shown_changes = changes[:3] + ([f"{len(changes) - 3} more"] if len(changes) > 3 else [])
        return {"used": False, "reason": ", ".join(shown_changes), "changed": changes}, None
    timings = {"key": round(keyed - clock, 4)}
    if where == "file":
        # Taken only once it reads whole, written by this engine, holding the record its head showed.
        try:
            doc = document._read(xbf)
            held = previous.read_record(doc)
        except Exception as error:  # noqa: BLE001 - a document that does not read is built again
            return {"used": False, "reason": f"the file does not read: {error}"}, None
        del doc
        if document.written_format(held[0]) != previous.FORMAT or held[1] != text:
            return {"used": False, "reason": "the file does not hold the closure its head shows"}, None
        timings["read"] = round(time.perf_counter() - keyed, 4)
        _WRITTEN[name] = _Written(("loaded", found["key"]), stats, None, text)
    else:
        # What the bodies made stays the memo's, as a replay would keep it: an edit after
        # any number of these builds replays all it leaves alone.
        memo.keep(name)
    log(f"took {_shown(xbf, None)}: its key is the model's ({found['bodies']} bodies), nothing ran")
    report = {"ok": True, "model": f"{shown}::{model.name}",
              "memo": {"hits": 0, "misses": 0, "uncached": 0, "bodies_run": 0, "bodies_skipped": 0,
                       "bodies_loaded": found["bodies"]},
              "retention": {"keys": round(context.key_seconds, 4),
                            "fallbacks": {key: list(reasons) for key, reasons in context.fallbacks.items()
                                          if key == model.identity},
                            "reads": {}},
              "children": {}, "bodies": {model.identity: "loaded"}, "cache": {"used": True, "from": where},
              "timings": timings,
              # Each file's row as a build's has it, its kind too: what reads the report for the
              # document (an export, a snapshot) finds the taken xbf by it and reads that file.
              "files": {str(path): {"kind": kind, "written": False, "seconds": 0.0, "bytes": stats[str(path)][1]}
                        for kind, path in targets}}
    report["closure"] = previous.located(found, xbf.parent)
    return report["cache"], report


def _as_built(name: str, remembered: _Written | None, stats: dict[str, tuple | None]) -> bool:
    """Whether model ``name``'s last build in this process made the document it holds and
    left every file as it stands now: the model's own (``stats``) and each child model's
    its run wrote, which a replay would write again were one moved or gone."""
    if remembered is None or remembered.kept is None or remembered.record is None or remembered.stats != stats:
        return False
    for family in _FAMILIES.get(name, ()):
        child = _WRITTEN.get(family) if family != name else None
        if child is not None and any(_stat(Path(path)) != stat for path, stat in child.stats.items()):
            return False
    return True


def _names(run: Any, part: Any) -> tuple[Any, dict[str, dict[str, Any]], dict[tuple[str, str], str | None]]:
    """A part's element names, from the run's history (None for a part no feature named);
    per feature name they hold, its operation and the function, file and line of its
    call; and the functions those names come from, each with its skeleton now. A part
    read from a file is named by its own product's elements."""
    try:
        lineage, features = run.account(part.shape)
    except Exception:  # noqa: BLE001 - naming never fails a build
        return None, {}, {}
    if lineage is None:
        return None, {}, {}
    trace = run.trace
    provenance = {}
    refs: dict[tuple[str, str], str | None] = {}
    skeletons: dict[str, dict[str, str]] = {}
    for name, index in features.items():
        feature = trace.features[index]
        ref = (trace.path_of(feature.file), feature.function)
        provenance[name] = {"operation": feature.op, "function": feature.function, "file": ref[0],
                            "line": feature.line}
        if ref not in refs:
            refs[ref] = _skeleton(ref, skeletons)
        if feature.assigner is not None:
            # Named by its caller's assignment (a helper returned it): that function too.
            caller = (trace.path_of(feature.assigner[0]), feature.assigner[1])
            if caller not in refs:
                refs[caller] = _skeleton(caller, skeletons)
    return {"faces": lineage.get("faces") or [], "edges": lineage.get("edges") or [],
            "vertices": lineage.get("vertices") or [], "table": lineage.get("table") or {}}, provenance, refs


_KINDS = {"face": "faces", "edge": "edges", "vertex": "vertices"}


def made_by(document: str, key: str, kind: str, ordinal: int) -> dict[str, Any] | None:
    """What made element ``ordinal`` (1-based) of kind ``kind`` (face, edge, vertex) of
    part ``key`` of ``document`` (its id, or the xbf's path), as this process's last build
    of it named it: the element's name, the feature that made it (its last step's), that feature's
    operation and the function, file and line of its call, and, where the name folds
    part of its derivation, the derivation spelled out. None for a document this process
    did not build, or an element its build gave no name."""
    named = _BUILT.get(document_id(document), {}).get(key)
    if named is None or not named.names:
        return None
    texts = named.names.get(_KINDS[kind]) or []
    name = texts[ordinal - 1] if 0 < ordinal <= len(texts) else None
    if name is None:
        return None
    feature = _last_feature(name)
    found = named.features.get(feature) or {}
    answer = {"name": name, "feature": feature, "operation": found.get("operation"),
              "function": found.get("function"), "file": found.get("file"), "line": found.get("line")}
    spelled = _spelled(name, named.names.get("table") or {})
    if spelled != name:
        answer["derivation"] = spelled
    return answer


def _spelled(text: str, table: dict[str, str]) -> str:
    """A name with every folded atom it holds spelled out, from its part's table."""
    from cadgen.engine.kernel.trace import folded_atoms

    for atom in folded_atoms(text):
        if atom in table:
            text = text.replace(atom, _spelled(table[atom], table))
    return text


def _skeleton(ref: tuple[str, str], skeletons: dict[str, dict[str, str]]) -> str | None:
    """The skeleton (``sources.skeleton``) of function ``ref[1]`` of file ``ref[0]`` now,
    each file read once a build (``skeletons``); None for a file or function not there."""
    from cadgen.engine.sources import skeleton

    path, function = ref
    found = skeletons.get(path)
    if found is None:
        try:
            found = skeletons[path] = skeleton(Path(path))
        except OSError:
            found = skeletons[path] = {}
    return found.get(function)


def _current(refs: dict[tuple[str, str], str | None], skeletons: dict[str, dict[str, str]]) -> bool:
    """Whether every function a part's names come from has the skeleton it had then."""
    return all(_skeleton(ref, skeletons) == digest for ref, digest in refs.items())


def _signature(tree: Any) -> tuple:
    return (tree.signature, tuple((part.shape.TShape(), part.name, part.color, part.key) for part in tree.parts))


def _stat(path: Path) -> tuple | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _last_feature(name: str) -> str:
    from cadgen.engine.kernel.trace import _features

    text = name.split(":", 1)[1] if ":" in name[:2] else name
    found = _features(text)
    return found[-1] if found else ""
