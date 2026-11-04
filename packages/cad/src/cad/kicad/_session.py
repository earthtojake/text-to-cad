"""``@kicad_pcb("board.kicad_pcb")``: a persistent board script, run through KiCad's IPC API.

The board file is the source; the decorated function edits it::

    from cad import dxf, kicad_pcb, step

    @step("board.step")                    # the saved board's STEP, by kicad-cli (--subst-models)
    @dxf("board.dxf")                      # its outline and holes (a @glb stacks the same way)
    @kicad_pcb("board.kicad_pcb")          # beside the script, as the engine's decorators' paths are
    def board(b):                          # b: KiPy's open Board (kicode.board.Board)
        ...

    if __name__ == "__main__":
        board()

A call runs it: a private, headless ``kicad-cli api-server --socket <path> <board>`` (the finder and the
private homes of ``_program``: kicode's kicad-cli and ``kicode.environment``; one ``CAD_KICAD_CLI`` names
without ``api-server``, any stable KiCad's for now, refused before it starts; ``--socket`` takes a plain
path, KiPy the ``ipc://`` form), KiPy (kicode's, ``kicode.KiCad``) connected to it (ready
when it answers, never when a path appears: Windows serves a named pipe, no file), the function handed the
open board, the board saved when the function returns and nothing saved when it raises; then the server
stopped and its folder removed, whatever happened. The files stacked on it (``@step``, ``@glb``, ``@dxf``)
are written from the saved board afterwards, each by its producer (``cad.registry``).

KiPy's ``KiCad.check_version()`` is never called: kicode's KiPy is the one built with its kicad-cli, and a
kicad-cli ``CAD_KICAD_CLI`` names may be another nightly's, which KiPy still reads and edits. Upstream
``kipy`` is never imported: it and kicode register the same protobuf files and cannot share a process.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from pkgutil import resolve_name
from typing import Any

from ._program import (KicadRunError, check_api_server, check_version, find_kicad_cli, kicad_version, private_run,
                       quiet)

__all__ = ["BoardRun", "BoardScript", "declare", "run"]

# How long kicad-cli api-server may take to answer for its board, and to stop when asked.
START_SECONDS = 120.0
STOP_SECONDS = 10.0
_POLL = 0.05


@dataclass
class BoardScript:
    """A function ``@kicad_pcb`` declared: the board it edits and the files stacked on it."""

    function: Callable[[Any], Any]
    board: Path
    outputs: list[tuple[str, Path]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.__name__ = getattr(self.function, "__name__", "board")
        self.__doc__ = getattr(self.function, "__doc__", None)

    def __call__(self) -> "BoardRun":
        return run(self)


@dataclass(frozen=True)
class BoardRun:
    """What a run of a board script did: the board it saved and the files it wrote from it."""

    board: Path
    written: tuple[Path, ...]


def _beside(function: Callable[..., Any], out: Any) -> Path:
    """``out`` resolved beside the script that defines ``function``, as the engine's decorators resolve theirs."""
    path = Path(os.fspath(out)).expanduser()
    if path.is_absolute():
        return path
    source = getattr(getattr(function, "__code__", None), "co_filename", None)
    folder = Path(source).resolve().parent if source and os.path.isfile(source) else Path.cwd()
    return folder / path


def declare(out: Any, *, name: str | None = None) -> Callable[[Callable[[Any], Any]], BoardScript]:
    """``@kicad_pcb(out)``: the function edits the board at ``out``, a ``.kicad_pcb`` beside its script."""
    if out is None or not isinstance(out, (str, os.PathLike)) or not os.fspath(out):
        raise TypeError("@kicad_pcb requires the board's path: @kicad_pcb(\"board.kicad_pcb\")")
    if Path(os.fspath(out)).suffix.lower() != ".kicad_pcb":
        raise ValueError(f"@kicad_pcb(out=...): the file must end in .kicad_pcb, not {os.fspath(out)!r}")
    if name is not None:
        raise TypeError("@kicad_pcb takes no name=: a board script is its board, not a model")

    def apply(function: Callable[[Any], Any]) -> BoardScript:
        if isinstance(function, BoardScript) or not callable(function):
            raise TypeError("@kicad_pcb decorates a function of one argument, the open board")
        return BoardScript(function, _beside(function, out))

    return apply


def declare_output(kind: str, script: BoardScript, out: Any) -> BoardScript:
    """A file stacked on a board script (``@step("board.step")``, ``@glb``, ``@dxf``), written from its saved
    board. Its path ends in its type's extension, as the engine's decorators check theirs."""
    from cad.registry import DOCUMENT_TYPES

    extensions = DOCUMENT_TYPES[kind].extensions
    if Path(os.fspath(out)).suffix.lower() not in extensions:
        raise ValueError(f"@{kind}(out=...): the file must end in {' or '.join(extensions)}, not {os.fspath(out)!r}")
    path = _beside(script.function, out)
    if any(existing == kind for existing, _ in script.outputs):
        raise TypeError(f"board script {script.__name__!r} declares @{kind} twice")
    script.outputs.insert(0, (kind, path))
    return script


# A Unix socket's path is at most 104 bytes on macOS (108 on Linux), and a sandbox's TMPDIR can be deep.
_SOCKET_PATH_MAX = 100


@contextmanager
def _socket(folder: Path) -> Iterator[Path]:
    """The api-server's address, a plain path: a socket file on POSIX, the name of a named pipe on Windows
    (where no file appears). The first of these whose path fits a socket's (a path too long would have
    kicad-cli say it listens and never bind): inside the private folder; in a short folder of its own
    directly in the temporary folder (``TMPDIR``, which a sandbox lets a program write); in one under /tmp
    (only this user's), which a sandbox may refuse. A folder of its own is removed afterwards. None fits:
    ``KicadRunError`` in one line, naming the cause and what to do."""
    path = folder / "api.sock"
    if sys.platform.startswith("win") or _fits(path):
        yield path
        return
    why: list[str] = []
    for parent in dict.fromkeys((tempfile.gettempdir(), "/tmp")):
        if not _fits(Path(parent) / "k12345678" / "api.sock"):  # mkdtemp's name: its prefix and eight letters
            why.append(f"{parent} is too deep")
            continue
        try:
            short = Path(tempfile.mkdtemp(prefix="k", dir=parent))
        except OSError as error:
            why.append(f"{parent} refused a folder ({error.strerror or error})")
            continue
        try:
            yield short / "api.sock"
        finally:
            shutil.rmtree(short, ignore_errors=True)
        return
    raise KicadRunError(f"a board script's KiCad api-server listens on a socket whose path is at most {_SOCKET_PATH_MAX} "
                        f"bytes, and no folder here gives one ({'; '.join(why)}): set TMPDIR to a shorter folder this "
                        "program may write, then run it again")


def _fits(path: Path) -> bool:
    return len(os.fsencode(path)) <= _SOCKET_PATH_MAX


@contextmanager
def _stopped_on_signals(server: subprocess.Popen) -> Iterator[None]:
    """SIGTERM and SIGHUP (how agent hosts cancel a command) stop the api-server before the script exits, as
    Ctrl-C (SIGINT) does: each becomes SystemExit inside the run, so its ``finally`` stops the server and
    removes its folder; the earlier handlers come back afterwards. Only the main thread can set handlers;
    SIGKILL can never be caught."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def leave(signum: int, _frame: Any) -> None:
        raise SystemExit(128 + signum)

    names = [name for name in ("SIGTERM", "SIGHUP") if hasattr(signal, name)]
    earlier = {name: signal.signal(getattr(signal, name), leave) for name in names}
    try:
        yield
    finally:
        for name, handler in earlier.items():
            signal.signal(getattr(signal, name), handler)


def _format_of(board: Path) -> str | None:
    """The board file's format, its ``(version YYYYMMDD)``."""
    with board.open("rb") as file:
        head = file.read(512).decode("utf-8", "replace")
    found = re.search(r"\(version\s+(\d+)\)", head)
    return found.group(1) if found else None


def _stop(server: subprocess.Popen) -> None:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=STOP_SECONDS)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


def _kipy() -> Any:
    """KiPy's ``KiCad`` class (kicode's), imported before any server is started: without it there is nothing
    to run."""
    try:
        from kicode import KiCad  # pyrefly: ignore[missing-import] - the kicad extra, installed where a board script runs
    except ImportError:
        raise ImportError("a @kicad_pcb script edits its board through KiCad's IPC API, whose client and kicad-cli "
                          "are the kicad extra's (kicode): install cad[kicad], or run the script with cad run") from None
    return KiCad


def _client(kicad: Any, socket: Path) -> Any:
    """KiPy, connected to the server's socket (its ``ipc://`` form)."""
    return kicad(socket_path=f"ipc://{socket}", client_name="cad", timeout_ms=60000)


def _connecting(error: BaseException) -> bool:
    """Whether ``error`` is a connection not made yet: KiPy's ``ConnectionError`` (its own class, by name) or
    the operating system's."""
    return isinstance(error, OSError) or type(error).__name__ == "ConnectionError"


def _board(kicad: Any, server: subprocess.Popen, log: Path) -> Any:
    """The open board, once the server answers for it. Ready is a connection, on every OS: KiPy dials the
    server and pings it until it answers (a connection error until it listens), and the server says it is
    not ready to reply until it has loaded the board. Any other refusal, a server that exits, or one that
    has not answered within ``START_SECONDS``, is a failure."""
    deadline, listened = time.monotonic() + START_SECONDS, False
    while True:
        try:
            kicad.ping()
            listened = True
            return kicad.get_board()
        except Exception as error:  # noqa: BLE001 - KiPy's errors, by kind and by the words it says while loading
            if not _connecting(error) and "not ready" not in str(error).lower():
                raise
            if server.poll() is not None:
                said = quiet(log.read_text(encoding="utf-8", errors="replace")) if log.exists() else ""
                stage = "loaded the board" if listened else "listened"
                raise KicadRunError(f"kicad-cli api-server stopped before it {stage} (exit status "
                                    f"{server.returncode})" + (f": {said}" if said else "")) from None
            if time.monotonic() > deadline:
                stage = "load the board" if listened else "answer"
                raise KicadRunError(f"kicad-cli api-server did not {stage} within {START_SECONDS:g} s") from None
        time.sleep(_POLL)


def run(script: BoardScript, *, cli: Path | None = None) -> BoardRun:
    """Run ``script`` on its board: saved when the function returns, untouched when it raises."""
    board = script.board
    if not board.is_file():
        raise FileNotFoundError(f"no board {board}: a @kicad_pcb script edits a saved board; make it in KiCad first")
    kicad = _kipy()
    if cli is None:
        cli = find_kicad_cli()
        check_version(cli, kicad_version(cli))
    check_api_server(cli)
    before = _format_of(board)
    with private_run("cad-kicad-api-", cli) as (folder, env), _socket(folder) as socket:
        log = folder / "api-server.log"
        with log.open("w", encoding="utf-8") as said:
            server = subprocess.Popen([str(cli), "api-server", "--socket", str(socket), str(board)], env=env,
                                      stdin=subprocess.DEVNULL, stdout=said, stderr=subprocess.STDOUT)
            try:
                with _stopped_on_signals(server):
                    opened = _board(_client(kicad, socket), server, log)
                    script.function(opened)  # a raise leaves the board as it was: nothing is saved
                    opened.save()
            finally:
                _stop(server)
        after = _format_of(board)
        if before and after and before != after:
            print(f"warning: {board.name} is saved in the board format of the KiCad that ran it ({after}, was "
                  f"{before}): a KiCad older than that can no longer open it", file=sys.stderr)
        written = tuple(_write_outputs(script, cli, folder))
    return BoardRun(board, written)


def _write_outputs(script: BoardScript, cli: Path, folder: Path) -> list[Path]:
    """Each file stacked on the script, written from the saved board by its producer's writer."""
    from cad.registry import producer_for

    written = []
    for kind, path in script.outputs:
        producer = producer_for(kind, script, where=f"board script {script.__name__}")
        writer = resolve_name(producer.writer)
        written.append(writer(script.board, path, cli=cli, scratch=folder))
    return written


def _write(to: str, suffix: str, board: Path, out: Path, *, cli: Path, scratch: Path) -> Path:
    """The saved board's ``to`` export (``cad.kicad._export``: what is said beside it, a part without its 3D
    model, said on stderr), moved into place at ``out``."""
    from ._export import export

    made = export(board, to, scratch / to, cli=cli)
    written = next(path for path in made if path.suffix.lower() == suffix)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(written, out)
    print(f"wrote {out}", file=sys.stderr)
    return out


def write_step(board: Path, out: Path, *, cli: Path, scratch: Path) -> Path:
    """The saved board's STEP (``kicad-cli pcb export step --subst-models``), moved into place at ``out``."""
    return _write("step", ".step", board, out, cli=cli, scratch=scratch)


def write_glb(board: Path, out: Path, *, cli: Path, scratch: Path) -> Path:
    """The saved board's GLB (``kicad-cli pcb export glb --subst-models``), moved into place at ``out``; the
    parts written without a 3D model named, as the STEP's are."""
    return _write("glb", ".glb", board, out, cli=cli, scratch=scratch)


def write_dxf(board: Path, out: Path, *, cli: Path, scratch: Path) -> Path:
    """The saved board's outline and drilled holes (``kicad-cli pcb export dxf``, Edge.Cuts, millimetres, as
    ``cad kicad_pcb export --to dxf`` writes them), moved into place at ``out``."""
    return _write("dxf", ".dxf", board, out, cli=cli, scratch=scratch)
