"""A model's tree is the geometry of the STEP it wrote — not the shape it returned.

``read_step`` on a cadgen-built ``.step`` used to answer from the store tree,
whose components were BinTools serializations of the shapes the script
RETURNED, while ``build123d.import_step`` (and a cold ``read_step``, with no
tree for the bytes) parsed the file. OCCT's STEP translation is not lossless:
a ``Sphere(1)`` rotated so its poles lie in the cut plane, scaled
anisotropically and trimmed keeps its upper cap in memory (42.3 mm³) and
reloads from STEP as the complementary lower cap (0.35 mm³). So the same
call on the same file gave different solids depending on cache state, and a
point inside the tree's solid was outside the file's (PR #370 bug records 028-030).

The build now writes the STEP, re-reads it, and publishes THOSE prototypes
(``cadgen.store.build.build_tree_through_step``). This suite pins the
consequence from the outside: warm ``read_step`` == cold ``read_step`` ==
``import_step`` on the written bytes, for the lossy solid above, for an
assembly whose members are compounds and links, and for a composed vendor part
whose face colours must survive the round trip.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

CADGEN_SRC = add_repo_path("packages/cadgen/src")

_ROT_CAP = '''from cadgen import build123d as bd, step


@step
def rot_cap():
    sphere = bd.Rot(90, 0, 0) * bd.Rot(0, 0, -90) * bd.Sphere(1)
    ellipsoid = sphere.transform_geometry(
        bd.Matrix([[2.7, 0, 0, 0], [0, 2.7, 0, 0], [0, 0, 1.4, 0], [0, 0, 0, 1]]))
    pad = bd.Pos(0, 0, 5.4) * ellipsoid
    return pad - (bd.Pos(0, 0, 4.15 - 10) * bd.Box(30, 30, 20))


if __name__ == "__main__":
    rot_cap()
'''

_PIN = '''from cadgen import build123d as bd, step


@step
def pin():
    return bd.Cylinder(1, 6)


if __name__ == "__main__":
    pin()
'''

# A compound member (two solids in ONE occurrence), a plain member, and two
# links to the pin model: every shape of node the re-read must map back.
_ASSEMBLY = '''from pathlib import Path

from cadgen import build123d as bd, read_step, step

from pin import pin

HERE = Path(__file__).resolve().parent


@step
def rig():
    pair = bd.Compound([bd.Box(2, 2, 2), bd.Pos(4, 0, 0) * bd.Box(2, 2, 2)])
    pair.label = "pair"
    bar = bd.Pos(0, 6, 0) * bd.Box(10, 1, 1)
    bar.label = "bar"
    bar.color = bd.Color(0.2, 0.4, 0.8)
    vendor = read_step(HERE / "vendor.step")
    vendor.label = "vendor"
    left = pin().moved(bd.Pos(-8, 0, 0))
    left.label = "pin_left"
    right = pin().moved(bd.Pos(8, 0, 0) * bd.Rot(0, 90, 0))
    right.label = "pin_right"
    return bd.Compound(children=[pair, bar, vendor.moved(bd.Pos(0, 0, 8)), left, right], label="rig")


if __name__ == "__main__":
    rig()
'''


def _volumes(shape) -> list[float]:
    return sorted(round(solid.volume, 6) for solid in shape.solids())


class TreeReflectsWrittenStep(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tree-through-step-")
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name).resolve()
        self.store = self.project / "store"
        self.environment = dict(os.environ)
        self.environment.update(
            {
                "CADGEN_DAEMON": "0",
                "CADGEN_COMPONENT_WORKERS": "1",
                "CADGEN_CACHE_DIR": str(self.store),
                "PYTHONPATH": str(CADGEN_SRC),
            }
        )

    def _run(self, model: str) -> None:
        completed = subprocess.run(
            [sys.executable, str(self.project / model), "--force"],
            cwd=str(self.project),
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=600,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def _write(self, name: str, source: str) -> None:
        (self.project / name).write_text(source, encoding="utf-8")

    def _read_three_ways(self, step_path: Path):
        """(warm read_step, cold read_step, import_step) of one file."""
        import build123d as bd

        from cadgen import read_step
        from cadgen.catalog import result_tree_for

        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store)}):
            self.assertIsNotNone(result_tree_for(step_path), "the build published no tree for its STEP")
            warm = read_step(step_path)
        with tempfile.TemporaryDirectory(prefix="empty-store-") as empty:
            with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": empty}):
                self.assertIsNone(result_tree_for(step_path))
                cold = read_step(step_path)
        return warm, cold, bd.import_step(str(step_path))

    def test_a_lossy_solid_reads_the_same_warm_cold_and_through_build123d(self) -> None:
        self._write("rot_cap.py", _ROT_CAP)
        self._run("rot_cap.py")
        warm, cold, imported = self._read_three_ways(self.project / "rot_cap.step")

        self.assertEqual(_volumes(warm), _volumes(cold))
        self.assertEqual(_volumes(warm), _volumes(imported))
        # The document holds the LOWER cap (the OCCT round trip picks the
        # complementary trim); the in-memory upper cap was ~42.3 mm³. Should a
        # kernel upgrade fix the translation, the three still agree — that is
        # the invariant; the number just pins today's loss.
        self.assertLess(_volumes(warm)[0], 1.0)
        probe = (0.0, 0.0, 5.0)
        self.assertEqual(
            warm.solids()[0].is_inside(probe), imported.solids()[0].is_inside(probe)
        )

    def test_compound_members_links_and_face_colours_round_trip(self) -> None:
        import build123d as bd

        from cadgen.step_export import export_build123d_step_file

        vendor = bd.Box(3, 3, 3)
        vendor.label = "vendor_part"
        # Two coloured faces on a vendor part (per-face colours as coloured XCAF
        # sub-shapes, the way a vendor STEP carries them; build123d's own
        # exporter writes only per-shape colours).
        vendor.cad_face_ordinal_colors = {1: (1.0, 0.0, 0.0, 1.0), 6: (0.0, 1.0, 0.0, 1.0)}
        export_build123d_step_file(vendor, self.project / "vendor.step")
        self._write("pin.py", _PIN)
        self._write("rig.py", _ASSEMBLY)
        self._run("pin.py")
        self._run("rig.py")

        step_path = self.project / "rig.step"
        warm, cold, imported = self._read_three_ways(step_path)
        self.assertEqual(_volumes(warm), _volumes(cold))
        self.assertEqual(_volumes(warm), _volumes(imported))
        self.assertEqual(len(_volumes(warm)), 6)  # pair(2) + bar + vendor + 2 pins

        from cadgen.catalog import result_descriptor_for
        from cadgen.store.objects import object_path
        from cadgen._internal.surface_extract import read_surf

        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store)}):
            descriptor = result_descriptor_for(step_path)
            by_name = {occ["name"]: occ for occ in descriptor["occurrences"]}
            # Occurrence metadata is the build's.
            self.assertEqual(by_name["bar"]["color"][:3], [0.2, 0.4, 0.8])
            # The tree links the pin model rather than copying it.
            tree = json.loads(object_path(descriptor["tree"]).read_text(encoding="utf-8"))
            self.assertEqual({link["name"] for link in tree["links"]}, {"pin_left", "pin_right"})
            # The vendor part's face colours came back through the document.
            vendor_cid = by_name["vendor"]["component"]
            index, _ = read_surf(object_path(descriptor["components"][vendor_cid]["surf"]).read_bytes())
            coloured = {tuple(round(c, 3) for c in face["color"][:3]) for face in index["faces"] if face.get("color")}
            self.assertEqual(coloured, {(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)})


if __name__ == "__main__":
    unittest.main()
