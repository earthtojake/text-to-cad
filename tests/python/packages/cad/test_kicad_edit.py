"""``kicad_pcb.edit`` and ``kicad_sch.edit``: the edit transaction, with kicad-cli's api-server and KiPy (kicode's)
stood in for.

A document is saved at the block's end when the block changed it, not when it changed nothing (so its file
stays byte for byte as it was) and not when the block raises, whose exception goes on; a file not there yet
is made by KiCad and saved. The api-server is ready when KiPy's connection answers, never when a file
appears (the fake server never makes one, as Windows' named pipe does not); a kicad-cli without api-server
is refused before one starts; the server is stopped and its private folder removed either way, and its
KiCad homes are that folder, never the person's. A schematic's project symbol libraries are loaded before
the block runs, and a placement from a library the project does not list is refused in one line naming it
and the row that adds it. A board and a schematic of one project edited in one block share one server.
The real edits, on a KiCad nightly, are ``tests/python/packages/kicad/test_edit.py``.
"""

from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad import kicad_pcb, kicad_sch  # noqa: E402
from cad.kicad import _program, _session  # noqa: E402

LOADED, ERROR, SYMBOL = "loaded", "error", "symbol"
CLI = Path("kicad-cli")


class _Server:
    """``kicad-cli api-server``: started with its command and environment, makes no file where it listens,
    and is asked to stop."""

    started: list["_Server"] = []

    def __init__(self, command, env=None, **options):
        self.command, self.env, self.returncode, self.stopped = command, env, None, False
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


class _KiCad:
    """What the stand-in KiCad saw and says."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.modified = {"pcb": True, "schematic": True}
        self.saved: list[str] = []
        self.loading = 2  # the getter's "not ready" answers, while the server loads the file
        self.dialing = 3  # ping's connection errors, before the server listens
        self.libraries = {"test": LOADED}


def _kicode(state: _KiCad) -> dict[str, types.ModuleType]:
    """The modules of kicode an edit imports, standing in for KiPy."""

    class ConnectionError(Exception):  # kicode.errors.ConnectionError (KiPy's): its own class, no OSError
        pass

    class Status:
        def __init__(self, nickname, status):
            self.nickname, self.status = nickname, status
            self.error_message = "the file is not there" if status == ERROR else None

    class Document:
        kind = ""

        def __init__(self, client, document):
            self._client, self._doc = client, document

        @property
        def client(self):
            return self._client

        @property
        def document(self):
            return self._doc

        def is_document_modified(self):
            return state.modified[self.kind]

        def save(self):
            state.saved.append(self.kind)

    class Board(Document):
        kind = "pcb"

    class Schematic(Document):
        kind = "schematic"

        def place_symbol_from_library(self, lib_id, position, **options):
            state.calls.append(("place", lib_id, self._doc))
            return "placed"

        def for_sheet(self, sheet):
            return Schematic(self._client, sheet)

    class KiCad:
        def __init__(self, socket_path=None, client_name=None, timeout_ms=None):
            assert socket_path.startswith("ipc://"), socket_path
            self.socket_path = socket_path

        def ping(self):
            assert not Path(self.socket_path.removeprefix("ipc://")).exists(), "the fake server makes no file"
            if state.dialing:
                state.dialing -= 1
                raise ConnectionError("Failed to connect to KiCad: Connection refused")

        def _loaded(self):
            if state.loading:  # the server opens its socket before it has loaded the file
                state.loading -= 1
                raise RuntimeError("KiCad returned error: KiCad is not ready to reply")

        def get_board(self):
            self._loaded()
            return Board(self, "board")

        def get_schematic(self):
            self._loaded()
            return Schematic(self, "root")

        def create_document(self, path, kind):
            state.calls.append(("create", path, kind))

        def open_document(self, path, kind):
            state.calls.append(("open", path, kind))

        def load_all_libraries(self, types=None):
            state.calls.append(("load", types))

        def wait_for_libraries(self, types=None, timeout_s=60.0):
            state.calls.append(("wait", types))
            return [Status(nickname, status) for nickname, status in state.libraries.items()]

        def check_version(self):  # never asked: a CAD_KICAD_CLI nightly may be another build
            raise AssertionError("check_version is never called")

    root = types.ModuleType("kicode")
    root.KiCad = KiCad
    schematic = types.ModuleType("kicode.schematic")
    schematic.Schematic = Schematic
    kinds = types.ModuleType("kicode.proto.common.types")
    kinds.DocumentType = types.SimpleNamespace(DOCTYPE_PCB="pcb", DOCTYPE_SCHEMATIC="schematic")
    libraries = types.ModuleType("kicode.proto.common.types.library_types_pb2")
    libraries.LibraryType = types.SimpleNamespace(LT_SYMBOL=SYMBOL)
    libraries.LibraryLoadStatus = types.SimpleNamespace(LLS_LOADED=LOADED)
    return {"kicode": root, "kicode.schematic": schematic, "kicode.proto.common.types": kinds,
            "kicode.proto.common.types.library_types_pb2": libraries}


class EditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="cad-kicad-edit-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.board = self.folder / "design.kicad_pcb"
        self.board.write_text("(kicad_pcb (version 20250114))\n", encoding="utf-8")
        self.schematic = self.folder / "design.kicad_sch"
        self.schematic.write_text("(kicad_sch (version 20250114))\n", encoding="utf-8")
        (self.folder / "sym-lib-table").write_text("(sym_lib_table (version 7))\n", encoding="utf-8")
        _Server.started.clear()
        self.kicad = _KiCad()
        for patch in (mock.patch.object(_session.subprocess, "Popen", _Server),
                      mock.patch.dict(sys.modules, _kicode(self.kicad)),
                      mock.patch.object(_session, "check_api_server", lambda cli: cli),
                      mock.patch.object(_session, "find_kicad_cli", lambda: CLI),
                      mock.patch.object(_session, "kicad_version", lambda cli: "10.99.0"),
                      mock.patch.object(_session, "check_version", lambda cli, version: version)):
            patch.start()
            self.addCleanup(patch.stop)

    def edit(self, path: Path, body=lambda document: None) -> str:
        """``body`` run in an edit of ``path``; what the edit said on stderr."""
        said = io.StringIO()
        with contextlib.redirect_stderr(said), _session.edit(path, _session._KINDS[path.suffix].type_id, cli=CLI) as opened:
            body(opened)
        return said.getvalue()


class TheTransaction(EditTest):
    def test_saved_when_the_block_changed_it_once_the_server_answers(self) -> None:
        handed = []
        self.edit(self.board, handed.append)
        self.assertEqual((1, ["pcb"], 0, 0), (len(handed), self.kicad.saved, self.kicad.loading, self.kicad.dialing),
                         "dialed until it answered, asked again while it said it was not ready, then handed the "
                         "board once and saved it")
        (server,) = _Server.started
        self.assertEqual([str(CLI), "api-server", "--socket"], server.command[:3])
        self.assertEqual(str(self.board), server.command[-1])
        self.assertTrue(server.stopped)
        self.assertFalse(server.socket.parent.exists(), "the private folder is removed")

    def test_a_block_that_changed_nothing_leaves_the_file_as_it_was(self) -> None:
        self.kicad.modified["pcb"] = False
        before = self.board.read_bytes()
        said = self.edit(self.board)
        self.assertEqual([], self.kicad.saved)
        self.assertEqual(before, self.board.read_bytes())
        self.assertNotIn("is saved in the board format", said)

    def test_a_raise_saves_nothing_and_goes_on(self) -> None:
        def broken(board):
            raise ValueError("no")

        with self.assertRaisesRegex(ValueError, "no"):
            self.edit(self.board, broken)
        self.assertEqual([], self.kicad.saved)
        (server,) = _Server.started
        self.assertTrue(server.stopped)
        self.assertFalse(server.socket.parent.exists())

    def test_a_file_not_there_yet_is_made_by_kicad_and_saved(self) -> None:
        board = self.folder / "new" / "fresh.kicad_pcb"
        self.kicad.modified["pcb"] = False  # a new board is saved whatever the block did
        folders = []
        said = self.edit(board, lambda opened: folders.append(board.parent.is_dir()))
        (server,) = _Server.started
        self.assertEqual("--socket", server.command[-2], "the server starts on no file")
        self.assertIn(("create", str(board), "pcb"), self.kicad.calls)
        self.assertEqual((["pcb"], [True]), (self.kicad.saved, folders), "its folder made for KiCad to make it in")
        self.assertIn(f"made {board}, a new board, and its project fresh.kicad_pro", said)

    def test_a_raise_on_a_file_not_there_yet_leaves_no_folder_it_made(self) -> None:
        def broken(opened):
            raise ValueError("no")

        with self.assertRaises(ValueError):
            self.edit(self.folder / "new" / "deeper" / "fresh.kicad_pcb", broken)
        self.assertFalse((self.folder / "new").exists())

    def test_the_servers_kicad_homes_are_private(self) -> None:
        """KiCad's settings, documents and cache homes are the server's own folder, never the person's: no
        global library table is read, and none is written."""
        self.edit(self.schematic)
        (server,) = _Server.started
        private = server.socket.parent
        for variable in ("KICAD_CONFIG_HOME", "KICAD_DOCUMENTS_HOME", "KICAD_CACHE_HOME", "HOME"):
            self.assertTrue(Path(server.env[variable]).is_relative_to(private), variable)

    def test_a_file_of_the_other_type_is_refused_by_name_before_anything_starts(self) -> None:
        with self.assertRaisesRegex(ValueError, r"design.kicad_sch is a kicad_sch, not a kicad_pcb: use cad.kicad_sch.edit"):
            with kicad_pcb.edit(self.schematic):
                pass
        with self.assertRaisesRegex(ValueError, "board.step is no KiCad file, not a kicad_sch"):
            with kicad_sch.edit(self.folder / "board.step"):
                pass
        self.assertEqual([], _Server.started)

    def test_the_type_has_no_decorator_and_names_its_edit(self) -> None:
        with self.assertRaisesRegex(TypeError, r"with cad.kicad_pcb.edit\(path\) as board:"):
            kicad_pcb("board.kicad_pcb")


class TheServer(EditTest):
    def test_a_server_that_stops_before_it_listens_says_so_and_saves_nothing(self) -> None:
        class Refusing(_Server):
            def __init__(self, command, **options):
                super().__init__(command, **options)
                self.returncode = 3

        self.kicad.dialing = 10**6
        with mock.patch.object(_session.subprocess, "Popen", Refusing), \
                self.assertRaisesRegex(Exception, "stopped before it listened"):
            self.edit(self.board)
        self.assertEqual([], self.kicad.saved)

    def test_a_refusal_other_than_not_ready_or_not_connected_is_the_edits_error(self) -> None:
        with mock.patch.object(_session, "_client", return_value=mock.Mock(**{"ping.side_effect": ValueError("bad token")})), \
                self.assertRaisesRegex(ValueError, "bad token"):
            self.edit(self.board)
        (server,) = _Server.started
        self.assertTrue(server.stopped)

    def test_a_kicad_cli_without_api_server_is_refused_before_one_starts(self) -> None:
        """A stable kicad-cli (9, 10) CAD_KICAD_CLI names checks and exports but has no api-server: refused up front,
        saying what an edit needs; a nightly's, which lists ``--socket``, is taken."""
        def answering(text, code):
            return lambda command, **options: subprocess.CompletedProcess(command, code, stdout=text, stderr="")

        with mock.patch.object(_session, "check_api_server", _program.check_api_server):
            with mock.patch.object(_program.subprocess, "run", answering("Unknown command: api-server\n", 1)), \
                    self.assertRaises(_program.KicadMissingError) as caught:
                self.edit(self.board)
            self.assertEqual([], _Server.started, "no server is started")
            for words in ("has no api-server", "KiCad nightly's (10.99)", "kicode", "KiCad 9 or newer", "CAD_KICAD_CLI"):
                self.assertIn(words, str(caught.exception))
            with mock.patch.object(_program.subprocess, "run", answering("Usage: api-server [--socket PATH] board\n", 0)):
                self.edit(self.board)
        self.assertEqual(1, len(_Server.started))

    def test_no_kicode_is_refused_before_a_server_starts(self) -> None:
        with mock.patch.dict(sys.modules, {"kicode": None}), self.assertRaisesRegex(ImportError, "cad\\[kicad\\]"):
            self.edit(self.board)
        self.assertEqual([], _Server.started)

    def test_a_board_and_a_schematic_of_one_project_share_one_server(self) -> None:
        """The schematic's edit, inside the board's, joins its server (KiCad opening the file there); each is
        saved at its own block's end, by its own state; the server stops when the edit that started it ends."""
        self.kicad.modified["pcb"] = False
        with contextlib.redirect_stderr(io.StringIO()), kicad_pcb.edit(self.board), \
                mock.patch.object(_session, "_client", side_effect=AssertionError("no second client")):
            with kicad_sch.edit(self.schematic):
                pass
            self.assertEqual(["schematic"], self.kicad.saved, "the schematic saved at its own block's end")
            (server,) = _Server.started
            self.assertFalse(server.stopped)
        self.assertTrue(server.stopped)
        self.assertEqual(["schematic"], self.kicad.saved, "the board, unchanged, is not")
        self.assertIn(("open", str(self.schematic), "schematic"), self.kicad.calls)
        with self.assertRaisesRegex(RuntimeError, "is open in an edit already"):
            with contextlib.redirect_stderr(io.StringIO()), kicad_pcb.edit(self.board), kicad_pcb.edit(self.board):
                pass

    def test_another_projects_file_gets_a_server_of_its_own(self) -> None:
        other = self.folder / "other.kicad_sch"
        other.write_text("(kicad_sch)\n", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()), kicad_pcb.edit(self.board), kicad_sch.edit(other):
            pass
        self.assertEqual(2, len(_Server.started))

    def test_a_socket_path_too_long_for_a_unix_socket_moves_to_a_short_folder(self) -> None:
        # In order: the private folder; a short folder directly in the temporary folder (what a sandbox lets a
        # program write); one under /tmp. Each folder of its own is removed afterwards.
        if sys.platform.startswith("win"):
            self.skipTest("a named pipe has no such limit")
        with _session._socket(self.folder) as socket:
            self.assertEqual(self.folder / "api.sock", socket)
        deep = self.folder / ("d" * 120)
        short_tmp = Path(tempfile.mkdtemp(prefix="t", dir="/tmp")).resolve()
        self.addCleanup(shutil.rmtree, short_tmp, ignore_errors=True)
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


class TheLibraries(EditTest):
    def test_the_project_libraries_load_before_the_block_runs(self) -> None:
        seen = []
        self.edit(self.schematic, lambda schematic: seen.append(list(self.kicad.calls)))
        self.assertEqual([[("load", SYMBOL), ("wait", SYMBOL)]], seen, "the symbol libraries alone, loaded first")

    def test_a_placement_from_a_library_the_project_lacks_is_one_line_naming_it_and_the_fix(self) -> None:
        def places(schematic):
            schematic.place_symbol_from_library("test:R", (0, 0), reference="R1")
            schematic.for_sheet("child").place_symbol_from_library("Device:R", (0, 0))

        with self.assertRaises(LookupError) as said:
            self.edit(self.schematic, places)
        message = str(said.exception)
        self.assertNotIn("\n", message)
        for words in ("no symbol library 'Device'", str(self.folder / "sym-lib-table"), "which lists test",
                      '(lib (name "Device")(type "KiCad")(uri "${KIPRJMOD}/Device.kicad_sym")'):
            self.assertIn(words, message)
        self.assertEqual([("place", "test:R", "root")], [call for call in self.kicad.calls if call[0] == "place"],
                         "a library the project has is KiCad's to place from; the other never reaches it")
        self.assertEqual([], self.kicad.saved, "a raise saves nothing")

    def test_a_project_without_a_table_is_told_to_write_one(self) -> None:
        (self.folder / "sym-lib-table").unlink()
        self.kicad.libraries = {}
        with self.assertRaisesRegex(LookupError, r"this project has no sym-lib-table .*\(sym_lib_table \(version 7\)"):
            self.edit(self.schematic, lambda schematic: schematic.place_symbol_from_library("test:R", (0, 0)))

    def test_a_library_that_did_not_load_is_said_and_named_by_a_placement_from_it(self) -> None:
        self.kicad.libraries = {"test": LOADED, "broken": ERROR}
        said = self.edit(self.schematic)
        self.assertIn("warning: symbol library broken did not load: the file is not there", said)
        with self.assertRaisesRegex(LookupError, "symbol library 'broken' did not load: the file is not there"):
            self.edit(self.schematic, lambda schematic: schematic.place_symbol_from_library("broken:X", (0, 0)))


if __name__ == "__main__":
    unittest.main()
