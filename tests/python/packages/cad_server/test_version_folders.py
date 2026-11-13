"""The server follows the library's folders (``cad.engine.places``): a process of an installed version keeps
its settings, telemetry spool, feed cache, update record, channels, documents' records, Recents, page token
and port in ``versions/<version>/data``, and its kernel and ``cad run`` environments in its code; a process
with no version -- this suite's own, under ``CAD_STATE_DIR`` and ``CAD_CACHE_DIR`` -- keeps the layout of 0.11.10 and
earlier. A version is faked by its code marker in a temporary device; nothing is installed or started."""

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
from cad_server import auto_updates, settings, updates
from cad_server._internal import base, channel, extras
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
        installation = base.Installation.here()
        return {"settings": settings.settings_path(), "feed": updates._cache(), "attempt": auto_updates._record_path(),
                "channels": channel._record_path(), "registry": registry.current().state.root,
                "documents": registry.current().cache.root, "records": records.current().root_folder,
                "recents": RecentStore().root, "kernel": base.where(installation).parent,
                "extras": extras.where(installation, ["numpy"]).parent}

    def test_no_version_keeps_the_layout_before_0_12(self) -> None:
        self.assertEqual(self.paths(), {
            "settings": self.state / "settings.json", "feed": self.state / "versions.json",
            "attempt": self.state / "update-automatic.json", "channels": self.state / "install-channels.json",
            "registry": self.state, "documents": self.cache, "records": self.state, "recents": self.state / "recents",
            "kernel": self.cache / "base", "extras": self.cache / "base"})
        self.assertIn("prefix", base._inputs(base.Installation.here()), "one cache folder for every installation")

    def test_a_version_keeps_its_data_and_environments_in_its_own_folder(self) -> None:
        data, code = self.version / "data", self.version / "code"
        with mock.patch.object(sys, "prefix", str(self.server)):
            self.assertEqual(self.paths(), {
                "settings": data / "settings.json", "feed": data / "versions.json",
                "attempt": data / "update-automatic.json", "channels": data / "install-channels.json",
                "registry": data, "documents": data / "cache", "records": data, "recents": data / "recents",
                "kernel": code / "base", "extras": code / "base"})
            self.assertNotIn("prefix", base._inputs(base.Installation.here()), "one installation a version")

    def test_what_a_version_writes_lands_in_its_folder_alone(self) -> None:
        with mock.patch.object(sys, "prefix", str(self.server)):
            settings.update_section("language", lambda _kept: {"locale": "en"})
            auto_updates.attempt(X, now=1.0)
            self.assertEqual(channel.remember("dev"), "dev")
            held = registry.current()
            self.assertTrue(held.make_token("t" * 43))
            held.put_engine("engine", {"port": 3246, "schema": registry.ENGINE_SCHEMA})
            self.assertEqual(held.token(), "t" * 43)
        written = sorted(str(path.relative_to(self.state)) for path in self.state.rglob("*") if path.is_file())
        self.assertTrue(written, "something was written")
        outside = [path for path in written if not path.startswith(f"versions{os.sep}{X}{os.sep}")]
        self.assertEqual(outside, [], "a version writes nothing of its own outside its folder")
        self.assertFalse(self.cache.exists(), "nor in the cache folder of 0.11.10 and earlier")
        for name in ("settings.json", "update-automatic.json", "install-channels.json", "engines/token",
                     "engines/engine.json"):
            self.assertTrue((self.version / "data" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
