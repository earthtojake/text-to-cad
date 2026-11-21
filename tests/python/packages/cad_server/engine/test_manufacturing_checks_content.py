"""A manufacturing check's measurement is kept by what was measured (``measurements.Measurements``,
``checks_runner.Runner``), so a check that reads the same parts the same way measures nothing, whatever
differs beside: an option its rules alone read, the path its file lies at, a process declared rather than
given, a colour, an edit made and undone, a restart. Each such answer is, byte for byte, the one a measurement
of that very check makes, read from its file in this process. On a real engine, with a state and a cache
folder of this file's own; each test's parts are of a size no other test's are, since what one measures is kept
for all."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.python.support import engine_daemon
from tests.python.support.manufacturing_fixtures import Fixture, _counts, _until

# A plate with a pocket, of a width and a colour a test gives it.
PLATE = """
import build123d as bd
from cad import model


@model
def plate():
    part = bd.Box({width}, 30, 10) - bd.Pos(0, 0, 3) * bd.Box(20, 10, 4.01)
    part.label, part.color = "plate", bd.Color("{colour}")
    return part


if __name__ == "__main__":
    print(plate().id)
"""

# A block whose material declares its process: machined aluminum.
DECLARED = """
import build123d as bd
from bd_materials import metals
from bd_materials.processes import machined
from cad import model


@model
def block():
    part = bd.Box(32, 22, 12) - bd.Pos(0, 0, 4) * bd.Box(12, 8, 4.01)
    part.label, part.material = "block", metals.aluminum(process=machined())
    return part


if __name__ == "__main__":
    print(block().id)
"""

# A plate whose width its build reads from the environment: what a build closure does not hold, so two builds of
# it at one revision are two documents.
SIZED = """
import os

import build123d as bd
from cad import model


@model
def plate():
    part = bd.Box(float(os.environ["CAD_TEST_WIDTH"]), 30, 10) - bd.Pos(0, 0, 3) * bd.Box(20, 10, 4.01)
    part.label = "plate"
    return part


if __name__ == "__main__":
    print(plate().id)
"""

COUNTED = ("measured", "reused", "described", "read")


def setUpModule() -> None:
    engine_daemon.isolate(unittest.addModuleCleanup)


def asked(case: unittest.TestCase, document_type: str, source: Any, process: str | None, **given: Any) -> dict[str, Any]:
    """The check as the engine answers it (``api.check``), once the engine has let it go: the next one asked is
    looked for in what was kept, never joined to this one."""
    from cad._internal import manufacturing
    from cad.engine import api

    check = {"type": document_type, "process": process, "candidates": False,
             "resolved": manufacturing.options(document_type, process, given),
             **({"given": given} if process is None else {})}
    answer = api.check(source, check)
    _until(case, lambda: _counts()["asked"] == 0, "the check is let go")
    return answer


def fresh(document_type: str, path: Path, process: str | None, **given: Any) -> str:
    """What a measurement of the check makes, kept by no one: the file read and measured in this process, its
    ``measured`` as JSON."""
    from cad._internal import manufacturing
    from cad.build123d import _dfm_check

    resolved = manufacturing.options(document_type, process, given)
    if process is None:
        process, resolved, report = _dfm_check.measure_declared(document_type, path, given, False)
    else:
        report = _dfm_check.measure(document_type, path, process, resolved, False)
    return json.dumps({"process": process, "resolved": resolved, "report": report})


class ContentTest(unittest.TestCase):
    def since(self, before: dict[str, int]) -> dict[str, int]:
        """What the engine did since ``before``: the checks measured, those reused, the documents described and
        those a process read."""
        now = _counts()
        return {name: now[name] - before[name] for name in COUNTED}

    def reuses(self, document_type: str, source: Any, path: Path, process: str | None, described: int = 0,
               **given: Any) -> dict[str, Any]:
        """The check asked, which measures nothing -- no process asked at all, but ``described`` asked to read
        the document once -- and answers what a measurement of it makes."""
        before = _counts()
        answer = asked(self, document_type, source, process, **given)
        self.assertEqual(self.since(before), {"measured": 0, "reused": 1, "described": described, "read": described})
        self.assertTrue(answer.get("reused"))
        self.assertEqual(json.dumps(answer["measured"]), fresh(document_type, path, process, **given))
        return answer

    def measures(self, document_type: str, source: Any, process: str | None, **given: Any) -> dict[str, Any]:
        """The check asked, which is measured."""
        before = _counts()
        answer = asked(self, document_type, source, process, **given)
        self.assertEqual((self.since(before)["measured"], self.since(before)["reused"]), (1, 0))
        return answer

    def folder(self) -> Path:
        """A folder of the test's own."""
        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-dfm-content-")))
        self.addCleanup(shutil.rmtree, folder, True)
        return folder

    def step(self, name: str, width: float, named: bool = True) -> Path:
        """A STEP of a box ``width`` wide in a folder of the test's own; ``named`` false, its root unnamed, so
        its reader names it by the file."""
        import build123d as bd

        step = self.folder() / name
        bd.export_step(bd.Box(width, 20, 6), str(step))
        if not named:
            step.write_text(re.sub(r"PRODUCT\('[^']*','[^']*'", "PRODUCT('',''", step.read_text(encoding="utf-8")),
                            encoding="utf-8")
        return step

    def test_an_option_the_measurement_does_not_read_is_no_other_measurement(self) -> None:
        """A material's limits judge a CNC part and measure nothing of it: another material is the same
        measurement, judged again. A sheet's material sets its K-factor, which its flat pattern is measured
        with: another material there is another measurement, while its kerf, which its rules alone read, is
        not."""
        step = self.step("part.step", 51)
        first = self.measures("step", step, "cnc", material="aluminum")
        steel = self.reuses("step", step, step, "cnc", material="steel")
        self.assertEqual((first["measured"]["resolved"]["material"], steel["measured"]["resolved"]["material"]),
                         ("aluminum", "steel"), "each answer its own options")
        self.assertEqual(steel["measured"]["report"], first["measured"]["report"])
        self.measures("step", step, "cnc", material="steel", axes=5)

        self.measures("step", step, "sheet")
        self.measures("step", step, "sheet", material="steel")
        self.reuses("step", step, step, "sheet", material="steel", kerf=0.3)

    def test_the_same_bytes_at_another_path_are_one_measurement(self) -> None:
        """A file's bytes under the same name anywhere are known for what they hold: no process is asked. Under
        another name they are read once, and are the same measurement where the document names itself; where
        its root is unnamed and takes the file's name, every finding and ref says that name, and it is measured
        as the other document it is."""
        step = self.step("part.step", 52)
        self.measures("step", step, "cnc")
        for name, described in (("part.step", 0), ("other.step", 1)):
            with self.subTest(name=name):
                copy = self.folder() / name
                shutil.copyfile(step, copy)
                self.reuses("step", copy, copy, "cnc", described=described)

        bare = self.step("bare.step", 53, named=False)
        first = self.measures("step", bare, "cnc")
        self.assertEqual(first["measured"]["report"]["document"]["name"], "bare")
        copy = self.folder() / "bare.step"
        shutil.copyfile(bare, copy)
        self.reuses("step", copy, copy, "cnc")
        moved = copy.with_name("moved.step")
        shutil.copyfile(bare, moved)
        self.assertEqual(self.measures("step", moved, "cnc")["measured"]["report"]["document"]["name"], "moved")

    def test_a_declared_process_and_the_same_one_given_are_one_measurement(self) -> None:
        """A model whose part declares its process, checked with none given and with that one given: measured
        once, the two answers apart by the finding that says a process was declared, each as a measurement of
        it reads. Its file the other way round: given first, then declared."""
        from cad.engine import api

        fixture = Fixture(self, DECLARED)
        (block,) = fixture.ids
        exported = fixture.folder / "block.xbf"
        api.export(block, exported, progress=False)
        declared = self.measures("model", block, None)
        self.assertEqual(json.dumps(declared["measured"]), fresh("model", exported, None))
        given = self.reuses("model", block, exported, "cnc")
        said = declared["measured"]["report"]["findings"]
        self.assertEqual((said[-1]["code"], given["measured"]["report"].get("findings", [])), ("process_declared", said[:-1]))
        self.assertEqual({**declared["measured"]["report"], "findings": None},
                         {**given["measured"]["report"], "findings": None})

        self.measures("xbf", exported, "cnc", material="steel")  # its file is a document of another type
        self.reuses("xbf", exported, exported, None)

    def test_a_colour_only_edit_measures_nothing(self) -> None:
        """A model built again with another colour is another version, read once to learn that it holds what
        the one before held, and measured no more."""
        from cad.engine import api

        fixture = Fixture(self, PLATE.format(width=54, colour="red"))
        (plate,) = fixture.ids
        first = self.measures("model", plate, "cnc")
        fixture.build(PLATE.format(width=54, colour="blue"))
        exported = fixture.folder / "plate.xbf"
        api.export(plate, exported, progress=False)
        again = self.reuses("model", plate, exported, "cnc", described=1)
        self.assertEqual(again["measured"], first["measured"])

    def test_an_edit_made_and_undone_finds_the_first_measurement(self) -> None:
        """A model edited and edited back is, by its build closure, the version it was: known for what it holds
        with no process asked, in the engine that measured it and in one started since."""
        from cad.engine import api

        fixture = Fixture(self, PLATE.format(width=55, colour="red"))
        (plate,) = fixture.ids
        exported = fixture.folder / "plate.xbf"
        api.export(plate, exported, progress=False)
        first = self.measures("model", plate, "cnc")
        fixture.build(PLATE.format(width=56, colour="red"))
        self.measures("model", plate, "cnc")
        fixture.build(PLATE.format(width=55, colour="red"))
        undone = self.reuses("model", plate, exported, "cnc")
        self.assertEqual(undone["measured"], first["measured"])

        fixture.build(PLATE.format(width=56, colour="red"))
        api.stop()
        engine_daemon.start()
        fixture.build(PLATE.format(width=55, colour="red"))
        before = _counts()
        self.assertEqual(self.reuses("model", plate, exported, "cnc")["measured"], first["measured"])
        self.assertEqual(_counts()["restored"], before["restored"] + 1, "from what the engine before it kept on disk")

    def test_a_model_deleted_with_no_engine_running_is_read_again_when_it_is_built_again(self) -> None:
        """What the engine remembers a model's versions hold goes with the model, whoever deletes it: ``cad
        delete`` with no server to ask removes it itself. So a model built again under its id -- by the same
        code, at the same revision, to other parts, as a build that reads its environment can -- is read and
        measured as it is, never answered for by the one deleted."""
        from cad.engine import api
        from cad_server.engine.cli import delete

        fixture = Fixture(self, SIZED, {"CAD_TEST_WIDTH": "57"})
        (plate,) = fixture.ids
        first = self.measures("model", plate, "cnc")
        known = Path(os.environ["CAD_CACHE_DIR"]) / "checks" / "models" / plate
        self.assertEqual(len(list(known.glob("*.json"))), 1)
        api.stop()
        self.addCleanup(engine_daemon.start)  # whatever happens next, the file's own engine is there again
        self.assertEqual([row["id"] for row in delete([plate])], [plate])
        self.assertFalse(known.exists(), "removed with the document, by the command itself")
        engine_daemon.start()
        fixture.env["CAD_TEST_WIDTH"] = "58"
        self.assertEqual(fixture.build(), [plate])
        again = self.measures("model", plate, "cnc")
        self.assertEqual([found["measured"]["report"]["bodies"][0]["bbox_mm"][0] for found in (first, again)], [57.0, 58.0])

    def test_a_model_built_otherwise_at_a_revision_it_had_is_another_version(self) -> None:
        """An edit undone brings a model back to a revision it had, and with no process asked where the build
        made what it made then. Where it did not -- the build reads its environment, which no closure holds --
        the engine sees by the build's facts that it is another document, reads it, and measures it as it is."""
        fixture = Fixture(self, SIZED, {"CAD_TEST_WIDTH": "59"})
        (plate,) = fixture.ids
        first = self.measures("model", plate, "cnc")
        fixture.build(SIZED.replace("Box(20, 10, 4.01)", "Box(21, 10, 4.01)"))  # an edit, built
        fixture.env["CAD_TEST_WIDTH"] = "60"
        fixture.build(SIZED)  # undone, in another environment: the revision it had, another plate
        before = _counts()
        again = asked(self, "model", plate, "cnc")
        self.assertEqual(self.since(before), {"measured": 1, "reused": 0, "described": 1, "read": 1})
        self.assertEqual([found["measured"]["report"]["bodies"][0]["bbox_mm"][0] for found in (first, again)], [59.0, 60.0])


if __name__ == "__main__":
    unittest.main()
