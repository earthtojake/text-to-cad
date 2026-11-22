"""A model's parameters, the library's half (``cad.engine.parameters``), the standard library alone: a
declaration checked, a load's declarations recorded with where each default is spelled, the rows a model
has (own, shared, expression), the page's view of them, and what a Save checks and writes."""

from __future__ import annotations

import os
import runpy
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import add_sources

add_sources()

from cad import model  # noqa: E402
from cad.engine import parameters  # noqa: E402
from cad.engine.parameters import ParameterRefused  # noqa: E402

SCRIPT = """\
# -- é: a byte beyond ASCII before the numbers, so a column is a byte, not a character
from cad import model
from spec import PITCH

WALL = model.param("wall", 2.0, min=1, max=5)
HOLES = model.param(
    "holes", -6, min=-12, max=-3)
TWICE = model.param("twice", WALL * 2)
"""
SPEC = 'from cad import model\n\nPITCH = model.param("pitch", 30.0, unit="mm")\n'


class DeclaringTest(unittest.TestCase):
    def test_a_declaration_returns_its_default_and_is_refused_by_name_where_it_is_wrong(self) -> None:
        self.assertIs(model.param, parameters.param, "cad.model.param is the function itself")
        namespace: dict = {}
        exec("from cad import model\nWALL = model.param('wall', 2.0, min=1, max=5, unit='mm')\n"
             "HOLES = model.param('holes', 6, step=2)\n", namespace)
        self.assertEqual((namespace["WALL"], type(namespace["HOLES"])), (2.0, int))
        refused = {
            "a bool": ("model.param('flag', True)", TypeError),
            "not finite": ("model.param('wall', float('nan'))", ValueError),
            "text": ("model.param('wall', '2')", TypeError),
            "an unknown option": ("model.param('wall', 2.0, maximum=5)", TypeError),
            "a unit outside the set": ("model.param('wall', 2.0, unit='in')", ValueError),
            "min not below max": ("model.param('wall', 2.0, min=5, max=5)", ValueError),
            "a default outside its range": ("model.param('wall', 9.0, max=5)", ValueError),
            "a step not above zero": ("model.param('wall', 2.0, step=0)", ValueError),
            "an integer's bound not whole": ("model.param('holes', 6, max=7.5)", ValueError),
            "a name that is no identifier": ("model.param('Wall', 2.0)", ValueError),
            "inside a function": ("def body():\n    return model.param('wall', 2.0)\nbody()", RuntimeError),
        }
        for what, (code, kind) in refused.items():
            with self.subTest(what), self.assertRaises(kind) as caught:
                exec("from cad import model\n" + code, {})
            if what == "an unknown option":
                self.assertIn("min, max, step, unit", str(caught.exception))


class RecordingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="parameters-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.script = self.folder / "bracket.py"
        self.script.write_text(SCRIPT, encoding="utf-8")
        (self.folder / "spec.py").write_text(SPEC, encoding="utf-8")

    def load(self) -> list[parameters.Declared]:
        """The script loaded as a build loads it: its declarations recorded."""
        import sys

        sys.path.insert(0, str(self.folder))
        self.addCleanup(sys.path.remove, str(self.folder))
        self.addCleanup(sys.modules.pop, "spec", None)
        with parameters.recording() as declared:
            runpy.run_path(str(self.script))
        return declared

    def rows(self) -> list[dict]:
        from cad.engine.ids import canonical

        return parameters.rows(self.load(), canonical(str(self.script)))

    def test_each_declaration_is_recorded_with_the_bytes_of_its_default(self) -> None:
        data = self.script.read_bytes()
        declared = {row.name: row for row in self.load()}
        self.assertEqual(list(declared), ["pitch", "wall", "holes", "twice"], "in the order declared")
        for name, spelled in (("wall", b"2.0"), ("holes", b"-6")):
            start, end = declared[name].span
            self.assertEqual(data[start:end], spelled, f"{name}: the literal's bytes, a leading minus with it")
            self.assertEqual(declared[name].digest, parameters.digest(data))
        self.assertIsNone(declared["twice"].span, "an expression has no bytes to write")
        self.assertEqual((declared["holes"].kind, declared["holes"].line), ("int", 6))
        with self.assertRaises(ValueError) as caught:  # one name, two declarations: both named
            self.script.write_text(SCRIPT + 'AGAIN = model.param("wall", 3.0)\n', encoding="utf-8")
            self.load()
        self.assertRegex(str(caught.exception), r"bracket\.py:5 and .*bracket\.py:9")

    def test_a_model_lists_its_own_writable_and_the_rest_read_only_and_the_page_serves_them_so(self) -> None:
        rows = {row["name"]: row for row in self.rows()}
        self.assertEqual({name: row["reason"] for name, row in rows.items()},
                         {"pitch": "shared", "wall": None, "holes": None, "twice": "expression"})
        record = parameters.record(list(rows.values()))
        self.assertNotIn("bracket.py", record, "a document records no file, line or span")
        listed = parameters.recorded(record)
        self.assertEqual(listed[1], {"name": "wall", "value": 2.0, "kind": "float", "min": 1, "max": 5, "step": None,
                                     "unit": None})
        live = {"script": str(self.script), "rows": list(rows.values())}
        served = {row["name"]: row for row in parameters.served(listed, model=True, live=live)}
        self.assertEqual({name: (row["writable"], row["reason"], row["source"]) for name, row in served.items()},
                         {"pitch": (False, "shared", "spec.py"), "wall": (True, None, "bracket.py"),
                          "holes": (True, None, "bracket.py"), "twice": (False, "expression", "bracket.py")})
        self.assertEqual({row["reason"] for row in parameters.served(listed, model=False, live=None)}, {"file"})
        self.assertEqual({(row["reason"], row["source"]) for row in parameters.served(listed, model=True, live=None)},
                         {("no_worker", None)})
        self.assertEqual(parameters.served(None, model=True, live=live), [])

    def test_a_change_is_checked_spelled_and_written_at_its_bytes_alone(self) -> None:
        rows = self.rows()
        refusals = {
            "unknown_parameter": {"depth": 1},
            "not_writable": {"pitch": 1.0},
            "not_a_number": {"holes": -6.5},
            "out_of_range": {"wall": 5.5},
        }
        for code, values in refusals.items():
            with self.subTest(code), self.assertRaises(ParameterRefused) as caught:
                parameters.changes(rows, values)
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(ParameterRefused) as caught:
            parameters.changes(rows, {"twice": 3.0})
        self.assertEqual(caught.exception.reason, "expression")
        for given in ("2", True, float("inf")):
            with self.subTest(given=given), self.assertRaises(ParameterRefused) as caught:
                parameters.changes(rows, {"wall": given})
            self.assertEqual(caught.exception.code, "not_a_number")
        self.assertEqual(parameters.changes(rows, {"wall": 2, "holes": -6}), [], "the values the code holds: no change")
        found = parameters.changes(rows, {"holes": -4.0, "wall": 1.0000004})
        self.assertEqual([(row["name"], value) for row, value in found], [("wall", 1.0), ("holes", -4)],
                         "in the order declared, a float to six decimals, an integer's value whole")
        data = self.script.read_bytes()
        parameters.standing(data, [row for row, _ in found], "bracket.py")
        made = parameters.splice(data, [(row["span"][0], row["span"][1], parameters.spelled(value, row["kind"]))
                                        for row, value in found])
        self.assertEqual(made, data.replace(b'"wall", 2.0', b'"wall", 1.0').replace(b'"holes", -6', b'"holes", -4'))
        edited = b"# an edit\n" + data
        with self.assertRaises(ParameterRefused) as caught:
            parameters.standing(edited, [row for row, _ in found], "bracket.py")
        self.assertEqual(caught.exception.code, "script_changed")
        self.assertEqual([parameters.spelled(value, "float") for value in (2.5, 3, -0.0, 1e-7, 1e16)],
                         ["2.5", "3.0", "0.0", "0.0", "1e+16"])
        self.assertEqual(parameters.spelled(8.0, "int"), "8")

    def test_a_value_no_float_holds_or_one_that_would_be_written_as_zero_is_refused(self) -> None:
        rows = self.rows()
        for values in ({"wall": 10**400}, {"holes": -(10**400)}):  # refused before anything converts it
            with self.subTest(values=list(values)), self.assertRaises(ParameterRefused) as caught:
                parameters.changes(rows, values)
            self.assertEqual(caught.exception.code, "not_a_number")
        self.assertLess(len(str(caught.exception)), 200, "the number is not said whole")
        gap = {"name": "gap", "value": 0.5, "kind": "float", "min": None, "max": None, "span": [0, 3], "reason": None}
        with self.assertRaises(ParameterRefused) as caught:
            parameters.changes([gap], {"gap": 1e-7})
        self.assertEqual(caught.exception.code, "not_a_number", "a value that is not zero is never written as 0.0")
        self.assertEqual(parameters.changes([gap], {"gap": 0})[0][1], 0.0)
        self.assertEqual(parameters.changes([gap], {"gap": 0.1234564})[0][1], 0.123456, "the value written and answered")

    def test_a_literal_that_is_not_one_declaration_s_alone_has_no_span(self) -> None:
        cases = {
            "a loop": "for name in ('a', 'b'):\n    model.param(name, 1)\n",
            "a comprehension": "X = [model.param(f'x{i}', 1) for i in range(2)]\n",
            "a coding that is not UTF-8": None,
        }
        for what, code in cases.items():
            with self.subTest(what):
                if code is None:
                    self.script.write_bytes("# -*- coding: latin-1 -*-\nfrom cad import model\ns = 'ééé'\n"
                                            "A = model.param('a', 1)\n".encode("latin-1"))
                else:
                    self.script.write_text("from cad import model\n" + code, encoding="utf-8")
                try:
                    declared = self.load()
                except RuntimeError:  # before 3.12 a comprehension is a function of its own: refused
                    self.assertEqual(what, "a comprehension")
                    continue
                self.assertTrue(declared)
                self.assertEqual({row.span for row in declared}, {None})
                self.assertEqual({row["reason"] for row in parameters.rows(declared, declared[0].file)}, {"expression"})
        # Two declarations a load found at one literal: neither keeps it.
        import sys
        import types

        held = parameters._Recording(lambda _file: True)
        held._literal = lambda *_args: ((10, 11), "digest")  # type: ignore[method-assign]
        for name, line in (("a", 1), ("b", 2)):
            frame = types.SimpleNamespace(f_code=sys._getframe().f_code, f_lineno=line)
            held.declare(frame, name, 1, "int", None, None, None, None)
        self.assertEqual([row.span for row in held.declared], [None, None])


if __name__ == "__main__":
    unittest.main()
