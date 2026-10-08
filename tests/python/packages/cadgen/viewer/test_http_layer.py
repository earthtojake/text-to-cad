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

from cadgen._internal.picker import FilePicker, PickerFailed
from cadgen.viewer import handler as handler_module
from cadgen.viewer import reload as reload_module
from cadgen.viewer.http_app import create_cad_app, host_is_allowed, hostname_only


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
        """Send raw bytes on one connection and read back ``reads`` responses."""
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
                status, _, _ = self.fixture.request("GET", "/__cad/server", headers={"Host": value})
                self.assertEqual(status, 200)

    def test_non_local_name_is_refused_with_the_exact_message(self):
        status, headers, body = self.fixture.request(
            "GET", "/__cad/server", headers={"Host": "attacker.example"}
        )
        self.assertEqual(status, 403)
        self.assertEqual(
            body.decode("utf-8"),
            '{"error":"Host header \'attacker.example\' is not a local name; '
            'refusing (DNS-rebinding defense)"}',
        )
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assertEqual(headers["cache-control"], "no-store")

    def test_the_sanitised_name_is_interpolated_not_the_raw_header(self):
        _, _, body = self.fixture.request("GET", "/__cad/server", headers={"Host": "EVIL.example:8443"})
        self.assertIn(b"'evil.example'", body)

    def test_the_gate_covers_every_route(self):
        for path in ("/", "/assets/app.js", "/__cad/catalog", "/__tess_cache/a.glb", "/__cad/nope"):
            with self.subTest(path=path):
                status, _, _ = self.fixture.request("GET", path, headers={"Host": "attacker.example"})
                self.assertEqual(status, 403)

    def test_head_is_gated_too(self):
        status, _, _ = self.fixture.request("HEAD", "/__cad/server", headers={"Host": "attacker.example"})
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
        status, _, body = self.fixture.request("POST", "/__cad/artifact")
        self.assertEqual(status, 403)
        self.assertEqual(
            body.decode("utf-8"),
            '{"error":"missing x-cadgen-viewer header (cross-site POST blocked); '
            "send 'x-cadgen-viewer: 1'\"}",
        )

    def test_an_empty_value_is_falsy_and_refused(self):
        status, _, _ = self.fixture.request("POST", "/__cad/artifact", headers={"x-cadgen-viewer": ""})
        self.assertEqual(status, 403)

    def test_the_gate_runs_before_dispatch_so_unknown_routes_are_covered(self):
        status, _, _ = self.fixture.request("POST", "/anything/at/all")
        self.assertEqual(status, 403)

    def test_host_gate_wins_over_the_header_gate(self):
        status, _, body = self.fixture.request(
            "POST", "/__cad/artifact", headers={"Host": "attacker.example", "x-cadgen-viewer": "1"}
        )
        self.assertEqual(status, 403)
        self.assertIn(b"DNS-rebinding", body)

    def test_reads_are_unaffected(self):
        status, _, _ = self.fixture.request("GET", "/__cad/server")
        self.assertEqual(status, 200)


class ServerInfo(HttpLayerTestCase):
    def test_payload(self):
        status, headers, body = self.fixture.request("GET", "/__cad/server")
        self.assertEqual(status, 200)
        info = json.loads(body)
        self.assertEqual(info["app"], "cad-viewer")
        self.assertIn("identityToken", info)
        self.assertIs(info["autoReload"], reload_module.running_from_source_checkout())
        self.assertIn(info["platform"], ("darwin", "win32", "linux"))
        self.assertEqual(info["pid"], os.getpid())
        self.assertEqual(info["port"], self.fixture.port)
        # Where a developer's relative links resolve, spelled with "/". A viewer has no root.
        self.assertEqual(info["start"], self.fixture.root.replace(os.sep, "/"))
        self.assertIsInstance(info["pick"], bool)
        # The display tessellation ladder the page draws STEP models by is cadgen's, and said here.
        from cadgen.tessellation_policy import ladder_payload

        self.assertEqual(info["tessellation"], ladder_payload())
        self.assertEqual(list(info), ["app", "identityToken", "autoReload", "platform", "tessellation", "user",
                                      "start", "pick", "port", "pid"])
        self.assertEqual(headers["cache-control"], "no-store")

    def test_json_is_compact_and_not_ascii_escaped(self):
        _, _, body = self.fixture.request("GET", "/__cad/server")
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
        status, _, _ = self.fixture.request("GET", "/__cad/server?file=/anything.step")
        self.assertEqual(status, 200)


class Catalog(HttpLayerTestCase):
    """A catalog is one file's, named by its absolute path wherever it is: nothing walks a folder."""

    def catalog(self, file=None):
        status, _, body = self.fixture.request(
            "GET", "/__cad/catalog" + ("" if file is None else f"?file={quote(str(file), safe='')}"))
        return status, json.loads(body)

    def test_a_named_file_is_its_one_row_and_no_file_has_none(self):
        # Under a hidden folder, outside the folder the viewer started in: named, so listed.
        part = Path(self.fixture.tmp.name, ".work", "part.stl")
        part.parent.mkdir(exist_ok=True)
        part.write_bytes(b"solid p\nendsolid p\n")
        status, catalog = self.catalog(part)
        self.assertEqual(status, 200)
        self.assertEqual(set(catalog), {"schemaVersion", "entries", "revision"})
        [entry] = catalog["entries"]
        self.assertEqual(entry["file"], str(part).replace(os.sep, "/"))
        self.assertEqual(list(entry), ["file", "kind", "url", "hash", "bytes"])
        # The row's URL is how its bytes are read.
        self.assertEqual(self.fixture.request("GET", entry["url"])[::2], (200, part.read_bytes()))
        part.write_bytes(b"solid moved\nendsolid moved\n")
        self.assertNotEqual(self.catalog(part)[1]["revision"], catalog["revision"])
        for missing in (None, "", str(part.with_name("gone.stl")), str(part.with_suffix(".txt"))):
            with self.subTest(file=missing):
                self.assertEqual(self.catalog(missing)[1]["entries"], [])

    def test_a_file_that_is_not_named_by_its_absolute_path_is_a_400(self):
        status, body = self.catalog("part.stl")
        self.assertEqual(status, 400)
        self.assertIn("absolute path", body["error"])


class ExplorerRoutes(HttpLayerTestCase):
    """The explorer's two reads (``folders.py``) over HTTP: a folder by its absolute path."""

    def read(self, route, path, **query):
        target = f"/__cad/{route}?path={quote(str(path), safe='')}" + "".join(f"&{k}={quote(v)}" for k, v in query.items())
        status, _, body = self.fixture.request("GET", target)
        return status, json.loads(body)

    def test_a_folder_lists_and_searches_and_says_why_it_cannot(self):
        folder = Path(self.fixture.tmp.name, "explore")
        (folder / "arm").mkdir(parents=True, exist_ok=True)
        (folder / "arm" / "link.step").write_bytes(b"x")
        self.assertEqual(self.read("folder", folder), (200, {"path": str(folder).replace(os.sep, "/"), "entries": [
            {"name": "arm", "kind": "directory"}], "truncated": False}))
        self.assertEqual(self.read("search", folder, q="LINK")[1]["results"],
                         [str(folder / "arm" / "link.step").replace(os.sep, "/")])
        for route in ("folder", "search"):
            with self.subTest(route=route):
                self.assertEqual(self.read(route, "explore")[0], 400)
                self.assertEqual(self.read(route, folder / "missing")[0], 404)
                self.assertEqual(self.read(route, folder / "arm" / "link.step")[0], 404)
        with mock.patch("cadgen.viewer.folders.list_folder", side_effect=PermissionError("denied")):
            self.assertEqual(self.read("folder", folder)[0], 403)


class Pick(HttpLayerTestCase):
    """The home's Open: the desktop's chooser, held for the page (and never opened by a test)."""

    def pick(self, **behaviour):
        with mock.patch.object(FilePicker, "choose", **behaviour):
            status, _, body = self.fixture.request("POST", "/__cad/pick", headers={"x-cadgen-viewer": "1"})
        return status, json.loads(body)

    def test_a_cad_file_is_its_path_and_anything_else_says_why(self):
        chosen = os.path.join(self.fixture.root, "part.step")
        self.assertEqual(self.pick(return_value=chosen), (200, {"path": chosen.replace(os.sep, "/")}))
        self.assertEqual(self.pick(return_value=None), (200, {"cancelled": True}))
        status, answer = self.pick(return_value=os.path.join(self.fixture.root, "notes.txt"))
        self.assertEqual(status, 400)
        self.assertIn("notes.txt is not one", answer["error"])
        self.assertEqual(self.pick(side_effect=PickerFailed("no chooser here")), (500, {"error": "no chooser here"}))
        self.assertEqual(self.fixture.request("POST", "/__cad/pick")[0], 403, "a page from another site cannot open it")

    def test_a_second_open_while_one_is_up_says_so(self):
        opened, release, answers = threading.Event(), threading.Event(), []

        def run(argv, **_):
            opened.set()
            release.wait(10)
            return subprocess.CompletedProcess(argv, 1, b"", b"")  # the person cancelled

        with mock.patch("cadgen._internal.picker._command", return_value=(["chooser"], {}, False)), \
                mock.patch("cadgen._internal.picker.subprocess.run", side_effect=run):
            first = threading.Thread(target=lambda: answers.append(
                self.fixture.request("POST", "/__cad/pick", headers={"x-cadgen-viewer": "1"})[0]))
            first.start()
            self.assertTrue(opened.wait(10))
            second = self.fixture.request("POST", "/__cad/pick", headers={"x-cadgen-viewer": "1"})
            release.set()
            first.join(10)
        self.assertEqual((second[0], json.loads(second[2])), (500, {"error": "A file chooser is already open."}))
        self.assertEqual(answers, [200])


class ArtifactBuildPayload(HttpLayerTestCase):
    """The build route answers at once: it never holds a request for a build.

    An ``.stl`` is the subject on purpose -- ``build_artifact`` answers "compiled"
    for an unowned entry without touching the kernel, so this pins the payload
    shape rather than exercising a compile (``test_document_compile`` follows a
    compile through the status route).
    """

    def test_an_entry_with_nothing_to_build_answers_compiled_and_nothing_else(self):
        import json as json_module

        target = os.path.join(self.fixture.root, "part.stl")
        Path(target).write_text("solid part\nendsolid part\n", encoding="utf-8")
        status, _, body = self.fixture.request(
            "POST",
            f"/__cad/artifact?file={target}",
            headers={"x-cadgen-viewer": "1"},
        )
        self.assertEqual(status, 200, body[:400])
        self.assertEqual(json_module.loads(body), {"ok": True, "state": "compiled"})


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

    def test_a_drawing_font_the_bundle_leaves_out_is_404_not_html(self):
        # The web bundle ships the drawing editor's fonts without the CJK
        # family; a font loader handed index.html at 200 fails to decode it
        # instead of falling back to a system font.
        status, headers, body = self.fixture.request("GET", "/excalidraw/fonts/Xiaolai/Xiaolai-Regular.woff2")
        self.assertEqual(status, 404)
        self.assertEqual(headers["content-type"], "text/plain; charset=utf-8")
        self.assertEqual(body, b"Not found")

    def test_drawing_fonts_and_their_notices_are_typed(self):
        from cadgen.viewer.content_types import content_type_for_static_asset
        self.assertEqual(content_type_for_static_asset("excalidraw/fonts/Excalifont/a.woff2"), "font/woff2")
        self.assertEqual(content_type_for_static_asset("excalidraw/fonts/Liberation/LiberationSans-Regular.ttf"), "font/ttf")
        self.assertEqual(content_type_for_static_asset("excalidraw/licenses/NOTICE.txt"), "text/plain; charset=utf-8")

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

    def test_plain_dot_segments_are_normalised_before_routing(self):
        # /__cad/../etc/passwd is /etc/passwd, i.e. the SPA, not an API path.
        status, _, body = self.fixture.request("GET", "/__cad/../etc/passwd")
        self.assertEqual(status, 200)
        self.assertIn(b"<!doctype html>", body)

    def test_cad_without_a_trailing_slash_is_the_spa_and_with_one_is_404_json(self):
        status, _, body = self.fixture.request("GET", "/__cad")
        self.assertEqual(status, 200)
        self.assertIn(b"<!doctype html>", body)
        status, _, body = self.fixture.request("GET", "/__cad/")
        self.assertEqual(status, 404)
        self.assertEqual(body, b'{"error":"Not found"}')

    def test_unknown_cad_route_is_404_json_never_the_spa(self):
        status, headers, body = self.fixture.request("GET", "/__cad/nope")
        self.assertEqual(status, 404)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assertEqual(body, b'{"error":"Not found"}')

    def test_a_null_byte_in_the_path_does_not_500(self):
        status, _, body = self.fixture.request("GET", "/index.html%00.js")
        self.assertEqual(status, 200)
        self.assertIn(b"<!doctype html>", body)

    def test_backslash_routes_as_a_slash(self):
        status, _, _ = self.fixture.request("GET", "/__cad\\server")
        self.assertEqual(status, 200)

    def test_authority_form_targets_route_on_the_path_only(self):
        raw = self.fixture.raw(
            b"GET //evil.example/__cad/server HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
        )
        self.assertIn(b"200 OK", raw.split(b"\r\n")[0])
        self.assertIn(b'"app":"cad-viewer"', raw)


class NoDistConfigured(unittest.TestCase):
    def test_every_page_path_is_404_when_no_client_is_built(self):
        fixture = ServerFixture(with_dist=False)
        try:
            status, _, _ = fixture.request("GET", "/")
            self.assertEqual(status, 404)
            status, _, _ = fixture.request("GET", "/__cad/server")
            self.assertEqual(status, 200)
        finally:
            fixture.close()


class Streaming(unittest.TestCase):
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
        # requestTimeout.
        for method in ("OPTIONS", "PUT", "DELETE", "PATCH", "TRACE"):
            with self.subTest(method=method):
                status, headers, body = self.fixture.request(method, "/__cad/server")
                self.assertEqual(status, 405)
                self.assertEqual(body, b"")
                self.assertEqual(headers["content-length"], "0")
                self.assertNotIn("content-type", {k.lower() for k in headers})

    def test_unknown_post_route_is_405_with_allow_post(self):
        status, headers, body = self.fixture.request(
            "POST", "/__cad/export", headers={"x-cadgen-viewer": "1"}
        )
        self.assertEqual(status, 405)
        self.assertEqual(headers["allow"], "POST")
        self.assertEqual(headers["content-length"], "0")
        self.assertEqual(body, b"")
        self.assertNotIn("content-type", {k.lower() for k in headers})


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
        for target in (b"/", b"/__cad/server", b"/assets/missing.js", b"/__cad/nope", b"/nope"):
            with self.subTest(target=target):
                _, names, head = self._raw_headers(
                    b"GET " + target + b" HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
                )
                self.assertNotIn(b"server", names, head)

    def test_date_is_present_everywhere(self):
        for target in (b"/", b"/__cad/server", b"/__cad/nope"):
            with self.subTest(target=target):
                _, names, head = self._raw_headers(
                    b"GET " + target + b" HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
                )
                self.assertIn(b"date", names, head)

    def test_no_access_control_header_on_any_route_or_status(self):
        targets = [
            b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            b"GET /__cad/server HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            b"GET /__cad/server HTTP/1.1\r\nHost: evil.example\r\nConnection: close\r\n\r\n",
            b"POST /__cad/artifact HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            b"OPTIONS / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            b"GET /assets/missing.js HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
        ]
        for request_bytes in targets:
            with self.subTest(request=request_bytes.split(b"\r\n")[0]):
                _, names, head = self._raw_headers(request_bytes)
                self.assertFalse([n for n in names if n.startswith(b"access-control")], head)

    def test_no_route_ever_emits_text_html_except_the_spa(self):
        # BaseHTTPRequestHandler's default send_error emits a 361-byte
        # text/html body with a header set that appears nowhere else.
        probes = [
            b"GET /__cad/nope HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
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

    ``POST /__cad/artifact`` never reads its request body — every parameter
    rides the query string, so a body sent with it goes unread.
    Node discards them harmlessly; an HTTP/1.1 handler that leaves
    content-length bytes in the buffer mis-parses the NEXT request on that
    connection. It never shows up in single-request tests — only as intermittent
    garbage under the client's parallel component fetches.
    """

    def test_an_undrained_post_body_does_not_desync_the_next_request(self):
        raw = self.fixture.raw(
            b"POST /__cad/artifact?file=/x.step HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\nx-cadgen-viewer: 1\r\nContent-Length: 5\r\n\r\nHELLO"
            b"GET /__cad/server HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            reads=2,
        )
        self.assertNotIn(b"Unsupported method", raw)
        self.assertNotIn(b"HELLOGET", raw)
        self.assertEqual(raw.count(b"HTTP/1.1 "), 2, raw[:600])
        self.assertIn(b'"app":"cad-viewer"', raw)

    def test_a_head_does_not_ship_a_body_and_desync_the_next_request(self):
        raw = self.fixture.raw(
            b"HEAD /assets/app.js HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
            b"GET /__cad/server HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            reads=2,
        )
        self.assertNotIn(b"export const x", raw)
        self.assertEqual(raw.count(b"HTTP/1.1 "), 2, raw[:600])
        self.assertIn(b'"app":"cad-viewer"', raw)

    def test_two_plain_gets_share_one_connection(self):
        raw = self.fixture.raw(
            b"GET /__cad/server HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
            b"GET /assets/app.js HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            reads=2,
        )
        self.assertEqual(raw.count(b"HTTP/1.1 "), 2, raw[:400])
        self.assertIn(b"export const x = 1;", raw)


class RequestBodies(HttpLayerTestCase):
    def test_tess_metadata_cap_precedes_body_read_and_closes_the_connection(self):
        from cadgen.viewer.tess_cache import TESS_CACHE_METADATA_MAX_BYTES

        for path, limit in (("/__tess_cache/probe", TESS_CACHE_METADATA_MAX_BYTES),
                            ("/__tess_cache/batch", TESS_CACHE_METADATA_MAX_BYTES),
                            ("/__cad/surfaces", 128 * 1024), ("/__cad/surfaces/cancel", 128 * 1024)):
            with self.subTest(path=path):
                raw = self.fixture.raw(
                    f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                    f"x-cadgen-viewer: 1\r\nContent-Length: {limit + 1}\r\n\r\n".encode()
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
            sock.sendall(b"POST /__cad/reveal HTTP/1.1\r\nHost: 127.0.0.1\r\nx-cadgen-viewer: 1\r\n"
                         + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
            while chunk := sock.recv(65536):
                received += chunk
        finally:
            sock.close()
        self.assertTrue(received.startswith(b"HTTP/1.1 413"), received[:200])

    def test_a_chunked_body_is_refused_deliberately(self):
        # The stdlib decodes no chunked framing at all. Silently mangling a
        # /__tess_cache/batch body would demote the client's provider to
        # per-key gets for the life of the page.
        raw = self.fixture.raw(
            b"POST /__tess_cache/batch HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\nx-cadgen-viewer: 1\r\nTransfer-Encoding: chunked\r\n\r\n"
            b"5\r\nHELLO\r\n0\r\n\r\n"
        )
        self.assertIn(b"400", raw.split(b"\r\n")[0])
        self.assertIn(b"chunked", raw)

    def test_an_over_cap_content_length_is_answered_before_the_close(self):
        # Node's req.destroy() races the 400 and the client usually never sees
        # it. Answer first, then close.
        oversize = handler_module.MAX_REQUEST_BODY_BYTES + 1
        raw = self.fixture.raw(
            b"POST /__tess_cache/batch HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            b"x-cadgen-viewer: 1\r\nContent-Length: " + str(oversize).encode() + b"\r\n\r\n"
        )
        self.assertIn(b"400", raw.split(b"\r\n")[0])
        self.assertIn(b"request body too large", raw)


class EveryRouteAnswersForReal(HttpLayerTestCase):
    def test_tess_get_requires_exact_object_and_admitted_size_before_read(self):
        from urllib.parse import urlencode

        digest = "ab" * 32
        for object_hash, limit in ((None, None), (digest, None), (None, "1"), (digest.upper(), "1"),
                                   (" " + digest, "1"), (digest, "0"), (digest, "-1"),
                                   (digest, "1.5"), (digest, "9007199254740992")):
            query = urlencode({key: value for key, value in (("object", object_hash), ("maxBytes", limit)) if value is not None})
            with self.subTest(object_hash=object_hash, limit=limit), mock.patch(
                "cadgen.viewer.http_app.read_tess_cache_entry", side_effect=AssertionError("unadmitted cache read"),
            ):
                status, _, _ = self.fixture.request("GET", f"/__tess_cache/a.glb?{query}")
            self.assertEqual(status, 400)

    def test_tess_get_uses_the_probed_object_and_byte_limit(self):
        import base64
        import json
        from cadgen.store import meshes
        from tests.python.support.tessellation import tessellation_fixture

        fixture = tessellation_fixture()
        payload = base64.b64decode(fixture["bytes"])
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(Path(self.fixture.root) / "store")}):
            row = meshes.write(fixture["key"], payload)
            status, _, body = self.fixture.request("POST", "/__tess_cache/probe", headers={"x-cadgen-viewer": "1"},
                                                 body=json.dumps({"tessellationInputs": [fixture["key"]]}).encode())
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["entries"][fixture["key"]], row)
            route = f"/__tess_cache/{fixture['key']}.glb?object={row['object']}&maxBytes={row['byteLength']}"
            status, headers, body = self.fixture.request("GET", route)
            self.assertEqual((status, body), (200, payload))
            self.assertEqual({name.lower(): value for name, value in headers.items()}.get("content-type"), "model/gltf-binary")
            # cadgen writes every mesh: a client's write is refused, and changes nothing.
            status, headers, _ = self.fixture.request("POST", f"/__tess_cache/{fixture['key']}.glb",
                                                      headers={"x-cadgen-viewer": "1"}, body=payload)
            self.assertEqual(status, 405)
            self.assertEqual(meshes.probe(fixture["key"]), row)

    def test_no_route_reports_itself_as_unported(self):
        # This class used to list the routes still awaiting their step, each
        # answering 501 with a distinctive body so a missing route could never
        # be mistaken for a working one. The list is empty: the assertion now
        # runs the other way, and no route may ever reintroduce that marker.
        for method, path, headers in [
            ("GET", "/__cad/server", {}),
            ("GET", "/__cad/catalog", {}),
            ("GET", "/__cad/artifact?file=x.step", {}),
            ("POST", "/__cad/artifact?file=x.step", {"x-cadgen-viewer": "1"}),
            ("GET", "/__cad/asset?file=/x.step", {}),
            ("GET", "/__cad/store?file=x", {}),
            ("GET", "/__tess_cache/a.glb", {}),
        ]:
            with self.subTest(method=method, path=path):
                _, _, body = self.fixture.request(method, path, headers=headers)
                self.assertNotIn(b"not yet ported", body)


if __name__ == "__main__":
    unittest.main()
