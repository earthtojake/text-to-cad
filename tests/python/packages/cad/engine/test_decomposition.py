"""A MuJoCo function's ``cad.mujoco.decompose`` (``hulls``, ``cad.coacd``): a part's collision replaced by the convex
hulls of its mesh, on a document's spec and on one read from an MJCF, with a decomposer the test stands in for;
the hulls kept in the engine's cache by the mesh and the options, so a second decomposition cuts nothing, the first
saying so as it starts, and each part as it is done, at its cap said so; at most 16 hulls by default, and options
out of range refused; a miss where coacd is not installed decomposed in the coacd integration's environment, which
the engine makes on first need (a stand-in here), and refused, saying why, where none can hold it (no wheel, no
engine, a making that failed); and, where coacd is installed (the development environment's extra), CoACD's own
hulls of an L-shaped part, two or more, which MuJoCo compiles, cut again from the MJCF it was written to."""

from __future__ import annotations

import contextlib
import importlib.util
import io
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
from cad.engine import hulls
from cad.engine.describe import describe
from cad.engine.export import Source
from cad.engine.export import mjcf

# An L-shaped bracket (two 40 x 10 x 10 mm arms meeting at the origin) turning about Z on a block that sits in its
# inner corner, 5 mm clear of both arms.
BRACKET = """
import build123d as bd
from cad.engine import xbf


@xbf("XBF/bracket.xbf")
def bracket():
    block = bd.Pos(25, 25, 5) * bd.Box(20, 20, 10)
    block.label = "block"
    arm = bd.Box(40, 10, 10, align=bd.Align.MIN) + bd.Box(10, 40, 10, align=bd.Align.MIN)
    arm.label = "bracket"
    turn = bd.RevoluteJoint("turn", block, axis=bd.Axis((0, 0, 0), (0, 0, 1)), angular_range=(-90, 90))
    bd.RigidJoint("turn", arm, turn.location)
    turn.connect_to(arm.joints["turn"], angle=0)
    return bd.Compound(children=[block, arm], label="bracket")
"""


# The bracket's two arms, in metres: what a decomposition of it should give, and what the stand-in gives.
ARMS = ((0.0, 0.0, 0.0, 0.04, 0.01, 0.01), (0.0, 0.0, 0.0, 0.01, 0.04, 0.01))


def _box(low_x: float, low_y: float, low_z: float, high_x: float, high_y: float, high_z: float) -> tuple[Any, Any]:
    corners = np.array([[x, y, z] for x in (low_x, high_x) for y in (low_y, high_y) for z in (low_z, high_z)],
                       dtype=np.float32)
    faces = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                      [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]], dtype=np.uint32)
    return corners, faces


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-decomposition-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        cache = mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(self.folder / "cache")})
        cache.start()
        self.addCleanup(cache.stop)
        self.calls: list[list[dict[str, Any]]] = []

    def build(self) -> Path:
        script = self.folder / "bracket.py"
        script.write_text(textwrap.dedent(BRACKET), encoding="utf-8")
        os.utime(script, ns=(time.time_ns(), time.time_ns()))
        report = engine_build.build(script, ["bracket"], cwd=self.folder)[0]
        self.assertTrue(report["ok"], report)
        return self.folder / "XBF/bracket.xbf"

    def stand_in(self, meshes: Any, _done: Any = None) -> list[list[tuple[Any, Any]]]:
        """The decomposer's child, stood in for: each mesh as the bracket's two arms."""
        self.calls.append([dict(options) for _positions, _triangles, options in meshes])
        return [[_box(*arm) for arm in ARMS] for _mesh in meshes]

    def without_coacd(self) -> Any:
        real = importlib.util.find_spec
        return mock.patch("importlib.util.find_spec",
                          lambda name, *args: None if name == "coacd" else real(name, *args))


class DecomposeTest(_Folder):
    """``cad.mujoco.decompose``: a part's collision replaced, in a MuJoCo function's spec, by its hulls, found by the
    part's label, on a document's spec and on one read from an MJCF, whose mesh is read from its file."""

    def test_a_document_s_spec_and_an_mjcf_s_take_the_hulls_by_the_part_s_label(self) -> None:
        import mujoco

        from cad.mujoco import collisions, decompose, save, spec

        cut: list[Any] = []

        def stand_in(meshes: Any, _done: Any = None) -> list[list[tuple[Any, Any]]]:
            cut.extend(positions for positions, _triangles, _options in meshes)
            return self.stand_in(meshes)

        path = self.build()
        made = spec(path)
        with mock.patch("cad.engine.hulls._decompose", stand_in):
            geoms = decompose(made, "bracket/bracket")
        self.assertEqual([geom.name for geom in geoms], ["bracket_hull0", "bracket_hull1"])
        self.assertEqual([geom.meshname for geom in geoms], ["bracket_hull0", "bracket_hull1"])
        self.assertEqual([geom.name for geom in collisions(made, "bracket")], ["bracket_hull0", "bracket_hull1"])
        self.assertIsNone(made.geom("bracket_collision"))
        self.assertEqual(made.compile().nmesh, 4)
        # At most 16 hulls by default; a second spec of the document finds them in the cache and cuts nothing.
        self.assertEqual(self.calls, [[{"maxHulls": 16}]])
        with mock.patch("cad.engine.hulls._decompose", stand_in):
            decompose(spec(path), "bracket")
        self.assertEqual(self.calls, [[{"maxHulls": 16}]], "the second decomposition found the hulls kept")
        # Read from an MJCF, the part is the mesh its collision uses, read from its file in metres.
        out = self.folder / "robot" / "bracket.xml"
        mjcf.write_description(describe(Source.read(path).view()), out)
        read = spec(out)
        with mock.patch("cad.engine.hulls._decompose", stand_in):
            geoms = decompose(read, "bracket", max_hulls=2, threshold=0.1)
        self.assertEqual(self.calls[-1], [{"maxHulls": 2, "threshold": 0.1}])
        np.testing.assert_allclose(cut[-1].min(axis=0), [0, 0, 0], atol=1e-6)
        np.testing.assert_allclose(cut[-1].max(axis=0), [0.04, 0.04, 0.01], atol=1e-6)
        self.assertEqual([geom.name for geom in geoms], ["bracket_hull0", "bracket_hull1"])
        with contextlib.redirect_stdout(io.StringIO()):
            save(read, self.folder / "saved" / "bracket.xml")
        model = mujoco.MjModel.from_xml_path(str(self.folder / "saved" / "bracket.xml"))
        self.assertEqual((model.nmesh, model.geom("bracket_hull1").group), (4, 3))
        # A miss where no environment can hold coacd is refused by the part's name, saying why.
        with self.without_coacd(), mock.patch.object(hulls, "published", return_value=False):
            with self.assertRaisesRegex(RuntimeError, r"^decompose 'bracket/bracket': CoACD makes the hulls: coacd "
                                                      r"comes with cad's coacd integration, cad\[coacd\], which "
                                                      r"installs it only where CoACD publishes wheels"):
                decompose(spec(path), "bracket", max_hulls=3)

    def test_an_option_out_of_range_is_refused_by_name(self) -> None:
        self.assertEqual(hulls.options(hulls.MAX_HULLS, None), {"maxHulls": 16})
        self.assertEqual(hulls.options(None, None), {}, "None for CoACD's no limit")
        for wrong in (0, True, 2.5):
            with self.assertRaisesRegex(ValueError, "max_hulls is a whole number of hulls, at least 1"):
                hulls.options(wrong, None)
        for wrong in (0.001, 2, "fine"):
            with self.assertRaisesRegex(ValueError, "threshold is CoACD's concavity threshold, 0.01 to 1"):
                hulls.options(None, wrong)


class CacheTest(_Folder):
    def test_the_hulls_are_kept_in_the_engine_s_cache_by_the_mesh_and_the_options(self) -> None:
        mesh = _box(0, 0, 0, 0.04, 0.04, 0.01)
        said = io.StringIO()
        with mock.patch.object(hulls, "_decompose", self.stand_in), contextlib.redirect_stderr(said):
            first = hulls.hulls([(*mesh, {"maxHulls": 16})], ["bracket"])
            again = hulls.hulls([(*mesh, {"maxHulls": 16})], ["bracket"])
        self.assertEqual(self.calls, [[{"maxHulls": 16}]], "the second asked for nothing")
        # The first says it decomposes, by the part, before CoACD starts; the second says nothing.
        self.assertEqual(said.getvalue(), "decomposing 1 part into convex hulls with CoACD: bracket (seconds to "
                                          "minutes each, once: the hulls are kept for the runs after)\n")
        for (positions, triangles), (kept, held) in zip(first[0], again[0]):
            np.testing.assert_array_equal(positions, kept)
            np.testing.assert_array_equal(triangles, held)
        self.assertEqual(len(list((self.folder / "cache" / "hulls").glob("*.npz"))), 1)
        # A hit needs no coacd at all; another option is another key.
        with self.without_coacd(), mock.patch.object(hulls, "PROVIDE", lambda _told: self.fail("asked")):
            hulls.hulls([(*mesh, {"maxHulls": 16})])
        with mock.patch.object(hulls, "_decompose", self.stand_in), contextlib.redirect_stderr(io.StringIO()):
            hulls.hulls([(*mesh, {"maxHulls": 2})])
        self.assertEqual(self.calls, [[{"maxHulls": 16}], [{"maxHulls": 2}]])
        self.assertEqual(len(list((self.folder / "cache" / "hulls").glob("*.npz"))), 2)

    def test_a_part_cut_into_as_many_hulls_as_its_cap_says_so_as_it_is_done(self) -> None:
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
    hold it, the refusal says why, naming the extra."""

    def test_a_miss_runs_the_decomposer_in_the_environment_the_engine_makes_with_the_lines_of_its_making(self) -> None:
        import pickle

        mesh = _box(0, 0, 0, 0.04, 0.04, 0.01)
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
            (found,) = hulls.hulls([(*mesh, {"maxHulls": 16})], ["bracket"])
        self.assertEqual(asked, ["made"])
        self.assertIn("cad: making the coacd integration's environment, once", said.getvalue())
        # Each part is said as the child finishes it: a first decomposition takes minutes.
        self.assertIn("\ndecomposed bracket: 2 hulls in 12.3 s (1 of 1)\n", said.getvalue())
        self.assertEqual(len(found), 2)
        # Kept: the next decomposition asks for no environment at all.
        with self.without_coacd(), mock.patch.object(hulls, "PROVIDE", lambda _told: self.fail("asked again")):
            hulls.hulls([(*mesh, {"maxHulls": 16})])

    def test_where_no_environment_can_hold_coacd_the_refusal_says_why(self) -> None:
        mesh = (*_box(0, 0, 0, 0.04, 0.04, 0.01), {"maxHulls": 16})
        prefix = r"^coacd comes with cad's coacd integration, cad\[coacd\], "
        cases = [
            ("no wheel", False, lambda _told: self.fail("no environment is made where no wheel exists"),
             prefix + r"which installs it only where CoACD publishes wheels, macOS arm64, Linux x86_64 and aarch64 "
                      r"\(glibc\) and Windows x86_64, and this is "),
            ("no engine", True, lambda _told: None,
             prefix + r"which this environment does not hold, and no engine answered to make its environment: "
                      r"run the script with cad run"),
        ]
        for name, wheel, provide, said in cases:
            with self.subTest(name), self.without_coacd(), mock.patch.object(hulls, "published", return_value=wheel), \
                    mock.patch.object(hulls, "PROVIDE", provide), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(hulls.Unavailable, said):
                    hulls.hulls([mesh])

        def offline(_told: Any) -> str:
            raise hulls.Unavailable("the engine could not make cad[coacd]'s environment: uv cannot reach the network")

        with self.without_coacd(), mock.patch.object(hulls, "published", return_value=True), \
                mock.patch.object(hulls, "PROVIDE", offline), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(hulls.Unavailable, r"^the engine could not make cad\[coacd\]'s environment: "
                                                           r"uv cannot reach the network$"):
                hulls.hulls([mesh])

    def test_coacd_publishes_wheels_for_four_platforms_alone(self) -> None:
        for system, machine, glibc, wheel in [
                ("Darwin", "arm64", None, True), ("Darwin", "x86_64", None, False),
                ("Windows", "AMD64", None, True), ("Windows", "ARM64", None, False),
                ("Linux", "x86_64", True, True), ("Linux", "aarch64", True, True),
                ("Linux", "x86_64", False, False), ("Linux", "armv7l", True, False), ("FreeBSD", "amd64", None, False)]:
            with self.subTest(system=system, machine=machine, glibc=glibc):
                self.assertIs(hulls.published(system, machine, glibc), wheel)

    def test_the_engine_is_asked_over_its_door_and_an_engine_without_the_request_is_none(self) -> None:
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
        from cad.mujoco import decompose, spec

        path = self.build()
        made = spec(path)
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            geoms = decompose(made, "bracket")
        self.assertGreaterEqual(len(geoms), 2)
        # The part said as the child finishes it, by its path, its hulls and its seconds.
        self.assertRegex(said.getvalue(), rf"\ndecomposed bracket/bracket: {len(geoms)} hulls in \d+\.\d s \(1 of 1\)\n")
        self.assertNotIn("cad-coacd-done", said.getvalue())
        self.assertEqual(made.compile().nmesh, 2 + len(geoms))
        # Read back from the plain MJCF, the part's mesh cut again from its file.
        plain = self.folder / "plain" / "bracket.xml"
        mjcf.write_description(describe(Source.read(path).view()), plain)
        read = spec(plain)
        with contextlib.redirect_stderr(io.StringIO()):
            again = decompose(read, "bracket")
        self.assertGreaterEqual(len(again), 2)
        self.assertEqual(read.compile().nmesh, 2 + len(again))
