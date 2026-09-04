"""The pool: ``submit(model) -> Job``, one interface, two executors.

Every child build a parent's body causes goes through :func:`submit`. Which
executor runs it is decided once per process:

* **daemon** (default) — the job is a ``run`` request to the warm daemon, exactly
  the request a top-level ``python model.py`` makes, streamed on a background
  thread. Inside a daemon worker this is the same client call back to the daemon
  the worker belongs to, so nesting is free and a child lands on ITS model's
  worker (or an extra, or a spare) while the parent's body keeps going.
* **transient** (``CADGEN_DAEMON=0``) — a subprocess per job, alive for this
  build only, discarded after. Each imports build123d once (~2.5 s, concurrently
  with its siblings). It inherits the environment, so a test's
  ``CADGEN_CACHE_DIR`` isolates its store with no protocol support; tests and CI
  exercise the real parallel path this way.

There is no serial mode. The store root travels with every job as an explicit
request field rather than as ambient environment, so one daemon serves any
number of isolated stores.

Events (``{"event": {...}}`` frames) describe the child build for the build
tree (§Output): they are forwarded to the current events sink, which in a
worker re-emits them on its own frame channel and in the root client renders
them. Ordinary stream frames from a child are captured and attached to its
error if it fails; a successful child's chatter is not the parent's business.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable


class Job:
    """A submitted build: ``wait()`` for its exit code, ``output()`` for what it said."""

    def __init__(self, model: Path) -> None:
        self.model = Path(model)
        self._done = threading.Event()
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

    def wait(self, timeout: float | None = None) -> int:
        if not self._done.wait(timeout):
            raise TimeoutError(f"build of {self.model.name} did not finish in {timeout}s")
        return int(self._code or 0)

    @property
    def done(self) -> bool:
        return self._done.is_set()

    def output(self) -> str:
        with self._lock:
            return "".join(self._chunks)


# --- events -------------------------------------------------------------------------

_EVENT_SINK: Callable[[dict], None] | None = None
_EVENT_LOCK = threading.Lock()


def set_event_sink(sink: Callable[[dict], None] | None) -> None:
    """Where child-build events go in this process (the tree renderer, or a
    re-emitter inside a worker)."""
    global _EVENT_SINK
    with _EVENT_LOCK:
        _EVENT_SINK = sink


def sink_installed() -> bool:
    with _EVENT_LOCK:
        return _EVENT_SINK is not None


def emit_event(event: dict) -> None:
    """Hand one model transition to the sink. Tags it with the root request's id
    (``CADGEN_ROOT_ID``, inherited by every job of one top-level build) so the root's
    renderer can tell its own tree from a stranger's."""
    with _EVENT_LOCK:
        sink = _EVENT_SINK
    if sink is None:
        return
    if "root" not in event:
        root = os.environ.get("CADGEN_ROOT_ID")
        if root:
            event = {**event, "root": root}
    try:
        sink(event)
    except Exception:  # noqa: BLE001 - reporting never fails a build
        pass


def model_event(model: Path | str, state: str, **extra: Any) -> dict:
    payload: dict[str, Any] = {"model": str(model), "state": state}
    payload.update({k: v for k, v in extra.items() if v is not None})
    return payload


def install_line_sink() -> None:
    """A transient worker's sink: every event is one ``CADGEN_EVENT {json}`` line on
    stderr, which the parent's reader turns back into an event (``_event_line``)."""

    def write(event: dict) -> None:
        sys.stderr.write(EVENT_LINE_PREFIX + json.dumps(event, separators=(",", ":")) + "\n")
        sys.stderr.flush()

    set_event_sink(write)


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


def submit(
    model: Path,
    *,
    store_root: Path | None = None,
    force: bool = False,
    root_id: str | None = None,
    parent: Path | str | None = None,
    closure: str | None = None,
) -> Job:
    """Start building ``model`` now and return without waiting.

    ``parent`` is the model whose body made the call; the build tree hangs the child's
    line under it. ``closure`` is the child's current closure hash: a job already in
    flight for the same ``(model, closure)`` is joined instead of duplicated (in-flight
    coalescing, cadgen.daemon.broker)."""
    from cadgen.store.paths import store_root as default_store_root

    model = Path(model).resolve()
    root = Path(store_root) if store_root is not None else default_store_root()
    job = Job(model)
    emit_event(model_event(model, "submitted", parent=str(parent) if parent else None))
    if use_daemon():
        _submit_daemon(job, root, force=force, root_id=root_id, closure=closure)
    else:
        _submit_transient(job, root, force=force, root_id=root_id, closure=closure)
    return job


@contextlib.contextmanager
def root_context():
    """What a TOP-LEVEL transient build owns for its length: the private broker its
    workers take job slots from and register in-flight jobs with. A no-op inside a
    worker (its root, or the daemon, is the broker) and under the daemon executor."""
    from cadgen.daemon import broker

    if use_daemon() or broker.BROKER_ADDRESS_VAR in os.environ or os.environ.get("CADGEN_EVENTS") == "1":
        yield None
        return
    private = broker.PrivateBroker()
    previous = {k: os.environ.get(k) for k in private.env()}
    os.environ.update(private.env())
    try:
        yield private
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        private.close()


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
    root_id: str | None = None,
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

    from cadgen.store.paths import store_root as default_store_root

    document = Path(document).resolve()
    root = Path(store_root) if store_root is not None else default_store_root()
    closure = hashlib.sha256(document.read_bytes()).hexdigest()
    job = Job(document)
    emit_event(model_event(document, "submitted", parent=str(parent) if parent else None))
    tool_argv = [str(document)] + (["--force"] if force else [])
    if use_daemon():
        _submit_daemon(
            job, root, force=force, root_id=root_id, closure=closure,
            tool="step-compile", argv=tool_argv, prog="cadgen step compile",
        )
    else:
        _submit_transient(
            job, root, force=force, root_id=root_id, closure=closure,
            command=[sys.executable, "-m", "cadgen.cli.step_compile", *tool_argv],
        )
    emit_event(model_event(document, "building", phase="compile"))

    def finish() -> None:
        # The compile narrates on stderr, not in tree events; the tree still needs its line closed.
        if job.wait() == 0:
            emit_event(model_event(document, "done"))

    threading.Thread(target=finish, name=f"cadgen-compile-{document.stem}", daemon=True).start()
    return job


def _submit_transient(
    job: Job,
    store_root: Path,
    *,
    force: bool,
    root_id: str | None,
    closure: str | None = None,
    command: list[str] | None = None,
) -> None:
    from cadgen.daemon import broker

    ticket = broker.claim_inflight(str(job.model), closure) if closure else None
    if ticket is not None and ticket[0] == "attached":
        # Identical source already building for this root: ride that job.
        def follow() -> None:
            job._finish(broker.wait_attached(ticket[1]))

        threading.Thread(target=follow, name=f"cadgen-attach-{job.model.stem}", daemon=True).start()
        return
    claim = ticket[1] if ticket is not None else None
    env = worker_env()
    env["CADGEN_DAEMON"] = "0"
    env["CADGEN_CACHE_DIR"] = str(store_root)
    env["CADGEN_EVENTS"] = "1"  # the child writes events as JSON lines on stderr
    if root_id:
        env["CADGEN_ROOT_ID"] = root_id
    argv = list(command) if command else [sys.executable, "-m", "cadgen.cli._run_model", str(job.model)]
    if force and not command:
        argv.append("--force")
    try:
        process = subprocess.Popen(
            argv,
            cwd=str(job.model.parent),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
        )
    except OSError as exc:
        job._say(f"could not start a worker for {job.model.name}: {exc}\n")
        if claim is not None:
            broker.report_done(claim, 1)
        job._finish(1)
        return

    def pump_stderr() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            event = _event_line(line)
            if event is not None:
                emit_event(event)
            else:
                job._say(line)

    def pump_stdout() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            job._say(line)

    def finish() -> None:
        readers = [threading.Thread(target=pump_stderr, daemon=True), threading.Thread(target=pump_stdout, daemon=True)]
        for reader in readers:
            reader.start()
        code = process.wait()
        for reader in readers:
            reader.join(timeout=5.0)
        if code != 0:
            emit_event(model_event(job.model, "failed", exit=code))
        if claim is not None:
            broker.report_done(claim, code)
        job._finish(code)

    threading.Thread(target=finish, name=f"cadgen-job-{job.model.stem}", daemon=True).start()


def _event_line(line: str) -> dict | None:
    """A ``CADGEN_EVENT {...}`` stderr line from a transient child, or None."""
    text = line.strip()
    if not text.startswith(EVENT_LINE_PREFIX):
        return None
    try:
        payload = json.loads(text[len(EVENT_LINE_PREFIX):])
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


EVENT_LINE_PREFIX = "CADGEN_EVENT "


# --- daemon executor ---------------------------------------------------------------------


def _submit_daemon(
    job: Job,
    store_root: Path,
    *,
    force: bool,
    root_id: str | None,
    closure: str | None = None,
    tool: str = "run",
    argv: list[str] | None = None,
    prog: str | None = None,
) -> None:
    from cadgen.daemon import client

    if argv is None:
        argv = [str(job.model)]
        if force:
            argv.append("--force")
    fallback = None
    if tool != "run":
        fallback = [sys.executable, "-m", f"cadgen.cli.{tool.replace('-', '_')}", *argv]

    def run() -> None:
        code = client.run_nested(
            tool,
            argv,
            str(job.model.parent),
            prog=prog or f"python {job.model.name}",
            store_root=str(store_root),
            root_id=root_id,
            closure=closure,
            on_stream=job._say,
            on_event=emit_event,
        )
        if code is None:
            # The daemon could not take the job (spawn failure, unsupported
            # platform mid-flight): run it transiently rather than fail the parent.
            _submit_transient(job, store_root, force=force, root_id=root_id, closure=closure, command=fallback)
            return
        if code != 0:
            emit_event(model_event(job.model, "failed", exit=code))
        job._finish(code)

    threading.Thread(target=run, name=f"cadgen-job-{job.model.stem}", daemon=True).start()
