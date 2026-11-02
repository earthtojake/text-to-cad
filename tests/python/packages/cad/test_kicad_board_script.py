"""``@kicad_pcb``: a board script's lifecycle, with kicad-cli's api-server and kipy stood in for.

The board is saved when the function returns and not when it raises; the api-server it started is
stopped and its private folder removed either way; a ``@step`` stacked on it is written from the saved
board by the kicad integration's producer, and dispatched there by what the function is. The real round
trip, on a KiCad nightly, is ``tests/python/packages/kicad/test_board_script.py``.
"""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad import kicad_pcb, step  # noqa: E402
from cad.kicad import _session  # noqa: E402


class _Server:
    """``kicad-cli api-server``: opens its socket at start, and is asked to stop."""

    started: list["_Server"] = []

    def __init__(self, command, **options):
        self.command, self.returncode, self.stopped = command, None, False
        self.socket = Path(command[command.index("--socket") + 1])
        self.socket.touch()
        _Server.started.append(self)

    def poll(self):
        return self.returncode

    def terminate(self):
        self.stopped, self.returncode = True, 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.terminate()


class _Board:
    saved = 0

    def save(self):
        _Board.saved += 1


def _kipy() -> types.ModuleType:
    module = types.ModuleType("kipy")

    class KiCad:
        def __init__(self, socket_path=None, client_name=None, kicad_token=None, timeout_ms=2000):
            assert socket_path.startswith("ipc://"), socket_path
            self.socket_path = socket_path

        def get_board(self):
            return _Board()

        def check_version(self):  # the PyPI client calls a nightly a future version: never asked
            raise AssertionError("check_version is never called")

    module.KiCad = KiCad
    return module


class BoardScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="cad-board-script-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.folder, ignore_errors=True))
        self.board = self.folder / "board.kicad_pcb"
        self.board.write_text("(kicad_pcb)\n", encoding="utf-8")
        _Server.started.clear()
        _Board.saved = 0
        patches = [mock.patch.object(_session.subprocess, "Popen", _Server), mock.patch.dict(sys.modules, {"kipy": _kipy()})]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def script(self, body, *stack):
        target = kicad_pcb(str(self.board))(body)
        for decorator in stack:
            target = decorator(target)
        return target

    def test_the_board_is_saved_when_the_function_returns(self) -> None:
        handed = []
        ran = _session.run(self.script(handed.append), cli=Path("/opt/kicad/kicad-cli"))
        self.assertEqual((1, 1), (len(handed), _Board.saved))
        self.assertEqual(self.board, ran.board)
        (server,) = _Server.started
        self.assertEqual(["/opt/kicad/kicad-cli", "api-server", "--socket"], server.command[:3])
        self.assertEqual(str(self.board), server.command[-1])
        self.assertTrue(server.stopped)
        self.assertFalse(server.socket.parent.exists(), "the private folder is removed")

    def test_nothing_is_saved_when_the_function_raises(self) -> None:
        def broken(board):
            raise ValueError("no")

        with self.assertRaises(ValueError):
            _session.run(self.script(broken), cli=Path("kicad-cli"))
        self.assertEqual(0, _Board.saved)
        (server,) = _Server.started
        self.assertTrue(server.stopped)
        self.assertFalse(server.socket.parent.exists())

    def test_a_stacked_step_is_the_kicad_producers_written_from_the_saved_board(self) -> None:
        def export(board, to, out_dir, *, cli=None):
            self.assertEqual((self.board, "step", 1), (board, to, _Board.saved))
            out_dir.mkdir(parents=True)
            (out_dir / f"{board.stem}.step").write_text("ISO-10303-21;\n", encoding="utf-8")
            return [out_dir / f"{board.stem}.step"]

        script = self.script(lambda board: None, step(str(self.folder / "out" / "board.step")))
        self.assertIsInstance(script, _session.BoardScript)
        with mock.patch("cad.kicad._export.export", export):
            ran = _session.run(script, cli=Path("kicad-cli"))
        self.assertEqual((self.folder / "out" / "board.step",), ran.written)
        self.assertTrue(ran.written[0].read_text(encoding="utf-8").startswith("ISO-10303-21"))

    def test_a_server_that_stops_before_it_listens_says_so_and_saves_nothing(self) -> None:
        class Refusing(_Server):
            def __init__(self, command, **options):
                self.command, self.returncode, self.stopped = command, 3, False
                self.socket = Path(command[command.index("--socket") + 1])
                _Server.started.append(self)

        with mock.patch.object(_session.subprocess, "Popen", Refusing), \
                self.assertRaisesRegex(Exception, "stopped before it listened"):
            _session.run(self.script(lambda board: None), cli=Path("kicad-cli"))
        self.assertEqual(0, _Board.saved)

    def test_the_decorator_takes_a_board_path_and_a_missing_board_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            kicad_pcb("board.step")
        with self.assertRaises(TypeError):
            kicad_pcb(None)
        script = kicad_pcb(str(self.folder / "absent.kicad_pcb"))(lambda board: None)
        with self.assertRaises(FileNotFoundError):
            _session.run(script, cli=Path("kicad-cli"))
        self.assertEqual([], _Server.started)


if __name__ == "__main__":
    unittest.main()
