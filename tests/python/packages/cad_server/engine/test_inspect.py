"""``cad xbf inspect DOC`` without a ref: what the document holds, on one screen, before its build
closure -- its state, parts, bounds, volume, materials, joints, states, sequences and declared
files -- read from the document the engine holds, and nothing built; ``--json`` the same as data;
``--query structure`` the same lists with nothing measured. Measuring is lazy: a build no inspection
has measured reads and measures nothing; the first summary measures, and each later build of the
inspected document has the part it changed measured once its worker settles, before anyone asks."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

HINGE = """
import pathlib
import build123d as bd
from cad import model
from bd_materials import metals
from cad.build123d import configuration_sequence, mechanism_state

pathlib.Path(__file__).with_suffix(".ran").write_text("ran", encoding="utf-8")


@model
def hinge():
    base = bd.Box(100, 60, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    arm = bd.Pos(40, 0, 20) * bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    base.label, arm.label = "base", "arm"
    base.material = metals.aluminum()
    elbow = bd.Axis((40, 0, 20), (0, -1, 0))
    bd.RevoluteJoint("elbow", base, axis=elbow, angular_range=(-10, 120))
    bd.RigidJoint("elbow", arm, bd.Plane(origin=elbow.position, z_dir=elbow.direction).location)
    base.joints["elbow"].connect_to(arm.joints["elbow"], angle=0)
    assembly = bd.Compound(children=[base, arm], label="hinge")
    mechanism_state(assembly, "open", elbow=90)
    return configuration_sequence(assembly, "cycle", [(0, "open"), (2.5, "open")])


if __name__ == "__main__":
    hinge()
"""


class SummaryTest(unittest.TestCase):
    """Through a real daemon, in an engine, a state and a cache folder of the test's own."""

    def setUp(self) -> None:
        self.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-inspect-")))
        self.addCleanup(shutil.rmtree, self.folder, True)
        engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, engine, True)
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(engine),
                                          "CAD_STATE_DIR": str(self.folder / "state"),
                                          "CAD_CACHE_DIR": str(self.folder / "cache"),
                                          "CAD_ENGINE_MESH": "inline"}, self.addCleanup)
        self.addCleanup(self.run_, "-m", "cad_server.engine", "stop")

    def run_(self, *args: str):
        return engine_daemon.run([sys.executable, *args], cwd=self.folder, env=self.env)

    def served(self) -> tuple[int, int]:
        """The bytes of the parts' facts the engine holds, and how many documents its server has
        loaded (``status --json``)."""
        status = self.run_("-m", "cad_server.engine", "status", "--json")
        self.assertEqual(status.returncode, 0, status.stderr)
        serving = json.loads(status.stdout)["serving"]
        return serving["memory"]["facts"], sum(row["state"] == "held" for row in serving["documents"])

    def facts(self) -> int:
        """The bytes of the parts' facts the engine holds (``status --json``)."""
        return self.served()[0]

    def test_a_hinge_with_one_joint_and_one_sequence_is_summarised_before_its_closure(self) -> None:
        (self.folder / "hinge.py").write_text(textwrap.dedent(HINGE), encoding="utf-8")
        built = self.run_("hinge.py")
        self.assertEqual(built.returncode, 0, built.stderr)
        ident = next(line.split()[1] for line in built.stdout.splitlines() if line.strip().startswith("id:"))
        (self.folder / "hinge.ran").unlink()

        # No inspection has measured it: its build loaded no document and measured nothing (the engine
        # decides so before the build answers).
        self.assertEqual(self.served(), (0, 0))

        # The structure: the summary's lists, nothing measured for them.
        listed = self.run_("-m", "cad_server.engine", "inspect", ident, "--query", "structure")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        lines = listed.stdout.splitlines()
        self.assertEqual(lines[2:7], ["parts       2 in hinge", "materials", "  Alu_G6061_T6: hinge/base",
                                      "  no material: hinge/arm", "joints"])
        self.assertIn("closure", lines)
        data = self.run_("-m", "cad_server.engine", "inspect", ident, "--query", "structure", "--json")
        self.assertEqual(data.returncode, 0, data.stderr)
        structure = json.loads(data.stdout)["summary"]
        self.assertFalse({"bounds", "volume", "mass"} & set(structure), structure)
        self.assertEqual(structure["materials"], [{"name": "Alu_G6061_T6", "density": 2700.0, "parts": ["hinge/base"]}])
        self.assertEqual(structure["states"], [{"name": "open", "values": {"elbow": 90.0}}])
        self.assertEqual(self.facts(), 0, "a structure measures nothing")

        shown = self.run_("-m", "cad_server.engine", "inspect", ident)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        lines = shown.stdout.splitlines()
        self.assertEqual(lines[0], f"hinge  {ident}")
        self.assertTrue(lines[1].startswith("state       live, "), lines[1])
        self.assertEqual(lines[2:18], [
            "parts       2 in hinge",
            "bounds      210 x 60 x 30 mm, from (-50, -30, 0)",
            "volume      144,000 mm^3",
            "materials   0.324 kg in all",
            "  Alu_G6061_T6: 0.324 kg, hinge/base",
            "  no material: hinge/arm",
            "joints",
            "  elbow  revolute  -10 to 120 deg, as built 0",
            "couplings   none",
            "states",
            "  open  elbow 90",
            "sequences",
            "  cycle  2.5 s",
            "animations  none",
            "declared files none",
            "closure",
        ])
        self.assertEqual(json.loads("\n".join(lines[18:]))["source"]["function"], "hinge")

        data = self.run_("-m", "cad_server.engine", "inspect", ident, "--json")
        self.assertEqual(data.returncode, 0, data.stderr)
        found = json.loads(data.stdout)
        summary = found["summary"]
        self.assertEqual(found["closure"]["source"]["function"], "hinge")
        self.assertEqual(summary["joints"], [{"name": "elbow", "type": "revolute", "range": [[-10.0, 120.0]],
                                              "units": ["deg"], "asBuilt": 0.0}])
        self.assertEqual((summary["states"], summary["sequences"]),
                         ([{"name": "open", "values": {"elbow": 90.0}}], [{"name": "cycle", "duration": 2.5}]))
        self.assertEqual((summary["parts"], summary["volume"], summary["mass"]),
                         ({"occurrences": 2, "distinct": 2, "root": "hinge"}, 144000.0, 0.324))
        # How far the measurement is, as the engine tells it through its door: counted to every part.
        probe = ("import json, sys\nfrom cad.engine import api\nframes = []\n"
                 "api.inspect(sys.argv[1], query='summary', progress=frames.append)\nprint(json.dumps(frames))\n")
        measuring = self.run_("-c", probe, ident)
        self.assertEqual(measuring.returncode, 0, measuring.stderr)
        frames = [frame for frame in json.loads(measuring.stdout) if frame["kind"] == "inspect-measure"]
        self.assertEqual([(frame["done"], frame["total"]) for frame in (frames[0], frames[-1])], [(0, 2), (2, 2)])
        self.assertIn(frames[-1]["detail"], ("base", "arm"))
        self.assertFalse((self.folder / "hinge.ran").exists(), "nothing ran the script")

        # Inspected now, the hinge's next build has the part it changed measured once its worker
        # settles, before anyone asks: the longer arm's facts are in before the next inspection.
        measured = self.facts()
        self.assertGreater(measured, 0)
        (self.folder / "hinge.py").write_text(textwrap.dedent(HINGE).replace("bd.Box(120, 20, 10", "bd.Box(130, 20, 10"),
                                              encoding="utf-8")
        built = self.run_("hinge.py")
        self.assertEqual(built.returncode, 0, built.stderr)
        deadline = time.monotonic() + 120
        while self.facts() <= measured:
            self.assertLess(time.monotonic(), deadline, "the build's parts were measured with nobody asking")
        again = json.loads(self.run_("-m", "cad_server.engine", "inspect", ident, "--json").stdout)["summary"]
        self.assertEqual(again["volume"], 146000.0, "the longer arm")


class CouplingsTest(unittest.TestCase):
    """A gear pair, a rack and pinion and a screw, as ``inspect`` lists them beside the joints."""

    KINEMATICS = {
        "pairs": [{"label": "ja", "type": "revolute"}, {"label": "jb", "type": "revolute"},
                  {"label": "slide", "type": "prismatic"}, {"label": "lead", "type": "cylindrical"}],
        "couplings": {"drive": {"range": [-90.0, 90.0], "terms": [["ja", 0, 1.0], ["jb", 0, -2.0]]},
                      "rack": {"range": [None, None], "terms": [["ja", 0, 1.0], ["slide", 0, 0.5]]},
                      "screw": {"range": [None, None], "terms": [["lead", 0, 1.0], ["lead", 1, 0.004]]}}}

    def test_a_material_s_parts_past_a_few_are_counted_in_text_and_every_one_named_in_data(self) -> None:
        from cad_server.engine.cli import summary_text

        screws = [f"arm/screw{at}" for at in range(120)]
        summary = {"name": "arm", "id": "x", "state": {"state": "file", "path": "/m/a.xbf"},
                   "parts": {"occurrences": 124, "distinct": 2, "root": "arm"}, "bounds": None, "volume": 0.0,
                   "materials": [{"name": "Steel", "density": 7850.0, "mass": 0.5, "parts": screws},
                                 {"name": "PLA", "density": 1240.0, "mass": 0.1, "parts": ["arm/a", "arm/b"]}],
                   "unweighed": ["arm/c", "arm/d", "arm/e", "arm/f", "arm/g"], "mass": 0.6, "joints": [],
                   "couplings": [], "states": [], "sequences": [], "animations": [], "files": []}
        lines = summary_text(summary).splitlines()
        at = lines.index("materials   0.6 kg in all")
        self.assertEqual(lines[at + 1:at + 4], ["  Steel: 0.5 kg, 120 parts: arm/screw0, arm/screw1, arm/screw2 and 117 more",
                                                "  PLA: 0.1 kg, arm/a, arm/b",
                                                "  no material: 5 parts: arm/c, arm/d, arm/e and 2 more"])

    def test_each_coupling_is_its_name_kind_joints_and_ratio_in_data_and_text(self) -> None:
        from cad.engine.api import couplings_of
        from cad_server.engine.cli import summary_text

        found = couplings_of(self.KINEMATICS)
        self.assertEqual(found[0], {"name": "drive", "kind": "gear_pair", "range": [-90.0, 90.0], "ratio": -2.0,
                                    "joints": [{"name": "ja", "ratio": 1.0}, {"name": "jb", "ratio": -2.0}]})
        self.assertEqual([(row["kind"], row["ratio"]) for row in found[1:]],
                         [("rack_and_pinion_pair", 0.5), ("screw_pair", None)])
        summary = {"name": "train", "id": "x", "state": {"state": "file", "path": "/m/a.xbf"},
                   "parts": {"occurrences": 1, "distinct": 1, "root": "train"}, "bounds": None, "volume": 0.0,
                   "materials": [], "unweighed": [], "joints": [], "couplings": found,
                   "states": [], "sequences": [], "animations": [], "files": []}
        lines = summary_text(summary).splitlines()
        at = lines.index("couplings")
        self.assertEqual(lines[at + 1:at + 4], ["  drive  gear_pair  ja 1, jb -2, ratio -2",
                                                "  rack  rack_and_pinion_pair  ja 1, slide 0.5, ratio 0.5",
                                                "  screw  screw_pair  lead 1 0.004"])


class SummaryTextTest(unittest.TestCase):
    def test_a_named_native_material_without_density_is_listed_as_unweighed(self) -> None:
        from bd_materials import FinishedMaterial
        from bd_materials.core import RangeMaterial
        from threejs_materials import PbrProperties

        from cad.engine import document
        from cad.engine.api import _summary
        from cad_server.engine.cli import summary_text

        material = FinishedMaterial(RangeMaterial(name="Imported paint", density=None),
                                    pbr=PbrProperties.create("Paint", color="#ff0000"))
        structure = {"name": "part", "prototypes": [{"key": "k", "material": document.material_json(material)}],
                     "instances": [{"prototype": 0, "path": "part"}], "tree": {"name": "part"}}
        for measured in (False, True):
            with self.subTest(measured=measured):
                summary = _summary(structure, Path("part.xbf"), lambda *_: {"k": {"volume": 1000}},
                                   "id", measured=measured)
                self.assertEqual(summary["unweighed"], ["part"])
                row = {"name": "Imported paint", "density": None, "parts": ["part"]}
                if measured:
                    row["mass"] = None
                    self.assertIsNone(summary["mass"])
                    self.assertIn("Imported paint: no density, part", summary_text(summary))
                self.assertNotIn("no material:", summary_text(summary))
                self.assertEqual(summary["materials"], [row])
                self.assertEqual(summary["untextured"], [])

    def test_a_part_whose_texture_maps_are_not_drawn_is_listed(self) -> None:
        from cad.engine.api import _summary
        from cad_server.engine.cli import summary_text

        structure = {"name": "box", "prototypes": [{"key": "k", "name": "lid",
                                                    "untextured": {"Hardwood_ASH": ["color", "normal"]}}],
                     "instances": [{"prototype": 0, "path": "box/lid"}], "tree": {"name": "box"}}
        summary = _summary(structure, Path("box.xbf"), lambda *_: {}, "id", measured=False)
        self.assertEqual(summary["untextured"], [{"part": "lid", "materials": {"Hardwood_ASH": ["color", "normal"]}}])
        lines = summary_text(summary).splitlines()
        at = lines.index("textures    not drawn yet: these parts wear their material's scalar look")
        self.assertEqual(lines[at + 1], "  lid: Hardwood_ASH's color and normal maps")

    def test_a_part_inside_out_is_named(self) -> None:
        # A solid whose faces point inward (a build123d boolean can make one) has a negative volume; the
        # kernel measures it as its size, and the summary names the part that is inside out.
        import build123d as bd

        from cad.engine.api import _summary
        from cad.engine.mesh import measured, shape_bytes
        from cad_server.engine.cli import summary_text

        facts = {"right": measured(shape_bytes(bd.Box(10, 10, 10).wrapped)),
                 "inside out": measured(shape_bytes(bd.Box(10, 10, 10).wrapped.Reversed()))}
        self.assertEqual([(round(row["volume"]), row["inverted"]) for row in facts.values()], [(1000, 0), (1000, 1)])
        structure = {"name": "knob", "prototypes": [{"key": "right"}, {"key": "inside out"}],
                     "instances": [{"prototype": 0, "path": "knob/body", "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]},
                                   {"prototype": 1, "path": "knob/cap", "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 20, 0, 0, 1]}],
                     "tree": {"name": "knob"}}
        summary = _summary(structure, Path("knob.xbf"), lambda *_: facts, "id")
        self.assertEqual(summary["inverted"], ["knob/cap"])
        self.assertIn("inside out  knob/cap: a solid whose faces point inward", summary_text(summary).splitlines())

    def test_names_a_file_carries_are_printed_without_their_control_characters(self) -> None:
        # A third-party STEP's product names reach the terminal: OCCT keeps an ESC in them.
        from cad_server.engine.cli import summary_text

        evil = "asm\x1b[2J\x1b]52;c;cHduZWQ=\x07\x9b"
        summary = {"name": evil, "id": "x", "state": {"state": "file", "path": "/m/a.step"},
                   "parts": {"occurrences": 1, "distinct": 1, "root": evil}, "bounds": None, "volume": 0.0,
                   "materials": [{"name": evil, "mass": None, "parts": [evil]}], "unweighed": [evil],
                   "joints": [{"name": evil, "type": "revolute", "range": [], "units": [], "asBuilt": None}],
                   "states": [], "sequences": [], "animations": [], "files": [evil]}
        text = summary_text(summary)
        self.assertFalse([character for character in text if ord(character) < 0x20 and character != "\n"
                          or 0x7f <= ord(character) < 0xa0], text)
        self.assertIn("asm\\x1b[2J", text, "each shown as its escape")

    def test_joint_values_read_as_the_viewer_shows_them_and_round_off_as_zero(self) -> None:
        # A joint placed through a turned sub-assembly measures -2.1e-31 as built: the kernel's zero.
        from cad_server.engine.cli import summary_text

        joints = [{"name": "roll", "type": "revolute", "range": [[-90.0, 90.0]], "units": ["deg"], "asBuilt": -2.148e-31},
                  {"name": "pitch", "type": "revolute", "range": [[-90.0, 90.0]], "units": ["deg"], "asBuilt": 29.99999999},
                  {"name": "lead", "type": "cylindrical", "range": [[], []], "units": ["deg", "mm"],
                   "asBuilt": [1e-30, 12.345]}]
        summary = {"name": "arm", "id": "x", "state": {"state": "file", "path": "/m/a.xbf"},
                   "parts": {"occurrences": 1, "distinct": 1, "root": "arm"}, "bounds": None, "volume": 0.0,
                   "materials": [], "unweighed": [], "joints": joints,
                   "states": [{"name": "rest", "values": {"roll": 3e-17, "pitch": 0.5, "lead": [180.25, 0.0]}}],
                   "sequences": [], "animations": [], "files": []}
        lines = summary_text(summary).splitlines()
        self.assertEqual(lines[lines.index("joints") + 1:lines.index("joints") + 4],
                         ["  roll  revolute  -90 to 90 deg, as built 0", "  pitch  revolute  -90 to 90 deg, as built 30",
                          "  lead  cylindrical  free; free, as built 0 12.3"])
        self.assertEqual(lines[lines.index("states") + 1], "  rest  roll 0, pitch 0.5, lead 180 0")


# A base bolted to an arm assembly declared to weigh 120 g, its servo case (no material) carrying a 30 g motor, and
# a 10 g lump on the base: the description weighs the arm 120 g in all, the base its aluminium plus 10 g.
WEIGHED = """
import build123d as bd
from bd_materials import metals
from cad.build123d import mass, point_mass
from cad.engine import xbf


@xbf("XBF/robot.xbf")
def robot():
    base = bd.Box(100, 60, 20, align=bd.Align.MIN)
    base.label, base.material = "base", metals.aluminum()
    link = bd.Pos(0, 0, 20) * bd.Box(100, 10, 10, align=bd.Align.MIN)
    link.label, link.material = "link", metals.aluminum()
    servo = bd.Pos(0, 20, 20) * bd.Box(40, 20, 30, align=bd.Align.MIN)
    servo.label = "servo"
    point_mass(servo, 30, bd.Pos(20, 30, 35), name="motor")
    point_mass(base, 10, bd.Pos(50, 30, 10), name="lump")
    arm = bd.Compound(children=[link, servo], label="arm")
    mass(arm, {grams})
    return bd.Compound(children=[base, arm], label="robot")
"""


class DeclaredMassTest(unittest.TestCase):
    """``inspect``'s masses where the model declares them (``mass``, ``point_mass``): as the robot description
    weighs them, not volume times density, and said which are declared and which computed."""

    def setUp(self) -> None:
        self.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-inspect-mass-")))
        self.addCleanup(shutil.rmtree, self.folder, True)
        from unittest import mock

        cache = mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(self.folder / "cache")})
        cache.start()
        self.addCleanup(cache.stop)

    def summarised(self, grams: float) -> tuple[dict, dict, dict, Path]:
        from cad.engine import build as engine_build
        from cad.engine import document
        from cad.engine.api import _summary

        script = self.folder / "robot.py"
        script.write_text(textwrap.dedent(WEIGHED.format(grams=grams)), encoding="utf-8")
        os.utime(script, ns=(time.time_ns(), time.time_ns()))
        report = engine_build.build(script, ["robot"], cwd=self.folder)[0]
        self.assertTrue(report["ok"], report)
        path = self.folder / "XBF/robot.xbf"
        structure = document.Loaded(path).structure()
        sizes = {"base": 100 * 60 * 20, "link": 100 * 10 * 10, "servo": 40 * 20 * 30}
        volumes = {prototype["key"]: float(sizes[prototype["name"]]) for prototype in structure["prototypes"]}
        summary = _summary(structure, path, lambda *_: {key: {"volume": volume} for key, volume in volumes.items()},
                           "id")
        return summary, structure, volumes, path

    def test_a_declared_mass_and_point_masses_weigh_as_the_robot_description_weighs_them(self) -> None:
        from cad.engine.describe import describe
        from cad.engine.export import Source
        from cad_server.engine.cli import summary_text

        summary, structure, volumes, path = self.summarised(120)
        density = next(prototype["material"]["material"]["density"] for prototype in structure["prototypes"]
                       if prototype["name"] == "base")
        base = 100 * 60 * 20 * 1e-9 * density
        described = describe(Source.read(path).view())
        self.assertAlmostEqual(sum(link.inertial.mass for link in described.links if link.inertial is not None),
                               base + 0.010 + 0.120, places=9, msg="the description's total")
        self.assertAlmostEqual(summary["mass"], base + 0.010 + 0.120, places=9, msg="inspect's agrees with it")
        declared = summary["declared"]
        self.assertAlmostEqual(declared["declared"], 0.130, places=9)
        self.assertAlmostEqual(declared["computed"], base, places=9)
        self.assertEqual(declared["masses"], [{"name": "arm", "path": "robot/arm", "grams": 120.0}])
        self.assertEqual(declared["pointMasses"], [{"part": "robot/base", "name": "lump", "grams": 10.0},
                                                   {"part": "robot/arm/servo", "name": "motor", "grams": 30.0}])
        self.assertEqual(declared["scaled"], ["robot/arm/link", "robot/arm/servo"])
        self.assertEqual(summary["unweighed"], [], "the servo's solid weighs nothing, and it carries its motor")
        # The arm's solids weigh the 90 g its motor leaves: the servo has no density of its own while its sibling
        # has one, so its solid carries none, and the link carries the 90 g.
        aluminium = next(row for row in summary["materials"] if row["parts"] == ["robot/base", "robot/arm/link"])
        self.assertAlmostEqual(aluminium["mass"], base + 0.090, places=9)
        lines = summary_text(summary).splitlines()
        self.assertIn(f"declared    0.13 kg of {_number(summary['mass'])} kg in all; {_number(base)} kg computed at "
                      "the materials' densities", lines)
        self.assertIn("  mass robot/arm: 120 g", lines)
        self.assertIn("  point mass motor on robot/arm/servo: 30 g", lines)
        self.assertIn("  scaled to a declared mass: robot/arm/link, robot/arm/servo", lines)
        # A ref weighs its own parts the same way, every part measured for the scale.
        from cad.engine import refs
        from cad.engine.said import weighed

        arm = weighed(structure, refs.resolve_structure(structure, "arm", path)[0], volumes)
        self.assertAlmostEqual(arm["mass"], 0.120, places=9)
        self.assertEqual(arm["declared"]["masses"], [{"name": "arm", "path": "robot/arm", "grams": 120.0}])
        self.assertEqual(arm["declared"]["pointMasses"], [{"part": "robot/arm/servo", "name": "motor", "grams": 30.0}])

    def test_a_mass_the_description_refuses_is_refused_in_its_words_and_weighs_nothing(self) -> None:
        from cad_server.engine.cli import summary_text

        summary, _structure, _volumes, _path = self.summarised(20)
        self.assertIsNone(summary["mass"])
        self.assertEqual(summary["declared"]["refused"], "'arm', declared to weigh 20 g, holds point masses and inner "
                                                         "masses of 30 g, which leave its own solids nothing to weigh")
        self.assertTrue(all(row["mass"] is None for row in summary["materials"]))
        self.assertIn("declared    refused: 'arm', declared to weigh 20 g, holds point masses and inner masses of 30 g, "
                      "which leave its own solids nothing to weigh", summary_text(summary).splitlines())


def _number(value: float) -> str:
    from cad.engine.said import number

    return number(value)


if __name__ == "__main__":
    unittest.main()
