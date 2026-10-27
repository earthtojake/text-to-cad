"""The engine's verbs counted for telemetry (``cadgen/analytics.py``).

The engine counts nothing and imports nothing of cadgen (its law 3). After each build, export and
snapshot it calls the functions in ``cadgen.engine.api.observers`` with a plain dict of what the verb
did (``api._facts``). ``observe`` is cadgen's: appended by cadgen's package ``__init__`` (``install``)
the moment the engine's verbs are imported, never sooner, so a process that does not use the engine
imports none of it. It counts these events (``analytics.EVENTS``):

- a ``build`` of kind ``model``, by who asked (``via``): ``python model.py``, or a Python caller's
  ``Model.build()``, is ``script`` (no command builds one now; ``command`` is still a value
  ``analytics.VIAS`` reads, which releases before 0.8 sent). How it ended (``crashed``: its
  worker died under it; ``cancelled``: interrupted), whether its documents were their xbfs taken whole
  (``cached``: every model's ``cache.used``), how long it took, and why it failed (``build_failure``,
  ``analytics.told_failure``);
- an export: a ``build`` of each destination's kind, asked as a build is, the verb's time shared out;
- a ``snapshot`` of the source's kind (``model`` for a live model; ``xbf`` for an actual file), and why one failed
  (``snapshot_failure``);
- ``feature``: a model calling other models or of several parts (``assembly``), one writing mesh files
  (``declared_mesh``), an export or a snapshot posing joints (``kinematics``);
- ``health``: a warm worker started for the work, one that died under it, one retired over its memory
  cap after it -- each told by the one answer it came with, so counted once;
- ``exception``: a mistake in cadgen's own code a worker answered with, or a file it could not write
  failed for (``analytics.told_signature``, where ``build``); one raised here, when no ``cadgen``
  command runs this process to report it (where ``command``, as the command's own report says it); and a
  worker that died, its exit status (``analytics.died``).

What a verb counted is kept in the spool beside the settings (``analytics.spool``), as a command's counts
are: the CAD app's or the viewer's next send takes it (as a ``cli`` batch of its own, naming no app) or, with
nothing taking it for a window, the sender a command starts (``telemetry_send``). Nothing is counted where
the environment turns telemetry off
(``analytics.refused``, read first), in an engine worker (what a build asks for is that build's), or for a
server's own work (``cadgen viewer``, ``cadgen mcp``: each counts what it serves). Never raises.
"""

from __future__ import annotations

import sys
from typing import Any

# The ``cadgen`` command this process runs (``cadgen.cli``, as it starts one); None for a model script or a
# Python caller.
command: str | None = None
# Commands that serve others and count their own work: a verb one asks for is a view's, not a build.
SERVERS = frozenset({"viewer", "mcp", "server"})
API = "cadgen.engine.api"
# An engine kind as telemetry names it (``analytics.KINDS``): models are distinct from file formats.
KINDS = {"xbf": "xbf", "step": "step", "glb": "glb", "stl": "stl", "threemf": "3mf", "dxf": "dxf", "urdf": "urdf",
         "sdf": "sdf", "srdf": "srdf", "model": "model"}
MESHES = frozenset({"stl", "glb", "threemf"})


def install() -> None:
    """``observe`` among the engine's observers: now, when its verbs are imported already, else as they are
    (``_Attach``). Idempotent."""
    module = sys.modules.get(API)
    if module is not None:
        _attach(module)
    elif not any(isinstance(finder, _Attach) for finder in sys.meta_path):
        sys.meta_path.insert(0, _Attach())


def _attach(module: Any) -> None:
    observers = getattr(module, "observers", None)
    if isinstance(observers, list) and observe not in observers:
        observers.append(observe)


class _Attach:
    """A ``sys.meta_path`` finder for the engine's verbs alone: found where Python finds them, by the path
    finder (asked itself, never the rest of ``sys.meta_path``, so no two finders hand one lookup back and
    forth), and ``observe`` appended to them once their module has run (``_Then``) -- a reload's too. Every
    other import passes it by at one comparison."""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname != API:
            return None
        from importlib.machinery import PathFinder

        spec = PathFinder.find_spec(fullname, path, target)
        if spec is not None and spec.loader is not None and hasattr(spec.loader, "exec_module"):
            spec.loader = _Then(spec.loader)
        return spec


class _Then:
    """A module's own loader, then ``observe`` attached to the module it ran."""

    def __init__(self, loader: Any) -> None:
        self._loader = loader

    def __getattr__(self, name: str) -> Any:
        return getattr(self._loader, name)

    def create_module(self, spec: Any) -> Any:
        return self._loader.create_module(spec)

    def exec_module(self, module: Any) -> None:
        self._loader.exec_module(module)
        _attach(module)


def observe(facts: dict[str, Any]) -> None:
    """Count what one engine verb did (``cadgen.engine.api.observers``): kept in the spool, and the sender
    started when the spool has waited a window. Never raises."""
    try:
        import os

        if os.environ.get("CADGEN_ENGINE_WORKER") == "1":
            return
        from cadgen import analytics

        if analytics.refused():
            return
        via = _via(facts)
        if via is not None and analytics.spool(counts(facts, via)):
            from cadgen._internal import telemetry_send

            telemetry_send.start_if_due()
    except Exception:  # noqa: BLE001 - telemetry never fails the verb it counts
        import logging

        logging.getLogger("cadgen.analytics").debug("could not count an engine verb", exc_info=True)


def _via(facts: dict[str, Any]) -> str | None:
    """Who asked: a model script (``python model.py``, a Python caller), a ``cadgen`` command, or -- ``None`` --
    a server, whose own work this is not."""
    if facts.get("program"):
        return "script"
    if command is not None:
        return None if command in SERVERS else "command"
    spec = getattr(sys.modules.get("__main__"), "__spec__", None)
    return "command" if str(getattr(spec, "name", None) or "").startswith("cadgen.engine") else "script"


def counts(facts: dict[str, Any], via: str) -> dict[str, Any]:
    """What one verb's facts count, as a command's counts are kept (``analytics.Recorder.take``): ``builds``,
    ``snapshots``, ``features``, ``crashes`` and ``health``, each left out when empty."""
    from cadgen import analytics

    verb = facts.get("verb")
    error = facts.get("error") if isinstance(facts.get("error"), dict) else None
    worker = facts.get("worker") if isinstance(facts.get("worker"), dict) else {}
    models = [model for model in facts.get("models") or () if isinstance(model, dict)]
    seconds = facts.get("seconds") if isinstance(facts.get("seconds"), (int, float)) else 0.0
    outcome = _outcome(facts, error, worker)
    failure = ({"reason": analytics.told_failure(error or {})} if outcome == "failed" and verb in ("build", "export")
               else {})
    builds: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    features: list[str] = []
    if verb == "build":
        cached = outcome == "ok" and bool(models) and all(model.get("cached") for model in models)
        builds.append({"kind": "model", "via": via, "outcome": outcome, "seconds": seconds, "cached": cached, **failure})
        if any(model.get("children") or (model.get("parts") or 0) > 1 for model in models):
            features.append("assembly")
        if any(MESHES & set(model.get("files") or ()) for model in models):
            features.append("declared_mesh")
    elif verb == "export":
        written = [KINDS[output.get("kind")] for output in facts.get("outputs") or ()
                   if isinstance(output, dict) and output.get("kind") in KINDS]
        builds += [{"kind": kind, "via": via, "outcome": outcome, "seconds": seconds / len(written), "cached": False,
                    **failure} for kind in written]
    elif verb == "snapshot" and facts.get("source") in KINDS:
        ok = outcome == "ok"
        snapshots.append({"format": KINDS[facts["source"]], "ok": ok, "seconds": seconds,
                          **({} if ok else {"reason": _snapshot_failure(facts, error, outcome)})})
    if verb == "snapshot" and facts.get("pose"):
        features.append("kinematics")
    health = {name: 1 for name, happened in (("workers", worker.get("fresh") is True),
                                             ("crashes", worker.get("died") is not None),
                                             ("recycles", bool(worker.get("retired")))) if happened}
    crashes = [analytics.died(worker["died"])] if worker.get("died") is not None else []
    # What a worker answered, or a report said, is reported here; what was raised here is the command's to report
    # (``cadgen.cli``) where one runs.
    crash = None
    if error is not None and not error.get("here"):
        crash = analytics.told_signature(error, "build")
    elif error is not None and command is None:
        crash = analytics.told_signature(error, "command", handled=False)
    if crash is not None:
        crashes.append(crash)
    found = {"builds": builds, "snapshots": snapshots, "features": features, "crashes": crashes, "health": health}
    return {name: value for name, value in found.items() if value}


def _outcome(facts: dict[str, Any], error: dict[str, Any] | None, worker: dict[str, Any]) -> str:
    if worker.get("died") is not None:
        return "crashed"
    if facts.get("ok") is True:
        return "ok"
    return "cancelled" if (error or {}).get("type") == "KeyboardInterrupt" else "failed"


def _snapshot_failure(facts: dict[str, Any], error: dict[str, Any] | None, outcome: str) -> str:
    """Why a snapshot failed (``analytics.SNAPSHOT_FAILURES``), as ``analytics.snapshot_failure`` decides it of an
    error caught there: the model it draws did not build (``input_error``); a request refused, or a file not
    there (``bad_request``, ``no_file``); cadgen's mistake (``bug``); a time, a memory or a file run out; else the
    picture was not drawn (``render_error``)."""
    from cadgen import analytics

    error = error or {}
    if outcome != "failed":
        return "other"
    if any(isinstance(model, dict) and not model.get("ok") for model in facts.get("models") or ()):
        return "input_error"
    if error.get("refused"):
        return "no_file" if facts.get("found") is False else "bad_request"
    if analytics.told_signature(error, "build") is not None:
        return "bug"
    name = str(error.get("type") or "")
    kind = analytics._builtin(name)
    if kind is not None and issubclass(kind, FileNotFoundError):
        return "no_file"
    if name.rpartition(".")[2] == "TimeoutError":
        return "timeout"
    if kind is not None and issubclass(kind, MemoryError):
        return "memory"
    return "render_error"
