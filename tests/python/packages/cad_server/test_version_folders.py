"""The server follows the library's folders (``cad.engine.places``): a process of an installed version keeps
its settings, telemetry spool, feed cache, documents' records, Recents, page token
and port in ``versions/<version>/data``; a process with no version -- this suite's own, under ``CAD_STATE_DIR`` and ``CAD_CACHE_DIR`` -- keeps the layout of 0.11.10 and
earlier. Every process keeps its kernel and ``cad run`` environments in the one cache folder, keyed by the
release and never by where cad is installed (test_base.py's). A version is faked by its code marker in a temporary device; nothing is installed or started."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import places
from cad.engine import records
from cad_server import settings, updates
from cad_server.engine import registry
from cad_server.viewer.recents import RecentStore

X = "0.12.0"


class ServerFoldersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="server-version-folders-")))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state, self.cache = self.root / "state", self.root / "cache"
        environment = {"CAD_STATE_DIR": str(self.state), "CAD_ENGINE_DIR": str(self.root / "engines"),
                       "CAD_CACHE_DIR": str(self.cache), "CAD_INSTALLATION_VERSION": ""}
        for patch in (mock.patch.dict(os.environ, environment), mock.patch.object(places, "HOME", None),
                      mock.patch.object(registry, "FACTORY", None)):
            patch.start()
            self.addCleanup(patch.stop)
        places._versioned.cache_clear()
        self.addCleanup(places._versioned.cache_clear)
        self.version = self.state / "versions" / X
        server = self.version / "code" / "server"
        (server / "bin").mkdir(parents=True)
        for script in ("python", "cad"):
            (server / "bin" / script).write_text("", encoding="utf-8")
        (self.version / "code" / places.VERSION_MARKER).write_text(json.dumps(
            {"schema": places.VERSION_SCHEMA, "version": X, "python": str(server / "bin" / "python"),
             "cad": str(server / "bin" / "cad"), "prefix": str(server)}), encoding="utf-8")
        self.server = server

    def paths(self) -> dict[str, Path]:
        return {"settings": settings.settings_path(), "feed": updates._cache(),
                "registry": registry.current().state.root,
                "documents": registry.current().cache.root, "records": records.current().root_folder,
                "recents": RecentStore().root}

    def test_no_version_keeps_the_layout_before_0_12(self) -> None:
        self.assertEqual(self.paths(), {
            "settings": self.state / "settings.json", "feed": self.state / "versions.json",
            "registry": self.state, "documents": self.cache, "records": self.state, "recents": self.state / "recents"})

    def test_a_version_keeps_its_data_and_environments_in_its_own_folder(self) -> None:
        data = self.version / "data"
        with mock.patch.object(sys, "prefix", str(self.server)):
            self.assertEqual(self.paths(), {
                "settings": data / "settings.json", "feed": data / "versions.json",
                "registry": data, "documents": data / "cache", "records": data, "recents": data / "recents"})

    def test_what_a_version_writes_lands_in_its_folder_alone(self) -> None:
        with mock.patch.object(sys, "prefix", str(self.server)):
            settings.update_section("language", lambda _kept: {"locale": "en"})
            held = registry.current()
            self.assertTrue(held.make_token("t" * 43))
            held.put_engine("engine", {"port": 3246, "schema": registry.ENGINE_SCHEMA})
            self.assertEqual(held.token(), "t" * 43)
        written = sorted(str(path.relative_to(self.state)) for path in self.state.rglob("*") if path.is_file())
        self.assertTrue(written, "something was written")
        outside = [path for path in written if not path.startswith(f"versions{os.sep}{X}{os.sep}")]
        self.assertEqual(outside, [], "a version writes nothing of its own outside its folder")
        self.assertFalse(self.cache.exists(), "nor in the cache folder of 0.11.10 and earlier")
        for name in ("settings.json", "engines/token",
                     "engines/engine.json"):
            self.assertTrue((self.version / "data" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
