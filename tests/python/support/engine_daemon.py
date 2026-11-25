"""Running a command that reaches the engine daemon so that, when it does not finish, the test
says why.

A command starts no server (``cad server start`` alone does, ``client.start``): the runner starts one
for each test file (``scripts/test/unittest_files.py``), and ``start`` one for a test's own engine folder.
``watched(env, cleanup)`` adds a journal to a test's environment, and starts a server there with it:
every Python process the test runs and the server starts -- the command, the daemon, the daemon's
workers -- records itself there (``engine_journal/sitecustomize.py``). ``run``/``communicate`` stand in for
``subprocess.run``/``Popen.communicate`` with a timeout, and fail early, with the journal,
the state folder and the command's output in the message, when:

- the command has exited but its output stays open ``HELD_SECONDS``: a process it started
  holds the command's stdout or stderr, so a plain ``communicate`` would wait for that one;
- the timeout passes.

The message counts the daemons started and says whether the first one ever listened.
A live caller may still be importing the kernel or building its input shape before it
asks for a daemon; absence of a daemon is not evidence that the command has hung."""

from __future__ import annotations

import json
import locale
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence

SITE = Path(__file__).resolve().parent / "engine_journal"
JOURNAL = "CAD_TEST_JOURNAL"
HELD_SECONDS = 10.0
TIMEOUT_SECONDS = 300.0
STACK_LINES = 30  # a thread's innermost frames: where it waits
# The version a test's interpreter is registered as (``register``): a name no release takes, which
# ``cad.engine.places.registered`` passes over, so the engine and its workers go by the release
# declared beside the code, as they would with no record; and What's new
# (``cad_server.whats_new``) too, so a test's fresh device is a new person's, shown no notes.
TEST_INSTALLATION = "0.0.0+test"


def register(state: str | os.PathLike, python: str | None = None, prefix: str | None = None) -> bool:
    """The interpreter ``python`` (this one), of the environment ``prefix`` (this one's), registered as
    the current installation in the state folder ``state``, as a real installation registers itself
    (``cad_server._internal.installations``): its record (``installations/<version>.json``: its Python,
    its ``cad`` console script and its environment) and ``installations/current``, which a test's device
    reads as a person's would. An environment with no ``cad`` console script -- an
    interpreter that reads the packages from ``PYTHONPATH`` -- gets one beside the record, which runs the
    server's command with that interpreter. The standard library alone: the runner registers each file's
    state folder before the file imports anything (``scripts/test/unittest_files.py``). True; raises
    where it cannot, so nothing goes on unregistered."""
    python = os.path.abspath(python or sys.executable)
    prefix = os.path.abspath(prefix or sys.prefix)
    if not os.path.isfile(python):
        raise FileNotFoundError(f"no interpreter to register: {python}")
    windows = os.name == "nt"
    if prefix == os.path.abspath(sys.prefix) and sys.prefix == sys.base_prefix:
        scripts = sysconfig.get_path("scripts")  # not a virtual environment: the interpreter's own folder
    else:
        scripts = os.path.join(prefix, "Scripts" if windows else "bin")
    folder = Path(state) / "installations"
    folder.mkdir(parents=True, exist_ok=True)
    console = os.path.join(scripts, "cad.exe" if windows else "cad")
    if not os.path.isfile(console):
        stub = folder / (f"{TEST_INSTALLATION}-cad.cmd" if windows else f"{TEST_INSTALLATION}-cad")
        stub.write_text(f'@"{python}" -m cad_server.cli %*\r\n' if windows else
                        f'#!/bin/sh\nexec "{python}" -m cad_server.cli "$@"\n', encoding="utf-8")
        stub.chmod(0o755)
        console = str(stub)
    record = {"version": TEST_INSTALLATION, "python": python, "cad": os.path.abspath(console), "prefix": prefix,
              "registered": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    # One key a line, as an installation writes it: the ``cad`` command's sh reads the python's line.
    (folder / f"{TEST_INSTALLATION}.json").write_text(json.dumps(record, indent=1, sort_keys=True) + "\n",
                                                      encoding="utf-8")
    (folder / "current").write_text(TEST_INSTALLATION, encoding="utf-8")
    return True


def isolate(cleanup: Callable[..., Any], *, started: bool = True) -> dict[str, str]:
    """An engine, a state and a cache folder of the caller's own (``CAD_ENGINE_DIR``,
    ``CAD_STATE_DIR``, ``CAD_CACHE_DIR``) in ``os.environ``, and a server started there -- but ``started`` false,
    for a caller that starts its own with an environment of its own (``watched``) --, until ``cleanup`` (a
    module's ``unittest.addModuleCleanup``, a test's ``addCleanup``) stops the server running there, puts the
    environment back and removes them: so the server, and every environment built from ``os.environ`` after,
    runs, records and caches its documents there, never in the developer's. The state folder registers this
    interpreter as its current installation (``register``). The runner gives each file its own
    (``scripts/test/unittest_files.py``); this is the same for a file run directly. The variables set."""
    from unittest import mock

    folder = tempfile.mkdtemp(prefix="cadgen-test-")
    # A short folder of its own for the engine's door: a socket's path has a length limit on POSIX.
    engine = tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)
    given = {"CAD_ENGINE_DIR": engine, "CAD_STATE_DIR": os.path.join(folder, "state"),
             "CAD_CACHE_DIR": os.path.join(folder, "cache")}
    register(given["CAD_STATE_DIR"])
    patch = mock.patch.dict(os.environ, given)
    patch.start()
    cleanup(shutil.rmtree, folder, True)
    cleanup(shutil.rmtree, engine, True)
    cleanup(patch.stop)
    cleanup(_stop_engine, engine)
    if started:
        start()
    return given


def start(env: dict[str, str] | None = None, cleanup: Callable[..., Any] | None = None) -> None:
    """A server started where ``env`` -- this process's environment, by default -- names the engine's folder
    (``CAD_ENGINE_DIR``: never the developer's own, where none is named), with that environment, by a process of
    its own as ``cad server start`` starts one (``client.start``: so the server is no child of this one), and
    stopped by ``cleanup``; nothing where one runs there already (the runner's, or one a test started)."""
    from unittest import mock

    from cad.engine import client
    from tests.python.support.paths import SOURCE_PATH

    given = dict(os.environ if env is None else env)
    engine = given["CAD_ENGINE_DIR"]
    with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": engine}):
        found = client._connect()
    if found is not None:
        found.close()
        return  # one runs there already
    code = "from cad.engine import client\nif client.request({'op': 'pid'}, start=False) is None:\n    client.start()"
    path = os.pathsep.join(item for item in (SOURCE_PATH, given.get("PYTHONPATH", "")) if item)
    done = subprocess.run([sys.executable, "-P", "-c", code], env={**given, "PYTHONPATH": path}, capture_output=True,
                          text=True, timeout=TIMEOUT_SECONDS)
    if done.returncode:
        raise AssertionError(f"no server started in {engine}: {done.stdout}{done.stderr}")
    if cleanup is not None:
        cleanup(_stop_engine, engine)


def _stop_engine(engine: str) -> None:
    """The engine in folder ``engine`` stopped, when one runs there."""
    if not any(name.endswith((".door", ".port")) for name in (os.listdir(engine) if os.path.isdir(engine) else ())):
        return
    from unittest import mock

    from cad.engine import api

    with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": engine}):
        api.stop()


def unwritable(folder: Path | str) -> str:
    """A cache folder (``CAD_CACHE_DIR``) no one can write, under ``folder``: a file in its place,
    which refuses a folder below it on every platform and to root too. The engine keeps no document
    there and does everything else as ever (an unwritable cache saves nothing): what a test names
    whose restart must find no document kept. Its path."""
    path = Path(folder) / "cache-unwritable"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return str(path)


def watched(env: dict[str, str], cleanup: Callable[..., Any], *, started: bool = True) -> dict[str, str]:
    """``env`` with a journal of its own, and a server started with it where ``env`` names the engine's
    folder (``start``) -- but ``started`` false, for a test of a server's start or of none running;
    ``cleanup`` (a test's ``addCleanup`` or ``addClassCleanup``) stops the server and removes the journal. A
    state folder ``env`` names (``CAD_STATE_DIR``) with no current installation registers this interpreter as
    its current one (``register``), as the runner's and ``isolate``'s are."""
    state = env.get("CAD_STATE_DIR")
    if state and not os.path.exists(os.path.join(state, "installations", "current")):
        register(state)
    folder = tempfile.mkdtemp(prefix="engine-journal-")
    cleanup(shutil.rmtree, folder, True)
    path = os.pathsep.join(item for item in (str(SITE), env.get("PYTHONPATH", "")) if item)
    journaled = {**env, "PYTHONPATH": path, JOURNAL: folder}
    if started and journaled.get("CAD_ENGINE_DIR"):
        start(journaled, cleanup)
    return journaled


def run(command: Sequence[str], *, env: dict[str, str], timeout: float = TIMEOUT_SECONDS, input: str | None = None,
        **options: Any) -> subprocess.CompletedProcess:
    """``subprocess.run(command, capture_output=True, text=True, timeout=timeout, input=input)``,
    watched."""
    process = subprocess.Popen(list(command), env=env, stdin=subprocess.DEVNULL if input is None else subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
    if input is not None:
        assert process.stdin is not None
        with process.stdin:
            process.stdin.write(input.encode())
    out, err = communicate(process, env, timeout)
    return subprocess.CompletedProcess(process.args, process.returncode, out, err)


def communicate(process: subprocess.Popen, env: dict[str, str],
                timeout: float = TIMEOUT_SECONDS) -> tuple[str, str]:
    """``process.communicate(timeout=timeout)`` for a process started with both outputs piped,
    watched; the outputs as text, whether or not the process was started with ``text=True``."""
    started = time.monotonic()
    read: dict[str, list[bytes]] = {"out": [], "err": []}  # as it comes: a command that hangs has said this much

    def drain(name: str, stream: Any) -> None:
        while chunk := (stream.buffer.read1(65536) if hasattr(stream, "buffer") else stream.read1(65536)):
            read[name].append(chunk)

    readers = [threading.Thread(target=drain, args=(name, stream), daemon=True)
               for name, stream in (("out", process.stdout), ("err", process.stderr))]
    for reader in readers:
        reader.start()
    exited: float | None = None
    while True:
        now = time.monotonic()
        if process.poll() is not None:
            exited = exited or now
            if not any(reader.is_alive() for reader in readers):
                for stream in (process.stdout, process.stderr):
                    stream.close()
                if process.returncode:
                    _say_stacks(env)
                return _text(b"".join(read["out"])), _text(b"".join(read["err"]))
            if now - exited > HELD_SECONDS:
                why = (f"exited with {process.returncode} but its output stayed open {HELD_SECONDS:.0f} s: a process "
                       "it started holds its stdout or stderr")
                break
        elif now - started > timeout:
            why = f"did not finish in {timeout:.0f} s"
            break
        time.sleep(0.2)
    process.kill()
    for reader in readers:
        reader.join(5)
    raise AssertionError(f"{process.args!r} {why}.\n" + report(env, started, read))


def stacks(env: dict[str, str]) -> str:
    """The stacks the journal holds of every process that died and of each daemon (its own as it
    stood): a native fault's (``faulthandler.enable``) and the last periodic dump. Empty when none
    wrote any -- a command that exits failing on its own (a refusal) leaves none."""
    folder = env.get(JOURNAL)
    lines: list[str] = []
    for role, pid in sorted(_processes(env)):
        path = Path(folder or "") / f"{role}-{pid}.stacks.txt"
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text and (role == "daemon" or not _alive(pid)):
            lines.append(f"--- {role} {pid} ({'alive' if _alive(pid) else 'gone'}): its stacks")
            lines.extend(text.splitlines()[-200:])
    return "\n".join(lines)


def _say_stacks(env: dict[str, str]) -> None:
    """A failed command's stacks, on the test's stderr, before the journal goes with the test."""
    said = stacks(env)
    if said:
        import sys

        print(f"engine journal stacks after a failed command:\n{said}", file=sys.stderr)


def _text(data: bytes) -> str:
    """A command's output as its writer wrote it, with universal newlines: UTF-8, which the ``cad`` command and
    ``cad run``'s program write to a pipe on every system; else, for a plain Python program's (a model script run by
    itself, ``python -m cad_server.engine``), the locale's encoding, as ``text=True`` reads it (cp1252 on the Windows
    runner, where ``·`` is 0xB7, no UTF-8 on its own)."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode(locale.getpreferredencoding(False), errors="replace")
    return text.replace("\r\n", "\n")


def _state(env: dict[str, str]) -> Path | None:
    folder = env.get("CAD_ENGINE_DIR")
    return Path(folder) if folder else None


def _processes(env: dict[str, str]) -> list[tuple[str, int]]:
    folder = env.get(JOURNAL)
    if not folder or not os.path.isdir(folder):
        return []
    found = []
    for path in Path(folder).glob("*.txt"):
        role, _, pid = path.stem.partition("-")
        if pid.isdigit():
            found.append((role, int(pid)))
    return found


def _alive(pid: int) -> bool:
    if os.name == "nt":
        return not _windows_exited(pid, 0)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _windows_exited(pid: int, milliseconds: int) -> bool:
    """The native termination signal, not an exit-code query: a failed query never means gone.
    Holding the handle throughout the wait also keeps the PID from being reused underneath it."""
    import _winapi

    try:
        handle = _winapi.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
    except OSError as error:
        if error.winerror == 87:  # ERROR_INVALID_PARAMETER: this PID no longer exists
            return True
        raise
    try:
        return _winapi.WaitForSingleObject(handle, milliseconds) == _winapi.WAIT_OBJECT_0
    finally:
        _winapi.CloseHandle(handle)


def await_exit(pid: int | None, within: float = 30.0) -> bool:
    """Whether the stopped engine's process ``pid`` has exited, waited for up to ``within`` s. Its lock
    goes before its process does (``client.wait_gone``), and on Windows that process stands in the
    parent of the engine's folder (``client._working_folder``) -- a test's temporary folder, which
    cannot be removed while it does. On POSIX, where the folder can go and an unreaped child would
    look alive, nothing is waited for."""
    if os.name != "nt" or pid is None:
        return True
    return _windows_exited(pid, max(0, int(within * 1000)))


def survivors(env: dict[str, str], within: float = 60.0) -> list[tuple[str, int]]:
    """Every process the journal of ``env`` names -- the engine daemon, its workers, readers and
    render processes, the commands -- awaited gone for up to ``within`` s once the engine was asked
    to stop; those still alive then are killed, so a failing test leaves none behind. The ones it
    found alive, as ``(role, pid)``: a test asserts there are none."""
    import signal

    deadline = time.monotonic() + within
    while (alive := [(role, pid) for role, pid in sorted(_processes(env)) if _alive(pid)]) \
            and time.monotonic() < deadline:
        time.sleep(0.05)
    for _role, pid in alive:
        try:
            os.kill(pid, signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM)
        except OSError:
            pass
    return alive


def engine_pid(env: dict[str, str]) -> int | None:
    """The pid of the engine ``env`` names, or None when none answers."""
    from unittest import mock

    from cad.engine.client import request

    with mock.patch.dict(os.environ, env, clear=True):
        answer = request({"op": "pid"}, start=False)
    return answer.get("pid") if answer else None


def report(env: dict[str, str], started: float, read: dict[str, list[bytes]]) -> str:
    """The daemons started and whether the first listened, every journal entry and stack dump,
    the state folder, and the command's output so far."""
    zero = time.time() - (time.monotonic() - started)
    lines = []
    folder = env.get(JOURNAL)
    entries: list[tuple[str, int, list[str]]] = []
    if folder and os.path.isdir(folder):
        for role, pid in _processes(env):
            text = (Path(folder) / f"{role}-{pid}.txt").read_text(encoding="utf-8", errors="replace")
            entries.append((role, pid, text.splitlines()))
    first = lambda item: float(item[2][0].split(" ", 1)[0]) if item[2] else 0.0  # noqa: E731
    entries.sort(key=first)
    daemons = [entry for entry in entries if entry[0] == "daemon"]
    listened = [entry for entry in daemons if any(" listening" in line for line in entry[2])]
    lines.append(f"daemons started: {len(daemons)}; listened: {len(listened)}; first listened: "
                 + ("none started" if not daemons else "yes" if daemons[0] in listened else "no"))
    for role, pid, text in entries:
        lines.append(f"--- {role} {pid} ({'alive' if _alive(pid) else 'gone'})")
        for line in text:
            stamp, _, rest = line.partition(" ")
            try:
                lines.append(f"  {float(stamp) - zero:+8.2f}s {rest}")
            except ValueError:
                lines.append(f"  {line}")
        stacks = Path(folder or "") / f"{role}-{pid}.stacks.txt"
        if stacks.is_file() and stacks.stat().st_size:
            lines.append("  stacks (the last dump; each thread's innermost frames first):")
            dumps = stacks.read_text(encoding="utf-8", errors="replace").split("Timeout (")
            for thread in ("Timeout (" + dumps[-1]).split("\n\n"):
                frames = thread.strip("\n").splitlines()
                lines.extend("    " + line for line in frames[:STACK_LINES])
                if len(frames) > STACK_LINES:
                    lines.append(f"    ... {len(frames) - STACK_LINES} outer frames")
    state = _state(env)
    if state is not None:
        listing = sorted(state.iterdir()) if state.is_dir() else []
        lines.append(f"--- state {state}: " + (", ".join(f"{p.name} ({p.stat().st_size} B)" for p in listing
                                                          if p.is_file()) or "empty"))
        for port in state.glob("*.port"):
            lines.append(f"  {port.name}: {port.read_text(encoding='utf-8', errors='replace').split()[:1]}")
    for name in ("out", "err"):
        lines.append(f"--- std{name} (the last 3000 characters)")
        lines.append(_text(b"".join(list(read.get(name, []))))[-3000:])
    return "\n".join(lines)


def reap(process: subprocess.Popen) -> None:
    """End ``process`` and let go of its pipes without reading them: a process it started may
    hold them open, and a ``communicate`` would wait for that one."""
    if process.poll() is None:
        process.kill()
    process.wait(30)
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
