"""The Viewer must render every entity kind the DXF engine can write.

Two halves of one product, in two languages: `cadgen._internal.dxf_emit` writes
drawings through build123d's `ExportDXF`, and `packages/core/src/lib/dxf/
parseDxf.js` is what the Viewer and the snapshot renderer read them back with.
An entity the engine emits and the parser does not know simply vanishes from the
render — a hole that is cut but not shown, which is the worst kind of silence in
a cut file.

The engine's set is not restated here as a constant; it is MEASURED, by building
a drawing that exercises every converter `ExportDXF` has (line, circle, arc,
ellipse, spline) and reading back what came out. So an upstream change that
starts emitting something new fails this test rather than the user's part.
"""

from __future__ import annotations

import collections
import re
import unittest

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

PARSER = repo_path("packages/core/src/lib/dxf/parseDxf.js")
# `if (entityType === "SPLINE") {` — the parser's dispatch, plus the explicit
# list of types it knowingly ignores.
_DISPATCH = re.compile(r'entityType === "([A-Z0-9_]+)"')


def _parser_entity_types() -> set[str]:
    return set(_DISPATCH.findall(PARSER.read_text(encoding="utf-8")))


def _emitted_entity_types() -> collections.Counter:
    import build123d as bd

    from cadgen._internal.dxf_emit import emit_dxf

    with bd.BuildSketch() as blank:
        bd.Rectangle(60, 40)
    # Side by side, not one cut out of the other: subtracting an ellipse from a
    # circle splits the circle into arcs and the rig stops covering CIRCLE.
    holes = [bd.Circle(6).face(), (bd.Pos(20, 0) * bd.Ellipse(8, 4).face())]
    with bd.BuildSketch() as mark:
        bd.Text("R", font_size=8)                             # SPLINE (glyph outlines)
    drawing = {
        # A kerf offset rounds the blank's corners: LINEs joined by true ARCs.
        # It has to be a layer of its own, because offsetting the holes too would
        # turn the CIRCLE into arcs and leave the rig covering less than it claims.
        "CUT": bd.offset(blank.sketch, amount=0.2),
        "CUT_HOLES": holes,
        "ENGRAVE": mark.sketch,
    }
    _, document = emit_dxf(drawing, label="viewer-coverage")
    return collections.Counter(entity.dxftype() for entity in document.modelspace())


class ViewerRendersEmittedDxfTest(unittest.TestCase):
    def test_the_rig_exercises_every_exporter_converter(self) -> None:
        """A coverage test that covers nothing passes for the wrong reason."""
        emitted = _emitted_entity_types()
        for kind in ("LINE", "CIRCLE", "ARC", "ELLIPSE", "SPLINE"):
            self.assertIn(kind, emitted, f"the rig no longer produces a {kind}")

    def test_the_viewer_parser_handles_every_emitted_kind(self) -> None:
        supported = _parser_entity_types()
        missing = sorted(set(_emitted_entity_types()) - supported)
        self.assertEqual(
            [],
            missing,
            f"{PARSER.name} does not handle {missing}, which the DXF engine emits. "
            "Add support in packages/core and regenerate the bundles, or the "
            "Viewer will silently drop that geometry.",
        )


if __name__ == "__main__":
    unittest.main()
