"""A part declared ``collision(part, "decomposed")`` (``describe``, ``hulls``, ``cad.coacd``): the declaration and its options
round-tripped through the document, its xbf and a shape rebuilt from it, an assembly's handed to its parts; the
writers' output with a decomposer the test stands in for -- an MJCF geom of a mesh asset per hull, a URDF
collision per hull, the visual whole, and the contact rule testing the hulls, not the part's one hull; the hulls
kept in the engine's cache by the mesh and the options, so a second description decomposes nothing, the first
saying so as it starts, and each part as it is done, at its cap said so; the refusals,
of an option on another kind and of options out of range; at most 16 hulls by default; a miss where coacd is not
installed decomposed in the coacd integration's environment, which the engine makes on first need (a stand-in
here), and refused, saying why, where none can hold it (no wheel, no engine, a making that failed); and,
where coacd is installed (the development environment's extra), CoACD's own hulls of an L-shaped part, two or
more, which MuJoCo compiles."""

from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import numpy as np

from cad.engine import build as engine_build
from cad.engine import document
from cad.engine.describe import describe
from cad.engine.description import DescriptionError
from cad.engine.export import Source
from cad.engine.export import mjcf, urdf

# An L-shaped bracket (two 40 x 10 x 10 mm arms meeting at the origin) turning about Z on a block that sits in its
# inner corner, 5 mm clear of both arms: the bracket's one hull covers the block, its two arms do not.
BRACKET = """
import build123d as bd
from cad.build123d import collision
from cad.engine import xbf


@xbf("XBF/bracket.xbf")
def bracket():
    block = bd.Pos(25, 25, 5) * bd.Box(20, 20, 10)
    block.label = "block"
    arm = bd.Box(40, 10, 10, align=bd.Align.MIN) + bd.Box(10, 40, 10, align=bd.Align.MIN)
    arm.label = "bracket"
    {declare}
    turn = bd.RevoluteJoint("turn", block, axis=bd.Axis((0, 0, 0), (0, 0, 1)), angular_range=(-90, 90))
    bd.RigidJoint("turn", arm, turn.location)
    turn.connect_to(arm.joints["turn"], angle=0)
    return {root}
"""
ROOT = 'bd.Compound(children=[block, arm], label="bracket")'


# The bracket's two arms, in metres: what a decomposition of it should give, and what the stand-in gives.
ARMS = ((0.0, 0.0, 0.0, 0.04, 0.01, 0.01), (0.0, 0.0, 0.0, 0.01, 0.04, 0.01))


def _box(low_x: float, low_y: float, low_z: float, high_x: float, high_y: float, high_z: float) -> tuple[Any, Any]:
    corners = np.array([[x, y, z] for x in (low_x, high_x) for y in (low_y, high_y) for z in (low_z, high_z)],
                       dtype=np.float32)
    faces = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                      [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]], dtype=np.uint32)
    return corners, faces


# Two cups of one geometry, each cut into its own number of hulls.
CUPS = """
import build123d as bd
from cad.build123d import collision
from cad.engine import xbf


def cup():
    return bd.Box(40, 40, 20) - bd.Pos(0, 0, 5) * bd.Box(30, 30, 20)


@xbf("XBF/cups.xbf")
def cups():
    a = cup()
    a.label = "a"
    b = bd.Pos(100, 0, 0) * cup()
    b.label = "b"
    collision(a, "decomposed", max_hulls={first})
    collision(b, "decomposed", max_hulls={second})
    return bd.Compound(children=[a, b], label="cups")
"""


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-decomposition-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        cache = mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(self.folder / "cache")})
        cache.start()
        self.addCleanup(cache.stop)
        self.calls: list[list[dict[str, Any]]] = []

    def build(self, declare: str, root: str = ROOT) -> Path:
        script = self.folder / "bracket.py"
        script.write_text(textwrap.dedent(BRACKET.format(declare=declare, root=root)), encoding="utf-8")
        os.utime(script, ns=(time.time_ns(), time.time_ns()))
        report = engine_build.build(script, ["bracket"], cwd=self.folder)[0]
        self.assertTrue(report["ok"], report)
        return self.folder / "XBF/bracket.xbf"

    def stand_in(self, meshes: Any, _done: Any = None) -> list[list[tuple[Any, Any]]]:
        """The decomposer's child, stood in for: each mesh as the bracket's two arms."""
        self.calls.append([dict(options) for _positions, _triangles, options in meshes])
        return [[_box(*arm) for arm in ARMS] for _mesh in meshes]

    def described(self, xbf: Path) -> Any:
        with mock.patch("cad.engine.hulls._decompose", self.stand_in):
            return describe(Source.read(xbf).view())


class DeclarationTest(_Folder):
    def test_the_declaration_and_its_options_round_trip_through_the_document_and_its_xbf(self) -> None:
        path = self.build('collision(arm, "decomposed", max_hulls=4, threshold=0.1)')
        loaded = document.Loaded(path).structure()
        self.assertEqual(loaded["prototypes"], document.tree_structure(document.saved(path), path)["prototypes"])
        by_name = {prototype["name"]: prototype for prototype in loaded["prototypes"]}
        self.assertEqual((by_name["bracket"]["collision"], by_name["bracket"]["decomposition"]),
                         ("decomposed", {"maxHulls": 4, "threshold": 0.1}))
        self.assertNotIn("decomposition", by_name["block"])
        rebuilt = Source.read(path).shape()
        parts = {child.label: child for child in rebuilt.children}
        self.assertEqual((parts["bracket"].__dict__["_collision"], parts["bracket"].__dict__["_decomposition"]),
                         ("decomposed", {"maxHulls": 4, "threshold": 0.1}))
        # Declared on the assembly, the kind and its options are every part's that declares none; the options
        # are the stand-in's input as the declaration gave them.
        self.build("pass", root=f'collision({ROOT}, "decomposed", max_hulls=3)')
        prototypes = document.Loaded(path).structure()["prototypes"]
        self.assertEqual({(p["collision"], p["decomposition"]["maxHulls"]) for p in prototypes}, {("decomposed", 3)})
        self.described(path)
        self.assertEqual(self.calls, [[{"maxHulls": 3}, {"maxHulls": 3}]], "both parts, in one call")

    def test_an_option_on_another_kind_or_out_of_range_is_refused_by_name(self) -> None:
        import build123d as bd

        from cad.build123d import collision

        part = bd.Box(1, 1, 1)
        with self.assertRaisesRegex(ValueError, "collision 'box' takes no max_hulls: they bound a decomposed one"):
            collision(part, "box", max_hulls=2)
        with self.assertRaisesRegex(ValueError, "takes no max_hulls or threshold"):
            collision(part, "mesh", max_hulls=2, threshold=0.1)
        for wrong in (0, True, 2.5):
            with self.assertRaisesRegex(ValueError, "max_hulls is a whole number of hulls, at least 1"):
                collision(part, "decomposed", max_hulls=wrong)
        for wrong in (0.001, 2, "fine"):
            with self.assertRaisesRegex(ValueError, "threshold is CoACD's concavity threshold, 0.01 to 1"):
                collision(part, "decomposed", threshold=wrong)
        # A later declaration replaces the earlier one, its options with it: at most 16 hulls by default, None
        # for CoACD's no limit; another kind is given no default.
        collision(part, "decomposed", max_hulls=2)
        collision(part, "decomposed")
        self.assertEqual(part.__dict__["_decomposition"], {"maxHulls": 16})
        collision(part, "decomposed", max_hulls=None)
        self.assertNotIn("_decomposition", part.__dict__)
        collision(part, "box")
        self.assertNotIn("_decomposition", part.__dict__)


class WritersTest(_Folder):
    def test_each_hull_is_a_collision_geom_of_its_own_mesh_and_the_visual_stays_whole(self) -> None:
        path = self.build('collision(arm, "decomposed")')
        description = self.described(path)
        bracket = description.link("bracket")
        self.assertEqual([visual.name for visual in bracket.visuals], ["bracket"])
        self.assertEqual([(c.name, c.of, c.geometry.kind) for c in bracket.collisions],
                         [("bracket_hull0", "bracket", "mesh"), ("bracket_hull1", "bracket", "mesh")])
        self.assertEqual([description.meshes[str(c.geometry.mesh)].name for c in bracket.collisions],
                         ["bracket_hull0", "bracket_hull1"])
        # The MJCF: the visual's one mesh, a mesh asset and a collision geom per hull.
        text, files = mjcf.rendered(description)
        self.assertIn('<mesh name="bracket_hull0" file="bracket_bracket_hull0.stl"/>', text)
        self.assertIn('<mesh name="bracket_hull1" file="bracket_bracket_hull1.stl"/>', text)
        self.assertIn('<geom class="collision" type="mesh" mesh="bracket_hull0" name="bracket_hull0"/>', text)
        self.assertIn('<geom class="collision" type="mesh" mesh="bracket_hull1" name="bracket_hull1"/>', text)
        self.assertEqual(text.count('<geom class="visual" type="mesh" mesh="bracket"'), 1)
        self.assertEqual(sorted(files), ["bracket_block.stl", "bracket_bracket.stl", "bracket_bracket_hull0.stl",
                                         "bracket_bracket_hull1.stl"])
        # The contact rule tests the hulls: neither arm reaches the block, so no exclusion; the part's one hull,
        # its default collision, covers the block and is excluded.
        self.assertNotIn("<contact>", text)
        whole, _files = mjcf.rendered(describe(Source.read(self.build("pass")).view()))
        self.assertIn('<exclude body1="block" body2="bracket"/>', whole)
        # The URDF: a collision per hull, each its own mesh file.
        written, _files = urdf.rendered(description)
        self.assertIn('<collision name="bracket_hull0">', written)
        self.assertIn('<collision name="bracket_hull1">', written)
        self.assertIn('filename="meshes/bracket_bracket_hull1.stl"', written)

    def test_the_hulls_are_kept_in_the_engine_s_cache_by_the_mesh_and_the_options(self) -> None:
        import contextlib
        import io

        path = self.build('collision(arm, "decomposed")')
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            first = self.described(path)
            again = self.described(path)
        self.assertEqual(self.calls, [[{"maxHulls": 16}]], "the second description decomposed nothing")
        # The first says it decomposes, by the part, before CoACD starts; the second says nothing.
        self.assertEqual(said.getvalue(), "decomposing 1 part into convex hulls with CoACD: bracket (seconds to "
                                          "minutes each, once: the hulls are kept for the exports after)\n")
        self.assertEqual([c.geometry.mesh for c in again.link("bracket").collisions],
                         [c.geometry.mesh for c in first.link("bracket").collisions])
        held = sorted((self.folder / "cache" / "hulls").glob("*.npz"))
        self.assertEqual(len(held), 1)
        self.assertEqual(mjcf.rendered(again), mjcf.rendered(first))
        # A hit needs no coacd at all; another option is another key.
        with mock.patch("importlib.util.find_spec", return_value=None):
            describe(Source.read(path).view())
        self.described(self.build('collision(arm, "decomposed", max_hulls=2)'))
        self.assertEqual(self.calls, [[{"maxHulls": 16}], [{"maxHulls": 2}]])
        self.assertEqual(len(list((self.folder / "cache" / "hulls").glob("*.npz"))), 2)

    def test_parts_of_one_geometry_are_cut_by_their_own_options_and_a_default_decomposed_one_by_16(self) -> None:
        def stand_in(meshes: Any, _done: Any = None) -> list[list[tuple[Any, Any]]]:
            self.calls.append([dict(options) for _positions, _triangles, options in meshes])
            return [[_box(*ARMS[0])] * options["maxHulls"] for _positions, _triangles, options in meshes]

        for first, second in ((6, 1), (1, 6)):
            script = self.folder / "cups.py"
            script.write_text(textwrap.dedent(CUPS.format(first=first, second=second)), encoding="utf-8")
            os.utime(script, ns=(time.time_ns(), time.time_ns()))
            self.assertTrue(engine_build.build(script, ["cups"], cwd=self.folder)[0]["ok"])
            with mock.patch("cad.engine.hulls._decompose", stand_in):
                description = describe(Source.read(self.folder / "XBF/cups.xbf").view())
            self.assertEqual([len(description.link(name).collisions) for name in ("a", "b")], [first, second])
        # Decomposed by the description's default, a part declaring nothing is cut into at most 16, as the
        # declaration's default.
        self.calls.clear()
        with mock.patch("cad.engine.hulls._decompose", self.stand_in):
            describe(Source.read(self.build("pass")).view(), collision_default="decomposed")
        self.assertEqual(self.calls, [[{"maxHulls": 16}, {"maxHulls": 16}]])

    def test_a_part_cut_into_as_many_hulls_as_its_cap_says_so_as_it_is_done(self) -> None:
        import contextlib
        import io

        from cad.engine import hulls

        def stand_in(meshes: Any, done: Any) -> list[list[tuple[Any, Any]]]:
            for index, (_positions, _triangles, options) in enumerate(meshes):
                done(index, options["maxHulls"] if index == 0 else 1, 2.0)
            return [[_box(*ARMS[0])] for _mesh in meshes]

        said = io.StringIO()
        with mock.patch.object(hulls, "_decompose", stand_in), contextlib.redirect_stderr(said):
            hulls.hulls([(*_box(*ARMS[0]), {"maxHulls": 4}), (*_box(*ARMS[1]), {"maxHulls": 4})], ["capped", "under"])
        # At its cap, CoACD merged hulls to fit: the line says so, so the hulls are looked at.
        self.assertIn("\ndecomposed capped: 4 hulls, the cap (max_hulls=4) in 2.0 s (1 of 2)\n", said.getvalue())
        self.assertIn("\ndecomposed under: 1 hull in 2.0 s (2 of 2)\n", said.getvalue())



class FirstNeedTest(_Folder):
    """Where this environment lacks coacd, the decomposer runs in the coacd integration's environment, which the
    engine makes on first need (``hulls.PROVIDE`` stands in for it: no network here); where no environment can
    hold it, the refusal says why, naming the part and the extra."""

    def without_coacd(self) -> Any:
        real = importlib.util.find_spec
        return mock.patch("importlib.util.find_spec",
                          lambda name, *args: None if name == "coacd" else real(name, *args))

    def test_a_miss_runs_the_decomposer_in_the_environment_the_engine_makes_with_the_lines_of_its_making(self) -> None:
        import contextlib
        import io
        import pickle

        from cad.engine import hulls

        path = self.build('collision(arm, "decomposed")')
        asked: list[str] = []

        def provide(told: Any) -> str:
            told("making the coacd integration's environment, once: cad[coacd] (about 4 MB to download)")
            asked.append("made")
            return "/elsewhere/bin/python"

        def child(argv: list[str], env: dict[str, str], done: Any) -> tuple[int, list[str]]:
            self.assertEqual(argv[:4], ["/elsewhere/bin/python", "-P", "-m", "cad.coacd._decomposer"])
            self.assertNotIn("PYTHONPATH", env, "another environment's Python imports its own cad")
            jobs = pickle.loads(Path(argv[4]).read_bytes())
            Path(argv[5]).write_bytes(pickle.dumps([{"hulls": [_box(*arm) for arm in ARMS]} for _job in jobs]))
            for index, _job in enumerate(jobs):
                done(index, len(ARMS), 12.34)
            return 0, []

        said = io.StringIO()
        with self.without_coacd(), mock.patch.object(hulls, "published", return_value=True), \
                mock.patch.object(hulls, "PROVIDE", provide), mock.patch.object(hulls, "_child", child), \
                contextlib.redirect_stderr(said):
            description = describe(Source.read(path).view())
        self.assertEqual(asked, ["made"])
        self.assertIn("cad: making the coacd integration's environment, once", said.getvalue())
        # Each part is said as the child finishes it: a first export decomposes for minutes.
        self.assertIn("\ndecomposed bracket: 2 hulls in 12.3 s (1 of 1)\n", said.getvalue())
        self.assertEqual([c.name for c in description.link("bracket").collisions], ["bracket_hull0", "bracket_hull1"])
        # Kept: the next description asks for no environment at all.
        with self.without_coacd(), mock.patch.object(hulls, "PROVIDE", lambda _told: self.fail("asked again")):
            describe(Source.read(path).view())

    def test_where_no_environment_can_hold_coacd_the_refusal_says_why(self) -> None:
        from cad.engine import hulls

        path = self.build('collision(arm, "decomposed")')
        prefix = (r"part 'bracket' collides as convex hulls \(collision 'decomposed'\), which CoACD makes: coacd comes "
                  r"with cad's coacd integration, cad\[coacd\], ")
        cases = [
            ("no wheel", False, lambda _told: self.fail("no environment is made where no wheel exists"),
             prefix + r"which installs it only where CoACD publishes wheels, macOS arm64, Linux x86_64 and aarch64 "
                      r"\(glibc\) and Windows x86_64, and this is "),
            ("no engine", True, lambda _told: None,
             prefix + r"which this environment does not hold, and no engine answered to make its environment: "
                      r"export through the cad command"),
        ]
        for name, wheel, provide, said in cases:
            with self.subTest(name), self.without_coacd(), mock.patch.object(hulls, "published", return_value=wheel), \
                    mock.patch.object(hulls, "PROVIDE", provide):
                with self.assertRaisesRegex(DescriptionError, said):
                    describe(Source.read(path).view())

        def offline(_told: Any) -> str:
            raise hulls.Unavailable("the engine could not make cad[coacd]'s environment: uv cannot reach the network")

        with self.without_coacd(), mock.patch.object(hulls, "published", return_value=True), \
                mock.patch.object(hulls, "PROVIDE", offline):
            with self.assertRaisesRegex(DescriptionError, r"which CoACD makes: the engine could not make cad\[coacd\]'s "
                                                          r"environment: uv cannot reach the network; or declare it"):
                describe(Source.read(path).view())

    def test_coacd_publishes_wheels_for_four_platforms_alone(self) -> None:
        from cad.engine.hulls import published

        for system, machine, glibc, wheel in [
                ("Darwin", "arm64", None, True), ("Darwin", "x86_64", None, False),
                ("Windows", "AMD64", None, True), ("Windows", "ARM64", None, False),
                ("Linux", "x86_64", True, True), ("Linux", "aarch64", True, True),
                ("Linux", "x86_64", False, False), ("Linux", "armv7l", True, False), ("FreeBSD", "amd64", None, False)]:
            with self.subTest(system=system, machine=machine, glibc=glibc):
                self.assertIs(published(system, machine, glibc), wheel)

    def test_the_engine_is_asked_over_its_door_and_an_engine_without_the_request_is_none(self) -> None:
        from cad.engine import hulls

        told: list[str] = []

        def answering(answer: Any) -> Any:
            def request(message: dict[str, Any], on_log: Any = None, **_given: Any) -> Any:
                self.assertEqual(message, {"op": "integration", "integration": "coacd"})
                on_log({"log": "making the coacd integration's environment, once"})
                return answer
            return mock.patch("cad.engine.client.request", request)

        with answering({"ok": True, "python": "/env/bin/python"}):
            self.assertEqual(hulls._engine(told.append), "/env/bin/python")
        self.assertEqual(told, ["making the coacd integration's environment, once"])
        for answer in (None, {"failed": "unknown request 'integration'"}):
            with answering(answer):
                self.assertIsNone(hulls._engine(told.append))
        with answering({"failed": "uv cannot reach the network"}):
            with self.assertRaisesRegex(hulls.Unavailable, "could not make cad\\[coacd\\]'s environment: uv cannot"):
                hulls._engine(told.append)


@unittest.skipUnless(importlib.util.find_spec("coacd"), "coacd is the coacd extra's: requirements-dev.txt installs it")
class CoacdTest(_Folder):
    def test_coacd_cuts_an_l_shaped_part_into_hulls_that_mujoco_compiles(self) -> None:
        import mujoco

        import contextlib
        import io

        path = self.build('collision(arm, "decomposed")')
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            description = describe(Source.read(path).view())
        hulls = description.link("bracket").collisions
        self.assertGreaterEqual(len(hulls), 2)
        # The part said as the child finishes it, by its name, its hulls and its seconds.
        self.assertRegex(said.getvalue(), rf"\ndecomposed bracket: {len(hulls)} hulls in \d+\.\d s \(1 of 1\)\n")
        self.assertNotIn("cad-coacd-done", said.getvalue())
        for hull in hulls:  # each inside the part's box
            points = description.meshes[str(hull.geometry.mesh)].positions
            self.assertGreaterEqual(float(points.min()), -1e-4)
            self.assertLessEqual(float(points.max()), 0.0401)
        out = self.folder / "robot" / "bracket.xml"
        mjcf.write_description(description, out)
        model = mujoco.MjModel.from_xml_path(str(out))
        self.assertEqual(model.nmesh, 2 + len(hulls))
        self.assertNotIn("<contact>", out.read_text(encoding="utf-8"), "the arms clear the block")
