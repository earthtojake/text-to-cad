import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cadgen import features
from cadgen.settings import write_section


class FeaturesTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.path = tmp / "state" / "settings.json"

    def test_every_feature_is_on_until_the_person_turns_it_off_and_the_choice_is_kept_beside_the_others(self) -> None:
        self.assertEqual(features.read(path=self.path), {"quickEdit": True})
        write_section("analytics", {"choice": "off"}, path=self.path)  # another feature's settings, untouched
        self.assertEqual(features.change({"quickEdit": False}, path=self.path), {"quickEdit": False})
        self.assertEqual(features.read(path=self.path), {"quickEdit": False})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")),
                         {"analytics": {"choice": "off"}, "features": {"quickEdit": False}})
        self.assertEqual(features.change({"quickEdit": True}, path=self.path), {"quickEdit": True})
        self.assertEqual(features.change({}, path=self.path), {"quickEdit": True})  # nothing to change: a read

    def test_only_a_known_feature_turned_on_or_off_is_kept(self) -> None:
        for choices in ({"quickEdit": "no"}, {"quickEdit": 0}, {"somethingElse": False}, ["quickEdit"], None):
            with self.assertRaises(ValueError, msg=repr(choices)):
                features.change(choices, path=self.path)
        self.assertFalse(self.path.exists())
        # A value a later version left, or a broken file, reads as the default.
        write_section("features", {"quickEdit": "off", "retired": False}, path=self.path)
        self.assertEqual(features.read(path=self.path), {"quickEdit": True})
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(features.read(path=self.path), {"quickEdit": True})


if __name__ == "__main__":
    unittest.main()
