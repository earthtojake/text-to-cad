"""The regular display modes' look (``render/look.py``): one record, served at ``GET /api/look``
as the viewer reads it with its environment image at ``GET /api/look/environment``, and the copy
of it the viewer's tests parse (``packages/core/src/lib/xbf/__fixtures__/look.json``) the same
record; the image decodes as three's HDRLoader decodes it, and maps onto the cube map OCCT reads."""

from __future__ import annotations

import json
import math
import unittest
import urllib.request
from pathlib import Path

import numpy as np

from cadgen.engine.render.finish import cube_faces, decode_hdr, sample
from cadgen.engine.render.look import LOOK
from cadgen.engine.serve import Server

FIXTURE = Path(__file__).resolve().parents[5] / "packages" / "core" / "src" / "lib" / "xbf" / "__fixtures__" / "look.json"
REGENERATE = ("regenerate it: PYTHONPATH=packages/cadgen/src python -c \"import json; from cadgen.engine.render.look "
              "import LOOK; print(json.dumps(LOOK.json(), indent=2))\" > packages/core/src/lib/xbf/__fixtures__/look.json")


class LookTest(unittest.TestCase):
    def test_the_engine_serves_the_record_and_its_environment_to_a_loopback_page(self) -> None:
        server = Server(port=0, mesh_mode="inline")
        server.start()
        self.addCleanup(server.stop)
        page = {"Origin": "http://localhost:5173"}
        with urllib.request.urlopen(urllib.request.Request(f"{server.url}/api/look", headers=page), timeout=30) as answer:
            self.assertEqual(answer.headers["Access-Control-Allow-Origin"], "http://localhost:5173")
            served = json.loads(answer.read())
        self.assertEqual(served, LOOK.json())
        url = f"{server.url}{served['environment']['url']}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=page), timeout=30) as answer:
            self.assertEqual(answer.read(), LOOK.environment_path.read_bytes())

    def test_the_viewers_copy_is_the_record(self) -> None:
        self.assertEqual(json.loads(FIXTURE.read_text(encoding="utf-8")), LOOK.json(), REGENERATE)

    def test_the_environment_is_the_studio_in_the_documents_frame(self) -> None:
        image = decode_hdr(LOOK.environment_path.read_bytes())
        self.assertEqual(image.shape, (256, 512, 3))
        # The key card hangs where the studio hangs it (photographicStudioRig.js: -0.35, -1, 1.5) at
        # radiance 8, an RGBE value decoded exactly; the floor under the model is dim.
        key = np.array([-0.35, -1.0, 1.5]) / math.sqrt(0.35 ** 2 + 1 + 1.5 ** 2)
        self.assertAlmostEqual(float(sample(image, key[None])[0, 0]), 8.0, places=5)
        self.assertLess(float(sample(image, np.array([[0.0, 0.0, -1.0]]))[0, 0]), 0.5)
        # OCCT reads a cube map's direction c as the document's (c.z, c.x, c.y): its +Y face is up.
        faces = cube_faces(image, 8)
        self.assertGreater(float(faces[:, 16:24].mean()), float(faces[:, 24:32].mean()), "+Y (up) outshines -Y (down)")

    def test_the_record_names_every_regular_mode_once(self) -> None:
        served = LOOK.json()
        self.assertEqual(list(served["modes"]), ["solid", "shaded", "parts", "xray", "hidden-line", "wireframe"])
        self.assertEqual(LOOK.mode("xray").opacity, 0.22)
        self.assertEqual(LOOK.edge("feature"), "#253443")
        self.assertEqual(served["tone"], "clamp", "OCCT's raster applies no tone curve")
        self.assertEqual(served["brdf"], "occt", "the surfaces answer light as OCCT's PBR program does")


if __name__ == "__main__":
    unittest.main()
