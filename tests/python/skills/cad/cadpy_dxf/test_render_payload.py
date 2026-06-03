import unittest
from pathlib import Path

import ezdxf

from tests.python.support.tmp_root import temporary_directory
from cadpy_dxf.render_payload import build_dxf_render_payload


class CadpyDxfTests(unittest.TestCase):
    def test_build_dxf_render_payload_supports_straight_lwpolyline(self) -> None:
        with temporary_directory(prefix="tmp-cad-dxf-") as tmpdir:
            dxf_path = Path(tmpdir) / "outline.dxf"
            doc = ezdxf.new("R2010")
            modelspace = doc.modelspace()
            modelspace.add_lwpolyline(
                [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
                close=True,
                dxfattribs={"layer": "CUT"},
            )
            doc.saveas(dxf_path)

            payload = build_dxf_render_payload(dxf_path, file_ref="test/outline.dxf")

        self.assertEqual(4, payload["counts"]["paths"])
        self.assertEqual(0, payload["counts"]["circles"])
        self.assertEqual(4, len(payload["geometry"]["lines"]))
        self.assertEqual(10.0, payload["bounds"]["width"])
        self.assertEqual(5.0, payload["bounds"]["height"])


if __name__ == "__main__":
    unittest.main()
