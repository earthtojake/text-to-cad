"""A real ``@kicad_pcb`` round trip: KiCad's headless api-server, kipy and kicad-cli's STEP, on a nightly.

The board is the test's own (``tests/python/support/kicad_board.py``, in a KiCad nightly's format), written
into a temporary folder; the script reads it through kipy, the board is saved, and the ``@step`` stacked
on it is written from the saved board. Runs in the KiCad job, which installs the nightly and the kicad
extra; anywhere without them it says why it skips.
"""

import contextlib
import io
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def _nightly(case: unittest.TestCase) -> Path:
    """The kicad-cli a board script runs (a nightly's, with api-server), and kipy; else the test skips."""
    from cad.kicad._program import KicadMissingError, find_kicad_cli, kicad_version, version_tuple

    try:
        import kipy  # noqa: F401
    except ImportError:
        case.skipTest("the kicad extra (kicad-python) is not installed")
    try:
        cli = find_kicad_cli()
    except KicadMissingError as error:
        case.skipTest(str(error))
    if version_tuple(kicad_version(cli) or "0")[:2] < (10, 99):
        case.skipTest("kicad-cli api-server is a KiCad nightly's (10.99)")
    return cli


def _servers_of(board: Path) -> list[str]:
    """The running ``kicad-cli api-server`` processes serving ``board``."""
    listed = subprocess.run(["ps", "-axww", "-o", "command"], capture_output=True, text=True, check=True).stdout
    return [line for line in listed.splitlines() if "api-server" in line and str(board) in line]


# A board script in a process of its own: it says "ready" from inside its function, then waits there.
WAITING = textwrap.dedent("""
    import sys, time
    from pathlib import Path
    from cad import kicad_pcb
    from cad.kicad._session import run

    @kicad_pcb(sys.argv[1])
    def waits(board):
        print("ready", flush=True)
        time.sleep(120)

    run(waits, cli=Path(sys.argv[2]))
""")


class BoardScriptRoundTrip(unittest.TestCase):
    def test_a_board_script_reads_saves_and_exports_its_board(self):
        cli = _nightly(self)
        from cad import kicad_pcb, step
        from cad.kicad._session import run
        from tests.python.support.kicad_board import write_board

        with tempfile.TemporaryDirectory(prefix="kicad-script-") as folder:
            board = write_board(Path(folder))
            seen = []

            @step(str(Path(folder) / "STEP" / "board.step"))
            @kicad_pcb(str(board))
            def script(opened):
                seen.append(sorted(footprint.reference_field.text.value for footprint in opened.get_footprints()))

            from cad.kicad._session import _format_of

            before = _format_of(board)
            said = io.StringIO()
            with contextlib.redirect_stderr(said):
                ran = run(script, cli=cli)
            self.assertEqual([["D1", "J1", "R1"]], seen)
            # Saved in the format of the KiCad that ran it: said when that is not the board's own.
            self.assertEqual(before != _format_of(board), "is saved in the board format" in said.getvalue(),
                             said.getvalue())
            self.assertEqual(board, ran.board)
            (step_file,) = ran.written
            self.assertTrue(step_file.read_text(encoding="utf-8", errors="replace").startswith("ISO-10303-21"))
            from cad.kicad_pcb import inspect

            self.assertEqual(3, inspect(board)["counts"]["parts"], "the saved board reads as it did")


@unittest.skipIf(sys.platform.startswith("win"), "POSIX signals and Unix socket paths")
class BoardScriptProcess(unittest.TestCase):
    def test_sigterm_stops_the_api_server(self):
        cli = _nightly(self)
        from tests.python.support.kicad_board import write_board

        with tempfile.TemporaryDirectory(prefix="kicad-term-") as folder:
            board = write_board(Path(folder))
            script = subprocess.Popen([sys.executable, "-c", WAITING, str(board), str(cli)], cwd=REPO,
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
        cli = _nightly(self)
        from tests.python.support.kicad_board import write_board

        with tempfile.TemporaryDirectory(prefix="kicad-deep-") as folder:
            board = write_board(Path(folder))
            deep = Path(folder) / ("t" * 60) / ("m" * 60)
            deep.mkdir(parents=True)
            code = WAITING.replace("time.sleep(120)", "pass")
            done = subprocess.run([sys.executable, "-c", code, str(board), str(cli)], cwd=REPO, capture_output=True,
                                  text=True, timeout=300, env={**os.environ, "TMPDIR": str(deep)})
            self.assertEqual(0, done.returncode, done.stderr)
            self.assertEqual("ready", done.stdout.strip())


if __name__ == "__main__":
    unittest.main()
