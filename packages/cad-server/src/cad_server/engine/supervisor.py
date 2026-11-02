"""The daemon's one supervisor of the processes it starts: each kind a service it declares
(``Service``: ``services`` holds the declarations), every one run by the same rules.

**A service** says what its process runs (``command``, in the environment it names:
``"kernel"``, the installation's base, ``places.kernel``, or a sibling environment's interpreter
by its absolute path), whether a lease may name the Python its process runs instead, its caller's
(``interpreter``: ``"lease"``; ``"environment"``, the default, never), the environment a process starts
with (``env``: the caller's, ``"lease"``,
or the daemon's own, ``"daemon"``; then ``set_env``, and the bytecode rule: the daemon's folder of
it, ``"daemon"``, or none written, ``"read-only"``), the folder it starts in (``cwd``: the lease's,
else the key's folder; or the daemon's, ``"inherit"``), what one process serves (``key``: a
script's path, normcased, or an id as given), what binds a process to its caller's interpreter
(``binding``: a lease whose values of those variables differ is another interpreter, and replaces
the process), what becomes of its stderr (``stderr``: each line passed to whoever asked and its
last 16,384 characters kept, ``"relay"``; or its last lines kept, ``"keep"``), the frames it sends
for the daemon's hooks (``events``), the words a process that is gone is said in (``words``),
whether it counts toward the count cap (``counted``), its rank when memory is shed (``rank``, and
``watched_rank`` for a process a page watches), whether its retirements are listed in ``status``
(``noted``: the row's name for what it served and for its answered requests), whether the
daemon drains it before it stops (``drain``), how long its start may take before it is given up
(``ready_seconds``: None waits as long as it lives; one given up is killed, and the lease that waited
for it fails with ``Gone.unready``, which no request asks again). Each field is a closed vocabulary,
refused at declaration otherwise. A new kind of process is a declaration; nothing of the daemon changes
for it.

**A lease** (``lease``): the process a request runs in, one request at a time, granted first come
first served. A request whose key has a live process of its binding takes it once it is free; one
of another binding replaces it in its slot once it is free (retired ``environment``); one whose
key's process is being started waits for that one. A lease that names its caller's Python
(``python``, of a service whose ``interpreter`` is ``"lease"``) is of a key of its own, its key and that
Python's own key together (``python_key``: the caller's environment and release, which the daemon
says), so the same key leased from two environments is two processes, and a process started in one
never serves a lease of another; the process runs the first Python its key was leased with, whatever
spelling of that environment's interpreter a later lease names. A request that needs a process of
its own starts one at once when its service does not count; else starts one in a free slot under the
count cap (``cap``, shared by every counted service). At the cap the idle counted process of the lowest
rank no page watches -- one no waiting request wants, then the least recently used -- is retired
``LRU``. When every idle one is watched the new one starts past the cap: connected means warm. With
none idle the request waits, and so does every counted request after it. ``release`` gives the
process back: free again, or, retired by its own answer (``retire``) or gone, out of the table
(``RSS``, ``exited``), drained when its service drains, and stopped. A process that dies idle leaves
the table at the next grant (``exited``). A process of a service in the kernel environment starts only
once that environment exists: its start makes it when it is not (``places.kernel``, on first need), and
the lease waits on the making; nothing is started ahead of a request, and no process stands by.

**Memory** (``shed``): every process's resident memory, as it last said it (its ``ready`` frame
and each answer's ``rssMb``), is held to one cap (``memory()``, in MiB; None: none). Past it, or under
the system's memory pressure to ``PRESSURE_SHARE`` of it, idle processes are retired in the order their
declarations rank them -- each service's rank, a watched process's ``watched_rank`` -- least recently
used first within a rank; a process that never said its memory is
skipped, a busy one never taken. Each retired is drained when its service drains, then stopped.

**The protocol** (``cad.engine.frames``): requests are one JSON object per line on the child's
stdin, a request's payload ``bytes`` after its line, each carrying the memory cap the child is held
to (``rssCapMb``, None for none: the daemon's, never the caller's environment's); the child answers
on its original stdout in frames. Its first is ``{"ready": pid, "rssMb"}``. Then, for each request,
its ``log``, ``notice`` and ``progress`` frames, which go to whoever asked (a progress frame to the
requests following it and to ``on_progress`` too), and one answer, which may carry ``rssMb`` and
``retire``. A frame of
one of its service's ``events`` goes to that event's hook (``on_event``), never to a request; a
side request's answer (``question``) to its waiter, by its id. Lines that are not JSON objects
are skipped. Whatever it prints goes to its stderr. It exits when its stdin closes; ``stop`` closes
it, waits ``STOP_SECONDS``, then kills. The supervisor holds each child from its spawn (``spawning``):
its own ``stop`` kills one still being started, which reads nothing until it is ready, so none
outlives the daemon.

Locks: the supervisor's, then ``watched``'s (the server's watch lock), never the other way.
``drain``, ``launch``, ``stop``, ``memory``, a process's own lock and the hooks are called with
the supervisor's lock not held. Constructing a supervisor starts no process and no thread.
"""

from __future__ import annotations

import collections
import itertools
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cad.engine import frames, places
from cad.engine.client import WORKER_STDERR

__all__ = ["Gone", "PRESSURE_SHARE", "Process", "RETIRED_KEPT", "STOP_SECONDS", "Service", "Supervisor", "Words"]

# Under the system's memory pressure, the processes' resident memory is brought down to this share of
# its cap, as the server's documents are of their budget (``serve.LOW_WATER``).
PRESSURE_SHARE = 0.5
# The retirements ``status`` lists, the latest first.
RETIRED_KEPT = 12
# How long a process stopped has, once its stdin is closed, before it is killed.
STOP_SECONDS = 5.0
# What a ``"relay"`` service's failure says of its stderr: its last characters, under ``WORKER_STDERR``.
TAIL_CHARACTERS = 16384
# What a ``"keep"`` service keeps of its stderr, and the last lines of it its failure says.
KEPT_LINES, SAID_LINES = 40, 5
# The ids of side requests (``question``), which no request's id begins with.
QUESTION = "?"
# What joins a process's key and the Python a lease named for it (``Supervisor._key``): no path or id
# holds it.
INTERPRETER = "\0"


def _closed(name: str, value: Any, allowed: tuple[Any, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{name} is {value!r}: one of {', '.join(repr(each) for each in allowed)}")


@dataclass(frozen=True)
class Words:
    """How a process that is gone is said, ``{label}`` its key as given, ``{name}`` that path's last
    part: it did not start (``unstarted``), it exited during a request (``exited``, with ``{code}``),
    its pipe broke (``broken``, with ``{error}``). Its stderr follows, as its service keeps it."""

    unstarted: str
    exited: str
    broken: str


@dataclass(frozen=True)
class Service:
    """One kind of process the daemon starts (see the module)."""

    name: str
    command: tuple[str, ...]  # ``"{python}"`` is the environment's interpreter, or the one a lease names
    environment: str  # ``"kernel"`` (``places.kernel``), or an interpreter's absolute path
    env: str  # ``"lease"`` (the caller's environment) or ``"daemon"`` (the daemon's ``os.environ``)
    words: Words
    set_env: tuple[tuple[str, str], ...] = ()
    bytecode: str = "daemon"  # ``"daemon"`` (the daemon's folder, ``places.bytecode``) or ``"read-only"``
    cwd: str = "lease"  # ``"lease"`` (the lease's folder, else its key's) or ``"inherit"`` (the daemon's)
    key: str = "path"  # ``"path"`` (normcased) or ``"id"`` (as given)
    lifetime: str = "warm"  # a process lives until it is retired or stopped
    concurrency: int = 1  # one request at a time per process
    binding: tuple[str, ...] = ()  # what of a lease's environment binds a process to it
    stderr: str = "relay"  # ``"relay"`` (each line to whoever asked, and a tail) or ``"keep"`` (the last lines)
    events: tuple[str, ...] = ()  # frames for the daemon's hooks (``on_event``), never a request's answer
    counted: bool = True  # holds a slot of the count cap
    rank: int = 2  # its order when memory is shed: lower goes first
    watched_rank: int | None = None  # a watched process's rank; such a process is never the count cap's
    noted: tuple[str, str] | None = None  # its retirements in ``status``: the row's names for its key and requests
    drain: bool = False  # the daemon's ``drain`` runs before it is stopped, out of the table and alive
    ready_seconds: float | None = None  # how long its start may take; None: as long as it lives
    # Whose Python a process runs: its ``environment``'s (``"environment"``), or the one a lease names,
    # its caller's (``"lease"``: ``Supervisor.lease``'s ``python``), else its environment's.
    interpreter: str = "environment"

    def __post_init__(self) -> None:
        if not self.name or not self.command:
            raise ValueError("a service has a name and a command")
        if self.environment != "kernel" and not os.path.isabs(self.environment):
            raise ValueError(f"environment is {self.environment!r}: 'kernel' or an interpreter's absolute path")
        _closed("env", self.env, ("lease", "daemon"))
        _closed("bytecode", self.bytecode, ("daemon", "read-only"))
        _closed("cwd", self.cwd, ("lease", "inherit"))
        _closed("key", self.key, ("path", "id"))
        _closed("lifetime", self.lifetime, ("warm",))
        _closed("concurrency", self.concurrency, (1,))
        _closed("stderr", self.stderr, ("relay", "keep"))
        _closed("interpreter", self.interpreter, ("environment", "lease"))
        if self.noted is not None:
            _closed("noted's key", self.noted[0], ("script", "document"))
            _closed("noted's count", self.noted[1], ("builds", "requests"))
        if self.ready_seconds is not None and not self.ready_seconds > 0:
            raise ValueError(f"ready_seconds is {self.ready_seconds!r}: a positive number, or None")


class Gone(Exception):
    """A process that is gone: it did not start, or it exited, or its pipe broke. ``during``: it
    exited while a request waited for its answer, which it may have half done; ``code``: its exit
    status, where it is known; ``unready``: it never said it was ready within its declared seconds, and
    was killed (another would wait as long again: no request asks one again)."""

    def __init__(self, message: str, *, during: bool = False, code: int | None = None, unready: bool = False) -> None:
        super().__init__(message)
        self.during, self.code, self.unready = during, code, unready


def _home(service: Service, label: str, cwd: str | None) -> str | None:
    """The folder a process of ``label`` starts in, asked from ``cwd``: the lease's, else its
    key's (a script's folder, so its relative reads resolve as under ``python SCRIPT``); None for
    a service that stands where the daemon does."""
    if service.cwd == "inherit":
        return None
    return cwd or str(Path(label).parent)


class Process:
    """The parent's side of one child of a service: its pipes and the threads that read them, the
    key it serves, and its place in the supervisor -- whether a lease holds it (``leased``) since
    when (``since``), when it was last let go (``used``), its resident memory as it last said it
    (``rss``, MiB), whether it said it is over its cap (``retired``) -- and ``state``, where the
    service's own code keeps what it knows of the process (a render process's version)."""

    def __init__(self, service: Service, key: str, label: str, environment: dict[str, str], popen: Any,
                 on_progress: Callable[["Process", dict[str, Any]], None] | None = None,
                 on_event: dict[str, Callable[["Process", Any, bytes], None]] | None = None,
                 memory: Callable[[], float | None] | None = None) -> None:
        self.service, self.key, self.label, self.environment = service, key, label, environment
        self.popen = popen
        self.on_progress = on_progress or (lambda _process, _frame: None)
        self.on_event = dict(on_event or {})
        # The memory cap of the supervisor that started it, which each request carries (``rssCapMb``),
        # so a process retires itself by the cap the daemon holds it to; None: started by no supervisor.
        self.memory = memory
        self.lock = threading.Lock()  # one request at a time
        self.writing = threading.Lock()  # one frame at a time on its stdin
        self.answers: "queue.Queue[dict[str, Any] | None]" = queue.Queue()
        self.asked: dict[str, "queue.Queue[Any]"] = {}
        self.questions = itertools.count(1)
        # Whoever the running request answers (its log, notices and progress), and the requests
        # waiting behind it that follow its progress (``Supervisor.follow``).
        self.sink: Callable[[dict[str, Any]], None] | None = None
        self.followers: list[Callable[[dict[str, Any]], None]] = []
        # The running request's op, when it began (``time.time()``) and its last progress frame.
        self.op: str | None = None
        self.began: float | None = None
        self.progress: dict[str, Any] | None = None
        self.pid: int | None = None
        # The Python a lease named for it, its caller's (``Service.interpreter``), as its first lease
        # spelled it, and the key of that Python's environment it serves (``Supervisor.lease``'s
        # ``python_key``); None: its service's environment's.
        self.python: str | None = None
        self.python_key: str | None = None
        self.started = time.time()
        self.requests = 0
        self.rss: float | None = None
        self.retired = False
        self.leased = False
        self.since = 0.0
        self.used = time.monotonic()
        self.state: dict[str, Any] = {}
        # Its stderr as its service keeps it (local failure detail, never telemetry): the last
        # characters since the running request began, or its last lines.
        self.tail = ""
        self.said: list[str] = []
        self.tail_lock = threading.Lock()
        self.stderr_thread: threading.Thread | None = None

    @classmethod
    def start(cls, service: Service, key: str, label: str, environment: dict[str, str], cwd: str | None = None, *,
              on_progress: Callable[["Process", dict[str, Any]], None] | None = None,
              on_event: dict[str, Callable[["Process", Any, bytes], None]] | None = None,
              memory: Callable[[], float | None] | None = None,
              spawned: Callable[[Any], None] | None = None, python: str | None = None) -> "Process":
        """A process of ``service`` started for ``key`` (``label`` as the lease gave it) in
        ``environment``, once it has said it is ready -- the kernel environment it runs in (``"kernel"``) made
        first when it is not, the request waiting on its making; ``memory``: the cap its requests carry; ``spawned``:
        told the child as soon as it exists, before it is ready (its supervisor's to kill should it
        stop meanwhile); ``python``: the Python a lease named, its caller's, which it runs in place of its
        service's environment's, its import path the caller's own. ``Gone`` when it does not start."""
        named = python
        if named is not None:
            own = False
        elif service.environment == "kernel":
            found = places.kernel(make=True)
            assert found is not None  # made, or refused
            python, own = found["python"], found["own"]
        else:
            python, own = service.environment, False
        env = dict(environment) if service.env == "lease" else dict(os.environ)
        if own:
            # The daemon's own environment: the engine it runs, its folder first on the path.
            root, path = places.engine_root(), env.get("PYTHONPATH", "")
            if root not in path.split(os.pathsep):
                env["PYTHONPATH"] = os.pathsep.join(item for item in (root, path) if item)
        if service.bytecode == "daemon":
            # The daemon's bytecode, whoever's lease starts the process: it serves every later one too.
            kept = {name: os.environ[name] for name in places.BYTECODE if name in os.environ}
            env = {name: value for name, value in env.items() if name not in places.BYTECODE}
            env.update(kept or places.bytecode({}))
        else:
            env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.update(service.set_env)
        argv = [python if part == "{python}" else part for part in service.command]
        popen = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=env, cwd=_home(service, label, cwd), **places.windowless())
        if spawned is not None:
            spawned(popen)
        process = cls(service, key, label, environment, popen, on_progress, on_event, memory)
        process.python = named
        process._ready(service.ready_seconds)
        return process

    def _ready(self, seconds: float | None) -> None:
        """Its readers started, and its ``ready`` frame awaited, ``seconds`` at most (None: as long
        as it lives); a process that never said it is killed."""
        self.stderr_thread = threading.Thread(target=self._stderr, daemon=True)
        self.stderr_thread.start()
        threading.Thread(target=self._reader, daemon=True).start()
        try:
            ready = self.answers.get(timeout=seconds)
        except queue.Empty:
            self.kill()
            raise Gone(f"{self._words('unstarted')}: it never said it was ready in {seconds:g} s",
                       unready=True) from None
        if ready is None or "ready" not in ready:
            error = self._gone(self._words("unstarted"))
            self.stop()
            raise error
        self.pid = ready["ready"]
        self.rss = ready.get("rssMb")

    def _words(self, which: str, **values: Any) -> str:
        return getattr(self.service.words, which).format(label=self.label, name=Path(self.label).name, **values)

    def _gone(self, said: str, *, during: bool = False, code: int | None = None) -> Gone:
        """``said``, and its stderr as its service keeps it: a ``relay`` service's tail of the
        running request (its stderr thread allowed to finish reading what is left, never waited on
        for long), under ``WORKER_STDERR``; a ``keep`` service's last lines."""
        if self.service.stderr == "relay":
            if self.stderr_thread is not None:
                self.stderr_thread.join(timeout=1)
            with self.tail_lock:
                detail = self.tail.strip()
            text = f"{said}{WORKER_STDERR}{detail}" if detail else said
        else:
            with self.tail_lock:
                last = " | ".join(line for line in self.said[-SAID_LINES:] if line)
            text = f"{said}: {last or 'no word from it'}"
        return Gone(text, during=during, code=code)

    def _tell(self, message: dict[str, Any]) -> None:
        """``message`` to whoever the running request answers, while they are there. One gone
        (killed, or hung up) is dropped, and the process is read on all the same: one writing to a
        pipe nobody reads blocks, its request never ends, and the next lease waits on it for ever."""
        sink = self.sink
        if sink is None:
            return
        try:
            sink(message)
        except (OSError, ValueError):
            if self.sink is sink:
                self.sink = None

    def _stderr(self) -> None:
        stream = self.popen.stderr
        assert stream is not None
        relay = self.service.stderr == "relay"
        try:
            for line in iter(stream.readline, b""):
                text = line.decode("utf-8", "replace")
                with self.tail_lock:
                    if relay:
                        self.tail = (self.tail + text)[-TAIL_CHARACTERS:]
                    else:
                        self.said = [*self.said[-KEPT_LINES:], text.rstrip()]
                if relay:
                    self._tell({"log": text.rstrip("\n"), "stream": "model"})
        except (OSError, ValueError):
            pass
        finally:
            stream.close()  # the reader owns its pipe; never closed by a waiting caller

    def _reader(self) -> None:
        """Every frame as it comes (see the module): a request's ``log``, ``notice`` and ``progress``
        to whoever asked, an answer to a question to its waiter (and nobody's once it gave up), an
        event to its hook, anything else the running request's answer."""
        stream = self.popen.stdout
        assert stream is not None
        events = self.service.events
        try:
            while (found := frames.read(stream)) is not None:
                message, payload = found
                if "log" in message:
                    self._tell({"log": message["log"]})
                elif "notice" in message:  # said to the caller at once (``worker.kernel``)
                    self._tell({"log": message["notice"], "stream": "notice"})
                elif "progress" in message:
                    frame = self.progress = message["progress"]
                    self._tell({"progress": frame})
                    for follow in list(self.followers):
                        try:
                            follow({"progress": frame})
                        except (OSError, ValueError):
                            pass  # a waiting client gone: its request leaves on its own
                    try:
                        self.on_progress(self, frame)
                    except Exception:  # noqa: BLE001 - where a request is never fails it
                        pass
                elif isinstance(message.get("id"), str) and message["id"].startswith(QUESTION):
                    waiting = self.asked.pop(message["id"], None)
                    if waiting is not None:
                        waiting.put(message)
                elif (event := next((name for name in events if name in message), None)) is not None:
                    hook = self.on_event.get(event)
                    if hook is not None:
                        try:
                            hook(self, message[event], payload)
                        except Exception:  # noqa: BLE001 - a hook never fails the process's pipe
                            pass
                else:
                    if payload:
                        message["payload"] = payload
                    self.answers.put(message)
        except (OSError, ValueError, EOFError):
            pass
        finally:
            stream.close()
            self.answers.put(None)  # gone: every request it held settles
            for waiting in list(self.asked.values()):
                waiting.put(None)

    def _write(self, message: dict[str, Any], payload: bytes = b"") -> None:
        assert self.popen.stdin is not None
        with self.writing:
            frames.write(self.popen.stdin, message, payload)

    def request(self, message: dict[str, Any], sink: Callable[[dict[str, Any]], None] | None = None,
                payload: bytes = b"") -> dict[str, Any]:
        """One request (``payload`` after its line) and its answer, the payload it carried as its
        ``payload``; what the request says on the way -- its log, notices and progress -- to ``sink``.
        The request carries its supervisor's memory cap (``rssCapMb``), which the process retires itself
        by; the answer's ``rssMb`` is the process's memory from then on, and its ``retire`` retires it
        once it is let go. ``Gone`` when the process is gone: ``during`` when it exited while the
        request waited."""
        if self.memory is not None:
            message = {**message, "rssCapMb": self.memory()}
        with self.lock:
            if self.service.stderr == "relay":
                with self.tail_lock:
                    self.tail = ""
            self.sink = sink
            self.progress = None
            self.op, self.began = message.get("op"), time.time()
            try:
                self._write(message, payload)
                answer = self.answers.get()
                if answer is None:
                    code = self.popen.wait()
                    raise self._gone(self._words("exited", code=code), during=True, code=code)
                self.requests += 1
                self.rss = answer.pop("rssMb", self.rss)
                if answer.pop("retire", False):
                    self.retired = True
                return answer
            except OSError as error:
                raise self._gone(self._words("broken", error=error)) from error
            finally:
                self.sink = None
                self.op = self.began = None

    def question(self, message: dict[str, Any], timeout: float = 10.0) -> dict[str, Any] | None:
        """A side request, answered by its id even while a request runs: its answering frame;
        None when none comes within ``timeout`` seconds, or the process is gone."""
        ident = f"{QUESTION}{next(self.questions)}"
        waiting: "queue.Queue[Any]" = queue.Queue(1)
        self.asked[ident] = waiting
        try:
            self._write({**message, "id": ident})
            return waiting.get(timeout=timeout)
        except (OSError, ValueError, queue.Empty):
            return None
        finally:
            self.asked.pop(ident, None)

    def tell(self, message: dict[str, Any], payload: bytes = b"") -> None:
        """A side request answered by no request: any frame it brings is an event's."""
        self._write(message, payload)

    def alive(self) -> bool:
        return self.popen.poll() is None

    def stop(self) -> None:
        """Its stdin closed, so it exits; killed when it has not within ``STOP_SECONDS``."""
        try:
            if self.popen.stdin is not None:
                self.popen.stdin.close()
            self.popen.wait(timeout=STOP_SECONDS)
        except Exception:  # noqa: BLE001
            self.kill()

    def kill(self) -> None:
        """Killed, and its stdin let go (its readers close the rest at its end)."""
        try:
            self.popen.kill()
            self.popen.wait(timeout=STOP_SECONDS)
        except Exception:  # noqa: BLE001 - gone already, or past waiting for
            pass
        try:
            if self.popen.stdin is not None:
                self.popen.stdin.close()
        except OSError:
            pass


@dataclass(eq=False)
class _Ticket:
    """A lease waiting its turn: granted its key's live process (``process``), or a slot to start one
    in (``start``), retiring ``victim`` first."""

    service: Service
    key: str
    label: str
    environment: dict[str, str]
    cwd: str | None
    process: Any = None
    start: bool = False
    victim: Any = None
    python: str | None = None  # the caller's Python it names (``Service.interpreter``); None: the service's
    python_key: str | None = None  # that Python's environment, as the process key has it

    @property
    def granted(self) -> bool:
        return self.process is not None or self.start


# ``launch(service, key, label, environment, cwd)``, and ``python=`` the caller's Python for a lease that
# names one (``Service.interpreter``).
Launch = Callable[..., Any]


class Supervisor:
    """The daemon's processes, by the declarations of their ``services`` (see the module): at most
    ``cap`` alive of the services that count, but for watched ones. ``launch(service, key, label,
    environment, cwd)`` starts a process (``Process.start``; a test's fakes), told ``python=``
    too for a lease that names its caller's Python; ``watched``
    says whether a page watches what a process holds; ``drain`` is asked of each process of a service
    that drains before it is stopped; ``memory`` is the cap on their resident memory together (MiB,
    or None); ``on_progress`` and
    ``on_event`` the daemon's hooks, every process's."""

    def __init__(self, cap: int, services: tuple[Service, ...] | list[Service], *, launch: Launch | None = None,
                 watched: Callable[[Any], bool] = lambda _process: False,
                 drain: Callable[[Any], None] = lambda _process: None,
                 memory: Callable[[], float | None] = lambda: None,
                 on_progress: Callable[[Any, dict[str, Any]], None] = lambda _process, _frame: None,
                 on_event: dict[str, Callable[[Any, Any, bytes], None]] | None = None) -> None:
        self.cap = max(1, int(cap))
        self.services = {service.name: service for service in services}
        self.launch: Launch = launch or self._launch
        self.watched = watched
        self.drain = drain
        self.memory = memory
        self.on_progress = on_progress
        self.on_event = dict(on_event or {})
        self.lock = threading.Condition()
        self.table: dict[tuple[str, str], Any] = {}  # by service and key, in the order they started
        self.starting: set[tuple[str, str]] = set()  # each being started, holding its slot
        self.queue: list[_Ticket] = []
        self.retired: collections.deque = collections.deque(maxlen=RETIRED_KEPT)
        # The children being started -- spawned, not yet ready --, held from their spawn so ``stop`` takes
        # them too.
        self.spawning: set[Any] = set()
        self.stopped = False

    def _launch(self, service: Service, key: str, label: str, environment: dict[str, str], cwd: str | None,
                python: str | None = None) -> Process:
        """``Process.start``, the child held from its spawn (``spawning``): one spawned once the supervisor
        has stopped is killed at once."""
        held: list[Any] = []

        def spawned(popen: Any) -> None:
            with self.lock:
                if not self.stopped:
                    self.spawning.add(popen)
                    held.append(popen)
                    return
            popen.kill()

        try:
            # ``memory`` looked up at each request: a test replaces the supervisor's.
            return Process.start(service, key, label, environment, cwd, on_progress=self.on_progress,
                                 on_event=self.on_event, memory=lambda: self.memory(), spawned=spawned, python=python)
        finally:
            with self.lock:
                self.spawning.difference_update(held)

    def _key(self, service: Service, key: str, python_key: str | None = None) -> str:
        """A process's key in the table: its key (a path normcased), and the key of the Python a lease
        named for it, its caller's (``Service.interpreter``), with it: one key from two environments is
        two processes."""
        found = os.path.normcase(key) if service.key == "path" else key
        return found if python_key is None else f"{found}{INTERPRETER}{python_key}"

    @staticmethod
    def _bound(service: Service, environment: dict[str, str]) -> dict[str, str]:
        """What of ``environment`` a process started in it is bound to (``Service.binding``)."""
        return {name: environment.get(name, "") for name in service.binding}

    # --- leases ------------------------------------------------------------------------------

    def lease(self, service: str, key: str, environment: dict[str, str], cwd: str | None = None,
              label: str | None = None, python: str | None = None, python_key: str | None = None) -> Any:
        """The process of ``service`` for ``key`` (a script's path, a document's id; ``label`` what it
        is said as, the key by default), for one request, waiting its turn (see the module): started
        when there is none. ``release`` it after. ``python``: the caller's Python (a service whose
        ``interpreter`` is ``"lease"``), which a process started for the lease runs, and ``python_key`` the
        key of its environment (by default the Python itself): a key of its own."""
        declared = self.services[service]
        if python is not None and declared.interpreter != "lease":
            raise ValueError(f"a {service} runs its own environment's Python: a lease names none")
        python_key = (python_key or python) if python is not None else None
        ticket = _Ticket(declared, self._key(declared, key, python_key), key if label is None else label, environment,
                         cwd, python=python, python_key=python_key)
        with self.lock:
            self.queue.append(ticket)
            self._grant()
            while not ticket.granted:
                self.lock.wait()
        if ticket.process is not None:
            return ticket.process
        if ticket.victim is not None:
            # The process whose slot this is exits before the new one starts.
            self._retire(ticket.victim)
        place = (service, ticket.key)
        try:
            process = self.launch(declared, ticket.key, ticket.label, environment, cwd,
                                  **({"python": python} if python is not None else {}))
        except BaseException:
            with self.lock:
                self.starting.discard(place)
                self._grant()
            raise
        if python is not None:
            process.python_key = python_key
        with self.lock:
            self.starting.discard(place)
            process.leased, process.since = True, time.monotonic()
            self.table[place] = process
        return process

    def release(self, process: Any) -> None:
        """A request is done with its process: it is free again, or retired when it is gone or said it
        is over its memory cap; then the processes' memory is held to its cap (``shed``)."""
        gone = False
        with self.lock:
            process.leased, process.used = False, time.monotonic()
            if process.retired or not process.alive():
                place = (process.service.name, process.key)
                gone = self.table.get(place) is process
                if gone:
                    del self.table[place]
                    self._note(process, "RSS" if process.retired else "exited")
            self._grant()
        if gone:
            self._retire(process)
        self.shed()

    def _retire(self, process: Any, drain: bool = True) -> None:
        """A process retired: drained when its service drains, then stopped. A drain that fails stops it all
        the same."""
        if drain and process.service.drain:
            try:
                self.drain(process)
            except Exception:  # noqa: BLE001 - what the drain could not take is evicted
                pass
        process.stop()

    def follow(self, service: str, key: str, send: Callable[[dict[str, Any]], None], op: str,
               python_key: str | None = None) -> tuple[Any, float] | None:
        """The process of ``key`` (of the caller's Python's ``python_key``, where the lease names one)
        while a lease holds it running an ``op`` request, and when that began (``time.time()``): ``send``
        follows its progress frames from now on (``Process.followers``) until the follower takes it off.
        None when none runs."""
        declared = self.services[service]
        with self.lock:
            process = self.table.get((service, self._key(declared, key, python_key)))
            if process is None or not process.leased or process.op != op or process.began is None:
                return None
            process.followers.append(send)
            return process, process.began

    def live(self, service: str, key: str, python_key: str | None = None) -> Any:
        """The live process of ``service`` for ``key`` (of the caller's Python's ``python_key``, where a
        lease named one), busy or idle; None when there is none."""
        declared = self.services[service]
        with self.lock:
            return self.table.get((service, self._key(declared, key, python_key)))

    def holds(self, process: Any) -> bool:
        """Whether ``process`` is live in the supervisor: neither retired nor gone."""
        with self.lock:
            return (self.table.get((process.service.name, process.key)) is process and not process.retired
                    and process.alive())

    def free_for(self, process: Any) -> float | None:
        """How long ``process`` has been free with no lease waiting for it, in seconds; None while a
        lease holds it or waits for it."""
        with self.lock:
            if process.leased or any(ticket.service is process.service and ticket.key == process.key
                                     and not ticket.granted for ticket in self.queue):
                return None
            return time.monotonic() - process.used

    def processes(self, service: str) -> list[Any]:
        """The live processes of ``service``, in the order they started."""
        with self.lock:
            return [process for (name, _key), process in self.table.items() if name == service]

    def waiting(self, service: str) -> int:
        """The leases of ``service`` waiting their turn."""
        with self.lock:
            return sum(not ticket.granted for ticket in self.queue if ticket.service.name == service)

    # --- memory ------------------------------------------------------------------------------

    def _resident(self) -> float:
        """The resident memory of every live process, in MiB, as each last said it (call with the lock
        held)."""
        return float(sum(process.rss or 0 for process in self.table.values()))

    def resident(self) -> float:
        with self.lock:
            return self._resident()

    def _rank(self, process: Any) -> int:
        """Its order when memory is shed and at the count cap: its service's rank, or its watched rank
        while a page watches it (call with the lock held: ``watched`` takes the server's watch lock)."""
        service = process.service
        if service.watched_rank is not None and self.watched(process):
            return service.watched_rank
        return service.rank

    def shed(self, pressure: bool = False) -> list[Any]:
        """The memory rule: while the processes' resident memory is over its cap -- under the system's
        memory pressure (``pressure``), over ``PRESSURE_SHARE`` of it -- idle processes are retired, in the
        order their declarations rank them, least recently used first within a rank. A busy process is
        never retired, nor one that never said its memory. Each is drained first when its service drains.
        The retired."""
        cap = self.memory()
        with self.lock:
            if self.stopped or cap is None:
                return []
            total = self._resident()
            target = cap * (PRESSURE_SHARE if pressure else 1.0)
            candidates = [(self._rank(process), process.used, process) for process in self.table.values()
                          if not process.leased]
            chosen: list[Any] = []
            for _rank, _used, held in sorted(candidates, key=lambda row: row[:2]):
                if total <= target:
                    break
                if not held.rss:
                    continue  # unmeasured: retiring it frees nothing the rule can count
                total -= held.rss
                chosen.append(held)
                del self.table[(held.service.name, held.key)]
                self._note(held, "pressure" if pressure else "RSS")
            if chosen:
                self._grant()
        for held in chosen:
            self._retire(held)
        return chosen

    # --- the grant ---------------------------------------------------------------------------

    def _occupied(self) -> int:
        """The slots of the count cap held (call with the lock held): every counted service's live
        processes, and those being started."""
        occupied = sum(1 for process in self.table.values() if process.service.counted)
        return occupied + sum(1 for name, _key in self.starting if self.services[name].counted)

    def _note(self, process: Any, reason: str) -> None:
        """A retirement, listed in ``status`` when its service notes them."""
        noted = process.service.noted
        if noted is None:
            return
        name, count = noted
        self.retired.appendleft({name: process.label, "pid": getattr(process, "pid", None),
                                 count: getattr(process, "requests", 0), "reason": reason, "at": time.time()})

    def _grant(self) -> None:
        """Grant what the waiting leases can have, in the order they came (call with the lock held):
        see the module."""
        for place, process in list(self.table.items()):
            if not process.leased and not process.alive():
                del self.table[place]
                self._note(process, "exited")
        wanted = {(ticket.service.name, ticket.key) for ticket in self.queue}
        taken: set[int] = set()  # the processes this pass granted or retired
        blocked = False  # a counted lease before found no slot: no later one takes one
        granted = False
        for ticket in self.queue:
            service = ticket.service
            place = (service.name, ticket.key)
            bound = self._bound(service, ticket.environment)
            process = self.table.get(place)
            if process is not None and self._bound(service, process.environment) == bound:
                if not process.leased and id(process) not in taken:
                    process.leased, process.since = True, time.monotonic()
                    ticket.process = process
                    taken.add(id(process))
                    granted = True
                continue
            if place in self.starting:
                continue  # its key's process is being started: it waits for that one
            if process is not None:
                # Its key's process, of another binding: replaced in its slot once it is free.
                if not process.leased and id(process) not in taken:
                    del self.table[place]
                    self._note(process, "environment")
                    self._slot(ticket, process)
                    taken.add(id(process))
                    granted = True
                continue
            if service.counted and blocked:
                continue
            if not service.counted or self._occupied() < self.cap:
                self._slot(ticket, None)
                granted = True
                continue
            idle = [held for held in self.table.values()
                    if held.service.counted and not held.leased and id(held) not in taken]
            if not idle:
                blocked = True
                continue
            # Connected means warm: a process whose document a page watches is never the count cap's
            # victim. With only watched idle ones the cap is exceeded instead, so a request never waits
            # on an open page and never costs one its warm process.
            unwatched = [held for held in idle if not (held.service.watched_rank is not None and self.watched(held))]
            if not unwatched:
                self._slot(ticket, None)
                granted = True
                continue
            victim = min(unwatched, key=lambda held: (held.service.rank, (held.service.name, held.key) in wanted,
                                                      held.used))
            del self.table[(victim.service.name, victim.key)]
            self._note(victim, "LRU")
            self._slot(ticket, victim)
            taken.add(id(victim))
            granted = True
        if granted:
            self.queue = [ticket for ticket in self.queue if not ticket.granted]
            self.lock.notify_all()

    def _slot(self, ticket: _Ticket, victim: Any) -> None:
        ticket.start, ticket.victim = True, victim
        self.starting.add((ticket.service.name, ticket.key))

    def stop(self) -> None:
        """Every process stopped, never drained: the daemon is stopping (its documents saved first,
        ``cache.Cache.final``). A child still being started is killed: it reads nothing until it is ready,
        and would outlive the daemon until then."""
        with self.lock:
            self.stopped = True
            every = list(self.table.values())
            starting = list(self.spawning)
            self.table.clear()
        for popen in starting:
            try:
                popen.kill()
            except OSError:
                pass
        for process in every:
            process.stop()
