"""quiddity asked about one part's STEP at a time, in a process of its own that can be stopped.

**Why a process of its own.** quiddity's library runs a recognition to its end: it has no time limit, no way to
stop one and no bound on its memory, its cost grows with the faces it is handed and with how free-form they are,
and a fault in its native code that is no Rust panic -- an exhausted stack, memory the system refuses -- ends the
process it runs in. A manufacturing check runs in one of the engine's kernel processes, which holds a document
and must outlive whatever a part's geometry does to a recogniser. So the process that holds the kernel never
imports quiddity: the recogniser is a child interpreter (``python -m cad.quiddity._recogniser``, which imports
quiddity alone), handed each part's STEP over a pipe and answering each in turn, nothing written to disk. A part
it has not answered ``timeout_s`` after it was asked is given up: the child is stopped, that part says
``timed_out``, and the parts after it go to a new child. While a part is with it the child's resident memory is
read from outside every ``WATCH_S`` (``cad.engine.worker.resident_of``, as a check's own process is held to its
limit), and a child that holds more than ``RSS_MB`` is stopped the same way: that part says ``over_memory``.
That is the only bound on its memory: between two readings it can grow by what it allocates in a quarter of a
second, and where the system does not say a process's memory (``resident_of`` None) there is none. A child
that ends while a part is with it says ``stopped``, with the end of what it printed, and the rest go to a new
one likewise. A child ends with its input: one whose asker has gone, however it went, stops in the middle of
whatever part it has.

**Where quiddity is.** An integration runs where its extra is installed: the child is this interpreter where this
environment holds quiddity (one installed with ``cad[quiddity]``, a checkout's development environment), else the
Python of the quiddity integration's environment, ``cad[quiddity]`` at the installation's release, which the
device's engine makes once, on first need, and keeps (``{"op": "integration", "integration": "quiddity"}`` over
its door, as a worker's decomposition has coacd's: ``cad_server._internal.integration_env``), each line of its
making said on stderr as it comes; offline first, from uv's cache, and the network for what that lacks. So the
engine's kernel processes, which run in the base (``cad[build123d]``), have quiddity with nothing added to the
base. ``Unavailable`` says why no environment can hold it: quiddity publishes no wheel for this platform
(``PLATFORMS``: none for Windows on ARM, a musl Linux or a glibc before 2.28), no engine answers to make it (a
program's own process with none running), or its making failed (uv's words). ``PROVIDE`` stands in for the engine
(a test's provisioner).

**No part waits on the network.** The engine is waited for ``ENVIRONMENT_S`` at most: an environment that is
made answers in milliseconds, and one made from uv's cache in a second or two, so the first part that needs it
has it; a making that needs the network takes longer than that, goes on in the engine with nobody waiting, and
is there for a later call. A part whose environment did not come in time, or could not be made, has no features
(``not_installed``), and this process asks for none again for ``ASK_AGAIN_S``: every part until then is
answered the same at once, so a making that fails -- a computer offline with nothing cached -- costs one wait,
never one a part or one a check.
"""

from __future__ import annotations

import collections
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cad.quiddity._frames import HEAD, read

__all__ = ["ASK_AGAIN_S", "ENVIRONMENT_S", "EXTRA", "PLATFORMS", "PROVIDE", "READY_S", "RSS_MB", "TIMEOUT_S", "WATCH_S",
           "Recogniser", "Unavailable", "published", "seconds"]

EXTRA = "cad[quiddity]"
#: The quiddity integration's recogniser, run as a module in the child (quiddity is never imported here).
CHILD = "cad.quiddity._recogniser"
#: Where quiddity publishes wheels, and so where ``cad[quiddity]`` installs it (its marker in ``pyproject.toml``;
#: manylinux_2_28 wheels, so a Linux of glibc 2.28 or newer).
PLATFORMS = "macOS, Linux x86_64 and aarch64 (glibc 2.28 or newer) and Windows x86_64"
#: The oldest glibc quiddity's Linux wheels run on (manylinux_2_28).
GLIBC = (2, 28)
#: The Python of the quiddity integration's environment, for a process whose own lacks quiddity: ``PROVIDE(told)``,
#: made first where it is not, each line of its making said to ``told``; None where nothing answers to make it;
#: ``Unavailable`` in its maker's words where it cannot be made. None: the device's engine's (``_engine``).
PROVIDE: Callable[[Callable[[str], None]], str | None] | None = None
#: The longest one part may take (s) where the caller names no other. A part takes quiddity hundredths of a second
#: to a few seconds; what this stops is the one that takes minutes.
TIMEOUT_S = 30.0
#: The longest a child may take to say it is ready (s): an interpreter's start and quiddity's import.
READY_S = 60.0
#: The longest a child told to end may take before it is stopped (s).
GOODBYE_S = 5.0
#: The longest the engine is waited for to answer with the integration's environment (s): one that is made answers
#: in milliseconds and one made from uv's cache in about a second (0.9 s measured for uv's part of it), so several
#: times that; a making that needs the network is not waited for (the module's **No part waits on the network**).
ENVIRONMENT_S = 6.0
#: After an environment that did not come in ``ENVIRONMENT_S`` or could not be made, the seconds this process asks
#: for none: long enough that a making which fails is paid for once a minute at most, short enough that one which
#: was only slow (the network, tens of megabytes of the library's own dependencies) is found soon after it is made.
ASK_AGAIN_S = 60.0
#: The most resident memory a child may hold while a part is with it (MiB), read every ``WATCH_S`` seconds: about
#: four times the most a part within the faces handed over took where it was measured (``_features.FACES``: under
#: 0.3 GiB), and a fraction of what a check's own process may hold.
RSS_MB = 1024.0
WATCH_S = 0.25
#: The lines of the child's own output kept, to say why it stopped where it stops.
TAIL = 6


class Unavailable(RuntimeError):
    """No environment holds quiddity for the recogniser to run in: ``reason`` is ``no_wheel`` or ``not_installed``."""

    def __init__(self, reason: str, text: str) -> None:
        super().__init__(text)
        self.reason = reason


class _Child:
    """One recogniser process: its frames read as they come, its own output's last lines kept."""

    def __init__(self, python: str, env: dict[str, str]) -> None:
        from cad.engine.places import windowless

        self.process = subprocess.Popen([python, "-P", "-m", CHILD], env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, **windowless())
        self.frames: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self.tail: collections.deque[str] = collections.deque(maxlen=TAIL)
        self.threads = [threading.Thread(target=self._frames, name="cad-quiddity-frames", daemon=True),
                        threading.Thread(target=self._output, name="cad-quiddity-output", daemon=True)]
        for thread in self.threads:
            thread.start()

    def _frames(self) -> None:
        assert self.process.stdout is not None
        try:
            while (data := read(self.process.stdout)) is not None:
                self.frames.put(json.loads(data))
        except (OSError, ValueError):
            pass  # a pipe that closed under the read, or a frame that is no JSON: the child is done with
        self.frames.put(None)

    def _output(self) -> None:
        assert self.process.stderr is not None
        try:
            for line in self.process.stderr:
                said = line.decode("utf-8", errors="replace").rstrip()
                if said:
                    self.tail.append(said)
        except (OSError, ValueError):
            pass

    def frame(self, timeout_s: float, rss_mb: float | None = None) -> dict[str, Any] | None | bool:
        """The child's next frame; None where it ended first; False where none came in ``timeout_s``; True where,
        before one came, the child held more resident memory than ``rss_mb`` (read every ``WATCH_S``: None reads
        none)."""
        deadline = time.monotonic() + timeout_s
        while (left := deadline - time.monotonic()) > 0:
            try:
                return self.frames.get(timeout=left if rss_mb is None else min(left, WATCH_S))
            except queue.Empty:
                if rss_mb is not None and (_resident_mb(self.process.pid) or 0.0) > rss_mb:
                    return True
        return False

    def hand(self, step: bytes) -> bool:
        """One part's STEP handed over; False where the child no longer reads."""
        assert self.process.stdin is not None
        try:
            self.process.stdin.write(HEAD.pack(len(step)) + step)
            self.process.stdin.flush()
        except (OSError, ValueError):
            return False
        return True

    def stopped(self) -> str:
        """How the child ended, with the end of what it printed."""
        code = self.process.poll()
        return (f"exit {code}" if code is not None else "still running") + "".join(f"\n  {line}" for line in self.tail)

    def end(self, kill: bool = False) -> None:
        """The child ended: told so by its input's end, stopped where it does not go (or at once: ``kill``)."""
        if kill:
            self.process.kill()
        for stream in (self.process.stdin,):
            try:
                if stream is not None:
                    stream.close()
            except (OSError, ValueError):
                pass
        try:
            self.process.wait(timeout=GOODBYE_S)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        for thread in self.threads:
            thread.join(timeout=GOODBYE_S)  # each ends with its pipe
        for stream in (self.process.stdout, self.process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except (OSError, ValueError):
                pass


class Recogniser:
    """``with Recogniser(timeout_s) as ask``: ``ask(step)`` is quiddity's answer about one part's STEP (its bytes), as
    the child gives it -- ``{"document", "anchors"}`` -- or why there is none, ``{"reason", "detail"}`` (``refused``,
    ``failed``; ``timed_out`` and ``stopped``, the child's end; ``no_wheel`` and ``not_installed``, which every part
    after it is answered too, nothing started again), each with ``quiddity``, its version where a child said it.
    The child starts with the first part asked and ends with the block."""

    def __init__(self, timeout_s: float = TIMEOUT_S) -> None:
        self.timeout_s = seconds(timeout_s)
        self._child: _Child | None = None
        self._version: str | None = None
        self._python: tuple[str, bool] | None = None
        self._never: dict[str, Any] | None = None

    def __enter__(self) -> Callable[[bytes], dict[str, Any]]:
        return self.ask

    def __exit__(self, *_exc: object) -> None:
        if self._child is not None:
            self._child.end()
            self._child = None

    def _start(self) -> dict[str, Any] | None:
        """A child started and ready; else why none is, which is kept where no other try could differ."""
        try:
            if self._python is None:
                self._python = _python()
            python, own = self._python
            child = _Child(python, _child_env(Path(__file__).resolve().parents[2]) if own else _foreign_env())
        except Unavailable as error:
            self._never = {"reason": error.reason, "detail": str(error)}
            return self._never
        except OSError as error:
            self._never = {"reason": "not_installed",
                           "detail": f"cannot run {self._python[0] if self._python else 'python'}: "
                                     f"{error.strerror or error}"}
            return self._never
        hello = child.frame(READY_S)
        if isinstance(hello, dict) and isinstance(hello.get("quiddity"), str):
            self._child, self._version = child, hello["quiddity"]
            return None
        child.end(kill=True)
        if isinstance(hello, dict):  # this Python has no quiddity, in the child's words
            self._never = {"reason": "not_installed",
                           "detail": f"{python} does not import quiddity: {hello.get('detail')}"}
        else:
            self._never = {"reason": "not_installed",
                           "detail": f"quiddity's process did not start ({child.stopped()})"}
        return self._never

    def ask(self, step: bytes) -> dict[str, Any]:
        if self._never is not None:
            return {**self._never, "quiddity": self._version}
        if not step:
            return {"reason": "refused", "detail": "an empty STEP", "quiddity": self._version}
        if self._child is None:
            failed = self._start()
            if failed is not None:
                return {**failed, "quiddity": self._version}
        child = self._child
        assert child is not None
        answer = child.frame(self.timeout_s, RSS_MB) if child.hand(step) else None
        if isinstance(answer, dict):
            return {**answer, "quiddity": self._version}
        self._child = None
        if answer is False:
            child.end(kill=True)
            return {"reason": "timed_out", "quiddity": self._version,
                    "detail": f"quiddity did not finish the part in {self.timeout_s:g} s and was stopped"}
        if answer is True:
            child.end(kill=True)
            return {"reason": "over_memory", "quiddity": self._version,
                    "detail": f"quiddity's process held more than {RSS_MB:g} MiB with the part and was stopped"}
        child.end()
        return {"reason": "stopped", "quiddity": self._version,
                "detail": f"quiddity's process ended while it had the part ({child.stopped()})"}


def seconds(timeout_s: Any) -> float:
    """``timeout_s`` as the seconds one part may take: a positive, finite number, or ``ValueError`` by its name
    (an infinite one would never give a part up, and no clock waits a negative or an undefined time)."""
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s) \
            or timeout_s <= 0:
        raise ValueError(f"timeout_s is a positive, finite number of seconds, not {timeout_s!r}")
    return float(timeout_s)


def _resident_mb(pid: int) -> float | None:
    """The resident memory of process ``pid`` now (MiB), read from outside it as a check's own process's is
    (``cad.engine.worker.resident_of``); None where the system does not say."""
    from cad.engine.worker import resident_of

    return resident_of(pid)


def published(system: str | None = None, machine: str | None = None, glibc: tuple[int, int] | None | bool = True) -> bool:
    """Whether quiddity publishes a wheel for this platform (``PLATFORMS``), or the one given (``glibc``: its
    version, or None for a Linux of another C library; True reads this one's)."""
    import platform

    system = platform.system() if system is None else system
    machine = (platform.machine() if machine is None else machine).lower()
    if system == "Darwin":
        return machine in ("arm64", "x86_64")
    if system == "Windows":
        return machine in ("amd64", "x86_64")
    if system == "Linux":
        version = _glibc() if glibc is True else glibc
        return machine in ("x86_64", "aarch64", "arm64") and bool(version) and tuple(version) >= GLIBC
    return False


def _glibc() -> tuple[int, int] | None:
    """This Python's glibc, as ``(major, minor)``; None on another C library (musl)."""
    import platform

    said = ""
    try:
        said = os.confstr("CS_GNU_LIBC_VERSION") or ""
    except (AttributeError, OSError, ValueError):
        pass
    name, _, version = said.partition(" ")
    if name != "glibc":
        name, version = platform.libc_ver()
    if name != "glibc":
        return None
    try:
        major, minor = (int(piece) for piece in version.split(".")[:2])
    except ValueError:
        return None
    return major, minor


def _python() -> tuple[str, bool]:
    """The Python the child runs (the module's **Where quiddity is**), and whether it is this one."""
    import importlib.util
    import platform

    if importlib.util.find_spec("quiddity") is not None:
        return sys.executable, True
    if not published():
        raise Unavailable("no_wheel", f"quiddity comes with cad's quiddity integration, {EXTRA}, which installs it only "
                                      f"where quiddity publishes wheels, {PLATFORMS}, and this is {platform.system()} "
                                      f"{platform.machine()}")
    return _provided(), False


# Why this process asks for no environment, and until when (``time.monotonic``): the last asking's failure.
_REFUSED: tuple[float, Unavailable] | None = None
_ASKING = threading.Lock()


def _provided() -> str:
    """The Python of the integration's environment as the engine (``PROVIDE``) answers it, waited for
    ``ENVIRONMENT_S`` at most; ``Unavailable`` (``not_installed``) where it does not come in time, cannot be
    made, or nothing answers to make it -- and then again, at once and unasked, for ``ASK_AGAIN_S`` (the
    module's **No part waits on the network**)."""
    global _REFUSED

    with _ASKING:
        if _REFUSED is not None and time.monotonic() < _REFUSED[0]:
            raise _REFUSED[1]
        answered: list[tuple[bool, Any]] = []

        def ask() -> None:
            try:
                answered.append((True, (PROVIDE or _engine)(_told)))
            except BaseException as error:  # noqa: BLE001 -- raised again by whoever waits, where it still waits
                answered.append((False, error))

        asking = threading.Thread(target=ask, name="cad-quiddity-environment", daemon=True)
        asking.start()
        asking.join(ENVIRONMENT_S)
        if not answered:
            failed = Unavailable("not_installed", f"{EXTRA}'s environment was not ready in {ENVIRONMENT_S:g} s (the "
                                                  "engine goes on making it): it is asked for again in "
                                                  f"{ASK_AGAIN_S:g} s, and until then no part is read with quiddity")
        elif not answered[0][0]:
            error = answered[0][1]
            if not isinstance(error, Unavailable):
                raise error
            failed = error
        elif answered[0][1] is None:
            failed = Unavailable("not_installed", f"quiddity comes with cad's quiddity integration, {EXTRA}, which this "
                                                  "environment does not hold, and no engine answered to make its "
                                                  "environment: run the script with cad run, whose engine makes it on "
                                                  f"first need, or install {EXTRA} here")
        else:
            _REFUSED = None
            return answered[0][1]
        _REFUSED = (time.monotonic() + ASK_AGAIN_S, failed)
        raise failed


def _told(line: str) -> None:
    print(f"cad: {line}", file=sys.stderr, flush=True)


def _engine(told: Callable[[str], None]) -> str | None:
    """The Python of the quiddity integration's environment, made by the device's engine where it is not (``{"op":
    "integration"}``), its lines said to ``told``; None where no engine answers, or one that has no such request
    (another release's). ``Unavailable`` in the engine's words where it cannot be made."""
    from cad.engine import client

    try:
        answer = client.request({"op": "integration", "integration": "quiddity"}, start=False,
                                on_log=lambda frame: told(str(frame.get("log", ""))))
    except (ConnectionError, OSError, ValueError):
        return None
    if not answer or str(answer.get("failed") or "").startswith(("unknown request", "no integration")):
        return None
    if answer.get("failed"):
        raise Unavailable("not_installed", f"the engine could not make {EXTRA}'s environment: {answer['failed']}")
    python = answer.get("python")
    return python if isinstance(python, str) and python else None


def _foreign_env() -> dict[str, str]:
    """The child's environment where it runs another environment's Python: this one, without the import path
    this process was handed, so that Python imports its own cad and quiddity."""
    return {name: value for name, value in os.environ.items() if name not in ("PYTHONPATH", "PYTHONHOME")}


def _child_env(source: Path) -> dict[str, str]:
    """The child's environment: this one, with the folder this cad was imported from first on its
    PYTHONPATH where the interpreter would not find it by itself (a source checkout, a test's path). Never
    a site-packages folder: on PYTHONPATH it would come before the standard library."""
    import site

    sites = {Path(p).resolve() for p in [*site.getsitepackages(), site.getusersitepackages()]}
    if source in sites:
        return dict(os.environ)
    return {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(source), os.environ.get("PYTHONPATH")]))}
