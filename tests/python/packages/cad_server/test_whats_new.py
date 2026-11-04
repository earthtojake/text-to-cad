"""What's new: which releases' notes the person has seen, in their settings, and whether a device was
updated (shown the notes) or is a new person's (shown nothing new), decided once."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cad_server import whats_new
from cad_server.settings import write_section


class WhatsNewTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.path = tmp / "state" / "settings.json"

    def kept(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_a_new_person_has_seen_everything_up_to_their_first_release(self) -> None:
        answer = whats_new.read(path=self.path, release="0.11", installed=lambda: ["0.11.0", "0.12.0-dev.1"])
        self.assertEqual(answer, {"seen": ["0.11"], "release": "0.11"})
        self.assertEqual(self.kept(), {"whats_new": {"seen": ["0.11"]}})
        # Decided once: an earlier release's record found later changes nothing.
        self.assertEqual(whats_new.read(path=self.path, release="0.11", installed=lambda: ["0.10.3"])["seen"], ["0.11"])

    def test_settings_an_earlier_release_wrote_without_the_field_are_an_update(self) -> None:
        write_section("telemetry", {"notifiedAt": 1.0, "notice": 1}, path=self.path)  # 0.10's settings, untouched
        answer = whats_new.read(path=self.path, release="0.11", installed=lambda: ["0.10.3", "0.11.0"])
        self.assertEqual(answer, {"seen": [], "release": "0.11"})
        self.assertEqual(self.kept(), {"telemetry": {"notifiedAt": 1.0, "notice": 1}, "whats_new": {"seen": []}})

    def test_a_dismissal_is_added_to_what_is_kept_and_never_taken_from_it(self) -> None:
        whats_new.read(path=self.path, release="0.11", installed=lambda: ["0.10.3"])
        self.assertEqual(whats_new.change({"seen": ["0.11"], "release": "0.11"}, path=self.path, release="0.11"),
                         {"seen": ["0.11"], "release": "0.11"})
        # A view that read before the dismissal and puts back what it read loses nothing.
        self.assertEqual(whats_new.change({"seen": []}, path=self.path, release="0.12")["seen"], ["0.11"])
        whats_new.change({"seen": ["0.13", "0.11"]}, path=self.path, release="0.13")
        self.assertEqual(self.kept(), {"whats_new": {"seen": ["0.11", "0.13"]}})
        for choice in ({"seen": "0.11"}, {"seen": ["v0.11"]}, {"seen": [11]}, {}, {"seen": [], "x": 1}, ["0.11"], None):
            with self.assertRaises(ValueError, msg=repr(choice)):
                whats_new.change(choice, path=self.path, release="0.13")

    def test_what_a_later_release_left_is_kept_and_a_broken_section_reads_as_none_seen(self) -> None:
        write_section("whats_new", {"seen": ["0.11", "nonsense", 3], "later": True}, path=self.path)
        self.assertEqual(whats_new.read(path=self.path, release="0.11", installed=list)["seen"], ["0.11"])
        whats_new.change({"seen": ["0.12"]}, path=self.path, release="0.12")
        self.assertEqual(self.kept(), {"whats_new": {"seen": ["0.11", "0.12"], "later": True}})

    def test_settings_that_cannot_be_kept_show_nothing(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.mkdir()  # settings.json a folder: neither read nor written
        self.assertEqual(whats_new.read(path=self.path, release="0.11", installed=lambda: ["0.10.3"]),
                         {"seen": ["0.11"], "release": "0.11"})
        whats_new.settle(path=self.path, release="0.11")  # never fails what it rides on

    def test_a_release_is_named_by_its_minor(self) -> None:
        self.assertEqual([whats_new.minor(v) for v in ("0.11.2", "0.11.0-dev.3", "0.11.0rc1", "1.0", "dev", None)],
                         ["0.11", "0.11", "0.11", "1.0", None, None])


if __name__ == "__main__":
    unittest.main()
