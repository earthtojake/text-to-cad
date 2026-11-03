"""The ``cad`` command's table, pinned: every document type's operations and every other command.

The shape is ``cad <document_type> <operation> <file>``, one id per type everywhere (the registry,
``cad.registry``), one set of operation names every type shares; the commands that are no
document's are the engine's process control, ``run`` and the installation's. A command added,
renamed or taken out is a change to what every agent reads, made here on purpose. The old
spellings are gone, a hard cutover: each answers as a command that never existed does.
"""

from __future__ import annotations

import contextlib
import io
import unittest

from tests.python.support.paths import add_sources

add_sources()

from cad.registry import DOCUMENT_TYPES  # noqa: E402

import cad_server.cli as cli  # noqa: E402
from cad_server.cli.document_types import operations_of, type_main  # noqa: E402

TYPES = {
    "xbf": ("export", "snapshot", "inspect"),
    "step": ("export", "snapshot", "inspect"),
    "stl": ("export", "snapshot"),
    "glb": ("export", "snapshot", "inspect"),
    "threemf": ("export", "snapshot"),
    "dxf": ("snapshot",),
    "urdf": ("snapshot", "check"),
    "srdf": ("snapshot", "check"),
    "sdf": ("snapshot", "check"),
    "kicad_pcb": ("export", "snapshot", "inspect", "check"),
}
COMMANDS = ("serve", "status", "stop", "delete", "server", "run", "requirement", "doctor", "setup", "update", "uninstall", "plugin",
            "viewer", "telemetry")


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class TheCommandTable(unittest.TestCase):
    def test_the_table_is_pinned(self) -> None:
        self.assertEqual(TYPES, {name: operations_of(name) for name in DOCUMENT_TYPES})
        self.assertEqual(sorted(TYPES), sorted(cli.TYPE_COMMANDS))
        self.assertEqual(sorted(COMMANDS), sorted(cli._COMMANDS))  # noqa: SLF001 - the table IS the subject
        for name, module in cli.TYPE_COMMANDS.items():
            self.assertEqual(f"cad_server.cli.{name}", module)

    def test_help_groups_the_commands_by_type(self) -> None:
        code, said, _ = _run(["--help"])
        self.assertEqual(0, code)
        self.assertIn("document types (cad <type> <operation> FILE):", said)
        self.assertRegex(said, r"\n  srdf +snapshot, check +SRDF: \.srdf\n")
        code, said, _ = _run(["step", "--help"])
        self.assertEqual(0, code)
        self.assertIn("operations:\n  export ", said)
        self.assertIn("(.step, .stp)", said)

    def test_a_file_of_another_type_is_refused_by_name(self) -> None:
        code, _, err = _run(["stl", "snapshot", "part.glb", "out.png"])
        self.assertEqual(2, code)
        self.assertIn("part.glb is a glb, not a stl: use cad glb snapshot", err)
        code, said, _ = _run(["urdf", "check", "robot.srdf", "--json"])
        self.assertEqual(1, code)
        self.assertIn('"error": "robot.srdf is a srdf, not a urdf: use cad srdf check"', said)

    def test_a_types_own_option_before_its_file_is_no_file(self) -> None:
        """``--urdf robot.urdf`` is srdf check's own option, wherever it stands: the file the check is of is
        the one the parser takes as its file, never the first word without a dash."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder:
            urdf, srdf = Path(folder) / "robot.urdf", Path(folder) / "robot.srdf"
            urdf.write_text('<robot name="r"><link name="a"/></robot>', encoding="utf-8")
            srdf.write_text('<robot name="r"><group name="arm"><link name="a"/></group></robot>', encoding="utf-8")
            for argv in (["srdf", "check", "--urdf", str(urdf), str(srdf)], ["srdf", "check", str(srdf), "--urdf", str(urdf)]):
                with self.subTest(argv=argv):
                    code, said, err = _run([*argv, "--json"])
                    self.assertNotIn("is a urdf, not a srdf", said + err)
                    self.assertIn('"path"', said)
            code, said, _ = _run(["srdf", "check", "--urdf", str(urdf), str(urdf), "--json"])
            self.assertEqual(1, code)
            self.assertIn("is a urdf, not a srdf", said)

    def test_an_operation_a_type_lacks_names_the_ones_it_has(self) -> None:
        code, _, err = _run(["stl", "inspect", "part.stl"])
        self.assertEqual(2, code)
        self.assertIn("cad stl has no operation 'inspect'; it has export, snapshot", err)
        self.assertEqual(2, type_main("dxf", ["export", "a.dxf"]))

    def test_the_old_spellings_are_commands_that_never_existed(self) -> None:
        for argv in (["export", "a.xbf", "a.step"], ["snapshot", "a.xbf", "a.png"], ["inspect", "a.xbf"]):
            with self.subTest(argv=argv):
                code, _, err = _run(argv)
                self.assertEqual(2, code)
                self.assertIn(f"cad: unknown command {argv[0]!r}", err)
        code, _, err = _run(["urdf", "validate", "robot.urdf"])
        self.assertEqual(2, code)
        self.assertIn("cad urdf has no operation 'validate'; it has snapshot, check", err)


if __name__ == "__main__":
    unittest.main()
