"""Jobs beside a build: a document's compile on the pool, and the events a build emits.

A model's children are no jobs: a child a parent's body calls is decoded or built
serially in the parent's own process (``cadgen.authoring``, STORE.md §9a). What a
build still hands to the pool is a document compile (:func:`submit_compile`), and
what it waits on is a :class:`Job`: the compile's exit, or, for the top-level call
of a model, the source result its own pipeline announces (:func:`capture_source_result`).
Which executor runs a compile is decided once per process:

* **daemon** (default) -- the job is a request to the warm daemon, streamed on a
  background thread. Inside a daemon worker this is the same client call back to the
  daemon the worker belongs to.
* **transient** (``CADGEN_DAEMON=0``) -- a subprocess alive for this job only. It
  inherits the environment, so a test's ``CADGEN_CACHE_DIR`` isolates its store with
  no protocol support; tests and CI run this way.

The store root travels with every job as an explicit request field rather than as
ambient environment, so one daemon serves any number of isolated stores.

Events (``{"event": {...}}`` frames) describe a build's models for the build tree
(``cadgen.cli_tree``): a build emits them for the model it runs and for each child it
builds inside it, and they go to the current events sink, which in a worker re-emits
them on its own frame channel and in the root client renders them.
"""

from __future__ import annotations

import contextlib
import itertools
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable


class Job:
    """One job's eventual exit, and the source result a model's build announces."""

    def __init__(self, model: Path | str) -> None:
        from cadgen.store.index import split_model_ref

        # The model's identity (``script::fn``); the script it lives in; the function.
        from cadgen.store.index import resolve_model_ref

        self.model = resolve_model_ref(model)
        self.script, self.function = split_model_ref(self.model)
        self._done = threading.Event()
        self._result_ready = threading.Event()
        self._tree: str | None = None
        self._code: int | None = None
        self._chunks: list[str] = []
        self._lock = threading.Lock()

    def _say(self, text: str) -> None:
        if text:
            with self._lock:
                self._chunks.append(text)

    def _finish(self, code: int) -> None:
        self._code = int(code)
        self._done.set()
        # A failed/superseded worker may never have produced geometry.
        self._result_ready.set()

    def _observe(self, event: dict) -> None:
        result = event.get("sourceResult")
        if not isinstance(result, dict) or result.get("model") != self.model:
            return
        tree = result.get("tree")
        if not isinstance(tree, str) or not tree:
            return
        with self._lock:
            if self._tree is None and not self.done:
                self._tree = tree
                self._result_ready.set()

    @property
    def result_ready(self) -> bool:
        return self._result_ready.is_set()

    def wait_result(self, timeout: float | None = None) -> str:
        """Return THIS job's final authored tree, without waiting for file exports."""
        if not self._result_ready.wait(timeout):
            raise TimeoutError(f"build of {self.script.name} produced no source result in {timeout}s")
        with self._lock:
            tree = self._tree
        if tree is None:
            raise RuntimeError(f"build of {self.script.name} finished without a source result:\n{self.output().rstrip()}")
        return tree

    def wait(self, timeout: float | None = None) -> int:
        if not self._done.wait(timeout):
            raise TimeoutError(f"build of {self.script.name} did not finish in {timeout}s")
        return int(self._code or 0)

    @property
    def done(self) -> bool:
        return self._done.is_set()

    def output(self) -> str:
        with self._lock:
            return "".join(self._chunks)


# --- events -------------------------------------------------------------------------

_EVENT_SINK: Callable[[dict], None] | None = None
_RELEASE_SINK: Callable[[int], None] | None = None
_EVENT_LOCK = threading.Lock()
_EVENT_SEQUENCE = itertools.count(1)
_RESULT_CAPTURE = threading.local()


@contextlib.contextmanager
def capture_source_result(model: Path | str):
    """Internal exact-call capture, independent of the optional reporting sink."""
    job = Job(model)
    previous = getattr(_RESULT_CAPTURE, "jobs", ())
    _RESULT_CAPTURE.jobs = (*previous, job)
    try:
        yield job
    finally:
        _RESULT_CAPTURE.jobs = previous


def emit_source_result(model: Path | str, tree: str) -> None:
    from cadgen.store.index import resolve_model_ref
    from cadgen.store.trees import tree_complete

    if not tree or not tree_complete(tree):
        raise RuntimeError("source result geometry disappeared before publication")
    emit_event(model_event(model, "building", phase="Source ready",
                           sourceResult={"model": resolve_model_ref(model), "tree": tree}))


def set_event_sink(sink: Callable[[dict], None] | None) -> None:
    """Where child-build events go in this process (the tree renderer, or a
    re-emitter inside a worker)."""
    global _EVENT_SINK
    with _EVENT_LOCK:
        _EVENT_SINK = sink


def sink_installed() -> bool:
    with _EVENT_LOCK:
        return _EVENT_SINK is not None


def set_release_sink(sink: Callable[[int], None] | None) -> None:
    """Where a command's release of its caller goes in this process: a daemon worker's
    frame to its client (``worker.serve``); nowhere in a process of the caller's own."""
    global _RELEASE_SINK
    with _EVENT_LOCK:
        _RELEASE_SINK = sink


def release_caller(code: int) -> None:
    """The command's answer is complete, with exit ``code`` so far: whoever asked may
    return (``--no-wait``), the files the run still owes finishing after. In a daemon
    worker the client gets the ``released`` frame and returns, the worker finishes the
    exports before its next job; in a process of the caller's own the answer is on its
    stdout already, so this is nothing."""
    with _EVENT_LOCK:
        sink = _RELEASE_SINK
    if sink is not None:
        sink(int(code))


def emit_event(event: dict) -> None:
    """Hand one model transition to the sink, tagged with the job it belongs to
    (``CADGEN_JOB_ID``, a daemon worker's) and its place in that job's sequence."""
    for capture in getattr(_RESULT_CAPTURE, "jobs", ()):
        capture._observe(event)
    with _EVENT_LOCK:
        sink = _EVENT_SINK
    if sink is None:
        return
    if "job" not in event:
        producer = os.environ.get("CADGEN_JOB_ID")
        if producer:
            event = {**event, "job": producer, "sequence": next(_EVENT_SEQUENCE)}
    try:
        sink(event)
    except Exception:  # noqa: BLE001 - reporting never fails a build
        pass


def model_event(model: Path | str, state: str, **extra: Any) -> dict:
    """One build-tree transition. ``model`` (and a ``parent`` in ``extra``) are
    named the way a person reads them: the script path, plus ``::fn`` only when
    the file holds several models (cadgen.store.index.display_model)."""
    from cadgen.store.index import display_model

    payload: dict[str, Any] = {"model": display_model(model), "state": state}
    if extra.get("parent"):
        extra["parent"] = display_model(extra["parent"])
    payload.update({k: v for k, v in extra.items() if v is not None})
    return payload


# --- executor selection ---------------------------------------------------------------


def use_daemon() -> bool:
    """The daemon executor unless the caller opted out or the platform cannot."""
    if os.environ.get("CADGEN_DAEMON") == "0":
        return False
    try:
        from cadgen.daemon.client import daemon_supported
    except ImportError:
        return False
    return daemon_supported()


# --- transient executor -----------------------------------------------------------------


def worker_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """The environment a worker process starts with: this cadgen, findable from any cwd.

    A worker runs ``python -m cadgen...`` from the MODEL's directory, so a relative
    ``PYTHONPATH`` entry (``packages/cadgen/src`` from a checkout root, the shape every
    test runner uses) would resolve against that directory and the worker would import
    whatever cadgen the interpreter has installed instead -- a different version, a
    different store layout, silently. Absolutize every entry and put this cadgen's
    source root first.
    """
    env = dict(os.environ if base is None else base)
    import cadgen

    own = str(Path(cadgen.__file__).resolve().parents[1])
    entries = [own]
    for entry in env.get("PYTHONPATH", "").split(os.pathsep):
        if entry and os.path.abspath(entry) not in entries:
            entries.append(os.path.abspath(entry))
    env["PYTHONPATH"] = os.pathsep.join(entries)
    return env


def submit_compile(
    document: Path,
    *,
    store_root: Path | None = None,
    force: bool = False,
    parent: Path | str | None = None,
) -> Job:
    """Compile a document whose bytes have no tree, as a job.

    The one door operation that is a job (STORE.md §9): doors read the store and
    never run a body, but a document with no tree — a vendor STEP, or one built
    into another store — has to be read by the kernel once. That read goes through
    the pool like a build — a slot, the tree, and coalescing with anyone compiling
    the same bytes (the CAD Viewer, another door) — on a daemon spare or a
    transient subprocess, never in the caller."""
    import hashlib

    from cadgen._internal.atomic_replace import read_bytes_with_ladder
    from cadgen.store.paths import store_root as default_store_root

    document = Path(document).resolve()
    root = Path(store_root) if store_root is not None else default_store_root()
    # Through the ladder: on Windows, a program saving, replacing or scanning the document
    # refuses the read for a moment, and that is not a failure of its bytes.
    closure = hashlib.sha256(read_bytes_with_ladder(document)).hexdigest()
    job = Job(document)
    emit_event(model_event(document, "submitted", parent=str(parent) if parent else None))
    tool_argv = [str(document)] + (["--force"] if force else [])
    if use_daemon():
        _submit_daemon(
            job, root, closure=closure, tool="step-compile", argv=tool_argv, prog="cadgen step compile",
        )
    else:
        _submit_transient(job, root, command=[sys.executable, "-P", "-m", "cadgen.cli.step_compile", *tool_argv])
    emit_event(model_event(document, "building", phase="compile"))

    def finish() -> None:
        # The compile narrates on stderr, not in tree events; the tree still needs its line closed.
        if job.wait() == 0:
            emit_event(model_event(document, "done"))

    threading.Thread(target=finish, name=f"cadgen-compile-{document.stem}", daemon=True).start()
    return job


def _submit_transient(job: Job, store_root: Path, *, command: list[str]) -> None:
    """Run ``command`` as a subprocess of this one, in the job's own store, and finish
    ``job`` with its exit; its output is kept for the error path."""
    env = worker_env()
    env["CADGEN_DAEMON"] = "0"
    env["CADGEN_CACHE_DIR"] = str(store_root)
    try:
        process = subprocess.Popen(
            command,
            cwd=str(job.script.parent),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
        )
    except OSError as exc:
        job._say(f"could not start a worker for {job.script.name}: {exc}\n")
        job._finish(1)
        return

    def pump(stream) -> None:
        for line in stream:
            job._say(line)

    def finish() -> None:
        readers = [threading.Thread(target=pump, args=(stream,), daemon=True) for stream in (process.stdout, process.stderr)]
        for reader in readers:
            reader.start()
        code = process.wait()
        for reader in readers:
            reader.join(timeout=5.0)
        if not any(reader.is_alive() for reader in readers):
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        if code != 0:
            emit_event(model_event(job.model, "failed", exit=code))
        job._finish(code)

    threading.Thread(target=finish, name=f"cadgen-job-{job.script.stem}", daemon=True).start()


# --- daemon executor ---------------------------------------------------------------------


def _submit_daemon(
    job: Job,
    store_root: Path,
    *,
    closure: str,
    tool: str,
    argv: list[str],
    prog: str,
) -> None:
    """Run the daemon tool ``tool`` with ``argv`` as a job the daemon coalesces by
    ``closure`` (a compile: the document's bytes), and finish ``job`` with its exit;
    a daemon that cannot take it runs the same tool transiently."""
    from cadgen.daemon import client

    fallback = [sys.executable, "-P", "-m", f"cadgen.cli.{tool.replace('-', '_')}", *argv]

    def run() -> None:
        code = client.run_nested(
            tool,
            argv,
            str(job.script.parent),
            prog=prog,
            store_root=str(store_root),
            closure=closure,
            on_stream=job._say,
            on_event=emit_event,
        )
        if code is None:
            # The daemon could not take the job (spawn failure, unsupported
            # platform mid-flight): run it transiently rather than fail the caller.
            _submit_transient(job, store_root, command=fallback)
            return
        if code != 0:
            emit_event(model_event(job.model, "failed", exit=code))
        job._finish(code)

    threading.Thread(target=run, name=f"cadgen-job-{job.script.stem}", daemon=True).start()
