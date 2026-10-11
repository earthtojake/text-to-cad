"""The display tessellation ladder, its floors and a snapshot's tessellation: one policy, cadgen's.

`cadgen.tessellation_policy` decides what cadgen meshes a STEP model's components at for
display. The store's default mesh key, the snapshot door's floors, a snapshot job's
tolerances and what the pages are told (the CAD Viewer's server info, the CAD app's launch)
all read it; the page only picks a rung from its camera.
"""

from __future__ import annotations

import json
import unittest

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

from cadgen import tessellation_policy as policy  # noqa: E402


class TessellationPolicyTests(unittest.TestCase):
    def test_the_ladder_runs_coarse_to_fine_and_opens_at_the_stores_standard_mesh(self) -> None:
        from cadgen.store import meshes

        levels = policy.ladder_payload()["levels"]
        chords = [level["chordTolerance"] for level in levels]
        self.assertEqual(chords, sorted(chords, reverse=True))
        self.assertGreaterEqual(levels[0]["angleTolerance"], max(level["angleTolerance"] for level in levels))
        standard = levels[policy.ladder_payload()["defaultLevel"]]
        # A key that names no tolerances is the standard rung's.
        self.assertEqual((meshes.DEFAULT_CHORD, meshes.DEFAULT_ANGLE),
                         (standard["chordTolerance"], standard["angleTolerance"]))
        self.assertEqual(meshes.tessellation_key("a" * 64),
                         meshes.tessellation_key("a" * 64, standard["chordTolerance"], standard["angleTolerance"]))
        # Every rung is one any request may ask to have meshed.
        for level in levels:
            for key, value in level.items():
                self.assertIsNone(policy.tolerance_refusal(key, value, name=key), level)

    def test_one_rule_bounds_a_tolerance_at_every_door_and_names_the_bound(self) -> None:
        from cadgen.metadata import normalize_mesh_numeric
        from cadgen.snapshot_core import SnapshotError, validate_render_tessellation
        from cadgen.store import meshes

        def flag(key, value):
            normalize_mesh_numeric(value, field_name={"chordTolerance": "mesh_tolerance",
                                                      "angleTolerance": "mesh_angular_tolerance"}[key])

        def snapshot(key, value):
            validate_render_tessellation({key: value})

        def request(key, value):
            meshes.normalize_tessellations([{**policy.DEFAULT_TESSELLATION, key: value}])

        def stored(key, value):
            pair = {**policy.DEFAULT_TESSELLATION, key: value}
            key_ = meshes.tessellation_key("a" * 64, pair["chordTolerance"], pair["angleTolerance"])
            if meshes.meshable_key(key_) is None:
                raise ValueError("not a key anything may ask to have meshed")

        doors = {"flag": flag, "snapshot": snapshot, "request": request, "stored key": stored}
        for key in ("chordTolerance", "angleTolerance"):
            floor, ceiling = policy.TESSELLATION_FLOORS[key], policy.TESSELLATION_CEILINGS[key]
            for door, check in doors.items():
                with self.subTest(key=key, door=door):
                    check(key, floor)
                    check(key, ceiling)
                    for outside, bound in ((floor * 0.99, f"at least {floor:g}"), (ceiling * 1.01, f"at most {ceiling:g}"),
                                           (1e300, f"at most {ceiling:g}")):
                        with self.assertRaises((ValueError, SnapshotError)) as caught:
                            check(key, outside)
                        if door != "stored key":
                            self.assertIn(bound, str(caught.exception))

    def test_a_snapshot_draws_the_rung_its_display_asks_for_or_what_it_names(self) -> None:
        levels = policy.TESSELLATION_LADDER
        standard, finest = levels[policy.DEFAULT_LEVEL], levels[-1]
        for display, expected in (
            ({}, standard),
            ({"mode": "solid"}, standard),
            ({"mode": "render"}, finest),  # Render lights at `final` unless told otherwise
            ({"mode": "render", "lighting": {"quality": "preview"}}, standard),
            ({"mode": "render", "lighting": {"enabled": False}}, standard),
            ({"mode": "solid", "lighting": {"quality": "final"}}, finest),
        ):
            with self.subTest(display=display):
                self.assertEqual(expected, policy.snapshot_tessellation({"display": display}))
        named = {"chordTolerance": 1e-4, "angleTolerance": 0.1}
        self.assertEqual(named, policy.snapshot_tessellation({"display": {"mode": "render"},
                                                              "quality": {"tessellation": named}}))
        # A tolerance a request leaves out is the standard rung's: the job names both.
        self.assertEqual({"chordTolerance": 1e-4, "angleTolerance": standard["angleTolerance"]},
                         policy.snapshot_tessellation({"quality": {"tessellation": {"chordTolerance": 1e-4}}}))

    def test_the_tests_copy_of_the_ladder_is_the_one_cadgen_publishes(self) -> None:
        # Written by make_fixtures.py for the JS tests, which install it as a host does.
        text = repo_path("packages/core/src/lib/surf/fixtures/tessellationLadder.js").read_text(encoding="utf-8")
        head = "export const TESSELLATION_LADDER = "
        literal = text[text.index(head) + len(head):].strip().removesuffix(";")
        self.assertEqual(policy.ladder_payload(), json.loads(literal))


if __name__ == "__main__":
    unittest.main()
