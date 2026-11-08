"""An ``@implicit`` model through an engine of the test's own: the document the engine holds of a field.

The field is a plate with a hole, 40 x 20 x 6 mm at a 1 mm cell, so every fact is the construction's. The
run's report says the sample (its triangles, its thinnest wall -- the plate's 6 mm -- and its bounds), the engine's cache holds the GLB from the moment
the build registers, the verbs of ``cad.implicit`` read it as a mesh file (an STL's extents, the summary's
triangles, a manufacturing check), the page's API names its kind and streams its source, a body that runs
to the same field samples nothing again, a changed cell samples anew under a new version, a cell too coarse
for the wall is refused by name, and a restarted engine answers it ``held`` from its file. The engine runs in folders of the test's own
(``engine_daemon.isolate``); the snapshot runs only under a display (CI's cadjoint job has none).
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import shutil
import tempfile
import textwrap
import time
import unittest
import urllib.request
from pathlib import Path

from tests.python.support import engine_daemon

MODEL = """
from cadjoint.construction import Solid
from cadjoint.sdf.boolean import Difference

from cad import implicit
from cad.cadjoint import field

CELL = {cell}


@implicit
def block():
    {line}
    plate = Solid.box(size=(20.0, 10.0, 3.0), position=(0.0, 0.0, 3.0), name="plate")
    hole = Solid.cylinder(radius=3.0, height=5.0, position=(0.0, 0.0, 3.0), name="hole")
    return field(Difference(plate, hole, smoothness=0.0), cell=CELL)


if __name__ == "__main__":
    block()
"""


class ImplicitDocumentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        engine_daemon.isolate(cls.addClassCleanup)
        cls.folder = Path(tempfile.mkdtemp(prefix="implicit-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.script = cls.folder / "block.py"

    def _write(self, cell: float = 1.0, line: str = "pass") -> None:
        self.script.write_text(textwrap.dedent(MODEL.format(cell=cell, line=line)), encoding="utf-8")
        os.utime(self.script, ns=(time.time_ns(), time.time_ns()))

    def _build(self, ok: bool = True) -> dict:
        from cad.engine import api

        report = api.build_script(self.script, ["block"]).models[0]
        if ok:
            self.assertTrue(report["ok"], report.get("error"))
        return report

    def test_the_document_its_verbs_its_page_and_its_life(self) -> None:
        import numpy as np

        import cad
        from cad.engine import api, said
        from cad.engine.formats.stl import read_stl
        from cad_server.engine.cli import summary_text

        self._write()
        report = self._build()
        ident = report["id"]
        self.assertEqual(report["type"], "implicit")
        self.assertEqual(report["document"]["format"], "glb")
        self.assertTrue(report["document"]["sampled"])
        delta = report["delta"]
        self.assertGreater(delta["triangles"]["now"], 100)
        np.testing.assert_allclose(delta["bounds"]["now"], (40.0, 20.0, 6.0), atol=0.05)
        self.assertAlmostEqual(delta["wall_mm"]["now"], 6.0, delta=0.05)
        self.assertAlmostEqual(delta["wall_cells"]["now"], 6.0, delta=0.05)
        line = said._delta(delta)
        self.assertRegex(line, r"^\n  triangles [\d,]+ . wall 6 cells \(6 mm\) . bounds 40 . 20 . 6 mm$")
        # The engine's file of it, from the moment it is built.
        cached = Path(os.environ["CAD_CACHE_DIR"]) / "documents" / ident / "document.glb"
        self.assertTrue(cached.is_file())
        self.assertEqual(cached.read_bytes()[:4], b"glTF")
        self.assertEqual(cached.stat().st_size, report["document"]["bytes"])

        # Its verbs read that file as a mesh file: an export's extents, the summary, a check.
        stl = self.folder / "block.stl"
        written = cad.implicit.export(ident, stl)
        self.assertEqual([row.kind for row in written], ["stl"])
        corners = read_stl(stl).reshape(-1, 3)
        np.testing.assert_allclose(corners.max(axis=0) - corners.min(axis=0), (40.0, 20.0, 6.0), atol=0.05)
        summary = cad.implicit.inspect(ident, query="summary")["summary"]
        self.assertEqual((summary["type"], summary["name"], summary["triangles"]), ("implicit", "block", delta["triangles"]["now"]))
        np.testing.assert_allclose(summary["bounds"], (40.0, 20.0, 6.0), atol=0.05)
        self.assertAlmostEqual(summary["volume"], 40 * 20 * 6 - 3.1416 * 9 * 6, delta=60)
        self.assertEqual((summary["wall_mm"], summary["wall_cells"]), (delta["wall_mm"]["now"], delta["wall_cells"]["now"]))
        self.assertIn("wall        6 cells (6 mm)", summary_text(summary).splitlines())
        self.assertEqual(cad.implicit.inspect(ident)["key"], report["closure"]["key"])
        checked = cad.implicit.dfm(ident, process="printing")
        self.assertTrue(checked.ok, checked.findings)
        with self.assertRaisesRegex(ValueError, "is a model's document id, not a .stl file"):
            cad.stl.export(ident, self.folder / "x.glb")
        handle = api.Document("block", self.script, report, self.folder)
        with self.assertRaisesRegex(TypeError, "is an implicit document"):
            handle.shape  # noqa: B018 - the property is the subject

        # The page's API: its kind, its exports, and its source, the GLB itself.
        url = report["url"]
        base, _, token = url.partition(f"/{ident}?token=")
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        opener.open(url, timeout=30).read()  # the link admits the session
        envelope = json.loads(opener.open(f"{base}/api/v1/documents/{ident}", timeout=30).read())
        self.assertEqual((envelope["kind"], envelope["api"], envelope["exports"]),
                         ("implicit", f"/api/v1/documents/implicit/{ident}", ["stl", "threemf", "glb"]))
        with opener.open(f"{base}/api/v1/documents/implicit/{ident}/source", timeout=30) as answer:
            self.assertEqual(answer.headers.get("content-type"), "model/gltf-binary")
            self.assertEqual(answer.read(), cached.read_bytes())
        rows = json.loads(opener.open(f"{base}/api/v1/documents", timeout=30).read())["documents"]
        self.assertEqual([(row["kind"], row["record"]) for row in rows if row["id"] == ident], [("implicit", "model")])
        version = envelope["version"]
        # The page's URL for the source carries the version as a query, which the route ignores; its version
        # route answers at once without ``after`` and waits (briefly here) when asked after the current one.
        with opener.open(f"{base}/api/v1/documents/implicit/{ident}/source?v={version}", timeout=30) as answer:
            self.assertEqual(answer.read()[:4], b"glTF")
        asked = json.loads(opener.open(f"{base}/api/v1/documents/{ident}/version", timeout=30).read())
        self.assertEqual(asked.get("version"), version)
        started = time.monotonic()
        waited = json.loads(opener.open(f"{base}/api/v1/documents/{ident}/version?after={version}&wait=1", timeout=30).read())
        self.assertEqual(waited.get("version"), version)
        self.assertGreaterEqual(time.monotonic() - started, 0.8)
        # The viewer's export of it: a job through the HTTP API, from the row the page shows.
        epoch = json.loads(opener.open(f"{base}/api/v1/exports", timeout=30).read())["epoch"]
        body = json.dumps({"requestId": "implicit-export-test-0001", "epoch": epoch, "format": "stl",
                           "source": {"doc": ident, "revision": envelope["entry"]["hash"]}}).encode()
        posted = urllib.request.Request(f"{base}/api/v1/documents/{ident}/exports", data=body, method="POST",
                                        headers={"content-type": "application/json", "x-cad-viewer": "1"})
        job = json.loads(opener.open(posted, timeout=30).read())
        deadline = time.monotonic() + 60
        while job["state"] not in ("ready", "failed", "expired") and time.monotonic() < deadline:
            time.sleep(0.2)
            job = json.loads(opener.open(f"{base}/api/v1/exports/{job['id']}", timeout=30).read())
        self.assertEqual(job["state"], "ready", job)
        with opener.open(f"{base}/api/v1/exports/{job['id']}/file", timeout=30) as answer:
            exported = answer.read()
        self.assertEqual(len(exported), 84 + 50 * delta["triangles"]["now"], "a binary STL of the sample's triangles")
        # Quick Edit's prompt names ``cad model snapshot <id>`` for any document: a model's verbs take an implicit
        # document's id too, and route it to its document (ids are opaque; a handle is refused by its type).
        cad.model.export(ident, self.folder / "by_model.stl")
        self.assertEqual((self.folder / "by_model.stl").stat().st_size, stl.stat().st_size)
        self.assertEqual(cad.model.inspect(ident, query="summary")["summary"]["type"], "implicit")

        # A body that runs again to the same field samples nothing: the bytes stand, under the new closure.
        self._write(line='print("ran")')
        again = self._build()
        self.assertFalse(again["document"]["sampled"])
        self.assertEqual(again["document"]["digest"], report["document"]["digest"])
        self.assertEqual(json.loads(opener.open(f"{base}/api/v1/documents/{ident}", timeout=30).read())["version"], version,
                         "the same bytes: no page fetches them again")
        # A finer cell is another field: sampled again, a new version, more triangles.
        self._write(cell=0.8, line='print("ran")')
        finer = self._build()
        self.assertTrue(finer["document"]["sampled"])
        self.assertNotEqual(finer["document"]["digest"], report["document"]["digest"])
        self.assertGreater(finer["delta"]["triangles"]["now"], delta["triangles"]["now"])
        self.assertEqual(finer["delta"]["triangles"]["was"], delta["triangles"]["now"])
        self.assertIn(" wall 7.5 cells (", said._delta(finer["delta"]))
        self.assertNotEqual(json.loads(opener.open(f"{base}/api/v1/documents/{ident}", timeout=30).read())["version"], version)

        # A cell too coarse for the wall: the build fails by name, and the document stays the last one.
        self._write(cell=4.0)
        refused = self._build(ok=False)
        self.assertFalse(refused["ok"])
        self.assertIn("the thinnest wall is 1.4 cells (6 mm at a 4 mm cell), and a wall needs about four: use a cell "
                      "of 1.5 mm or less, or thicken it", refused.get("error", ""))
        self._write(cell=0.8, line='print("ran")')
        self.assertFalse(self._build()["document"]["sampled"])

        # A snapshot, where a display is there to draw on: by its own type, and by ``cad model snapshot`` as Quick
        # Edit's prompt names it.
        if os.environ.get("DISPLAY"):
            drawn = cad.implicit.snapshot(ident, self.folder / "review.png")
            self.assertTrue(drawn.path.is_file())
            self.assertTrue(cad.model.snapshot(ident, self.folder / "review2.png").path.is_file())

        # Stopped and asked again: held from its file, every verb answering, nothing run.
        self.assertTrue(api.stop())
        state = api.inspect(ident, query="summary")["summary"]["state"]
        self.assertEqual(state["state"], "held")
        self.assertIn("disk", str(state.get("held")))
        cad.implicit.export(ident, self.folder / "again.stl")
        self.assertTrue((self.folder / "again.stl").is_file())
        # And a fresh worker that runs the body to the same field takes the file's bytes, sampling nothing.
        taken = self._build()
        self.assertFalse(taken["document"]["sampled"])


if __name__ == "__main__":
    unittest.main()
