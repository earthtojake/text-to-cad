"""What the asset routes will send, and the gates every route keeps.

There is no served directory: a file is named by its absolute path, wherever it is
(``cadgen.viewer.backend``). What IS refused is a ref that is not an absolute path (400), and
anything that would leave as bytes without being a CAD file or its sidecar (404). Every denial
asserts BOTH the status and that the secret bytes are absent — a denial that 404s for the wrong
reason passes vacuously otherwise.

Probe files use ``.step``, never ``.txt``, where a test is about a path: ``is_served_cad_asset``
filters by EXTENSION, so a ``.txt`` probe 404s on the extension and proves nothing else.
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import quote

from cadgen.viewer import handler as handler_module
from cadgen.viewer.http_app import create_cad_app
from cadgen.viewer.store_paths import result_tree

from tests.python.support.store_fixtures import seed_result

SECRET = "TOP-SECRET-BYTES"


class AttackFixture:
    """``base/project`` plus a store, behind a live server."""

    def __init__(self):
        self.base = tempfile.mkdtemp()
        self.root = os.path.join(self.base, "project")
        os.makedirs(self.root)
        self.cache = os.path.join(self.base, "cache")
        os.makedirs(self.cache)
        self._previous_cache = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = self.cache

        self.write("ok.step", "public step\n")
        self.write("ok.stl", "solid public\n")
        self.write("robot.urdf", '<robot name="r" xmlns:h="http://www.w3.org/1999/xhtml"><h:script>fetch("/__cad/analytics")</h:script></robot>')
        self.write("part.step.json", '{"kinematics":{}}')
        self.write("secrets.json", f'{{"token":"{SECRET}"}}')
        self.write(".env", f"TOKEN={SECRET}\n")
        self.write("id_rsa", SECRET)
        self.write("model.py", f"# {SECRET}\n")
        self.write("loose.js", f"// {SECRET}\n")
        self.write("part.anim.js", f"// {SECRET}\n")
        self.write(".dotfile.step", SECRET)
        self.write(".worktree/inside.step", "under a hidden folder\n")
        os.makedirs(os.path.join(self.root, "dir.step"))

        # A real result in the store: the tree hash is what the store route serves.
        self.package_name = seed_result(
            Path(self.root, "part.step"), {"kind": "assembly-package", "components": {"c0": {}}}
        )
        from cadgen.store.trees import get_tree
        from cadgen.store.objects import read_verified_object
        from tests.python.support.store_fixtures import FIXTURE_SURFACE_PRODUCER
        self.component_name, component = next(iter(get_tree(self.package_name)["components"].items()))
        self.component_payload = read_verified_object(component["brep"])
        self.store_binding = "&surfaceProducer=" + quote(json.dumps(FIXTURE_SURFACE_PRODUCER))

        self.dist = os.path.join(self.base, "dist")
        os.makedirs(os.path.join(self.dist, "assets"))
        Path(self.dist, "index.html").write_text("<!doctype html><title>cad</title>", encoding="utf-8")
        Path(self.dist, "assets", "app.js").write_text("export const x = 1;\n", encoding="utf-8")

        self.app = create_cad_app(host="127.0.0.1", port=0, dist_dir=self.dist, start=self.root)
        self.server = handler_module.serve(self.app, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        self.app.port = self.port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def write(self, rel: str, text: str) -> str:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Bytes, not text mode: served bodies are asserted byte-exact, and
        # text mode would write \r\n on Windows.
        Path(path).write_bytes(text.encode("utf-8"))
        return path

    def path(self, rel: str) -> str:
        return os.path.join(self.root, rel)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self._previous_cache is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = self._previous_cache
        shutil.rmtree(self.base, ignore_errors=True)

    def request(self, method, target, *, headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest(method, target, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", f"127.0.0.1:{self.port}")
            for name, value in (headers or {}).items():
                conn.putheader(name, value)
            conn.endheaders(body)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def asset(self, file_param):
        return self.request("GET", f"/__cad/asset?file={quote(str(file_param), safe='')}")


class SecurityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = AttackFixture()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.close()

    def assertDenied(self, status, body, expected):
        self.assertIn(status, expected, body[:400])
        self.assertNotIn(SECRET.encode("ascii"), body)


class ControlCases(SecurityTestCase):
    """Without these, every denial below could be passing for the wrong reason."""

    def test_a_step_serves(self):
        status, headers, body = self.fixture.asset(self.fixture.path("ok.step"))
        self.assertEqual(status, 200)
        self.assertEqual(body, b"public step\n")
        self.assertEqual(headers["content-type"], "application/step")
        self.assertEqual(headers["cache-control"], "no-store")
        # The viewer serves bytes to render, never a save-as: no route attaches.
        self.assertNotIn("content-disposition", {k.lower() for k in headers})

    def test_a_source_sidecar_serves(self):
        status, headers, _ = self.fixture.asset(self.fixture.path("part.step.json"))
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")

    def test_the_store_route_serves_a_component(self):
        status, headers, body = self.fixture.request(
            "GET", f"/__cad/store?file={self.fixture.package_name}/components/{self.fixture.component_name}.brep"
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, self.fixture.component_payload)
        self.assertEqual(headers["content-type"], "application/octet-stream")
        self.assertNotIn("content-disposition", {k.lower() for k in headers})


class RawFilesAreNeverPages(SecurityTestCase):
    def test_a_project_file_opened_as_a_page_runs_nothing(self):
        # A robot description's XML can carry an XHTML <script>: opened straight in the browser, a
        # project's file is a sandboxed document with no script and an origin of its own.
        sandbox = ("nosniff", "default-src 'none'; sandbox")
        status, headers, _ = self.fixture.asset(self.fixture.path("robot.urdf"))
        self.assertEqual((status, headers["content-type"]), (200, "application/xml; charset=utf-8"))
        self.assertEqual((headers["x-content-type-options"], headers["content-security-policy"]), sandbox)
        status, headers, _ = self.fixture.request(
            "GET", f"/__cad/store?file={self.fixture.package_name}/components/{self.fixture.component_name}.brep"
        )
        self.assertEqual((status, headers["x-content-type-options"], headers["content-security-policy"]), (200, *sandbox))
        # The viewer's own page is the app, never sandboxed.
        status, headers, _ = self.fixture.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertNotIn("content-security-policy", {name.lower() for name in headers})


class FilesByAbsolutePath(SecurityTestCase):
    def test_a_file_is_served_wherever_it_is_when_named_by_its_absolute_path(self):
        # A hidden FOLDER on the way is no reason to refuse a file that is named; dot segments
        # collapse before anything is read.
        status, _, body = self.fixture.asset(self.fixture.path(".worktree/inside.step"))
        self.assertEqual((status, body), (200, b"under a hidden folder\n"))
        status, _, body = self.fixture.asset(self.fixture.root + "/.worktree/../ok.step")
        self.assertEqual((status, body), (200, b"public step\n"))

    def test_a_ref_that_is_not_an_absolute_path_is_a_400(self):
        refs = ["ok.step", "../project/ok.step", "\\\\server\\share\\x.step", "//server/share/x.step" if os.name == "nt" else "C:\\x.step"]
        for ref in refs:
            with self.subTest(ref=ref):
                status, _, body = self.fixture.asset(ref)
                self.assertDenied(status, body, {400})
        for target in ("/__cad/asset", "/__cad/asset?file=", "/__cad/asset?v=1"):
            with self.subTest(target=target):
                self.assertEqual(self.fixture.request("GET", target)[0], 400)

    def test_a_null_byte_is_a_400_with_the_exact_message(self):
        status, _, body = self.fixture.request("GET", "/__cad/asset?file=%2Froot%2Fok.step%00.png")
        self.assertEqual(status, 400)
        self.assertEqual(body, b'{"error":"File path contains an invalid null byte"}')

    def test_repeated_file_params_take_the_first(self):
        good = quote(self.fixture.path("ok.step"), safe="")
        bad = quote(self.fixture.path(".dotfile.step"), safe="")
        status, _, body = self.fixture.request("GET", f"/__cad/asset?file={good}&file={bad}")
        self.assertEqual((status, body), (200, b"public step\n"))
        status, _, body = self.fixture.request("GET", f"/__cad/asset?file=&v=1&file={bad}")
        self.assertDenied(status, body, {400})

    def test_an_enormous_path_does_not_500(self):
        # Absolute in this platform's spelling (a drive on Windows), so it reaches the file check.
        status, _, _ = self.fixture.asset(os.path.join(os.path.abspath(os.sep), "a" * 5000 + ".step"))
        self.assertEqual(status, 404)

    def test_crlf_in_a_filename_cannot_inject_a_header(self):
        name = "a\r\nX-Evil: 1.step"
        if os.name != "nt":
            # The benign sibling is incidental; on NTFS its ':' would silently
            # create an alternate data stream instead of this file.
            self.fixture.write(name.replace("\r\n", "_"), "x")
        status, headers, _ = self.fixture.asset(self.fixture.path(name))
        self.assertIn(status, {400, 404})
        self.assertNotIn("x-evil", {k.lower() for k in headers})


class OnlyCadBytesLeave(SecurityTestCase):
    def test_configs_secrets_scripts_and_hidden_files_are_never_streamed(self):
        for name in ("secrets.json", ".env", "id_rsa", "model.py", "loose.js", "part.anim.js", ".dotfile.step"):
            with self.subTest(name=name):
                status, _, body = self.fixture.asset(self.fixture.path(name))
                self.assertDenied(status, body, {404})
        # A system file, by its absolute path on this platform: not a CAD file, so never sent.
        system_file = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "win.ini") if os.name == "nt" else "/etc/passwd"
        status, _, _ = self.fixture.asset(system_file)
        self.assertEqual(status, 404)

    def test_a_directory_with_a_served_extension_is_404(self):
        status, _, body = self.fixture.asset(self.fixture.path("dir.step"))
        self.assertDenied(status, body, {404})

    def test_the_sidecar_allowlist_is_the_pair_of_suffixes_not_dot_json(self):
        status, _, _ = self.fixture.asset(self.fixture.path("part.step.json"))
        self.assertEqual(status, 200)
        status, _, body = self.fixture.asset(self.fixture.path("secrets.json"))
        self.assertDenied(status, body, {404})


class MalformedPercentEncoding(SecurityTestCase):
    def test_a_malformed_escape_does_not_take_the_server_down(self):
        status, _, _ = self.fixture.request("GET", "/__cad/asset?file=%zz")
        self.assertIn(status, {400, 404})
        status, _, _ = self.fixture.request("GET", "/__cad/server")
        self.assertEqual(status, 200, "the server still answers afterwards")

    def test_the_dist_route_rejects_malformed_overlong_and_lone_surrogate(self):
        for target in ("/assets/%zz.js", "/assets/%C0%AF.js", "/assets/%ED%A0%80.js"):
            with self.subTest(target=target):
                status, _, body = self.fixture.request("GET", target)
                self.assertEqual(status, 400)
                self.assertEqual(body, b"Bad request")

    def test_encoded_traversal_out_of_dist_is_403(self):
        status, _, body = self.fixture.request(
            "GET", "/assets/%2e%2e%2f%2e%2e%2fetc%2fpasswd"
        )
        self.assertEqual(status, 403)
        self.assertEqual(body, b"Forbidden")


class RoutingNormalisation(SecurityTestCase):
    """WHATWG pathname semantics, which ``urlsplit`` does not share."""

    def test_the_routing_table(self):
        cases = [
            # (target, expected status, expected body fragment)
            ("/__cad/../etc/passwd", 200, b"<!doctype html>"),
            ("/__cad/%2e%2e/etc/passwd", 200, b"<!doctype html>"),
            ("/__tess_cache/../escape.tess", 200, b"<!doctype html>"),
            ("/__cad", 200, b"<!doctype html>"),
            ("/__cad/", 404, b'{"error":"Not found"}'),
            ("/__cad//asset", 404, b'{"error":"Not found"}'),
            ("/__CAD/server", 200, b"<!doctype html>"),
        ]
        for target, status, fragment in cases:
            with self.subTest(target=target):
                got_status, _, body = self.fixture.request("GET", target)
                self.assertEqual(got_status, status)
                self.assertIn(fragment, body)

    def test_a_backslash_routes_as_a_separator(self):
        ref = quote(self.fixture.path("ok.step"), safe="")
        status, _, body = self.fixture.request("GET", f"/__cad\\asset?file={ref}")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"public step\n")

    def test_an_authority_form_target_routes_on_the_path(self):
        status, _, body = self.fixture.request("GET", "//evil.example/__cad/server")
        self.assertEqual(status, 200)
        self.assertIn(b'"app":"cad-viewer"', body)


class TheTwoGatesCoverTheDataRoutes(SecurityTestCase):
    def targets(self):
        ref = quote(self.fixture.path("ok.step"), safe="")
        return [
            f"/__cad/catalog?file={ref}",
            f"/__cad/asset?file={ref}",
            f"/__cad/folder?path={quote(self.fixture.root, safe='')}",
            f"/__cad/store?file={self.fixture.package_name}/assembly.json{self.fixture.store_binding}",
        ]

    def test_a_hostile_host_is_refused_on_every_data_route(self):
        for target in self.targets():
            with self.subTest(target=target):
                conn = http.client.HTTPConnection("127.0.0.1", self.fixture.port, timeout=10)
                try:
                    conn.request("GET", target, headers={"Host": "attacker.example"})
                    response = conn.getresponse()
                    body = response.read()
                finally:
                    conn.close()
                self.assertEqual(response.status, 403)
                self.assertIn(b"DNS-rebinding", body)

    def test_no_access_control_header_on_any_route_or_status(self):
        # Their absence is what keeps another site from reading any of it.
        for target in ["/", "/assets/app.js", "/assets/missing.js", "/__cad/server", "/__cad/nope",
                       "/__cad/asset?file=/etc/passwd", "/__cad/asset?file=relative.step", *self.targets()]:
            with self.subTest(target=target):
                _, headers, _ = self.fixture.request("GET", target)
                offenders = [k for k in headers if k.lower().startswith("access-control-")]
                self.assertEqual(offenders, [])


class ArtifactRoute(SecurityTestCase):
    """``/__cad/artifact`` takes a file by its absolute path, like every route."""

    def artifact(self, file_param, *, method="GET"):
        target = f"/__cad/artifact?file={quote(str(file_param), safe='')}"
        headers = {"x-cadgen-viewer": "1"} if method == "POST" else None
        return self.fixture.request(method, target, headers=headers)

    def test_a_relative_ref_is_a_400_on_both_methods_and_compiles_nothing(self):
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                status, _, body = self.artifact("ok.step", method=method)
                self.assertEqual(status, 400, body[:400])
        self.assertIsNone(result_tree(self.fixture.path("ok.step")), "a refused ref never reaches the kernel")

    def test_an_absolute_ref_is_answered(self):
        # GET rather than POST: accepting a ref on POST means compiling it, and
        # this asserts acceptance rather than exercising the kernel.
        status, _, body = self.artifact(self.fixture.path("ok.step"))
        self.assertEqual(status, 200, body[:400])
        self.assertEqual(json.loads(body)["state"], "not-compiled")

    def test_a_trailing_newline_is_not_a_step_entry(self):
        r"""``\Z``, not ``$``: Python's ``$`` also matches before a trailing newline, so ``ok.step\n``
        once claimed STEP ownership and was offered a compile of a document that does not exist."""
        status, _, body = self.artifact(self.fixture.path("ok.step") + "\n")
        self.assertEqual(status, 200, body[:400])
        payload = json.loads(body)
        self.assertEqual(payload["state"], "compiled")
        self.assertNotIn("compile", payload)


class StoreRouteConfinement(SecurityTestCase):
    """The store tier: a tree and its objects by hash, never a path the client names."""

    def test_traversal_and_hidden_components_are_404_never_403(self):
        for rel in ("../../etc/hosts", "..%2F..%2Fetc%2Fhosts", "/etc/hosts", ".building-x/assembly.json"):
            with self.subTest(rel=rel):
                status, _, body = self.fixture.request("GET", f"/__cad/store?file={rel}")
                self.assertEqual(status, 404)
                self.assertEqual(body, b'{"error":"Not found"}')

    def test_leading_slashes_are_stripped_so_the_client_form_works(self):
        # resolvePackageAssetUrl emits file=/<key>/components/c0.surf.
        status, _, body = self.fixture.request(
            "GET", f"/__cad/store?file=/{self.fixture.package_name}/components/{self.fixture.component_name}.brep"
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, self.fixture.component_payload)

    def test_backslashes_are_converted(self):
        status, _, _ = self.fixture.request(
            "GET",
            f"/__cad/store?file={self.fixture.package_name}\\components\\{self.fixture.component_name}.brep",
        )
        self.assertEqual(status, 200)

    def test_the_v_param_is_accepted_and_ignored(self):
        status, _, _ = self.fixture.request(
            "GET", f"/__cad/store?file={self.fixture.package_name}/assembly.json{self.fixture.store_binding}&v=zzz"
        )
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
