"""Real ``kicad_pcb.edit`` and ``kicad_sch.edit``: kicode's headless api-server and its KiPy, on files of the test's own.

The board is the test board (``tests/python/support/kicad_board.py``), the schematic a project with a symbol
library of its own (``tests/python/support/kicad_schematic.py``'s ``write_library_project``), each written
into a temporary folder. Each edit runs in the Python of the environment of ``cad[kicad]``, as ``cad run``
runs a script (``tests/python/support/kicode.py``), and the saved files are read back with the readers
(``kicad_pcb.read``, ``kicad_sch.read``), which need no KiCad. A changed file is saved and reads back
changed; a raise saves nothing; a block that changes nothing leaves the file byte for byte; a board and a
schematic of one project edited in one block share one server; a file not there yet is made; a symbol is
placed from the project's own library, and one the project lacks is refused in one line; copper KiCad takes
onto a pad's net as it saves is said, with the pad, and a net the block set is not. Runs in the KiCad job;
anywhere the environment cannot be made it says why it skips.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import kicode
from tests.python.support.kicad_board import write_board
from tests.python.support.kicad_schematic import write_library_project

# The API servers running on this machine for files in ``folder`` (``ps``): kicad-cli's, by the command each runs.
SERVERS = textwrap.dedent("""
    import subprocess

    def servers(folder):
        listed = subprocess.run(["ps", "-axww", "-o", "command"], capture_output=True, text=True, check=True).stdout
        return [line for line in listed.splitlines()
                if line.split(" ", 1)[0].endswith("kicad-cli") and "api-server" in line and folder in line]
""")

# The VBUS track made 0.8 mm wide (it is saved 1 mm); with "raise", an exception after the change.
WIDENED = textwrap.dedent("""
    import json, sys
    from cad import kicad_pcb
    from kicode.util.units import from_mm

    try:
        with kicad_pcb.edit(sys.argv[1]) as b:
            power = [track for track in b.get_tracks() if track.net.name == "VBUS"]
            for track in power:
                track.width = from_mm(0.8)
            b.update_items(power)
            if sys.argv[2] == "raise":
                raise RuntimeError("after the change")
        print(json.dumps({"changed": len(power)}))
    except RuntimeError as error:
        print(json.dumps({"raised": str(error)}))
""")

# Copper KiCad takes onto a pad's net: the block widens the VBUS track (so the board is saved) and gives a via clear
# of every pad the LED net, deliberately, then sends every via back as it reads them; its ground via through R1's
# VBUS pad, and the polygon joined to it, it does not touch. What the edit found is printed.
VIA, RING, LONE = ("7a1c0000-0000-4000-8000-0000000000a1", "7a1c0000-0000-4000-8000-0000000000a2",
                   "7a1c0000-0000-4000-8000-0000000000a3")
ON_A_PAD = (f'(via (at 34.175 15) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "GND") (uuid "{VIA}"))'
            f'(gr_poly (pts (xy 33.5 14) (xy 35.5 14) (xy 35.5 16) (xy 33.5 16)) (stroke (width 0) (type solid))'
            f' (fill yes) (layer "B.Cu") (net "GND") (uuid "{RING}"))'
            f'(via (at 30 5) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "GND") (uuid "{LONE}"))')
DRIFTED = textwrap.dedent("""
    import json, sys
    from cad import kicad_pcb
    from kicode.util.units import from_mm

    with kicad_pcb.edit(sys.argv[1]) as b:
        power = [track for track in b.get_tracks() if track.net.name == "VBUS"]
        for track in power:
            track.width = from_mm(0.8)
        b.update_items(power)
        led = next(net for net in b.get_nets() if net.name == "LED")
        lone = next(via for via in b.get_vias() if via.id.value == sys.argv[2])
        lone.net = led
        b.update_items(lone)
        b.update_items(list(b.get_vias()))  # every via sent back as read: the moved one's new net is not asked for
    print(json.dumps([change.as_data() for change in b.net_changes]))
""")

# Blocks that change nothing: a board's and a schematic's, each only read.
READS = textwrap.dedent("""
    import json, sys
    from cad import kicad_pcb, kicad_sch

    with kicad_pcb.edit(sys.argv[1]) as b:
        parts = sorted(footprint.reference_field.text.value for footprint in b.get_footprints())
    with kicad_sch.edit(sys.argv[2]) as s:
        symbols = len(s.get_symbols())
    print(json.dumps({"parts": parts, "symbols": symbols}))
""")

# Two resistors from the project's own library, R1's pin 2 wired to R2's pin 1 (a pin's place on the sheet is
# the symbol's position plus the pin's, unrotated).
WIRED = textwrap.dedent("""
    import sys
    from cad import kicad_sch
    from kicode.geometry import Vector2
    from kicode.schematic_types import SchematicLine, SchematicLineType

    def pin_at(symbol, number):
        pin = next(pin for pin in symbol.definition.pins if pin.number == number)
        return symbol.position + pin.position

    with kicad_sch.edit(sys.argv[1]) as s:
        r1 = s.place_symbol_from_library("parts:R", Vector2.from_xy_mm(50.8, 50.8), reference="R1")
        r2 = s.place_symbol_from_library("parts:R", Vector2.from_xy_mm(50.8, 63.5), reference="R2")
        wire = SchematicLine()
        wire.type = SchematicLineType.SLT_WIRE
        wire.start, wire.end = pin_at(r1, "2"), pin_at(r2, "1")
        s.create_items(wire)
""")

# The schematic and the board of one project in one block: one server between them, each saved at its own
# block's end.
BOTH = SERVERS + textwrap.dedent("""
    import json, sys
    from cad import kicad_pcb, kicad_sch
    from kicode.geometry import Vector2
    from kicode.util.units import from_mm

    with kicad_sch.edit(sys.argv[1]) as s, kicad_pcb.edit(sys.argv[2]) as b:
        running = len(servers(sys.argv[3]))
        s.place_symbol_from_library("parts:R", Vector2.from_xy_mm(50.8, 50.8), reference="R1")
        power = [track for track in b.get_tracks() if track.net.name == "VBUS"]
        for track in power:
            track.width = from_mm(0.8)
        b.update_items(power)
    print(json.dumps({"running": running, "after": len(servers(sys.argv[3]))}))
""")

ELSEWHERE = textwrap.dedent("""
    import sys
    from cad import kicad_sch
    from kicode.geometry import Vector2

    try:
        with kicad_sch.edit(sys.argv[1]) as s:
            s.place_symbol_from_library("Device:R", Vector2.from_xy_mm(50.8, 50.8), reference="R1")
    except LookupError as error:
        print(error)
""")

# A sheet symbol made over IPC (its file not there yet): this nightly saves the root, then fails to save the new
# sheet, resolving its file against the root's file name; the edit's save is whole or none.
SHEET = textwrap.dedent("""
    import json, sys
    from cad import kicad_sch
    from kicode.geometry import Vector2
    from kicode.schematic_types import SheetSymbol

    try:
        with kicad_sch.edit(sys.argv[1]) as s:
            sheet = SheetSymbol()
            sheet.position, sheet.size = Vector2.from_xy_mm(50.8, 50.8), Vector2.from_xy_mm(25.4, 12.7)
            sheet.name_field.text.value = "Power"
            sheet.filename_field.text.value = "power.kicad_sch"
            s.create_items(sheet)
        print(json.dumps({"saved": True}))
    except RuntimeError as error:
        print(json.dumps({"raised": type(error).__name__, "said": str(error)}))
""")

# An edit in a process of its own: it says "ready" from inside its block, then waits there.
WAITING = textwrap.dedent("""
    import sys, time
    from cad import kicad_pcb

    with kicad_pcb.edit(sys.argv[1]) as b:
        print("ready", flush=True)
        time.sleep(120)
""")


def _files(folder: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(folder.iterdir()) if path.is_file()}


class Edits(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="kicad-edit-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def run_edit(self, code: str, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        done = kicode.run_python(self, code, *args, cwd=self.folder, **({"env": env} if env else {}))
        self.assertEqual(0, done.returncode, done.stderr)
        return done

    def last(self, done: subprocess.CompletedProcess) -> dict:
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_a_changed_board_is_saved_and_reads_back_changed(self) -> None:
        from cad import kicad_pcb

        board = write_board(self.folder)
        done = self.run_edit(WIDENED, str(board), "save")
        self.assertEqual({"changed": 1}, self.last(done))
        widths = {track.width for track in kicad_pcb.read(board).tracks if track.net == "VBUS"}
        self.assertEqual({0.8}, widths)
        self.assertEqual(3, kicad_pcb.inspect(board)["counts"]["parts"], "the rest of the board as it was")
        self.assertFalse(board.with_suffix(".kicad_prl").exists(), "no local settings left beside it")

    def test_a_raise_saves_nothing_and_a_block_that_changes_nothing_leaves_both_files_as_they_were(self) -> None:
        board = write_board(self.folder, "design")
        schematic = write_library_project(self.folder)
        before = _files(self.folder)
        self.assertEqual({"raised": "after the change"}, self.last(self.run_edit(WIDENED, str(board), "raise")))
        self.assertEqual(before, _files(self.folder))
        done = self.run_edit(READS, str(board), str(schematic))
        self.assertEqual({"parts": ["D1", "J1", "R1"], "symbols": 0}, self.last(done))
        self.assertEqual(before, _files(self.folder), "byte for byte, in their own formats, and nothing beside them")
        self.assertNotIn("is saved in the", done.stderr)

    def test_a_save_kicad_cannot_finish_leaves_every_file_as_it_was(self) -> None:
        schematic = write_library_project(self.folder)
        before = _files(self.folder)
        ran = self.last(self.run_edit(SHEET, str(schematic)))
        if ran.get("saved"):  # a KiCad that saves a sheet made over IPC: the hierarchy, whole
            self.assertTrue((self.folder / "power.kicad_sch").is_file())
            return
        self.assertEqual("KicadRunError", ran["raised"], ran)
        self.assertIn("KiCad could not save design.kicad_sch: failed to save schematic", ran["said"])
        self.assertEqual(before, _files(self.folder), "the root as it was, no new sheet file, nothing beside them")

    def test_copper_kicad_moves_onto_a_pads_net_is_said_and_what_the_block_set_is_not(self) -> None:
        from cad import kicad_pcb

        board = write_board(self.folder)
        board.write_text(board.read_text(encoding="utf-8").rstrip()[:-1] + ON_A_PAD + ")\n", encoding="utf-8")
        done = self.run_edit(DRIFTED, str(board), LONE)
        said = [(change["kind"], change["id"], change["was"], change["now"], change["pad"], change["joined"])
                for change in self.last(done)]
        self.assertEqual([("via", VIA, "GND", "VBUS", "#R1.1", None),
                          ("shape", RING, "GND", "VBUS", None, f"#via:{VIA}")], said)
        warned = [line for line in done.stderr.splitlines() if "KiCad saved" in line]
        self.assertEqual(2, len(warned), done.stderr)
        self.assertIn(f"KiCad saved via #via:{VIA} on VBUS, not GND: it overlaps pad #R1.1 of VBUS", warned[0])
        nets = {via.id: via.net for via in kicad_pcb.read(board).vias}
        self.assertEqual(("VBUS", "LED"), (nets[VIA], nets[LONE]), "the board as KiCad saved it; the block's net kept")

    def test_a_board_and_a_schematic_of_one_project_share_one_server(self) -> None:
        from cad import kicad_pcb, kicad_sch

        board = write_board(self.folder, "design")
        schematic = write_library_project(self.folder)
        ran = self.last(self.run_edit(BOTH, str(schematic), str(board), str(self.folder)))
        self.assertEqual({"running": 1, "after": 0}, ran)
        self.assertEqual(["R1"], list(kicad_sch.read(schematic).parts), "the schematic saved")
        self.assertEqual({0.8}, {track.width for track in kicad_pcb.read(board).tracks if track.net == "VBUS"},
                         "and the board")

    def test_symbols_placed_from_the_projects_library_and_wired_read_back_on_one_net(self) -> None:
        from cad import kicad_sch

        schematic = write_library_project(self.folder)
        self.run_edit(WIRED, str(schematic))
        read = kicad_sch.read(schematic)
        self.assertEqual(["R1", "R2"], sorted({pin.ref for pin in read.pins}))
        self.assertEqual({"1", "2"}, {pin.number for pin in read.pins if pin.ref == "R1"})
        net = read.resolve("#R1.2").net
        self.assertEqual(net, read.resolve("#R2.1").net)
        self.assertEqual({"R1.2", "R2.1"}, {f"{pin.ref}.{pin.number}" for pin in read.net(net).pins})
        self.assertIn('(lib_id "parts:R")', schematic.read_text(encoding="utf-8"), "each symbol keeps its library link")

    def test_a_library_the_project_lacks_is_one_line_naming_it(self) -> None:
        schematic = write_library_project(self.folder)
        said = self.run_edit(ELSEWHERE, str(schematic)).stdout.strip()
        self.assertEqual(1, len(said.splitlines()), said)
        self.assertIn("no symbol library 'Device' in this project's sym-lib-table", said)
        self.assertIn("which lists parts", said)

    def test_files_not_there_yet_are_made_with_their_project(self) -> None:
        from cad import kicad_pcb, kicad_sch

        schematic = write_library_project(self.folder / "new", schematic=False)
        done = self.run_edit(WIRED, str(schematic))
        self.assertIn(f"made {schematic}, a new schematic, and its project design.kicad_pro", done.stderr)
        self.assertTrue(schematic.with_suffix(".kicad_pro").is_file())
        self.assertEqual(["R1", "R2"], sorted(kicad_sch.read(schematic).parts))
        # Both of a new project in one block: one server, each made in it and saved, its project said once.
        board, other = self.folder / "pair" / "pair.kicad_pcb", self.folder / "pair" / "pair.kicad_sch"
        done = self.run_edit(textwrap.dedent("""
            import sys
            from cad import kicad_pcb, kicad_sch

            with kicad_sch.edit(sys.argv[1]) as s, kicad_pcb.edit(sys.argv[2]) as b:
                pass
        """), str(other), str(board))
        self.assertEqual(1, done.stderr.count("and its project pair.kicad_pro"), done.stderr)
        self.assertEqual(["pair.kicad_pcb", "pair.kicad_pro", "pair.kicad_sch"], sorted(_files(board.parent)))
        self.assertEqual(0, kicad_pcb.inspect(board)["counts"]["parts"])
        self.assertEqual((), kicad_sch.read(other).parts)

    @unittest.skipIf(sys.platform.startswith("win"), "POSIX signals and Unix socket paths")
    def test_sigterm_stops_the_api_server(self) -> None:
        board = write_board(self.folder)
        script = subprocess.Popen([kicode.python(self), "-c", WAITING, str(board)], cwd=self.folder,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        servers = {}
        exec(SERVERS, servers)  # noqa: S102 - the test's own helper, shared with the edits it runs
        try:
            line = script.stdout.readline().strip()
            if line != "ready":  # the edit failed: what it said is only read once it has exited
                script.kill()
                self.fail(f"the edit did not start: {script.stderr.read()}")
            self.assertTrue(servers["servers"](str(board)), "the api-server runs while the block does")
            script.send_signal(signal.SIGTERM)
            self.assertEqual(128 + signal.SIGTERM, script.wait(timeout=60))
            self.assertEqual([], servers["servers"](str(board)))
        finally:
            if script.poll() is None:
                script.kill()
                script.wait()
            script.stdout.close()
            script.stderr.close()

    @unittest.skipIf(sys.platform.startswith("win"), "Unix socket paths")
    def test_a_deep_temporary_folder_still_serves(self) -> None:
        board = write_board(self.folder)
        deep = self.folder / ("t" * 60) / ("m" * 60)
        deep.mkdir(parents=True)
        done = self.run_edit(WAITING.replace("time.sleep(120)", "pass"), str(board), env={**os.environ, "TMPDIR": str(deep)})
        self.assertEqual("ready", done.stdout.strip())


if __name__ == "__main__":
    unittest.main()
