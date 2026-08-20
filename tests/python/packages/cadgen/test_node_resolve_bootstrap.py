"""The Node builder's ``--import`` bootstrap URL has to be valid on Windows too.

`node_runtime` built it as ``"file://" + pathname2url(path)``. On POSIX `pathname2url` returns
``/usr/...`` and that concatenation is correct, which is why this went unnoticed; on Windows it
returns a leading ``///`` (urllib delegates to `nturl2path`), so the prefix doubled into a
five-slash URL and Node rejected it before the builder wrote anything:

    TypeError [ERR_INVALID_FILE_URL_PATH]: File URL path must be absolute
      input: 'file://///C:/Users/.../node_resolve_register.mjs'

Issue #266. Every Node builder invocation on Windows went through that line, in every vendored
copy of the module, so it is worth pinning from a POSIX CI box as well as a Windows one --
`nturl2path` and `PureWindowsPath` are importable everywhere, so the platform-specific behaviour
is testable without the platform.
"""

from __future__ import annotations

import nturl2path
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.node_runtime import node_resolve_bootstrap  # noqa: E402

WINDOWS_PATH = r"C:\Users\M\AppData\Roaming\npm\plugin 0.4.10\cadgen\_internal\node_resolve_register.mjs"
POSIX_PATH = "/home/m/.local/share/plugin 0.4.10/cadgen/_internal/node_resolve_register.mjs"


class NodeResolveBootstrapUrlTests(unittest.TestCase):
    def test_the_bootstrap_url_is_a_valid_absolute_file_url(self) -> None:
        url = node_resolve_bootstrap()
        self.assertTrue(url.startswith("file:///"), url)
        # Four or more slashes is the #266 failure: Node reads everything after ``file://`` as a
        # host, so an extra pair makes the path non-absolute.
        self.assertFalse(url.startswith("file:////"), f"malformed file URL: {url}")

    def test_the_url_points_at_the_shipped_bootstrap_file(self) -> None:
        from urllib.parse import urlparse
        from urllib.request import url2pathname

        resolved = Path(url2pathname(urlparse(node_resolve_bootstrap()).path))
        self.assertTrue(resolved.is_file(), resolved)
        self.assertEqual("node_resolve_register.mjs", resolved.name)

    def test_as_uri_is_correct_on_both_platforms_where_concatenation_was_not(self) -> None:
        """The fix, and the bug it replaced, on both platform flavours from one box."""
        # What the old line produced on Windows: pathname2url already supplies ``///``.
        broken = "file://" + nturl2path.pathname2url(WINDOWS_PATH)
        self.assertTrue(broken.startswith("file://///"), broken)

        # What as_uri() produces: three slashes, drive letter intact, spaces encoded.
        windows_url = PureWindowsPath(WINDOWS_PATH).as_uri()
        self.assertTrue(windows_url.startswith("file:///C:/"), windows_url)
        self.assertFalse(windows_url.startswith("file:////"), windows_url)
        self.assertIn("plugin%200.4.10", windows_url, "a space in the install path must be encoded")

        posix_url = PurePosixPath(POSIX_PATH).as_uri()
        self.assertTrue(posix_url.startswith("file:///home/"), posix_url)
        self.assertIn("plugin%200.4.10", posix_url)

    def test_no_vendored_copy_builds_a_file_url_by_concatenation(self) -> None:
        """The module is vendored into every skill runtime, so the pattern must be gone from all
        of them -- a stale copy would keep failing on Windows while the source read correctly."""
        offenders = []
        # Committed trees only. `tmp/` holds throwaway copies the bundle checks extract for
        # comparison, and a stale one there says nothing about what ships.
        roots = [repo_path("packages"), repo_path("skills"), repo_path("viewer")]
        candidates = [
            candidate
            for root in roots
            for candidate in root.rglob("node_runtime.py")
            if not any(part in {"node_modules", "dist", "tmp", "__pycache__"} or part.startswith(".")
                       for part in candidate.relative_to(repo_path()).parts)
        ]
        self.assertTrue(candidates, "expected at least the canonical module")
        for candidate in candidates:
            text = candidate.read_text(encoding="utf-8")
            # Strip comments so this test cannot be tripped by prose describing the bug.
            code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
            if '"file://" +' in code or "'file://' +" in code:
                offenders.append(str(candidate.relative_to(repo_path())))
        self.assertEqual([], offenders, "these build a file URL by concatenation")


if __name__ == "__main__":
    unittest.main()
