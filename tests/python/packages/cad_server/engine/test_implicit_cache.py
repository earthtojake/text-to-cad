"""The daemon's cache holds a document's bytes in the format they are: an xbf's as ``document.xbf``, an
implicit document's GLB as ``document.glb`` (``cache.Cache``), one file per document, found again by either name
after a restart, the record's ``cache`` naming the format."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_sources

add_sources()

from cad_server.engine.cache import Cache  # noqa: E402
from cad_server.engine.registry import Registry  # noqa: E402

IDENT = "c0dd17f5-181f-5a66-a604-5394190acea3"
GLB = b"glTF" + bytes(20)  # begins as a GLB does: what the cache reads the format from


class _Models:
    def __init__(self, held: Registry) -> None:
        self.held = held

    def registry(self) -> Registry:
        return self.held

    def row(self, ident: str):
        return None

    def _working(self, worker) -> bool:
        return False


class CacheFormatTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="implicit-cache-"))
        self.addCleanup(shutil.rmtree, folder, True)
        self.registry = Registry(folder / "state", folder / "cache")
        self.cache = Cache(_Models(self.registry))
        self.registry.put({"schema": 1, "id": IDENT, "kind": "model", "root": str(folder), "home": "m.py", "entry": "part",
                           "namespace": str(folder), "name": "part", "revision": "r1", "built": 1.0, "format": "glb"})

    def test_a_glb_is_written_as_document_glb_and_found_again_by_that_name(self) -> None:
        self.assertEqual(Cache.inside(IDENT), f"documents/{IDENT}/document.xbf")
        self.assertEqual(Cache.inside(IDENT, "glb"), f"documents/{IDENT}/document.glb")
        self.assertEqual((Cache.format_of(GLB), Cache.format_of(b"xbf bytes")), ("glb", "xbf"))
        self.cache.write_now(IDENT, "r1", GLB)
        path = self.registry.cache.path(f"documents/{IDENT}/document.glb")
        self.assertEqual(path.read_bytes(), GLB)
        self.assertFalse(self.registry.cache.path(f"documents/{IDENT}/document.xbf").exists())
        self.assertEqual(self.registry.get(IDENT)["cache"], {"revision": "r1", "bytes": len(GLB), "format": "glb"})
        self.assertTrue(self.cache.current(IDENT, "r1"))
        self.assertEqual(self.cache.read(IDENT), GLB)
        self.assertEqual(self.cache.file(IDENT), path)
        # A fresh cache (a restart) indexes the file by either name, and reads the format from the record.
        again = Cache(_Models(self.registry))
        self.assertEqual(again.documents(), [IDENT])
        self.assertEqual(again.format(IDENT), "glb")
        self.assertIsNotNone(again.found(IDENT))
        self.assertEqual(again.file(IDENT), path)
        # The other format written over it replaces the file: one file per document.
        self.registry.update(IDENT, lambda found: {**found, "revision": "r2"})
        self.cache.write_now(IDENT, "r2", b"xbf bytes")
        self.assertFalse(path.exists())
        self.assertEqual(self.registry.cache.path(f"documents/{IDENT}/document.xbf").read_bytes(), b"xbf bytes")
        self.assertEqual(self.cache.format(IDENT), "xbf")

    def test_a_file_of_another_size_than_the_record_says_is_not_cached(self) -> None:
        self.cache.write_now(IDENT, "r1", GLB)
        self.registry.cache.path(f"documents/{IDENT}/document.glb").write_bytes(GLB + b"more")
        self.assertIsNone(Cache(_Models(self.registry)).found(IDENT))
        self.assertIsNone(Cache(_Models(self.registry)).file(IDENT))


if __name__ == "__main__":
    unittest.main()
