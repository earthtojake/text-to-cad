"""``cad xbf <operation> FILE``: the older spelling of ``cad model <operation> FILE.xbf``, answered and listed
nowhere (``cad_server.cli.xbf``). It is ``cad model`` under that name, which the other tests cover on its own;
these are the tests a removal of the older spelling deletes with it.
"""

from __future__ import annotations

import contextlib
import io
import unittest

from tests.python.support.paths import add_sources

add_sources()

import cad_server.cli as cli  # noqa: E402


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exited:
            code = exited.code
    return code, out.getvalue(), err.getvalue()


class CadXbfIsCadModel(unittest.TestCase):
    def test_it_is_answered_and_not_listed(self) -> None:
        self.assertIn("xbf", cli._UNLISTED)  # noqa: SLF001 - the table IS the subject
        self.assertEqual(cli.TYPE_COMMANDS["xbf"], "cad_server.cli.xbf")
        types = _run(["--help"])[1].split("document types, the files cad shows", 1)[1].split("\n\n", 1)[0]
        self.assertNotIn("xbf", [line.split()[0] for line in types.splitlines()[1:]])
        self.assertEqual(cli.resolve(["xbf", "export", "arm.xbf", "arm.glb"]), ("model export", ["arm.xbf", "arm.glb"]))

    def test_every_operation_is_the_model_s_given_the_same_command_line(self) -> None:
        from unittest import mock

        from cad_server.cli.document_types import OPERATIONS, operations_of

        for operation in operations_of("model"):
            ran: list[tuple[list[str], str]] = []

            def run(argv: list[str], prog: str) -> int:
                ran.append((argv, prog))
                return 7

            argv = ["share/arm.xbf", "--json"]
            with self.subTest(operation=operation), mock.patch.dict(OPERATIONS, {("model", operation): run}):
                self.assertEqual([_run(["xbf", operation, *argv])[0], _run(["model", operation, *argv])[0]], [7, 7])
                self.assertEqual(ran, [(argv, f"cad xbf {operation}"), (argv, f"cad model {operation}")])
        # Unpatched: the same refusal, under its own name.
        self.assertEqual(_run(["xbf", "export", "no-such-file.xbf", "out.glb"]),
                         (2, "", "cad xbf export: no such file: no-such-file.xbf\n"))


if __name__ == "__main__":
    unittest.main()
