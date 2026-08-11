"""Static-data checks for the two content-type maps (ported verbatim from JS)."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from server_py import content_types  # noqa: E402


class AssetContentType(unittest.TestCase):
    CASES = {
        "x.js": "text/javascript; charset=utf-8",
        "x.mjs": "text/javascript; charset=utf-8",
        "x.json": "application/json; charset=utf-8",
        "x.wasm": "application/wasm",
        "x.glb": "model/gltf-binary",
        "x.stl": "model/stl",
        "x.3mf": "model/3mf",
        "x.step": "application/step",
        "x.STP": "application/step",  # case-insensitive
        "x.dxf": "application/dxf",
        "x.py": "text/plain; charset=utf-8",
        "x.urdf": "application/xml; charset=utf-8",
        "x.srdf": "application/xml; charset=utf-8",
        "x.sdf": "application/xml; charset=utf-8",
        "x.svg": "image/svg+xml",
        "x.png": "image/png",
        "x.unknown": "application/octet-stream",
        "noext": "application/octet-stream",
    }

    def test_map(self):
        for path, expected in self.CASES.items():
            self.assertEqual(content_types.content_type_for_path(path), expected, path)


class StaticContentType(unittest.TestCase):
    CASES = {
        "x.css": "text/css; charset=utf-8",
        "x.html": "text/html; charset=utf-8",
        "x.ico": "image/x-icon",
        "x.js": "text/javascript; charset=utf-8",
        "x.json": "application/json; charset=utf-8",
        "x.map": "application/json; charset=utf-8",
        "x.svg": "image/svg+xml",
        "x.wasm": "application/wasm",
        "x.glb": "",  # unknown in the static map -> no header
        "noext": "",
    }

    def test_map(self):
        for path, expected in self.CASES.items():
            self.assertEqual(
                content_types.content_type_for_static_asset(path), expected, path
            )


if __name__ == "__main__":
    unittest.main()
