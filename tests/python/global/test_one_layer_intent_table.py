"""Layer intent -- which DXF layers must hold closed cut contours -- is decided in one place, the
engine's drawing checks (``cadgen.engine.export.dxf``).

There used to be a second table, in JavaScript, because the viewer parsed DXF itself; the two
were hand-copied and nothing pinned them, so validation could accept a drawing the viewer then
rendered as cut paths. Drawing is flattening now (``cadgen.drawing_payload``), which reads no
layer NAMES at all, so the engine's classifier is the only one -- and must stay the only one.
"""

from __future__ import annotations

import unittest

from tests.python.support.paths import REPO_ROOT


class OneLayerIntentTable(unittest.TestCase):
    def test_no_javascript_carries_a_second_layer_intent_table(self) -> None:
        strays = sorted(
            path.relative_to(REPO_ROOT).as_posix()
            for path in (REPO_ROOT / "packages").rglob("*.js")
            if "node_modules" not in path.parts
            and "dist" not in path.parts
            and "_runtime" not in path.parts
            and "INTENT_BY_TOKEN" in path.read_text(encoding="utf-8", errors="ignore")
        )
        self.assertEqual([], strays, f"a second layer-intent table reappeared in {strays}")

    def test_the_engine_still_holds_the_one_table(self) -> None:
        # The guard above looks for the table by its name (the JavaScript copy's was
        # LAYER_INTENT_BY_TOKEN): a rename of the engine's would leave it looking for nothing.
        source = (REPO_ROOT / "packages/cadgen/src/cadgen/engine/export/dxf.py").read_text(encoding="utf-8")
        self.assertIn("_INTENT_BY_TOKEN = {", source)


if __name__ == "__main__":
    unittest.main()
