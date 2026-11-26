"""A file's view bundle, what ``cad share`` uploads as a share's view (``api.bundle``, the share's step, which no
export is), written by an engine of this test's own and held to the answers that engine gives a page over HTTP: every file the manifest lists is there with its
size and digest, each is the live answer byte for byte (but what a structure says of the computer it was
answered on: a file's ``path``, a model's ``closure``, where a robot's meshes are; and the two things it
holds apart, its mechanism and its prototypes' element names, which its reader puts back), a prototype's
names are a file named by its bytes, a part's table holds exactly what asking for each element answers of its
geometry, a document's part files are asked at once, a bundle written again after an edit rewrites the
changed part's files and no other part's, a writing that fails leaves the folder as it was, and no file of a
bundle names a folder of the computer it was made on. A model (its ``.xbf``), a STEP, an STL, a DXF and a URDF each
have one; an export takes no ``.view`` destination.

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
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the packages' sources, as PYTHONPATH names them

# The peg turns in the plate: a mechanism. The two rims are of one function, so named alike, and of two
# geometries; the boss and the lug are of one geometry, so one part's key, and named apart.
MODEL = """
import build123d as bd
from cad import model, step
from bd_materials import metals


def rim(width):
    made = bd.Box(width, 4, 2)
    made.label = "rim"
    return made


def boss():
    made = bd.Box(3, 3, 3)
    made.label = "boss"
    return made


def lug():
    made = bd.Box(3, 3, 3)
    made.label = "boss"
    return made


@model("XBF/pair.xbf")
@step("pair.step")
def pair():
    plate = bd.Box(10, 6, 4) - bd.Cylinder(1, 10)
    plate.label, plate.color = "plate", bd.Color(0.8, 0.1, 0.1)
    peg = bd.Pos(8, 0, 4) * bd.Cylinder(1, 6)
    peg.label, peg.material = "peg", metals.aluminum()
    turn = bd.Axis((8, 0, 4), (0, 0, 1))
    bd.RevoluteJoint("turn", plate, axis=turn, angular_range=(-90, 90))
    bd.RigidJoint("turn", peg, bd.Plane(origin=turn.position, z_dir=turn.direction).location)
    plate.joints["turn"].connect_to(peg.joints["turn"], angle=0)
    return bd.Compound(children=[plate, peg, bd.Pos(0, 10, 0) * rim(4), bd.Pos(10, 10, 0) * rim(6),
                                 bd.Pos(0, 20, 0) * boss(), bd.Pos(10, 20, 0) * lug()], label="pair")


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
NAMES = ("faceNames", "edgeNames", "vertexNames")


def put_back(folder: Path) -> dict:
    """A bundle's structure as its reader answers it (**View bundle**): the mechanism put back from
    ``kinematics.json`` where the bundle holds one, and each prototype's element names from the file it
    names, in place of ``names``."""
    structure = json.loads((folder / "structure.json").read_bytes())
    if (folder / "kinematics.json").is_file():
        structure["kinematics"] = json.loads((folder / "kinematics.json").read_bytes())
    for prototype in structure["prototypes"]:
        if "names" in prototype:
            prototype.update(json.loads((folder / prototype.pop("names")).read_bytes()))
    return structure


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
        from cad.engine.ids import file_id

        cls.model = file_id(cls.base / "XBF" / "pair.xbf")  # a model's id is its .xbf's
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
        # One bundle of each source, written once for every test that reads one: a model by its .xbf, which a live
        # worker holds.
        cls.sources = {"model": cls.base / "XBF" / "pair.xbf", "step": cls.base / "pair.step",
                       "stl": cls.out / "pair.stl", "dxf": cls.base / "plate.dxf",
                       "urdf": cls.base / "robot" / "arm.urdf"}
        cls.rows = {name: api.bundle(source, cls.out / name) for name, source in cls.sources.items()}

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
        opening = {"path": str(self.sources[name])}
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
                folder = self.out / name
                manifest = self.manifest(folder)
                self.assertEqual((manifest["format"], manifest["made"]["tool"]), ("view-bundle/1", "cad"))
                self.assertEqual(self.files(folder), {*manifest["files"], "manifest.json"})
                for path, entry in manifest["files"].items():
                    data = (folder / path).read_bytes()
                    self.assertEqual((entry["bytes"], entry["sha256"]), (len(data), hashlib.sha256(data).hexdigest()), path)
                    self.assertTrue(entry["type"], path)
                # What the writing answers is the folder and what it holds.
                self.assertEqual((Path(row["path"]), row["removed"]), (folder, []))
                self.assertEqual((row["document"], row["files"]), (manifest["document"], len(manifest["files"]) + 1))
                self.assertEqual(set(row["written"]), self.files(folder))
        from cad.engine.ids import file_id

        envelope = json.loads(self.live(f"/api/v1/documents/{self.model}"))
        structure = json.loads(self.live(self.api("model") + "/structure"))
        self.assertEqual(self.manifest(self.out / "model")["document"],
                         {"id": self.model, "kind": "model", "name": envelope["name"], "version": structure["version"]})
        files = ("step", "stl", "dxf", "urdf")
        self.assertEqual([self.manifest(self.out / name)["document"] for name in files],
                         [{"id": file_id(self.sources[name]), "kind": name, "name": self.sources[name].name,
                           "version": json.loads(self.live(f"/api/v1/documents/{file_id(self.sources[name])}"))["version"]
                           if name in ("stl", "dxf", "urdf") else
                           json.loads((self.out / name / "structure.json").read_bytes())["version"]}
                          for name in files])
        # A mesh file's bundle is the file, which its page parses; a drawing's, its drawing; a robot's, its
        # structure, the one primitive cad meshed for it and the one mesh file its links draw, each once.
        self.assertEqual(self.files(self.out / "stl"), {"manifest.json", "source.stl"})
        self.assertEqual(self.files(self.out / "dxf"), {"manifest.json", "drawing.json"})
        mesh = hashlib.sha256((self.base / "robot" / "meshes" / "head.stl").read_bytes()).hexdigest()
        robot = self.files(self.out / "urdf")
        self.assertLessEqual({"manifest.json", "structure.json", f"meshes/{mesh}.stl"}, robot)
        self.assertEqual([len(robot), len([path for path in robot if path.startswith("parts/") and path.endswith(".glb")])],
                         [4, 1])

    def test_each_bundled_answer_is_the_live_answer(self) -> None:
        for name in ("model", "step"):
            with self.subTest(source=name):
                folder, api = self.out / name, self.api(name)
                structure = json.loads(self.live(api + "/structure"))
                # A structure is the answer but for what it says of the computer it was answered on: a
                # model's names the code that built it (its closure: the script and its modules by path, their
                # names), which its bundle leaves out, and its path is its id, as a live worker answers it; a
                # file's names where the file is, and its bundle the file's name alone.
                if name == "model":
                    self.assertEqual(structure["closure"]["source"]["function"], "pair")
                    self.assertEqual(structure["path"], self.model)
                    portable = {key: value for key, value in structure.items() if key != "closure"}
                else:
                    self.assertNotIn("closure", structure)
                    self.assertEqual(Path(structure["path"]), self.sources[name])
                    portable = {**structure, "path": self.sources[name].name}
                # And it holds two things apart, each once, which its reader puts back: the mechanism, the
                # same object as kinematics.json, and each prototype's element names, in a file of their own.
                bundled = json.loads((folder / "structure.json").read_bytes())
                self.assertEqual((folder / "structure.json").read_bytes(), json.dumps(bundled, separators=(",", ":")).encode())
                self.assertEqual(put_back(folder), portable)
                self.assertNotIn("kinematics", bundled)
                self.assertEqual([prototype for prototype in bundled["prototypes"] if set(NAMES) & set(prototype)], [])
                self.assertEqual("kinematics.json" in self.files(folder), "kinematics" in structure)
                if "kinematics" in structure:
                    self.assertEqual((folder / "kinematics.json").read_bytes(), self.live(api + "/kinematics"))
                if name == "model":  # the model's mechanism, which its xbf holds too
                    self.assertIn("kinematics", structure)
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
                # No page kept a picture of it.
                self.assertNotIn("thumbnail.png", self.files(folder))
        source = self.live(self.api("stl") + "/source")
        self.assertEqual((self.out / "stl" / "source.stl").read_bytes(), source)
        self.assertEqual(source, self.sources["stl"].read_bytes())
        drawing = self.live(self.api("dxf") + "/drawing")
        self.assertEqual(json.loads(drawing)["schemaVersion"] > 0, True, drawing[:200])
        self.assertEqual((self.out / "dxf" / "drawing.json").read_bytes(), drawing)

    def test_a_prototypes_names_are_a_file_named_by_its_bytes(self) -> None:
        for name in ("model", "step"):
            with self.subTest(source=name):
                folder = self.out / name
                bundled = json.loads((folder / "structure.json").read_bytes())
                held = {path for path in self.files(folder) if path.startswith("names/")}
                self.assertEqual(held, {prototype["names"] for prototype in bundled["prototypes"] if "names" in prototype})
                self.assertTrue(held)
                # Compact JSON of a prototype's names alone, every key sorted, named by its SHA-256.
                for path in held:
                    body = (folder / path).read_bytes()
                    self.assertEqual(path, f"names/{hashlib.sha256(body).hexdigest()}.json")
                    self.assertEqual(body, json.dumps(json.loads(body), separators=(",", ":"), sort_keys=True).encode())
                    self.assertLessEqual(set(json.loads(body)), set(NAMES))
        # Named by what it holds, never by a part's key: the two rims, two geometries named alike, share one;
        # the boss and the lug, one geometry named apart, hold one each.
        prototypes = json.loads((self.out / "model" / "structure.json").read_bytes())["prototypes"]
        named = {label: [prototype for prototype in prototypes if prototype["name"] == label] for label in ("rim", "boss")}
        self.assertEqual([(len({one["key"] for one in alike}), len({one["names"] for one in alike}))
                          for alike in named.values()], [(2, 1), (1, 2)])

    def test_a_robots_bundle_holds_its_meshes_and_names_them_where_it_holds_them(self) -> None:
        folder, api = self.out / "urdf", self.api("urdf")
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
            folder, api = self.out / name, self.api(name)
            structure = put_back(folder)
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

        script, folder = self.base / "edited.py", self.out / "kit"
        script.write_text(textwrap.dedent(EDITED).replace("HEIGHT", "6"), encoding="utf-8")
        self.run_script("edited.py")
        xbf = self.base / "kit.xbf"  # @model saves it beside its script
        first = api.bundle(xbf, folder)
        before = self.manifest(folder)
        stamps = {path: (folder / path).stat().st_mtime_ns for path in self.files(folder)}
        parts = {path.split("/")[1] for path in before["files"] if path.startswith("parts/")}
        self.assertEqual(len(parts), 2)

        # Written again with nothing changed: nothing is written.
        again = api.bundle(xbf, folder)
        self.assertEqual((again["written"], again["removed"]), ([], []))
        self.assertEqual(again["bytes"], first["bytes"])

        # The peg made taller, the plate left alone: a small edit, run.
        script.write_text(textwrap.dedent(EDITED).replace("HEIGHT", "7"), encoding="utf-8")
        self.run_script("edited.py")
        edited = api.bundle(xbf, folder)
        after = self.manifest(folder)
        kept = {path for path in after["files"] if path in before["files"] and after["files"][path] == before["files"][path]}
        added = set(after["files"]) - set(before["files"])
        gone = set(before["files"]) - set(after["files"])
        # One part's two files are new, the peg's, and the peg's old two are gone; the plate's are the same files.
        self.assertEqual({len(added), len(gone)}, {2})
        self.assertEqual({path.rsplit("/", 1)[1] for path in added}, {f"{json.loads((folder / 'structure.json').read_bytes())['tessellation']}.xbm", "elements.json"})
        self.assertEqual(len({path.split("/")[1] for path in added}), 1)
        self.assertEqual(len({path.split("/")[1] for path in kept if path.startswith("parts/")}), 1)
        self.assertEqual(set(edited["removed"]), gone)
        # Written: the new part's files, and the document's own that say it changed. Nothing else.
        self.assertEqual(set(edited["written"]), added | {"manifest.json", "structure.json", "measure.json"})
        self.assertLessEqual({"look.json", "look/environment.hdr"}, kept)
        for path in kept:
            self.assertEqual((folder / path).stat().st_mtime_ns, stamps[path], f"{path} was written again")
        self.assertEqual(self.files(folder), {*after["files"], "manifest.json"})
        self.assertNotEqual(after["document"]["version"], before["document"]["version"])

    def test_a_writing_that_fails_leaves_the_folder_as_it_was(self) -> None:
        from cad.engine import api
        from cad.engine.api import EngineError

        # A robot of its own, bundled; then a visual of it named by the folder it is in, which no bundle holds.
        source, folder = self.base / "robot" / "named.urdf", self.out / "named"
        source.write_text(ROBOT.replace("NAME", "plinth"), encoding="utf-8")
        api.bundle(source, folder)
        before = {path: ((folder / path).read_bytes(), (folder / path).stat().st_mtime_ns) for path in self.files(folder)}
        source.write_text(ROBOT.replace("NAME", (self.base / "robot" / "plinth").as_posix()), encoding="utf-8")
        for target in (folder, self.out / "unmade"):
            with self.subTest(folder=target.name):
                with self.assertRaises(EngineError) as failed:
                    api.bundle(source, target)
                self.assertIn("would name a folder of this computer", str(failed.exception))
        # The earlier bundle is byte for byte what it was, no folder was made for the new one, and nothing
        # the writing gathered is left beside them.
        self.assertEqual({path: ((folder / path).read_bytes(), (folder / path).stat().st_mtime_ns)
                          for path in self.files(folder)}, before)
        self.assertFalse((self.out / "unmade").exists())
        self.assertEqual([path.name for path in self.out.iterdir() if path.name.endswith(".tmp")], [])

    def test_a_bundle_holds_the_picture_a_page_kept(self) -> None:
        from cad.engine import api
        from cad.engine.ids import file_id

        source = self.base / "pictured.dxf"
        shutil.copyfile(self.sources["dxf"], source)
        picture = b"\x89PNG\r\n\x1a\n a page's picture of it"
        for change in ({"action": "open"}, {"action": "thumbnail", "png": base64.b64encode(picture).decode()}):
            self.live("/api/v1/documents", "PATCH", {**change, "path": str(source)})
        api.bundle(source, self.out / "pictured")
        self.assertEqual(self.live(f"/api/v1/documents/{file_id(source)}/thumbnail"), picture)
        self.assertEqual((self.out / "pictured" / "thumbnail.png").read_bytes(), picture)
        self.assertEqual(self.manifest(self.out / "pictured")["files"]["thumbnail.png"]["type"], "image/png")

    def test_a_bundle_names_no_folder_of_this_computer(self) -> None:
        home = os.path.expanduser("~")
        places = {str(self.base), self.base.as_posix(), str(self.state), os.environ.get("CAD_STATE_DIR") or str(self.base)}
        if len(Path(home).parts) > 1:
            places.add(home)
        needles = {spelled.encode() for place in places for spelled in (place, json.dumps(place)[1:-1])}
        for name in self.rows:
            folder = self.out / name
            for path in sorted(self.files(folder)):
                data = (folder / path).read_bytes()
                for needle in needles:
                    self.assertNotIn(needle, data, f"{name}/{path} names {needle!r}")
        # The live answers do name them, where the bundle's do not: a model's elements say the file that made
        # them, and a robot's links where their mesh files are.
        key = json.loads((self.out / "model" / "structure.json").read_bytes())["prototypes"][0]["key"]
        face = json.loads(self.live(f"{self.api('model')}/parts/{key}/faces/1"))
        self.assertEqual(Path(face["made_by"]["file"]), self.base / "models.py")
        self.assertIn(json.dumps(str(self.base / "robot" / "meshes" / "head.stl")).encode(),
                      self.live(self.api("urdf") + "/structure"))

    def test_what_is_no_bundle_is_refused_before_anything_is_written_and_no_export_writes_one(self) -> None:
        from cad import model
        from cad.engine import api
        from cad.engine.export import ExportRefused

        xbf = self.sources["model"]
        junk = self.out / "junk"
        junk.mkdir()
        (junk / "notes.txt").write_text("mine", encoding="utf-8")
        (self.base / "notes.txt").write_text("mine", encoding="utf-8")
        cases = {
            "holds other files and no manifest.json": lambda: api.bundle(xbf, junk),
            "is no CAD file": lambda: api.bundle(self.base / "notes.txt", self.out / "notes"),
            "no document": lambda: api.bundle(self.base / "gone.stl", self.out / "gone"),
        }
        for words, writing in cases.items():
            with self.subTest(refusal=words):
                with self.assertRaises(ExportRefused) as refused:
                    writing()
                self.assertIn(words, str(refused.exception))
        self.assertEqual(self.files(junk), {"notes.txt"})
        self.assertFalse((self.out / "notes").exists() or (self.out / "gone").exists())
        # A view bundle is no export: a .view destination is refused as any other unknown suffix, by the library
        # and by the command, and nothing is written.
        with self.assertRaisesRegex(ExportRefused, r"^pair\.view: an export is one of "):
            model.export(xbf, self.out / "pair.view")
        done = engine_daemon.run([sys.executable, "-m", "cad_server.cli", "model", "export", str(xbf),
                                  str(self.out / "said.view"), "--json"], env=self.env)
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("said.view: an export is one of ", json.loads(done.stdout)["error"])
        self.assertFalse((self.out / "pair.view").exists() or (self.out / "said.view").exists())


class AskedAtOnceTest(unittest.TestCase):
    """A document's part files are asked at once, ``ASKS`` at a time (``take_all``), each put at its path as it
    comes in: the engine makes each part's table in a process of its pool, so asked one after another a first
    bundle's tables would be made on one core."""

    def test_a_documents_part_files_are_asked_at_once(self) -> None:
        from cad_server.viewer import bundle

        asks = [(f"parts/{key}/{file}", f"/api/v1/documents/model/m/parts/{key}/{file}")
                for key in ("a", "b") for file in ("0.25-28.5.xbm", "elements.json")]
        together = threading.Barrier(len(asks), timeout=30)  # each answered once every one is asked

        class App:  # the engine's page's application, standing in: each answer is the path it was asked at
            def handle(self, request, response) -> None:
                together.wait()
                response.send_bytes(200, request.path.encode(), "application/octet-stream")

        folder = Path(tempfile.mkdtemp(prefix="asked-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        (folder / "stage").mkdir()
        writing = bundle._Bundle(App(), folder / "kit", folder / "stage", {}, "0", [])
        with mock.patch.object(bundle, "ASKS", len(asks)):
            writing.take_all(asks)
        self.assertEqual({path: (folder / "stage" / path).read_bytes() for path, _url in asks},
                         {path: url.encode() for path, url in asks})
        self.assertEqual(sorted(writing.files), sorted(path for path, _url in asks))


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); the class still names its own engine folder.
    engine_daemon.isolate(unittest.addModuleCleanup, started=False)


if __name__ == "__main__":
    unittest.main()
