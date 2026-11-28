"""The stills on the WebAssembly kernel (``render/core.py``): ``occt.Scene``'s decisions written as the view core's
scene, and the ``render`` job asked of its job server. The server here is a stand-in that speaks its frames and keeps
buffers by key (the real one is the view core's host, whose pictures its own tools hold to OCCT's, case by case), so
what the scene says and what crosses the pipe are checked wherever the suite runs; the pictures the core draws are
``test_render.py``'s goldens where the suite runs on that kernel. The path loads no kernel module: a render process on
that kernel runs in a Python that has none."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np

from tests.python.support.paths import add_sources

SRC = add_sources()

from cad.engine.formats.buffer import buffer  # noqa: E402
from cad.engine.render import core as drawing  # noqa: E402
from cad.engine.render import finish  # noqa: E402
from cad.engine.render.core import NOT_YET, Core, CoreScene  # noqa: E402
from cad.engine.render.look import LOOK  # noqa: E402
from cad.engine.render.occt import BACKGROUND, EDGES_WIN_OFFSET  # noqa: E402
from cad.engine.snapshot import SnapshotRefused, Still  # noqa: E402

# A job server that keeps each buffer sent under a key, answers ``missing`` for a key it does not keep, and draws
# the scene's background over the picture asked; every request is written to the log it is given, a JSON line.
SERVER = textwrap.dedent("""
    import json, struct, sys
    sizes = struct.Struct(">QI")
    asked, out, log = sys.stdin.buffer, sys.stdout.buffer, open(sys.argv[1], "a")
    kept = {}

    def send(header, payloads=()):
        head = json.dumps({**header, "payloads": [len(p) for p in payloads]}).encode()
        out.write(sizes.pack(4 + len(head) + sum(map(len, payloads)), len(head)) + head + b"".join(payloads))
        out.flush()

    while True:
        first = asked.read(sizes.size)
        if len(first) < sizes.size:
            break
        length, head_length = sizes.unpack(first)
        body = asked.read(length - 4)
        header = json.loads(body[:head_length])
        payloads, at = [], head_length
        for size in header["payloads"]:
            payloads.append(body[at:at + size]); at += size
        log.write(json.dumps({"job": header["job"], "keys": header.get("keys"), "sizes": header["payloads"],
                              "scene": header.get("scene")}) + "\\n"); log.flush()
        if header["job"] == "forget":
            kept.clear(); send({"id": header["id"], "ok": True}); continue
        keys = header.get("keys") or [None] * len(payloads)
        missing = [k for k, p in zip(keys, payloads) if k is not None and not p and k not in kept]
        kept.update({k: p for k, p in zip(keys, payloads) if k is not None and p})
        if missing:
            send({"id": header["id"], "ok": True, "missing": missing}); continue
        scene = header["scene"]
        pixel = bytes(round(255 * min(max(c, 0), 1)) for c in scene["background"]) + b"\\xff"
        send({"id": header["id"], "ok": True, "width": scene["width"], "height": scene["height"], "seconds": 0.01},
             [pixel * (scene["width"] * scene["height"])])
""")


def _box(low: tuple[float, float, float], high: tuple[float, float, float]) -> bytes:
    """A box's mesh buffer, made without the kernel: twelve triangles, each side a face of its own."""
    x0, y0, z0 = low
    x1, y1, z1 = high
    corners = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    triangles, faces = [], []
    for ordinal, (a, b, c, d) in enumerate(quads, 1):
        triangles += [(a, b, c), (a, c, d)]
        faces += [ordinal, ordinal]
    mesh, _uvs = buffer(corners, np.array(triangles), faces=np.array(faces))
    return mesh.to_bytes()


IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
STRUCTURE = {
    "prototypes": [{"key": "big", "color": [0.8, 0.1, 0.1, 1.0]},
                   {"key": "small", "color": [0.1, 0.2, 0.9, 1.0], "faceColors": {"1": [0.0, 1.0, 0.0, 1.0]}}],
    "instances": [{"prototype": 0, "matrix": IDENTITY},
                  {"prototype": 1, "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 30, 0, 0, 1]},
                  {"prototype": 1, "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 60, 0, 0, 1]}],
}


class CoreSceneTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="render-core-"))
        self.log = folder / "asked.jsonl"
        program = folder / "viewcore"
        (folder / "server.py").write_text(SERVER, encoding="utf-8")
        program.write_text(f"#!/bin/sh\nexec {json.dumps(sys.executable)} {json.dumps(str(folder / 'server.py'))} "
                           f"{json.dumps(str(self.log))}\n", encoding="utf-8")
        program.chmod(0o755)
        self.core = Core(str(program))
        self.addCleanup(self.core.stop)
        self.buffers = {"big": _box((0, 0, 0), (20, 20, 20)), "small": _box((0, 0, 0), (6, 6, 6))}
        self.scene = CoreScene(Path("boxes.xbf"), self.buffers, size=(64, 48), structure=json.loads(json.dumps(STRUCTURE)),
                               core=self.core)

    def asked(self) -> list[dict]:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_the_scene_is_what_occt_is_handed(self) -> None:
        self.scene.show({"mode": "solid"})
        self.scene.frame("iso")
        scene, payloads, keys = self.scene.describe()
        self.assertEqual((scene["width"], scene["height"], scene["format"]), (64, 48, "rgba"))
        self.assertEqual(scene["background"], [float(c) for c in finish.linear(BACKGROUND)])
        self.assertEqual(keys[:2], ["mesh:big", "mesh:small"], "each part's mesh once, by its key, in the order drawn")
        self.assertEqual([payloads[i] for i in scene["meshes"]], [self.buffers["big"], self.buffers["small"]])
        self.assertEqual(len(payloads[scene["matrices"]]), 3 * 128, "every instance placed, sixteen doubles each")
        faces = [item for item in scene["draw"] if "faces" in item]
        edges = [item for item in scene["draw"] if "edges" in item]
        # The big box one group; each small box its own faces and its painted one.
        self.assertEqual([(item["faces"], item["matrix"], "ranges" in item) for item in faces],
                         [(0, 0, False), (1, 1, True), (1, 1, True), (1, 2, True), (1, 2, True)])
        painted = faces[2]
        self.assertEqual(painted["ranges"], [[0, 6]], "face 1's two triangles")
        made = finish.finish((0.0, 1.0, 0.0, 1.0), None)
        self.assertEqual((painted["shading"], painted["color"], painted["roughness"], painted["offset"]),
                         ("pbr", [float(c) for c in made["color"]], made["roughness"], list(EDGES_WIN_OFFSET)))
        self.assertTrue(edges and all(item["layer"] == "default" for item in edges))
        self.assertEqual(scene["light"]["environment"]["intensity"], LOOK.environment.intensity)
        self.assertEqual(scene["camera"]["projection"], "orthographic")
        self.assertAlmostEqual(scene["camera"]["height"], self.scene.camera["scale"])
        self.assertNotIn("clip", scene)

    def test_x_ray_wireframe_and_hidden_line_are_their_looks(self) -> None:
        self.scene.show({"mode": "xray"})
        self.scene.frame("iso")
        scene = self.scene.describe()[0]
        self.assertIn("phong", scene)
        self.assertNotIn("light", scene)
        self.assertTrue(all(item["layer"] == "topmost" for item in scene["draw"] if "edges" in item))
        self.assertTrue(all(item["shading"] == "phong" for item in scene["draw"] if "faces" in item))
        self.scene.show({"mode": "wireframe"})
        self.assertFalse(any("faces" in item for item in self.scene.describe()[0]["draw"]))
        self.scene.show({"mode": "hidden-line"})
        hidden = [item for item in self.scene.describe()[0]["draw"] if "faces" in item]
        self.assertTrue(all(item["shading"] == "unlit" and item["color"] == [float(c) for c in finish.linear(BACKGROUND)]
                            for item in hidden))

    def test_a_clip_cuts_with_one_plane_and_caps_each_instance_shown(self) -> None:
        self.scene.hidden = frozenset({2})
        self.scene.show({"mode": "solid", "clip": {"axis": "x", "at": 10}})
        self.scene.frame("iso")
        scene = self.scene.describe()[0]
        self.assertEqual(scene["clip"], [-1.0, 0.0, 0.0, 10.0], "the lower side of x = 10 kept")
        self.assertEqual([item["matrix"] for item in scene["draw"] if "cap" in item], [0, 1], "a hidden part has none")
        self.scene.show({"mode": "wireframe", "clip": {"axis": "x", "at": 10}})
        self.assertFalse(any("cap" in item for item in self.scene.describe()[0]["draw"]))

    def test_the_grid_and_the_ink_are_triangles_and_lines_of_their_own(self) -> None:
        self.scene.show({"mode": "solid"})
        self.scene.frame("iso")
        self.scene.grid(True)
        # A stroke as wide as 6 pixels of a 900-pixel viewer is a ribbon; one under a pixel and a half, a GL line.
        self.scene.annotate({"marks": [{"kind": "stroke", "color": "#ff00ff", "width": 6 * 900 / 48,
                                        "points": [0, 0, 20, 20, 20, 20]},
                                       {"kind": "stroke", "color": "#0000ff", "width": 1, "points": [0, 0, 0, 20, 0, 0]}]})
        draw = self.scene.describe()[0]["draw"]
        grid = [item for item in draw if "triangles" in item and "texture" in item]
        self.assertEqual((len(grid), grid[0]["clip"], grid[0]["blend"]), (1, False, True))
        ribbon = [item for item in draw if "triangles" in item and item.get("layer") == "top"]
        self.assertEqual(ribbon[0]["color"], [*finish.linear("#ff00ff"), 1.0])
        lines = [item for item in draw if "lines" in item]
        self.assertEqual((len(lines), lines[0]["layer"]), (1, "top"))
        self.assertAlmostEqual(lines[0]["width"], 48 / 900, msg="its pen as heavy against this picture as on the viewer")

    def test_a_mesh_crosses_the_pipe_once_and_again_when_the_server_lost_it(self) -> None:
        self.scene.show({"mode": "shaded"})
        self.scene.frame("iso")
        frame = self.scene.canvas.frame()
        self.assertEqual(frame.shape, (48, 64, 3))
        self.assertTrue((frame == np.rint(np.array(drawing._linear(BACKGROUND)) * 255).astype(np.uint8)).all())
        self.scene.canvas.frame()
        self.core.job({"job": "forget"}, [])
        self.scene.canvas.frame()
        renders = [line for line in self.asked() if line["job"] == "render"]
        meshes = [line["sizes"][:2] for line in renders]
        self.assertTrue(all(meshes[0]), "sent")
        self.assertEqual(meshes[1], [0, 0], "named only")
        self.assertEqual((meshes[2], renders[2].get("keys")[:2]), ([0, 0], ["mesh:big", "mesh:small"]))
        self.assertTrue(all(meshes[3]), "sent again once the server said it lacked them")

    def test_what_the_core_does_not_draw_yet_is_refused_in_one_line(self) -> None:
        from cad.engine.render.drawing import Held as Drawing
        from cad.engine.render.service import Held, holder

        held = Held(Path("boxes.xbf"), core=self.core)
        self.addCleanup(held.close)
        held.hold({**json.loads(json.dumps(STRUCTURE)), "version": "1"}, self.buffers)
        data, report = held.draw(Still({"mode": "solid"}, size=(64, 48)))
        self.assertEqual((data[:8], report["renderer"]), (b"\x89PNG\r\n\x1a\n", "core"))
        with self.assertRaises(SnapshotRefused) as refused:
            held.scenes[False].preview_look(path_trace=16)
        self.assertEqual(str(refused.exception), NOT_YET["path-trace"])
        drawing = holder(Path("plan.dxf"), self.core)
        self.assertIsInstance(drawing, Drawing)
        self.assertIs(drawing.core, self.core, "a DXF's drawing is the core's too")
        for said in NOT_YET.values():
            self.assertNotIn("\n", said)


class NoKernelTest(unittest.TestCase):
    def test_the_core_path_loads_no_kernel(self) -> None:
        """A render process on the WebAssembly kernel runs in a Python with no kernel: its scene is made with every
        kernel module refused."""
        script = textwrap.dedent(f"""
            import json, sys
            sys.path[:0] = {json.dumps([str(Path(__file__).resolve().parents[5]), str(SRC)])}
            class Refuse:
                def find_spec(self, name, path=None, target=None):
                    if name.partition(".")[0] in ("OCP", "build123d"):
                        raise ImportError("no kernel here: " + name)
            sys.meta_path.insert(0, Refuse())
            from pathlib import Path
            from tests.python.packages.cad.engine.test_render_core import STRUCTURE, _box
            from cad.engine.render import service
            from cad.engine.render.core import CoreScene
            scene = CoreScene(Path("boxes.xbf"), {{"big": _box((0, 0, 0), (2, 2, 2)), "small": _box((0, 0, 0), (1, 1, 1))}},
                              size=(32, 24), structure=STRUCTURE, core=None)
            scene.show({{"mode": "solid", "clip": {{"axis": "z"}}}})
            scene.frame("35:20", "perspective")
            scene.grid(True)
            print(len(scene.describe()[0]["draw"]), sorted(m for m in sys.modules if m.startswith(("OCP", "build123d"))))
        """)
        done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120,
                              env={**os.environ, "PYTHONPATH": ""})
        self.assertEqual(done.returncode, 0, done.stderr)
        count, loaded = done.stdout.strip().split(" ", 1)
        self.assertGreater(int(count), 5)
        self.assertEqual(loaded, "[]")


if __name__ == "__main__":
    unittest.main()
