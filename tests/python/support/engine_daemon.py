"""Running a command that reaches the engine daemon so that, when it does not finish, the test
says why.

``watched(env, cleanup)`` adds a journal to a test's environment: every Python process the
command starts -- the command, the daemon it starts, the daemon's workers -- records itself
there (``engine_journal/sitecustomize.py``). ``run``/``communicate`` stand in for
``subprocess.run``/``Popen.communicate`` with a timeout, and fail early, with the journal,
the state folder and the command's output in the message, when:

- the command has exited but its output stays open ``HELD_SECONDS``: a process it started
  holds the command's stdout or stderr, so a plain ``communicate`` would wait for that one;
- the timeout passes.

The message counts the daemons started and says whether the first one ever listened.
A live caller may still be importing the kernel or building its input shape before it
asks for a daemon; absence of a daemon is not evidence that the command has hung."""

from __future__ import annotations

import locale
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence

SITE = Path(__file__).resolve().parent / "engine_journal"
JOURNAL = "CADGEN_TEST_JOURNAL"
HELD_SECONDS = 10.0
TIMEOUT_SECONDS = 300.0
STACK_LINES = 30  # a thread's innermost frames: where it waits


def isolate(cleanup: Callable[..., Any]) -> dict[str, str]:
    """An engine, a state and a cache folder of the caller's own (``CADGEN_ENGINE_DIR``,
    ``CADGEN_STATE_DIR``, ``CADGEN_CACHE_DIR``) in ``os.environ`` until ``cleanup`` (a module's
    ``unittest.addModuleCleanup``, a test's ``addCleanup``) stops an engine started there, puts the
    environment back and removes them: so an engine a test starts, and every environment built from
    ``os.environ`` after, runs, records and caches its documents there, never in the developer's.
    The runner gives each file its own (``scripts/test/unittest_files.py``); this is the same for a
    file run directly. The variables set."""
    from unittest import mock

    folder = tempfile.mkdtemp(prefix="cadgen-test-")
    # A short folder of its own for the engine's door: a socket's path has a length limit on POSIX.
    engine = tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)
    given = {"CADGEN_ENGINE_DIR": engine, "CADGEN_STATE_DIR": os.path.join(folder, "state"),
             "CADGEN_CACHE_DIR": os.path.join(folder, "cache")}
    patch = mock.patch.dict(os.environ, given)
    patch.start()
    cleanup(shutil.rmtree, folder, True)
    cleanup(shutil.rmtree, engine, True)
    cleanup(patch.stop)
    cleanup(_stop_engine, engine)
    return given


def _stop_engine(engine: str) -> None:
    """The engine in folder ``engine`` stopped, when one runs there."""
    if not any(name.endswith((".door", ".port")) for name in os.listdir(engine)):
        return
    from unittest import mock

    from cadgen.engine import api

    with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": engine}):
        api.stop()


def unwritable(folder: Path | str) -> str:
    """A cache folder (``CADGEN_CACHE_DIR``) no one can write, under ``folder``: a file in its place,
    which refuses a folder below it on every platform and to root too. The engine keeps no document
    there and does everything else as ever (an unwritable cache saves nothing): what a test names
    whose restart must find no document kept. Its path."""
    path = Path(folder) / "cache-unwritable"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return str(path)


def watched(env: dict[str, str], cleanup: Callable[..., Any]) -> dict[str, str]:
    """``env`` with a journal of its own; ``cleanup`` (a test's ``addCleanup`` or
    ``addClassCleanup``) removes it."""
    folder = tempfile.mkdtemp(prefix="engine-journal-")
    cleanup(shutil.rmtree, folder, True)
    path = os.pathsep.join(item for item in (str(SITE), env.get("PYTHONPATH", "")) if item)
    return {**env, "PYTHONPATH": path, JOURNAL: folder}


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
    """As ``text=True`` reads a command's output: in the locale's encoding (cp1252 on the Windows
    runner, where cadgen's ``·`` is 0xB7), with universal newlines."""
    return data.decode(locale.getpreferredencoding(False), errors="replace").replace("\r\n", "\n")


def _state(env: dict[str, str]) -> Path | None:
    folder = env.get("CADGEN_ENGINE_DIR")
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

    from cadgen.engine.client import request

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
