"""``@kicad_pcb("board.kicad_pcb")``: a persistent board script, run through KiCad's IPC API.

The board file is the source; the decorated function edits it::

    from cad import kicad_pcb, step

    @step("board.step")                    # the saved board's STEP, by kicad-cli (--subst-models)
    @kicad_pcb("board.kicad_pcb")          # beside the script, as the engine's decorators' paths are
    def board(b):                          # b: kipy's open Board
        ...

    if __name__ == "__main__":
        board()

A call runs it: a private, headless ``kicad-cli api-server --socket <path> <board>`` (the finder and the
private homes of ``_program``; ``--socket`` takes a plain path, kipy the ``ipc://`` form), kipy connected
to it, the function handed the open board, the board saved when the function returns and nothing saved
when it raises; then the server stopped and its folder removed, whatever happened. The files stacked on
it (``@step``) are written from the saved board afterwards, each by its producer (``cad.registry``).

kipy's ``KiCad.check_version()`` is never called: the PyPI client (0.8.0) targets KiCad 10.0 and calls a
nightly server a future version, while it reads and edits a nightly's boards.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._program import KicadRunError, check_version, find_kicad_cli, kicad_version, private_run, quiet

__all__ = ["BoardRun", "BoardScript", "declare", "run"]

# How long kicad-cli api-server may take to open its socket, and to stop when asked.
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
    """A file stacked on a board script (``@step("board.step")``), written from its saved board."""
    path = _beside(script.function, out)
    if any(existing == kind for existing, _ in script.outputs):
        raise TypeError(f"board script {script.__name__!r} declares @{kind} twice")
    script.outputs.insert(0, (kind, path))
    return script


def _socket(folder: Path) -> Path:
    """The api-server's socket, a plain path inside the private folder (named pipes on Windows)."""
    return folder / "api.sock"


def _wait_for(server: subprocess.Popen, socket: Path, log: Path) -> None:
    """Until the server's socket is there; a server that exits first, or never opens it, is a failure."""
    deadline = time.monotonic() + START_SECONDS
    while not socket.exists():
        if server.poll() is not None:
            said = quiet(log.read_text(encoding="utf-8", errors="replace")) if log.exists() else ""
            raise KicadRunError(f"kicad-cli api-server stopped before it listened (exit status {server.returncode})"
                                + (f": {said}" if said else ""))
        if time.monotonic() > deadline:
            raise KicadRunError(f"kicad-cli api-server did not listen within {START_SECONDS:g} s")
        time.sleep(_POLL)


def _stop(server: subprocess.Popen) -> None:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=STOP_SECONDS)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


def _client(socket: Path) -> Any:
    """kipy, connected to the server's socket (its ``ipc://`` form)."""
    try:
        from kipy import KiCad  # pyrefly: ignore[missing-import] - the kicad extra, installed where a board script runs
    except ImportError:
        raise ImportError("a @kicad_pcb script edits its board through KiCad's IPC API, whose client is the "
                          "kicad extra: install cad[kicad]") from None
    return KiCad(socket_path=f"ipc://{socket}", client_name="cad", timeout_ms=60000)


def run(script: BoardScript, *, cli: Path | None = None) -> BoardRun:
    """Run ``script`` on its board: saved when the function returns, untouched when it raises."""
    board = script.board
    if not board.is_file():
        raise FileNotFoundError(f"no board {board}: a @kicad_pcb script edits a saved board; make it in KiCad first")
    if cli is None:
        cli = find_kicad_cli()
        check_version(cli, kicad_version(cli))
    with private_run("cad-kicad-api-") as (folder, env):
        socket, log = _socket(folder), folder / "api-server.log"
        with log.open("w", encoding="utf-8") as said:
            server = subprocess.Popen([str(cli), "api-server", "--socket", str(socket), str(board)], env=env,
                                      stdin=subprocess.DEVNULL, stdout=said, stderr=subprocess.STDOUT)
            try:
                _wait_for(server, socket, log)
                kicad = _client(socket)
                opened = kicad.get_board()
                script.function(opened)  # a raise leaves the board as it was: nothing is saved
                opened.save()
            finally:
                _stop(server)
        written = tuple(_write_outputs(script, cli, folder))
    return BoardRun(board, written)


def _write_outputs(script: BoardScript, cli: Path, folder: Path) -> list[Path]:
    """Each file stacked on the script, written from the saved board by its producer's writer."""
    from cad.registry import producer_for

    written = []
    for kind, path in script.outputs:
        producer = producer_for(kind, script, where=f"board script {script.__name__}")
        writer = _writer(producer.writer)
        written.append(writer(script.board, path, cli=cli, scratch=folder))
    return written


def _writer(path: str) -> Callable[..., Path]:
    import importlib

    module, _, name = path.rpartition(".")
    return getattr(importlib.import_module(module), name)


def write_step(board: Path, out: Path, *, cli: Path, scratch: Path) -> Path:
    """The saved board's STEP (``kicad-cli pcb export step --subst-models``), moved into place at ``out``."""
    from ._export import export

    made = export(board, "step", scratch / "step", cli=cli)
    step = next(path for path in made if path.suffix.lower() == ".step")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(step, out)
    print(f"wrote {out}", file=sys.stderr)
    return out
