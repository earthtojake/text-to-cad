"""A model's parameters set in its script, through the engine (``cad_server.engine.parameters``): the served
structure lists what the worker that built the model recorded; ``set`` -- the library's, the command's and the
page's route alike -- writes the numbers at their bytes alone and builds the script's last run again, refuses
by one word of a closed set with nothing written, and puts the bytes and the document back where the build at
the new values fails. A declared xbf carries the record, read-only; a document no live worker built is too."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()

import cad.model  # noqa: E402
import cad.xbf  # noqa: E402
from cad.engine import api, client  # noqa: E402
from cad.engine.ids import model_id  # noqa: E402
from cad.engine.parameters import ParameterRefused  # noqa: E402

SCRIPT = """\
import build123d as bd
from cad import model, xbf

from spec import PITCH

WALL = model.param("wall", 2.0, min=1, max=5)
HOLES = model.param("holes", 6, min=3, max=12)
TWICE = model.param("twice", WALL * 2)


@xbf("XBF/bracket.xbf")
def bracket():
    if WALL > 4.5:
        raise ValueError(f"a wall of {WALL} leaves no room for the holes")
    return bd.Box(PITCH, 10 + HOLES, WALL)
"""
SPEC = 'from cad import model\n\nPITCH = model.param("pitch", 30.0, unit="mm")\n'


class SetCase(unittest.TestCase):
    """A model of the class's own folder, built on an engine of the class's own."""

    @classmethod
    def setUpClass(cls) -> None:
        engine_daemon.isolate(cls.addClassCleanup)
        cls.folder = Path(tempfile.mkdtemp(prefix="parameters-set-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.script = cls.folder / "bracket.py"
        (cls.folder / "spec.py").write_text(SPEC, encoding="utf-8")
        cls.ident = model_id(cls.script, "bracket")

    def setUp(self) -> None:
        self.script.write_text(SCRIPT, encoding="utf-8")
        self.build()

    def build(self) -> None:
        report = api.build_script(self.script, ["bracket"], progress=False)
        self.assertTrue(report.ok, report.models)

    def summary(self, query: str = "structure") -> dict:
        return api.inspect(self.ident, query=query, progress=False)["summary"]

    def served(self) -> dict[str, dict]:
        return {row["name"]: row for row in self.summary()["parameters"]}

    def refused(self, code: str, **values) -> ParameterRefused:
        data = self.script.read_bytes()
        with self.assertRaises(ParameterRefused) as caught:
            cad.model.set(self.ident, **values)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        self.assertEqual(self.script.read_bytes(), data, f"{code}: nothing written")
        return caught.exception


class SetTest(SetCase):
    def test_set_writes_the_numbers_alone_and_the_document_is_built_at_them(self) -> None:
        self.assertEqual({name: (row["value"], row["writable"], row["reason"], row["source"])
                          for name, row in self.served().items()},
                         {"pitch": (30.0, False, "shared", "spec.py"), "wall": (2.0, True, None, "bracket.py"),
                          "holes": (6, True, None, "bracket.py"), "twice": (4.0, False, "expression", "bracket.py")})
        before = self.script.read_bytes()
        answer = cad.model.set(self.ident, wall=2.5, holes=8)
        self.assertEqual(answer, {"id": self.ident, "rebuilt": [self.ident], "written": [
            {"name": "wall", "from": 2.0, "to": 2.5, "file": str(self.script), "line": 6},
            {"name": "holes", "from": 6, "to": 8, "file": str(self.script), "line": 7}]},
            "each number written, where its last run recorded it")
        self.assertEqual(self.script.read_bytes(),
                         before.replace(b'"wall", 2.0', b'"wall", 2.5').replace(b'"holes", 6', b'"holes", 8'))
        summary = self.summary("summary")
        self.assertEqual([round(value, 6) for value in summary["bounds"]["size"]], [30.0, 18.0, 2.5])
        self.assertEqual({name: row["value"] for name, row in self.served().items()},
                         {"pitch": 30.0, "wall": 2.5, "holes": 8, "twice": 5.0})
        # The declared xbf is the document's: its record read from the file alone, every parameter read-only.
        listed = cad.xbf.inspect(self.folder / "XBF" / "bracket.xbf", query="structure")["summary"]["parameters"]
        self.assertEqual({(row["name"], row["value"], row["writable"], row["reason"], row["source"]) for row in listed},
                         {("pitch", 30.0, False, "file", None), ("wall", 2.5, False, "file", None),
                          ("holes", 8, False, "file", None), ("twice", 5.0, False, "file", None)})
        self.assertEqual(cad.model.set(self.ident, wall=2.5), {"id": self.ident, "written": [], "rebuilt": []})

    def test_each_refusal_says_its_code_and_writes_nothing(self) -> None:
        self.refused("unknown_parameter", depth=3)
        self.assertEqual(self.refused("not_writable", pitch=20.0).reason, "shared")
        self.assertEqual(self.refused("not_writable", twice=3.0).reason, "expression")
        for value in ("3", True, 7.5):
            self.refused("not_a_number", holes=value)
        self.refused("out_of_range", wall=5.5)
        with self.script.open("a", encoding="utf-8") as script:
            script.write("# edited, and not run\n")
        self.refused("script_changed", wall=3.0)

    def test_a_build_that_fails_at_the_new_values_puts_the_bytes_and_the_document_back(self) -> None:
        before = self.script.read_bytes()
        refused = self.refused("build_failed", wall=4.8)
        self.assertIn("ValueError: a wall of 4.8 leaves no room for the holes", str(refused))
        self.assertEqual(self.script.read_bytes(), before)
        served = self.served()
        self.assertEqual((served["wall"]["value"], served["wall"]["writable"]), (2.0, True),
                         "the last good document, its positions recorded again")
        self.assertEqual(cad.model.set(self.ident, wall=3.0)["written"][0]["to"], 3.0)

    def test_the_page_route_needs_the_guard_and_takes_numbers_alone(self) -> None:
        serving = client.request({"op": "status"}, start=False)["serving"]
        token = client.request({"op": "http"}, start=False)["token"]

        def post(kind: str, body: object, guard: bool = True) -> tuple[int, dict]:
            request = urllib.request.Request(
                f"{serving['url']}/api/v1/documents/{kind}/{self.ident}/parameters", method="POST",
                data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {token}", "content-type": "application/json",
                                                         **({"x-cad-viewer": "1"} if guard else {})})
            try:
                with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - a loopback test
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                with error:
                    return error.code, json.loads(error.read() or b"{}")

        before = self.script.read_bytes()
        self.assertEqual(post("model", {"values": {"wall": 3}}, guard=False)[0], 403)
        status, said = post("model", {"values": {"wall": "3"}})
        self.assertEqual((status, said["code"]), (400, "not_a_number"))
        status, said = post("model", {"values": {"pitch": 3}})
        self.assertEqual((status, said["code"], said["reason"]), (409, "not_writable", "shared"))
        self.assertEqual(post("model", {"path": str(self.script)})[0], 400, "a request names values alone")
        self.assertEqual(post("xbf", {"values": {"wall": 3}})[0], 404, "a model's route alone")
        self.assertEqual(self.script.read_bytes(), before)
        status, said = post("model", {"values": {"wall": 3}})
        self.assertEqual((status, said["written"][0]["to"], said["rebuilt"]), (200, 3.0, [self.ident]))
        self.assertIn(b'"wall", 3.0,', self.script.read_bytes(), "an integer given a float parameter stays a float")

    def test_the_command_sets_them_and_exits_by_the_refusal_s_class(self) -> None:
        env = {**os.environ, "PYTHONPATH": str(SRC)}

        def command(*args: str) -> subprocess.CompletedProcess:
            return engine_daemon.run([sys.executable, "-m", "cad_server.cli", "model", "set", self.ident, *args],
                                     env=env, cwd=self.folder)

        done = command("wall=2.25", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["written"][0]["to"], 2.25)
        for args, status, code in ((["wall=9", "--json"], 2, "out_of_range"), (["pitch=1", "--json"], 1, "not_writable"),
                                   (["wall", "--json"], 2, None)):
            with self.subTest(args=args):
                done = command(*args)
                self.assertEqual(done.returncode, status, done.stdout + done.stderr)
                said = json.loads(done.stdout)
                self.assertEqual((said["ok"], said.get("code")), (False, code))
        done = command("holes=9")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(done.stdout, rf"holes  6 -> 9  .*bracket\.py:7\nrebuilt {self.ident}\n")


class BusyTest(unittest.TestCase):
    def test_a_script_building_now_is_refused_busy_before_its_bytes_are_read(self) -> None:
        import types

        from cad_server.engine.parameters import LAST_RUN, Setting

        row = {"name": "wall", "value": 2.0, "kind": "float", "min": None, "max": None, "step": None, "unit": None,
               "file": os.path.join(tempfile.gettempdir(), "no-such-script.py"), "line": 1, "span": [0, 3],
               "digest": "0", "reason": None}
        worker = types.SimpleNamespace(leased=True, op="build", state={LAST_RUN: {"request": {"script": row["file"]},
                                                                                  "functions": None}})
        models = types.SimpleNamespace(live=lambda _ident: {"rows": [row], "worker": worker, "name": "bracket"})
        setting = Setting(types.SimpleNamespace(models=models))
        with self.assertRaises(ParameterRefused) as caught:
            setting.set("id", {"wall": 3.0})
        self.assertEqual(caught.exception.code, "busy")
        worker.leased, worker.op = False, None
        setting.scripts.add(os.path.normcase(row["file"]))  # a set of the same script under way
        with self.assertRaises(ParameterRefused) as caught:
            setting.set("id", {"wall": 3.0})
        self.assertEqual(caught.exception.code, "busy")


class NoWorkerTest(SetCase):
    def test_a_document_no_live_worker_built_lists_its_parameters_read_only(self) -> None:
        self.assertTrue(api.stop())
        engine_daemon.start()  # the engine again, the document read from its cache: no worker built it
        self.assertEqual({(row["value"], row["writable"], row["reason"]) for row in self.served().values()} >=
                         {(2.0, False, "no_worker"), (6, False, "no_worker")}, True)
        self.refused("no_worker", wall=3.0)
        self.build()  # run again: its worker recorded where they are
        self.assertTrue(self.served()["wall"]["writable"])


if __name__ == "__main__":
    unittest.main()
