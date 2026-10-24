"""The engine counts nothing: after each build, export and snapshot it tells ``api.observers`` what the
verb did, as plain facts -- kinds, counts, times and an error's type and frames, never a model's name or a
path but the frames' files -- and an observer that fails never fails the verb."""

from __future__ import annotations

import json
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = """
import build123d as bd
from cadgen.engine import stl, xbf


@xbf("XBF/secret_plate.xbf")
@stl("secret_plate.stl")
def secret_plate():
    plate = bd.Box(10, 10, 2)
    plate.label = "plate"
    peg = bd.Pos(20, 0, 0) * bd.Cylinder(2, 4)
    peg.label = "peg"
    return bd.Compound(children=[plate, peg], label="secret_plate")


@xbf("XBF/secret_broken.xbf")
def secret_broken():
    raise ValueError("the secret part did not fit")
"""


class ObserversTest(unittest.TestCase):
    def setUp(self) -> None:
        from cadgen.engine import api

        self.api = api
        self.folder = Path(tempfile.mkdtemp(prefix="engine-observers-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        (self.folder / "secret.py").write_text(textwrap.dedent(SCRIPT), encoding="utf-8")
        self.told: list[dict] = []
        # This test's observer alone: cadgen's own counts nothing here.
        patched = mock.patch.object(api, "observers", [self.told.append])
        patched.start()
        self.addCleanup(patched.stop)

    def test_each_verb_tells_what_it_did_as_plain_facts(self) -> None:
        api = self.api
        report = api.build_script(self.folder / "secret.py", daemon=False)  # a script builds as its decorators say
        self.assertEqual([model["ok"] for model in report.models], [True, False])
        api.export(self.folder / "XBF/secret_plate.xbf", self.folder / "out.step", self.folder / "out.3mf", daemon=False)
        with self.assertRaises(ValueError):  # refused by name
            api.snapshot(self.folder / "missing.xbf", self.folder / "out.png", daemon=False)
        api.inspect(self.folder / "XBF/secret_plate.xbf")  # where, serve and status tell nothing
        built, exported, drawn = self.told
        self.assertEqual(len(self.told), 3)
        for facts in self.told:
            text = json.dumps(facts)  # plain: JSON as it is
            outside_frames = json.dumps({key: value for key, value in facts.items() if key != "error"})
            self.assertNotIn("secret", outside_frames, "no name and no path of the person's")
            self.assertNotIn("did not fit", text, "never a message")
        self.assertEqual((built["verb"], built["ok"], built["program"]), ("build", False, False))
        self.assertEqual(built["models"], [
            {"ok": True, "cached": False, "children": 0, "parts": 2, "files": ["stl", "xbf"]},
            {"ok": False, "cached": False, "children": 0, "parts": 0, "files": []}])
        self.assertEqual(built["worker"], {"fresh": None, "retired": False, "died": None})  # built here, no worker
        error = built["error"]
        self.assertEqual((error["type"], error["engine"], error["refused"], error["here"]), ("ValueError", False, False, False))
        self.assertEqual([(Path(frame["file"]).name, frame["function"]) for frame in error["frames"]],
                         [("secret.py", "secret_broken")], "the model's frames, its file as Python has it")
        self.assertEqual((exported["verb"], exported["ok"], exported["source"]), ("export", True, "xbf"))
        self.assertNotIn("pose", exported, "an export has no pose to tell")
        self.assertEqual([output["kind"] for output in exported["outputs"]], ["step", "threemf"])
        self.assertIsNone(exported["error"])
        self.assertEqual((drawn["verb"], drawn["ok"], drawn["source"], drawn["found"]), ("snapshot", False, "xbf", False))
        self.assertEqual((drawn["error"]["type"], drawn["error"]["refused"], drawn["error"]["here"]),
                         ("cadgen.engine.snapshot.SnapshotRefused", True, True))

    def test_an_observer_that_raises_never_fails_the_verb(self) -> None:
        def broken(_facts: dict) -> None:
            raise RuntimeError("an observer's own bug")

        self.api.observers[:] = [broken, self.told.append]
        report = self.api.build_script(self.folder / "secret.py", ["secret_plate"], daemon=False)
        self.assertEqual([model["ok"] for model in report.models], [True])
        written = self.api.export(self.folder / "XBF/secret_plate.xbf", self.folder / "out.stl", daemon=False)
        self.assertEqual([row.kind for row in written], ["stl"])
        built, exported = self.told  # the next observer is told all the same
        self.assertEqual((built["verb"], built["ok"]), ("build", True))
        self.assertEqual((exported["verb"], exported["source"], exported["ok"]), ("export", "xbf", True))

    def test_a_worker_s_words_are_read_for_its_error_and_its_death(self) -> None:
        """What the daemon answers when its worker failed or died (``worker.main``, ``daemon.Worker.build``)
        is all that comes back of it: the engine reads the error's type and frames from it, and the death's
        exit status, and tells those."""
        api = self.api
        crash = "".join(["Traceback (most recent call last):\n",
                         '  File "/site/cadgen/engine/worker.py", line 401, in main\n    reports = build(script)\n',
                         '  File "/site/cadgen/engine/document.py", line 88, in to_xcaf\n    label = kept.labels[key]\n',
                         "        ~~~~~~~~~~~^^^^^\n", "KeyError: 'secret'\n"])
        cases = {crash: {"type": "KeyError", "functions": ["main", "to_xcaf"], "died": None},
                 "the worker for secret.py exited (-11) during the build": {"type": None, "functions": [], "died": -11}}
        for text, expected in cases.items():
            worker = {"fresh": None, "retired": False, "died": None}
            error = api._error(api.EngineError(text), [], worker)
            self.assertEqual((error["type"], [frame["function"] for frame in error["frames"]], worker["died"]),
                             (expected["type"], expected["functions"], expected["died"]))
            self.assertEqual((error["engine"], error["refused"], error["here"]), (True, False, False))
        refused = api._error(api.EngineError("no script secret.py"), [], {"died": None})
        self.assertEqual((refused["type"], refused["refused"]), (None, True))


if __name__ == "__main__":
    unittest.main()
