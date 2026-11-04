#!/usr/bin/env python3

"""Injection molding's mesh verdicts hold across tessellations: every mesh case of the planted-defect corpus
(``test_dfm_molding_corpus``) exported again at two coarse settings around (0.2, 0.6) -- (0.15, 0.5) and
(0.3, 0.8) -- and once turned 7 degrees round the pull before tessellating, turned back, and its vertices
jittered by 1e-4 of its size (a fine case is jittered at its own fine tessellation too). A clean case stays
clean and a planted defect stays found, at its region, on every variant: the same ground truth, scored the
same way. OCCT tessellates differently by platform, and a verdict that moved with the triangles would move
with the machine.
"""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

import build123d as bd
import numpy as np
import trimesh

import cad
from tests.python.packages.cad.test_dfm_molding_corpus import CASES, Tally, _Places, _score

JITTER = 1e-4
TURN_DEG = 7.0


def _variants(case) -> list[tuple[str, tuple[float, float], float, float]]:
    """(label, (tolerance, angular), turn in degrees, jitter as a share of the size)."""
    found = [("coarse 0.15/0.5", (0.15, 0.5), 0.0, 0.0), ("coarse 0.3/0.8", (0.3, 0.8), 0.0, 0.0),
             ("turned and jittered", (0.2, 0.6), TURN_DEG, JITTER)]
    if case.mesh == "fine":
        found.append(("fine, jittered", (0.01, 0.1), 0.0, JITTER))
    return found


def _export(shape, path: Path, tolerance: tuple[float, float], turn: float, jitter: float) -> None:
    bd.export_stl(shape.rotate(bd.Axis.Z, turn) if turn else shape, str(path), tolerance=tolerance[0],
                  angular_tolerance=tolerance[1])
    if not (turn or jitter):
        return
    mesh = trimesh.load(str(path), force="mesh")
    if turn:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-turn), [0, 0, 1]))
    if jitter:
        noise = np.random.default_rng(7).uniform(-1.0, 1.0, mesh.vertices.shape)
        mesh.vertices = mesh.vertices + noise * jitter * float(np.linalg.norm(mesh.extents))
    mesh.export(str(path))


class MeshVariantsTest(unittest.TestCase):
    tallies: dict[str, Tally]

    @classmethod
    def setUpClass(cls) -> None:
        folder = tempfile.TemporaryDirectory(prefix="cad-molding-variants-")
        cls.addClassCleanup(folder.cleanup)
        root = Path(folder.name)
        cls.tallies = defaultdict(Tally)
        cls.partial: list[str] = []
        for case in (case for case in CASES if case.mesh):
            shape = case.build()
            expect = case.expect if case.mesh_expect is None else case.mesh_expect
            absent = case.absent if case.mesh_absent is None else case.mesh_absent
            for index, (label, tolerance, turn, jitter) in enumerate(_variants(case)):
                path = root / f"{case.name}.{index}.stl"
                _export(shape, path, tolerance, turn, jitter)
                result = cad.stl.check(str(path), process="molding", rules=case.rules, material="abs")
                if result.measurements.get("partial"):
                    cls.partial.append(f"{case.name} ({label}): {result.measurements.get('partial_sections')}")
                _score(f"{case.name} ({label})", result, expect, absent, _Places(None), cls.tallies)
        lines = [f"{'rule':34} {'tp':>4} {'fp':>4} {'fn':>4}"]
        lines += [f"{rule:34} {t.tp:4} {t.fp:4} {t.fn:4}" for rule, t in sorted(cls.tallies.items())]
        print("\nmolding mesh variants, per rule:\n" + "\n".join(lines), file=sys.stderr)

    def test_planted_defects_stay_found_on_every_tessellation(self) -> None:
        self.assertEqual([miss for tally in self.tallies.values() for miss in tally.misses], [])

    def test_clean_cases_stay_clean_on_every_tessellation(self) -> None:
        self.assertEqual([found for tally in self.tallies.values() for found in tally.false], [])

    def test_every_variant_measured_whole(self) -> None:
        self.assertEqual(self.partial, [])


if __name__ == "__main__":
    unittest.main()
