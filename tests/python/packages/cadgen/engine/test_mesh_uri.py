"""A robot description's mesh reference as every reader of one resolves it (``cadgen.engine.mesh_uri``):
a drive letter is not a URI scheme, a ``file:`` URI is the platform's path, and a ``file:`` URI's host is
a share on Windows and no local file elsewhere. Windows is pinned on every platform by reading the
references with Windows' ``url2pathname``, as ``cadgen (Windows)`` reads them natively."""

from __future__ import annotations

import os
import unittest
import warnings
from unittest import mock

from cadgen.engine import mesh_uri

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)  # the module is deprecated in 3.14; Windows' urllib uses its own
    from nturl2path import url2pathname as windows_url2pathname

LOCAL = ("C:/robot/base.stl", "C:\\robot\\base.stl", "c:/robot/base.stl", "file:///C:/robot/base.stl",
         "file://localhost/C:/robot/base.stl", "file:///C:/my%20robot/base.stl", "file://server/share/base.stl")


class MeshUriTest(unittest.TestCase):
    def test_windows_reads_drive_paths_file_uris_and_shares(self) -> None:
        with mock.patch.object(mesh_uri, "_WINDOWS", True), \
                mock.patch.object(mesh_uri, "url2pathname", windows_url2pathname):
            read = [mesh_uri.local_path(reference) for reference in LOCAL]
        self.assertEqual(read, ["C:/robot/base.stl", "C:\\robot\\base.stl", "c:/robot/base.stl", "C:\\robot\\base.stl",
                                "C:\\robot\\base.stl", "C:\\my robot\\base.stl", "\\\\server\\share\\base.stl"])

    @unittest.skipIf(os.name == "nt", "POSIX's reading; Windows' is pinned above")
    def test_posix_reads_a_drive_path_as_a_path_and_a_share_as_no_local_file(self) -> None:
        read = [mesh_uri.local_path(reference) for reference in LOCAL]
        self.assertEqual(read, ["C:/robot/base.stl", "C:\\robot\\base.stl", "c:/robot/base.stl", "/C:/robot/base.stl",
                                "/C:/robot/base.stl", "/C:/my robot/base.stl", None])

    def test_a_drive_letter_is_no_scheme_and_any_other_scheme_names_no_local_file(self) -> None:
        self.assertEqual([mesh_uri.scheme(reference) for reference in LOCAL[:3]], ["", "", ""])
        for reference in ("package://arm/meshes/base.stl", "model://arm/meshes/base.stl", "https://x.test/base.stl"):
            self.assertIsNone(mesh_uri.local_path(reference), reference)


if __name__ == "__main__":
    unittest.main()
