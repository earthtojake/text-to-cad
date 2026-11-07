"""OpenSCAD programs rendered by the real OpenSCAD (``scripts/test/test-openscad.sh``, the job that installs it).

The openscad integration runs the person's OpenSCAD headless, in a private folder, with their libraries
reachable: a program with a hole and an include in a folder with a space in its name renders to the mesh
OpenSCAD makes of it; ``cad scad inspect`` says what it renders to, ``cad scad export`` writes its STL, 3MF and
GLB, ``cad scad dfm`` measures it, ``cad scad snapshot`` draws it (the engine's OCCT still, on the display
the runner gives it); the engine keeps the mesh by the program's bytes and its includes', and renders again
when a library file alone changes; a library in the person's own library folder resolves; a 2D program and a
syntax error are refused in OpenSCAD's words.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad import scad
from cad.openscad import _program, _render
from cad_server._internal import scads
from cad_server.cli.document_types import type_main

PROGRAM = """include <lib dir/lib.scad>
use <helper.scad>
difference() {{ cube([20, 20, 6], center=true); cylinder(h=10, r=3, center=true, $fn=32); }}
translate([0, 0, 3]) post({height});
echo(version=version());
"""


def _run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = type_main("scad", list(argv))
        except SystemExit as exited:
            code = exited.code
    return code, out.getvalue(), err.getvalue()


class RealRenders(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("openscad") is None and not os.environ.get("CAD_OPENSCAD"):
            raise AssertionError("the openscad suite needs OpenSCAD installed (scripts/test/test-openscad.sh)")
        cls.version = _program.ready()[1]

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tmp-openscad-real-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        (self.root / "lib dir").mkdir()
        self.lib = self.root / "lib dir" / "lib.scad"
        self.lib.write_text("module post(h) { cylinder(h=h, r=2, $fn=24); }\n", encoding="utf-8")
        (self.root / "helper.scad").write_text("module helper() {}\n", encoding="utf-8")
        self.program = self.root / "part.scad"
        self.program.write_text(PROGRAM.format(height=4), encoding="utf-8")
        cache = mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(self.root / "cache")})
        cache.start()
        self.addCleanup(cache.stop)

    def test_a_program_with_a_hole_and_an_include_renders_to_openscads_mesh(self) -> None:
        found = _render.render(self.program, self.root / "out" / "part.stl")
        self.assertEqual(found.version, self.version)
        self.assertEqual(found.includes, (self.root / "helper.scad", self.lib))
        self.assertIn("ECHO: version =", found.said)
        mesh = scad.read(self.program)
        self.assertEqual(tuple(round(value, 3) for value in mesh.bounding_box().size), (20.0, 20.0, 10.0))
        self.assertGreater(len(mesh.triangles), 100, "the hole and the post are faceted")
        code, out, _ = _run("inspect", str(self.program), "--json")
        said = json.loads(out)
        self.assertEqual((code, said["openscad"], said["bounds"]["size"]), (0, self.version, [20.0, 20.0, 10.0]))
        self.assertEqual(said["includes"], [str(self.root / "helper.scad"), str(self.lib)])

    def test_the_commands_write_measure_and_draw_the_mesh(self) -> None:
        out = self.root / "out"
        code, said, err = _run("export", str(self.program), str(out / "part.stl"), str(out / "part.3mf"),
                               str(out / "part.glb"), "--json")
        self.assertEqual(code, 0, said + err)
        self.assertEqual([row["kind"] for row in json.loads(said)["files"]], ["stl", "threemf", "glb"])
        for name in ("part.stl", "part.3mf", "part.glb"):
            self.assertGreater((out / name).stat().st_size, 200, name)
        code, said, _ = _run("dfm", str(self.program), "--process", "printing", "--json")
        payload = json.loads(said)
        self.assertEqual((code, payload["ok"]), (0, True), said)
        # The slab less its hole, plus the post: 20*20*6 - pi*9*6 + pi*4*4, near enough for 32- and 24-gons.
        self.assertAlmostEqual(payload["measurements"]["mesh"]["volume_mm3"], 2400 - 169.6 + 50.3, delta=12)
        code, said, err = _run("snapshot", str(self.program), str(out / "part.png"), "--camera", "top", "--json")
        self.assertEqual(code, 0, said + err)
        self.assertEqual(json.loads(said)["output"], str(out / "part.png"))
        self.assertEqual((out / "part.png").read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_the_engine_keeps_the_mesh_by_the_program_and_renders_again_for_a_library_edit(self) -> None:
        mesh, key = scads.rendered(self.program, self.version)
        self.assertEqual(mesh, scads.folder(self.program) / key / scads.MESH)
        self.assertEqual(scads.includes(self.program), [self.root / "helper.scad", self.lib])
        stamp = mesh.stat().st_mtime_ns
        self.assertEqual(scads.rendered(self.program, self.version), (mesh, key))
        self.assertEqual(mesh.stat().st_mtime_ns, stamp, "the same bytes: not rendered again")
        self.lib.write_text("module post(h) { cylinder(h=h, r=4, $fn=24); }\n", encoding="utf-8")
        other, changed = scads.rendered(self.program, self.version)
        self.assertNotEqual(changed, key, "the library alone changed")
        self.assertNotEqual(other, mesh)
        self.assertNotEqual(other.read_bytes(), mesh.read_bytes(), "a wider post: other triangles")
        self.assertEqual(_box(other), _box(mesh), "the slab's bounds hold the post")

    def test_a_library_in_the_persons_own_folder_resolves(self) -> None:
        home = self.root / "home"
        library = home / ".local" / "share" / "OpenSCAD" / "libraries" / "mine"
        library.mkdir(parents=True)
        (library / "shapes.scad").write_text("module brick() { cube([10, 5, 2]); }\n", encoding="utf-8")
        program = self.root / "uses.scad"
        program.write_text("include <mine/shapes.scad>\nbrick();\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}), \
                mock.patch.object(_program.sys, "platform", "linux"), \
                mock.patch.object(os.path, "expanduser", lambda path, h=str(home): path.replace("~", h, 1)):
            os.environ.pop("XDG_DATA_HOME", None)
            os.environ.pop("OPENSCADPATH", None)
            found = _render.render(program, self.root / "out" / "uses.stl")
        self.assertEqual(found.includes, (library / "shapes.scad",))
        self.assertEqual(tuple(round(value, 3) for value in _box(found.mesh)), (10.0, 5.0, 2.0))

    def test_what_openscad_refuses_is_said_in_its_words(self) -> None:
        flat = self.root / "flat.scad"
        flat.write_text("square(10);\n", encoding="utf-8")
        with self.assertRaisesRegex(_render.TwoDimensional, r"flat\.scad is a 2D program"):
            _render.render(flat, self.root / "flat.stl")
        bad = self.root / "bad.scad"
        bad.write_text("cube(\n", encoding="utf-8")
        with self.assertRaisesRegex(_render.RenderError, r"could not render bad\.scad \(exit 1\): ERROR: Parser error"):
            _render.render(bad, self.root / "bad.stl")
        self.assertFalse((self.root / "bad.stl").exists(), "nothing written")
        code, out, err = _run("inspect", str(flat))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("flat.scad is a 2D program", err)


def _box(stl: Path) -> tuple[float, float, float]:
    from cad.engine.formats.stl import read_stl

    points = read_stl(stl).reshape(-1, 3)
    return tuple((points.max(axis=0) - points.min(axis=0)).tolist())


if __name__ == "__main__":
    unittest.main()
