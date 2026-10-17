"""The display tolerance and the export bounds: one policy, cadgen's.

`cadgen.tessellation_policy` decides what cadgen meshes a STEP model's components at for
display: one pair, configurable nowhere. Each part's display mesh is made at it, and a mesh
export that names none is cut from that mesh; no store key and no page names it. Only a mesh
export names tolerances of its own, held to the policy's bounds.
"""

from __future__ import annotations

import contextlib
import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen import tessellation_policy as policy  # noqa: E402


class _Accepted(Exception):
    """The export got past its checks to the meshes."""


def _export(*, chord=None, angle=None, stored_meshes=None):
    """Run the mesh export door for one STL at ``chord``/``angle`` (the display ones when None),
    up to the meshes it asks for: ``stored_meshes`` hears the request, then the run stops."""
    from cadgen._internal import mesh_export
    from cadgen._internal.mesh_export import MeshExportJob, MeshSource, run_mesh_exporter
    from cadgen.cli_logging import CliLogger

    def stop(source, pairs, appearance, **_):
        if stored_meshes is not None:
            stored_meshes(pairs)
        raise _Accepted

    job = MeshExportJob(fmt="stl", out=Path("part.stl"), mesh_tolerance=chord, mesh_angular_tolerance=angle)
    with mock.patch.object(mesh_export, "stored_meshes", stop), contextlib.suppress(_Accepted):
        run_mesh_exporter(MeshSource("0" * 64), [job], name="part", logger=CliLogger("test", verbose=False))


class TessellationPolicyTests(unittest.TestCase):
    def test_each_part_is_meshed_for_display_at_the_display_tolerance(self) -> None:
        from build123d import Solid
        from cadgen._internal import tessellate
        from cadgen.store import parts
        from cadgen.store.build import build_tree_from_compound

        display = policy.DISPLAY_TESSELLATION
        for key, value in display.items():
            self.assertIsNone(policy.tolerance_refusal(key, value, name=key))
        with generated_cad_directory(prefix="display-tolerance-") as root, \
                mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(Path(root) / "store"), "CADGEN_DAEMON": "0"}):
            tree, _, _ = build_tree_from_compound(Solid.make_box(1, 2, 3), root_name="box")
            with mock.patch.object(tessellate, "mesh_component", wraps=tessellate.mesh_component) as meshed:
                parts.derive(tree)
        [call] = meshed.call_args_list
        self.assertEqual((call.kwargs["chord"], call.kwargs["angle"]), (display["chordTolerance"], display["angleTolerance"]))

    def test_one_rule_bounds_a_tolerance_at_every_door_and_names_the_bound(self) -> None:
        from cadgen.metadata import normalize_mesh_numeric

        def flag(key, value):
            normalize_mesh_numeric(value, field_name={"chordTolerance": "mesh_tolerance",
                                                      "angleTolerance": "mesh_angular_tolerance"}[key])

        def export(key, value):
            _export(**{{"chordTolerance": "chord", "angleTolerance": "angle"}[key]: value})

        doors = {"flag": flag, "export": export}
        for key in ("chordTolerance", "angleTolerance"):
            floor, ceiling = policy.TESSELLATION_FLOORS[key], policy.TESSELLATION_CEILINGS[key]
            for door, check in doors.items():
                with self.subTest(key=key, door=door):
                    check(key, floor)
                    check(key, ceiling)
                    for outside, bound in ((floor * 0.99, f"at least {floor:g}"), (ceiling * 1.01, f"at most {ceiling:g}"),
                                           (1e300, f"at most {ceiling:g}")):
                        with self.assertRaises(ValueError) as caught:
                            check(key, outside)
                        self.assertIn(bound, str(caught.exception))

    def test_an_export_that_names_no_tolerance_is_cut_from_the_display_mesh(self) -> None:
        asked = []
        _export(stored_meshes=asked.append)
        display = policy.DISPLAY_TESSELLATION
        # One pair, the display one: the very meshes the viewer and snapshots read.
        self.assertEqual([[(display["chordTolerance"], display["angleTolerance"])]], asked)



if __name__ == "__main__":
    unittest.main()
