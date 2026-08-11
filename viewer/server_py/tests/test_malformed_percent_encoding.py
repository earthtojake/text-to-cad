"""A malformed percent-escape must not take the viewer down.

`GET /__cad/foo%zz.step` crashed the whole Node CAD Viewer server: it called
`decodeURIComponent` on the raw pathname outside any try, and JS throws `URIError` on an
invalid escape. Fixed on develop in #192 -- against `viewer/src/server/httpHandlers.mjs`,
a file this branch DELETED when the backend became Python, which is why merging develop
conflicts here.

"The file is gone" is not on its own a reason to drop a crash fix. The reason is that
Python's `urllib.parse.unquote` does not raise on a malformed escape at all -- it passes
the invalid sequence through unchanged -- so the failure mode has no analogue in the
replacement. That is a stdlib guarantee rather than something this repo controls, which is
exactly why it is worth pinning: if a future path swaps in a strict decoder, this fails
instead of the server.
"""

from __future__ import annotations

import unittest
from urllib.parse import unquote

MALFORMED = (
    "/__cad/foo%zz.step",   # the request from the original report
    "foo%zz.step",
    "%",                    # truncated escape
    "%e0%a4%a",             # truncated multi-byte sequence
    "%ff%fe",               # valid escapes, invalid UTF-8
)


class MalformedPercentEncodingTests(unittest.TestCase):
    def test_unquote_never_raises(self):
        for value in MALFORMED:
            with self.subTest(value=value):
                self.assertIsInstance(unquote(value), str)

    def test_an_invalid_escape_passes_through_rather_than_decoding(self):
        self.assertEqual("/__cad/foo%zz.step", unquote("/__cad/foo%zz.step"))

    def test_the_path_helpers_survive_it(self):
        from server_py import backend  # noqa: PLC0415 - deferred like its callers

        for value in MALFORMED:
            with self.subTest(value=value):
                # Whatever this returns, it must RETURN -- not raise.
                self.assertIsInstance(backend.normalized_file_ref(value), str)


if __name__ == "__main__":
    unittest.main()
