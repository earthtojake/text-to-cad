"""A real ``@kicad_pcb`` round trip: kicode's headless api-server, its KiPy and kicad-cli's STEP.

The board is the test's own (``tests/python/support/kicad_board.py``, in a KiCad nightly's format), written
into a temporary folder; the script, run by the Python of the environment of ``cad[kicad]`` as ``cad run``
runs one (``tests/python/support/kicode.py``), reads it through KiPy, the board is saved, and the ``@step``
stacked on it is written from the saved board, as a ``@glb`` and a ``@dxf`` are. Runs in the KiCad job; anywhere the environment cannot be
made it says why it skips.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import kicode



def _servers_of(board: Path) -> list[str]:
    """The running ``kicad-cli api-server`` processes serving ``board``."""
    listed = subprocess.run(["ps", "-axww", "-o", "command"], capture_output=True, text=True, check=True).stdout
    return [line for line in listed.splitlines() if "api-server" in line and str(board) in line]


# A board script in a process of its own: it says "ready" from inside its function, then waits there.
WAITING = textwrap.dedent("""
    import sys, time
    from cad import kicad_pcb
    from cad.kicad._session import run

    @kicad_pcb(sys.argv[1])
    def waits(board):
        print("ready", flush=True)
        time.sleep(120)

    run(waits)
""")

# The round trip: the parts KiPy reads, the board saved, the STEP stacked on it written from it.
ROUND_TRIP = textwrap.dedent("""
    import json, sys
    from pathlib import Path
    from cad import kicad_pcb, step
    from cad.kicad._session import _format_of, run

    seen = []

    @step(str(Path(sys.argv[1]).parent / "STEP" / "board.step"))
    @kicad_pcb(sys.argv[1])
    def script(opened):
        seen.append(sorted(footprint.reference_field.text.value for footprint in opened.get_footprints()))

    before = _format_of(Path(sys.argv[1]))
    ran = run(script)
    print(json.dumps({"seen": seen, "board": str(ran.board), "written": [str(path) for path in ran.written],
                      "before": before, "after": _format_of(ran.board)}))
""")


class BoardScriptRoundTrip(unittest.TestCase):
    def test_a_board_script_reads_saves_and_exports_its_board(self):
        from tests.python.support.kicad_board import write_board

        with tempfile.TemporaryDirectory(prefix="kicad-script-") as folder:
            board = write_board(Path(folder))
            done = kicode.run_python(self, ROUND_TRIP, str(board), cwd=folder)
            self.assertEqual(0, done.returncode, done.stderr)
            ran = json.loads(done.stdout.strip().splitlines()[-1])
            self.assertEqual([["D1", "J1", "R1"]], ran["seen"])
            # Saved in the format of the KiCad that ran it: said when that is not the board's own.
            self.assertEqual(ran["before"] != ran["after"], "is saved in the board format" in done.stderr, done.stderr)
            self.assertEqual(str(board), ran["board"])
            (step_file,) = [Path(path) for path in ran["written"]]
            self.assertTrue(step_file.read_text(encoding="utf-8", errors="replace").startswith("ISO-10303-21"))
            from cad.kicad_pcb import inspect

            self.assertEqual(3, inspect(board)["counts"]["parts"], "the saved board reads as it did")

    def test_a_glb_and_a_dxf_stacked_on_a_board_script_are_written_from_its_saved_board(self):
        """``@glb`` and ``@dxf`` on a board script, as ``@step``: kicad-cli's GLB of the board and its parts, and
        its outline and holes, written from the board the script saved."""
        from tests.python.support.kicad_board import write_board

        with tempfile.TemporaryDirectory(prefix="kicad-script-files-") as folder:
            board = write_board(Path(folder))
            done = kicode.run_python(self, FILES, str(board), cwd=folder)
            self.assertEqual(0, done.returncode, done.stderr)
            written = [Path(path) for path in json.loads(done.stdout.strip().splitlines()[-1])]
            self.assertEqual(["board.glb", "board.dxf"], [path.name for path in written])
            glb, dxf = written
            self.assertEqual(b"glTF", glb.read_bytes()[:4])
            drawing = dxf.read_text(encoding="utf-8", errors="replace")
            self.assertIn("ENTITIES", drawing)
            self.assertIn("Edge.Cuts", drawing.replace("Edge_Cuts", "Edge.Cuts"))
            self.assertEqual(["board.dxf", "board.glb"], sorted(path.name for path in (Path(folder) / "out").iterdir()),
                             "each file where it was declared, and nothing of kicad-cli's beside it")


# Two files stacked on a script that edits nothing: written from the board it saved.
FILES = textwrap.dedent("""
    import json, sys
    from pathlib import Path
    from cad import dxf, glb, kicad_pcb
    from cad.kicad._session import run

    out = Path(sys.argv[1]).parent / "out"

    @glb(str(out / "board.glb"))
    @dxf(str(out / "board.dxf"))
    @kicad_pcb(sys.argv[1])
    def script(opened):
        pass

    print(json.dumps([str(path) for path in run(script).written]))
""")


@unittest.skipIf(sys.platform.startswith("win"), "POSIX signals and Unix socket paths")
class BoardScriptProcess(unittest.TestCase):
    def test_sigterm_stops_the_api_server(self):
        from tests.python.support.kicad_board import write_board

        with tempfile.TemporaryDirectory(prefix="kicad-term-") as folder:
            board = write_board(Path(folder))
            script = subprocess.Popen([kicode.python(self), "-c", WAITING, str(board)], cwd=folder,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                line = script.stdout.readline().strip()
                if line != "ready":  # the script failed: what it said is only read once it has exited
                    script.kill()
                    self.fail(f"the board script did not start: {script.stderr.read()}")
                self.assertTrue(_servers_of(board), "the api-server runs while the function does")
                script.send_signal(signal.SIGTERM)
                self.assertEqual(128 + signal.SIGTERM, script.wait(timeout=60))
                self.assertEqual([], _servers_of(board))
            finally:
                if script.poll() is None:
                    script.kill()
                    script.wait()
                script.stdout.close()
                script.stderr.close()

    def test_a_deep_temporary_folder_still_serves(self):
        from tests.python.support.kicad_board import write_board

        with tempfile.TemporaryDirectory(prefix="kicad-deep-") as folder:
            board = write_board(Path(folder))
            deep = Path(folder) / ("t" * 60) / ("m" * 60)
            deep.mkdir(parents=True)
            code = WAITING.replace("time.sleep(120)", "pass")
            done = kicode.run_python(self, code, str(board), cwd=folder, env={**os.environ, "TMPDIR": str(deep)})
            self.assertEqual(0, done.returncode, done.stderr)
            self.assertEqual("ready", done.stdout.strip())


if __name__ == "__main__":
    unittest.main()
