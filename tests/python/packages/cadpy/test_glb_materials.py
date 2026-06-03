from __future__ import annotations

import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadpy/src")

from cadpy.glb import _GlbBuilder


class GlbMaterialTests(unittest.TestCase):
    def test_materials_record_source_color_hint(self) -> None:
        builder = _GlbBuilder()

        source_index = builder.add_material((0.1, 0.1, 0.1, 1.0), source_color=True)
        fallback_index = builder.add_material((0.72, 0.72, 0.72, 1.0), source_color=False)

        materials = builder.json["materials"]
        self.assertEqual({"cadSourceColor": True}, materials[source_index]["extras"])
        self.assertEqual({"cadSourceColor": False}, materials[fallback_index]["extras"])


if __name__ == "__main__":
    unittest.main()
