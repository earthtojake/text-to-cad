"""The adversarial suite for path containment and the asset routes.

Every case here is a concrete request against a real launched server, and every
denial asserts BOTH the status and that the secret bytes are absent — a denial
that 404s for the wrong reason passes vacuously otherwise.

TWO RULES THIS FIXTURE ENCODES
------------------------------
1. Probe files use ``.step``, never ``.txt``. ``is_served_cad_asset`` filters by
   EXTENSION BEFORE containment, so a ``.txt`` probe 404s on the extension and
   proves nothing about the containment check underneath it.
2. ``root-evil`` sits beside ``root``. That is the jupyter_server
   GHSA-5789-5fc7-67v3 shape: a name-prefix sibling that a naive
   ``startswith(root)`` check lets through.

WHAT IS DELIBERATELY ALLOWED
----------------------------
A symlink that leaves the served root IS served, and so is a directory link
pointing outside. The viewer serves whatever absolute directory it was started
on, so a link grants no reach the URL did not already grant. Recorded here as
current behaviour rather than endorsed; what stays refused is a ``..`` that
walks out AFTER a symlinked component, because containment collapses dot
segments lexically before any link is followed.
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
    """``base/{root, root-evil, outside}`` plus a store, behind a live server."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp()
        self.base = self.tmp
        self.root = os.path.join(self.base, "root")
        self.evil = os.path.join(self.base, "root-evil")
        self.outside = os.path.join(self.base, "outside")
        for directory in (self.root, self.evil, self.outside):
            os.makedirs(directory)
        self.cache = os.path.join(self.base, "cache")
        os.makedirs(os.path.join(self.cache, "packages"))
        self._previous_cache = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = self.cache

        self.write("ok.step", "public step\n")
        self.write("ok.stl", "solid public\n")
        self.write("part.step.json", '{"kinematics":{}}')
        self.write("secrets.json", f'{{"token":"{SECRET}"}}')
        self.write(".env", f"TOKEN={SECRET}\n")
        self.write("id_rsa", SECRET)
        self.write("model.py", f"# {SECRET}\n")
        self.write("part.step.js", f"// {SECRET}\n")
        self.write(".dotfile.step", SECRET)
        self.write(".hidden/secret.step", SECRET)
        self.write("sub/.git/config.step", SECRET)
        os.makedirs(os.path.join(self.root, "dir.step"))
        Path(self.evil, "stolen.step").write_text(SECRET, encoding="utf-8")
        Path(self.outside, "secret.step").write_text(SECRET, encoding="utf-8")
        Path(self.outside, "notes.txt").write_text(SECRET, encoding="utf-8")

        # A symlinked file and a symlinked directory that both leave the root.
        os.symlink(os.path.join(self.outside, "secret.step"), os.path.join(self.root, "escape.step"))
        os.symlink(self.outside, os.path.join(self.root, "lib"))

        # A real result in the store: the tree hash is what the store route serves.
        self.package_name = seed_result(
            Path(self.root, "part.step"), {"kind": "assembly-package", "components": {"c0": {}}}, surf=b"SURF\x00\x01\x02"
        )
        Path(self.cache, "packages-evil-marker").write_text(SECRET, encoding="utf-8")

        self.dist = os.path.join(self.base, "dist")
        os.makedirs(os.path.join(self.dist, "assets"))
        Path(self.dist, "index.html").write_text("<!doctype html><title>cad</title>", encoding="utf-8")
        Path(self.dist, "assets", "app.js").write_text("export const x = 1;\n", encoding="utf-8")

        self.app = create_cad_app(root=self.root, host="127.0.0.1", port=0, dist_dir=self.dist)
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

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self._previous_cache is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = self._previous_cache
        shutil.rmtree(self.tmp, ignore_errors=True)

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

    def test_an_in_root_step_serves(self):
        status, headers, body = self.fixture.asset(os.path.join(self.fixture.root, "ok.step"))
        self.assertEqual(status, 200)
        self.assertEqual(body, b"public step\n")
        self.assertEqual(headers["content-type"], "application/step")
        self.assertEqual(headers["cache-control"], "no-store")
        # The viewer serves bytes to render, never a save-as: no route attaches.
        self.assertNotIn("content-disposition", {k.lower() for k in headers})

    def test_the_root_itself_is_contained_but_has_no_served_extension(self):
        status, _, body = self.fixture.asset(self.fixture.root)
        self.assertDenied(status, body, {404})

    def test_a_source_sidecar_serves(self):
        status, headers, _ = self.fixture.asset(os.path.join(self.fixture.root, "part.step.json"))
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")

    def test_the_store_route_serves_a_component(self):
        status, headers, body = self.fixture.request(
            "GET", f"/__cad/store?file={self.fixture.package_name}/components/c0.surf"
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, b"SURF\x00\x01\x02")
        self.assertEqual(headers["content-type"], "application/octet-stream")
        self.assertNotIn("content-disposition", {k.lower() for k in headers})


class A_EncodedAndLayeredTraversal(SecurityTestCase):
    def test_traversal_and_encoded_traversal_out_of_the_root(self):
        root = self.fixture.root
        outside_secret = os.path.join(self.fixture.outside, "secret.step")
        cases = {
            "plain ..": f"{root}/../outside/secret.step",
            "absolute outside": outside_secret,
            "backslash": f"{root}\\..\\outside\\secret.step",
            "nested ..": f"{root}/sub/../../outside/secret.step",
            "dot segments": f"{root}/./././../outside/secret.step",
        }
        for label, ref in cases.items():
            with self.subTest(label):
                status, _, body = self.fixture.asset(ref)
                self.assertDenied(status, body, {403})

    def test_encoded_separators_decode_in_the_query_and_are_refused(self):
        # file= is not percent-decoded by the backend, but the QUERY layer
        # decodes it once, so %2F arrives as "/".
        ref = f"{self.fixture.root}%2F..%2Foutside%2Fsecret.step"
        status, _, body = self.fixture.request("GET", f"/__cad/asset?file={ref}")
        self.assertDenied(status, body, {403})

    def test_a_relative_ref_is_404_not_a_traversal(self):
        status, _, body = self.fixture.asset("../outside/secret.step")
        self.assertDenied(status, body, {404})

    def test_double_encoding_never_reaches_the_file(self):
        ref = f"{self.fixture.root}/..%252f..%252fetc%252fpasswd"
        status, _, body = self.fixture.request("GET", f"/__cad/asset?file={ref}")
        self.assertDenied(status, body, {403, 404})

    def test_a_dotdot_after_a_symlinked_component_is_still_refused(self):
        # root/lib -> outside. Containment collapses ".." lexically BEFORE any
        # link is followed, which is why realpath may not be the primary check.
        ref = f"{self.fixture.root}/lib/../../outside/secret.step"
        status, _, body = self.fixture.asset(ref)
        self.assertDenied(status, body, {403})


class B_NamePrefixSibling(SecurityTestCase):
    """jupyter_server GHSA-5789-5fc7-67v3: ``/base/root-evil`` beside ``/base/root``."""

    def test_the_sibling_is_refused_on_the_asset_route(self):
        ref = os.path.join(self.fixture.evil, "stolen.step")
        status, _, body = self.fixture.asset(ref)
        self.assertDenied(status, body, {403})

    def test_the_store_route_refuses_a_prefix_sibling_of_the_packages_tier(self):
        status, _, body = self.fixture.request(
            "GET", "/__cad/store?file=../packages-evil-marker"
        )
        self.assertDenied(status, body, {404})


class C_UnicodeAndCase(SecurityTestCase):
    def test_a_differently_cased_root_spelling_is_refused(self):
        # realpath does NOT canonicalise case on macOS, so this fails closed.
        # Casefolding would look right on APFS and be WRONG on ext4, where
        # /ROOT is a genuinely different directory.
        ref = os.path.join(self.fixture.base, "ROOT", "ok.step")
        status, _, body = self.fixture.asset(ref)
        if os.name == "nt":
            # On NTFS base/ROOT IS the served root — ntpath.realpath resolves
            # to the on-disk casing — so serving it is correct, not a leak.
            self.assertEqual(status, 200)
            self.assertEqual(body, b"public step\n")
        else:
            self.assertDenied(status, body, {403, 404})

    def test_an_nfc_nfd_spelling_is_never_a_403(self):
        # A normalisation-insensitive filesystem (macOS) serves it, a
        # normalisation-sensitive one 404s. Neither may be a containment error.
        self.fixture.write("café.step", "cafe\n")
        for spelling in ("caf\u00e9.step", "cafe\u0301.step"):
            with self.subTest(spelling=spelling):
                status, _, _ = self.fixture.asset(os.path.join(self.fixture.root, spelling))
                self.assertIn(status, {200, 404})


class D_Symlinks(SecurityTestCase):
    def test_a_file_link_leaving_the_root_is_served_deliberately(self):
        status, _, body = self.fixture.asset(os.path.join(self.fixture.root, "escape.step"))
        self.assertEqual(status, 200)
        self.assertEqual(body.decode("utf-8"), SECRET)

    def test_a_directory_link_leaving_the_root_is_served_deliberately(self):
        status, _, body = self.fixture.asset(
            os.path.join(self.fixture.root, "lib", "secret.step")
        )
        self.assertEqual(status, 200)
        self.assertEqual(body.decode("utf-8"), SECRET)

    def test_a_link_target_with_no_served_extension_is_still_refused(self):
        status, _, body = self.fixture.asset(os.path.join(self.fixture.root, "lib", "notes.txt"))
        self.assertDenied(status, body, {404})


class E_AbsolutePathsDrivesAndUnc(SecurityTestCase):
    def test_an_unserved_absolute_path_is_404_on_the_extension(self):
        status, _, _ = self.fixture.asset("/etc/passwd")
        self.assertEqual(status, 404)

    def test_a_served_extension_outside_the_root_is_403(self):
        status, _, _ = self.fixture.asset("/etc/passwd.step")
        self.assertEqual(status, 403)

    @unittest.skipIf(os.name == "nt", "POSIX drive-letter semantics")
    def test_a_windows_drive_path_is_relative_on_posix(self):
        status, _, _ = self.fixture.asset("C:\\Windows\\win.ini")
        self.assertEqual(status, 404)

    @unittest.skipIf(os.name == "nt", "POSIX UNC semantics")
    def test_a_unc_path_becomes_absolute_and_outside_on_posix(self):
        # \\server\share\x.step -> /server/share/x.step: absolute, outside,
        # refused by containment rather than attempted as an SMB fetch.
        status, _, _ = self.fixture.asset("\\\\server\\share\\x.step")
        self.assertEqual(status, 403)

    def test_an_absent_or_empty_file_param_is_404(self):
        for target in ("/__cad/asset", "/__cad/asset?file=", "/__cad/asset?v=1"):
            with self.subTest(target=target):
                status, _, _ = self.fixture.request("GET", target)
                self.assertEqual(status, 404)

    def test_an_enormous_path_does_not_500(self):
        status, _, _ = self.fixture.asset("/" + "a" * 5000 + ".step")
        self.assertEqual(status, 403)

    def test_thousands_of_dot_segments_do_not_recurse_to_death(self):
        status, _, _ = self.fixture.asset("../" * 5000 + "secret.step")
        self.assertIn(status, {403, 404})

    def test_repeated_file_params_take_the_first(self):
        good = quote(os.path.join(self.fixture.root, "ok.step"), safe="")
        bad = quote(os.path.join(self.fixture.outside, "secret.step"), safe="")
        status, _, body = self.fixture.request("GET", f"/__cad/asset?file={good}&file={bad}")
        self.assertEqual(status, 200)
        self.assertNotIn(SECRET.encode("ascii"), body)

    def test_a_blank_first_value_wins_over_a_later_one(self):
        bad = quote(os.path.join(self.fixture.outside, "secret.step"), safe="")
        status, _, body = self.fixture.request("GET", f"/__cad/asset?file=&v=1&file={bad}")
        self.assertDenied(status, body, {404})


class F_NullBytesAndControlCharacters(SecurityTestCase):
    def test_a_null_byte_is_a_400_with_the_exact_message(self):
        status, _, body = self.fixture.request("GET", "/__cad/asset?file=%2Froot%2Fok.step%00.png")
        self.assertEqual(status, 400)
        self.assertEqual(
            body, b'{"error":"File path contains an invalid null byte"}'
        )

    def test_a_null_byte_in_the_spa_path_does_not_500(self):
        status, _, body = self.fixture.request("GET", "/index.html%00.js")
        self.assertEqual(status, 200)
        self.assertIn(b"<!doctype html>", body)

    def test_crlf_in_a_filename_cannot_inject_a_header(self):
        name = "a\r\nX-Evil: 1.step"
        if os.name != "nt":
            # The benign sibling is incidental; on NTFS its ':' would silently
            # create an alternate data stream instead of this file.
            self.fixture.write(name.replace("\r\n", "_"), "x")
        status, headers, _ = self.fixture.asset(os.path.join(self.fixture.root, name))
        self.assertIn(status, {403, 404})
        self.assertNotIn("x-evil", {k.lower() for k in headers})


class G_MalformedPercentEncoding(SecurityTestCase):
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


class H_RoutingNormalisation(SecurityTestCase):
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
        ref = quote(os.path.join(self.fixture.root, "ok.step"), safe="")
        status, _, body = self.fixture.request("GET", f"/__cad\\asset?file={ref}")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"public step\n")

    def test_an_authority_form_target_routes_on_the_path(self):
        status, _, body = self.fixture.request("GET", "//evil.example/__cad/server")
        self.assertEqual(status, 200)
        self.assertIn(b'"app":"cad-viewer"', body)


class I_TheTwoGatesCoverTheAssetRoutes(SecurityTestCase):
    def test_a_hostile_host_is_refused_on_every_data_route(self):
        ref = quote(os.path.join(self.fixture.root, "ok.step"), safe="")
        targets = [
            "/__cad/catalog",
            f"/__cad/asset?file={ref}",
            f"/__cad/store?file={self.fixture.package_name}/assembly.json",
        ]
        for target in targets:
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
        ref = quote(os.path.join(self.fixture.root, "ok.step"), safe="")
        targets = [
            "/",
            "/assets/app.js",
            "/assets/missing.js",
            "/__cad/server",
            "/__cad/catalog",
            f"/__cad/asset?file={ref}",
            "/__cad/asset?file=/etc/passwd.step",
            "/__cad/asset?file=/etc/passwd",
            "/__cad/nope",
            f"/__cad/store?file={self.fixture.package_name}/assembly.json",
        ]
        for target in targets:
            with self.subTest(target=target):
                _, headers, _ = self.fixture.request("GET", target)
                offenders = [k for k in headers if k.lower().startswith("access-control-")]
                self.assertEqual(offenders, [])


class J_HiddenPaths(SecurityTestCase):
    def test_hidden_files_and_components_are_404_not_403(self):
        root = self.fixture.root
        for ref in (
            os.path.join(root, ".dotfile.step"),
            os.path.join(root, ".hidden", "secret.step"),
            os.path.join(root, "sub", ".git", "config.step"),
        ):
            with self.subTest(ref=ref):
                status, _, body = self.fixture.asset(ref)
                self.assertDenied(status, body, {404})

    def test_the_store_route_refuses_hidden_components(self):
        status, _, body = self.fixture.request(
            "GET", "/__cad/store?file=.building-x/assembly.json"
        )
        self.assertDenied(status, body, {404})
        self.assertEqual(body, b'{"error":"Not found"}')

    def test_a_root_under_a_hidden_absolute_path_still_serves(self):
        # Only ROOT-RELATIVE components are dot-checked.
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        hidden_root = os.path.join(tmp, ".models")
        os.makedirs(hidden_root)
        Path(hidden_root, "ok.step").write_bytes(b"visible\n")
        app = create_cad_app(root=hidden_root, host="127.0.0.1", port=0, dist_dir="")
        server = handler_module.serve(app, "127.0.0.1", 0)
        port = server.server_address[1]
        app.port = port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            ref = quote(os.path.join(hidden_root, "ok.step"), safe="")
            conn.request("GET", f"/__cad/asset?file={ref}")
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"visible\n")
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_the_catalog_never_lists_hidden_or_skipped_content(self):
        _, _, body = self.fixture.request("GET", "/__cad/catalog")
        catalog = json.loads(body)
        listed = [entry["rootRelativeFile"] for entry in catalog["entries"]]
        for forbidden in (".dotfile.step", ".hidden/secret.step", "sub/.git/config.step"):
            self.assertNotIn(forbidden, listed)


class K_NonServedContentUnderTheRoot(SecurityTestCase):
    def test_configs_secrets_and_scripts_are_never_streamed(self):
        root = self.fixture.root
        for name in ("secrets.json", ".env", "id_rsa", "model.py", "part.step.js"):
            with self.subTest(name=name):
                status, _, body = self.fixture.asset(os.path.join(root, name))
                self.assertDenied(status, body, {404})

    def test_a_directory_with_a_served_extension_is_404(self):
        status, _, body = self.fixture.asset(os.path.join(self.fixture.root, "dir.step"))
        self.assertDenied(status, body, {404})

    def test_the_sidecar_allowlist_is_the_pair_of_suffixes_not_dot_json(self):
        status, _, _ = self.fixture.asset(os.path.join(self.fixture.root, "part.step.json"))
        self.assertEqual(status, 200)
        status, _, body = self.fixture.asset(os.path.join(self.fixture.root, "secrets.json"))
        self.assertDenied(status, body, {404})


class L_ArtifactRouteContainment(SecurityTestCase):
    """``/__cad/artifact`` obeys the rule ``/__cad/asset`` always did.

    THE CHAIN THIS CLOSES — open in the Node backend too, where ``cadgenOps``
    resolved its candidate with no containment check of any kind:

      1. ``GET  /__cad/asset?file=<outside>.step``          -> 403, correctly.
      2. ``POST /__cad/artifact?file=<outside>.step``       -> 200, and it
         COMPILED that file into the shared content-addressed store.
      3. ``GET  /__cad/store?file=<key>/assembly.json``     -> 200.
      4. ``GET  /__cad/store?file=<key>/components/*.surf`` -> 200: the
         tessellated geometry of a document the viewer was never pointed at.

    Hop 1 was never the leak; hops 2-4 were, which is why this tests the WHOLE
    chain. A test that stopped at "the POST is 403" would still pass if the
    refusal landed after the compile had already published the package.
    """

    def artifact(self, file_param, *, method="GET"):
        target = f"/__cad/artifact?file={quote(str(file_param), safe='')}"
        headers = {"x-cadgen-viewer": "1"} if method == "POST" else None
        return self.fixture.request(method, target, headers=headers)

    def test_the_whole_chain_dies_at_the_build_route(self):
        victim = os.path.join(self.fixture.outside, "secret.step")
        key = "f" * 64

        # 1. The hop that was always correct, kept as the control.
        status, _, body = self.fixture.asset(victim)
        self.assertDenied(status, body, {403})

        # 2. The hop that leaked. 403 now — and no package on disk, so the
        #    refusal landed BEFORE the compile rather than after it.
        status, _, body = self.artifact(victim, method="POST")
        self.assertDenied(status, body, {403})
        self.assertEqual(json.loads(body)["error"], "Forbidden")
        self.assertIsNone(
            result_tree(victim),
            "a refused ref must never reach the kernel: no result may exist",
        )

        # 3/4. Nothing was compiled, so there is nothing to read back out.
        for rel in (f"{key}/assembly.json", f"{key}/components/c0.surf"):
            with self.subTest(rel=rel):
                status, _, body = self.fixture.request("GET", f"/__cad/store?file={rel}")
                self.assertDenied(status, body, {404})

    def test_the_status_route_refuses_the_same_ref(self):
        # GET compiles nothing, but it resolves the same candidate and reports
        # on it — including whether it is importable, which is a disclosure
        # about a file outside the root all by itself.
        victim = os.path.join(self.fixture.outside, "secret.step")
        status, _, body = self.artifact(victim)
        self.assertDenied(status, body, {403})

    def test_relative_refs_that_walk_out_are_refused_on_both_methods(self):
        # This route ACCEPTS a relative ref where the asset route does not, so
        # stripping leading slashes is not enough: ".." still escapes once
        # joined against the root.
        for ref in ("../outside/secret.step", "sub/../../outside/secret.step"):
            for method in ("GET", "POST"):
                with self.subTest(ref=ref, method=method):
                    status, _, body = self.artifact(ref, method=method)
                    self.assertDenied(status, body, {403})

    def test_the_name_prefix_sibling_is_refused_here_too(self):
        # root-evil beside root: the jupyter_server shape, on the build route.
        status, _, body = self.artifact(
            os.path.join(self.fixture.evil, "stolen.step"), method="POST"
        )
        self.assertDenied(status, body, {403})

    def test_a_dotdot_after_a_symlinked_component_is_refused_here_too(self):
        status, _, body = self.artifact(
            f"{self.fixture.root}/lib/../../outside/secret.step", method="POST"
        )
        self.assertDenied(status, body, {403})

    def test_an_absolute_in_root_ref_is_STILL_ACCEPTED(self):
        """The judgement call, pinned.

        Absolute refs are not refused as a class — only absolute refs that land
        outside. They have to keep working: the catalog absolutizes every
        entry's ``file`` and the client echoes exactly that back, so a blanket
        ban would break the normal path while fixing nothing.

        GET rather than POST, because accepting a ref on POST means compiling
        it, and this asserts acceptance rather than exercising the kernel.
        """
        status, _, body = self.artifact(os.path.join(self.fixture.root, "ok.step"))
        self.assertEqual(status, 200, body[:400])
        self.assertIn(json.loads(body)["state"], {"not-compiled", "error", "ready"})

    def test_a_relative_in_root_ref_is_still_accepted(self):
        status, _, body = self.artifact("ok.step")
        self.assertEqual(status, 200, body[:400])

    def test_a_trailing_newline_is_not_a_step_entry(self):
        r"""``\Z``, not ``$``.

        Python's ``$`` also matches immediately before a trailing newline, so
        ``ok.step\n`` used to claim STEP ownership and be answered with a
        not-compiled import offer for a document that does not exist. Node
        answered ``ready``, because JavaScript's ``$`` does not match there.
        """
        status, _, body = self.artifact(os.path.join(self.fixture.root, "ok.step") + "\n")
        self.assertEqual(status, 200, body[:400])
        payload = json.loads(body)
        self.assertEqual(payload["state"], "rendered")
        self.assertNotIn("compile", payload)


class StoreRouteConfinement(SecurityTestCase):
    """The store tier proper. The build route's half of containment is class L."""

    def test_traversal_is_404_never_403_on_this_route(self):
        for rel in ("../../etc/hosts", "..%2F..%2Fetc%2Fhosts", "/etc/hosts"):
            with self.subTest(rel=rel):
                status, _, body = self.fixture.request("GET", f"/__cad/store?file={rel}")
                self.assertEqual(status, 404)
                self.assertEqual(body, b'{"error":"Not found"}')

    def test_leading_slashes_are_stripped_so_the_client_form_works(self):
        # resolvePackageAssetUrl emits file=/<key>/components/c0.surf.
        status, _, body = self.fixture.request(
            "GET", f"/__cad/store?file=/{self.fixture.package_name}/components/c0.surf"
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, b"SURF\x00\x01\x02")

    def test_backslashes_are_converted(self):
        status, _, _ = self.fixture.request(
            "GET",
            f"/__cad/store?file={self.fixture.package_name}\\components\\c0.surf",
        )
        self.assertEqual(status, 200)

    def test_the_v_param_is_accepted_and_ignored(self):
        status, _, _ = self.fixture.request(
            "GET", f"/__cad/store?file={self.fixture.package_name}/assembly.json&v=zzz"
        )
        self.assertEqual(status, 200)


class CatalogOverHttp(SecurityTestCase):
    def test_the_catalog_is_absolutized_and_compact(self):
        status, headers, body = self.fixture.request("GET", "/__cad/catalog")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertNotIn(b'": ', body)
        catalog = json.loads(body)
        self.assertEqual(catalog["schemaVersion"], 4)
        by_ref = {e["rootRelativeFile"]: e for e in catalog["entries"]}

        mesh = by_ref["ok.stl"]
        self.assertTrue(os.path.isabs(mesh["file"]))
        self.assertTrue(mesh["url"].startswith("/__cad/asset?file="))
        self.assertEqual(mesh["assetFile"], mesh["file"])
        # Key order: the raw keys, then rootRelativeFile, then assetFile.
        self.assertEqual(
            list(mesh), ["file", "kind", "url", "hash", "bytes", "rootRelativeFile", "assetFile"]
        )

        # A store URL is already in its served form and is left untouched — no
        # rewrite and, deliberately, no assetFile sibling.
        step = by_ref["ok.step"]
        self.assertTrue(step["url"].startswith("/__cad/store?file="))
        self.assertNotIn("assetFile", step)

    def test_a_catalog_url_round_trips_through_the_asset_route(self):
        _, _, body = self.fixture.request("GET", "/__cad/catalog")
        entry = next(
            e for e in json.loads(body)["entries"] if e["rootRelativeFile"] == "ok.stl"
        )
        status, _, payload = self.fixture.request("GET", entry["url"])
        self.assertEqual(status, 200)
        self.assertEqual(payload, b"solid public\n")


if __name__ == "__main__":
    unittest.main()
