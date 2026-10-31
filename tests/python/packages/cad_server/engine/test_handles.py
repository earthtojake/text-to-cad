"""A model call returns its document's handle -- never a bare shape, never a report -- and
``model(shape, name=...)`` makes a document of a shape a program holds.

A handle has the document's id and page; its ``shape`` is transferred into the caller, the kernel
loaded, on first access and never before; ``handle.export(...)`` is ``export(handle, ...)``. Inside a
body a child's call returns its handle too, whose ``shape`` is the result in the worker, which the
caller composes. A shape handed over is held, cached and served as a drained document is, its page
and its export work, its record says a program the engine did not run showed it (no command builds
it again), ``name=`` names it, and the animations passed with it are baked into its GLB. Through a
real daemon in private engine, state and cache folders."""

from __future__ import annotations

import json
import os
import shutil
import struct
import sys
import tempfile
import textwrap
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

from cad.engine.ids import derived_id, model_id  # noqa: E402
from cad_server.engine.registry import Registry  # noqa: E402

PARTS = """
import build123d as bd
from cad import model, xbf


@model
def peg():
    return bd.Cylinder(2, 10)


@xbf("XBF/base.xbf")
def base():
    first, second = peg(), peg()
    # A child's call is its handle, inside the body too: its id, no page yet, its result here.
    assert type(first).__name__ == "Document" and first.id == peg.id and first.url is None, first
    return bd.Compound(children=[bd.Box(20, 20, 3), first.shape.moved(bd.Pos(5, 0, 6)),
                                 second.shape.moved(bd.Pos(-5, 0, 6))], label="base")
"""

CALLER = """
import json
import sys

import cad
import parts

handle = parts.base()
before = "OCP" in sys.modules
shape = handle.shape
handle.export("out/a.step")
cad.export(handle, "out/b.step")
print("RESULT " + json.dumps({
    "type": type(handle).__name__, "id": handle.id, "url": handle.url, "name": handle.name,
    "kernel_before": before, "kernel_after": "OCP" in sys.modules, "volume": shape.volume,
    "labels": sorted(child.label for child in shape.children), "again": handle.shape is shape}))
"""

# Eight models with no file of their own, each body noting its run (an append: an output, which no
# key hears), exported by their functions and one by its handle, and drawn by a function where OCCT draws.
EIGHT = """
import pathlib

import build123d as bd
from cad import model

RUNS = pathlib.Path(__file__).with_name("runs.txt")


def _box(name, size):
    with RUNS.open("a", encoding="utf-8") as runs:
        runs.write(name + "\\n")
    box = bd.Box(size, size, size)
    box.label = name
    return box
""" + "".join(f"""

@model
def m{at}():
    return _box("m{at}", {at + 1})
""" for at in range(8))

EXPORTER = """
import json
import sys

import cad
import eight

MODELS = [getattr(eight, f"m{at}") for at in range(8)]
for found in MODELS:
    cad.export(found, f"out/{found.name}.step")
eight.m0().export("out/handle.step")
if "--draw" in sys.argv:
    cad.snapshot(eight.m1, "out/m1.png", width=64, height=48)
print("RESULT " + json.dumps({"ok": True}))
"""

HANDED = """
import json

import build123d as bd
from cad import model
from cad.gltf import animation

lid = bd.Box(10, 10, 2)
lid.label = "lid"
crate = bd.Compound(children=[bd.Box(10, 10, 10), lid.moved(bd.Pos(0, 0, 6))], label="crate")
lift = animation(crate, "lift", duration=2).translation("lid", by=(0, 0, 10), end=2)
handle = model(crate, name="crate", animations=[lift])
handle.export("crate.glb", "crate.step")
tag = model(bd.Box(1, 1, 1), name="tag")
print("RESULT " + json.dumps({"id": handle.id, "url": handle.url, "same": handle.shape is crate, "tag": tag.id}))
"""


HINGE = """
import build123d as bd
from cad import model
from cad.ap242 import mechanism_state, posed


@model
def hinge():
    base = bd.Box(100, 60, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    arm = bd.Pos(40, 0, 20) * bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    base.label, arm.label = "base", "arm"
    elbow = bd.Axis((40, 0, 20), (0, -1, 0))
    bd.RevoluteJoint("elbow", base, axis=elbow, angular_range=(-10, 120))
    bd.RigidJoint("elbow", arm, bd.Plane(origin=elbow.position, z_dir=elbow.direction).location)
    base.joints["elbow"].connect_to(arm.joints["elbow"], angle=0)
    assembly = bd.Compound(children=[base, arm], label="hinge")
    return mechanism_state(assembly, "open", elbow=90)


@model
def hinge_open():
    return posed(hinge().shape, "open")
"""

POSER = """
import json

from cad.ap242 import posed
from hinge import hinge, hinge_open


def arm(shape):
    box = next(part for part in shape.leaves if part.label == "arm").bounding_box()
    return [round(value, 6) for value in (*box.min, *box.max)]


handle = hinge()
try:
    posed(handle.shape, "open")
    refused = None
except ValueError as error:
    refused = str(error)
print("RESULT " + json.dumps({"built": arm(handle.shape), "posed": arm(posed(handle, "open")),
                              "valued": arm(posed(handle, {"elbow": 90})), "in_body": arm(hinge_open().shape),
                              "refused": refused}))
"""


# A child whose sub-assemblies stand turned and moved, and two readers of its ``.shape``: a body
# (``inside``, which notes what it read) and the program itself.
NESTED = """
import json
import pathlib

import build123d as bd
from cad import model


def tree(node, path=()):
    location = node.location.wrapped.Transformation()
    box = node.bounding_box()
    rows = [{"path": list(path), "kind": node.wrapped.ShapeType().name, "label": node.label,
             "location": [round(location.Value(row, column), 6) + 0.0 for row in (1, 2, 3) for column in (1, 2, 3, 4)],
             "box": [round(value, 6) + 0.0 for value in (*box.min, *box.max)]}]
    for at, child in enumerate(node.children or ()):
        rows += tree(child, path + (at,))
    return rows


@model
def arm():
    base = bd.Box(40, 40, 10).located(bd.Location((0, 0, 5)))
    servo = bd.Box(20, 10, 8).located(bd.Location((10, 0, 0)))
    screw = bd.Cylinder(1.5, 6).located(bd.Location((1, 2, 3), (0, 30, 0)))
    base.label, servo.label, screw.label = "base", "servo", "screw"
    clamp = bd.Compound(children=[screw], label="clamp").located(bd.Location((0, 5, 0), (90, 0, 0)))
    elbow = bd.Compound(children=[servo, clamp], label="elbow").located(bd.Location((100, 0, 0), (0, 0, 180)))
    return bd.Compound(children=[base, elbow], label="arm")


@model
def inside():
    shape = arm().shape
    pathlib.Path(__file__).with_name("inside.json").write_text(json.dumps(tree(shape)), encoding="utf-8")
    return shape


if __name__ == "__main__":
    inside()
    print("RESULT " + json.dumps({"inside": json.loads(pathlib.Path(__file__).with_name("inside.json").read_text()),
                                  "caller": tree(arm().shape)}))
"""


def _served(url: str, ident: str) -> dict:
    """The document a page serves (``/api/doc/<id>``), with the token its URL carries."""
    page, _, query = url.partition("?")
    base = page.rsplit("/", 1)[0]
    token = dict(part.split("=", 1) for part in query.split("&") if "=" in part).get("token", "")
    request = urllib.request.Request(f"{base}/api/doc/{ident}", headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - the engine's own server
        return json.loads(response.read())


def _glb_json(path: Path) -> dict:
    data = path.read_bytes()
    length = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20:20 + length])


class HandleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="handles-")))
        cls.engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cls.state, cls.cache = cls.folder / "state", cls.folder / "cache"
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.addClassCleanup(shutil.rmtree, cls.engine, True)
        cls.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(cls.engine),
                                         "CAD_STATE_DIR": str(cls.state), "CAD_CACHE_DIR": str(cls.cache),
                                         "CAD_ENGINE_MESH": "inline"},
                                        cls.addClassCleanup)
        cls.addClassCleanup(cls.cli, "stop")

    @classmethod
    def cli(cls, *args: str):
        return engine_daemon.run([sys.executable, "-m", "cad_server.engine", *args], cwd=cls.folder, env=cls.env)

    def project(self, name: str, files: dict[str, str]) -> Path:
        folder = self.folder / name
        folder.mkdir()
        for file, text in files.items():
            (folder / file).write_text(textwrap.dedent(text), encoding="utf-8")
        return folder

    def run_python(self, *args: str, cwd: Path, input: str | None = None) -> dict:
        done = engine_daemon.run([sys.executable, *args], cwd=cwd, env=self.env, input=input)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.rsplit("RESULT ", 1)[1])

    def ask(self, message: dict) -> dict:
        from cad.engine.client import request

        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(self.engine)}):
            return request(message, start=False) or {}

    def test_a_call_returns_a_handle_whose_shape_loads_on_first_access_and_a_child_s_composes(self) -> None:
        project = self.project("parts", {"parts.py": PARTS, "caller.py": CALLER})
        found = self.run_python("caller.py", cwd=project)
        ident = model_id(project / "parts.py", "base")
        self.assertEqual((found["type"], found["id"], found["name"]), ("Document", ident, "base"))
        self.assertTrue(found["url"].split("?")[0].endswith(f"/{ident}"), found["url"])
        self.assertEqual((found["kernel_before"], found["kernel_after"]), (False, True),
                         "the shape is transferred, and the kernel loaded, on its first access alone")
        self.assertAlmostEqual(found["volume"], 20 * 20 * 3 + 2 * 3.141592653589793 * 2 ** 2 * 10, places=3)
        self.assertEqual(found["labels"], ["part1", "peg", "peg"], "the built shape, the children's results placed")
        self.assertTrue(found["again"], "transferred once")
        self.assertEqual((project / "out/a.step").read_bytes(), (project / "out/b.step").read_bytes(),
                         "handle.export is export(handle)")
        self.assertEqual(_served(found["url"], ident)["name"], "base", "its page serves it")

    def test_a_model_exported_by_its_function_is_built_as_its_call_is_never_cold(self) -> None:
        """``export(model, path)`` is the model's call, then its handle's export: eight in one program
        run once, replay in the next run, and after a restart are taken from the engine's cache --
        no body runs again -- and write what the handle form writes, byte for byte. (A document taken
        from the cache writes its STEP as read back, a signed zero apart from the live build's: the
        handle form's the same.)"""
        from cad.engine.render import context
        from tests.python.support import opengl

        project = self.project("eight", {"eight.py": EIGHT, "exporter.py": EXPORTER})
        draw = ["--draw"] if opengl.draws(context.available(), "a snapshot is drawn by OCCT") else []
        runs = project / "runs.txt"
        self.run_python("exporter.py", *draw, cwd=project)
        self.assertEqual(sorted(runs.read_text(encoding="utf-8").split()), sorted(f"m{at}" for at in range(8)),
                         "each body ran once, the handle's call and the snapshot's reusing the first")
        first = {path.name: path.read_bytes() for path in (project / "out").glob("*.step")}
        self.assertEqual(first["m0.step"], first["handle.step"], "the function form writes the handle form's bytes")
        self.run_python("exporter.py", *draw, cwd=project)
        self.assertEqual(len(runs.read_text(encoding="utf-8").split()), 8, "a second program's run replays")
        self.assertEqual(self.cli("stop").returncode, 0)
        self.run_python("exporter.py", *draw, cwd=project)
        self.assertEqual(len(runs.read_text(encoding="utf-8").split()), 8, "after a restart: taken from the cache")
        self.assertEqual((project / "out/m0.step").read_bytes(), (project / "out/handle.step").read_bytes(),
                         "from the cache too, the function form writes the handle form's bytes")

    def test_a_shape_handed_over_is_a_document_held_served_exported_and_never_rebuilt(self) -> None:
        project = self.project("handed", {"hand.py": HANDED})
        found = self.run_python("hand.py", cwd=project)
        ident = derived_id(project / "hand.py", "crate")
        self.assertEqual((found["id"], found["tag"], found["same"]), (ident, derived_id(project / "hand.py", "tag"), True))
        self.assertEqual(_served(found["url"], ident)["name"], "crate", "its page serves it")
        self.assertEqual([clip["name"] for clip in _glb_json(project / "crate.glb").get("animations") or []],
                         ["lift"], "the animations passed are baked into its GLB")
        self.assertTrue((project / "crate.step").is_file())
        record = Registry(self.state).get(ident)
        self.assertEqual((record["kind"], record["entry"], record["program"]), ("shape", "crate", "hand.py"))
        self.assertEqual(set(record) - {"cache"}, {"schema", "id", "kind", "root", "home", "entry", "program",
                                                   "revision", "built", "created", "namespace", "name"}, "a model's shape, and the program that showed it")
        from cad_server.viewer.recents import RecentStore

        [shown] = [entry.public() for entry in RecentStore(self.state).list() if entry.path == ident]
        self.assertIn(f"a shape handed over by {project / 'hand.py'}, a program the engine did not run", shown["shown"],
                      "its words, from its program")
        # From a REPL: the working folder is its scope.
        repl = self.run_python("-", cwd=project, input="import json, build123d as bd\nfrom cad import model\n"
                               "h = model(bd.Box(2, 2, 2), name='scratch')\nprint('RESULT ' + json.dumps(h.id))\n")
        self.assertEqual(repl, derived_id(project, "scratch"))
        # Exported by its id, as any document the engine holds; after a restart, from the cache.
        self.assertEqual(self.cli("export", ident, str(project / "again.stl")).returncode, 0)
        self.assertEqual(self.cli("stop").returncode, 0)
        self.assertEqual(self.cli("export", ident, str(project / "restarted.stl")).returncode, 0)
        # With its cache file gone, nothing builds it again, and the words say so.
        self.assertEqual(self.cli("stop").returncode, 0)
        shutil.rmtree(self.cache / "documents" / ident)
        refused = self.cli("export", ident, str(project / "gone.stl"))
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertIn("a program the engine did not run: no script to rerun", refused.stderr)
        answer = self.ask({"op": "state", "id": ident})
        self.assertEqual((answer["state"], answer["rebuild"]), ("unsaved", None))


    def test_a_handle_is_posed_where_the_engine_holds_its_mechanism(self) -> None:
        # From a plain script, the handle is posed (its .shape carries no joints, and says what to pass
        # instead); in a body, the child's shape is posed as it always was.
        project = self.project("hinge", {"hinge.py": HINGE, "poser.py": POSER})
        found = self.run_python("poser.py", cwd=project)
        self.assertEqual(found["built"], [40, -10, 20, 160, 10, 30])
        # A quarter turn about -Y through (40, 0, 20) stands the arm up: its tip at z 140.
        self.assertEqual(found["posed"], [30, -10, 20, 40, 10, 140])
        self.assertEqual(found["valued"], found["posed"])
        self.assertEqual(found["in_body"], found["posed"])
        self.assertEqual(found["refused"], "posed() was given hinge's .shape, which carries its parts and not its "
                                           "joints: pass the handle the model call returns, posed(hinge(), 'open')")

    def test_a_child_s_shape_is_one_tree_in_the_body_and_in_the_caller(self) -> None:
        # Read in the calling process, a child's sub-assemblies keep the placements the body gave
        # them, and each part is the shape the body made, where the body put it: every node's
        # kind (a solid, not the compound the document wraps it in), label, placement and box are
        # the body's.
        project = self.project("nested", {"nested.py": NESTED})
        found = self.run_python("nested.py", cwd=project)
        self.assertEqual([row["path"] for row in found["caller"]], [[], [0], [1], [1, 0], [1, 1], [1, 1, 0]])
        elbow = next(row for row in found["caller"] if row["label"] == "elbow")
        self.assertEqual(elbow["location"][3], 100.0, "the elbow stands where the body put it, turned")
        self.maxDiff = None
        self.assertEqual(found["caller"], found["inside"])
        # After a restart the document comes from the engine's cache, read as its xbf: the same tree.
        self.assertEqual(self.cli("stop").returncode, 0)
        self.assertEqual(self.run_python("nested.py", cwd=project)["caller"], found["inside"])

    def test_a_relative_pythonpath_names_a_folder_of_the_caller_s_working_folder(self) -> None:
        # ``PYTHONPATH=src python src/sub/model.py`` finds ``src/dims.py`` as Python does: from the
        # folder the command ran in, never from the script's own folder, where the engine builds it.
        project = self.project("relative", {})
        (project / "src" / "sub").mkdir(parents=True)
        (project / "src" / "dims.py").write_text("WIDTH = 7\n", encoding="utf-8")
        (project / "src" / "sub" / "model.py").write_text(textwrap.dedent("""
            import json

            import build123d as bd
            from cad import model

            from dims import WIDTH


            @model
            def plate():
                return bd.Box(WIDTH, 2, 1)


            if __name__ == "__main__":
                print("RESULT " + json.dumps(round(plate().shape.bounding_box().size.X, 6)))
        """), encoding="utf-8")
        env = {**self.env, "PYTHONPATH": os.pathsep.join(("src", str(SRC)))}
        done = engine_daemon.run([sys.executable, "src/sub/model.py"], cwd=project, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout.rsplit("RESULT ", 1)[1]), 7.0)

    def test_an_export_a_program_makes_says_each_file_it_wrote_as_the_export_verb_does(self) -> None:
        project = self.project("exports", {"parts.py": PARTS, "exports.py": """
            import cad
            import parts

            handle = parts.base()
            handle.export("out/a.step", "out/a.stl")
            cad.export(handle, "out/a.step")
        """})
        done = engine_daemon.run([sys.executable, "exports.py"], cwd=project, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        said = [line for line in done.stdout.splitlines() if line.startswith(("wrote ", "unchanged "))]
        self.assertEqual([line.split(" (")[0] for line in said],
                         ["wrote out/a.step", "wrote out/a.stl", "unchanged out/a.step"], done.stdout)
        self.assertRegex(said[0], r"^wrote out/a\.step \(\d+(\.\d)? [KM]?B\) in \d+\.\d\ds$")


UNREACHED = """
import sys

import build123d as bd
from cad import model


@model
def peg():
    return bd.Cylinder(2, 10)


if __name__ == "__main__":
    if sys.argv[1:] == ["catch"]:
        try:
            peg()
        except ConnectionError:
            print("caught")
    else:
        peg()
"""


class UnreachedEngineTest(unittest.TestCase):
    def test_a_model_call_no_engine_serves_ends_in_one_line_on_stderr(self) -> None:
        """``python model.py`` and ``cad run model.py`` in a sandboxed shell with no engine: the
        client's line on stderr, as a ``cadgen`` verb says it, status 1, no traceback; a program
        that catches the error hears nothing."""
        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="unreached-")))
        self.addCleanup(shutil.rmtree, folder, True)
        engine = folder / "engine"
        engine.mkdir(mode=0o700)
        (folder / "peg.py").write_text(UNREACHED, encoding="utf-8")
        from cad.engine.client import SANDBOXES
        from cad.engine.client import SANDBOXED

        env = {**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(engine),
               "CAD_STATE_DIR": str(folder / "state"), "CAD_CACHE_DIR": str(folder / "cache"),
               **dict(SANDBOXES)}
        for command in ([sys.executable, "peg.py"], [sys.executable, "-m", "cad_server.cli", "run", "peg.py"]):
            done = engine_daemon.run(command, cwd=folder, env=env)
            self.assertEqual((done.returncode, done.stdout, done.stderr), (1, "", f"cad: {SANDBOXED}\n"), command)
        caught = engine_daemon.run([sys.executable, "peg.py", "catch"], cwd=folder, env=env)
        self.assertEqual((caught.returncode, caught.stdout, caught.stderr), (0, "caught\n", ""))
        self.assertEqual(sorted(path.name for path in engine.iterdir()), [], "no engine started")


if __name__ == "__main__":
    unittest.main()
