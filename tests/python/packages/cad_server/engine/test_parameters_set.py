"""A model's parameters set in its script, through the engine (``cad_server.engine.parameters``): the served
structure lists what the worker that built the model recorded; the CAD Viewer's Save (the page's route, the
one way the engine writes them) writes the numbers at their bytes alone and builds the script's last run again, refuses
by one word of a closed set with nothing written, and puts the bytes and the document back where the build at
the new values fails. A declared xbf carries the record, read-only, and so does one exported from the model; a
document no live worker built is read-only too."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import textwrap
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from tests.python.support import engine_daemon
from tests.python.support.parameters import save
from tests.python.support.paths import add_sources

add_sources()

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
            save(self.ident, **values)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        self.assertEqual(self.script.read_bytes(), data, f"{code}: nothing written")
        return caught.exception


class SetTest(SetCase):
    def test_a_save_writes_the_numbers_alone_and_the_document_is_built_at_them(self) -> None:
        self.assertEqual({name: (row["value"], row["writable"], row["reason"], row["source"])
                          for name, row in self.served().items()},
                         {"pitch": (30.0, False, "shared", "spec.py"), "wall": (2.0, True, None, "bracket.py"),
                          "holes": (6, True, None, "bracket.py"), "twice": (4.0, False, "expression", "bracket.py")})
        before = self.script.read_bytes()
        answer = save(self.ident, wall=2.5, holes=8)
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
        self.assertEqual(save(self.ident, wall=2.5), {"id": self.ident, "written": [], "rebuilt": []})

    def test_each_refusal_says_its_code_and_writes_nothing(self) -> None:
        self.refused("unknown_parameter", depth=3)
        self.assertEqual(self.refused("not_writable", pitch=20.0).reason, "shared")
        self.assertEqual(self.refused("not_writable", twice=3.0).reason, "expression")
        for value in ("3", True, 7.5):
            self.refused("not_a_number", holes=value)
        self.refused("out_of_range", wall=5.5)
        self.refused("not_a_number", wall=10**400)  # beyond any float: refused before anything converts it
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
        self.assertEqual(save(self.ident, wall=3.0)["written"][0]["to"], 3.0)

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
        status, said = post("model", {"values": {"wall": 10**400}})
        self.assertEqual((status, said["code"]), (400, "not_a_number"))
        status, said = post("model", {"values": {"pitch": 3}})
        self.assertEqual((status, said["code"], said["reason"]), (409, "not_writable", "shared"))
        self.assertEqual(post("model", {"path": str(self.script)})[0], 400, "a request names values alone")
        self.assertEqual(post("xbf", {"values": {"wall": 3}})[0], 404, "a model's route alone")
        self.assertEqual(self.script.read_bytes(), before)
        status, said = post("model", {"values": {"wall": 3}})
        self.assertEqual((status, said["written"][0]["to"], said["rebuilt"]), (200, 3.0, [self.ident]))
        self.assertIn(b'"wall", 3.0,', self.script.read_bytes(), "an integer given a float parameter stays a float")


SIBLINGS = """\
import build123d as bd
from cad import model

WALL = model.param("wall", 2.0, min=1, max=5)


@model
def a():
    if WALL > 4.5:
        raise ValueError("too thick")
    return bd.Box(10, 10, WALL)


@model
def b():
    return bd.Box(10, 10, 1)


@model
def bad():
    raise RuntimeError("always broken")
"""


class SiblingsTest(unittest.TestCase):
    """One script's three models: ``a`` reads the parameter, ``b`` does not, ``bad`` never builds."""

    @classmethod
    def setUpClass(cls) -> None:
        engine_daemon.isolate(cls.addClassCleanup)
        cls.folder = Path(tempfile.mkdtemp(prefix="parameters-siblings-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.script = cls.folder / "siblings.py"
        cls.a, cls.b = model_id(cls.script, "a"), model_id(cls.script, "b")

    def setUp(self) -> None:
        self.script.write_text(SIBLINGS, encoding="utf-8")
        report = api.build_script(self.script, None, progress=False)
        self.assertEqual({row["model"].rsplit("::", 1)[-1]: row["ok"] for row in report.models}, {"a": True, "b": True, "bad": False})

    def wall(self, ident: str) -> tuple:
        row = next(row for row in api.inspect(ident, query="structure", progress=False)["summary"]["parameters"])
        return row["value"], row["writable"], row["reason"]

    def test_a_model_the_change_does_not_reach_holds_and_serves_the_new_record(self) -> None:
        self.assertEqual(self.wall(self.b), (2.0, True, None), "b served before the set")
        # ``bad`` failed in the run and fails the same way now: not the change's, so the set stands.
        answer = save(self.a, wall=3.0)
        self.assertEqual(answer["rebuilt"], [self.a, self.b])
        self.assertEqual(self.wall(self.b), (3.0, True, None), "b's document is a new generation, its rows served")
        self.script.write_text(SIBLINGS.replace('"wall", 2.0', '"wall", 3.5'), encoding="utf-8")  # by hand, and run
        api.build_script(self.script, None, progress=False)
        self.assertEqual(self.wall(self.b), (3.5, True, None))
        self.assertEqual(save(self.b, wall=4.0)["written"][0]["to"], 4.0, "set through b")

    def test_an_xbf_exported_from_a_model_carries_its_parameters_read_only(self) -> None:
        out = Path(tempfile.mkdtemp(prefix="parameters-export-")).resolve()
        self.addCleanup(shutil.rmtree, out, True)
        api.export(self.a, out / "a.xbf", progress=False)
        listed = cad.xbf.inspect(out / "a.xbf", query="structure")["summary"]["parameters"]
        self.assertEqual([(row["name"], row["value"], row["kind"], row["min"], row["max"], row["writable"], row["reason"])
                          for row in listed], [("wall", 2.0, "float", 1, 5, False, "file")])

    def test_a_model_that_built_and_fails_at_the_new_values_fails_the_set(self) -> None:
        with self.assertRaises(ParameterRefused) as caught:
            save(self.a, wall=4.8)
        self.assertEqual(caught.exception.code, "build_failed")
        self.assertIn("ValueError: too thick", str(caught.exception))
        self.assertEqual(self.script.read_text(encoding="utf-8"), SIBLINGS)


class PutBackTest(unittest.TestCase):
    """``Setting`` on a stand-in daemon whose build is a hook: what another writer does meanwhile, at a known step."""

    def setUp(self) -> None:
        import types

        from cad.engine import parameters
        from cad_server.engine.parameters import LAST_RUN

        folder = Path(tempfile.mkdtemp(prefix="parameters-put-back-")).resolve()
        self.addCleanup(shutil.rmtree, folder, True)
        self.script = folder / "bracket.py"
        self.before = b"W = 2.0\n"
        self.script.write_bytes(self.before)
        row = {"name": "wall", "value": 2.0, "kind": "float", "min": None, "max": None, "step": None, "unit": None,
               "file": str(self.script), "line": 1, "span": [4, 7], "digest": parameters.digest(self.before),
               "reason": None}
        worker = types.SimpleNamespace(leased=False, op=None, state={LAST_RUN: {
            "request": {"script": str(self.script)}, "functions": None, "failed": {}}})
        self.builds: list = []
        self.during = lambda: None  # what happens while the build at the new values runs

        def handle(order, send):
            self.builds.append(self.script.read_bytes())
            if len(self.builds) == 1:
                self.during()
                send({"done": [{"model": "bracket", "id": "id", "ok": False, "error": "ValueError: too thick"}]})
            else:
                send({"done": [{"model": "bracket", "id": "id", "ok": True}]})

        from cad_server.engine.parameters import Setting

        models = types.SimpleNamespace(live=lambda _ident: {"rows": [row], "worker": worker, "name": "bracket"})
        self.setting = Setting(types.SimpleNamespace(models=models, handle=handle))

    def refused(self) -> ParameterRefused:
        with self.assertRaises(ParameterRefused) as caught:
            self.setting.set("id", {"wall": 4.8})
        self.assertEqual(caught.exception.code, "build_failed")
        return caught.exception

    def test_a_file_changed_while_it_built_is_left_as_it_is(self) -> None:
        edited = b"W = 4.8\n# another writer's line\n"
        self.during = lambda: self.script.write_bytes(edited)
        said = str(self.refused())
        self.assertEqual(self.script.read_bytes(), edited, "the other writer's bytes, never the old ones over them")
        self.assertIn("changed while it built, so the engine did not put it back", said)
        self.assertEqual(len(self.builds), 1, "nothing put back, nothing built again")

    def test_a_put_back_that_fails_says_the_new_bytes_are_on_disk(self) -> None:
        from unittest import mock

        from cad_server.engine import parameters as setting

        real = setting._write
        calls: list = []

        def write(path, data, holds):
            calls.append(data)
            if len(calls) == 2:
                raise PermissionError(13, "Permission denied", str(path))
            real(path, data, holds)

        with mock.patch.object(setting, "_write", write):
            said = str(self.refused())
        self.assertEqual(self.script.read_bytes(), b"W = 4.8\n")
        self.assertIn(f"{self.script} could not be put back (Permission denied): it holds the new values", said)

    def test_a_file_changed_before_the_new_bytes_go_in_is_not_written(self) -> None:
        from unittest import mock

        from cad.engine import parameters

        edited = b"W = 2.0  # another writer's\n"
        real = parameters.splice

        def splice(data, edits):
            self.script.write_bytes(edited)  # between the check of its bytes and the write
            return real(data, edits)

        with mock.patch.object(parameters, "splice", splice), self.assertRaises(ParameterRefused) as caught:
            self.setting.set("id", {"wall": 4.8})
        self.assertEqual(caught.exception.code, "script_changed")
        self.assertEqual((self.script.read_bytes(), self.builds), (edited, []))


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
        from cad.engine.ids import canonical

        key = canonical(row["file"])
        with setting.building(key):  # a build of the script in another worker (another Python's), or waiting for one
            with self.assertRaises(ParameterRefused) as caught:
                setting.set("id", {"wall": 3.0})
            self.assertEqual(caught.exception.code, "busy")
        setting.claims[key] = 0  # a set of the same script under way, on another thread
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
