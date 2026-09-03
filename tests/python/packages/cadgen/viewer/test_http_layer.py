"""Black-box HTTP against a real launched server.

Several of these are RAW SOCKET tests rather than urllib ones. That is not
fussiness: the contract pins the ABSENCE of headers (no ``Server``, no
``Access-Control-*``, no ``content-type`` on the bare responses) and the
framing of consecutive requests on one connection, and neither is visible to a
status-code assertion.
"""

from __future__ import annotations

import http.client
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from cadgen.viewer import handler as handler_module
from cadgen.viewer.http_app import create_cad_app, host_is_allowed, hostname_only


class ServerFixture:
    """A CadApp on an ephemeral loopback port, torn down on exit."""

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
        self.app = create_cad_app(root=self.root, host=host, port=0, dist_dir=self.dist)
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
        for path in ("/", "/assets/app.js", "/__cad/catalog", "/__tess_cache/a.tess", "/__cad/nope"):
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
        import json

        status, headers, body = self.fixture.request("GET", "/__cad/server")
        self.assertEqual(status, 200)
        info = json.loads(body)
        self.assertEqual(info["app"], "cad-viewer")
        self.assertEqual(info["backend"], "local-fs")
        self.assertEqual(info["serverMode"], "serve")
        self.assertEqual(info["serverFeatures"], ["path-directory"])
        self.assertEqual(info["stepArtifactGenerationAvailable"], False)
        self.assertEqual(info["pid"], os.getpid())
        self.assertEqual(info["port"], self.fixture.port)
        self.assertEqual(info["rootPath"], self.fixture.root)
        self.assertEqual(info["rootName"], "models")
        self.assertFalse(info["url"].endswith("/"), "serverInfo.url carries NO trailing slash")
        self.assertEqual(headers["cache-control"], "no-store")

    def test_the_key_order_is_the_shipped_one(self):
        _, _, body = self.fixture.request("GET", "/__cad/server")
        text = body.decode("utf-8")
        order = [
            '"app"', '"viewerVersion"', '"identityToken"', '"serverMode"', '"serverFeatures"', '"backend"',
            '"rootPath"', '"rootName"', '"port"', '"pid"',
            '"stepArtifactGenerationAvailable"',
            '"packageDir"', '"startedAt"', '"url"',
        ]
        positions = [text.index(key) for key in order]
        self.assertEqual(positions, sorted(positions))

    def test_json_is_compact_and_not_ascii_escaped(self):
        _, _, body = self.fixture.request("GET", "/__cad/server")
        self.assertNotIn(b", ", body)
        self.assertNotIn(b'": ', body)

    def test_the_file_param_the_client_sends_is_ignored(self):
        status, _, _ = self.fixture.request("GET", "/__cad/server?file=/anything.step")
        self.assertEqual(status, 200)


class ArtifactBuildPayload(HttpLayerTestCase):
    """``ref`` and ``catalog`` describe the SAME moment.

    The Node backend took ``ref`` from a scan made BEFORE the build and
    ``catalog`` from one made after, so a cold import shipped a pre-import ref
    (no ``&v=`` cache-buster) inside a post-import catalog. This backend takes
    one post-build scan and derives both from it: the import is exactly the
    event that changes this entry's URL, and one payload cannot honestly
    describe two moments.

    An ``.stl`` is the subject on purpose — ``build_artifact`` answers "ready"
    for an unowned entry without touching the kernel, so this pins the payload
    shape rather than exercising a compile.
    """

    def test_ref_is_the_url_of_the_entry_in_the_attached_catalog(self):
        import json as json_module

        target = os.path.join(self.fixture.root, "part.stl")
        Path(target).write_text("solid part\nendsolid part\n", encoding="utf-8")
        status, _, body = self.fixture.request(
            "POST",
            f"/__cad/artifact?file={target}",
            headers={"x-cadgen-viewer": "1"},
        )
        self.assertEqual(status, 200, body[:400])
        payload = json_module.loads(body)
        self.assertEqual(payload["state"], "ready")
        entry = next(
            e for e in payload["catalog"]["entries"] if e["rootRelativeFile"] == "part.stl"
        )
        self.assertTrue(payload["ref"])
        self.assertEqual(payload["ref"], entry["url"])


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
            ("GET", "/__tess_cache/a.tess", {}),
        ]:
            with self.subTest(method=method, path=path):
                _, _, body = self.fixture.request(method, path, headers=headers)
                self.assertNotIn(b"not yet ported", body)


if __name__ == "__main__":
    unittest.main()
