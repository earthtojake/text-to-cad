"""``@kicad_pcb``: a board script's lifecycle, with kicad-cli's api-server and KiPy (kicode's) stood in for.

The board is saved when the function returns and not when it raises; the api-server is ready when KiPy's
connection answers, never when a file appears (the fake server never makes one, as Windows' named pipe
does not); a kicad-cli without api-server is refused before one starts; the api-server it started is
stopped and its private folder removed either way; a ``@step`` stacked on it is written from the saved
board by the kicad integration's producer, and dispatched there by what the function is. The real round
trip, on a KiCad nightly, is ``tests/python/packages/kicad/test_board_script.py``.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad import kicad_pcb, step  # noqa: E402
from cad.kicad import _program, _session  # noqa: E402


class _Server:
    """``kicad-cli api-server``: listens where it is told, makes no file there, and is asked to stop."""

    started: list["_Server"] = []

    def __init__(self, command, **options):
        self.command, self.returncode, self.stopped = command, None, False
        self.socket = Path(command[command.index("--socket") + 1])
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
    loading = 0  # get_board's "not ready" answers, while the server loads the board
    dialing = 0  # ping's connection errors, before the server listens

    def save(self):
        _Board.saved += 1


def _kicode() -> types.ModuleType:
    module = types.ModuleType("kicode")

    class ConnectionError(Exception):  # kicode.errors.ConnectionError (KiPy's): its own class, no OSError
        pass

    class KiCad:
        def __init__(self, socket_path=None, client_name=None, kicad_token=None, timeout_ms=2000):
            assert socket_path.startswith("ipc://"), socket_path
            self.socket_path = socket_path

        def ping(self):
            assert not Path(self.socket_path.removeprefix("ipc://")).exists(), "the fake server makes no file"
            if _Board.dialing:
                _Board.dialing -= 1
                raise ConnectionError("Failed to connect to KiCad: Connection refused")

        def get_board(self):
            if _Board.loading:  # the server opens its socket before it has loaded the board
                _Board.loading -= 1
                raise RuntimeError("KiCad returned error: KiCad is not ready to reply")
            return _Board()

        def check_version(self):  # never asked: a CAD_KICAD_CLI nightly may be another build
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
        _Board.saved, _Board.loading, _Board.dialing = 0, 2, 3
        patches = [mock.patch.object(_session.subprocess, "Popen", _Server), mock.patch.dict(sys.modules, {"kicode": _kicode()}),
                   mock.patch.object(_session, "check_api_server", lambda cli: cli)]
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
        self.assertEqual((1, 1, 0, 0), (len(handed), _Board.saved, _Board.loading, _Board.dialing),
                         "dialed until it answered, asked again while it said it was not ready, then handed the "
                         "board once")
        self.assertEqual(self.board, ran.board)
        (server,) = _Server.started
        self.assertEqual([str(Path("/opt/kicad/kicad-cli")), "api-server", "--socket"], server.command[:3])
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
                super().__init__(command, **options)
                self.returncode = 3

        _Board.dialing = 10**6
        with mock.patch.object(_session.subprocess, "Popen", Refusing), \
                self.assertRaisesRegex(Exception, "stopped before it listened"):
            _session.run(self.script(lambda board: None), cli=Path("kicad-cli"))
        self.assertEqual(0, _Board.saved)

    def test_a_refusal_other_than_not_ready_or_not_connected_is_the_runs_error(self) -> None:
        _Board.dialing, _Board.loading = 0, 0
        with mock.patch.object(_Board, "save", side_effect=AssertionError("never saved")), \
                mock.patch.object(_session, "_client", return_value=mock.Mock(**{"ping.side_effect": ValueError("bad token")})), \
                self.assertRaisesRegex(ValueError, "bad token"):
            _session.run(self.script(lambda board: None), cli=Path("kicad-cli"))
        (server,) = _Server.started
        self.assertTrue(server.stopped)

    def test_a_kicad_cli_without_api_server_is_refused_before_one_starts(self) -> None:
        """A stable kicad-cli (9, 10) CAD_KICAD_CLI names checks and exports but has no api-server: refused up front, saying what
        a board script needs; a nightly's, which lists ``--socket``, is taken."""
        def answering(text, code):
            return lambda command, **options: subprocess.CompletedProcess(command, code, stdout=text, stderr="")

        with mock.patch.object(_session, "check_api_server", _program.check_api_server):
            with mock.patch.object(_program.subprocess, "run", answering("Unknown command: api-server\n", 1)), \
                    self.assertRaises(_program.KicadMissingError) as caught:
                _session.run(self.script(lambda board: None), cli=Path("kicad-cli"))
            self.assertEqual([], _Server.started, "no server is started")
            for words in ("has no api-server", "KiCad nightly's (10.99)", "kicode", "KiCad 9 or newer", "CAD_KICAD_CLI"):
                self.assertIn(words, str(caught.exception))
            with mock.patch.object(_program.subprocess, "run", answering("Usage: api-server [--socket PATH] board\n", 0)):
                _session.run(self.script(lambda board: None), cli=Path("kicad-cli"))
        self.assertEqual(1, len(_Server.started))

    def test_the_decorator_takes_a_board_path_and_a_missing_board_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            kicad_pcb("board.step")
        with self.assertRaises(TypeError):
            kicad_pcb(None)
        script = kicad_pcb(str(self.folder / "absent.kicad_pcb"))(lambda board: None)
        with self.assertRaises(FileNotFoundError):
            _session.run(script, cli=Path("kicad-cli"))
        self.assertEqual([], _Server.started)


    def test_no_kicode_is_refused_before_a_server_starts(self) -> None:
        with mock.patch.dict(sys.modules, {"kicode": None}), self.assertRaisesRegex(ImportError, "cad\\[kicad\\]"):
            _session.run(self.script(lambda board: None), cli=Path("kicad-cli"))
        self.assertEqual([], _Server.started)

    def test_a_socket_path_too_long_for_a_unix_socket_moves_to_a_short_folder(self) -> None:
        # In order: the private folder; a short folder directly in the temporary folder (what a sandbox lets a
        # program write); one under /tmp. Each folder of its own is removed afterwards.
        if sys.platform.startswith("win"):
            self.skipTest("a named pipe has no such limit")
        with _session._socket(self.folder) as socket:
            self.assertEqual(self.folder / "api.sock", socket)
        deep = self.folder / ("d" * 120)
        short_tmp = Path(tempfile.mkdtemp(prefix="t", dir="/tmp")).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(short_tmp, ignore_errors=True))
        with mock.patch.object(_session.tempfile, "gettempdir", lambda: str(short_tmp)):
            with _session._socket(deep) as socket:
                self.assertEqual(short_tmp, socket.parent.parent, "directly in the temporary folder")
                self.assertLessEqual(len(str(socket)), 100)
                self.assertTrue(socket.parent.is_dir())
                made = socket.parent
            self.assertFalse(made.exists(), "the short folder is removed")
        made_in: list[str] = []
        real = tempfile.mkdtemp

        def refusing(prefix: str = "", dir: str | None = None):  # noqa: A002 - mkdtemp's own name
            made_in.append(str(dir))
            if dir != "/tmp":
                raise PermissionError(1, "Operation not permitted")
            return real(prefix=prefix, dir=dir)

        with mock.patch.object(_session.tempfile, "gettempdir", lambda: str(short_tmp)), \
                mock.patch.object(_session.tempfile, "mkdtemp", refusing):
            with _session._socket(deep) as socket:
                self.assertEqual(Path("/tmp"), socket.parent.parent, "then /tmp")
        self.assertEqual([str(short_tmp), "/tmp"], made_in)

    def test_no_folder_that_gives_a_short_socket_is_one_line_naming_the_cause_and_the_fix(self) -> None:
        if sys.platform.startswith("win"):
            self.skipTest("a named pipe has no such limit")
        deep = self.folder / ("d" * 120)

        def refused(prefix: str = "", dir: str | None = None):  # noqa: A002 - mkdtemp's own name
            raise PermissionError(1, "Operation not permitted")

        with mock.patch.object(_session.tempfile, "gettempdir", lambda: str(deep)), \
                mock.patch.object(_session.tempfile, "mkdtemp", refused):
            with self.assertRaises(_program.KicadRunError) as said:
                with _session._socket(deep):
                    self.fail("no socket")
        message = str(said.exception)
        self.assertNotIn("\n", message)
        self.assertIn(f"{deep} is too deep", message)
        self.assertIn("/tmp refused a folder (Operation not permitted)", message)
        self.assertIn("set TMPDIR to a shorter folder this program may write", message)

    def test_step_on_a_function_of_the_board_names_the_order(self) -> None:
        def edits(board):
            pass

        with self.assertRaisesRegex(TypeError, r"declared by @kicad_pcb\(\.\.\.\) directly on it, with @step above"):
            step(str(self.folder / "board.step"))(edits)


if __name__ == "__main__":
    unittest.main()
