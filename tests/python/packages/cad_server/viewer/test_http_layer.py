"""Black-box HTTP against a real launched server.

Several of these are RAW SOCKET tests rather than urllib ones. That is not
fussiness: the contract pins the ABSENCE of headers (no ``Server``, no
``Access-Control-*``, no ``content-type`` on the bare responses) and the
framing of consecutive requests on one connection, and neither is visible to a
status-code assertion.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

import cad_server
from cad_server._internal.picker import FilePicker, PickerFailed
from cad_server.viewer import handler as handler_module
from cad_server.viewer.http_app import create_cad_app, host_is_allowed, hostname_only


class ServerFixture:
    """A CadApp on an ephemeral loopback port, started in ``root`` (a folder of the fixture's own),
    torn down on exit."""

    def __init__(self, *, host="127.0.0.1", with_dist=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "models")
        os.makedirs(self.root)
        self.dist = ""
        if with_dist:
            self.dist = os.path.join(self.tmp.name, "dist")
            os.makedirs(os.path.join(self.dist, "assets"))
            Path(self.dist, "index.html").write_text("<!doctype html><title>cad</title>", encoding="utf-8")
            # Bytes, not text mode: the body is asserted byte-exact, and text
            # mode would write \r\n on Windows.
            Path(self.dist, "assets", "app.js").write_bytes(b"export const x = 1;\n")
            Path(self.dist, "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
            Path(self.dist, "weird.xyz").write_text("unknown extension", encoding="utf-8")
        self.app = create_cad_app(host=host, port=0, dist_dir=self.dist, start=self.root)
        self.server = handler_module.serve(self.app, host, 0)
        self.port = self.server.server_address[1]
        self.app.port = self.port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    # --- clients -----------------------------------------------------------

    def request(self, method, path, *, headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            payload = response.read()
            return response.status, dict(response.getheaders()), payload
        finally:
            conn.close()

    def raw(self, request_bytes, *, reads=1):
        """Send raw bytes on one connection and read ``reads`` responses."""
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        try:
            sock.sendall(request_bytes)
            chunks = []
            sock.settimeout(3)
            while True:
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
                if reads and b"".join(chunks).count(b"HTTP/1.") >= reads:
                    # Give the peer a beat to flush the rest of the last body.
                    sock.settimeout(0.3)
            return b"".join(chunks)
        finally:
            sock.close()


class HttpLayerTestCase(unittest.TestCase):
    with_dist = True
    bind_host = "127.0.0.1"

    @classmethod
    def setUpClass(cls):
        cls.fixture = ServerFixture(host=cls.bind_host, with_dist=cls.with_dist)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.close()


class HostGate(HttpLayerTestCase):
    def test_loopback_names_pass(self):
        for value in ("127.0.0.1:1", "localhost", "LOCALHOST", "[::1]:3245", "[::1]", " localhost "):
            with self.subTest(host=value):
                status, _, _ = self.fixture.request("GET", "/api/v1/server", headers={"Host": value})
                self.assertEqual(status, 200)

    def test_non_local_name_is_refused_with_the_exact_message(self):
        status, headers, body = self.fixture.request(
            "GET", "/api/v1/server", headers={"Host": "attacker.example"}
        )
        self.assertEqual(status, 403)
        self.assertEqual(
            body.decode("utf-8"),
            '{"error":"Host header \'attacker.example\' is not a local name; '
            'refusing (DNS-rebinding defense)","hint":"open the CAD Viewer at 127.0.0.1 or localhost"}',
        )
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assertEqual(headers["cache-control"], "no-store")

    def test_the_sanitised_name_is_interpolated_not_the_raw_header(self):
        _, _, body = self.fixture.request("GET", "/api/v1/server", headers={"Host": "EVIL.example:8443"})
        self.assertIn(b"'evil.example'", body)

    def test_the_gate_covers_every_route(self):
        for path in ("/", "/assets/app.js", "/app", "/api/v1/documents", "/api/v1/look", "/api/v1/nope"):
            with self.subTest(path=path):
                status, _, _ = self.fixture.request("GET", path, headers={"Host": "attacker.example"})
                self.assertEqual(status, 403)

    def test_head_is_gated_too(self):
        status, _, _ = self.fixture.request("HEAD", "/api/v1/server", headers={"Host": "attacker.example"})
        self.assertEqual(status, 403)

    def test_unit_cases(self):
        self.assertEqual(hostname_only("[::1]:3245"), "::1")
        self.assertEqual(hostname_only("127.0.0.1:80:80"), "127.0.0.1:80")
        self.assertEqual(hostname_only("127.0.0.1:abc"), "127.0.0.1:abc")
        self.assertEqual(hostname_only("localhost:"), "localhost:")
        self.assertEqual(hostname_only("[bad"), "[bad")
        self.assertTrue(host_is_allowed("", "127.0.0.1"))
        self.assertFalse(host_is_allowed("::1", "127.0.0.1"))
        self.assertFalse(host_is_allowed("127.0.0.1.evil.example", "127.0.0.1"))
        self.assertFalse(host_is_allowed("0.0.0.0", "127.0.0.1"))
        # Port is never compared.
        self.assertTrue(host_is_allowed("localhost:12345", "127.0.0.1"))


class NonLoopbackBindDisablesTheGate(unittest.TestCase):
    def test_binding_a_non_loopback_host_allows_everything(self):
        # Not launched: hostIsAllowed's first branch is a pure function and
        # binding 0.0.0.0 in a test would expose a port to the network.
        self.assertTrue(host_is_allowed("attacker.example", "0.0.0.0"))
        self.assertTrue(host_is_allowed("anything", "192.168.1.5"))


class BindAsksNoReverseDns(unittest.TestCase):
    def test_the_bind_never_names_the_host_by_reverse_dns(self):
        # http.server's own bind calls socket.getfqdn, which waits 35 s on a Mac
        # whose resolver does not answer: every launch's URL line waited on it.
        with mock.patch("socket.getfqdn", side_effect=AssertionError("a reverse DNS lookup at bind")):
            server = handler_module.CadHTTPServer(("127.0.0.1", 0), handler_module.make_handler_class(None), None)
        server.server_close()


class PostGuard(HttpLayerTestCase):
    def test_missing_header_is_refused_with_the_exact_message(self):
        status, _, body = self.fixture.request("POST", "/api/v1/documents")
        self.assertEqual(status, 403)
        self.assertEqual(
            body.decode("utf-8"),
            '{"error":"missing x-cad-viewer header (cross-site POST blocked)",'
            '"hint":"send \'x-cad-viewer: 1\'"}',
        )

    def test_every_method_that_changes_something_is_guarded(self):
        for method, path in (("PUT", "/api/v1/settings"), ("PATCH", "/api/v1/documents"),
                             ("DELETE", "/api/v1/documents/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab")):
            with self.subTest(method=method):
                status, _, body = self.fixture.request(method, path)
                self.assertEqual(status, 403)
                self.assertIn(f"cross-site {method} blocked", json.loads(body)["error"])

    def test_an_empty_value_is_falsy_and_refused(self):
        status, _, _ = self.fixture.request("POST", "/api/v1/documents", headers={"x-cad-viewer": ""})
        self.assertEqual(status, 403)

    def test_the_gate_runs_before_dispatch_so_unknown_routes_are_covered(self):
        status, _, _ = self.fixture.request("POST", "/anything/at/all")
        self.assertEqual(status, 403)

    def test_host_gate_wins_over_the_header_gate(self):
        status, _, body = self.fixture.request(
            "POST", "/api/v1/documents", headers={"Host": "attacker.example", "x-cad-viewer": "1"}
        )
        self.assertEqual(status, 403)
        self.assertIn(b"DNS-rebinding", body)

    def test_reads_are_unaffected(self):
        status, _, _ = self.fixture.request("GET", "/api/v1/server")
        self.assertEqual(status, 200)


class ServerInfo(HttpLayerTestCase):
    def test_payload(self):
        status, headers, body = self.fixture.request("GET", "/api/v1/server")
        self.assertEqual(status, 200)
        info = json.loads(body)
        self.assertEqual(info["app"], "cad-viewer")
        self.assertIn("identityToken", info)
        self.assertIn(info["platform"], ("darwin", "win32", "linux"))
        self.assertEqual(info["pid"], os.getpid())
        self.assertEqual(info["port"], self.fixture.port)
        # Where a developer's relative links resolve, spelled with "/". A viewer has no root.
        self.assertEqual(info["start"], self.fixture.root.replace(os.sep, "/"))
        # No tolerance: the page reads each part's one display mesh by its key.
        # Where the explorer starts with nowhere else to: the person's home folder, spelled with "/".
        self.assertEqual(info["home"], os.path.expanduser("~").replace(os.sep, "/"))
        self.assertIsInstance(info["pick"], bool)
        # The release the engine runs: a page that reconnects to another reloads into it.
        self.assertEqual(info["release"], cad_server.__version__)
        self.assertEqual(list(info), ["app", "release", "identityToken", "platform", "user", "home",
                                      "start", "pick", "port", "pid", "notice", "instance", "update", "kinds"])
        self.assertEqual(headers["cache-control"], "no-store")
        # This start of the engine: a page that sees another one reloads. One per process, so it is
        # the same at every ask.
        self.assertRegex(info["instance"], r"^[0-9a-f]{16}$")
        self.assertEqual(json.loads(self.fixture.request("GET", "/api/v1/server")[2])["instance"], info["instance"])
        # Where an update a click started is, and the kinds of documents it reads with what each exports.
        self.assertIn(info["update"]["state"], ("idle", "working", "restarting", "failed"))
        self.assertEqual(info["kinds"]["reads"], ["model", "xbf", "step", "stl", "glb", "3mf", "dxf", "urdf", "srdf", "sdf"])
        self.assertEqual(info["kinds"]["exports"]["xbf"], ["step", "stl", "threemf", "glb", "dxf", "original"])
        self.assertEqual(info["kinds"]["exports"]["dxf"], [])

    def test_json_is_compact_and_not_ascii_escaped(self):
        _, _, body = self.fixture.request("GET", "/api/v1/server")
        self.assertNotIn(b", ", body)
        self.assertNotIn(b'": ', body)

    @unittest.skipIf(os.name == "nt", "Windows refuses to delete a process's working folder")
    def test_a_viewer_started_in_a_deleted_folder_resolves_links_from_home(self):
        gone = tempfile.mkdtemp()
        held = os.getcwd()
        os.chdir(gone)
        try:
            os.rmdir(gone)
            app = create_cad_app(host="127.0.0.1", port=0)
        finally:
            os.chdir(held)
        self.assertEqual(app.start, os.path.expanduser("~").replace(os.sep, "/"))

    def test_the_file_param_the_client_sends_is_ignored(self):
        status, _, _ = self.fixture.request("GET", "/api/v1/server?file=/anything.step")
        self.assertEqual(status, 200)


class Documents(HttpLayerTestCase):
    """A document's envelope: one file's, named by its absolute path wherever it is (nothing walks a
    folder), or a document's by its id."""

    def by_path(self, file=None):
        status, _, body = self.fixture.request(
            "GET", "/api/v1/documents" + ("?path=" if file is None else f"?path={quote(str(file), safe='')}"))
        return status, json.loads(body)

    def test_a_named_file_is_its_one_envelope_and_no_file_has_none(self):
        # Under a hidden folder, outside the folder the viewer started in: named, so listed.
        part = Path(self.fixture.tmp.name, ".work", "part.stl")
        part.parent.mkdir(exist_ok=True)
        part.write_bytes(b"solid p\nendsolid p\n")
        status, answer = self.by_path(part)
        self.assertEqual(status, 200)
        [envelope] = answer["documents"]
        from cad.engine.ids import file_id

        # Its document's id: the page names the file by it (``/<id>``), and rows join by it.
        ident = file_id(part)
        self.assertEqual(list(envelope), ["id", "kind", "name", "version", "state", "source", "producers", "api",
                                          "exports", "schemaVersion", "entry", "revision"])
        self.assertEqual((envelope["id"], envelope["kind"], envelope["name"], envelope["state"]), (ident, "stl", "part.stl", "live"))
        self.assertEqual(envelope["source"], {"type": "file", "path": str(part).replace(os.sep, "/"), "present": True})
        self.assertEqual((envelope["producers"], envelope["api"]), ([], f"/api/v1/documents/stl/{ident}"))
        self.assertEqual(envelope["exports"], ["threemf", "glb"])
        entry = envelope["entry"]
        self.assertEqual(entry["file"], str(part).replace(os.sep, "/"))
        self.assertEqual(list(entry), ["file", "kind", "url", "hash", "bytes", "id"])
        self.assertEqual((entry["id"], envelope["version"]), (ident, entry["hash"]))
        # By its id: the same document, its row as the engine keys it (its canonical path).
        status, _, body = self.fixture.request("GET", f"/api/v1/documents/{ident}")
        by_id = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual({key: by_id[key] for key in ("id", "kind", "name", "version", "api", "exports")},
                         {key: envelope[key] for key in ("id", "kind", "name", "version", "api", "exports")})
        self.assertEqual(os.path.realpath(by_id["entry"]["file"]), os.path.realpath(entry["file"]))
        # The row's URL is how its bytes are read, and so is its document's source.
        self.assertEqual(self.fixture.request("GET", entry["url"])[::2], (200, part.read_bytes()))
        self.assertEqual(self.fixture.request("GET", f"{envelope['api']}/source")[::2], (200, part.read_bytes()))
        part.write_bytes(b"solid moved\nendsolid moved\n")
        self.assertNotEqual(self.by_path(part)[1]["documents"][0]["revision"], envelope["revision"])
        for missing in ("", str(part.with_name("gone.stl")), str(part.with_suffix(".txt"))):
            with self.subTest(file=missing):
                self.assertEqual(self.by_path(missing)[1]["documents"], [])

    def test_a_model_by_its_id_is_its_envelope_at_the_build_held_and_one_not_held_names_its_state(self):
        ident = "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab"
        script = os.path.join(self.fixture.root, "parts", "cube.py")
        answers = {"model_info": {"model": {"source": {"name": "cube", "script": script}, "version": "v1",
                                            "builtAt": 12.5, "state": "held"}}}
        app = self.fixture.app

        def envelope():
            status, _, body = self.fixture.request("GET", f"/api/v1/documents/{ident}")
            return status, json.loads(body)

        with mock.patch("cad_server.viewer.model_catalog.request", side_effect=lambda ask, start: answers[ask["op"]]), \
                mock.patch.object(app, "_file_of", return_value=None), \
                mock.patch.object(app.engine_documents, "server", mock.Mock(served={ident: object()}, model_loaders={})):
            # The row's hash is the build the engine holds: a rebuild is a new revision of the row.
            status, found = envelope()
            self.assertEqual(status, 200)
            row = found["entry"]
            self.assertEqual((row["id"], row["file"], row["sourcePath"], row["hash"]), (ident, ident, None, "model:v1"))
            self.assertEqual((found["kind"], found["name"], found["version"], found["state"], found["held"]),
                             ("model", "cube", "v1", "held", True))
            # Its script, and whether it is there now: one named but gone (or never kept) is not.
            self.assertEqual(found["source"], {"type": "script", "path": script, "function": "cube", "present": False})
            os.makedirs(os.path.dirname(script), exist_ok=True)
            Path(script).write_text("", encoding="utf-8")
            self.assertEqual(envelope()[1]["source"]["present"], True)
            self.assertEqual(found["producers"], [{"tool": "cad", "release": None, "at": 12.5}])
            self.assertEqual((found["api"], found["exports"]), (f"/api/v1/documents/model/{ident}",
                                                                ["step", "stl", "threemf", "glb", "dxf", "xbf"]))
            answers["model_info"] = {"model": {"source": {"name": "cube"}, "version": "v2"}}
            self.assertEqual(envelope()[1]["entry"]["hash"], "model:v2")
            # One it does not hold says why, in the engine's words, and its state.
            answers["model_info"] = {"failed": f"cube ({ident}) is not saved: run `cad run /m/cube.py`", "state": "unsaved"}
            status, answer = envelope()
            self.assertEqual((status, answer["state"], set(answer)), (404, "unsaved", {"error", "hint", "state"}))
            self.assertIn("is not saved", answer["error"])

    def test_an_id_no_document_has_and_a_word_that_is_no_id_are_404s_that_say_so(self):
        status, _, body = self.fixture.request("GET", "/api/v1/documents/not-an-id")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["error"], "not-an-id is not a document id")

    def test_a_file_that_is_not_named_by_its_absolute_path_is_a_400(self):
        status, body = self.by_path("part.stl")
        self.assertEqual(status, 400)
        self.assertIn("absolute path", body["error"])
        self.assertIn("hint", body)

    def test_a_kind_route_on_a_document_of_another_kind_is_a_404_naming_its_kind(self):
        part = Path(self.fixture.tmp.name, "kinded.stl")
        part.write_bytes(b"solid p\nendsolid p\n")
        [envelope] = self.by_path(part)[1]["documents"]
        status, _, body = self.fixture.request("GET", f"/api/v1/documents/dxf/{envelope['id']}/drawing")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {"error": f"{envelope['id']} is a stl",
                                            "hint": f"read it at /api/v1/documents/stl/{envelope['id']}"})
        # A route its own kind does not answer says what its kind's routes are.
        status, _, body = self.fixture.request("GET", f"/api/v1/documents/stl/{envelope['id']}/structure")
        self.assertEqual((status, json.loads(body)["hint"]), (404, "a stl's routes are source"))
        # A kind that is none.
        status, _, body = self.fixture.request("GET", "/api/v1/documents?kind=pdf")
        self.assertEqual((status, json.loads(body)["error"]), (404, "no kind pdf"))

    def test_post_opens_a_file_as_a_document(self):
        part = Path(self.fixture.tmp.name, "opened.stl")
        part.write_bytes(b"solid p\nendsolid p\n")
        from cad.engine.ids import file_id

        def open_(payload):
            status, headers, body = self.fixture.request("POST", "/api/v1/documents", body=json.dumps(payload).encode(),
                                                         headers={"x-cad-viewer": "1", "content-type": "application/json"})
            return status, json.loads(body)

        ident = file_id(part)
        self.assertEqual(open_({"path": str(part)}), (201, {"id": ident, "kind": "stl", "api": f"/api/v1/documents/stl/{ident}"}))
        # Known by its id from then on.
        self.assertEqual(self.fixture.request("GET", f"/api/v1/documents/{ident}")[0], 200)
        status, answer = open_({"path": str(part.with_name("gone.stl"))})
        self.assertEqual((status, set(answer)), (404, {"error", "hint"}))
        status, answer = open_({"path": str(part.with_suffix(".txt"))})
        self.assertEqual(status, 400)
        self.assertIn("is not one", answer["error"])
        self.assertEqual(open_({"path": "opened.stl"})[0], 400)
        self.assertEqual(open_({"file": str(part)})[0], 400)
        # An .xbf or a STEP is the engine's to read: an application with no engine serves none.
        step = part.with_suffix(".step")
        step.write_bytes(b"ISO-10303-21;")
        status, answer = open_({"path": str(step)})
        self.assertEqual(status, 400)
        self.assertIn("served by the installation's engine", answer["error"])

    def test_an_engine_document_still_being_read_is_a_202_with_when_to_ask_again(self):
        step = Path(self.fixture.tmp.name, "reading.step")
        step.write_bytes(b"ISO-10303-21;")
        frame = {"stage": "read", "done": 1, "total": 3}
        reading = (202, {"state": "reading", "retryMs": 1500, "building": frame})
        with mock.patch.object(self.fixture.app.engine_documents, "response", return_value=reading):
            status, headers, body = self.fixture.request("POST", "/api/v1/documents", body=json.dumps({"path": str(step)}).encode(),
                                                         headers={"x-cad-viewer": "1"})
        from cad.engine.ids import file_id

        self.assertEqual(status, 202)
        self.assertEqual(headers["retry-after"], "2")
        self.assertEqual(json.loads(body), {"id": file_id(step), "kind": "step", "api": f"/api/v1/documents/step/{file_id(step)}",
                                            "state": "reading", "retryMs": 1500, "building": frame})


class ExplorerRoutes(HttpLayerTestCase):
    """The explorer's two reads (``folders.py``) over HTTP: a folder by its absolute path."""

    def read(self, route, path, **query):
        target = f"/api/v1/local/{route}?path={quote(str(path), safe='')}" + "".join(f"&{k}={quote(v)}" for k, v in query.items())
        status, _, body = self.fixture.request("GET", target)
        return status, json.loads(body)

    def test_a_folder_lists_and_searches_and_says_why_it_cannot(self):
        folder = Path(self.fixture.tmp.name, "explore")
        (folder / "arm").mkdir(parents=True, exist_ok=True)
        (folder / "arm" / "link.step").write_bytes(b"x")
        self.assertEqual(self.read("folder", folder), (200, {"path": str(folder).replace(os.sep, "/"), "entries": [
            {"name": "arm", "kind": "directory"}], "truncated": False}))
        # With ``q``, the CAD files under it whose path holds it.
        self.assertEqual(self.read("folder", folder, q="LINK")[1]["results"],
                         [str(folder / "arm" / "link.step").replace(os.sep, "/")])
        for query in ({}, {"q": "link"}):
            with self.subTest(query=query):
                self.assertEqual(self.read("folder", "explore", **query)[0], 400)
                self.assertEqual(self.read("folder", folder / "missing", **query)[0], 404)
                self.assertEqual(self.read("folder", folder / "arm" / "link.step", **query)[0], 404)
        with mock.patch("cad_server.viewer.folders.list_folder", side_effect=PermissionError("denied")):
            self.assertEqual(self.read("folder", folder)[0], 403)


class Pick(HttpLayerTestCase):
    """The home's Open: the desktop's chooser, held for the page (and never opened by a test)."""

    def pick(self, **behaviour):
        with mock.patch.object(FilePicker, "choose", **behaviour):
            status, _, body = self.fixture.request("POST", "/api/v1/local/pick", headers={"x-cad-viewer": "1"})
        return status, json.loads(body)

    def test_a_cad_file_is_its_path_and_anything_else_says_why(self):
        chosen = os.path.join(self.fixture.root, "part.step")
        self.assertEqual(self.pick(return_value=chosen), (200, {"path": chosen.replace(os.sep, "/")}))
        self.assertEqual(self.pick(return_value=None), (200, {"cancelled": True}))
        status, answer = self.pick(return_value=os.path.join(self.fixture.root, "notes.txt"))
        self.assertEqual(status, 400)
        self.assertIn("notes.txt is not one", answer["error"])
        status, answer = self.pick(side_effect=PickerFailed("no chooser here"))
        self.assertEqual((status, answer["error"]), (500, "no chooser here"))
        self.assertEqual(self.fixture.request("POST", "/api/v1/local/pick")[0], 403, "a page from another site cannot open it")

    def test_a_second_open_while_one_is_up_says_so(self):
        opened, release, answers = threading.Event(), threading.Event(), []

        def run(argv, **_):
            opened.set()
            release.wait(10)
            return subprocess.CompletedProcess(argv, 1, b"", b"")  # the person cancelled

        with mock.patch("cad_server._internal.picker._command", return_value=(["chooser"], {}, False)), \
                mock.patch("cad_server._internal.picker.subprocess.run", side_effect=run):
            first = threading.Thread(target=lambda: answers.append(
                self.fixture.request("POST", "/api/v1/local/pick", headers={"x-cad-viewer": "1"})[0]))
            first.start()
            self.assertTrue(opened.wait(10))
            second = self.fixture.request("POST", "/api/v1/local/pick", headers={"x-cad-viewer": "1"})
            release.set()
            first.join(10)
        self.assertEqual((second[0], json.loads(second[2])["error"]), (500, "A file chooser is already open."))
        self.assertEqual(answers, [200])


class StaticDistAndSpa(HttpLayerTestCase):
    def test_root_serves_index_html(self):
        status, headers, body = self.fixture.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/html; charset=utf-8")
        self.assertIn(b"<!doctype html>", body)

    def test_unknown_path_falls_back_to_the_spa(self):
        status, _, body = self.fixture.request("GET", "/Users/someone/models")
        self.assertEqual(status, 200)
        self.assertIn(b"<!doctype html>", body)

    def test_existing_asset_is_served_with_its_type(self):
        status, headers, body = self.fixture.request("GET", "/assets/app.js")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/javascript; charset=utf-8")
        self.assertEqual(body, b"export const x = 1;\n")

    def test_a_missing_hashed_asset_is_404_not_html(self):
        # If this fell back to index.html the browser's module loader would
        # report a syntax error instead of a status anyone can read.
        status, headers, body = self.fixture.request("GET", "/assets/missing.js")
        self.assertEqual(status, 404)
        self.assertEqual(headers["content-type"], "text/plain; charset=utf-8")
        self.assertEqual(body, b"Not found")

    def test_fonts_and_their_notices_are_typed(self):
        from cad_server.viewer.content_types import content_type_for_static_asset
        self.assertEqual(content_type_for_static_asset("assets/fonts/a.woff2"), "font/woff2")
        self.assertEqual(content_type_for_static_asset("assets/fonts/a.ttf"), "font/ttf")
        self.assertEqual(content_type_for_static_asset("assets/licenses/NOTICE.txt"), "text/plain; charset=utf-8")

    def test_unknown_extension_gets_no_content_type_at_all(self):
        status, headers, _ = self.fixture.request("GET", "/weird.xyz")
        self.assertEqual(status, 200)
        self.assertNotIn("content-type", {k.lower() for k in headers})

    def test_malformed_percent_escape_is_400_with_no_content_type(self):
        status, headers, body = self.fixture.request("GET", "/assets/%zz.js")
        self.assertEqual(status, 400)
        self.assertEqual(body, b"Bad request")
        self.assertNotIn("content-type", {k.lower() for k in headers})

    def test_overlong_utf8_and_lone_surrogate_also_400(self):
        for target in ("/assets/%C0%AF.js", "/assets/%ED%A0%80.js"):
            with self.subTest(target=target):
                status, _, _ = self.fixture.request("GET", target)
                self.assertEqual(status, 400)

    def test_encoded_traversal_out_of_dist_is_403_with_no_content_type(self):
        status, headers, body = self.fixture.request("GET", "/assets/%2e%2e%2f%2e%2e%2fetc%2fpasswd")
        self.assertEqual(status, 403)
        self.assertEqual(body, b"Forbidden")
        self.assertNotIn("content-type", {k.lower() for k in headers})

    def test_unknown_api_route_is_404_json_never_the_spa(self):
        for path in ("/api/v1/nope", "/api/v2/server", "/api/doc/x", "/api", "/api/v1/documents/x/y/z/w"):
            with self.subTest(path=path):
                status, headers, body = self.fixture.request("GET", path)
                self.assertEqual(status, 404)
                self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
                answer = json.loads(body)
                self.assertEqual(set(answer), {"error", "hint"})
        self.assertEqual(json.loads(self.fixture.request("GET", "/api/v1/nope")[2]),
                         {"error": "no route /api/v1/nope",
                          "hint": "the engine's routes are under /api/v1; GET /api/v1/server says what this engine reads"})

    def test_a_null_byte_in_the_path_does_not_500(self):
        status, _, body = self.fixture.request("GET", "/index.html%00.js")
        self.assertEqual(status, 200)
        self.assertIn(b"<!doctype html>", body)

    def test_authority_form_targets_route_on_the_path_only(self):
        raw = self.fixture.raw(
            b"GET //evil.example/api/v1/server HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
        )
        self.assertIn(b"200 OK", raw.split(b"\r\n")[0])
        self.assertIn(b'"app":"cad-viewer"', raw)


class NoDistConfigured(unittest.TestCase):
    def test_every_page_path_is_404_when_no_client_is_built(self):
        fixture = ServerFixture(with_dist=False)
        try:
            status, _, _ = fixture.request("GET", "/")
            self.assertEqual(status, 404)
            status, _, _ = fixture.request("GET", "/api/v1/server")
            self.assertEqual(status, 200)
        finally:
            fixture.close()


class Streaming(unittest.TestCase):
    def test_atomic_replacement_before_open_uses_the_open_file_length(self):
        from cad_server.viewer.response import Response
        from cad_server.mcp.tunnel import ViewerTunnel
        import base64

        fixture = ServerFixture()
        original = Response.stream_file
        model = Path(fixture.root, "part.stl")
        url = f"/api/v1/local/files?path={quote(str(model), safe='')}"
        try:
            for payload in (b"small", b"larger replacement" * 8):
                for via_tunnel in (False, True):
                    with self.subTest(length=len(payload), tunnel=via_tunnel):
                        model.write_bytes(b"original contents")

                        def replace(response, path, stat_result, *args):
                            pending = Path(path).with_suffix(".pending")
                            pending.write_bytes(payload)
                            os.replace(pending, path)
                            return original(response, path, stat_result, *args)

                        with mock.patch.object(Response, "stream_file", replace):
                            if via_tunnel:
                                reply = ViewerTunnel().serve(method="GET", url=url, headers={}, body=b"")
                                status, headers, body = reply["status"], reply["headers"], base64.b64decode(reply["body"])
                            else:
                                conn = http.client.HTTPConnection("127.0.0.1", fixture.port, timeout=1)
                                try:
                                    conn.request("GET", url)
                                    reply = conn.getresponse()
                                    status, headers, body = reply.status, dict(reply.getheaders()), reply.read()
                                finally:
                                    conn.close()
                        self.assertEqual((status, int(headers["content-length"]), body), (200, len(payload), payload))
        finally:
            fixture.close()

    def test_atomic_replacement_after_headers_keeps_the_open_inode_and_etag(self):
        from cad_server.viewer.response import Response
        from cad_server.mcp.tunnel import ViewerTunnel
        import base64

        fixture = ServerFixture()
        model = Path(fixture.root, "part.stl")
        payload = b"original contents"
        model.write_bytes(payload)
        stat = model.stat()
        original = Response._begin

        def replace(response, status, headers):
            original(response, status, headers)
            pending = model.with_suffix(".pending")
            pending.write_bytes(b"replacement contents")
            try:
                os.replace(pending, model)
            except PermissionError:
                # Windows refuses to replace a file a handle holds open (cadgen's own
                # atomic_replace waits that out); the open stream keeps the original
                # bytes on either platform, which is what this pins.
                if os.name != "nt":
                    raise

        try:
            with mock.patch.object(Response, "_begin", replace):
                reply = ViewerTunnel().serve(method="GET", url=f"/api/v1/local/files?path={quote(str(model), safe='')}", headers={"range": "bytes=1-4"}, body=b"")
                status, headers, body = reply["status"], reply["headers"], base64.b64decode(reply["body"])
            self.assertEqual((status, body), (206, payload[1:5]))
            self.assertEqual(headers["etag"], f'"{stat.st_ino:x}-{stat.st_size:x}-{stat.st_mtime_ns:x}"')
        finally:
            fixture.close()

    def test_a_large_file_streams_with_an_accurate_content_length(self):
        fixture = ServerFixture()
        try:
            payload = os.urandom(3 * 1024 * 1024)
            Path(fixture.dist, "assets", "big.bin").write_bytes(payload)
            status, headers, body = fixture.request("GET", "/assets/big.bin")
            self.assertEqual(status, 200)
            self.assertEqual(int(headers["content-length"]), len(payload))
            self.assertEqual(body, payload)
        finally:
            fixture.close()

    def test_head_returns_the_same_headers_and_no_body(self):
        fixture = ServerFixture()
        try:
            _, get_headers, get_body = fixture.request("GET", "/assets/app.js")
            status, head_headers, head_body = fixture.request("HEAD", "/assets/app.js")
            self.assertEqual(status, 200)
            self.assertEqual(head_body, b"")
            self.assertEqual(head_headers["content-length"], get_headers["content-length"])
            self.assertEqual(head_headers["content-type"], get_headers["content-type"])
            self.assertNotEqual(get_body, b"")
        finally:
            fixture.close()


class MethodHandling(HttpLayerTestCase):
    def test_unsupported_methods_answer_405_rather_than_hanging(self):
        # The one deliberate behaviour change in the port: the Node server
        # dropped handle()'s false return and these stalled until Node's 300s
        # requestTimeout. A method no route takes is refused before any route runs.
        for method in ("OPTIONS", "TRACE"):
            with self.subTest(method=method):
                status, headers, body = self.fixture.request(method, "/api/v1/server")
                self.assertEqual(status, 405)
                self.assertEqual(body, b"")
                self.assertEqual(headers["content-length"], "0")
                self.assertNotIn("content-type", {k.lower() for k in headers})

    def test_a_route_asked_with_another_method_answers_405_naming_its_own(self):
        for method, path, allowed in (("GET", "/api/v1/local/pick", "POST"), ("GET", "/api/v1/local/reveal", "POST"),
                                      ("POST", "/api/v1/server", "GET, HEAD"), ("PUT", "/api/v1/server", "GET, HEAD"),
                                      ("DELETE", "/api/v1/settings", "GET, PUT, HEAD"),
                                      ("PUT", "/api/v1/documents", "GET, POST, PATCH, HEAD"),
                                      ("POST", "/app", "GET, HEAD")):
            with self.subTest(method=method, path=path):
                status, headers, body = self.fixture.request(method, path, headers={"x-cad-viewer": "1"})
                self.assertEqual(status, 405)
                self.assertEqual(headers["allow"], allowed)
                self.assertEqual(json.loads(body), {"error": f"{method} is not allowed on {path}",
                                                    "hint": "use " + " or ".join(allowed.removesuffix(", HEAD").split(", "))})

    def test_unknown_post_route_is_json_404(self):
        for path in ("/api/v1/export", "/nope"):
            with self.subTest(path=path):
                status, headers, body = self.fixture.request("POST", path, headers={"x-cad-viewer": "1"})
                self.assertEqual(status, 404)
                self.assertEqual(json.loads(body)["error"], f"no route {path}" if path == "/api/v1/export" else "no route POST /nope")
                self.assertNotIn("allow", headers)
                self.assertIn("application/json", headers["content-type"])


class HeaderContract(HttpLayerTestCase):
    """Raw-socket assertions about headers that are ABSENT."""

    def _raw_headers(self, request_line_and_headers):
        raw = self.fixture.raw(request_line_and_headers)
        head = raw.split(b"\r\n\r\n", 1)[0]
        lines = head.split(b"\r\n")
        status = lines[0]
        names = {line.split(b":", 1)[0].strip().lower() for line in lines[1:] if b":" in line}
        return status, names, head

    def test_no_server_header_anywhere(self):
        for target in (b"/", b"/api/v1/server", b"/assets/missing.js", b"/api/v1/nope", b"/nope"):
            with self.subTest(target=target):
                _, names, head = self._raw_headers(
                    b"GET " + target + b" HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
                )
                self.assertNotIn(b"server", names, head)

    def test_date_is_present_everywhere(self):
        for target in (b"/", b"/api/v1/server", b"/api/v1/nope"):
            with self.subTest(target=target):
                _, names, head = self._raw_headers(
                    b"GET " + target + b" HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
                )
                self.assertIn(b"date", names, head)

    def test_no_route_ever_emits_text_html_except_the_spa(self):
        # BaseHTTPRequestHandler's default send_error emits a 361-byte
        # text/html body with a header set that appears nowhere else.
        probes = [
            b"GET /api/v1/nope HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            b"GET /assets/missing.js HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            b"OPTIONS / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            b"BOGUS / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            b"GET / HTTP/9.9\r\nHost: 127.0.0.1\r\n\r\n",
            b"\r\n\r\n",
        ]
        for request_bytes in probes:
            with self.subTest(request=request_bytes[:40]):
                raw = self.fixture.raw(request_bytes)
                self.assertNotIn(b"text/html", raw.lower(), raw[:400])
                self.assertNotIn(b"<!DOCTYPE HTML", raw)

    def test_an_http_0_9_request_still_gets_a_framed_response(self):
        # The stdlib suppresses the status line entirely for HTTP/0.9, so a
        # bare "GET /" would otherwise come back as a naked body. This request
        # legitimately reaches the SPA, so text/html is the right answer here.
        raw = self.fixture.raw(b"GET /\r\n\r\n")
        self.assertTrue(raw.startswith(b"HTTP/1."), raw[:120])
        self.assertIn(b"content-type: text/html; charset=utf-8", raw)

    def test_an_unknown_method_answers_405_with_a_bare_header_set(self):
        status, names, head = self._raw_headers(b"BOGUS / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        self.assertIn(b"405", status)
        self.assertEqual(names, {b"date", b"allow", b"content-length"}, head)

    def test_a_bad_http_version_answers_bare_and_closes(self):
        status, names, head = self._raw_headers(b"GET / HTTP/9.9\r\nHost: 127.0.0.1\r\n\r\n")
        self.assertIn(b"HTTP/1.", status)
        self.assertEqual(names, {b"date", b"content-length"}, head)


class KeepAlive(HttpLayerTestCase):
    """The highest-risk framing detail in the port.

    A POST answered without its body read (one to a route that is not there)
    leaves the body unread.
    Node discards them harmlessly; an HTTP/1.1 handler that leaves
    content-length bytes in the buffer mis-parses the NEXT request on that
    connection. It never shows up in single-request tests — only as intermittent
    garbage under the client's parallel component fetches.
    """

    def test_an_undrained_post_body_does_not_desync_the_next_request(self):
        raw = self.fixture.raw(
            b"POST /api/v1/nope?file=/x.step HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\nx-cad-viewer: 1\r\nContent-Length: 5\r\n\r\nHELLO"
            b"GET /api/v1/server HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            reads=2,
        )
        self.assertNotIn(b"Unsupported method", raw)
        self.assertNotIn(b"HELLOGET", raw)
        self.assertEqual(raw.count(b"HTTP/1.1 "), 2, raw[:600])
        self.assertIn(b'"app":"cad-viewer"', raw)

    def test_a_head_does_not_ship_a_body_and_desync_the_next_request(self):
        raw = self.fixture.raw(
            b"HEAD /assets/app.js HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
            b"GET /api/v1/server HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            reads=2,
        )
        self.assertNotIn(b"export const x", raw)
        self.assertEqual(raw.count(b"HTTP/1.1 "), 2, raw[:600])
        self.assertIn(b'"app":"cad-viewer"', raw)

    def test_two_plain_gets_share_one_connection(self):
        raw = self.fixture.raw(
            b"GET /api/v1/server HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
            b"GET /assets/app.js HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            reads=2,
        )
        self.assertEqual(raw.count(b"HTTP/1.1 "), 2, raw[:400])
        self.assertIn(b"export const x = 1;", raw)


class RequestBodies(HttpLayerTestCase):
    def test_a_body_cap_precedes_the_body_read_and_closes_the_connection(self):
        from cad_server.viewer.http_app import _LIBRARY_BODY_LIMIT

        for method, path, limit in (("PUT", "/api/v1/settings", 4096),
                                    ("PATCH", "/api/v1/documents", _LIBRARY_BODY_LIMIT)):
            with self.subTest(path=path):
                raw = self.fixture.raw(
                    f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                    f"x-cad-viewer: 1\r\nContent-Length: {limit + 1}\r\n\r\n".encode()
                )
                self.assertIn(b"413", raw.split(b"\r\n")[0])
                self.assertIn(b"connection: close", raw.lower())

    def test_a_refused_body_is_read_before_the_close_so_its_answer_arrives(self):
        # A socket closed with bytes unread is reset, and the reset takes the 413 with it: on
        # Windows even for a small body, anywhere for one the client is still writing.
        body = b"x" * (1 << 20)
        sock = socket.create_connection(("127.0.0.1", self.fixture.port), timeout=10)
        received = b""
        try:
            sock.sendall(b"POST /api/v1/local/reveal HTTP/1.1\r\nHost: 127.0.0.1\r\nx-cad-viewer: 1\r\n"
                         + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
            while chunk := sock.recv(65536):
                received += chunk
        finally:
            sock.close()
        self.assertTrue(received.startswith(b"HTTP/1.1 413"), received[:200])

    def test_a_chunked_body_is_refused_deliberately(self):
        # The stdlib decodes no chunked framing at all: a body it cannot frame is
        # refused before any route reads a mangled one.
        raw = self.fixture.raw(
            b"POST /api/v1/documents HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\nx-cad-viewer: 1\r\nTransfer-Encoding: chunked\r\n\r\n"
            b"5\r\nHELLO\r\n0\r\n\r\n"
        )
        self.assertIn(b"400", raw.split(b"\r\n")[0])
        self.assertIn(b"chunked", raw)

    def test_an_over_cap_content_length_is_answered_before_the_close(self):
        # Node's req.destroy() races the 400 and the client usually never sees
        # it. Answer first, then close.
        oversize = handler_module.MAX_REQUEST_BODY_BYTES + 1
        raw = self.fixture.raw(
            b"POST /api/v1/documents HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            b"x-cad-viewer: 1\r\nContent-Length: " + str(oversize).encode() + b"\r\n\r\n"
        )
        self.assertIn(b"400", raw.split(b"\r\n")[0])
        self.assertIn(b"request body too large", raw)


class EngineClientFollowsARestartedEngine(unittest.TestCase):
    """A long-lived client (the MCP stdio peer) holds the engine's endpoint; an engine restarted on
    the same --port has a new token, and the client's next call asks the engine for it."""

    def test_a_refused_token_is_asked_again_once(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        from cad_mcp import engine as engine_client

        class Engine(BaseHTTPRequestHandler):
            def do_GET(self):
                ok = self.headers.get("Authorization") == "Bearer new"
                body = b"{}" if ok else b'{"error":"engine token required"}'
                self.send_response(200 if ok else 403)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Engine)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}"
        answers = [{"url": url, "token": "old"}, {"url": url, "token": "new"}]
        with mock.patch.object(engine_client, "request", side_effect=lambda _message, start=True: answers.pop(0)):
            client = engine_client.EngineClient()
            self.assertEqual(client.call("GET", "/api/v1/server")[0], 200)
            self.assertEqual(client.endpoint["token"], "new")


if __name__ == "__main__":
    unittest.main()
