"""A tool library file: the user's tools written once, found beside the job file or the part, kept when an operation
uses them or ``only`` picks them, and refused with the file and entry named."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cadgen._internal.cam.job import CamJobError, parse_job

LIBRARY = {"name": "shop", "tools": [
    {"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 20, "stickout_mm": 30},
    {"id": "T4", "type": "drill", "diameter_mm": 5},
    {"id": "T9", "type": "flat", "diameter_mm": 2, "number": 1},
]}


def job(tools, *operations) -> dict:
    return {"machine": {"kind": "mill", "post": "grbl", "max_rpm": 24000, "rapid_mm_min": 5000, "tool_change_s": 10,
                        "spindle_spinup_s": 1},
            "material": "aluminum-6061", "stock": {"kind": "box", "margin_mm": [2, 2, 1]}, "tools": tools,
            "setups": [{"id": "top", "operations": list(operations) or [{"op": "face", "tool": "T1"}]}]}


class ToolLibrary(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="cam-tools-")
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)

    def write(self, name: str, data) -> Path:
        path = self.directory / name
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return path

    def refuse(self, expected: str, raw, **kwargs) -> str:
        with self.assertRaises(CamJobError) as caught:
            parse_job(raw, **kwargs)
        self.assertIn(expected, str(caught.exception))
        return str(caught.exception)

    def test_a_library_beside_the_job_file_gives_the_tools_its_operations_use(self):
        self.write("shop.json", LIBRARY)
        job_file = self.write("part.cam.json", job("shop.json"))
        parsed = parse_job(str(job_file))
        # T9 posts as T1 too, but it is not the job's (no operation uses it), so the numbers do not clash.
        self.assertEqual(["T1"], [tool.id for tool in parsed.tools])
        self.assertEqual(30.0, parsed.tool("T1").stickout_mm)
        self.assertFalse([entry for entry in parsed.assumed if entry["key"].startswith("tools.")])

    def test_beside_the_part_a_bare_list_and_only_keeps_a_tool_no_operation_uses(self):
        self.write("rack.json", LIBRARY["tools"][:2])
        parsed = parse_job(job([{"library": "rack.json", "only": ["T4"]}, {"id": "T5", "type": "spot", "diameter_mm": 6}]),
                           part_dir=self.directory)
        self.assertEqual(["T1", "T4", "T5"], sorted(tool.id for tool in parsed.tools))

    def test_a_used_tool_that_posts_as_another_number_is_still_refused(self):
        self.write("shop.json", LIBRARY)
        self.refuse("tools 'T1' and 'T9' both post as T1", job("shop.json", {"op": "face", "tool": "T1"},
                                                              {"op": "face", "tool": "T9"}), part_dir=self.directory)

    def test_every_refusal_names_the_file_and_the_entry(self):
        self.write("shop.json", LIBRARY)
        self.write("broken.json", '{"tools": [')
        self.write("odd.json", {"tools": [{"id": "T1", "type": "endmill", "diameter_mm": 6}]})
        self.write("extra.json", {"tools": LIBRARY["tools"], "vendor": "x"})
        cases = {
            "two tools are called 'T1' (shop.json tools[0] and tools[1])":
                job([{"library": "shop.json"}, {"id": "T1", "type": "flat", "diameter_mm": 3}]),
            "tools[0].only[] (a tool of shop.json) is 'T5'; use one of T1, T4, T9":
                job([{"library": "shop.json", "only": ["T5"]}]),
            "tools[0].library: no tool library at": job("missing.json"),
            "the tool library broken.json is not valid JSON": job("broken.json"),
            "odd.json tools[0].type is 'endmill'": job("odd.json"),
            "unknown key 'vendor'": job("extra.json"),
            "tools[0].only lists tool ids from shop.json": job([{"library": "shop.json", "only": "T1"}]),
            "unknown key 'tools'": job([{"library": "shop.json", "tools": []}]),
        }
        for words, raw in cases.items():
            with self.subTest(words=words):
                self.refuse(words, raw, part_dir=self.directory)


if __name__ == "__main__":
    unittest.main()
