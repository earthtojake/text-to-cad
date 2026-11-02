"""The Viewer's part in the model library every CAD view shares: the home reads it, and a view
records what it opens, its picture, and what the person pins or removes -- by absolute path."""

from __future__ import annotations

import base64
import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from cad_server.viewer import handler as handler_module
from cad_server.viewer.http_app import create_cad_app
from cad_server.viewer.recents import RecentStore

STL = b"solid t\nendsolid t\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class LibraryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))  # as the viewer spells it (ids.canonical)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.model = self.tmp / "anywhere" / "a.stl"
        self.model.parent.mkdir()
        self.model.write_bytes(STL)
        state = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.tmp / "state"),
                                             "CAD_CACHE_DIR": str(self.tmp / "cache")})
        state.start()
        self.addCleanup(state.stop)
        server = handler_module.serve(create_cad_app(host="127.0.0.1", port=0), "127.0.0.1", 0)
        self.port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            headers = {"x-cad-viewer": "1", "content-type": "application/json"} if body is not None else {}
            connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def change(self, action: str, path: str, **extra) -> tuple[int, dict]:
        status, body = self.request("PATCH", "/api/v1/documents", {"action": action, "path": path, **extra})
        return status, json.loads(body)

    def test_the_library_is_read_and_changed_by_absolute_path(self) -> None:
        from cad.engine.ids import file_id

        self.assertEqual(self.request("GET", "/api/v1/documents"), (200, b'{"documents":[]}'))
        status, answer = self.change("open", str(self.model))
        self.assertEqual((status, [entry["path"] for entry in answer["documents"]]), (200, [str(self.model)]))
        status, answer = self.change("thumbnail", str(self.model), png=base64.b64encode(PNG).decode("ascii"))
        [entry] = answer["documents"]
        # The record's row, its document named: its id, its kind and where its reads are; the record's
        # own kind is ``record`` -- a file's row: removed from the list, its file untouched.
        ident = file_id(self.model)
        self.assertEqual(entry, {**RecentStore().list()[0].public(), "id": ident, "kind": "stl", "record": "file",
                                 "api": f"/api/v1/documents/stl/{ident}"})
        self.assertTrue(self.change("pin", str(self.model))[1]["documents"][0]["pinned"])
        self.assertFalse(self.change("unpin", str(self.model))[1]["documents"][0]["pinned"])
        # The picture, by its document's id.
        status, png = self.request("GET", f"/api/v1/documents/{ident}/thumbnail")
        self.assertEqual((status, png), (200, PNG))
        # Filtered by kind, searched by name or path, at most a number.
        for query, found in (("?kind=stl", 1), ("?kind=model", 0), ("?q=A.ST", 1), ("?q=nothing", 0), ("?limit=1", 1)):
            with self.subTest(query=query):
                self.assertEqual(len(json.loads(self.request("GET", "/api/v1/documents" + query)[1])["documents"]), found)
        self.assertEqual(json.loads(self.request("GET", "/api/v1/documents/stl")[1])["documents"], [entry])
        self.assertEqual(self.request("GET", "/api/v1/documents?limit=0")[0], 400)
        self.assertEqual(self.change("remove", str(self.model)), (200, {"documents": []}))
        self.assertTrue(self.model.is_file(), "removing a file's entry leaves the file")

    def test_a_link_its_target_and_a_case_variant_are_one_entry(self) -> None:
        # One file, one entry, however it is spelled: the spelling the engine keys it by (ids.canonical).
        link = self.tmp / "link.stl"
        try:
            link.symlink_to(self.model)
        except OSError as error:  # Windows without the symlink privilege
            self.skipTest(f"no symlinks here: {error}")
        spellings = [str(link), str(self.model), str(self.model.parent / ".." / "anywhere" / "a.stl")]
        if os.path.exists(str(self.model).upper()):  # a case-insensitive file system (macOS, Windows)
            spellings.append(str(self.model.parent / "A.STL"))
        for spelling in spellings:
            status, answer = self.change("open", spelling)
        self.assertEqual((status, [entry["path"] for entry in answer["documents"]]), (200, [str(self.model)]))
        self.assertEqual(self.change("remove", str(link)), (200, {"documents": []}))

    def test_a_change_names_a_cad_file_by_its_absolute_path(self) -> None:
        (self.tmp / "notes.txt").write_text("x", encoding="utf-8")
        for action, path, extra in (("open", "anywhere/a.stl", {}), ("open", str(self.tmp / "notes.txt"), {}),
                                    ("open", str(self.tmp / "gone.stl"), {}), ("sort", str(self.model), {}),
                                    ("thumbnail", str(self.model), {"png": base64.b64encode(b"GIF89a").decode("ascii")})):
            with self.subTest(action=action, path=path):
                self.assertEqual(self.change(action, path, **extra)[0], 400)
        self.assertEqual(RecentStore().list(), [])

    def test_a_built_model_is_listed_by_its_id_pinned_and_deleted_by_it(self) -> None:
        from cad.engine.ids import model_id
        from cad_server.engine.registry import Registry

        script = self.tmp / "parts.py"
        script.write_text("", encoding="utf-8")
        ident = model_id(script, "cube")
        Registry(self.tmp / "state").put({"id": ident, "kind": "model", "root": str(self.tmp),
                                          "home": "parts.py", "entry": "cube", "revision": "r1", "built": 1.0})
        status, body = self.request("GET", "/api/v1/documents")
        [entry] = json.loads(body)["documents"]
        self.assertEqual((status, entry["path"], entry["id"], entry["kind"], entry["record"], entry["name"]),
                         (200, ident, ident, "model", "model", "cube"), "the home opens it by its id: /<id>")
        self.assertEqual((entry["updated"], entry["opened"]), (1.0, None), "updated is its run's; no page opened it yet")
        [entry] = self.change("open", ident)[1]["documents"]
        self.assertEqual(entry["updated"], 1.0)
        self.assertGreater(entry["opened"], 1.0, "a page's open of its id says when")
        self.assertTrue(self.change("pin", ident)[1]["documents"][0]["pinned"])
        cached = self.tmp / "cache" / "documents" / ident / "document.xbf"
        cached.parent.mkdir(parents=True)
        cached.write_bytes(b"its document")
        self.assertEqual(self.change("remove", ident)[0], 400, "a model is deleted, never removed: the word is Delete")
        self.assertEqual(self.change("delete", ident), (200, {"documents": []}))
        self.assertIsNone(Registry(self.tmp / "state").get(ident))
        self.assertFalse(cached.parent.exists(), "its document in the engine's cache goes with its record")
        self.assertTrue(script.is_file(), "its script stays")

    def test_a_document_forgotten_by_its_id_leaves_its_file(self) -> None:
        from cad.engine.ids import file_id

        self.change("open", str(self.model))
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("DELETE", f"/api/v1/documents/{file_id(self.model)}", headers={"x-cad-viewer": "1"})
            response = connection.getresponse()
            self.assertEqual((response.status, response.read()), (204, b""))
        finally:
            connection.close()
        self.assertEqual(self.request("GET", "/api/v1/documents"), (200, b'{"documents":[]}'))
        self.assertTrue(self.model.is_file(), "forgetting a file's document leaves the file")

    def test_only_a_documents_own_picture_is_read(self) -> None:
        for ident in ("x", "..%2Frecents.jsonl", "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab"):
            with self.subTest(ident=ident):
                self.assertEqual(self.request("GET", f"/api/v1/documents/{ident}/thumbnail")[0], 404)


if __name__ == "__main__":
    unittest.main()
