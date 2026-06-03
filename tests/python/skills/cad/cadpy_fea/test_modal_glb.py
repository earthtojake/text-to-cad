from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[5] / "skills" / "cad"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))


def _has_numpy() -> bool:
    try:
        import numpy  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _parse_glb(data: bytes) -> dict:
    magic, version, _length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, "bad glTF magic"
    assert version == 2, "expected glTF 2.0"
    off = 12
    json_len, json_type = struct.unpack_from("<II", data, off)
    assert json_type == 0x4E4F534A, "first chunk must be JSON"
    off += 8
    gltf = json.loads(data[off:off + json_len].decode("utf-8"))
    off += json_len
    bin_len, bin_type = struct.unpack_from("<II", data, off)
    assert bin_type == 0x004E4942, "second chunk must be BIN"
    return gltf


@unittest.skipUnless(_has_numpy(), "numpy not importable")
class ModalGlbTests(unittest.TestCase):
    def _build(self, tmp: str):
        import numpy as np

        from cadpy_fea.modal_glb import build_modal_glb

        # Unit quad (two triangles), 4 verts.
        verts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float)
        tris = np.array([[0, 1, 2], [0, 2, 3]], dtype=int)
        modes = [
            {"index": 1, "frequencyHz": 38.3, "label": "x-translation",
             "displacement": np.tile([0.1, 0, 0], (4, 1))},
            {"index": 2, "frequencyHz": 95.2, "label": "rocking about y",
             "displacement": np.tile([0, 0, 0.2], (4, 1))},
        ]
        out = Path(tmp) / "modal.glb"
        build_modal_glb(out, verts, tris, modes)
        return out

    def test_structure_has_morph_targets_and_animations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = self._build(tmp)
            gltf = _parse_glb(out.read_bytes())

            mesh = gltf["meshes"][0]
            prim = mesh["primitives"][0]
            self.assertEqual(len(prim["targets"]), 2)            # one morph target / mode
            self.assertEqual(len(mesh["weights"]), 2)
            self.assertEqual(len(gltf["animations"]), 2)         # one clip / mode
            for anim in gltf["animations"]:
                self.assertEqual(anim["channels"][0]["target"]["path"], "weights")
                self.assertEqual(anim["channels"][0]["target"]["node"], 0)
            # Frequencies preserved in names + extras.
            self.assertIn("38.3 Hz", gltf["animations"][0]["name"])
            meta = mesh["extras"]["modes"]
            self.assertEqual([m["frequencyHz"] for m in meta], [38.3, 95.2])

    def test_y_up_conversion(self) -> None:
        # CAD (x, y, z) -> glTF (x, z, -y): a +Z CAD displacement becomes -Y? no,
        # +Z -> +Y. Check the base POSITION of a known vertex.
        import numpy as np

        from cadpy_fea.modal_glb import _y_up

        pts = np.array([[1.0, 2.0, 3.0]])
        out = _y_up(pts)[0]
        self.assertEqual(list(out), [1.0, 3.0, -2.0])

    def test_loads_with_pygltflib_if_available(self) -> None:
        try:
            import pygltflib  # noqa: F401
        except Exception:  # noqa: BLE001
            self.skipTest("pygltflib not installed")
        with tempfile.TemporaryDirectory() as tmp:
            out = self._build(tmp)
            gltf = pygltflib.GLTF2().load(str(out))
            self.assertEqual(len(gltf.animations), 2)
            self.assertEqual(len(gltf.meshes[0].primitives[0].targets), 2)


if __name__ == "__main__":
    unittest.main()
