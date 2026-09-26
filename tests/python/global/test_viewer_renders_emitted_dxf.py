"""What the DXF engine writes is what the Viewer and the CLI can draw.

Two halves of one product: ``cadgen._internal.dxf_emit`` writes drawings through
build123d's ``ExportDXF``, and ``cadgen.drawing_payload`` is what both readers
get them back through — `GET /__cad/drawing` for the Viewer's DXF pane, and the
resolved job for `cadgen dxf snapshot`. An entity the engine emits and the
payload does not carry simply vanishes from the picture: a hole that is cut but
not shown, which is the worst kind of silence in a cut file.

The engine's set is not restated here as a constant; it is MEASURED, by building
a drawing that exercises every converter ``ExportDXF`` has (line, circle, arc,
ellipse, spline) and reading back what came out. So an upstream change that
starts emitting something new fails this test rather than the user's part.

This used to compare that set against a JavaScript DXF parser's entity dispatch.
There is no such parser any more — flattening is ezdxf's, on the server, once —
so the question is answered where it is now decided: every layer the drawing
declares must reach the payload with primitives on it.
"""

from __future__ import annotations

import collections
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

# One layer per converter family, so a layer missing from the payload names the
# geometry that vanished rather than "something".
EXPECTED_LAYERS = ("CUT", "CUT_HOLES", "ENGRAVE")


def _emitted_document():
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
    return document


def _emitted_entity_types() -> collections.Counter:
    return collections.Counter(entity.dxftype() for entity in _emitted_document().modelspace())


def _payload_for_emitted_drawing() -> dict:
    from cadgen.drawing_payload import build_drawing_payload

    document = _emitted_document()
    # A fresh temp directory of its own: the payload is read from a FILE, which
    # is the door both the route and the snapshot resolver use.
    with tempfile.TemporaryDirectory(prefix="cadgen-emitted-dxf-") as tmp:
        path = Path(tmp) / "coverage.dxf"
        document.saveas(path)
        return build_drawing_payload(path)


class ViewerRendersEmittedDxfTest(unittest.TestCase):
    def test_the_rig_exercises_every_exporter_converter(self) -> None:
        """A coverage test that covers nothing passes for the wrong reason."""
        emitted = _emitted_entity_types()
        for kind in ("LINE", "CIRCLE", "ARC", "ELLIPSE", "SPLINE"):
            self.assertIn(kind, emitted, f"the rig no longer produces a {kind}")

    def test_the_drawing_payload_carries_every_emitted_layer(self) -> None:
        payload = _payload_for_emitted_drawing()
        self.assertTrue(payload["primitives"], "the emitted drawing flattened to nothing at all")
        self.assertIsNotNone(payload["bounds"], "a drawing with geometry must have bounds to fit")
        drawn = {str(layer["name"]): int(layer["count"]) for layer in payload["layers"]}
        for layer in EXPECTED_LAYERS:
            with self.subTest(layer=layer):
                self.assertIn(
                    layer,
                    drawn,
                    f"nothing on layer {layer!r} reached the drawing payload, so the Viewer "
                    "and `cadgen dxf snapshot` would both draw that geometry as nothing. "
                    f"Layers with primitives: {sorted(drawn)}",
                )
                self.assertGreater(drawn[layer], 0)

    def test_every_primitive_is_a_shape_the_shared_drawing_code_knows(self) -> None:
        # The client half (packages/core/src/lib/drawing2d) THROWS on a primitive
        # type it does not know rather than dropping it, so a new shape here is a
        # drawing that refuses to open. Pinned against the same five names.
        known = {"point", "lines", "path", "filled-paths", "filled-polygon"}
        payload = _payload_for_emitted_drawing()
        unknown = sorted({str(primitive["type"]) for primitive in payload["primitives"]} - known)
        self.assertEqual(
            [],
            unknown,
            f"the emitted drawing produced primitive type(s) {unknown}; teach "
            "packages/core/src/lib/drawing2d/drawing.js about them, or the viewer and the "
            "snapshot both refuse the drawing.",
        )


if __name__ == "__main__":
    unittest.main()
