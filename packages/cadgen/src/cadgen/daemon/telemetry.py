"""The build daemon's telemetry (``cadgen/analytics.py``): the builds it answers and how they end, its
workers' health, the crashes it meets -- its own, its workers' (``exited``, ``worker_died``) -- and what
commands hand it to count (``counted``). One recorder for the daemon, made as it starts serving
(``start``) and closed, its last batch sent, as it stops (``close``); until then, and in every other
process, each call here does nothing.

A build worker's job is followed here too (``job_started``, ``job_reused``, ``job_finished``): whether
what it made came from the store, and the crashes in cadgen's code it met, which ride its exit frame to
the daemon (``worker.serve``).

A build is counted once, for whoever asked: a model script (``python model.py``) or a ``cadgen``
command. What a build asks for in turn (a child's build, a document's compile) is that build's work,
and what the CAD Viewer asks for (an artifact) is a view's, so neither is a build of its own. A client
whose environment turns telemetry off (``analytics.refused``) has nothing it asks for counted.

A build no daemon answers -- ``CADGEN_DAEMON=0``, a platform without one, or one that declined -- is made
in the process that asked, and counted there the same way (``cold_build``): handed to a running daemon
like a command's counts, or kept for the next process that sends (``analytics.spool``).

Nothing here is waited on by a build or raises into one: every call is guarded, and the recorder
notes in memory and sends from its own thread.
"""

from __future__ import annotations

import functools
import logging
import os
import time
from typing import Any, Callable

LOG = logging.getLogger("cadgen.analytics")

_RECORDER = None  # the daemon's, while it serves
# A command's format, by the daemon tool it runs (``cadgen.cli``); a model script's is what it declares.
_COMMANDS = {"step-build": "step", "step-compile": "step", "stl-build": "stl", "3mf-build": "3mf", "glb-build": "glb"}
_MESHES = (".stl", ".3mf", ".glb")
# What the pool counts from its start (``Pool.snapshot``), by the name a batch gives it. Its own count of
# crashes takes in workers killed because their client left, so crashes are counted here (``Build.finish``).
_POOL = {"workers": "imports", "recycles": "recycles", "refusals": "memoryRefusals"}
_MOST = 16  # the most crashes one job's exit frame carries


def _quiet(method):
    """Never raise into the daemon: a failure is a debug line, and nothing counted."""
    @functools.wraps(method)
    def quiet(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except Exception:  # noqa: BLE001 - telemetry never fails what it counts
            LOG.debug("daemon telemetry %s failed", method.__name__, exc_info=True)
            return None
    return quiet


@_quiet
def start(pool_stats: Callable[[], dict[str, Any]]) -> None:
    """Make the daemon's recorder, sending every few minutes until ``close``; ``pool_stats``: the pool's
    counts since it started, of which each batch takes what is new."""
    global _RECORDER
    from cadgen import analytics
    from cadgen.analytics import Recorder

    seen: dict[str, int] = {}

    def collect(recorder) -> None:
        stats = pool_stats()
        for name, field in _POOL.items():
            value = int(stats.get(field) or 0)
            recorder.health(name, value - seen.get(field, 0))
            seen[field] = value

    _RECORDER = Recorder(process="daemon", collect=collect)
    _RECORDER.start()
    analytics.collect_crashes(_RECORDER.crashed)  # the daemon's own, as ``analytics.report`` finds them


@_quiet
def close() -> None:
    """The last batch, as the daemon stops: waited for a moment at most (``analytics.CLOSE_SECONDS``)."""
    global _RECORDER
    from cadgen import analytics

    recorder, _RECORDER = _RECORDER, None
    analytics.collect_crashes(None)
    if recorder is not None:
        recorder.close()


@_quiet
def worker_died(status: Any) -> None:
    """A worker that died under a job -- not one stopped because whoever asked left -- or could not start
    for one: a crash, its exit status what there is to tell (a native fault, or killed for memory)."""
    from cadgen.analytics import died

    if _RECORDER is not None:
        _RECORDER.health("crashes")
        _RECORDER.crashed(died(status))


@_quiet
def exited(frame: dict[str, Any], build: Build | None) -> None:
    """A worker's exit frame (``job_finished``): the crashes in cadgen's code its job met, and whether
    what it made came from the store."""
    crashes = frame.get("crashes")
    if _RECORDER is not None and isinstance(crashes, list):
        for crash in crashes[:_MOST]:
            _RECORDER.crashed(crash)  # checked there: a worker is another process
    if build is not None and frame.get("reused") is True:
        build.reused = True


# A build worker's job, while one runs in this process (``worker.serve``): what it saw, for its exit frame.
_JOB: dict[str, Any] | None = None


def job_started() -> None:
    global _JOB
    _JOB = {"built": False, "reused": False, "crashes": [], "children": False}


def building() -> bool:
    """Whether a build's job runs in this process now: a worker's, or one made here (``cold_build``)."""
    return _JOB is not None


def job_child() -> None:
    """The job's model called another: an assembly. Called wherever a model composes a child; it counts
    only for a build made in this process (``cold_build``) -- the daemon sees a worker's in its events."""
    if _JOB is not None:
        _JOB["children"] = True


def job_reused(reused: bool) -> None:
    """Something a job makes was the store's already (``True``), or was made now: called wherever cadgen
    decides, in any process; it counts only in a build worker's job."""
    if _JOB is not None:
        _JOB["reused" if reused else "built"] = True


def job_result(result: Any) -> None:
    """A command's result (``cli_from_function.emit``): whether what it made was the store's already --
    a compile it skipped, a build with nothing to rebuild, mesh exports every one of which was current."""
    if _JOB is None:
        return
    skipped, files = getattr(result, "skipped", None), getattr(result, "files", None)
    if isinstance(skipped, bool):  # a build that only refreshed its sidecar kept its geometry's bytes
        job_reused(skipped or getattr(result, "sidecar_only", False) is True)
    elif isinstance(files, (list, tuple)) and files and all(isinstance(getattr(file, "skipped", None), bool) for file in files):
        job_reused(all(file.skipped for file in files))


def job_crashed(crash: dict[str, Any]) -> None:
    """A crash in a build worker's job (``analytics.collect_crashes``), for its exit frame."""
    if _JOB is not None and len(_JOB["crashes"]) < _MOST:
        _JOB["crashes"].append(crash)


def job_finished() -> dict[str, Any]:
    """What the job's exit frame tells the daemon: ``reused`` when everything it made was the store's,
    and its ``crashes``."""
    global _JOB
    job, _JOB = _JOB, None
    if job is None:
        return {}
    return {**({"reused": True} if job["reused"] and not job["built"] else {}),
            **({"crashes": job["crashes"]} if job["crashes"] else {})}


class Build:
    """One build a client asked for, from its request until it ends: what it was, and what its
    worker's tree events said of it (``observe``)."""

    def __init__(self, kind: str, via: str, job: str, meshes: bool) -> None:
        self.kind, self.via, self.job, self.meshes = kind, via, job, meshes
        self.states: set[str] = set()  # the model's own transitions (``cadgen.daemon.executors.model_event``)
        self.children = False  # a child's, announced by this model: an assembly
        self.reused = False  # its worker said everything it made was the store's (``exited``)

    def observe(self, event: Any) -> None:
        """A frame's event, if it is this job's: called for each frame, so cheap."""
        if isinstance(event, dict) and event.get("job") == self.job:
            if event.get("parent"):
                self.children = True
            else:
                self.states.add(str(event.get("state") or ""))

    @_quiet
    def finish(self, exit_code: int, ended: str | None, seconds: float) -> None:
        """Count it: ``ended`` is ``crashed`` or ``cancelled`` when its worker died or was stopped, else
        its exit code says. It was the store's answer when its worker said so (``exited``), or when its
        model's own transitions say it was current and nothing was built."""
        recorder = _RECORDER
        if recorder is None:
            return
        outcome = ended or ("ok" if exit_code == 0 else "failed")
        current = "current" in self.states and not self.states & {"building", "done", "failed"}
        recorder.built(self.kind, self.via, outcome, seconds, cached=self.reused or current)
        if self.children:
            recorder.used("assembly")
        if self.meshes:
            recorder.used("declared_mesh")


@_quiet
def build(request: dict[str, Any], job: dict[str, Any]) -> Build | None:
    """The build a request asks for, to be counted as it ends -- or ``None``: no recorder, a request
    that is not one (a dependency's, an artifact's, a command's ``--help``), or a client whose
    environment turned telemetry off."""
    if _RECORDER is None or request.get("dependency"):
        return None
    tool, argv = request.get("tool"), request.get("argv") or []
    if tool != "run" and tool not in _COMMANDS or "-h" in argv or "--help" in argv:
        return None
    from cadgen.analytics import refused

    env = request.get("env")
    if refused(env if isinstance(env, dict) else {}):
        return None
    outputs = [str(output).lower() for output in job.get("outputs") or ()]
    if tool == "run":
        kind = "dxf" if any(output.endswith(".dxf") for output in outputs) else "step"
        return Build(kind, "script", str(job.get("id") or ""), any(output.endswith(_MESHES) for output in outputs))
    return Build(_COMMANDS[tool], "command", str(job.get("id") or ""), False)


@_quiet
def counted(message: dict[str, Any]) -> None:
    """A command's counts, handed over (``cadgen.daemon.client.hand_over``): builds it made itself,
    snapshots rendered, the features used, and its crashes (``analytics.Recorder.take``)."""
    if _RECORDER is not None:
        _RECORDER.take(message)


def command_kind(tool: str) -> str | None:
    """The format a daemon tool builds (``cadgen.cli``), or ``None`` for a tool that is not a build."""
    return _COMMANDS.get(tool)


def cold_build(kind: str, via: str, run: Callable[[], int], *, meshes: bool = False) -> int:
    """Run ``run``, a build this process makes itself with no daemon to answer it, and count it as the
    daemon counts the builds it answers (``Build.finish``): how it ended, how long it took, whether what it
    made was the store's already, and the features it used. What ``run`` returns or raises is the caller's,
    untouched. Not counted in a daemon worker (the daemon counts its jobs), inside another build made here,
    or where the environment turned telemetry off."""
    if os.environ.get("CADGEN_DAEMON_CHILD") or _JOB is not None or _refused():
        return run()
    job_started()
    started, outcome = time.perf_counter(), "failed"
    try:
        code = run()
        outcome = "ok" if code == 0 else "failed"
        return code
    except KeyboardInterrupt:
        outcome = "cancelled"
        raise
    except SystemExit as stop:
        outcome = "ok" if stop.code in (0, None) else "failed"
        raise
    finally:
        _hand_cold(kind, via, outcome, time.perf_counter() - started, meshes)


def _refused() -> bool:
    try:
        from cadgen.analytics import refused

        return refused()
    except Exception:  # noqa: BLE001 - an environment that cannot be read is no yes
        return True


@_quiet
def _hand_cold(kind: str, via: str, outcome: str, seconds: float, meshes: bool) -> None:
    global _JOB
    job, _JOB = _JOB, None
    if job is None:
        return
    cached = outcome == "ok" and job["reused"] and not job["built"]
    features = [name for name, used in (("assembly", job["children"]), ("declared_mesh", meshes)) if used]
    from cadgen.daemon.client import hand_over

    hand_over({"builds": [{"kind": kind, "via": via, "outcome": outcome, "seconds": round(seconds, 3), "cached": cached}],
               **({"features": features} if features else {})})
