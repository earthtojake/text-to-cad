"""What a person's terminal gets on top of the plain lines of ``cad plugin install`` (``cad_server/plugin/terminal.py``:
``Screen``, ``play_logo``, ``Live``), unit by unit, and the command run in a pseudo-terminal on a computer of its own
(``tests/python/support/agent_apps.py``)."""

from __future__ import annotations

import io
import os
import re
import subprocess
import time
import unittest
import unittest.mock

from cad_server.plugin import computer, terminal
from tests.python.support.agent_apps import PluginRuns
from tests.python.support.paths import REPO_ROOT


class TerminalTests(unittest.TestCase):
    def test_the_logo_s_letters_are_the_brand_s(self) -> None:
        """The letters drawn are the brand logo's (its front faces in apps/docs/public/brand/logo-cad.svg, from the
        same profiles), and so is its oblique view: the top face shows the depth 0.84 right and 0.84 up."""
        svg = (REPO_ROOT / "apps/docs/public/brand/logo-cad.svg").read_text(encoding="utf-8")

        def corners(points):
            points = points[:-1] if points[0] == points[-1] else points
            return tuple(point for index, point in enumerate(points)
                         if (point[0] - points[index - 1][0]) * (points[(index + 1) % len(points)][1] - point[1])
                         != (point[1] - points[index - 1][1]) * (points[(index + 1) % len(points)][0] - point[0]))

        def number(text):
            value = float(text)
            return int(value) if value.is_integer() else value

        faces = set()
        for d in re.findall(r'<path d="(M[^"]+)" clip-rule="evenodd"', svg):
            faces.add(tuple(corners([tuple(number(part) for part in point.split(","))
                                     for point in loop.rstrip("Z").split("L")])
                            for loop in d[1:].split("M")))
        for letter in terminal.LOGO_LETTERS:
            self.assertIn(letter, faces)
        lift = terminal.LOGO_DEPTH * terminal.LOGO_SLANT
        self.assertIn(f'd="M0,0L{lift:g},-{lift:g}L', svg)

    def test_the_logo_is_sketched_extruded_and_ends_whole(self) -> None:
        for flat in (False, True):
            logo = terminal.Logo(4, flat=flat)
            frames = logo.frames()
            self.assertLess(len(frames) / terminal.LOGO_FPS, 2)  # it never holds up the install for long
            self.assertEqual(frames[-1], (logo.solid(), 0.0))
            colours = {colour for row in frames[-1][0] for colour in row}
            self.assertIn(terminal.LOGO_FLAT[4] if flat else terminal.LOGO_EDGE, colours)
            # Extruded, the logo covers more than its front faces do.
            covered = [sum(colour is not None for row in logo.solid(depth=depth) for colour in row) for depth in (0, 2)]
            self.assertLess(covered[0], covered[1])
            lines = terminal.half_blocks(frames[-1][0], truecolor=not flat)
            self.assertEqual(len(lines), (logo.height + 1) // 2)
            self.assertIn("38;2;" if not flat else "38;5;", lines[3])

    def test_only_a_person_s_terminal_gets_more_than_the_lines(self) -> None:
        class Tty(io.StringIO):
            def isatty(self) -> bool:
                return True

        here = computer.Here({"HOME": "/home/x", "TERM": "xterm-256color"}, platform="linux")
        self.assertTrue(terminal.Screen(here, Tty()).live)
        self.assertFalse(terminal.Screen(here, io.StringIO()).live)
        for extra in ({"NO_COLOR": ""}, {"TERM": "dumb"}, {"CI": "true"}):
            here = computer.Here({"HOME": "/home/x", "TERM": "xterm-256color", **extra}, platform="linux")
            self.assertFalse(terminal.Screen(here, Tty()).live, extra)

    def test_the_live_line_names_the_command_and_gives_way_to_printed_lines(self) -> None:
        here = computer.Here({"HOME": "/home/x", "TERM": "xterm"}, platform="linux")
        out = io.StringIO()
        live = terminal.Live(terminal.Screen(here, out), out, "/home/x")
        live.DELAY = 0
        live.start()
        live.begin("Codex")
        live.watch(["/usr/local/bin/codex", "plugin", "add", "/home/x/plugin"])
        deadline = time.monotonic() + 5
        while "Codex" not in out.getvalue() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertIn("codex plugin add ~/plugin", out.getvalue())
        print("Codex: updated", file=live)
        self.assertTrue(out.getvalue().endswith("\r\x1b[2KCodex: updated\n"))
        live.watch(None)  # a command that writes to the terminal itself: no line over it
        drawn = out.getvalue()
        time.sleep(0.3)
        self.assertEqual(out.getvalue(), drawn)
        live.close()
        self.assertTrue(out.getvalue().endswith("\x1b[?25h"))
        self.assertTrue(live.mark("Codex: updated", "updated").endswith("Codex: updated"))

    def test_what_the_terminal_was_shown_is_said_in_a_word(self) -> None:
        """For whoever counts a run: the colours it drew in, and what it showed of the logo."""
        class Tty(io.StringIO):
            def isatty(self) -> bool:
                return True

        class Sized(terminal.Screen):
            def __init__(self, here, stream, columns: int, rows: int) -> None:
                super().__init__(here, stream)
                self.shape = os.terminal_size((columns, rows))

            def size(self) -> os.terminal_size:
                return self.shape

        plain = computer.Here({"HOME": "/home/x", "TERM": "xterm-256color"}, platform="linux")
        true = computer.Here({**plain.environ, "COLORTERM": "truecolor"}, platform="linux")
        self.assertEqual([terminal.Screen(plain, io.StringIO()).colour, terminal.Screen(plain, Tty()).colour,
                          terminal.Screen(true, Tty()).colour], ["none", "256", "24bit"])
        with unittest.mock.patch.object(terminal.time, "sleep"):
            self.assertEqual([terminal.play_logo(Sized(true, Tty(), columns, rows), io.StringIO())
                              for columns, rows in ((80, 24), (80, 8), (20, 24))],
                             [terminal.PLAYED, terminal.STILL, terminal.NONE])


@unittest.skipIf(os.name == "nt", "the stand-ins are scripts run by their #! line, and a pseudo-terminal is POSIX's")
class InATerminalTests(PluginRuns):
    def run_in_terminal(self, **extra: str) -> str:
        """``cad plugin install`` run in a pseudo-terminal 80 by 24, as a person runs it: what the terminal was sent."""
        import pty

        command, environ = self.child("install", TERM="xterm-256color", COLUMNS="80", LINES="24", **extra)
        environ.pop("CI", None)
        leader, follower = pty.openpty()
        process = subprocess.Popen(command, env=environ, stdin=subprocess.DEVNULL, stdout=follower, stderr=follower)
        os.close(follower)
        received = b""
        while True:
            try:
                chunk = os.read(leader, 65536)
            except OSError:  # the terminal closed with the process
                break
            if not chunk:
                break
            received += chunk
        process.wait(timeout=120)
        os.close(leader)
        return received.decode("utf-8", "replace")

    def test_a_person_s_terminal_gets_the_logo_marks_and_a_live_line(self) -> None:
        self.programs("claude")
        shown = self.run_in_terminal(COLORTERM="truecolor")
        self.assertIn("\x1b[38;2;", shown)  # the logo, in 24-bit colour
        self.assertIn("text-to-cad", shown)
        self.assertIn("✓\x1b[0m Claude Code: installed", shown)
        self.assertTrue(shown.rstrip().endswith("\x1b[?25h"))  # the cursor given back
        self.assertIn("\x1b[38;5;", self.run_in_terminal())  # xterm's 256 colours
        plain = self.run_in_terminal(NO_COLOR="1")
        self.assertNotIn("\x1b", plain)
        self.assertIn("Claude Code: installed", plain)


if __name__ == "__main__":
    unittest.main()
