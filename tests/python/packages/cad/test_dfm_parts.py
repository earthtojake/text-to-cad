"""What is kept of one part's measurement (``cad._internal.dfm.parts``): a part's result found by the part as it
stands and what measured it, written whole, served only as what its name says, never one that could come out
otherwise; and the checks that keep them (sheet, CNC and the recogniser's features), each measuring only the parts
it holds no result of, its report the one it makes of every part measured afresh. Every part is built here, and
every store is a folder of the test's own."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

GEOMETRY = "0123456789abcdef0123456789abcdef"


class KeptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="dfm-parts-"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def kept(self, code: str = "c0de") -> object:
        from cad._internal.dfm.parts import Kept

        return Kept(self.root / "parts", code, {"OCP": "7.8.1"})

    def test_a_result_is_found_by_its_part_and_what_measured_it_and_by_nothing_else(self) -> None:
        from cad._internal.dfm.parts import CNC, FEATURES

        kept = self.kept()
        rest = {"part": {"name": "plate", "owner": "plate", "matrix": [1.0] + [0.0] * 15}, "options": {"axes": 3}}
        kept.keep(CNC, GEOMETRY, rest, {"items": [1, 2]})
        self.assertEqual(kept.get(CNC, GEOMETRY, rest), {"items": [1, 2]})
        self.assertEqual(self.kept().get(CNC, GEOMETRY, json.loads(json.dumps(rest))), {"items": [1, 2]},
                         "found again by another process, its rest read back")
        for other in ({**rest, "options": {"axes": 5}}, {**rest, "part": {**rest["part"], "owner": "other"}}):
            self.assertIsNone(kept.get(CNC, GEOMETRY, other))
        self.assertIsNone(kept.get(FEATURES, GEOMETRY, rest), "another kind")
        self.assertIsNone(kept.get(CNC, GEOMETRY[::-1], rest), "another geometry")
        self.assertIsNone(self.kept("other").get(CNC, GEOMETRY, rest), "other code")
        self.assertEqual(kept.counts[CNC], {"reused": 1, "measured": 3, "kept": 1})
        (path,) = (self.root / "parts" / CNC / GEOMETRY[:2]).iterdir()
        self.assertRegex(path.name, rf"^{GEOMETRY}-[0-9a-f]{{20}}\.json$")

    def test_an_entry_that_does_not_read_as_its_name_says_is_removed_and_never_served(self) -> None:
        from cad._internal.dfm.parts import CNC

        kept = self.kept()
        rest = {"part": {"name": "plate"}}
        kept.keep(CNC, GEOMETRY, rest, [1])
        (path,) = (self.root / "parts" / CNC / GEOMETRY[:2]).iterdir()
        entry = json.loads(path.read_text(encoding="utf-8"))
        for broken in (b"{", json.dumps({**entry, "rest": {"part": {"name": "other"}}}).encode(),
                       json.dumps({**entry, "format": 0}).encode()):
            with self.subTest(broken=broken[:20]):
                path.write_bytes(broken)
                self.assertIsNone(kept.get(CNC, GEOMETRY, rest))
                self.assertFalse(path.exists())

    def test_nothing_is_kept_that_could_come_out_otherwise_or_is_no_plain_data(self) -> None:
        from cad._internal.dfm.parts import CNC, Kept, unrepeatable

        kept = self.kept()
        for result in ({"walls": {"error": "x: MemoryError: "}}, [{"recognition": {"repeatable": False}}], {1, 2}):
            with self.subTest(result=result):
                kept.keep(CNC, GEOMETRY, {"n": str(result)}, result)
        self.assertFalse((self.root / "parts").exists())
        self.assertFalse(unrepeatable({"recognition": {"repeatable": True}, "walls": {"error": "x: ValueError: y"}}))
        self.assertEqual(Kept.settled({"a": (1, 2)}), {"a": [1, 2]}, "as it reads back from disk")
        Kept(None, "c0de").keep(CNC, GEOMETRY, {}, [1])  # no folder: nothing, and no error
        blocked = self.root / "blocked"
        blocked.write_text("", encoding="utf-8")
        Kept(blocked / "parts", "c0de").keep(CNC, GEOMETRY, {}, [1])  # a folder that takes no write

    def test_a_process_keeps_its_parts_where_its_code_is_its_own_and_for_sheet_and_cnc_alone(self) -> None:
        from cad._internal.dfm.parts import FOLDER, Kept
        from cad.engine import _measuring

        said = {"code": "c", "dfm": {"cnc": "cnc-code", "sheet": "sheet-code"}, "libraries": {"OCP": "7"}}
        with mock.patch.object(_measuring, "measuring", return_value=said), \
                mock.patch.dict("os.environ", {"CAD_CACHE_DIR": str(self.root)}):
            cnc = Kept.of("cnc")
            self.assertEqual((cnc.folder, cnc.code, cnc.libraries), (self.root / FOLDER, "cnc-code", {"OCP": "7"}))
            self.assertIsNone(Kept.of("molding"))
            self.assertIsNone(Kept.of("printing"))
        edited = {**said, "dfm": {"cnc": "cnc-code" + _measuring.EDITED}}
        with mock.patch.object(_measuring, "measuring", return_value=edited):
            self.assertIsNone(Kept.of("cnc"), "code edited since its process loaded it is no other process's")


if __name__ == "__main__":
    unittest.main()
