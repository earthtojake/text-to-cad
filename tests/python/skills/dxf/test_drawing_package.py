"""The drawing package's shape depends on what kind of DXF it holds.

A cut layout bakes preview.glb, the 3D prism of its profile. A dimensioned drawing has no flat
pattern to extrude, so its package carries the parsed 2D geometry and nothing else -- and both
freshness authorities have to know that, or the package is reported current with a payload the
viewer cannot render, or stale forever (issue #246).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from cadgen._internal import drawing_package
from cadgen._internal.source_hash import closure_for_files
from cadgen.catalog import render_package_dir
from tests.python.support.tmp_root import temporary_directory


def python_source_closure_for(source: Path):
    return closure_for_files(source, [source], base=source.parent)


class DrawingProfilePackageTest(unittest.TestCase):
    """A dimensioned drawing's package holds its 2D geometry and no 3D prism.

    preview.glb is the extruded CUT profile; a drawing has no flat pattern to extrude. The two
    freshness authorities have to agree about that, or the package is either reported current
    with a payload the viewer cannot render, or stale forever (issue #246).
    """

    def test_payload_keys_depend_on_the_profile(self) -> None:
        self.assertEqual(("geometry",), drawing_package.drawing_payload_keys({"profile": "drawing"}))
        self.assertEqual(
            ("preview", "geometry"), drawing_package.drawing_payload_keys({"profile": "cut"})
        )

    def test_a_descriptor_written_before_profiles_existed_still_expects_a_preview(self) -> None:
        # Backwards compatibility in the direction that matters: every package written so far is
        # a cut layout, and must keep being validated as one.
        self.assertEqual(("preview", "geometry"), drawing_package.drawing_payload_keys({}))
        self.assertFalse(drawing_package.descriptor_is_drawing({}))

    def test_the_viewer_asks_the_same_question_from_the_same_function(self) -> None:
        # Not "the two lists match today" -- the viewer imports cadgen's rule, so they cannot
        # drift. This asserts the wiring, which is the thing an edit could undo.
        import sys
        from pathlib import Path as _Path

        viewer_root = str(_Path(__file__).resolve().parents[4] / "viewer")
        if viewer_root not in sys.path:
            sys.path.insert(0, viewer_root)
        from server_py import artifact as viewer_artifact

        self.assertIs(viewer_artifact.drawing_payload_keys, drawing_package.drawing_payload_keys)
        self.assertEqual(
            ["geometry.json"],
            viewer_artifact._drawing_payload_refs(
                {"profile": "drawing", "geometry": "geometry.json", "preview": "preview.glb"}
            ),
            "a drawing package must not be checked for the prism it never bakes",
        )

    def test_a_drawing_package_with_no_bake_is_still_current(self) -> None:
        # The rebuild loop this guards: a bakeHash gate applied to a package that never baked
        # reports stale on every poll, so the viewer rebuilds forever.
        with temporary_directory(prefix="cad-drawing-profile-") as temp_dir:
            source = Path(temp_dir) / "sheet.dxf.py"
            source.write_text("def gen_dxf():\n    raise NotImplementedError\n")
            package_dir = render_package_dir(source)
            (package_dir).mkdir(parents=True, exist_ok=True)
            (package_dir / "geometry.json").write_text("{}")
            closure = python_source_closure_for(source)
            (package_dir / "drawing.json").write_text(json.dumps({
                "kind": drawing_package.DRAWING_PACKAGE_KIND,
                "packageSchemaVersion": drawing_package.DXF_PACKAGE_SCHEMA_VERSION,
                "profile": "drawing",
                "sourceKind": "python",
                "sourcePath": source.name,
                "sourceHash": "unused",
                "geometry": "geometry.json",
                "sourceClosureHash": closure.closure_hash,
                "sourceClosureFiles": list(closure.files),
            }))
            self.assertTrue(drawing_package.drawing_package_current(source))
