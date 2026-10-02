import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cadgen.settings import read_section, write_section


class SettingsTest(unittest.TestCase):
    def test_each_feature_writes_only_its_own_section(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = tmp / "state" / "settings.json"
        self.assertEqual(read_section("analytics", path=path), {})  # nothing kept yet
        write_section("analytics", {"choice": "off"}, path=path)
        write_section("viewer", {"layout": "list"}, path=path)  # another app, another setting
        self.assertEqual(read_section("analytics", path=path), {"choice": "off"})
        write_section("viewer", None, path=path)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"analytics": {"choice": "off"}})
        path.write_text("{not json", encoding="utf-8")  # a broken file reads as no settings, and the next write mends it
        self.assertEqual(read_section("analytics", path=path), {})
        write_section("analytics", {"choice": "on"}, path=path)
        self.assertEqual(read_section("analytics", path=path), {"choice": "on"})


if __name__ == "__main__":
    unittest.main()
