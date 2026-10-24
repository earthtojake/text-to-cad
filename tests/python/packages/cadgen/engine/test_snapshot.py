"""`cadgen snapshot`: a document drawn by OCCT (`engine/render`) into a PNG, its timings
reported, and what an engine document's view does not offer refused by name before anything
renders, with OUT untouched; the document's own mesh exports drawn by OCCT too, read by their
readers (`engine/formats`, and `test_formats.py` for every kind), in this process and through the
daemon. A page on this machine may read a served document; a page from anywhere else may not.

A test that draws a document makes an OpenGL context and is skipped, saying why, where none can be
made (`test_render.py` says where that is); the refusals need none."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import urllib.request
from pathlib import Path

from cadgen.engine import build as engine_build
from cadgen.engine.access import loopback_origin
from cadgen.engine.render import context
from cadgen.engine.serve import Server
from cadgen.engine.snapshot import (SnapshotRefused, authored, parse_annotation, parse_camera, parse_display,
                                    parse_measurements, snapshot)
from tests.python.support import opengl

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"

MODEL = """
import build123d as bd
from cadgen.engine import paint, xbf


@xbf("XBF/stand.xbf")
def stand():
    plate = bd.Box(40, 20, 4) - bd.Cylinder(4, 10)
    plate = paint(plate, plate.faces().sort_by(bd.Axis.Z)[-1], "#ffa500")
    plate.label = "plate"
    peg = bd.Cylinder(3, 12)
    peg.label = "peg"
    return bd.Compound(children=[plate, bd.Pos(12, 0, 8) * peg, bd.Pos(-12, 0, 8) * peg], label="stand")


@xbf("XBF/peg.xbf")
def peg():
    return bd.Cylinder(3, 12)
"""


def gl() -> None:
    """Skip, saying why, where no OpenGL context can be made (on CI with a display, fail)."""
    opengl.require(context.available())


class SnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(tempfile.mkdtemp(prefix="engine-snapshot-")).resolve()
        script = cls.folder / "stand.py"
        script.write_text(textwrap.dedent(MODEL), encoding="utf-8")
        reports = engine_build.build(script, None, cwd=cls.folder)
        assert all(report["ok"] for report in reports), reports
        cls.document = cls.folder / "XBF/stand.xbf"
        cls.single = cls.folder / "XBF/peg.xbf"
        # One part at a time on this process's thread: the test asks for no pool.
        cls.mesh = os.environ.get("CADGEN_ENGINE_MESH")
        os.environ["CADGEN_ENGINE_MESH"] = "inline"

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.mesh is None:
            os.environ.pop("CADGEN_ENGINE_MESH", None)
        else:
            os.environ["CADGEN_ENGINE_MESH"] = cls.mesh
        shutil.rmtree(cls.folder, ignore_errors=True)

    def test_a_document_is_drawn_into_a_png_with_its_timings(self) -> None:
        from PIL import Image

        gl()
        out = self.folder / "solid.png"
        report = snapshot(self.document, out, display=parse_display("solid", grid=False), camera=parse_camera("iso"),
                          size=(320, 240), daemon=False)
        self.assertEqual((report["width"], report["height"], report["camera"]), (320, 240, "iso"))
        self.assertEqual((report["parts"], report["instances"], report["unmeshed"], report["renderer"]),
                         (2, 3, {}, "occt"))
        for stage in ("serveMs", "meshMs", "sceneMs", "presentMs", "frameMs", "drawMs", "renderMs", "totalMs"):
            self.assertIsInstance(report["timings"][stage], int, stage)
        with Image.open(out) as image:
            self.assertEqual(image.size, (320, 240))
            data = image.convert("RGB").tobytes()
        pixels = [tuple(data[at:at + 3]) for at in range(0, len(data), 3)]
        # Not a blank frame: the backdrop is one colour; the parts, their paint and edges are many.
        backdrop = max(set(pixels), key=pixels.count)
        drawn = [pixel for pixel in pixels if pixel != backdrop]
        self.assertGreater(len(drawn), len(pixels) // 10)
        self.assertGreater(len(set(drawn)), 50)
        # The painted top face is warm (the viewer's surface grades its orange): red well above blue.
        self.assertTrue(any(r - b > 60 for r, g, b in drawn))

    def test_the_cli_prints_what_it_drew_and_its_timings(self) -> None:
        gl()
        out = self.folder / "wire.png"
        env = {**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_MESH": "inline"}
        done = subprocess.run([sys.executable, "-m", "cadgen.engine", "snapshot", str(self.document), str(out),
                               "--display", "wireframe", "--grid", "--width", "200", "--height", "160",
                               "--json"], env=env, capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual((report["displayMode"], report["width"], report["height"]), ("wireframe", 200, 160))
        self.assertGreater(report["timings"]["totalMs"], 0)
        self.assertEqual(out.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_what_a_document_does_not_offer_is_refused_by_name_and_keeps_the_earlier_picture(self) -> None:
        # A refused or failed run leaves the picture an earlier run wrote at OUT byte for byte,
        # and nothing beside it; an OUT that is no .png is refused, and kept.
        out = self.folder / "stale.png"

        def stale() -> Path:
            out.write_bytes(b"before")
            return out
        with self.assertRaisesRegex(SnapshotRefused, "exploded=2 is no amount"):
            parse_display("exploded=2", grid=False)
        with self.assertRaisesRegex(SnapshotRefused, "display.exploded has no spin"):
            parse_display('{"exploded": {"amount": 0.5, "spin": 1}}', grid=False)
        with self.assertRaisesRegex(SnapshotRefused, "'solid' is no display mode"):
            parse_display("wireframe,solid", grid=False)
        with self.assertRaisesRegex(SnapshotRefused, "lighting"):
            parse_display('{"lighting": {}}', grid=False)
        with self.assertRaisesRegex(SnapshotRefused, "sideways"):
            parse_display("sideways", grid=False)
        with self.assertRaisesRegex(SnapshotRefused, "underneath"):
            parse_camera("underneath")
        with self.assertRaisesRegex(SnapshotRefused, "projection"):
            parse_camera('{"projection": "perspective"}')
        (self.folder / "out.jpg").write_bytes(b"a photo")
        with self.assertRaisesRegex(SnapshotRefused, r"\.png"):
            snapshot(self.document, self.folder / "out.jpg", daemon=False)
        self.assertEqual((self.folder / "out.jpg").read_bytes(), b"a photo")
        # Parts colours placed parts apart, and Explode moves them apart: a document of one is
        # refused before anything renders.
        for said, call in (
                ("parts .* places 1 part", lambda: snapshot(self.single, stale(), display={"mode": "parts"}, daemon=False)),
                ("exploded .* peg.xbf places 1 part", lambda: snapshot(
                    self.single, stale(), display=parse_display("exploded=0.5", grid=False), daemon=False)),
                ("--camera authored .* give --annotation", lambda: snapshot(self.document, stale(), camera="authored",
                                                                           daemon=False))):
            with self.assertRaisesRegex(SnapshotRefused, said):
                call()
            self.assertEqual(out.read_bytes(), b"before", said)
        env = {**os.environ, "PYTHONPATH": str(SRC)}
        stale()
        done = subprocess.run([sys.executable, "-m", "cadgen.engine", "snapshot", str(self.single), str(out),
                               "--display", '{"exploded": {"enabled": true}}'],
                              env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 2)
        self.assertIn("display.exploded", done.stderr)
        self.assertEqual(out.read_bytes(), b"before")

    def test_a_failed_render_keeps_every_earlier_picture_and_a_job_moves_its_pictures_in_together(self) -> None:
        from unittest import mock

        from cadgen.engine import snapshot as drawing
        from cadgen.engine.render import service

        folder = Path(tempfile.mkdtemp(prefix="engine-kept-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        first, second = folder / "first.png", folder / "second.png"
        first.write_bytes(b"first, earlier")
        second.write_bytes(b"second, earlier")
        with mock.patch.object(service, "draw_here", side_effect=RuntimeError("the render broke")), \
                self.assertRaisesRegex(RuntimeError, "the render broke"):
            snapshot(self.document, first, daemon=False)
        self.assertEqual(first.read_bytes(), b"first, earlier")
        still = drawing.Still({}, None, False, False, (8, 8), None, None, None)
        pictures = [(self.document, first, still), (self.document, second, still)]
        drawn = {"timings": {}}
        written = drawing._written

        def second_fails(document, out, data, report, started):
            if len(list(folder.glob(".*.tmp/*.png"))) == 1:  # the first picture is in its staging folder
                raise OSError("the disk is full")
            return written(document, out, data, report, started)

        with mock.patch.object(service, "draw_here_each", return_value=[(b"new 1", dict(drawn)), (b"new 2", dict(drawn))]):
            with mock.patch.object(drawing, "_written", side_effect=second_fails), \
                    self.assertRaisesRegex(OSError, "disk is full"):
                drawing.draw_pictures(pictures, daemon=False)
            self.assertEqual((first.read_bytes(), second.read_bytes()), (b"first, earlier", b"second, earlier"))
            self.assertEqual(sorted(path.name for path in folder.iterdir()), ["first.png", "second.png"])
            done = drawing.draw_pictures(pictures, daemon=False)
        self.assertEqual((first.read_bytes(), second.read_bytes()), (b"new 1", b"new 2"))
        self.assertEqual([found["output"] for found in done], [str(first), str(second)])
        self.assertEqual(sorted(path.name for path in folder.iterdir()), ["first.png", "second.png"])

    def test_an_out_that_is_a_folder_is_given_the_source_s_stem_and_the_time(self) -> None:
        import re

        from cadgen.engine import api
        from cadgen.engine.snapshot import picture_path

        folder = Path(tempfile.mkdtemp(prefix="engine-out-folder-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        timed = r"_\d{8}T\d{6}Z\.png"
        self.assertRegex(picture_path(folder, self.document).name, rf"^stand{timed}$")  # a folder that is there
        fresh = picture_path(f"{folder / 'stills'}{os.sep}", self.document)  # a separator: a folder to be
        self.assertEqual(fresh.parent, folder / "stills")
        ident = "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab"
        self.assertRegex(picture_path(folder, ident).name, rf"^{ident}{timed}$")  # a document's id
        self.assertEqual(picture_path(folder / "named.png", self.document), folder / "named.png")
        # A packet's pictures share one time, told apart by their job and output where they have several.
        self.assertEqual(picture_path(folder, self.document, at="T", job=(1, 3), output=(0, 2)).name, "stand_j2_1_T.png")
        self.assertEqual(picture_path(folder, self.document, at="T", job=(0, 1), output=(0, 1)).name, "stand_T.png")
        (folder / "file.png").write_bytes(b"x")
        with self.assertRaisesRegex(SnapshotRefused, "names a folder"):
            picture_path(f"{folder / 'file.png'}{os.sep}", self.document)
        # The verb writes there, and says where.
        gl()
        drawn = api.snapshot(self.document, f"{folder / 'stills'}{os.sep}", width=160, height=120, daemon=False)
        self.assertEqual(drawn.path.parent, folder / "stills")
        self.assertRegex(drawn.path.name, rf"^stand{timed}$")
        self.assertEqual((Path(drawn.report["output"]), drawn.path.read_bytes()[:4]), (drawn.path, b"\x89PNG"))

    def test_a_failure_under_json_is_its_envelope_on_stdout(self) -> None:
        """Under --json a verb says its failure as ``{"ok": false, "error": ...}`` on stdout, the result's
        channel, and exits 1; without it, its words on stderr: 2 for a request refused before anything ran."""
        import contextlib
        import io

        from cadgen.engine import cli
        from cadgen.engine.snapshot import main as snapshot_main

        def run(call) -> tuple[int, str, str]:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = call()
            return status, out.getvalue(), err.getvalue()

        out = str(self.folder / "enveloped.png")
        for argv, said, status in ((["snapshot", str(self.folder / "missing.xbf"), out], "no document", 2),
                                   (["snapshot", str(self.document), out, "--display", "sideways"], "sideways", 2)):
            with self.subTest(argv=argv):
                code, printed, err = run(lambda: cli.main([*argv, "--json"]))
                found = json.loads(printed)
                self.assertEqual((code, set(found), found["ok"], err), (1, {"ok", "error"}, False, ""))
                self.assertIn(said, found["error"])
                code, printed, err = run(lambda: cli.main(argv))
                self.assertEqual((code, printed), (status, ""))
                self.assertIn(said, err)
        # A format's own snapshot: what it does not draw, refused in the same envelope.
        code, printed, _err = run(lambda: snapshot_main([str(self.document), out, "--json"], prog="cadgen dxf snapshot",
                                                        suffixes=(".dxf",)))
        self.assertEqual((code, json.loads(printed)), (1, {"ok": False, "error": f"{self.document} is not a .dxf file"}))

    def test_explode_an_annotation_and_measurements_are_asked_for_by_flags_and_checked(self) -> None:
        self.assertEqual(parse_display("exploded=0.6", grid=False), {"exploded": {"enabled": True, "amount": 0.6}})
        self.assertEqual(parse_display("hidden-line,exploded", grid=True),
                         {"mode": "hidden-line", "exploded": {"enabled": True, "amount": 0.5}, "grid": True})
        self.assertEqual(parse_display('{"exploded": {"enabled": true}}', grid=False)["exploded"]["amount"], 0.5)
        mark = {"id": "m1", "kind": "stroke", "part": "i0", "points": [-10, 0, 2, 10, 0, 2], "color": "#ff00ff", "width": 4,
                "view": "view 1"}
        annotation = {"units": "mm", "parts": {}, "marks": [mark]}
        for broken, said in (({"marks": {}}, "units, parts and marks"), ({"marks": [], "colour": 1}, "has no colour"),
                             ({"marks": [{**mark, "kind": "blob"}]}, r"marks\[0\].kind"),
                             ({"marks": [{**mark, "points": [0, 0]}]}, "triples"),
                             ({"marks": [{**mark, "view": 1}]}, "label of the view")):
            with self.assertRaisesRegex(SnapshotRefused, said):
                parse_annotation(json.dumps(broken))
        with self.assertRaisesRegex(SnapshotRefused, "no such file"):
            parse_annotation(str(self.folder / "missing.json"))
        line = {"start": [-20, -10, 2], "end": [20, -10, 2], "label": "40.0 mm", "color": "#0000ff"}
        self.assertEqual(parse_measurements(json.dumps(line)), [line], "one, as a chip copies it")
        with self.assertRaisesRegex(SnapshotRefused, r"\.start is \[x, y, z\]"):
            parse_measurements(json.dumps([{**line, "start": [0, 0]}]))

    def test_the_authored_view_is_read_from_the_quick_edit_packet(self) -> None:
        """A mark names its view by label; the view -- camera, size, projection -- is a job of the
        packet the viewer writes (``cadgen.viewer``'s prompt files), given as --annotation or beside
        the annotation file. None, or no view: refused by name."""
        folder = Path(tempfile.mkdtemp(prefix="engine-authored-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        camera = {"position": [80, -60, 50], "target": [0, 0, 4], "up": [0, 0, 1], "orthographicHalfHeight": 25}
        mark = {"id": "m1", "kind": "stroke", "part": "i0", "points": [-10, 0, 2, 10, 0, 2], "color": "#ff00ff",
                "width": 4, "view": "view 1"}
        annotation = {"units": "mm", "parts": {}, "marks": [mark]}
        packet = {"input": str(self.document), "annotation": annotation, "jobs": [
            {"camera": camera, "display": {"mode": "solid", "camera": {"projection": "orthographic"}},
             "output": {"padding": 0, "tightFrame": False},
             "outputs": [{"path": str(folder / "stand-1-view-1.png"), "label": "view 1", "width": 240, "height": 180}]}]}
        (folder / "stand-1.snapshot.json").write_text(json.dumps(packet), encoding="utf-8")
        file = folder / "stand-2.annotation.json"
        file.write_text(json.dumps(annotation), encoding="utf-8")
        self.assertEqual(parse_camera("authored"), "authored")
        self.assertEqual(parse_annotation(str(folder / "stand-1.snapshot.json")), annotation, "a packet's annotation")
        for source in (str(file), str(folder / "stand-1.snapshot.json"), packet):
            found, exact, view = authored("authored", annotation, source, self.document)
            self.assertEqual((found, exact, view.size, view.lens), (camera, True, (240, 180), {"projection": "orthographic"}))
        self.assertEqual(authored("iso", annotation, str(file), self.document)[:2], ("iso", False))
        with self.assertRaisesRegex(SnapshotRefused, "name no view"):
            authored("authored", {"marks": [{**mark, "view": None}]}, str(file), self.document)
        with self.assertRaisesRegex(SnapshotRefused, "give --annotation"):
            authored("authored", None, None, self.document)
        # A packet beside the file that draws another document, or no packet: refused, naming what it lacks.
        with self.assertRaisesRegex(SnapshotRefused, "no Quick Edit packet .* beside stand-2.annotation.json holds "
                                                     "that view of peg.xbf"):
            authored("authored", annotation, str(file), self.single)
        with self.assertRaisesRegex(SnapshotRefused, "'view 2'"):
            authored("authored", {"marks": [{**mark, "view": "view 2"}]}, str(file), self.document)
        # The verb draws from it: the view's size unless one is asked, over the exploded parts, ink and dimension on.
        gl()
        out = folder / "annotated.png"
        report = snapshot(self.document, out, display=parse_display("exploded=0.6", grid=False), camera="authored",
                          daemon=False, annotation=annotation, annotation_source=str(file),
                          measurements=[{"start": [-20, -10, 2], "end": [20, -10, 2], "label": "40.0 mm",
                                         "color": "#0000ff"}])
        self.assertEqual((report["exploded"], report["width"], report["height"]), (0.6, 240, 180))
        self.drawn(out, (240, 180))

    def packet(self, folder: Path) -> tuple[dict, dict]:
        """A Quick Edit packet of two views, as the viewer writes one, and the first view's camera: the
        view the ink was drawn in (a peg hidden), and a top view written twice -- into a folder, and
        from the front -- on nothing, padded wide and supersampled."""
        camera = {"position": [80, -60, 50], "target": [0, 0, 4], "up": [0, 0, 1], "orthographicHalfHeight": 25}
        mark = {"id": "m1", "kind": "stroke", "part": "i0", "points": [-10, 0, 2, 10, 0, 2], "color": "#ff00ff",
                "width": 4, "view": "view 1"}
        packet = {"input": str(self.document), "annotation": {"units": "mm", "parts": {}, "marks": [mark]},
                  "measurements": [{"start": [-20, -10, 2], "end": [20, -10, 2], "label": "40.0 mm", "color": "#0000ff"}],
                  "hidden": ["peg.1"], "jobs": [
                      {"camera": camera, "display": {"mode": "solid", "camera": {"projection": "orthographic"},
                                                     "hidden": ["peg.1"]},
                       "output": {"padding": 0, "tightFrame": False},
                       "outputs": [{"path": str(folder / "view-1.png"), "label": "view 1", "width": 240, "height": 180}]},
                      {"camera": "top", "display": {"mode": "xray"},
                       "output": {"padding": 0.15, "transparent": True, "renderScale": 2},
                       "outputs": [{"path": f"{folder / 'tops'}{os.sep}", "width": 200, "height": 150},
                                   {"path": str(folder / "front.png"), "camera": "front", "width": 160, "height": 120}]}]}
        return packet, camera

    def test_a_job_replays_each_view_of_a_packet_into_every_output_it_names(self) -> None:
        """``--job``: each view drawn as the snapshot draws it (the first, exactly as ``--annotation PACKET
        --camera authored`` with its display draws it), the packet's ink and dimensions over each, every output
        written at its job's settings: on nothing (its backdrop's colour matted out), supersampled to its size."""
        import numpy as np
        from PIL import Image

        from cadgen.engine import cli

        gl()
        folder = Path(tempfile.mkdtemp(prefix="engine-job-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        packet, _camera = self.packet(folder)
        path = folder / "stand-1.snapshot.json"
        path.write_text(json.dumps(packet), encoding="utf-8")
        done = subprocess.run([sys.executable, "-m", "cadgen.engine", "snapshot", "--job", str(path)],
                              env={**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_MESH": "inline"},
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, 0, done.stderr)
        [top] = (folder / "tops").iterdir()
        self.assertRegex(top.name, r"^stand_j2_1_\d{8}T\d{6}Z\.png$")
        self.assertEqual([line.split(" (")[0] for line in done.stdout.splitlines()],
                         [f"wrote {os.path.relpath(found)}" for found in (folder / "view-1.png", top, folder / "front.png")])

        def rgba(found: Path) -> np.ndarray:
            with Image.open(found) as image:
                return np.asarray(image.convert("RGBA")).astype(int)

        # The view the ink was drawn in: the snapshot's own picture of it, its peg left out.
        alone = folder / "alone.png"
        snapshot(self.document, alone, display=parse_display(json.dumps(packet["jobs"][0]["display"]), grid=False),
                 camera="authored", daemon=False, annotation=packet["annotation"], annotation_source=packet,
                 measurements=packet["measurements"])
        self.assertLess(np.abs(rgba(folder / "view-1.png") - rgba(alone)).max(), 3)
        everything = folder / "everything.png"
        snapshot(self.document, everything, display={"mode": "solid", "camera": {"projection": "orthographic"}},
                 camera="authored", daemon=False, annotation=packet["annotation"], annotation_source=packet)
        self.assertGreater(np.abs(rgba(folder / "view-1.png") - rgba(everything)).max(), 60, "the hidden peg is drawn")
        # On nothing, at its size: what is not the model is clear, and over the look's backdrop it is the
        # picture drawn on that backdrop.
        for found, size in ((top, (200, 150)), (folder / "front.png", (160, 120))):
            picture = rgba(found)
            self.assertEqual((picture.shape[1], picture.shape[0]), size)
            self.assertEqual((picture[0, 0, 3], picture[..., 3].max() > 200), (0, True), found.name)
        opaque = folder / "opaque.json"
        job = {**packet["jobs"][1], "output": {"padding": 0.15, "renderScale": 2},
               "outputs": [{"path": str(folder / "opaque.png"), "width": 200, "height": 150}]}
        opaque.write_text(json.dumps({"input": str(self.document), "jobs": [job]}), encoding="utf-8")
        self.assertEqual(cli.main(["snapshot", "--job", str(opaque), "--json"]), 0)
        drawn, clear = rgba(folder / "opaque.png")[..., :3], rgba(top)

        def linear(srgb: np.ndarray) -> np.ndarray:
            srgb = srgb / 255
            return np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)

        alpha = clear[..., 3:] / 255  # laid over the backdrop in linear light, as OCCT lays its X-ray faces
        over = linear(clear[..., :3]) * alpha + linear(drawn[0, 0]) * (1 - alpha)
        over = np.where(over <= 0.0031308, over * 12.92, 1.055 * over ** (1 / 2.4) - 0.055) * 255
        self.assertLess(np.abs(over - drawn).mean(), 1.0)
        # Padded wide, the model is drawn smaller than with no padding.
        tight = folder / "tight.json"
        tight.write_text(json.dumps({"input": str(self.document), "jobs": [{**job, "output": {"padding": 0}, "outputs": [
            {"path": str(folder / "tight.png"), "width": 200, "height": 150}]}]}), encoding="utf-8")
        self.assertEqual(cli.main(["snapshot", "--job", str(tight)]), 0)

        def reach(found: Path) -> int:
            picture = rgba(found)[..., :3]
            drawn_x = np.nonzero((np.abs(picture - picture[0, 0]).sum(-1) > 30).any(0))[0]
            return int(drawn_x.max() - drawn_x.min())
        self.assertLess(reach(folder / "opaque.png"), reach(folder / "tight.png") * 0.85)

    def test_a_job_is_checked_before_anything_renders(self) -> None:
        from cadgen.engine import cli
        from cadgen.engine.snapshot import job_pictures

        folder = Path(tempfile.mkdtemp(prefix="engine-job-refused-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        packet, _camera = self.packet(folder)
        pictures = job_pictures(packet)
        self.assertEqual([(out.name, still.exact, still.padding, still.tight, still.transparent, still.scale, still.size)
                          for _document, out, still in pictures][::2],
                         [("view-1.png", True, 0.0, False, False, 1.0, (240, 180)),
                          ("front.png", False, 0.15, True, True, 2.0, (160, 120))])
        self.assertEqual(pictures[0][2].display["hidden"], ["peg.1"])
        self.assertEqual([still.annotation for _document, _out, still in pictures], [packet["annotation"]] * 3,
                         "the packet's ink, over every view")
        # The flags override every job: SRC drawn in place of the input, and the size of every output.
        sized = job_pictures(packet, self.single, width=64, height=48)
        self.assertEqual({(document, still.size) for document, _out, still in sized}, {(self.single, (64, 48))})
        stale = folder / "view-1.png"
        stale.write_bytes(b"an earlier run's")
        job = packet["jobs"][1]
        for broken, said in (
                ({**packet, "colour": 1}, "--job has no colour"),
                ({**packet, "jobs": [{**job, "mode": "list"}]}, r"jobs\[0\] has no mode"),
                ({**packet, "jobs": [{**job, "output": {"padding": 0.5}}]}, r"padding is a number from 0 to 0.15"),
                ({**packet, "jobs": [{**job, "output": {"renderScale": 4}}]}, r"renderScale is a number from 1 to 3"),
                ({**packet, "jobs": [{**job, "output": {"viewLabels": True}}]}, "output has no viewLabels"),
                ({**packet, "jobs": [{**job, "outputs": []}]}, "lists the pictures it writes"),
                ({**packet, "jobs": [{**job, "outputs": [{"path": str(folder / "a.jpg")}]}]}, r"a\.jpg is not one"),
                ({**packet, "jobs": [job, job]}, "writes .*front.png twice"),
                ({**packet, "input": str(folder / "gone.xbf")}, "no document"),
                ({"jobs": [job]}, "names no input"),
                ({**packet, "jobs": [{**job, "selection": {"pick": []}}]}, r"selection is \{hide, focus\}")):
            with self.subTest(said=said), self.assertRaisesRegex(SnapshotRefused, said):
                job_pictures(broken)
        self.assertEqual(stale.read_bytes(), b"an earlier run's", "a refused job writes nothing, and takes nothing away")
        # A document's id is drawn in place of the job's input, as the engine holds it; a script never is.
        ident = "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab"
        self.assertEqual(str(job_pictures(packet, ident)[0][0]), ident)
        for script in (self.folder / "stand.py", f"{self.folder / 'stand.py'}::stand"):
            with self.subTest(script=str(script)), self.assertRaisesRegex(SnapshotRefused, "is neither a document"):
                job_pictures(packet, script)
        import contextlib
        import io

        path = folder / "packet.json"
        path.write_text(json.dumps(packet), encoding="utf-8")
        for argv, said in ((["--job", str(path), str(self.document), str(folder / "out.png")], "takes no OUT"),
                           ([str(self.document)], "required: SRC, OUT.png")):
            with self.subTest(argv=argv):
                printed = io.StringIO()
                with contextlib.redirect_stdout(printed):
                    self.assertEqual(cli.main(["snapshot", *argv, "--json"]), 1)
                self.assertIn(said, json.loads(printed.getvalue())["error"])

    def drawn(self, path: Path, size: tuple[int, int]) -> None:
        """A picture of something: the size asked, and more than a backdrop."""
        from PIL import Image

        with Image.open(path) as image:
            self.assertEqual(image.size, size)
            data = image.convert("RGB").tobytes()
        pixels = [tuple(data[at:at + 3]) for at in range(0, len(data), 3)]
        backdrop = max(set(pixels), key=pixels.count)
        self.assertGreater(len([pixel for pixel in pixels if pixel != backdrop]), len(pixels) // 20)

    def test_a_mesh_file_is_drawn_by_occt_as_its_document_is(self) -> None:
        """The document's GLB, STL and 3MF, read by their readers and drawn by OCCT, frame as the
        document does: the same parts where the document has them (the STL one part of all)."""
        from cadgen.engine.export import translate

        gl()
        for suffix, parts in ((".glb", 2), (".stl", 1), (".3mf", 2)):
            mesh = self.folder / f"stand{suffix}"
            translate(self.document, None, mesh)
            out = self.folder / f"mesh-{suffix[1:]}.png"
            report = snapshot(mesh, out, camera=parse_camera("iso"), size=(240, 180), daemon=False)
            self.assertEqual((report["width"], report["height"], report["renderer"], report["kind"]),
                             (240, 180, "occt", suffix[1:]), suffix)
            self.assertEqual((report["parts"], report["instances"]), (parts, 3 if parts > 1 else 1), suffix)
            self.drawn(out, (240, 180))
        with self.assertRaisesRegex(SnapshotRefused, "is a mesh and has none"):
            snapshot(self.folder / "stand.glb", self.folder / "posed.png", pose="raised", daemon=False)

    def test_a_model_is_drawn_from_its_worker_and_the_picture_is_the_snapshot_s_one_file(self) -> None:
        from cadgen.engine import api

        gl()
        folder = Path(tempfile.mkdtemp(prefix="engine-drawn-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        script = folder / "stand.py"
        # No @xbf: the picture is drawn from the document the worker holds. The build writes what the
        # model declares (law 10), its GLB; the snapshot, no file but the picture.
        script.write_text(textwrap.dedent(MODEL).replace("@xbf(\"XBF/stand.xbf\")\ndef stand", "@glb(\"stand.glb\")\ndef stand")
                          .replace("import paint, xbf", "import glb, paint, xbf"), encoding="utf-8")
        drawn = api.snapshot(_model(script, "stand"), folder / "stand.png", display="xray", camera="iso", width=200,
                             height=150, daemon=False)
        self.assertEqual((drawn.width, drawn.height), (200, 150))
        self.drawn(folder / "stand.png", (200, 150))
        self.assertEqual(sorted(path.name for path in folder.rglob("*") if path.is_file()),
                         ["stand.glb", "stand.png", "stand.py"])

    def test_a_model_taken_from_its_file_is_drawn_from_that_file(self) -> None:
        from cadgen.engine import api
        from cadgen.engine.kernel import memo

        gl()
        folder = Path(tempfile.mkdtemp(prefix="engine-taken-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        script = folder / "stand.py"
        script.write_text(textwrap.dedent(MODEL), encoding="utf-8")
        self.assertTrue(engine_build.build(script, ["stand"], cwd=folder)[-1]["ok"])
        xbf = folder / "XBF" / "stand.xbf"
        written = xbf.stat().st_mtime_ns
        # A fresh process: nothing held, so the build takes the model's xbf whole from its file.
        for held in (engine_build._WRITTEN, engine_build._PARTS, engine_build._BUILT):
            held.clear()
        memo.clear()
        self.addCleanup(memo.clear)
        drawn = api.snapshot(_model(script, "stand"), folder / "stand.png", camera="iso", width=200, height=150,
                             daemon=False)
        self.assertEqual((drawn.width, drawn.height), (200, 150))
        self.drawn(folder / "stand.png", (200, 150))
        self.assertEqual(xbf.stat().st_mtime_ns, written, "taken, not written again")


def _model(script: Path, name: str):
    """The ``Model`` a script defines, as the program importing it has it (Python's own import)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"{script.stem}_{name}_model", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, name)


class AccessTest(unittest.TestCase):
    """The page that reads a document from the engine is the viewer's or the snapshot's, on this
    machine: those origins are named as allowed readers, and no other is."""

    def test_loopback_pages_may_read_a_served_document_and_no_other_page_may(self) -> None:
        for origin in ("http://127.0.0.1:3245", "http://localhost", "http://[::1]:5173", "http://app.localhost:8080"):
            self.assertTrue(loopback_origin(origin), origin)
        for origin in ("https://example.com", "http://127.0.0.1.example.com", "null", "", None, "http://localhost:x"):
            self.assertFalse(loopback_origin(origin), origin)
        folder = Path(tempfile.mkdtemp(prefix="engine-access-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        (folder / "peg.py").write_text(textwrap.dedent(MODEL), encoding="utf-8")
        engine_build.build(folder / "peg.py", ["peg"], cwd=folder)
        server = Server(port=0, mesh_mode="inline")
        server.start()
        self.addCleanup(server.stop)
        url = f"{server.url}/api/doc/{server.add(folder / 'XBF' / 'peg.xbf')}"

        def allowed(origin: str) -> str | None:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Origin": origin}), timeout=60) as answer:
                return answer.headers.get("Access-Control-Allow-Origin")

        self.assertEqual(allowed("http://127.0.0.1:3245"), "http://127.0.0.1:3245")
        self.assertIsNone(allowed("https://example.com"))


if __name__ == "__main__":
    unittest.main()
