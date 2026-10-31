"""The state folder an earlier release kept, adopted (``cad.engine.places.adopt``, ``adopt_earlier``).

0.9 names its state folder ``texttocad`` where 0.8's was ``cadgen``: what this release keeps of the earlier
one -- the person's settings, the installations' records less ``current``, the engines' records with the page
token, the documents' records and Recents, setup's receipt and the install channels -- moves into its own,
each once, and the rest stays. Every folder here is a temporary one: the platform's places are stood in
for, never read.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import places

EVERYTHING = ["settings.json", "installations", "engines", "documents", "recents", "install-receipt.json",
              "install-channels.json"]


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
        self.earlier, self.folder = self.root / "cadgen", self.root / "texttocad"
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
        self.assertEqual(sorted(path.name for path in (self.folder / "installations").iterdir()), ["0.8.4.json"],
                         "an earlier release's current is not this one's to keep")
        self.assertEqual((self.folder / "settings.json").read_text(encoding="utf-8"), '{"telemetry": {"choice": "off"}}',
                         "a no stays a no")
        self.assertEqual((self.folder / "engines" / "token").read_text(encoding="utf-8"), "t" * 43)
        self.assertTrue((self.folder / "documents" / "a" / "document.json").is_file())
        self.assertTrue((self.folder / "recents" / "thumbnails" / "a.png").is_file())
        # Moved, never copied: the locks and what was noted and not sent stay behind, alone.
        self.assertEqual(sorted(path.name for path in self.earlier.iterdir()),
                         ["install.lock", "settings.lock", "telemetry-spool.jsonl"])
        self.assertEqual(places.adopt(self.earlier, self.folder), [], "once")

    def test_what_this_release_already_keeps_is_never_replaced(self) -> None:
        write(self.folder / "settings.json", '{"telemetry": {"notifiedAt": 1}}')
        write(self.folder / "engines" / "token", "n" * 43)
        self.assertEqual(places.adopt(self.earlier, self.folder),
                         [name for name in EVERYTHING if name not in ("settings.json", "engines")])
        self.assertEqual((self.folder / "engines" / "token").read_text(encoding="utf-8"), "n" * 43)
        self.assertEqual((self.folder / "settings.json").read_text(encoding="utf-8"), '{"telemetry": {"notifiedAt": 1}}')
        self.assertTrue((self.earlier / "engines" / "token").is_file(), "left where it was")

    def test_no_earlier_folder_moves_nothing_and_makes_nothing(self) -> None:
        self.assertEqual(places.adopt(self.root / "absent", self.folder), [])
        self.assertFalse(self.folder.exists())


class AdoptEarlierTest(Folders):
    """Where no state folder is named: the platform's places, stood in for."""

    def platform(self, names: tuple[str, str]) -> Path:
        return {places.STATE: self.folder, places.EARLIER_STATE: self.earlier}[names]

    def test_the_earlier_folder_is_adopted_once_whatever_this_release_wrote_first(self) -> None:
        # A told command (`cad doctor`'s notice) may have written this release's folder first.
        write(self.folder / "telemetry-batches.jsonl")
        with mock.patch.object(places, "_platform_state", side_effect=self.platform), \
                mock.patch.dict(os.environ, {"CAD_STATE_DIR": ""}):
            self.assertEqual(places.adopt_earlier(), EVERYTHING)
            self.assertEqual(places.state_dir(), self.folder)
            write(self.earlier / "installations" / "0.8.5.json", "{}")  # written by 0.8 after the move
            self.assertEqual(places.adopt_earlier(), [], "this release's folder has it: never again")
        self.assertFalse((self.folder / "installations" / "0.8.5.json").exists())

    def test_what_earlier_releases_left_is_looked_for_in_their_own_folders_or_the_ones_named(self) -> None:
        with mock.patch.object(places, "_platform_state", side_effect=self.platform), \
                mock.patch.dict(os.environ, {"CAD_STATE_DIR": "", "CAD_CACHE_DIR": "", "XDG_CACHE_HOME": str(self.root),
                                             "LOCALAPPDATA": str(self.root)}):
            self.assertEqual(places.earlier_state_dir(), self.earlier)
            self.assertEqual(places.earlier_cache_dir(), self.root / "cadgen")
            self.assertEqual(places.cache_dir(), self.root / "texttocad")
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


if __name__ == "__main__":
    unittest.main()
