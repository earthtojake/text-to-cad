"""The PCB benchmark's pure helpers (``scripts/bench/pcb_fetch.py``, ``pcb_bench.py``): the corpus manifest and
the task file checked, a fetched file's path and hash, the seeded edits on a tiny board's text, and the checks'
logic on facts written by hand. Nothing here downloads, runs KiCad or reads the corpus: AGENTS.md runs only the
benchmarks' helpers in a test runner."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.python.support.paths import REPO_ROOT
from tests.python.support.tmp_root import temporary_directory

BENCH = REPO_ROOT / "scripts" / "bench"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, BENCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pcb_fetch = _load("pcb_fetch")
pcb_bench = _load("pcb_bench")

SHA = "a" * 64


def upstream(**overrides):
    project = {"name": "tiny", "tier": "small", "kind": "upstream", "repo": "someone/boards", "ref": "v1",
               "commit": "0123456789abcdef0123456789abcdef01234567", "root": "hw/tiny", "board": "tiny.kicad_pcb",
               "schematic": "tiny.kicad_sch", "licence": "CERN-OHL-P-2.0",
               "licence_file": {"path": "LICENSE", "sha256": SHA, "bytes": 10}, "kicad_format": 20241229,
               "copper_layers": 2, "footprints": 3, "bytes": 30,
               "files": [{"path": name, "sha256": SHA, "bytes": 10}
                         for name in ("tiny.kicad_pcb", "tiny.kicad_pro", "tiny.kicad_sch")]}
    project.update(overrides)
    return project


# A board with each kind of item the edits touch, in KiCad 6's and KiCad 8's spellings: a text with a
# parenthesis, an escaped quote and a backslash before a letter (KiCad writes newlines as \n) must not end it.
BOARD = """(kicad_pcb (version 20241229) (generator "pcbnew")
	(net 0 "")
	(net 1 "GND")
	(net 2 "/SIG")
	(footprint "R_0603" (layer "F.Cu") (uuid "f0000000-0000-0000-0000-000000000001") (at 10 20 90)
		(property "Reference" "R1" (at 0 -1.4 90) (uuid "f0000000-0000-0000-0000-0000000000a1"))
		(pad "1" smd rect (at -0.8 0 90) (size 0.8 0.9) (layers "F.Cu") (net 2 "/SIG") (uuid "f0000000-0000-0000-0000-0000000000b1"))
	)
	(gr_text "a (note) with \\"quotes\\" and a \\\\ and \\n a newline" (at 0 0) (layer "F.SilkS") (uuid "e0000000-0000-0000-0000-000000000001"))
	(segment (start 0 0) (end 1 0) (width 0.2) (layer "F.Cu") (net 2) (tstamp 10000000-0000-0000-0000-000000000001))
	(segment (start 1 0) (end 2 0) (width 0.2) (layer "F.Cu") (net 1) (uuid "10000000-0000-0000-0000-000000000002"))
	(via (at 2 0) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "/SIG") (uuid "20000000-0000-0000-0000-000000000001"))
)
"""


class ManifestTest(unittest.TestCase):
    def test_the_committed_manifest_and_tasks_are_well_formed(self):
        manifest = json.loads(pcb_fetch.MANIFEST.read_text(encoding="utf-8"))
        tasks = json.loads(pcb_bench.TASKS.read_text(encoding="utf-8"))
        self.assertEqual(pcb_fetch.problems(manifest), [])
        self.assertEqual(pcb_bench.task_problems(tasks, manifest), [])

    def test_each_problem_is_named(self):
        self.assertEqual(pcb_fetch.problems({"projects": [upstream()]}), [])
        big = upstream(files=[{"path": "tiny.kicad_pcb", "sha256": SHA, "bytes": 11 * 1024 * 1024},
                              *upstream()["files"][1:]])
        cases = {
            "tiny: licence CC-BY-NC-SA-4.0 forbids commercial use (NC)": upstream(licence="CC-BY-NC-SA-4.0"),
            "tiny: licence CC-BY-ND-4.0 forbids derivatives (ND)": upstream(licence="CC-BY-ND-4.0"),
            "tiny: no licence": upstream(licence=""),
            "tiny: licence Proprietary is not one of the open licences": upstream(licence="Proprietary"),
            "tiny: `commit` is a full 40-character": upstream(commit="v1.0"),
            "tiny: `tiny.kicad_pcb`'s sha256 is 64 lowercase hex digits": upstream(
                files=[{"path": "tiny.kicad_pcb", "sha256": "ABC", "bytes": 10}, *upstream()["files"][1:]]),
            "tiny: `../escape.kicad_sch` is not a safe relative path": upstream(
                files=[*upstream()["files"], {"path": "../escape.kicad_sch", "sha256": SHA, "bytes": 0}]),
            "tiny: `root` is a safe relative folder": upstream(root="/abs"),
            "tiny: `tiny.kicad_pcb` is 11534336 bytes, over the 10 MB cap": big,
            "tiny: `board` is one of its files": upstream(board="other.kicad_pcb"),
            "tiny: the board's .kicad_pro is one of its files": upstream(
                files=[upstream()["files"][0], upstream()["files"][2]]),
            "tiny: `bytes` is 31, its files add to 30": upstream(bytes=31),
            "tiny: a licence file inside the project's root is one of its files": upstream(
                licence_file={"path": "hw/tiny/LICENCE", "sha256": SHA, "bytes": 1}),
            "tiny: a second project of this name": [upstream(), upstream()],
        }
        for expected, projects in cases.items():
            with self.subTest(expected=expected):
                found = pcb_fetch.problems({"projects": projects if isinstance(projects, list) else [projects]})
                self.assertTrue(any(line.startswith(expected) for line in found), found)

    def test_a_task_is_checked_against_the_corpus(self):
        manifest = {"projects": [upstream()]}
        task = {"id": "tiny-fix", "project": "tiny", "kind": "fix_drc", "proof": "selftest",
                "prompt": "DRC fails on tiny.kicad_pcb since my last edit; fix it.",
                "mutations": [{"op": "delete", "file": "tiny.kicad_pcb", "uuids": ["10000000-0000-0000-0000-000000000002"]}],
                "checks": [{"check": "drc_no_worse"}], "reference": [{"op": "restore", "file": "tiny.kicad_pcb"}]}
        self.assertEqual(pcb_bench.task_problems({"tasks": [task]}, manifest), [])
        cases = {
            "tiny-fix: the prompt speaks of a benchmark": {"prompt": "This benchmark task: fix DRC on tiny.kicad_pcb."},
            "tiny-fix: no project 'gone'": {"project": "gone"},
            "tiny-fix mutation 1: no file gone.kicad_pcb in the project": {
                "mutations": [{"op": "delete", "file": "gone.kicad_pcb", "uuids": ["10000000-0000-0000"]}]},
            "tiny-fix check 1: part_at needs `at`": {"checks": [{"check": "part_at", "ref": "R1"}]},
            "tiny-fix: a build_edit task is graded on a rebuild": {"kind": "build_edit"},
            "tiny-fix: `reference` is the fix": {"reference": []},
        }
        for expected, change in cases.items():
            with self.subTest(expected=expected):
                found = pcb_bench.task_problems({"tasks": [{**task, **change}]}, manifest)
                self.assertTrue(any(line.startswith(expected) for line in found), found)


class FetchTest(unittest.TestCase):
    def test_paths_stay_inside_and_never_through_a_symlink(self):
        for good in ("a.kicad_pcb", "lib/a.pretty/R.kicad_mod", "Atmega328p Arduino Nano/x.kicad_sch"):
            self.assertTrue(pcb_fetch.safe_path(good), good)
        for bad in ("", "/etc/passwd", "../x", "a/../../x", "a//b", "./a", "a\\b", "C:/x"):
            self.assertFalse(pcb_fetch.safe_path(bad), bad)
        with temporary_directory(prefix="pcb-fetch-") as folder:
            root = Path(folder)
            (root / "project").mkdir()
            (root / "outside").mkdir()
            (root / "project" / "lib").symlink_to(root / "outside")
            with self.assertRaisesRegex(ValueError, "refuses unsafe"):
                pcb_fetch.inside(root / "project", "../outside/x")
            with self.assertRaisesRegex(ValueError, "refuses symlink"):
                pcb_fetch.inside(root / "project", "lib/x.kicad_mod")

    def test_a_file_is_kept_only_with_its_hash_and_never_fetched_twice(self):
        data = b"(kicad_pcb)\n"
        entry = {"path": "a.kicad_pcb", "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        with temporary_directory(prefix="pcb-fetch-") as folder:
            project = Path(folder)
            with patch.object(pcb_fetch, "download", return_value=b"(tampered)\n"):
                with self.assertRaises(SystemExit):
                    pcb_fetch.place(project, "a.kicad_pcb", entry, "https://example.invalid/a")
            self.assertFalse((project / "a.kicad_pcb").exists())
            with patch.object(pcb_fetch, "download", return_value=data) as fetched:
                self.assertEqual(pcb_fetch.place(project, "a.kicad_pcb", entry, "https://example.invalid/a"), "fetched")
                self.assertEqual(pcb_fetch.place(project, "a.kicad_pcb", entry, "https://example.invalid/a"), "kept")
            self.assertEqual(fetched.call_count, 1)
            self.assertEqual((project / "a.kicad_pcb").read_bytes(), data)


class MutationTest(unittest.TestCase):
    def test_lists_skip_strings_and_escapes(self):
        heads = [pcb_bench.head(BOARD, span) for span in pcb_bench.lists(BOARD)]
        self.assertEqual(heads, ["version", "generator", "net", "net", "net", "footprint", "gr_text", "segment",
                                 "segment", "via"])

    def test_delete_takes_an_items_own_uuid_alone(self):
        text = pcb_bench.mutate(BOARD, {"op": "delete", "file": "b", "uuids": ["10000000-0000-0000-0000-000000000001",
                                                                             "20000000-0000-0000-0000-000000000001"]})
        self.assertNotIn("tstamp 10000000", text)
        self.assertNotIn("(via", text)
        self.assertIn("10000000-0000-0000-0000-000000000002", text)
        self.assertEqual(text.count("\n"), BOARD.count("\n") - 2)  # each item's line, not a blank left behind
        with self.assertRaisesRegex(ValueError, "found 0"):  # a pad's uuid is no top-level item
            pcb_bench.mutate(BOARD, {"op": "delete", "file": "b", "uuids": ["f0000000-0000-0000-0000-0000000000b1"]})

    def test_strip_net_by_name_or_number_and_move_and_edit(self):
        stripped = pcb_bench.mutate(BOARD, {"op": "strip_net", "file": "b", "net": "/SIG"})
        self.assertEqual([pcb_bench.head(stripped, s) for s in pcb_bench.lists(stripped)][-1], "segment")
        self.assertIn("(net 1)", stripped)  # GND's track stays, and the pad on /SIG
        self.assertIn('(net 2 "/SIG") (uuid', stripped)
        with self.assertRaisesRegex(ValueError, "no track"):
            pcb_bench.mutate(BOARD, {"op": "strip_net", "file": "b", "net": "/NONE"})
        moved = pcb_bench.mutate(BOARD, {"op": "move_part", "file": "b", "ref": "R1", "at": [12.5, 20]})
        self.assertIn("(at 12.5 20 90)", moved)
        self.assertIn("(at -0.8 0 90)", moved)  # a pad's place is the footprint's own frame
        edited = pcb_bench.mutate(BOARD, {"op": "edit", "file": "b", "uuid": "10000000-0000-0000-0000-000000000002",
                                          "from": "(width 0.2)", "to": "(width 0.5)"})
        self.assertEqual(edited.count("(width 0.5)"), 1)
        with self.assertRaisesRegex(ValueError, "occurs 2 times"):
            pcb_bench.mutate(BOARD, {"op": "edit", "file": "b", "from": "(width 0.2)", "to": "(width 0.5)"})


class Facts:
    """Facts written by hand, in the shapes ``pcb_bench.Facts`` reads from a board."""

    def __init__(self, **values):
        self.values = values

    def drc(self, pristine=False):
        return self.values["drc_before" if pristine else "drc"]

    def erc(self, pristine=False):
        return self.values["erc_before" if pristine else "erc"]

    def pads(self, pristine=False):
        return self.values["pads_before" if pristine else "pads"]

    def parts(self, pristine=False):
        return self.values["parts_before" if pristine else "parts"]

    def sch_nets(self, pristine=False):
        return self.values["nets_before" if pristine else "nets"]

    def copper_on(self, net):
        return self.values["copper"].get(net, 0)

    def changed_files(self):
        return self.values["changed"]

    def text(self, relative):
        return self.values["texts"].get(relative)


def finding(type_, net=None, severity="error", check="violation", ref=None):
    return {"check": check, "severity": severity, "type": type_, "description": type_,
            "items": [{"net": net, "ref": ref, "part": ref.lstrip("#").split(".")[0] if ref else None}]}


class CheckTest(unittest.TestCase):
    def test_drc_is_held_to_the_original_board_kind_by_kind(self):
        before = [finding("clearance"), finding("silk_overlap", severity="warning")]
        unconnected = finding("unconnected_items", net="/SIG", check="unconnected")
        facts = Facts(drc=[finding("clearance"), unconnected, finding("silk_overlap", severity="warning")],
                      drc_before=before, copper={"/SIG": 0})
        passed, grown = pcb_bench.evaluate({"check": "drc_no_worse"}, facts)
        self.assertFalse(passed)
        self.assertEqual(grown, {"unconnected": [0, 1]})
        self.assertFalse(pcb_bench.evaluate({"check": "net_routed", "net": "/SIG"}, facts)[0])
        self.assertFalse(pcb_bench.evaluate({"check": "drc_none", "net": "/SIG"}, facts)[0])
        fixed = Facts(drc=before, drc_before=before, copper={"/SIG": 3})
        self.assertTrue(pcb_bench.evaluate({"check": "drc_no_worse"}, fixed)[0])
        self.assertTrue(pcb_bench.evaluate({"check": "net_routed", "net": "/SIG"}, fixed)[0])

    def test_connections_names_and_places(self):
        pads_before = {("R1", "1"): "/MATCHL", ("R1", "2"): "GND", ("U1", "3"): "/MATCHL"}
        renamed = {("R1", "1"): "/ADDR", ("R1", "2"): "GND", ("U1", "3"): "/ADDR"}
        facts = Facts(pads=renamed, pads_before=pads_before,
                      nets={"/ADDR": ("R1.1", "U1.3"), "GND": ("R1.2",)},
                      nets_before={"/MATCHL": ("R1.1", "U1.3"), "GND": ("R1.2",)},
                      parts={"R1": (10.0, 20.0, 90.0, "top"), "H1": (112.0, 100.0, 0.0, "top")},
                      parts_before={"R1": (10.0, 20.0, 90.0, "top"), "H1": (100.0, 100.0, 0.0, "top")})
        rename = {"/MATCHL": "/ADDR"}
        self.assertTrue(pcb_bench.evaluate({"check": "connectivity_same", "rename": rename}, facts)[0])
        self.assertFalse(pcb_bench.evaluate({"check": "connectivity_same"}, facts)[0])
        self.assertTrue(pcb_bench.evaluate({"check": "board_net_named", "net": "/ADDR", "was": "/MATCHL"}, facts)[0])
        self.assertTrue(pcb_bench.evaluate({"check": "sch_net_named", "net": "/ADDR", "was": "/MATCHL"}, facts)[0])
        self.assertTrue(pcb_bench.evaluate({"check": "sch_nets_same", "rename": rename}, facts)[0])
        self.assertFalse(pcb_bench.evaluate({"check": "parts_unmoved"}, facts)[0])
        self.assertTrue(pcb_bench.evaluate({"check": "parts_unmoved", "except": ["H1"]}, facts)[0])
        self.assertTrue(pcb_bench.evaluate({"check": "part_at", "ref": "H1", "at": [112.03, 100]}, facts)[0])
        self.assertFalse(pcb_bench.evaluate({"check": "part_at", "ref": "H1", "at": [112.1, 100]}, facts)[0])
        circle = {"check": "parts_on_circle", "refs": ["H1"], "centre": [100, 100], "radius": 12.0}
        self.assertTrue(pcb_bench.evaluate(circle, facts)[0])
        self.assertFalse(pcb_bench.evaluate({**circle, "radius": 12.5}, facts)[0])

    def test_erc_and_a_review(self):
        error = {"severity": "error", "code": "pin_not_connected", "message": "Pin not connected: Symbol Q2 Pin 1"}
        info = {"severity": "info", "code": "libraries_not_checked", "message": "not checked"}
        facts = Facts(erc=[error, info], erc_before=[info], changed=["REVIEW.md"],
                      texts={"REVIEW.md": "1. ADC7 is open (via missing).\n2. R6 overlaps R7.\n"})
        self.assertEqual(pcb_bench.evaluate({"check": "erc_no_worse"}, facts)[1], {"error/pin_not_connected": [0, 1]})
        self.assertFalse(pcb_bench.evaluate({"check": "erc_none", "code": "pin_not_connected"}, facts)[0])
        self.assertTrue(pcb_bench.evaluate({"check": "files_unchanged", "except": ["REVIEW.md"]}, facts)[0])
        self.assertFalse(pcb_bench.evaluate({"check": "files_unchanged"}, facts)[0])
        faults = [{"id": "adc7", "any": ["ADC ?7"]}, {"id": "r6", "any": ["\\bR6\\b"]}, {"id": "cc2", "any": ["CC ?2"]}]
        passed, named = pcb_bench.evaluate({"check": "review_names", "file": "REVIEW.md", "faults": faults}, facts)
        self.assertFalse(passed)
        self.assertEqual(named, {"adc7": True, "r6": True, "cc2": False})
        self.assertFalse(pcb_bench.evaluate({"check": "review_names", "file": "NOTES.md", "faults": faults}, facts)[0])


class RunFolderTest(unittest.TestCase):
    def test_a_run_folder_is_opaque_and_its_snapshot_skips_kicads_leftovers(self):
        name = pcb_bench.run_name("ecc83-reconnect", "1")
        self.assertRegex(name, r"^w[0-9a-f]{10}$")
        self.assertNotEqual(name, pcb_bench.run_name("ecc83-reconnect", "2"))
        with temporary_directory(prefix="pcb-run-") as folder:
            root = Path(folder)
            (root / "board.kicad_pcb").write_text(BOARD, encoding="utf-8")
            (root / "board.kicad_prl").write_text("{}", encoding="utf-8")
            (root / "fp-info-cache").write_text("", encoding="utf-8")
            self.assertEqual(list(pcb_bench.snapshot(root)), ["board.kicad_pcb"])
            pcb_bench.apply(root, [{"op": "write", "file": "REVIEW.md", "text": "ok\n"},
                                   {"op": "move_part", "file": "board.kicad_pcb", "ref": "R1", "at": [1, 2]}])
            self.assertIn("(at 1 2 90)", (root / "board.kicad_pcb").read_text(encoding="utf-8"))
            self.assertEqual(sorted(pcb_bench.snapshot(root)), ["REVIEW.md", "board.kicad_pcb"])


if __name__ == "__main__":
    unittest.main()
