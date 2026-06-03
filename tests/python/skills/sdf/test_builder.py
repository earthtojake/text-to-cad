import unittest
import xml.etree.ElementTree as ET

from tests.python.support.paths import add_repo_path

add_repo_path("skills/sdf/scripts")

from sdf import builder


class SdfBuilderTests(unittest.TestCase):
    def test_builds_minimal_model_with_box_geometry(self) -> None:
        root = builder.sdf_root()
        model = builder.model(root, "fixture", static=False)
        base = builder.link(model, "base_link")
        visual = builder.visual(base, "base_visual")
        builder.box(visual, (0.4, 0.3, 0.1))
        collision = builder.collision(base, "base_collision")
        builder.box(collision, (0.4, 0.3, 0.1))

        xml = ET.tostring(root, encoding="unicode")

        self.assertIn('<sdf version="1.12"', xml)
        self.assertIn('<model name="fixture"', xml)
        self.assertIn("<size>0.4 0.3 0.1</size>", xml)

    def test_rejects_invalid_numeric_values(self) -> None:
        root = builder.sdf_root()
        model = builder.model(root, "fixture")
        base = builder.link(model, "base_link")
        visual = builder.visual(base, "base_visual")

        with self.assertRaisesRegex(ValueError, "positive"):
            builder.box(visual, (1, 0, 1))
        with self.assertRaisesRegex(ValueError, "nonzero"):
            builder.axis(model, (0, 0, 0))

    def test_builds_static_plugin_metadata(self) -> None:
        root = builder.sdf_root()
        model = builder.model(root, "fixture")
        builder.plugin(model, "controller", "gz-sim-joint-controller-system", topic="/cmd")

        xml = ET.tostring(root, encoding="unicode")

        self.assertIn('name="controller"', xml)
        self.assertIn('filename="gz-sim-joint-controller-system"', xml)
        self.assertIn("<topic>/cmd</topic>", xml)


if __name__ == "__main__":
    unittest.main()
