"""A document's view bundle (``cad <type> export SRC DST.view``), written by an engine of this test's own
and held to the answers that engine gives a page over HTTP: every file the manifest lists is there with its
size and digest, each is the live answer byte for byte (but what a structure says of the computer it was
answered on: a file's ``path``, a model's ``closure``, where a robot's meshes are), a part's table holds
exactly what asking for each element answers of its geometry, a bundle written again after an edit rewrites
the changed part's files and no other part's, an export that fails leaves the folder as it was, and no file
of a bundle names a folder of the computer it was made on. A model, an ``.xbf``, a STEP, an STL, a DXF and a
URDF each have one.

The models are written into a fresh temporary folder and built there; nothing reads the sample corpus.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from urllib.parse import quote

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the packages' sources, as PYTHONPATH names them

MODEL = """
import build123d as bd
from cad import step, xbf
from bd_materials import metals


@xbf("XBF/pair.xbf")
@step("pair.step")
def pair():
    plate = bd.Box(10, 6, 4) - bd.Cylinder(1, 10)
    plate.label, plate.color = "plate", bd.Color(0.8, 0.1, 0.1)
    peg = bd.Pos(8, 0, 4) * bd.Cylinder(1, 6)
    peg.label, peg.material = "peg", metals.aluminum()
    return bd.Compound(children=[plate, peg], label="pair")


if __name__ == "__main__":
    pair()
"""

# A model of its own for the edit: its peg's height is the one thing a second run changes.
EDITED = """
import build123d as bd
from cad import model


@model
def kit():
    plate = bd.Box(10, 6, 4) - bd.Cylinder(1, 10)
    plate.label = "plate"
    peg = bd.Pos(8, 0, 4) * bd.Cylinder(1, HEIGHT)
    peg.label = "peg"
    return bd.Compound(children=[plate, peg], label="kit")


if __name__ == "__main__":
    kit()
"""

ELEMENTS = {"faces": "face", "edges": "edge", "vertices": "vertex"}

# A robot of one box cad meshes and one mesh file two links draw; NAME is a visual's name.
ROBOT = """<?xml version="1.0"?>
<robot name="arm">
  <link name="base"><visual name="NAME"><geometry><box size="0.4 0.4 0.1"/></geometry></visual></link>
  <link name="head"><visual><geometry><mesh filename="meshes/head.stl" scale="0.001 0.001 0.001"/></geometry></visual></link>
  <link name="hat"><visual><geometry><mesh filename="meshes/head.stl" scale="0.001 0.001 0.001"/></geometry></visual></link>
  <joint name="nod" type="revolute"><parent link="base"/><child link="head"/><origin xyz="0 0 0.2"/><axis xyz="0 1 0"/>
    <limit lower="-1" upper="1" effort="1" velocity="1"/></joint>
  <joint name="top" type="fixed"><parent link="head"/><child link="hat"/><origin xyz="0 0 0.2"/></joint>
</robot>
"""


class ViewBundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="view-bundle-")))
        cls.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cls.saved = {name: os.environ.get(name) for name in ("CAD_ENGINE_DIR", "CAD_ENGINE_MESH")}
        # The daemon this test starts is its own: its own engine folder, one part meshed at a time.
        os.environ.update({"CAD_ENGINE_DIR": str(cls.state), "CAD_ENGINE_MESH": "inline"})
        cls.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC)}, cls.addClassCleanup)
        (cls.base / "models.py").write_text(textwrap.dedent(MODEL), encoding="utf-8")
        cls.run_script("models.py")
        from cad.engine import api
        from cad.engine.client import request
        from cad.engine.ids import model_id

        cls.model = model_id(cls.base / "models.py", "pair")
        cls.out = cls.base / "out"
        api.export(cls.base / "XBF" / "pair.xbf", cls.out / "pair.stl")
        import ezdxf

        drawing = ezdxf.new("R2010", setup=True)
        drawing.modelspace().add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)], close=True, dxfattribs={"layer": "CUT"})
        drawing.saveas(cls.base / "plate.dxf")
        (cls.base / "robot" / "meshes").mkdir(parents=True)
        shutil.copyfile(cls.out / "pair.stl", cls.base / "robot" / "meshes" / "head.stl")
        (cls.base / "robot" / "arm.urdf").write_text(ROBOT.replace("NAME", "plinth"), encoding="utf-8")
        launched = request({"op": "viewer", "api_only": True, "start": str(cls.base)})
        assert launched and "failed" not in launched, launched
        cls.port, cls.token = launched["port"], launched["token"]
        # One bundle of each source, written once for every test that reads one.
        cls.sources = {"model": cls.model, "xbf": cls.base / "XBF" / "pair.xbf", "step": cls.base / "pair.step",
                       "stl": cls.out / "pair.stl", "dxf": cls.base / "plate.dxf",
                       "urdf": cls.base / "robot" / "arm.urdf"}
        cls.rows = {name: api.export(source, cls.out / f"{name}.view")[0] for name, source in cls.sources.items()}

    @classmethod
    def tearDownClass(cls) -> None:
        subprocess.run([sys.executable, "-m", "cad_server.engine", "stop"], env={**os.environ, "PYTHONPATH": str(SRC)},
                       capture_output=True, timeout=120)
        deadline = time.monotonic() + 20
        while any(cls.state.glob("*.door")) and time.monotonic() < deadline:
            time.sleep(0.05)
        for name, value in cls.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        shutil.rmtree(cls.base, ignore_errors=True)
        shutil.rmtree(cls.state, ignore_errors=True)

    # --- helpers ---------------------------------------------------------------------------

    @classmethod
    def run_script(cls, name: str) -> None:
        """A script run as a person runs one: through this test's own engine."""
        done = engine_daemon.run([sys.executable, name], cwd=cls.base, env=cls.env)
        assert done.returncode == 0, done.stdout + done.stderr

    def live(self, target: str, method: str = "GET", body: dict | None = None) -> bytes:
        """The engine's answer to a page's request, over HTTP: ``target`` as a page spells it, its query's
        escapes its own."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=300)
        try:
            connection.request(method, target, body=None if body is None else json.dumps(body).encode(),
                               headers={"Authorization": "Bearer " + self.token, "x-cad-viewer": "1"})
            response = connection.getresponse()
            data = response.read()
            self.assertIn(response.status, (200, 201), (target, data))
            return data
        finally:
            connection.close()

    def api(self, name: str) -> str:
        """Where a page reads the source ``name``: its document opened as a page opens it."""
        source = self.sources[name]
        opening = {"id": source} if name == "model" else {"path": str(source)}
        deadline = time.monotonic() + 300
        while True:
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=300)
            try:
                connection.request("POST", "/api/v1/documents", body=json.dumps(opening).encode(),
                                   headers={"Authorization": "Bearer " + self.token, "x-cad-viewer": "1"})
                response = connection.getresponse()
                answer = json.loads(response.read())
            finally:
                connection.close()
            if response.status != 202:
                self.assertEqual(response.status, 201, answer)
                return answer["api"]
            self.assertLess(time.monotonic(), deadline, "the engine never finished reading the document")

    def manifest(self, folder: Path) -> dict:
        return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    def files(self, folder: Path) -> set[str]:
        return {path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()}

    @staticmethod
    def segment(name: str) -> str:
        """A key as the layout spells a path segment (**View bundle**)."""
        return "".join(char if char.isascii() and (char.isalnum() or char in "._-") else f"~{ord(char):02X}"
                       for char in name)

    # --- the tests -------------------------------------------------------------------------

    def test_a_bundle_holds_every_file_its_manifest_lists(self) -> None:
        for name, row in self.rows.items():
            with self.subTest(source=name):
                folder = self.out / f"{name}.view"
                manifest = self.manifest(folder)
                self.assertEqual((manifest["format"], manifest["made"]["tool"]), ("view-bundle/1", "cad"))
                self.assertEqual(self.files(folder), {*manifest["files"], "manifest.json"})
                for path, entry in manifest["files"].items():
                    data = (folder / path).read_bytes()
                    self.assertEqual((entry["bytes"], entry["sha256"]), (len(data), hashlib.sha256(data).hexdigest()), path)
                    self.assertTrue(entry["type"], path)
                # What the export answers is the folder and what it holds.
                self.assertEqual((row.path, row.kind, row.written), (folder, "view", True))
                self.assertEqual((row.view["document"], row.view["files"]), (manifest["document"], len(manifest["files"]) + 1))
                self.assertEqual(set(row.view["written"]), self.files(folder))
        from cad.engine.ids import file_id

        envelope = json.loads(self.live(f"/api/v1/documents/{self.model}"))
        structure = json.loads(self.live(self.api("model") + "/structure"))
        self.assertEqual(self.manifest(self.out / "model.view")["document"],
                         {"id": self.model, "kind": "model", "name": envelope["name"], "version": structure["version"]})
        files = ("xbf", "step", "stl", "dxf", "urdf")
        self.assertEqual([self.manifest(self.out / f"{name}.view")["document"] for name in files],
                         [{"id": file_id(self.sources[name]), "kind": name, "name": self.sources[name].name,
                           "version": json.loads(self.live(f"/api/v1/documents/{file_id(self.sources[name])}"))["version"]
                           if name in ("stl", "dxf", "urdf") else
                           json.loads((self.out / f"{name}.view" / "structure.json").read_bytes())["version"]}
                          for name in files])
        # A mesh file's bundle is the file, which its page parses; a drawing's, its drawing; a robot's, its
        # structure, the one primitive cad meshed for it and the one mesh file its links draw, each once.
        self.assertEqual(self.files(self.out / "stl.view"), {"manifest.json", "source.stl"})
        self.assertEqual(self.files(self.out / "dxf.view"), {"manifest.json", "drawing.json"})
        mesh = hashlib.sha256((self.base / "robot" / "meshes" / "head.stl").read_bytes()).hexdigest()
        robot = self.files(self.out / "urdf.view")
        self.assertLessEqual({"manifest.json", "structure.json", f"meshes/{mesh}.stl"}, robot)
        self.assertEqual([len(robot), len([path for path in robot if path.startswith("parts/") and path.endswith(".glb")])],
                         [4, 1])

    def test_each_bundled_answer_is_the_live_answer(self) -> None:
        for name in ("model", "xbf", "step"):
            with self.subTest(source=name):
                folder, api = self.out / f"{name}.view", self.api(name)
                structure = json.loads(self.live(api + "/structure"))
                # A structure is the answer but for what it says of the computer it was answered on: a
                # model's names the code that built it (its closure: the script and its modules by path, their
                # names), which its bundle leaves out; a file's names where the file is, and its bundle the
                # file's name alone.
                if name == "model":
                    self.assertEqual(structure["closure"]["source"]["function"], "pair")
                    portable = {key: value for key, value in structure.items() if key != "closure"}
                else:
                    self.assertNotIn("closure", structure)
                    self.assertEqual(Path(structure["path"]), self.sources[name])
                    portable = {**structure, "path": self.sources[name].name}
                self.assertEqual((folder / "structure.json").read_bytes(),
                                 json.dumps(portable, separators=(",", ":")).encode())
                # Every part is meshed before the structure is read: it names each part's unmeshed faces.
                self.assertTrue(all("unmeshed" in prototype for prototype in structure["prototypes"]))
                tessellation = structure["tessellation"]
                for key in {prototype["key"] for prototype in structure["prototypes"]}:
                    part, held = f"{api}/parts/{quote(key, safe='')}", folder / "parts" / self.segment(key)
                    buffer = (held / f"{tessellation}.xbm").read_bytes()
                    self.assertEqual(buffer[:4], b"XBM2")
                    self.assertEqual(buffer, self.live(f"{part}?tessellation={quote(tessellation)}"))
                    self.assertEqual((held / "elements.json").read_bytes(), self.live(part + "/elements"))
                self.assertEqual((folder / "measure.json").read_bytes(), self.live(api + "/measure"))
                self.assertEqual((folder / "look.json").read_bytes(), self.live("/api/v1/look"))
                self.assertEqual((folder / "look" / "environment.hdr").read_bytes(), self.live("/api/v1/look/environment"))
                # No joints, so no mechanism, and no page kept a picture of it.
                self.assertFalse({"kinematics.json", "thumbnail.png"} & self.files(folder))
        source = self.live(self.api("stl") + "/source")
        self.assertEqual((self.out / "stl.view" / "source.stl").read_bytes(), source)
        self.assertEqual(source, self.sources["stl"].read_bytes())
        drawing = self.live(self.api("dxf") + "/drawing")
        self.assertEqual(json.loads(drawing)["schemaVersion"] > 0, True, drawing[:200])
        self.assertEqual((self.out / "dxf.view" / "drawing.json").read_bytes(), drawing)

    def test_a_robots_bundle_holds_its_meshes_and_names_them_where_it_holds_them(self) -> None:
        folder, api = self.out / "urdf.view", self.api("urdf")
        structure = json.loads(self.live(api + "/structure"))
        meshes = self.base / "robot" / "meshes"
        self.assertEqual(len(structure["visuals"]), 3)
        # Each mesh a page reads -- a primitive by its digest, a link's file by its path on this computer -- is
        # in the bundle byte for byte, named by its content.
        for visual in structure["visuals"]:
            url = visual["mesh"]["url"]
            data = self.live(url)
            if url.startswith(api + "/parts/"):
                held = f"parts/{url.rsplit('/', 1)[1]}.glb"
                self.assertEqual(visual["mesh"]["format"], "glb")
            else:
                self.assertTrue(url.startswith("/api/v1/local/files?path="), url)
                self.assertEqual(data, (meshes / "head.stl").read_bytes())
                held = f"meshes/{hashlib.sha256(data).hexdigest()}.stl"
            self.assertEqual((folder / held).read_bytes(), data)
            visual["mesh"]["url"] = held
        # The structure is the answer but for where each mesh is: its URL is its path in the bundle, and the
        # path a link's facts give its file is the file's name alone.
        for link in structure["links"]:
            for fact in link["visuals"]:
                if "path" in fact:
                    self.assertEqual(Path(fact["path"]), meshes / "head.stl")
                    fact["path"] = "head.stl"
        self.assertEqual((folder / "structure.json").read_bytes(), json.dumps(structure, separators=(",", ":")).encode())

    def test_a_parts_table_holds_what_asking_for_each_element_answers(self) -> None:
        # The live answer of one element is its row of the table and two things of its document, which a
        # table, named by the part's geometry alone, leaves out: whether the face is meshed, and -- of a
        # model's document -- what made it, which is served live and never written.
        for name in ("model", "step"):
            folder, api = self.out / f"{name}.view", self.api(name)
            structure = json.loads((folder / "structure.json").read_bytes())
            measured = json.loads((folder / "measure.json").read_bytes())
            for prototype in structure["prototypes"]:
                key = prototype["key"]
                part = f"{api}/parts/{quote(key, safe='')}"
                table = json.loads((folder / "parts" / self.segment(key) / "elements.json").read_bytes())
                self.assertEqual(set(table), {*ELEMENTS, "groups"})
                for plural, kind in ELEMENTS.items():
                    with self.subTest(source=name, part=prototype["name"], kind=kind):
                        # Every element of the part, by the ordinals its names go by.
                        self.assertEqual(set(table[plural]), set(prototype[f"{kind}Names"]))
                        self.assertTrue(table[plural])
                        for ordinal, facts in table[plural].items():
                            live = json.loads(self.live(f"{part}/{plural}/{ordinal}"))
                            self.assertEqual(set(live) - set(facts),
                                             ({"meshed"} if kind == "face" else set()) | ({"made_by"} if name == "model" else set()))
                            self.assertEqual({field: live[field] for field in facts}, facts)
                            if kind == "face":
                                self.assertIs(live["meshed"], int(ordinal) not in prototype["unmeshed"])
                self.assertEqual(table["groups"], json.loads(self.live(part + "/groups")))
                self.assertEqual(measured[key], json.loads(self.live(part + "/volume")))

    def test_a_bundle_written_again_after_an_edit_rewrites_only_what_changed(self) -> None:
        from cad.engine import api
        from cad.engine.ids import model_id

        script, folder = self.base / "edited.py", self.out / "kit.view"
        script.write_text(textwrap.dedent(EDITED).replace("HEIGHT", "6"), encoding="utf-8")
        self.run_script("edited.py")
        ident = model_id(script, "kit")
        first = api.export(ident, folder)[0]
        before = self.manifest(folder)
        stamps = {path: (folder / path).stat().st_mtime_ns for path in self.files(folder)}
        parts = {path.split("/")[1] for path in before["files"] if path.startswith("parts/")}
        self.assertEqual(len(parts), 2)

        # Written again with nothing changed: nothing is written.
        again = api.export(ident, folder)[0]
        self.assertEqual((again.written, again.view["written"], again.view["removed"]), (False, [], []))
        self.assertEqual(again.bytes, first.bytes)

        # The peg made taller, the plate left alone: a small edit, run.
        script.write_text(textwrap.dedent(EDITED).replace("HEIGHT", "7"), encoding="utf-8")
        self.run_script("edited.py")
        edited = api.export(ident, folder)[0]
        after = self.manifest(folder)
        kept = {path for path in after["files"] if path in before["files"] and after["files"][path] == before["files"][path]}
        added = set(after["files"]) - set(before["files"])
        gone = set(before["files"]) - set(after["files"])
        # One part's two files are new, the peg's, and the peg's old two are gone; the plate's are the same files.
        self.assertEqual({len(added), len(gone)}, {2})
        self.assertEqual({path.rsplit("/", 1)[1] for path in added}, {f"{json.loads((folder / 'structure.json').read_bytes())['tessellation']}.xbm", "elements.json"})
        self.assertEqual(len({path.split("/")[1] for path in added}), 1)
        self.assertEqual(len({path.split("/")[1] for path in kept if path.startswith("parts/")}), 1)
        self.assertEqual(set(edited.view["removed"]), gone)
        # Written: the new part's files, and the document's own that say it changed. Nothing else.
        self.assertEqual(set(edited.view["written"]), added | {"manifest.json", "structure.json", "measure.json"})
        self.assertLessEqual({"look.json", "look/environment.hdr"}, kept)
        for path in kept:
            self.assertEqual((folder / path).stat().st_mtime_ns, stamps[path], f"{path} was written again")
        self.assertEqual(self.files(folder), {*after["files"], "manifest.json"})
        self.assertNotEqual(after["document"]["version"], before["document"]["version"])

    def test_an_export_that_fails_leaves_the_folder_as_it_was(self) -> None:
        from cad.engine import api
        from cad.engine.api import EngineError

        # A robot of its own, bundled; then a visual of it named by the folder it is in, which no bundle holds.
        source, folder = self.base / "robot" / "named.urdf", self.out / "named.view"
        source.write_text(ROBOT.replace("NAME", "plinth"), encoding="utf-8")
        api.export(source, folder)
        before = {path: ((folder / path).read_bytes(), (folder / path).stat().st_mtime_ns) for path in self.files(folder)}
        source.write_text(ROBOT.replace("NAME", (self.base / "robot" / "plinth").as_posix()), encoding="utf-8")
        for target in (folder, self.out / "unmade.view"):
            with self.subTest(folder=target.name):
                with self.assertRaises(EngineError) as failed:
                    api.export(source, target)
                self.assertIn("would name a folder of this computer", str(failed.exception))
        # The earlier bundle is byte for byte what it was, no folder was made for the new one, and nothing
        # the export gathered is left beside them.
        self.assertEqual({path: ((folder / path).read_bytes(), (folder / path).stat().st_mtime_ns)
                          for path in self.files(folder)}, before)
        self.assertFalse((self.out / "unmade.view").exists())
        self.assertEqual([path.name for path in self.out.iterdir() if path.name.endswith(".tmp")], [])

    def test_a_bundle_holds_the_picture_a_page_kept(self) -> None:
        from cad.engine import api
        from cad.engine.ids import file_id

        source = self.base / "pictured.dxf"
        shutil.copyfile(self.sources["dxf"], source)
        picture = b"\x89PNG\r\n\x1a\n a page's picture of it"
        for change in ({"action": "open"}, {"action": "thumbnail", "png": base64.b64encode(picture).decode()}):
            self.live("/api/v1/documents", "PATCH", {**change, "path": str(source)})
        api.export(source, self.out / "pictured.view")
        self.assertEqual(self.live(f"/api/v1/documents/{file_id(source)}/thumbnail"), picture)
        self.assertEqual((self.out / "pictured.view" / "thumbnail.png").read_bytes(), picture)
        self.assertEqual(self.manifest(self.out / "pictured.view")["files"]["thumbnail.png"]["type"], "image/png")

    def test_a_bundle_names_no_folder_of_this_computer(self) -> None:
        home = os.path.expanduser("~")
        places = {str(self.base), self.base.as_posix(), str(self.state), os.environ.get("CAD_STATE_DIR") or str(self.base)}
        if len(Path(home).parts) > 1:
            places.add(home)
        needles = {spelled.encode() for place in places for spelled in (place, json.dumps(place)[1:-1])}
        for name in self.rows:
            folder = self.out / f"{name}.view"
            for path in sorted(self.files(folder)):
                data = (folder / path).read_bytes()
                for needle in needles:
                    self.assertNotIn(needle, data, f"{name}.view/{path} names {needle!r}")
        # The live answers do name them, where the bundle's do not: a model's elements say the file that made
        # them, and a robot's links where their mesh files are.
        key = json.loads((self.out / "model.view" / "structure.json").read_bytes())["prototypes"][0]["key"]
        face = json.loads(self.live(f"{self.api('model')}/parts/{key}/faces/1"))
        self.assertEqual(Path(face["made_by"]["file"]), self.base / "models.py")
        self.assertIn(json.dumps(str(self.base / "robot" / "meshes" / "head.stl")).encode(),
                      self.live(self.api("urdf") + "/structure"))

    def test_what_is_no_view_bundle_is_refused_before_anything_is_written(self) -> None:
        from cad.engine import api
        from cad.engine.export import ExportRefused

        xbf = self.sources["xbf"]
        junk = self.out / "junk.view"
        junk.mkdir()
        (junk / "notes.txt").write_text("mine", encoding="utf-8")
        cases = {
            "in a command of its own": lambda: api.export(xbf, self.out / "one.view", self.out / "one.glb"),
            "takes no tolerance": lambda: api.export(xbf, self.out / "two.view", tolerance=0.1),
            "written by the CAD server": lambda: api.export(xbf, self.out / "three.view", daemon=False),
            "holds other files and no manifest.json": lambda: api.export(xbf, junk),
        }
        for words, export in cases.items():
            with self.subTest(refusal=words):
                with self.assertRaises(ExportRefused) as refused:
                    export()
                self.assertIn(words, str(refused.exception))
        self.assertEqual(self.files(junk), {"notes.txt"})
        self.assertFalse([path.name for path in self.out.iterdir() if path.name.startswith(("one.", "two.", "three."))])

    def test_the_command_says_the_bundle_it_wrote(self) -> None:
        folder = self.out / "said.view"
        done = engine_daemon.run([sys.executable, "-m", "cad_server.cli", "dxf", "export", str(self.sources["dxf"]),
                                  str(folder), "--json"], env=self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        answer = json.loads(done.stdout)
        (row,) = answer["files"]
        self.assertEqual((answer["ok"], row["kind"], Path(row["path"]), row["written"]), (True, "view", folder, True))
        self.assertEqual(row["view"]["document"], self.manifest(folder)["document"])
        self.assertEqual(row["view"]["files"], len(self.files(folder)))


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); the class still names its own engine folder.
    engine_daemon.isolate(unittest.addModuleCleanup, started=False)


if __name__ == "__main__":
    unittest.main()
