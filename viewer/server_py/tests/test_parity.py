"""Assert the Python encoders match Node byte-for-byte via golden.json.

golden.json is produced by gen_golden.mjs from the real JS semantics. If it is
missing, regenerate it with: ``node viewer/server_py/tests/gen_golden.mjs``.
"""

import json
import os
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from server_py import encoding, natural_sort, urls  # noqa: E402

_GOLDEN_PATH = pathlib.Path(__file__).resolve().parent / "golden.json"


def load_golden():
    if not _GOLDEN_PATH.exists():
        raise unittest.SkipTest(
            "golden.json missing — run: node viewer/server_py/tests/gen_golden.mjs"
        )
    # encoding: golden.json is UTF-8 and holds names like 'résumé (1).glb'. read_text()
    # without one uses the LOCALE encoding, which is cp1252 on a Windows runner -- so the
    # corpus decoded into different characters and the encoders were blamed for it.
    return json.loads(_GOLDEN_PATH.read_text(encoding='utf-8'))


class EncodeUriComponentParity(unittest.TestCase):
    def test_matches_node(self):
        golden = load_golden()["encodeUriComponent"]
        for source, expected in golden.items():
            self.assertEqual(encoding.encode_uri_component(source), expected, source)


class ContentDispositionParity(unittest.TestCase):
    def test_matches_node(self):
        golden = load_golden()["contentDisposition"]
        for source, expected in golden.items():
            self.assertEqual(
                encoding.attachment_content_disposition(source), expected, repr(source)
            )


class Base36Parity(unittest.TestCase):
    def test_matches_node(self):
        golden = load_golden()["base36"]
        for source, expected in golden.items():
            self.assertEqual(encoding.base36(int(source)), expected, source)


@unittest.skipIf(
    os.name == "nt",
    "the corpus feeds POSIX absolute paths, and this is the one parity case that also\n    exercises absolute_file_ref -- which is platform-dependent BY DESIGN: on Windows\n    '/abs/x.glb' is drive-relative and resolves to 'D:/abs/x.glb'. The encoders either\n    side of it are pure string work and stay covered here.",
)
class AssetUrlParity(unittest.TestCase):
    def test_matches_node(self):
        for case in load_golden()["assetUrls"]:
            built = urls.local_asset_url_for_path(
                case["file"], version=case["v"], root_dir=case["dir"]
            )
            self.assertEqual(built, case["url"], case)


class NaturalSortParity(unittest.TestCase):
    def test_matches_node(self):
        for case in load_golden()["sort"]:
            entries = [{"file": name} for name in case["input"]]
            got = [e["file"] for e in natural_sort.sort_catalog_entries(entries)]
            self.assertEqual(got, case["sorted"], case["input"])


if __name__ == "__main__":
    unittest.main()
