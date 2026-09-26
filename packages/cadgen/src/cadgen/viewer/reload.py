"""Development auto-reload: a Viewer run from a source CHECKOUT restarts itself.

This is a development convenience — the ``uvicorn --reload`` of this server —
and it exists in exactly one situation: cadgen imported from a source checkout.
The installed wheel carries none of it. No watcher thread starts, no digest is
computed, nothing restarts, and ``/__cad/server`` reports ``autoReload: false``,
because nothing edits a wheel's Python underneath a running server and a tool a
user installed must never restart itself.

THE PREDICATE, IN ONE PLACE
    ``running_from_source_checkout()`` is the only thing that decides. The
    directory holding the ``cadgen`` package is named ``src`` and its parent
    holds a ``pyproject.toml`` that names cadgen — which is exactly this repo's
    ``packages/cadgen/src/cadgen``, and exactly what an EDITABLE install
    resolves to (however the finder got there, the modules' ``__file__``
    points into the checkout). A wheel lands in ``site-packages``, whose parent
    holds no project file, so it reads false. Deliberately NOT an environment
    variable: an env var is a second predicate, and two predicates drift.

WHAT IS WATCHED
    Every ``.py`` under the cadgen package, not just ``cadgen/viewer``: this
    server imports the daemon client, the store and the transport, and
    watching the viewer alone left it running against changed code it had
    already imported. ``__pycache__`` and ``_runtime`` are skipped — a
    byte-identical tree must not read as changed because an interpreter
    recompiled it.

    The BUILT CLIENT is deliberately not watched. Development is
    ``npm run dev``, where Vite owns the client and HMR already handles it; a
    checkout's ``cadgen viewer`` serves the last ``npm run build`` on purpose
    (see apps/web/README.md). Keeping a stale ``dist/`` in sync is not this
    module's job.

HOW IT DECIDES
    Two stages, the same shape as the launcher's identity token: a cheap
    name/size/mtime signature guards a content digest, and only a CONTENT
    change counts. A ``touch``, or a rebuild that produces the same bytes,
    restarts nothing. The comparison is against the digest taken when THIS
    process started, so an edit that is undone before the restart fires simply
    stops being pending.

    The cheap guard is skipped ONCE A RESTART IS PENDING. It exists to keep the
    idle path free, and it cannot be trusted to report a tree settling back:
    Windows stamps a write from the ~15.6ms interrupt clock, so an edit and the
    edit that undoes it can land in one tick with the same mtime and the same
    size, and the signature is then identical across a change it must not hide.
    Once something is pending we are already committed to restarting, so the
    handful of ticks before it fires read the content outright and correctness
    costs one walk rather than an unstoppable restart into code nobody wrote.

    Then two gates. Edits must go QUIET (every further change pushes the
    deadline out) so a rebase that touches forty files restarts once, and the
    server must be idle, so the restart never kills a compile the viewer is
    proxying for the browser.

HOW IT RESTARTS
    On the SAME PORT, always — that is what keeps the URL in the browser, and
    Vite's dev proxy target, valid across the restart. ``restart_argv`` rewrites
    only the binding flags.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

__all__ = [
    "WATCH_INTERVAL_SECONDS",
    "QUIET_SECONDS",
    "DEFERRED_POLL_SECONDS",
    "package_dir",
    "running_from_source_checkout",
    "watched_sources",
    "source_stat_signature",
    "source_content_digest",
    "restart_argv",
    "execute_restart",
    "SourceReloader",
]

# One second is the uvicorn/watchfiles feel: fast enough that saving a file and
# reloading the browser finds new code, slow enough to be free (190 stats).
WATCH_INTERVAL_SECONDS = 1.0
# How long the sources must stop changing before the restart fires.
QUIET_SECONDS = 1.0
# While a restart is pending but deferred, re-check this often instead.
DEFERRED_POLL_SECONDS = 0.25

_PACKAGE_DIR = Path(__file__).resolve().parents[1]
_IGNORED_DIRS = frozenset({"__pycache__", "_runtime"})


def package_dir() -> Path:
    """The installed ``cadgen`` package directory (``.../cadgen``)."""
    return _PACKAGE_DIR


def running_from_source_checkout(directory=None) -> bool:
    """True when this cadgen is a source checkout rather than an installed wheel.

    The single predicate the whole mechanism is gated on; see the module
    docstring for why it is spelled this way and why there is no env var.
    """
    package = Path(directory) if directory is not None else _PACKAGE_DIR
    src_dir = package.parent
    if src_dir.name != "src":
        return False
    try:
        project = (src_dir.parent / "pyproject.toml").read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return False
    return 'name = "cadgen"' in project


def watched_sources(base=None) -> list[str]:
    """Every watched ``.py`` path, sorted — the walk both digests share."""
    root = os.fspath(base if base is not None else _PACKAGE_DIR)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in _IGNORED_DIRS]
        for filename in filenames:
            if filename.endswith(".py"):
                found.append(os.path.join(dirpath, filename))
    return sorted(found)


def _digest_over(base, reader) -> str:
    root = os.fspath(base if base is not None else _PACKAGE_DIR)
    digest = hashlib.sha256()
    digest.update(os.fsencode(root))
    digest.update(b"\0")
    for path in watched_sources(root):
        digest.update(os.fsencode(os.path.relpath(path, root)))
        digest.update(b"\0")
        try:
            digest.update(reader(path))
        except OSError as error:
            # A tree changing under the walk must never look identical to a
            # tree that did not change. The next tick reads a stable value.
            digest.update(f"!{type(error).__name__}:{error.errno}".encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _stat_bytes(path: str) -> bytes:
    value = os.stat(path)
    return f"{value.st_size}:{value.st_mtime_ns}".encode("ascii")


def _content_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def source_stat_signature(base=None) -> str:
    """Names, sizes and mtimes: the cheap guard, never the decision."""
    return _digest_over(base, _stat_bytes)


def source_content_digest(base=None) -> str:
    """Names and BYTES: the decision. A no-op rebuild digests identically."""
    return _digest_over(base, _content_bytes)


def restart_argv(argv, *, port: int) -> list[str]:
    """The same launch, pinned to the port this process already holds.

    Everything the operator asked for survives — ``--host``, ``--dist``,
    ``--api-only``, ``--no-registry``, ``--new``, ``--json``. Only the BINDING
    is rewritten: ``--ephemeral`` and any ``--port`` are dropped and
    ``--port <bound>`` appended, so the restarted process takes the very port
    the browser is already open on (and, under ``npm run dev``, the ephemeral
    port Vite's proxy was handed at startup). An explicit ``--port`` also makes
    the launcher skip its reuse lookup, so a restart can never hand itself back
    to some other instance instead of coming back.
    """
    rebuilt: list[str] = []
    drop_value = False
    for item in list(argv):
        if drop_value:
            drop_value = False
            continue
        if item == "--ephemeral":
            continue
        if item == "--port":
            drop_value = True
            continue
        if item.startswith("--port="):
            continue
        rebuilt.append(item)
    rebuilt.extend(["--port", str(int(port))])
    return rebuilt


def execute_restart(argv, *, executable: str = "", platform: str = "") -> None:
    """Become the new code. The caller has already closed the listening socket.

    POSIX: ``os.execv`` replaces the image and KEEPS THE PID, so the registry
    entry — which is named by pid — stays the operator's handle across the
    restart and the new image simply writes over it.

    Windows: ``os.execv`` there is the C runtime's, which spawns a NEW process
    with a new pid and terminates this one, so the pid handoff cannot be
    implicit — the caller drops the registry entry and the child registers
    itself. The standard handles are passed EXPLICITLY (``stdout=1, stderr=2``)
    rather than left to inheritance: an exec keeps whatever stdout and stderr
    were, and a Windows spawn only does so if it is told to — without this, a
    server whose stderr had been redirected to a file or a pipe came back
    writing to a console that, in CI, is not there at all, and its narration
    simply vanished at the restart. Nothing else is inherited, and the cwd is
    left alone: it IS the served directory, and the replacement needs it.

    Always ``-m cadgen.viewer``: it is the documented equivalent of the
    ``cadgen viewer`` console script, and it works whichever of the two
    started this process, since the interpreter running it can import cadgen by
    construction.
    """
    interpreter = executable or sys.executable
    if not interpreter:
        raise OSError("no interpreter to re-execute (sys.executable is empty)")
    command = [interpreter, "-m", "cadgen.viewer", *list(argv)]
    if (platform or sys.platform).startswith("win"):
        # Flush BEFORE spawning: parent and child write the same descriptors,
        # and anything still sitting in this process's buffers would otherwise
        # land after the replacement's first lines.
        _flush_std_streams()
        subprocess.Popen(command, stdout=1, stderr=2)  # noqa: S603 - our own interpreter, our own argv
        os._exit(0)
    os.execv(interpreter, command)


def _flush_std_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, ValueError, AttributeError):  # detached, closed, or replaced
            pass


class SourceReloader:
    """Poll the checkout's Python sources; restart once the edits settle.

    ``is_idle()`` is the server's own in-flight accounting and ``restart()``
    asks the serve loop to stop — both injected, so the whole decision is
    testable without a socket or a process.
    """

    def __init__(
        self,
        *,
        is_idle,
        restart,
        base_dir=None,
        interval: float = WATCH_INTERVAL_SECONDS,
        quiet: float = QUIET_SECONDS,
        clock=time.monotonic,
    ) -> None:
        self._base = os.fspath(base_dir) if base_dir is not None else os.fspath(_PACKAGE_DIR)
        self._is_idle = is_idle
        self._restart = restart
        self._interval = float(interval)
        self._quiet = float(quiet)
        self._clock = clock
        self._stat = source_stat_signature(self._base)
        # The code THIS process is running. Compared against, never replaced:
        # an edit that is reverted before the restart fires stops being pending
        # instead of restarting into the code already loaded.
        self._running = source_content_digest(self._base)
        self._seen = self._running
        self._changed_at = 0.0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.restarts = 0

    @property
    def pending(self) -> bool:
        return self._seen != self._running

    def poll_once(self) -> bool:
        """One tick. True when it fired the restart.

        The test seam: drive this directly and nothing here needs a thread.
        """
        signature = source_stat_signature(self._base)
        # `or self.pending`: while a restart is queued the cheap guard is not
        # allowed to hide the tree settling back to the running code -- see the
        # module docstring on Windows's 15.6ms write clock.
        if signature != self._stat or self.pending:
            self._stat = signature
            content = source_content_digest(self._base)
            if content != self._seen:
                self._seen = content
                # Debounce. Each further change pushes the deadline out, so a
                # checkout, rebase or bundle that rewrites many files at once
                # produces exactly one restart.
                self._changed_at = self._clock()
        if not self.pending:
            return False
        if self._clock() - self._changed_at < self._quiet:
            return False
        if not self._is_idle():
            # A compile the viewer is proxying holds its request thread for the
            # whole build. The restart waits; it never kills that build.
            return False
        self.restarts += 1
        self._running = self._seen
        self._restart()
        return True

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, name="cadgen-viewer-reload", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(DEFERRED_POLL_SECONDS if self.pending else self._interval):
            try:
                if self.poll_once():
                    return
            except Exception:  # noqa: BLE001 - a watcher fault must not kill the server
                return
