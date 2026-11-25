"""``cad xbf <operation> ...``: the earlier spelling of ``cad model <operation> ...``, from the days an ``.xbf`` was
a document type of its own (``cad_server.cli.xbf``). It runs ``cad model`` itself, after one line on stderr saying it
is deprecated (none under ``--json``), and is otherwise byte for byte ``cad model``: its output, its ``--json`` and
its exit status. Unlisted. These are the tests a removal of the spelling deletes with it.
"""

from __future__ import annotations

import contextlib
import io
import unittest

from tests.python.support.paths import add_sources

add_sources()

import cad_server.cli as cli  # noqa: E402

DEPRECATED = "cad xbf: deprecated and will be removed: use cad model\n"


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exited:
            code = exited.code
    return code, out.getvalue(), err.getvalue()


class CadXbfRunsCadModel(unittest.TestCase):
    def test_it_is_answered_and_not_listed(self) -> None:
        self.assertIn("xbf", cli._UNLISTED)  # noqa: SLF001 - the table IS the subject
        self.assertEqual(cli.TYPE_COMMANDS["xbf"], "cad_server.cli.xbf")
        types = _run(["--help"])[1].split("document types, the files cad shows", 1)[1].split("\n\n", 1)[0]
        self.assertNotIn("xbf", [line.split()[0] for line in types.splitlines()[1:]])
        self.assertEqual(cli.resolve(["xbf", "export", "arm.xbf", "arm.glb"]), ("model export", ["arm.xbf", "arm.glb"]))

    def test_every_operation_is_the_model_s_with_one_line_more_on_stderr_but_under_json(self) -> None:
        from unittest import mock

        from cad_server.cli.document_types import OPERATIONS, operations_of

        for operation in operations_of("model"):
            ran: list[tuple[list[str], str]] = []

            def run(argv: list[str], prog: str) -> int:
                ran.append((argv, prog))
                print(f"ran {prog}")
                return 7

            for argv, said in ((["share/arm.xbf"], DEPRECATED), (["share/arm.xbf", "--json"], "")):
                with self.subTest(operation=operation, argv=argv), mock.patch.dict(OPERATIONS, {("model", operation): run}):
                    older, now = _run(["xbf", operation, *argv]), _run(["model", operation, *argv])
                    self.assertEqual(older, (now[0], now[1], said + now[2]))
                    self.assertEqual(older[:2], (7, f"ran cad model {operation}\n"))
                    self.assertEqual(ran[-2:], [(argv, f"cad model {operation}")] * 2)

    def test_a_refusal_is_the_model_s_own_byte_for_byte(self) -> None:
        argv = ["export", "no-such-file.xbf", "out.glb"]
        self.assertEqual(_run(["model", *argv]), (2, "", "cad model export: no such file: no-such-file.xbf\n"))
        self.assertEqual(_run(["xbf", *argv]), (2, "", DEPRECATED + "cad model export: no such file: no-such-file.xbf\n"))
        refused = '{"ok":false,"error":"no such file: no-such-file.xbf","reason":"not_found"}\n'
        self.assertEqual(_run(["xbf", *argv, "--json"]), (2, refused, ""))
        self.assertEqual(_run(["model", *argv, "--json"]), (2, refused, ""))
        # Its help is the model's, said under the model's name.
        older, now = _run(["xbf", "--help"]), _run(["model", "--help"])
        self.assertEqual(older, (now[0], now[1], DEPRECATED + now[2]))


if __name__ == "__main__":
    unittest.main()
