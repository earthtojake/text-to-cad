"""The state folder an earlier release kept, adopted (``cad.engine.places.adopt``, ``adopt_earlier``).

0.10 names its state folder ``cad`` where 0.8's was ``cadgen``: what this release keeps of the earlier one
-- the person's settings, the documents' records and Recents, and setup's receipt -- moves into its own, each
once, and the rest stays -- 0.8's installations' records, its engines' records and page token, its install
channels --, with the person's telemetry no for the earlier release still installed. Every folder here is a
temporary one: the platform's places are stood in for, never read.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import places

EVERYTHING = ["settings.json", "documents", "recents", "install-receipt.json"]


def write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class Folders(unittest.TestCase):
    """An earlier release's state folder, as 0.8 left it, and where this release's goes."""

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="places-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.earlier, self.folder = self.root / "cadgen", self.root / "cad"
        write(self.earlier / "settings.json", '{"telemetry": {"choice": "off"}}')
        write(self.earlier / "installations" / "0.8.4.json", '{"version": "0.8.4"}')
        write(self.earlier / "installations" / "current", "0.8.4")
        write(self.earlier / "engines" / "token", "t" * 43)
        write(self.earlier / "engines" / "engine.json", '{"port": 3245}')
        write(self.earlier / "documents" / "a" / "document.json", "{}")
        write(self.earlier / "recents" / "thumbnails" / "a.png")
        write(self.earlier / "install-receipt.json", "{}")
        write(self.earlier / "install-channels.json", "{}")
        for kept in ("settings.lock", "install.lock", "telemetry-spool.jsonl"):
            write(self.earlier / kept)


class AdoptTest(Folders):
    def test_what_this_release_keeps_moves_and_the_rest_stays(self) -> None:
        self.assertEqual(places.adopt(self.earlier, self.folder), EVERYTHING)
        self.assertEqual((self.folder / "settings.json").read_text(encoding="utf-8"), '{"telemetry": {"choice": "off"}}',
                         "a no stays a no")
        self.assertTrue((self.folder / "documents" / "a" / "document.json").is_file())
        self.assertTrue((self.folder / "recents" / "thumbnails" / "a.png").is_file())
        self.assertEqual((self.folder / "install-receipt.json").read_text(encoding="utf-8"), "{}")
        # Moved, never copied: what only 0.8 runs by -- its installations' records, its engines' with the page
        # token, its install channels --, the locks and what was noted and not sent stay behind, and the
        # person's no, for the earlier release still installed, which would take settings it found missing for
        # never told.
        self.assertEqual(sorted(path.name for path in self.earlier.iterdir()),
                         ["engines", "install-channels.json", "install.lock", "installations", "settings.json",
                          "settings.lock", "telemetry-spool.jsonl"])
        self.assertEqual((self.earlier / "engines" / "token").read_text(encoding="utf-8"), "t" * 43)
        self.assertEqual((self.earlier / "installations" / "current").read_text(encoding="utf-8"), "0.8.4")
        self.assertFalse((self.folder / "engines").exists() or (self.folder / "installations").exists())
        self.assertEqual(json.loads((self.earlier / "settings.json").read_text(encoding="utf-8")),
                         {"telemetry": {"choice": "off"}})
        self.assertEqual(places.adopt(self.earlier, self.folder), [], "once")

    def test_only_a_no_stays_behind_and_without_the_deletion_it_owes(self) -> None:
        for kept, behind in (({"choice": "off", "decidedAt": 2, "forget": ["id"]}, {"choice": "off", "decidedAt": 2}),
                             ({"choice": "on", "decidedAt": 2}, None), ({"notice": 1, "notifiedAt": 1}, None)):
            with self.subTest(kept=kept):
                for folder in (self.earlier, self.folder):
                    (folder / "settings.json").unlink(missing_ok=True)
                write(self.earlier / "settings.json", json.dumps({"telemetry": kept, "language": "de"}))
                places.adopt(self.earlier, self.folder)
                self.assertEqual(json.loads((self.folder / "settings.json").read_text(encoding="utf-8")),
                                 {"telemetry": kept, "language": "de"}, "the settings move whole")
                left = self.earlier / "settings.json"
                self.assertEqual(json.loads(left.read_text(encoding="utf-8")) if left.exists() else None,
                                 {"telemetry": behind} if behind else None)

    def test_what_this_release_already_keeps_is_never_replaced(self) -> None:
        write(self.folder / "settings.json", '{"telemetry": {"notifiedAt": 1}}')
        write(self.folder / "recents" / "thumbnails" / "b.png", "mine")
        self.assertEqual(places.adopt(self.earlier, self.folder),
                         [name for name in EVERYTHING if name not in ("settings.json", "recents")])
        self.assertEqual(sorted(path.name for path in (self.folder / "recents" / "thumbnails").iterdir()), ["b.png"])
        self.assertEqual((self.folder / "settings.json").read_text(encoding="utf-8"), '{"telemetry": {"notifiedAt": 1}}')
        self.assertTrue((self.earlier / "recents" / "thumbnails" / "a.png").is_file(), "left where it was")

    def test_no_earlier_folder_moves_nothing_and_makes_nothing(self) -> None:
        self.assertEqual(places.adopt(self.root / "absent", self.folder), [])
        self.assertFalse(self.folder.exists())


class AdoptEarlierTest(Folders):
    """Where no state folder is named: the platform's places, stood in for."""

    def platform(self, names: tuple[str, str]) -> Path:
        return {places.EARLIER_STATE: self.earlier}[names]

    def setUp(self) -> None:
        super().setUp()
        local = mock.patch.object(places, "_local_state", return_value=self.root)  # this release's: root/cad
        local.start()
        self.addCleanup(local.stop)

    def test_the_earlier_folder_is_adopted_once_whatever_this_release_wrote_first(self) -> None:
        # A told command (`cad doctor`'s notice) may have written this release's folder first.
        write(self.folder / "telemetry-batches.jsonl")
        with mock.patch.object(places, "_platform_state", side_effect=self.platform), \
                mock.patch.dict(os.environ, {"CAD_STATE_DIR": ""}):
            self.assertEqual(places.adopt_earlier(), EVERYTHING)
            self.assertEqual(places.state_dir(), self.folder)
            write(self.earlier / "documents" / "b" / "document.json", "{}")  # written by 0.8 after the move
            self.assertEqual(places.adopt_earlier(), [], "this release's folder has it: never again")
        self.assertFalse((self.folder / "documents" / "b").exists())

    def test_what_earlier_releases_left_is_looked_for_in_their_own_folders_or_the_ones_named(self) -> None:
        with mock.patch.object(places, "_platform_state", side_effect=self.platform), \
                mock.patch.dict(os.environ, {"CAD_STATE_DIR": "", "CAD_CACHE_DIR": "", "XDG_CACHE_HOME": str(self.root),
                                             "LOCALAPPDATA": str(self.root)}):
            self.assertEqual(places.earlier_state_dir(), self.earlier)
            self.assertEqual(places.earlier_cache_dir(), self.root / "cadgen")
            self.assertEqual(places.cache_dir(), self.root / "cad")
        named = {"CAD_STATE_DIR": str(self.root / "s"), "CAD_CACHE_DIR": str(self.root / "c")}
        with mock.patch.dict(os.environ, named):
            self.assertEqual((places.earlier_state_dir(), places.earlier_cache_dir()), (self.root / "s", self.root / "c"))

    def test_a_named_state_folder_adopts_nothing(self) -> None:
        named = self.root / "named"
        with mock.patch.object(places, "_platform_state", side_effect=self.platform), \
                mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(named)}):
            self.assertEqual(places.adopt_earlier(), [])
            self.assertEqual(places.state_dir(), named)
        self.assertFalse(self.folder.exists())
        self.assertFalse(named.exists())
        self.assertTrue((self.earlier / "installations" / "current").is_file())


class WindowsTest(Folders):
    """On Windows 0.10.0 kept its folders in the local application data, which an app package (the Claude
    desktop app's) virtualizes for every process it starts; this release keeps them in the user's own
    folder, as Linux does, and moves what 0.10.0 kept there once -- 0.10.0's folder before 0.8's, whose
    settings are only the telemetry no it kept behind (#759)."""

    def setUp(self) -> None:
        super().setUp()
        self.home = self.root / "home"
        self.appdata = self.root / "AppData" / "Local"
        self.ten = self.appdata / "cad-state"
        (self.earlier / "settings.json").write_text('{"telemetry": {"choice": "off"}}', encoding="utf-8")
        for name in ("documents", "recents", "install-receipt.json"):
            path = self.earlier / name
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        write(self.ten / "settings.json", '{"telemetry": {"choice": "off"}, "language": "zh-TW"}')
        write(self.ten / "engines" / "token", "u" * 43)
        write(self.ten / "engines" / "engine.json", '{"port": 3246, "schema": 3}')
        write(self.ten / "documents" / "a" / "document.json", "{}")
        write(self.ten / "recents" / "thumbnails" / "a.png")
        write(self.ten / "install-receipt.json", "{}")
        write(self.ten / "install-channels.json", "{}")
        write(self.ten / "installations" / "current", "0.10.0")
        write(self.ten / "releases" / "0.10.0" / "Scripts" / "python.exe")
        write(self.appdata / "cad" / "documents" / "a" / "document.xbf", "xbf")
        write(self.appdata / "cad" / "base" / "0123" / "pyvenv.cfg")
        environment = {"CAD_STATE_DIR": "", "CAD_CACHE_DIR": "", "CAD_ENGINE_DIR": "", "XDG_STATE_HOME": "",
                       "XDG_CACHE_HOME": "", "HOME": str(self.home), "USERPROFILE": str(self.home),
                       "LOCALAPPDATA": str(self.appdata)}
        for patch in (mock.patch.object(places, "WINDOWS", True), mock.patch("sys.platform", "win32"),
                      mock.patch.object(places, "_platform_state", side_effect=lambda names: self.earlier),
                      mock.patch.dict(os.environ, environment)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_the_folders_are_the_users_own_out_of_the_local_application_data(self) -> None:
        self.assertEqual(places.state_dir(), self.home / ".local" / "state" / "cad")
        self.assertEqual(places.cache_dir(), self.home / ".cache" / "cad")
        self.assertEqual(Path(places.default_engine_dir()), self.home / ".local" / "state" / "cad-engine")
        self.assertEqual((places.appdata_state_dir(), places.appdata_cache_dir()), (self.ten, self.appdata / "cad"))
        self.assertEqual(places.appdata_engine_dir(), Path(tempfile.gettempdir()) / "cad-engine")
        with mock.patch.dict(os.environ, {"CAD_STATE_DIR": "s", "CAD_CACHE_DIR": "c", "CAD_ENGINE_DIR": "e"}):
            self.assertEqual((places.appdata_state_dir(), places.appdata_cache_dir(), places.appdata_engine_dir()),
                             (None, None, None))

    def test_what_0_10_kept_moves_once_with_the_page_token_its_port_and_its_documents_bytes(self) -> None:
        state, cache = places.state_dir(), places.cache_dir()
        self.assertEqual(places.adopt_earlier(), [*places.APPDATA_ADOPTED, "documents"])
        self.assertEqual(json.loads((state / "settings.json").read_text(encoding="utf-8")),
                         {"telemetry": {"choice": "off"}, "language": "zh-TW"}, "0.10's whole settings, not 0.8's no")
        self.assertEqual((state / "engines" / "token").read_text(encoding="utf-8"), "u" * 43, "every link still works")
        self.assertEqual(json.loads((state / "engines" / "engine.json").read_text(encoding="utf-8"))["port"], 3246)
        self.assertTrue((state / "documents" / "a" / "document.json").is_file())
        self.assertEqual((cache / "documents" / "a" / "document.xbf").read_text(encoding="utf-8"), "xbf")
        # What 0.10.0 runs by stays for it -- its installations, its release, its base --, and its telemetry no.
        self.assertTrue((self.ten / "installations" / "current").is_file())
        self.assertTrue((self.ten / "releases" / "0.10.0" / "Scripts" / "python.exe").is_file())
        self.assertTrue((self.appdata / "cad" / "base" / "0123" / "pyvenv.cfg").is_file())
        self.assertEqual(json.loads((self.ten / "settings.json").read_text(encoding="utf-8")),
                         {"telemetry": {"choice": "off"}})
        self.assertFalse((state / "installations").exists() or (cache / "base").exists())
        self.assertEqual(places.adopt_earlier(), [], "once")


if __name__ == "__main__":
    unittest.main()
