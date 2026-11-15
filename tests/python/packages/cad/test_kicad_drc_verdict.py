"""What ``cad kicad_pcb drc`` runs and what it makes of KiCad's report (``cad.kicad._check``): the zones refilled
in memory, the board held to the schematic beside it, and which findings fail the board.

No KiCad here: kicad-cli is stood in for by one that writes a report as kicad-cli 10.99 writes it (the KiCad
suite runs the real check on a stale pour, a parity mismatch and an exclusion,
``tests/python/packages/kicad/test_native_files.py``). The board is the test board
(``tests/python/support/kicad_board.py``), in a fresh folder.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.kicad_board import write_board, write_schematic
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

TRACK = {"uuid": "a", "description": "Track [VBUS] on F.Cu, length 9.2 mm", "pos": {"x": 5, "y": 8}}
DANGLING = {"type": "track_dangling", "severity": "warning", "description": "Track has unconnected end", "items": [TRACK]}
# KiCad reports a violation the project excludes at its rule's severity, marked, with the exclusion's comment.
EXCLUDED = {"type": "clearance", "severity": "error", "excluded": True, "comment": "stub is intentional",
            "description": "Clearance violation", "items": [TRACK]}
UNCONNECTED = {"type": "unconnected_items", "severity": "error", "description": "Missing connection between items",
               "items": [TRACK]}
# A part of the schematic the board lacks names no item and no place; KiCad calls every parity finding a warning.
MISSING = {"type": "missing_footprint", "severity": "warning", "description": "Missing footprint R3 (1k)", "items": []}


class Verdict(unittest.TestCase):
    def checked(self, report: dict, *, schematic: bool = True, project: bool = True, stderr: str = ""):
        """``check`` of the test board with kicad-cli stood in for: the result, and the command line it ran."""
        from cad.kicad import _check

        folder = tempfile.TemporaryDirectory(prefix="drc-verdict-")
        self.addCleanup(folder.cleanup)
        board = write_board(Path(folder.name))
        if schematic:
            write_schematic(Path(folder.name))
        if project:
            board.with_suffix(".kicad_pro").write_text("{}", encoding="utf-8")
        seen: list[list[str]] = []

        def run(command, **_options):
            seen.append(command)
            Path(command[command.index("-o") + 1]).write_text(json.dumps(report), encoding="utf-8")
            return mock.Mock(returncode=0, stdout="", stderr=stderr)

        with mock.patch.object(_check, "ready", return_value=Path("/opt/kicad/bin/kicad-cli")), \
                mock.patch.object(_check.subprocess, "run", run):
            result = _check.check(board)
        return result, seen[0]

    def test_the_zones_are_refilled_in_memory_and_a_difference_from_the_schematic_fails_the_board(self) -> None:
        result, command = self.checked({"violations": [DANGLING], "schematic_parity": [MISSING]})
        self.assertIn("--refill-zones", command)
        self.assertNotIn("--save-board", command, "the board is never rewritten")
        self.assertIn("--schematic-parity", command)
        self.assertFalse(result.ok)
        # The finding that fails the board is the check's error, whatever KiCad called it; its row keeps KiCad's.
        self.assertEqual([("error", "missing_footprint", None), ("warning", "track_dangling", "(5, 8) mm")],
                         [(finding.severity, finding.code, finding.location) for finding in result.findings])
        [row] = [row for row in result.measurements["drc"] if row["check"] == "parity"]
        self.assertEqual(("warning", [], None, False), (row["severity"], row["items"], row["at"], row["excluded"]))
        self.assertEqual("FAILED", result.human_lines()[-1].split()[0])

    def test_a_board_with_no_schematic_says_it_was_not_checked_against_one(self) -> None:
        result, command = self.checked({"violations": [], "schematic_parity": []}, schematic=False)
        self.assertNotIn("--schematic-parity", command)
        self.assertTrue(result.ok)
        self.assertEqual([("info", "no_schematic")], [(finding.severity, finding.code) for finding in result.findings])
        self.assertIn("no blinky.kicad_sch beside the board", result.findings[0].message)
        # A schematic kicad-cli could not take a netlist from reads, in its report, as a board that matches.
        failed, _command = self.checked({"schematic_parity": []}, stderr="Failed to fetch schematic netlist for parity tests.")
        self.assertEqual((False, ["kicad_failed"]), (failed.ok, [finding.code for finding in failed.findings]))

    def test_a_finding_the_project_excludes_is_listed_and_fails_nothing(self) -> None:
        older = {**UNCONNECTED, "severity": "exclusion"}  # as an older kicad-cli reports one, with no comment
        result, _command = self.checked({"violations": [EXCLUDED, DANGLING], "unconnected_items": [older]})
        self.assertTrue(result.ok)
        self.assertTrue(result.summary.endswith("DRC clean (1 warning(s), 2 excluded)"), result.summary)
        self.assertEqual(["warning", "info", "info"], [finding.severity for finding in result.findings])
        clearance = next(finding for finding in result.findings if finding.code == "clearance")
        self.assertTrue(clearance.message.endswith("(excluded in the project: stub is intentional)"), clearance.message)
        rows = {row["type"]: row for row in result.measurements["drc"]}
        self.assertEqual(("error", True, "stub is intentional"),
                         (rows["clearance"]["severity"], rows["clearance"]["excluded"], rows["clearance"]["comment"]))
        self.assertEqual((True, None), (rows["unconnected_items"]["excluded"], rows["unconnected_items"]["comment"]))
        # Not excluded, an unconnected item fails the board whatever severity the project gives it.
        result, _command = self.checked({"unconnected_items": [{**UNCONNECTED, "severity": "warning"}]})
        self.assertEqual((False, ["error"]), (result.ok, [finding.severity for finding in result.findings]))

    def test_the_summary_counts_the_warning_said_of_a_board_with_no_project(self) -> None:
        result, _command = self.checked({"violations": []}, project=False)
        self.assertEqual(["no_project"], [finding.code for finding in result.findings])
        self.assertTrue(result.ok and result.summary.endswith("DRC clean (1 warning(s))"), result.summary)


if __name__ == "__main__":
    unittest.main()
