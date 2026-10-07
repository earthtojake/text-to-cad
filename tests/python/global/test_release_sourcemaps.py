"""The pages' source maps a release uploads to PostHog: scripts/release/sourcemaps.py.

Publish Release gathers, from each page's build, every chunk a crash on that page can name with its
map, so a release whose crashes PostHog could not show the source of has to fail there, before PyPI.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.python.support.paths import REPO_ROOT

spec = importlib.util.spec_from_file_location("sourcemaps", REPO_ROOT / "scripts/release/sourcemaps.py")
sourcemaps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sourcemaps)

VIEWER_ID = "0de4d024-c159-4f6d-b15a-cc4ef7a6856d"
APP_ID = "5105e120-ad57-4fd0-9af1-d64b4ab0ab1c"


class SourceMapsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def chunk(self, directory: str, name: str, debug_id: str, *, map_id: str | None = None) -> None:
        self.write(f"{directory}/{name}", f"export const a=1;\n//# debugId={debug_id}\n")
        self.write(f"{directory}/{name}.map", json.dumps({"version": 3, "mappings": "AAAA", "sources": ["a.ts"],
                                                          "debugId": map_id or debug_id}))

    def pages(self) -> None:
        self.write("apps/web/dist/index.html", f'<head><script>globalThis.__cadChunkIds={{"index-A.js":"{VIEWER_ID}"}}</script>')
        self.chunk("apps/web/dist/assets", "index-A.js", VIEWER_ID)
        # A worker's map, which no crash on the page can name: left out.
        self.write("apps/web/dist/assets/worker-B.js.map", json.dumps({"version": 3, "mappings": ""}))
        self.write("apps/mcp/dist/index.html", f'const SOURCES={{}},IMPORTS={{}},IDS={{"index-C.js":"{APP_ID}"}},ENTRY="index-C.js";')
        self.chunk("apps/mcp/dist/sourcemaps", "index-C.js", APP_ID)

    def test_every_chunk_a_page_can_name_is_gathered_with_its_map_and_zipped(self) -> None:
        self.pages()
        out = self.root / "out"
        self.assertEqual(sourcemaps.collect(out, root=self.root), {"viewer": 1, "cad-app": 1})
        self.assertEqual(sorted(path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file()),
                         ["cad-app/index-C.js", "cad-app/index-C.js.map", "viewer/index-A.js", "viewer/index-A.js.map"])
        sourcemaps.archive(out, self.root / "maps.zip")
        with zipfile.ZipFile(self.root / "maps.zip") as archive:
            self.assertIn("viewer/index-A.js.map", archive.namelist())

    def test_a_page_whose_maps_posthog_could_not_use_stops_the_release(self) -> None:
        self.pages()
        self.chunk("apps/mcp/dist/sourcemaps", "index-C.js", APP_ID, map_id=VIEWER_ID)  # the map names another chunk
        with self.assertRaisesRegex(sourcemaps.Unfit, "index-C.js names debug id"):
            sourcemaps.collect(self.root / "out", root=self.root)
        self.pages()
        (self.root / "apps/web/dist/assets/index-A.js.map").unlink()  # a named chunk without its map
        with self.assertRaisesRegex(sourcemaps.Unfit, "or its map is not there"):
            sourcemaps.collect(self.root / "out", root=self.root)
        self.pages()
        self.write("apps/web/dist/index.html", "<head>")  # a page its build wrote no table into
        with self.assertRaisesRegex(sourcemaps.Unfit, "names no chunk's debug id"):
            sourcemaps.collect(self.root / "out", root=self.root)


if __name__ == "__main__":
    unittest.main()
