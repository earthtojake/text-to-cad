"""A Windows drive-letter directory must open, not 403 (issue #211).

`http://127.0.0.1:3245/D:/some/project/models` returned `403 Forbidden` for every
Windows user. The URL-path form of an absolute Windows path (`/D:/models`) is not
a filesystem path, and two stdlib calls read it wrong in opposite ways:

    os.path.join(dist_root, "D:/models") -> "D:\\models"      base DISCARDED -> 403
    os.path.abspath("/D:/models")        -> "C:\\D:\\models"  leading slash = current drive

The first made an ordinary directory request look like a traversal escape; fixing
it surfaced the second in `resolve_root`, where the catalog then failed with
`CAD Viewer directory not found: C:\\D:\\some\\project`.

CI is ubuntu-only (issue #196), where `splitdrive` never reports a drive and every
transform below is the identity -- so none of this is observable here unless the
tests say so. They bind `paths._PATH` to `ntpath` to run the Windows branches on a
POSIX host, and assert alongside that POSIX behaviour is genuinely unchanged.
"""

from __future__ import annotations

import ntpath
import os
import pathlib
import posixpath
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from server_py import backend as backend_mod  # noqa: E402
from server_py import paths  # noqa: E402
from server_py import server as server_mod  # noqa: E402
from server_py import server_info  # noqa: E402
from server_py import start_viewer  # noqa: E402


def _as_windows():
    """Give `paths` the path semantics of a real Windows host."""
    return mock.patch.object(paths, "_PATH", ntpath)


def _as_posix():
    return mock.patch.object(paths, "_PATH", posixpath)


class _NtPathWithOverrides:
    """`ntpath`, with named functions replaced -- e.g. an `isdir` that says yes to a
    drive that does not exist on the host running the test."""

    def __init__(self, **overrides):
        self._overrides = overrides

    def __getattr__(self, name):
        try:
            return self._overrides[name]
        except KeyError:
            return getattr(ntpath, name)


def _windows_os_for(module, **path_overrides):
    """Swap one module's `os` for a Windows-semantics stand-in.

    Scoped to the module under test rather than patching the global `os.path`, which
    would redirect every other caller in the process for the duration.
    """
    shim = types.SimpleNamespace(
        path=_NtPathWithOverrides(**path_overrides),
        sep=ntpath.sep,
        getcwd=os.getcwd,
        getpid=os.getpid,
    )
    return mock.patch.object(module, "os", shim)


class UrlPathToFilesystemPathTests(unittest.TestCase):
    def test_a_windows_url_path_drops_the_url_leading_slash(self):
        with _as_windows():
            self.assertEqual("D:/some/project", paths.filesystem_path_from_url_path("/D:/some/project"))
            self.assertEqual("C:/", paths.filesystem_path_from_url_path("/C:/"))
            self.assertEqual("d:/lower/drive", paths.filesystem_path_from_url_path("/d:/lower/drive"))

    def test_an_already_bare_windows_path_is_untouched(self):
        with _as_windows():
            self.assertEqual("D:/some/project", paths.filesystem_path_from_url_path("D:/some/project"))

    def test_a_posix_leading_slash_is_part_of_the_path_and_is_kept(self):
        for as_platform in (_as_posix, _as_windows):
            with self.subTest(platform=as_platform.__name__), as_platform():
                self.assertEqual("/Users/me/models", paths.filesystem_path_from_url_path("/Users/me/models"))

    def test_a_posix_host_never_strips_a_drive_looking_path(self):
        # A directory literally named `D:` at the root is legal on POSIX and must survive.
        with _as_posix():
            self.assertEqual("/D:/some/project", paths.filesystem_path_from_url_path("/D:/some/project"))

    def test_empty_and_relative_inputs_pass_through(self):
        with _as_windows():
            self.assertEqual("", paths.filesystem_path_from_url_path(""))
            self.assertEqual("", paths.filesystem_path_from_url_path(None))
            self.assertEqual("models/part.step", paths.filesystem_path_from_url_path("models/part.step"))


class FilesystemPathToUrlPathTests(unittest.TestCase):
    def test_a_windows_path_becomes_a_url_path(self):
        with _as_windows():
            self.assertEqual("/D:/some/project", paths.url_path_from_filesystem_path("D:\\some\\project"))

    def test_a_posix_path_is_already_its_own_url_path(self):
        with _as_posix():
            self.assertEqual("/Users/me/models", paths.url_path_from_filesystem_path("/Users/me/models"))

    def test_a_backslash_stays_a_filename_character_on_posix(self):
        with _as_posix():
            self.assertEqual("/Users/me/od\\d", paths.url_path_from_filesystem_path("/Users/me/od\\d"))

    def test_empty_names_no_directory(self):
        with _as_windows():
            self.assertEqual("", paths.url_path_from_filesystem_path(""))

    def test_round_trip(self):
        with _as_windows():
            url_path = paths.url_path_from_filesystem_path("D:\\some\\project")
            self.assertEqual("D:/some/project", paths.filesystem_path_from_url_path(url_path))


class UrlPathAsRelativeTests(unittest.TestCase):
    """What the dist join needs: a path that can never discard the base it is joined to."""

    def test_a_windows_directory_request_is_reduced_to_a_relative_path(self):
        with _as_windows():
            self.assertEqual("some/project/models", paths.url_path_as_relative("/D:/some/project/models"))

    def test_a_bundle_asset_path_keeps_everything_but_its_leading_slash(self):
        for as_platform in (_as_posix, _as_windows):
            with self.subTest(platform=as_platform.__name__), as_platform():
                self.assertEqual("assets/index-abc123.js", paths.url_path_as_relative("/assets/index-abc123.js"))

    def test_the_result_is_never_absolute_to_the_join_that_consumes_it(self):
        # The invariant is per-platform: `D:/models` is absolute to ntpath.join and
        # relative to posixpath.join, and only the host's own module does the join.
        candidates = (
            "/D:/some/project",
            "//D:/some/project",
            "\\\\D:\\some\\project",
            "/C:/Windows/System32",
            "/Users/me/models",
            "/",
            "",
        )
        for as_platform, path_module in ((_as_posix, posixpath), (_as_windows, ntpath)):
            for candidate in candidates:
                with self.subTest(platform=path_module.__name__, candidate=candidate), as_platform():
                    result = paths.url_path_as_relative(candidate)
                    self.assertFalse(path_module.isabs(result), result)
                    # The point of the invariant: the base survives the join.
                    self.assertTrue(path_module.join("base", result).startswith("base"), result)

    def test_traversal_segments_survive_so_the_containment_check_still_sees_them(self):
        # This helper is NOT a traversal guard and must not be mistaken for one.
        with _as_windows():
            self.assertEqual("../../etc/passwd", paths.url_path_as_relative("/../../etc/passwd"))


class _RecordingHandler(server_mod.Handler):
    """A Handler with the socket machinery replaced by recording stubs.

    `BaseHTTPRequestHandler.__init__` would serve a request off a real socket, so it
    is deliberately not called.
    """

    def __init__(self):  # noqa: D107 - see class docstring
        self.command = "GET"
        self.status = None
        self.sent_headers = {}
        self.body = b""
        self.wfile = self

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, key, value):
        self.sent_headers[str(key).lower()] = value

    def end_headers(self):
        pass

    def write(self, data):
        self.body += data


class ServeDistPosixTests(unittest.TestCase):
    """POSIX serving is unchanged by the fix -- including the traversal guard."""

    def setUp(self):
        self._dist = tempfile.TemporaryDirectory()
        self.addCleanup(self._dist.cleanup)
        dist_root = str(pathlib.Path(self._dist.name).resolve())
        pathlib.Path(dist_root, "index.html").write_text("<!doctype html><title>cad</title>", encoding="utf-8")
        assets = pathlib.Path(dist_root, "assets")
        assets.mkdir()
        (assets / "index-abc123.js").write_bytes(b"export default 1;\n")

        previous = server_mod._Ctx.dist_root
        server_mod._Ctx.dist_root = dist_root
        self.addCleanup(setattr, server_mod._Ctx, "dist_root", previous)
        self.dist_root = dist_root

    def _get(self, request_path):
        handler = _RecordingHandler()
        handler._serve_dist(request_path)
        return handler

    def test_an_absolute_directory_falls_through_to_the_spa(self):
        handler = self._get("/Users/me/robots/models")
        self.assertEqual(200, handler.status)
        self.assertIn(b"<!doctype html>", handler.body)

    def test_a_directory_containing_dots_is_still_a_directory(self):
        self.assertEqual(200, self._get("/Users/j/v0.4/models").status)

    def test_a_bundle_asset_is_served_from_dist(self):
        handler = self._get("/assets/index-abc123.js")
        self.assertEqual(200, handler.status)
        self.assertEqual(b"export default 1;\n", handler.body)

    def test_a_missing_bundle_asset_is_404_not_the_spa(self):
        self.assertEqual(404, self._get("/assets/does-not-exist.js").status)

    def test_traversal_out_of_dist_root_is_still_forbidden(self):
        self.assertEqual(403, self._get("/../../../../etc/passwd").status)

    def test_a_malformed_percent_escape_is_still_a_bad_request(self):
        self.assertEqual(400, self._get("/models/%zz").status)


class _RoutingHandler(_RecordingHandler):
    """Records WHICH file `_serve_dist` chose instead of reading it.

    Lets the Windows routing run against paths (`C:\\viewer\\dist\\index.html`) that
    cannot exist on the host running the test.
    """

    def __init__(self):
        super().__init__()
        self.served = []

    def _serve_static_file(self, file_path, content_type):
        self.served.append(file_path)
        self.status = 200
        return True


class ServeDistWindowsTests(unittest.TestCase):
    """The 403 from issue #211, at the routing level that produced it."""

    DIST_ROOT = "C:\\viewer\\dist"

    def setUp(self):
        previous = server_mod._Ctx.dist_root
        server_mod._Ctx.dist_root = self.DIST_ROOT
        self.addCleanup(setattr, server_mod._Ctx, "dist_root", previous)

    def _get(self, request_path, **path_overrides):
        handler = _RoutingHandler()
        # No file exists under a fabricated dist root, so every lookup misses and the
        # route is decided by the containment check alone -- which is the thing at issue.
        overrides = {"isfile": lambda value: False}
        overrides.update(path_overrides)
        with _as_windows(), _windows_os_for(server_mod, **overrides):
            handler._serve_dist(request_path)
        return handler

    def test_a_drive_letter_directory_serves_the_spa_instead_of_403(self):
        handler = self._get("/D:/some/project/models")
        self.assertEqual(200, handler.status)
        self.assertEqual(["C:\\viewer\\dist\\index.html"], handler.served)

    def test_the_drive_the_viewer_itself_lives_on_is_no_different(self):
        self.assertEqual(200, self._get("/C:/Users/me/models").status)

    def test_a_bundle_asset_is_still_looked_up_under_dist_root(self):
        handler = self._get("/assets/index-abc123.js", isfile=lambda value: True)
        self.assertEqual(["C:\\viewer\\dist\\assets\\index-abc123.js"], handler.served)

    def test_a_missing_bundle_asset_is_still_404(self):
        handler = self._get("/assets/does-not-exist.js")
        self.assertEqual(404, handler.status)
        self.assertEqual([], handler.served)

    def test_traversal_out_of_dist_root_is_still_forbidden(self):
        handler = self._get("/../../Windows/System32/drivers/etc/hosts")
        self.assertEqual(403, handler.status)
        self.assertEqual([], handler.served)


class ResolveRootTests(unittest.TestCase):
    def test_a_windows_url_path_root_is_not_prefixed_with_the_process_drive(self):
        # The catalog failed with `CAD Viewer directory not found: C:\D:\some\project`.
        with _as_windows(), _windows_os_for(backend_mod, isdir=lambda value: True):
            resolved = backend_mod.LocalAssetBackend().resolve_root("/D:/some/project")

        self.assertEqual("D:\\some\\project", resolved["rootPath"])
        self.assertEqual("D:/some/project", resolved["dir"])
        self.assertEqual("project", resolved["rootName"])

    def test_a_posix_root_still_resolves_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            resolved = backend_mod.LocalAssetBackend().resolve_root(str(pathlib.Path(directory).resolve()))
            self.assertEqual(str(pathlib.Path(directory).resolve()), resolved["rootPath"])

    def test_a_missing_directory_still_reports_the_path_asked_for(self):
        with self.assertRaisesRegex(ValueError, "CAD Viewer directory not found"):
            backend_mod.LocalAssetBackend().resolve_root("/no/such/viewer/directory")


class NormalizedFileRefTests(unittest.TestCase):
    def test_a_windows_url_path_ref_resolves_to_its_drive(self):
        with _as_windows(), _windows_os_for(backend_mod):
            self.assertEqual(
                "D:/some/project/part.step",
                backend_mod.normalized_file_ref("/D:/some/project/part.step"),
            )

    def test_a_relative_ref_is_still_relative(self):
        self.assertEqual("models/part.step", backend_mod.normalized_file_ref("models/part.step"))

    @unittest.skipIf(
        os.name == "nt",
        "asserts POSIX semantics, which is a claim about the HOST rather than about the\n        code under test: on Windows a leading-slash path really is drive-relative, so\n        D:/Users/... is the right answer there, not a regression.",
    )
    def test_a_posix_absolute_ref_is_unchanged(self):
        self.assertEqual("/Users/me/models/part.step", backend_mod.normalized_file_ref("/Users/me/models/part.step"))


class ServerInfoRootTests(unittest.TestCase):
    def test_the_reported_root_matches_what_the_backend_resolves(self):
        with _as_windows(), _windows_os_for(server_info):
            info = server_info.build_viewer_server_info(root_dir="/D:/some/project")

        self.assertEqual("D:\\some\\project", info["rootPath"])
        self.assertEqual("D:\\some\\project", info["rootDir"])
        self.assertEqual("project", info["rootName"])


class ViewerUrlTests(unittest.TestCase):
    def test_a_windows_directory_produces_a_usable_url(self):
        with _as_windows(), _windows_os_for(start_viewer):
            url = start_viewer.viewer_url("127.0.0.1", 3245, "D:\\some\\project")

        # Concatenating the raw path yielded `http://127.0.0.1:3245D:\some\project`,
        # which is not a URL at all.
        self.assertEqual("http://127.0.0.1:3245/D:/some/project", url)

    @unittest.skipIf(
        os.name == "nt",
        "asserts POSIX semantics, which is a claim about the HOST rather than about the\n        code under test: on Windows a leading-slash path really is drive-relative, so\n        D:/Users/... is the right answer there, not a regression.",
    )
    def test_a_posix_directory_is_unchanged(self):
        with _as_posix():
            self.assertEqual(
                "http://127.0.0.1:3245/Users/me/models",
                start_viewer.viewer_url("127.0.0.1", 3245, "/Users/me/models"),
            )

    def test_no_directory_still_yields_the_bare_origin(self):
        self.assertEqual("http://127.0.0.1:3245/", start_viewer.viewer_url("127.0.0.1", 3245, ""))


if __name__ == "__main__":
    unittest.main()
