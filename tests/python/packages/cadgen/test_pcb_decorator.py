"""``@pcb`` against a fake KiCad: the build's sequence, its files, its report and its refusals.

The one seam, ``cadgen.pcb.connect``, is replaced by a fake client that records every
call, so the contract runs without KiCad: the document is created at the right path,
the project's footprint libraries are loaded and waited for, the function gets the
board, the zones are refilled, the unrouted pads are counted, the board is saved, its
hash is recorded as the project's ``CADGEN_BUILD`` and saved again, the document is
closed, the server is stopped, KiCad's DRC runs on the saved file (``--no-drc`` skips
it), one line and the findings are printed, and a fresh settings directory is the
server's ``KICAD_CONFIG_HOME`` for exactly its lifetime. Before a build, a board the
record does not cover is refused unless ``--force``. The real sequence against KiCad
is the KiCad suite's (``tests/python/packages/kicad``).
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cadgen.pcb as pcb
from cadgen.kicad.cli import Finding
from cadgen.kicad.install import KicadMissingError
from cadgen.kipy.errors import ApiError
from cadgen.kipy.proto.common.types.base_types_pb2 import DocumentType
from cadgen.kipy.proto.common.types.library_types_pb2 import LibraryLoadStatus, LibraryType

SCRIPT = """\
from cadgen import pcb

seen = []

@pcb
def blinky(board):
    seen.append(board)

@pcb(path="boards/other.kicad_pcb")
def other(board):
    seen.append(board)

@pcb
def broken(board):
    raise ValueError("no such part")

@pcb
def missing(board):
    from cadgen.kipy.errors import ApiError
    raise ApiError("KiCad returned error: footprint 'LED_SMD:LED_0603' not found", "footprint 'LED_SMD:LED_0603' not found")
"""

# What KiCad's DRC reports, a warning ahead of an error: the printed order is errors first.
FINDINGS = (
    Finding("violation", "warning", "track_dangling", "Track has unconnected end", ("Track [GND] on F.Cu",), None),
    Finding("violation", "error", "clearance", "Clearance violation (0.1 mm < 0.15 mm)", ("Track [LED] on F.Cu", "Pad 1 [GND] of D1"), (8.0, -5.0)),
)


def _pad(net: str, ident: str) -> SimpleNamespace:
    return SimpleNamespace(net=SimpleNamespace(name=net), id=SimpleNamespace(value=ident))


def _row(nickname: str, status=LibraryLoadStatus.LLS_LOADED, error: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(nickname=nickname, status=status, error_message=error)


class FakeProject:
    """The project's text variables, kept on the fake server as the ``.kicad_pro`` keeps them
    across documents: a rebuild's first save carries the previous record, as KiCad's does."""

    def __init__(self, kicad: FakeKiCad) -> None:
        self.kicad = kicad

    def get_text_variables(self):
        return dict(self.kicad.variables)

    def set_text_variables(self, variables) -> None:
        self.kicad.log.append(("set_text_variables", dict(variables)))
        self.kicad.variables = dict(variables)


class FakeBoard:
    def __init__(self, kicad: FakeKiCad, path: Path) -> None:
        self.kicad, self.log, self.path = kicad, kicad.log, path
        # VBUS: both pads joined; GND: one of three pads reaches nothing; LED: a single pad.
        self.pads = [_pad("VBUS", "v1"), _pad("VBUS", "v2"), _pad("GND", "g1"), _pad("GND", "g2"), _pad("GND", "g3"), _pad("LED", "l1")]
        self.reached = {"v1": ["v2"], "g1": ["g2"]}

    def refill_zones(self) -> None:
        self.log.append("refill_zones")

    def get_pads(self):
        return self.pads

    def get_connected_items(self, items):
        return [pad for pad in self.pads if pad.id.value in self.reached.get(items[0].id.value, [])]

    def get_footprints(self):
        return ["J1", "R1"]

    def get_tracks(self):
        return ["t1", "t2", "t3"]

    def get_vias(self):
        return ["v"]

    def get_zones(self):
        return ["pour"]

    def get_project(self):
        return FakeProject(self.kicad)

    def save(self) -> None:
        # As KiCad writes it: the project's text variables are properties of the board file.
        self.log.append("save")
        record = self.kicad.variables.get(pcb.RECORD)
        lines = ['(kicad_pcb (version 20260901) (generator "pcbnew")'] + ([f'\t(property "{pcb.RECORD}" "{record}")'] if record else []) + ['\t(footprint "R1")', ")"]
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class FakeKiCad:
    def __init__(self, log: list, rows, version=(10, 99, 0)) -> None:
        self.log, self.rows, self.version = log, rows, version
        self.variables: dict[str, str] = {}
        self.boards: list[FakeBoard] = []
        self._client = "the client"  # what kipy keeps private, and the build reaches for once

    def make_board(self, client, document):
        # Stands in for cadgen.kipy.board.Board: the build constructs the board on the
        # specifier create_document returned, never through get_board().
        self.log.append(("Board", client, document))
        self.boards.append(FakeBoard(self, Path(document[1])))
        return self.boards[-1]

    def get_version(self):
        return SimpleNamespace(major=self.version[0], minor=self.version[1], patch=self.version[2])

    def create_document(self, path, kind):
        self.log.append(("create_document", path, kind))
        return ("document", path)

    def load_all_libraries(self, types):
        self.log.append(("load_all_libraries", list(types)))

    def wait_for_libraries(self, types, interval_ms, timeout_s):
        self.log.append(("wait_for_libraries", list(types)))
        return self.rows

    def get_board(self):
        raise AssertionError("get_board() reports a project path the project commands reject; build on the specifier")

    def close_document(self, document):
        self.log.append(("close_document", document))

    def close(self):
        self.log.append("close")


def _hash_without_record(board: Path) -> str:
    """What the record must equal: the file's SHA-256 with the record's own line left out."""
    kept = [line for line in board.read_bytes().splitlines(keepends=True) if pcb.RECORD.encode() not in line]
    return hashlib.sha256(b"".join(kept)).hexdigest()


class PcbDecorator(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-pcb-decorator-")
        self.addCleanup(self._tempdir.cleanup)
        self.root = Path(self._tempdir.name).resolve()
        (self.root / "blinky.py").write_text(SCRIPT, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("blinky_script", self.root / "blinky.py")
        self.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.script)
        self.log: list = []
        self.rows = [_row("Resistor_SMD"), _row("my")]
        self.kicad = FakeKiCad(self.log, self.rows)
        self.connections: list[dict] = []

        def connect(cli, settings):
            self.connections.append({"cli": cli, "settings": settings, "exists": settings.is_dir(),
                                     "config_home": os.environ.get("KICAD_CONFIG_HOME")})
            return self.kicad

        def run_drc(cli, board):
            self.log.append(("drc", cli, board, board.is_file()))
            return list(FINDINGS)

        self.real_connect = pcb.connect
        self.enterContext(mock.patch.object(pcb, "connect", connect))
        self.enterContext(mock.patch("cadgen.kicad.cli.run_drc", run_drc))
        self.enterContext(mock.patch("cadgen.kipy.board.Board", self.kicad.make_board))
        self.enterContext(mock.patch("cadgen.kicad.install.find_kicad_cli", return_value=Path("/fake/kicad-cli")))
        self.enterContext(mock.patch.dict(os.environ, {}, clear=False))
        os.environ.pop("KICAD_CONFIG_HOME", None)

    def _build(self, function, *flags: str):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["blinky.py", *flags]), contextlib.redirect_stdout(out):
            result = function()
        return result, out.getvalue()

    def test_the_build_sequence_the_files_and_the_report(self) -> None:
        result, printed = self._build(self.script.blinky)
        board = str(self.root / "blinky.kicad_pcb")
        record = _hash_without_record(Path(board))
        self.assertEqual(
            [("create_document", board, DocumentType.DOCTYPE_PCB), ("load_all_libraries", [LibraryType.LT_FOOTPRINT]),
             ("wait_for_libraries", [LibraryType.LT_FOOTPRINT]), ("Board", "the client", ("document", board)),
             "refill_zones", "save", ("set_text_variables", {pcb.RECORD: record}), "save",
             ("close_document", ("document", board)), "close",
             ("drc", Path("/fake/kicad-cli"), Path(board), True)],
            self.log,
        )
        self.assertEqual([self.kicad.boards[0]], self.script.seen)
        self.assertEqual((Path(board), self.root / "blinky.kicad_pro"), (result.board, result.project))
        self.assertEqual((2, 3, 1, 1, 1), (result.parts, result.tracks, result.vias, result.zones, result.unconnected))
        self.assertEqual(pcb.DrcReport(errors=1, warnings=1, findings=FINDINGS), result.drc)
        line, *findings = printed.splitlines()
        self.assertRegex(line, r"blinky\.kicad_pcb: 2 parts, 3 tracks, 1 via, 1 zone, 1 unconnected, DRC 1 error 1 warning, \d+\.\d s$")
        self.assertEqual(line, result.report())
        # The findings as `cadgen pcb drc` prints them, errors first.
        self.assertEqual(
            ["error: clearance at (8, -5) mm: Clearance violation (0.1 mm < 0.15 mm): Track [LED] on F.Cu; Pad 1 [GND] of D1",
             "warning: track_dangling: Track has unconnected end: Track [GND] on F.Cu"],
            findings,
        )
        self.assertEqual(findings, result.drc.lines())

    def test_no_drc_skips_the_check_and_its_counts(self) -> None:
        result, printed = self._build(self.script.blinky, "--no-drc")
        self.assertEqual("close", self.log[-1])
        self.assertIsNone(result.drc)
        self.assertRegex(printed, r"blinky\.kicad_pcb: 2 parts, 3 tracks, 1 via, 1 zone, 1 unconnected, \d+\.\d s\n$")

    def test_the_record_covers_the_saved_board_and_a_rebuild_passes_it(self) -> None:
        self._build(self.script.blinky)
        board = self.root / "blinky.kicad_pcb"
        recorded, actual = pcb.signature(board)
        self.assertEqual((_hash_without_record(board), _hash_without_record(board)), (recorded, actual))
        self.assertIn(f'(property "{pcb.RECORD}" "{recorded}")', board.read_text(encoding="utf-8"))
        # The rebuild's first save carries the previous record and the second the new one; the
        # hash leaves that line out, so the board of a rebuild verifies as well.
        self.log.clear()
        self._build(self.script.blinky)
        self.assertEqual(2, self.log.count("save"))
        self.assertEqual(pcb.signature(board)[0], pcb.signature(board)[1])

    def test_a_board_something_else_saved_is_refused_unless_forced(self) -> None:
        self._build(self.script.blinky)
        board = self.root / "blinky.kicad_pcb"
        with board.open("a", encoding="utf-8") as handle:
            handle.write("\t(gr_text \"by hand\")\n")
        edited = board.read_bytes()
        self.log.clear()
        with self.assertRaisesRegex(pcb.BoardError, r"blinky\.kicad_pcb was last saved by something other than this script .*: pass --force to overwrite it$"):
            self._build(self.script.blinky)
        self.assertEqual(([], edited), (self.log, board.read_bytes()), "nothing started, nothing written")
        # No record at all -- a board another tool wrote at that path -- is the same refusal.
        board.write_text('(kicad_pcb (version 20260901) (generator "pcbnew"))\n', encoding="utf-8")
        with self.assertRaisesRegex(pcb.BoardError, "pass --force"):
            self._build(self.script.blinky)
        _, printed = self._build(self.script.blinky, "--force")
        self.assertIn("blinky.kicad_pcb: 2 parts", printed)
        self.assertEqual(pcb.signature(board)[0], pcb.signature(board)[1])

    def test_a_script_run_reports_a_failure_as_one_line(self) -> None:
        # Declared in the script being run, a build's failure is the script's: one FAILED line
        # on stderr and exit 1, as a @step script's is. Imported (every other test here), the
        # exception is the caller's.
        self.script.broken.__wrapped__.__module__ = "__main__"
        err = io.StringIO()
        with mock.patch.object(sys, "argv", ["blinky.py"]), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stopped:
            self.script.broken()
        self.assertEqual(1, stopped.exception.code)
        self.assertRegex(err.getvalue(), r"^\[python blinky\.py\] FAILED: ValueError: no such part\n")
        self.assertNotIn("Traceback", err.getvalue())

    def test_the_server_gets_a_settings_directory_for_exactly_its_lifetime(self) -> None:
        self._build(self.script.blinky)
        [connection] = self.connections
        self.assertEqual(Path("/fake/kicad-cli"), connection["cli"])
        self.assertTrue(connection["exists"])
        self.assertFalse(connection["settings"].exists(), "the settings directory outlives the build")

    def test_connect_hands_the_settings_directory_to_the_server_as_its_config_home(self) -> None:
        # The real seam: kicad-python's server inherits this process's environment, so the
        # variable is set for the start and restored, whichever way the start ends.
        seen = []

        def fake_kicad(**kwargs):
            seen.append((kwargs, os.environ.get("KICAD_CONFIG_HOME")))
            if kwargs["kicad_cli_path"].endswith("broken"):
                raise TimeoutError("no api-server")
            return "client"

        os.environ["KICAD_CONFIG_HOME"] = "/home/person/.config/kicad"
        with mock.patch("cadgen.kipy.KiCad", fake_kicad):
            self.assertEqual("client", self.real_connect(Path("/opt/kicad-cli"), Path("/tmp/settings")))
            with self.assertRaises(TimeoutError):
                self.real_connect(Path("/opt/broken"), Path("/tmp/settings"))
        self.assertEqual("/home/person/.config/kicad", os.environ["KICAD_CONFIG_HOME"])
        self.assertEqual(2, len(seen))
        for kwargs, config_home in seen:
            self.assertEqual(str(Path("/tmp/settings")), config_home)
            # The path is passed as a string, spelled as this platform spells it.
            self.assertEqual((True, Path("/opt")), (kwargs["headless"], Path(kwargs["kicad_cli_path"]).parent))

    def test_a_path_is_relative_to_the_script_and_names_a_board(self) -> None:
        result, _ = self._build(self.script.other)
        self.assertEqual(self.root / "boards" / "other.kicad_pcb", result.board)
        self.assertEqual(str(self.root / "boards" / "other.kicad_pcb"), self.log[0][1])
        self.assertTrue((self.root / "boards").is_dir())
        with self.assertRaisesRegex(ValueError, r"ends in \.kicad_pcb"):
            pcb(path="other.kicad_pro")

    def test_an_exception_in_the_function_stops_the_server_and_saves_nothing(self) -> None:
        with self.assertRaisesRegex(ValueError, "no such part"):
            self._build(self.script.broken)
        self.assertNotIn("save", self.log)
        self.assertEqual("close", self.log[-1])
        self.assertFalse(any(self.root.glob("broken.*")))
        with self.assertRaisesRegex(TypeError, "takes no arguments"):
            self.script.blinky("board")

    def test_a_footprint_no_library_has_names_the_table_rows(self) -> None:
        with self.assertRaises(pcb.BoardError) as caught:
            self._build(self.script.missing)
        self.assertIsInstance(caught.exception.__cause__, ApiError)
        message = str(caught.exception)
        for text in ("footprint 'LED_SMD:LED_0603' not found", str(self.root / "fp-lib-table"),
                     "loaded Resistor_SMD (LLS_LOADED), my (LLS_LOADED)"):
            self.assertIn(text, message)
        self.assertNotIn("save", self.log)

    def test_a_table_row_that_did_not_load_is_refused_before_the_function_runs(self) -> None:
        self.rows.append(_row("broken", LibraryLoadStatus.LLS_ERROR, "Footprint library 'nowhere.pretty' not found."))
        with self.assertRaisesRegex(pcb.BoardError, r"fp-lib-table: broken: LLS_ERROR, Footprint library 'nowhere.pretty' not found"):
            self._build(self.script.blinky)
        self.assertEqual([], self.script.seen)
        self.assertNotIn("save", self.log)

    def test_a_kicad_below_the_minimum_is_refused_by_name(self) -> None:
        self.kicad.version = (10, 0, 7)
        with self.assertRaisesRegex(KicadMissingError, r"kicad-cli is KiCad 10\.0\.7; cadgen needs KiCad 10\.99"):
            self._build(self.script.blinky)
        self.assertEqual(["close"], self.log)
        with mock.patch.object(pcb, "connect", side_effect=TimeoutError("no api-server")):
            with mock.patch("cadgen.kicad.install.kicad_version", return_value="10.0.7"):
                with self.assertRaisesRegex(KicadMissingError, r"is KiCad 10\.0\.7"):
                    self._build(self.script.blinky)
            with mock.patch("cadgen.kicad.install.kicad_version", return_value="10.99.0"):
                with self.assertRaisesRegex(RuntimeError, r"\(KiCad 10\.99\.0\) could not start its API server: no api-server"):
                    self._build(self.script.blinky)


if __name__ == "__main__":
    unittest.main()
