import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cad_server import language
from cad_server.settings import write_section


class LanguageTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.path = tmp / "state" / "settings.json"

    def test_automatic_until_the_person_chooses_and_automatic_again_forgets_the_choice(self) -> None:
        self.assertEqual(language.read(path=self.path), {"locale": None})
        write_section("analytics", {"choice": "off"}, path=self.path)  # another feature's settings, untouched
        self.assertEqual(language.change({"locale": "zh-TW"}, path=self.path), {"locale": "zh-TW"})
        self.assertEqual(language.read(path=self.path), {"locale": "zh-TW"})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")),
                         {"analytics": {"choice": "off"}, "language": {"locale": "zh-TW"}})
        self.assertEqual(language.change({"locale": None}, path=self.path), {"locale": None})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"analytics": {"choice": "off"}})

    def test_only_a_known_locale_or_automatic_is_kept(self) -> None:
        for choice in ({"locale": "fr"}, {"locale": "zh"}, {"locale": 1}, {}, {"locale": "en", "x": 1}, ["en"], None):
            with self.assertRaises(ValueError, msg=repr(choice)):
                language.change(choice, path=self.path)
        self.assertFalse(self.path.exists())
        # A locale a later version left, or a broken file, reads as Automatic.
        write_section("language", {"locale": "fr"}, path=self.path)
        self.assertEqual(language.read(path=self.path), {"locale": None})
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(language.read(path=self.path), {"locale": None})


if __name__ == "__main__":
    unittest.main()
