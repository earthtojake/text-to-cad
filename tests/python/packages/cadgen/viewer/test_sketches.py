"""A Quick Edit's sketch, saved for a copied prompt to name by path."""

from __future__ import annotations

import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from cadgen.viewer import handler as handler_module
from cadgen.viewer import sketches
from cadgen.viewer.http_app import create_cad_app

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class SketchesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.saved = self.tmp / "sketches"
        where = mock.patch.object(sketches, "sketches_dir", return_value=self.saved)
        where.start()
        self.addCleanup(where.stop)
        app = create_cad_app(host="127.0.0.1", port=0)
        server = handler_module.serve(app, "127.0.0.1", 0)
        self.port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def save(self, png: bytes, name: str) -> tuple[int, dict]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("POST", f"/__cad/sketches?name={name}", body=png, headers={"x-cadgen-viewer": "1", "content-type": "image/png"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_a_sketch_is_saved_under_the_name_the_view_gives_it_once_per_picture(self) -> None:
        status, body = self.save(PNG, "parts%2Fbracket%20v2-sketch.png")
        path = Path(body["path"])
        self.assertEqual((status, path.parent, path.read_bytes()), (200, self.saved, PNG))
        self.assertRegex(path.name, r"^bracket-v2-sketch-[0-9a-f]{12}\.png$")
        self.assertEqual(self.save(PNG, "parts%2Fbracket%20v2-sketch.png")[1]["path"], str(path))
        self.assertEqual(self.save(b"GIF89a", "a-sketch.png")[0], 400)

    def test_only_the_newest_sketches_are_kept(self) -> None:
        with mock.patch.object(sketches, "KEEP", 2):
            first = sketches.save_sketch(PNG + b"\x01", "a.step")
            os.utime(first, ns=(10**9, 10**9))
            second = sketches.save_sketch(PNG + b"\x02", "a.step")
            os.utime(second, ns=(2 * 10**9, 2 * 10**9))
            sketches.save_sketch(PNG + b"\x01", "a.step")  # saved again: the newest once more
            third = sketches.save_sketch(PNG + b"\x03", "a.step")
        self.assertEqual(sorted(path.name for path in self.saved.iterdir()), sorted([Path(first).name, Path(third).name]))


if __name__ == "__main__":
    unittest.main()
