"""Where a job is: one progress event for every job the engine runs, said by the engine alone.

Nothing in a model says it: the engine reports what it runs, by name. A job is a build, an import
(a STEP a page first opens), an export, a snapshot, a measurement (``inspect``'s summary, a volume
per part) or an update (a person's click of the update button), and every one says where it is in
frames of one shape, the **progress event**::

    {"kind": "build", "stage": "body", "job": "hand.py::hand", "outputs": ["/abs/XBF/hand.xbf"],
     "detail": "middle", "done": 2, "total": null, "elapsedMs": 4120}

``kind`` is one of ``KINDS`` and ``stage`` one of that kind's ``STAGES``, a closed vocabulary (an
unknown one is refused by name, naming the set); ``job`` names what the job is of as the engine
names it (a build's model as its report does, ``script::function``, the script alone while it
loads; an import's, an export's or a snapshot's source file by its name, a held document by its
id; a measurement's document by its name); ``outputs`` are the absolute paths of the files the job
writes (a build's declared files, an export's destinations, a snapshot's picture; an import and a
measurement write none); ``detail`` is a name the engine gives of what is in flight within the
stage -- a body's function, the file being written, an import's file and its size -- never a
sentence and never a model's own words; ``done`` of ``total`` counts the stage's units where it
has any (``total`` null where they cannot be counted: a build's bodies, whose ``done`` still
counts), and ``elapsedMs`` counts from the job's start. A stage opens with a frame of its own; the
frames a stage says as its count moves (a body done, a part collected or measured) come at least
``INTERVAL`` apart, the latest held one sent when the interval is up (or with the next frame), so
a thousand small steps send a frame an interval and a job's last state is always its last frame.
The end of a job is no stage: it is the job's answer on the same channel (a build's report, the
page's ``building`` null, the verb's ``wrote`` line, an operation's ``succeeded``).

The words of each stage are here too (``STAGES``, ``words``), in English, for whatever reads a frame
on a terminal or in a report; a page says each in its own language by the key
``progress.<kind>.<stage>``.

A build's stages are the engine's own steps, said where the build reaches them (``build.py``,
through ``current``): the files each model writes, planned, give its frames their ``outputs``; a
model's body opens ``body``, inside which each ``@memo`` call and each child model the body calls is
a body of its own, said where it begins and where it ends by its function's name
(``Progress.entering``, ``leaving``: the detail is the innermost body's name while it runs, and the
count of bodies done moves when one ends; a body the memo replays still begins and ends, a
placement of one this build already made says nothing, and a body that raises says no end); its
result collected and its elements named ``names``; its XCAF document made ``document``; and each
file written ``write``, the file's name its detail, counted of the model's files. An import says
``read`` while its reader parses the file and ``collect`` as each part's shape is collected,
counted. An export says ``read`` while it reads a file source and ``write`` for each destination,
counted, the file's name its detail. A snapshot says ``scene`` while the document is served, meshed
and its scene made, ``draw`` while the frame is drawn, and ``write`` as the picture is written. A
measurement says ``measure``, counted as the engine has each part's facts: the ones it holds at
once, the rest as the pool answers their batches (``serve.Server.measure``). An update says
``install`` while the release's folder is made, ``build123d`` while its base is, ``apps`` while the agent
apps' plugins are updated and ``restart`` as the engine drains for the switch, counted of the four
(``cad_server._internal.update``); its frames are read by the page that asked, from the update's state.

Whoever runs the job takes the frames (``building``): a worker sends them over its pipe and its
daemon passes them on (``daemon``), the daemon sends a snapshot's as it draws, a server sends an
import's to the document's pages (``serve.Server.importing``); a terminal draws them as a bar
(``Bar``, one line per change); the build's ``--json`` report holds each model's last
(``Progress.attach``). Nothing is written to disk, and no frame is ever a guess: a stage is said
where the job reaches it, never on a timer.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, TextIO

__all__ = ["INTERVAL", "KINDS", "STAGES", "Bar", "Progress", "building", "current", "describe", "event", "say",
           "sink", "words"]

# Each kind of job the engine runs, and each stage of it, in the order a job passes them, with its words.
STAGES: dict[str, dict[str, str]] = {
    "build": {"load": "Loading the script", "body": "Building geometry", "names": "Naming elements",
              "document": "Making the document", "write": "Writing files"},
    "import": {"read": "Importing model", "collect": "Collecting parts"},
    "export": {"read": "Reading the document", "write": "Writing files"},
    "snapshot": {"scene": "Making the scene", "draw": "Drawing the picture", "write": "Writing the picture"},
    "inspect-measure": {"measure": "Measuring parts"},
    "update": {"install": "Installing the update", "build123d": "Installing build123d",
               "apps": "Updating the apps", "restart": "Restarting"},
}
KINDS = tuple(STAGES)
# The least time between two frames of one stage's count, in seconds; a stage's own frame is never held.
INTERVAL = 0.1


def event(kind: str, stage: str, *, job: str = "", outputs: Iterable[str] = (), detail: str = "", done: int = 0,
          total: int | None = None, elapsed_ms: int = 0) -> dict[str, Any]:
    """One progress event (the module), its ``kind`` and ``stage`` checked against the vocabulary:
    an unknown one is refused naming the set."""
    stages = STAGES.get(kind)
    if stages is None:
        raise ValueError(f"no progress kind {kind!r}: one of {', '.join(KINDS)}")
    if stage not in stages:
        raise ValueError(f"no stage {stage!r} of a {kind}: one of {', '.join(stages)}")
    return {"kind": kind, "stage": stage, "job": str(job or ""), "outputs": [str(path) for path in outputs],
            "detail": str(detail or ""), "done": int(done), "total": None if total is None else int(total),
            "elapsedMs": int(elapsed_ms)}


def words(frame: dict[str, Any] | None) -> str:
    """A frame's stage in words (``STAGES``): ``Building geometry``; the stage's name for one outside
    the vocabulary, and nothing for no frame."""
    if not frame:
        return ""
    stage = str(frame.get("stage") or "")
    return STAGES.get(str(frame.get("kind") or ""), {}).get(stage, stage)


class Progress:
    """One job's progress (see the module): its state, and each frame of it sent to ``send``.

    ``kind`` is the job's; ``job`` and ``outputs`` name it and its files until a stage names others.
    ``script`` and ``cwd`` are a build's, which name its models as their reports do (``name``)."""

    def __init__(self, send: Callable[[dict[str, Any]], None], *, kind: str = "build", job: str = "",
                 outputs: Iterable[str] = (), script: Path | str | None = None, cwd: Path | str | None = None) -> None:
        if kind not in STAGES:
            raise ValueError(f"no progress kind {kind!r}: one of {', '.join(KINDS)}")
        self.send = send
        self.kind = kind
        self.script = Path(script) if script is not None else None
        self.cwd = Path(cwd) if cwd is not None else None
        self.started = time.monotonic()
        self.lock = threading.Lock()
        self.job = str(job or "")
        self.outputs: list[str] = [str(path) for path in outputs]
        self.stage_name = next(iter(STAGES[kind]))
        self.detail = ""
        self.count: list[Any] | None = None  # the stage's own [done, total]: files written, bodies done
        self.bodies: list[str] = []  # the bodies running inside a model's, the innermost last
        # Per model, by its script and function: its name in a frame and the files its build writes.
        self.planned: dict[tuple[str, str], tuple[str, list[str]]] = {}
        self.sent = float("-inf")
        self.held = False
        self.timer: threading.Timer | None = None
        self.closed = False
        self.last: dict[str, Any] | None = None
        self.frames: dict[str, dict[str, Any]] = {}  # each job's (a build's each model's) last frame

    # --- the frames --------------------------------------------------------------------------

    def frame(self) -> dict[str, Any]:
        """Where the job is now."""
        count = self.count
        done, total = (count[0], count[1]) if count is not None else (0, None)
        return event(self.kind, self.stage_name, job=self.job, outputs=self.outputs, detail=self.detail, done=done,
                     total=total, elapsed_ms=round((time.monotonic() - self.started) * 1000))

    def _emit(self, force: bool = False) -> None:
        """Send where the job is; a count's frames (not ``force``) ``INTERVAL`` apart, a held one
        sent when the interval is up. Call with ``lock`` held."""
        if self.closed:
            return
        now = time.monotonic()
        if not force and now - self.sent < INTERVAL:
            self.held = True
            if self.timer is None:
                self.timer = threading.Timer(INTERVAL - (now - self.sent), self._flush)
                self.timer.daemon = True
                self.timer.start()
            return
        self._send(now)

    def _send(self, now: float) -> None:
        self.held = False
        self.sent = now
        found = self.frame()
        self.last = found
        if found["job"]:
            self.frames[found["job"]] = found
        try:
            self.send(found)
        except Exception:  # noqa: BLE001 - saying where a job is never fails it
            pass

    def _flush(self) -> None:
        from cad.engine.profiling import quiet

        with quiet(), self.lock:  # the timer's thread: never while a build is profiled
            self.timer = None
            if self.held and not self.closed:
                self._send(time.monotonic())

    def close(self) -> None:
        """The job is over: a held frame is sent now, and no other after it."""
        with self.lock:
            if self.timer is not None:
                self.timer.cancel()
                self.timer = None
            if self.held and not self.closed:
                self._send(time.monotonic())
            self.closed = True

    def attach(self, reports: Iterable[dict[str, Any]]) -> None:
        """Each report's ``progress``: its model's last frame, else the build's (a script that
        failed to load: where it was)."""
        for report in reports:
            if isinstance(report, dict):
                report["progress"] = self.frames.get(str(report.get("model")), self.last)

    # --- the stages ----------------------------------------------------------------------------

    def name(self, script: Path | str | None, function: str | None = None) -> str:
        """A model as its report names it: its script relative to the build's folder, and its
        function."""
        if script is None:
            shown = ""
        else:
            try:
                shown = os.path.relpath(script, self.cwd or Path.cwd())
            except ValueError:  # another drive
                shown = str(script)
        return f"{shown}::{function}" if function else shown

    def stage(self, stage: str, *, job: str | None = None, outputs: Iterable[str] | None = None, detail: str = "",
              count: list[Any] | None = None) -> None:
        """A stage begins: its own frame, sent at once. ``job`` and ``outputs`` name the job from here
        on where given; ``count`` is the stage's ``[done, total]`` as it opens."""
        if stage not in STAGES[self.kind]:
            raise ValueError(f"no stage {stage!r} of a {self.kind}: one of {', '.join(STAGES[self.kind])}")
        with self.lock:
            self.stage_name = stage
            if job is not None:
                self.job = str(job)
            if outputs is not None:
                self.outputs = [str(path) for path in outputs]
            self.detail = detail
            self.count = count
            self.bodies = []
            self._emit(force=True)

    def counted(self, done: int, total: int | None = None, detail: str | None = None) -> None:
        """The stage's count moved (a part collected, a part measured): a frame, held to the
        interval; ``detail`` replaces the stage's where given."""
        with self.lock:
            self.count = [int(done), None if total is None else int(total)]
            if detail is not None:
                self.detail = detail
            self._emit()

    # --- a build's stages --------------------------------------------------------------------

    def load(self) -> None:
        """The build has begun: its script loads."""
        self.stage("load", job=self.name(self.script), outputs=[])

    def plan(self, model: Any, paths: list[str]) -> None:
        with self.lock:
            self.planned[(str(model.script), model.name)] = (self.name(model.script, model.name), paths)

    def _model(self, script: str | None, function: str) -> tuple[str, list[str]] | None:
        found = self.planned.get((script, function)) if script is not None else None
        if found is None:  # by its function alone: the last planned of that name
            found = next((value for (_script, name), value in reversed(self.planned.items()) if name == function),
                         None)
        return found

    def body(self, model: Any) -> None:
        found = self._model(str(model.script), model.name)
        name, outputs = found if found is not None else (self.name(model.script, model.name), [])
        self.stage("body", job=name, outputs=outputs)

    def named(self, function: str) -> None:
        found = self._model(None, function)
        if found is None:
            self.stage("names")
        else:
            self.stage("names", job=found[0], outputs=found[1])

    def writing(self, path: Any) -> None:
        """A file is written: of the model whose files it is, the one being written now."""
        text = str(Path(os.fspath(path)))
        owner = next(((name, paths) for name, paths in reversed(list(self.planned.values())) if text in paths), None)
        if owner is None:
            self.stage("write", detail=Path(text).name)
        else:
            name, paths = owner
            self.stage("write", job=name, outputs=paths, detail=Path(text).name,
                       count=[paths.index(text), len(paths)])

    # --- the bodies inside a model's ---------------------------------------------------------

    def entering(self, name: str) -> None:
        """A body inside the model's begins (a ``@memo`` call, a child model): its name is the
        detail while it runs."""
        with self.lock:
            self.bodies.append(name)
            self.detail = name
            self._emit()

    def leaving(self, name: str) -> None:
        """That body is done: it counts, and the detail is the body around it again."""
        with self.lock:
            if self.bodies and self.bodies[-1] == name:
                self.bodies.pop()
            done = self.count[0] if self.stage_name == "body" and self.count is not None else 0
            self.count = [done + 1, None]
            self.detail = self.bodies[-1] if self.bodies else ""
            self._emit()


# --- the job of this process -----------------------------------------------------------------------

_JOBS: list[Progress] = []  # the jobs running in this process, the newest last
_LOCK = threading.Lock()


def current() -> Progress | None:
    """This process's job (``building``), whose frames the engine's stages are; None outside one."""
    return _JOBS[-1] if _JOBS else None


@contextlib.contextmanager
def building(progress: Progress) -> Iterator[Progress]:
    """Inside it, ``progress`` is this process's job: the engine's stages and the bodies it runs
    are its frames. It is closed after (``Progress.close``)."""
    with _LOCK:
        _JOBS.append(progress)
    try:
        yield progress
    finally:
        with _LOCK:
            _JOBS.remove(progress)
        progress.close()


def say(stage: str, **where: Any) -> None:
    """A stage of this process's job (``current``), where the engine reaches it: ``Progress.stage``'s
    arguments. Nothing outside a job, and never a failure: saying where a job is never fails it."""
    said = current()
    if said is None:
        return
    try:
        said.stage(stage, **where)
    except Exception:  # noqa: BLE001
        pass


def sink(progress: Any) -> tuple[Callable[[dict[str, Any]], None] | None, "Bar | None"]:
    """Where a verb's frames go, from its ``progress`` argument: None (the default) draws a bar on
    stderr when it is a terminal and nothing when it is not; ``False`` nothing; a callable takes
    each frame. The frame taker (None for nothing) and the bar to close after, if one."""
    if progress is None:
        bar = Bar()
        return bar.frame, bar
    return (progress or None), None


# --- in words, and on a terminal ---------------------------------------------------------------


def describe(frame: dict[str, Any]) -> str:
    """A frame in words: its stage, its count and what is in flight (``Building geometry · 2/5
    middle``)."""
    count = f"{frame.get('done')}/{frame.get('total')}" if frame.get("total") else ""
    tail = " ".join(text for text in (count, str(frame.get("detail") or "")) if text)
    head = words(frame)
    return f"{head} · {tail}" if tail else head


def elapsed(seconds: float) -> str:
    """A duration read at a glance: ``259ms``, ``1.1s``, ``10m03s``, ``2h10m``."""
    seconds = max(0.0, float(seconds))
    if seconds < 1.0:
        return f"{int(round(seconds * 1000))}ms"
    if seconds < 60.0:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes}m{remainder:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def _drawn(ratio: float, width: int = 18) -> str:
    filled = int(round(min(1.0, max(0.0, ratio)) * width))
    return f"▕{'█' * filled}{'░' * (width - filled)}▏"


class Bar:
    """A job's frames drawn on a terminal, whatever the job: a line per job (a build's per model),
    under it a line per stage it finished with how long that took, and the stage in flight on a
    live line repainted in place -- its count as a bar when it has one, and what is in flight. On a
    stream that is no terminal it draws nothing at all. Lines printed through ``around`` go above
    the live line."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream if stream is not None else sys.stderr
        try:
            self.enabled = bool(self.stream.isatty())
        except (AttributeError, ValueError, OSError):
            self.enabled = False
        self.lock = threading.RLock()
        self.width = 0
        self.job: str | None = None
        self.stage: str | None = None
        self.label = ""
        self.began = 0.0
        self.live = ""

    def _write(self, text: str) -> None:
        try:
            self.stream.write(text)
            self.stream.flush()
        except (OSError, ValueError):
            self.enabled = False

    def _clear(self) -> None:
        if self.width:
            self._write(f"\r{' ' * self.width}\r")
            self.width = 0

    def _commit(self, text: str) -> None:
        padding = max(0, self.width - len(text))
        self._write(f"\r{text}{' ' * padding}\n")
        self.width = 0

    def _repaint(self) -> None:
        if self.live:
            padding = max(0, self.width - len(self.live))
            self._write(f"\r{self.live}{' ' * padding}")
            self.width = len(self.live)

    def _finished(self) -> None:
        if self.stage is not None:
            self._commit(f"  ✓ {self.label.lower():<26}{elapsed(time.monotonic() - self.began):>9}")

    def frame(self, frame: dict[str, Any]) -> None:
        """One frame: a stage that ended leaves its line, the live line shows this one."""
        if not self.enabled:
            return
        with self.lock:
            job = str(frame.get("job") or "")
            stage = f"{frame.get('kind')}.{frame.get('stage')}"
            if job != self.job or stage != self.stage:
                self._finished()
                if job != self.job and job and frame.get("stage") != "load":
                    self._commit(job)  # a job's stages begin under its name; a script loading has none
                self.job, self.stage = job, stage
                self.label = words(frame) or str(frame.get("stage") or "")
                self.began = time.monotonic()
            text = self.label.lower()
            if frame.get("total"):
                text += f"  {_drawn(frame['done'] / frame['total'])}  {frame['done']}/{frame['total']}"
            if frame.get("detail"):
                text += f"  {frame['detail']}"
            self.live = f"    {text}"
            self._repaint()

    def around(self, write: Callable[[str], None]) -> Callable[[str], None]:
        """``write`` with the live line cleared before it and drawn again after."""
        if not self.enabled:
            return write

        def written(text: str) -> None:
            with self.lock:
                self._clear()
                write(text)
                self._repaint()

        return written

    def close(self) -> None:
        """The job is over: its last stage leaves its line, the live line goes."""
        if not self.enabled:
            return
        with self.lock:
            self._finished()
            self._clear()
            self.stage = self.job = None
            self.live = ""
