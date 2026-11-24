"""The older spellings of ``cad.model`` for the file a model is saved as: ``cad.xbf`` and ``@xbf``, answered and
listed nowhere. Each is the same thing as the model spelling, which the other tests cover on its own; these are
the tests a removal of the older spellings deletes with them.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

import cad
import cad.engine
import cad.engine.model

# One model, declared by either spelling: its .xbf beside the script, in a folder of its own.
ARM = """
import build123d as bd
{imports}


{declared}
def arm():
    base = bd.Box(40, 20, 10)
    pin = bd.Pos(0, 0, 10) * bd.Cylinder(4, 10)
    base.label, pin.label = "base", "pin"
    return bd.Compound(children=[base, pin], label="arm")
"""


class TheOlderSpellingsAreTheModelOnes(unittest.TestCase):
    def test_they_are_answered_and_not_listed(self) -> None:
        self.assertNotIn("xbf", cad.__all__)
        self.assertNotIn("xbf", cad.engine.__all__)
        self.assertNotIn("xbf", cad.engine.model.__all__)
        self.assertIs(cad.engine.xbf, cad.engine.model.xbf)
        self.assertEqual(repr(cad.xbf), "<document type 'xbf': .xbf>")

    def test_the_decorator_is_the_model_s_declaration_of_its_xbf(self) -> None:
        def declared(decorate):
            def arm():
                return None

            found = decorate(arm)
            return found.id, found.plan(), found.explicit_name, [(o.kind, o.out, o.tolerance, o.angle) for o in found.outputs]

        for older, now in ((cad.xbf("XBF/arm.xbf"), cad.model("XBF/arm.xbf")),
                           (cad.engine.xbf(out="XBF/arm.xbf"), cad.engine.model("XBF/arm.xbf")),
                           (cad.xbf("a.xbf", name="older-arm"), cad.model("a.xbf", name="older-arm"))):
            self.addCleanup(cad.engine.model._NAMES.clear)
            self.assertEqual(declared(older), declared(now))
            cad.engine.model._NAMES.clear()

    def test_the_reader_is_the_model_s(self) -> None:
        self.assertIs(cad.xbf.read, cad.model.read)

    def test_an_operation_is_the_model_s_given_the_file_and_of_a_file_alone(self) -> None:
        from unittest import mock

        from cad._internal.document_type import _operation
        from cad.engine import api

        ident = "0b4c5f1e-1a2b-4c3d-8e9f-0123456789ab"
        for name in ("export", "inspect", "snapshot", "dfm", "interference", "solve", "ranges"):
            with self.subTest(operation=name):
                self.assertTrue(callable(getattr(cad.xbf, name)))
                with self.assertRaises(ValueError) as refused:
                    getattr(cad.xbf, name)(ident)
                self.assertEqual(str(refused.exception), f"{ident} is a model's document id, not a .xbf file: use cad.model")
        with mock.patch.object(api, "inspect", return_value="read") as verb:
            self.assertEqual((_operation("xbf", "inspect")("share/arm.xbf"), _operation("model", "inspect")("share/arm.xbf")),
                             ("read", "read"))
        self.assertEqual(verb.call_args_list, [mock.call("share/arm.xbf"), mock.call("share/arm.xbf")])
        with mock.patch.object(api, "check", return_value={"unmeasured": {"message": "gone", "code": "stopped"}}) as check:
            cad.xbf.interference("share/arm.xbf")
            cad.model.interference("share/arm.xbf")
        self.assertEqual(check.call_args_list[0], check.call_args_list[1])


class TheOlderDecoratorBuildsTheSameDocument(unittest.TestCase):
    def test_either_spelling_makes_one_document_one_file_and_one_closure(self) -> None:
        """A script that says ``@xbf(path)`` and the same script saying ``@model(path)`` are one model: the
        same id, the same file at the path relative to the script, byte for byte (the closure in it too), and a
        run of one after the other is a run that changed nothing, which leaves the file as it is."""
        from cad.engine import build as engine_build

        folder = Path(tempfile.mkdtemp(prefix="older-xbf-")).resolve()
        self.addCleanup(shutil.rmtree, folder, True)
        script, saved = folder / "src" / "arm.py", folder / "share" / "arm.xbf"
        script.parent.mkdir()

        def built(imports: str, declared: str) -> dict:
            script.write_text(ARM.format(imports=imports, declared=declared), encoding="utf-8")
            os.utime(script, ns=(time.time_ns(), time.time_ns()))  # a rewrite in one clock tick is a new file
            (report,) = engine_build.build(script, ["arm"], cwd=folder)
            self.assertTrue(report["ok"], report)
            return report

        now = built("from cad import model", '@model("../share/arm.xbf")')
        self.assertEqual({path: row["written"] for path, row in now["files"].items()}, {str(saved): True})
        first, written = saved.read_bytes(), saved.stat().st_mtime_ns
        older = built("from cad import xbf", '@xbf("../share/arm.xbf")')
        self.assertEqual((older["id"], list(older["files"])), (now["id"], list(now["files"])))
        self.assertEqual([row["written"] for row in older["files"].values()], [False], "the file it already is")
        self.assertEqual((saved.read_bytes(), saved.stat().st_mtime_ns), (first, written))
        saved.unlink()
        again = built("from cad import xbf", '@xbf("../share/arm.xbf")')
        self.assertEqual(([row["written"] for row in again["files"].values()], saved.read_bytes()), ([True], first))


if __name__ == "__main__":
    unittest.main()
