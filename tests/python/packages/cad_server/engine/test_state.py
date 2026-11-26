"""The state folder's own (``engine/state.py``): what the cache derives of a file lives under its document and
goes when it is forgotten, and the engine's record reads a port alone. And the declarations: a function in a
saved file points; one in no file is refused, with the words that hand its shape over instead."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

from cad.engine.model import Model  # noqa: E402


class StateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = Path(os.path.realpath(tempfile.mkdtemp(prefix="state-")))
        self.addCleanup(shutil.rmtree, self.state, True)

    def test_a_file_s_derived_views_live_under_its_document_keyed_by_its_bytes(self) -> None:
        """A KiCad board's plot, refilled pours, DRC and kept exports are kept in the document cache under the
        board's own document, keyed by its bytes: a changed file is a new entry."""
        from cad.engine.formats.kicad import poured
        from cad.engine.ids import file_id
        cache = self.state / "cache"
        board = self.state / "board.kicad_pcb"
        board.write_text("(kicad_pcb (version 20241229))", encoding="utf-8")
        with mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(cache)}):
            first = poured.folder(board, poured.key(board))
            self.assertEqual(first, cache / "documents" / file_id(board) / "kicad" / poured.key(board))
            first.mkdir(parents=True)
            (first / "drc.json").write_text("{}", encoding="utf-8")
            board.write_text("(kicad_pcb (version 20241229) (general))", encoding="utf-8")
            self.assertNotEqual(poured.folder(board, poured.key(board)), first, "a changed file is a new entry")

    def test_an_engine_record_reads_only_a_port_number(self) -> None:
        from cad_server.engine import state

        engines = self.state / state.ENGINES
        engines.mkdir(parents=True, exist_ok=True)
        for port, read in ((3246, {"port": 3246}), (True, {}), ("3246", {}), (70000, {}), (3246.0, {})):
            (engines / "abc123.json").write_text(json.dumps({"schema": state.ENGINE_SCHEMA, "port": port}),
                                                 encoding="utf-8")
            self.assertEqual(state.State(self.state).engine("abc123"), read, port)


class StoreTest(unittest.TestCase):
    """What a declaration makes of a function: a document from its file, through one declaration."""

    def define(self, source: str, filename: str) -> Model:
        namespace: dict = {"__name__": "__main__"}
        exec(compile(source, filename, "exec"), namespace)  # noqa: S102
        return namespace["cell"]

    def test_a_saved_file_points_and_a_function_in_no_file_is_refused_with_the_shape_form(self) -> None:
        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="store-")))
        self.addCleanup(shutil.rmtree, folder, True)
        source = "from cad.engine import model\n\n@model\ndef cell():\n    return None\n"
        saved = folder / "cell.py"
        saved.write_text(source, encoding="utf-8")
        self.assertEqual(self.define(source, str(saved)).name, "cell")
        self.assertFalse(hasattr(self.define(source, str(saved)), "store"), "no store to choose")
        for nowhere in ("<stdin>", str(folder / "ipykernel_1" / "2.py")):  # a REPL's, a notebook cell's
            with self.subTest(file=nowhere), self.assertRaisesRegex(ValueError, r"xbf\(shape, name='cell'\)"):
                self.define(source, nowhere)
        # store= is gone: an unexpected keyword argument, as any name that never was (law 14).
        for given in ("@model(store='memory')", "@model('XBF/cell.xbf', store='memory')"):
            with self.subTest(given=given), self.assertRaisesRegex(
                    TypeError, r"^(model|xbf)\(\) got an unexpected keyword argument 'store'$"):
                self.define(source.replace("@model", given), str(saved))
        self.assertEqual(self.define(source.replace("@model", "@model(name='other')"), str(saved)).explicit_name, "other")

    def test_model_stacks_with_file_decorators_and_one_kind_twice_is_refused(self) -> None:
        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="store-")))
        self.addCleanup(shutil.rmtree, folder, True)
        saved = folder / "cell.py"
        saved.write_text("", encoding="utf-8")
        # Each declaration adds its file: bare @model its .xbf beside the script, beside the others'.
        for stack, files in (("@step('cell.step')\n@model", ["cell.xbf", "cell.step"]),
                             ("@glb('a.glb')\n@model\n@stl('a.stl')", ["cell.xbf", "a.glb", "a.stl"])):
            with self.subTest(stack=stack):
                made = self.define(f"from cad.engine import model, step, glb, stl\n\n{stack}\ndef cell():\n"
                                   "    return None\n", str(saved))
                self.assertEqual([path.name for _kind, path in made.targets()], files)
        # Its own .xbf twice, bare or given: nothing says which is the model's.
        for stack in ("@model\n@model('XBF/cell.xbf')", "@model('XBF/cell.xbf')\n@model", "@model('a.xbf')\n@model('b.xbf')"):
            with self.subTest(stack=stack), self.assertRaisesRegex(
                    TypeError, r"^model 'cell' declares its \.xbf twice: keep one @xbf$"):
                self.define(f"from cad.engine import model\n\n{stack}\ndef cell():\n    return None\n", str(saved))
        both = self.define("from cad.engine import model, step\n\n@model('XBF/cell.xbf')\n@step('cell.step')\n"
                           "def cell():\n    return None\n", str(saved))
        self.assertEqual([kind for kind, _path in both.targets()], ["xbf", "step"], "file decorators stack")


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
