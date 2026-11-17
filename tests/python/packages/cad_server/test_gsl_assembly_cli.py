"""``cad gsl fit`` and ``cad gsl bake`` given an assembly alone: what they read first, checked before anything runs.

With the exact parts named, the first source is a ``.gsl`` as any GSL operation's; alone, it is the assembly that
names its concepts, a document id or an ``.xbf``, and anything else is refused by name.
"""

from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

ID = "48dd0951-1525-5504-9181-488c12975bd4"


class WhatIsReadFirst(unittest.TestCase):
    def check(self, path: str, exact: str | None = None, operation: str = "fit") -> None:
        from cad_server.cli.document_types import _concept_or_assembly

        _concept_or_assembly(operation, argparse.Namespace(path=path, exact=exact))

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.folder, ignore_errors=True))

    def test_an_assembly_alone_is_a_document_id_or_an_xbf_that_is_there(self) -> None:
        self.check(ID)
        held = self.folder / "device.xbf"
        held.write_bytes(b"")
        self.check(str(held), operation="bake")

    def test_anything_else_alone_is_refused_by_name(self) -> None:
        from cad_server._internal.cli_errors import Failure

        for given in ("device.py", str(self.folder / "enclosure.gsl"), "device.step"):
            with self.assertRaisesRegex(Failure, "alone is no assembly: cad gsl fit takes a .gsl concept and the exact parts"):
                self.check(given)
        with self.assertRaisesRegex(Failure, "gone.xbf is not there"):
            self.check(str(self.folder / "gone.xbf"))

    def test_with_the_exact_parts_named_the_first_is_a_gsl_as_ever(self) -> None:
        from cad_server._internal.cli_errors import Failure

        concept = self.folder / "enclosure.gsl"
        concept.write_text("return length(p) - 1.0;\n", encoding="utf-8")
        self.check(str(concept), ID)
        with self.assertRaisesRegex(Failure, "is a model's document id, not a .gsl file"):
            self.check(ID, ID)

    def test_the_exact_parts_are_optional_in_both_commands(self) -> None:
        from cad_server._internal.cli_from_function import generated_parser

        for operation in ("fit", "bake"):
            parsed = generated_parser(("cad.gsl", operation), prog=f"cad gsl {operation}").parse_args([ID])
            self.assertEqual((ID, None), (str(parsed.path), parsed.exact))


if __name__ == "__main__":
    unittest.main()
