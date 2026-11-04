"""The KiCad board reader and ``cad.kicad_pcb`` import the standard library and each other alone.

A check script reads a board under ``cad run`` and the server plots one in its own process, where
the CAD kernel is not installed; KiCad is never required to read a board. Static, over the AST, so
a lazy or function-local import counts too. (Drawing a board, ``render/board.py``, is Pillow's and
outside this family.) ``cad.kicad_pcb.drc`` and ``export`` hand the board to the kicad integration,
imported when they run: its DRC and exports, which import nothing but the standard library and kicode's
names, and kicode only where kicad-cli is run.
"""

from __future__ import annotations

import ast
import sys
import unittest

from tests.python.support.paths import LIBRARY

SOURCE = LIBRARY / "src" / "cad"
FAMILY = sorted((SOURCE / "engine" / "formats" / "kicad").glob("*.py")) + [SOURCE / "kicad_pcb" / "__init__.py"]
OWN = "cad.engine.formats.kicad"


def imported(path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(OWN if node.level else node.module or "")
    return found


class KicadReaderIsStdlibPure(unittest.TestCase):
    def test_the_family_imports_the_standard_library_and_itself_alone(self) -> None:
        self.assertGreater(len(FAMILY), 8)
        offenders = sorted(f"{path.relative_to(SOURCE)}: {name}" for path in FAMILY for name in imported(path)
                           if name != "__future__" and name.partition(".")[0] not in sys.stdlib_module_names
                           and name != OWN and not name.startswith(OWN + ".")
                           and name not in ("cad._internal.document_type",  # cad.kicad_pcb is a DocumentType
                                            "cad.results", "cad.kicad._check", "cad.kicad._export",
                                            # poured's cache, under the board's document id
                                            "cad.engine.places", "cad.engine.atomic_replace", "cad.engine.ids"))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
