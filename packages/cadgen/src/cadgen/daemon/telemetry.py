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

Nothing here is waited on by a build or raises into one: every call is guarded, and the recorder
notes in memory and sends from its own thread.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

LOG = logging.getLogger("cadgen.analytics")

_RECORDER = None  # the daemon's, while it serves
# A command's format, by the daemon tool it runs (``cadgen.cli``); a model script's is what it declares.
_COMMANDS = {"step-build": "step", "step-compile": "step", "stl-build": "stl", "3mf-build": "3mf", "glb-build": "glb"}
_MESHES = (".stl", ".3mf", ".glb")
# What the pool counts from its start (``Pool.snapshot``), by the name a batch gives it. Its own count of
# crashes takes in workers killed because their client left, so crashes are counted here (``Build.finish``).
_POOL = {"workers": "imports", "recycles": "recycles", "refusals": "memoryRefusals"}
_MOST = 16  # the most snapshots, and features, one hand-over counts


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
    _JOB = {"built": False, "reused": False, "crashes": []}


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
    """A command's counts, handed over (``cadgen.daemon.client.hand_over``): snapshots rendered, the
    features used, and its crashes. Anything else in it, or past ``_MOST`` of any, is not counted."""
    recorder = _RECORDER
    if recorder is None:
        return
    snapshots, features, crashes = message.get("snapshots"), message.get("features"), message.get("crashes")
    for snapshot in snapshots[:_MOST] if isinstance(snapshots, list) else ():
        if isinstance(snapshot, dict) and isinstance(snapshot.get("ok"), bool):
            recorder.rendered(snapshot.get("format"), snapshot["ok"], snapshot.get("seconds"))
    for feature in features[:_MOST] if isinstance(features, list) else ():
        recorder.used(feature)
    for crash in crashes[:_MOST] if isinstance(crashes, list) else ():
        recorder.crashed(crash)  # checked there: a command is another process
