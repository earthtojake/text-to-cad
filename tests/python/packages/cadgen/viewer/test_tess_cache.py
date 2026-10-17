"""The viewer's read-only routes to the store's parts: a route path's name, URI-decoded
and checked; the status a read answers; and the batch requests and container.

What the routes read is the store's, and its suites hold it (test_store_tess_cache,
test_store_parts). The container test does not read the format by eye — it hands the
Python encoder's bytes to the AUTHORITATIVE decoder in ``packages/core``, which is where
the format lives. A hand-written assertion about offsets would pass just as happily
against a subtly wrong encoder, and the client would then silently fall back to one
round trip per component for the life of the page.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from cadgen.viewer.tess_cache import (
    TESS_CACHE_ROUTE_PREFIX,
    read_tess_cache_batch,
    read_tess_cache_entry,
    tess_cache_name_from_route_path,
)

from tests.python.support.tessellation import part_fixture, store_part

FIXTURE = part_fixture()
GOOD_KEY = FIXTURE["key"]
PAYLOAD = base64.b64decode(FIXTURE["glb"])
TABLE = base64.b64decode(FIXTURE["selectors"])
RECORD = FIXTURE["record"]
# Another part's key: well formed, and stored nowhere.
ABSENT_KEY = "2" * 64 + GOOD_KEY[64:]


def admitted(key=GOOD_KEY, size=None):
    return {"part": key, "object": RECORD["glb"]["object"], "maxBytes": len(PAYLOAD) if size is None else size}

# The authoritative codec: @text-to-cad/core in this repository. The suite is root-owned
# and runs from a checkout, so the source path is always present -- no skip.
REPO_ROOT = Path(__file__).resolve().parents[5]
CADGEN_JS_CODEC = REPO_ROOT / "packages" / "core" / "src" / "lib" / "parts" / "tessellationCache.js"


class TessCacheTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Blank every root the resolver consults, not just the one this
        # platform reads: setting HOME alone leaves the sandbox a no-op on
        # Windows and lets the tests write into the runner's real cache.
        self._saved = {
            name: os.environ.get(name)
            for name in (
                "CADGEN_CACHE_DIR",
                "XDG_CACHE_HOME",
                "LOCALAPPDATA",
                "HOME",
                "USERPROFILE",
            )
        }
        self.addCleanup(self._restore)
        for name in self._saved:
            os.environ.pop(name, None)
        os.environ["HOME"] = self.tmp.name
        os.environ["USERPROFILE"] = self.tmp.name
        os.environ["CADGEN_CACHE_DIR"] = os.path.join(self.tmp.name, "cache")

    def _restore(self) -> None:
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def route(self, name: str) -> str:
        return f"{TESS_CACHE_ROUTE_PREFIX}{name}"

    def read(self, name: str, role: str = "glb", **admission):
        """``read_tess_cache_entry`` for ``name``, admitted by the record's facts of ``role``
        unless ``admission`` says otherwise."""
        facts = RECORD[role]
        admission = {"expected_object": facts["object"], "max_bytes": facts["byteLength"], **admission}
        return read_tess_cache_entry(self.route(name), **admission)


class NameValidation(TessCacheTestCase):
    def test_a_parts_two_objects_are_named_by_its_key(self):
        for suffix in (".glb", ".selectors.json"):
            with self.subTest(suffix=suffix):
                self.assertEqual(tess_cache_name_from_route_path(self.route(GOOD_KEY + suffix)), GOOD_KEY + suffix)

    def test_an_encoded_traversal_is_decoded_and_refused(self):
        # The store lives outside every folder a file is served from, so containment
        # cannot help here: the part key's pattern is the whole defence, and it judges
        # the decoded name (the store's suite holds the pattern).
        for name in ("%2e%2e%2fescape.glb", "..%2Fescape.glb"):
            with self.subTest(name=name):
                self.assertIsNone(tess_cache_name_from_route_path(self.route(name)))

    def test_a_malformed_percent_escape_is_a_refusal_not_a_crash(self):
        for name in ("%zz.glb", "%.glb", "%2.glb", "%C0%AF.glb", "%ED%A0%80.glb"):
            with self.subTest(name=name):
                self.assertIsNone(tess_cache_name_from_route_path(self.route(name)))

    def test_a_trailing_newline_does_not_sneak_past_the_anchor(self):
        # Python's `$` also matches before a trailing newline; JavaScript's does
        # not. fullmatch is what keeps the two the same.
        self.assertIsNone(tess_cache_name_from_route_path(self.route(f"{GOOD_KEY}.glb%0A")))


class ReadStatus(TessCacheTestCase):
    def test_a_hit_is_200_a_miss_404_and_a_refused_name_403(self):
        self.assertEqual(self.read(f"{ABSENT_KEY}.glb")[0], 404)
        self.assertEqual(self.read("../escape.glb")[0], 403)
        self.assertEqual(store_part(), RECORD)
        self.assertEqual(self.read(f"{GOOD_KEY}.glb"), (200, PAYLOAD))
        self.assertEqual(self.read(f"{GOOD_KEY}.selectors.json", "selectors"), (200, TABLE))
        self.assertEqual(self.read(f"{GOOD_KEY}.glb", expected_object="f" * 64)[0], 404,
                         "a read the record does not admit is a miss")
        self.assertEqual(self.read(f"{GOOD_KEY}.tess")[0], 403, "a mesh is a GLB body")


class BatchRequests(TessCacheTestCase):
    def test_a_malformed_request_is_none_so_the_route_can_answer_400(self):
        # CPython's C JSON scanner has a separate recursion guard from
        # sys.getrecursionlimit(); this remains below the HTTP metadata cap.
        depth = 10_000
        for body in (b"not json", b"[]", b'{"names":"x"}', b"{}", b'{"names":null}',
                     b'{"entries":' + b'[' * depth + b'0' + b']' * depth + b'}'):
            with self.subTest(body=body):
                self.assertIsNone(read_tess_cache_batch(body))

    def test_one_undecodable_byte_is_a_per_entry_miss_not_a_400(self):
        """``Buffer.from(body).toString("utf8")`` substitutes; it does not throw.

        The per-entry-miss rule, applied to the BYTES. Strict decoding turned a
        single bad byte anywhere in the request into a malformed-request 400, so
        one component's name cost an assembly its entire tessellation round trip
        and dropped it to one request per component for the life of the page.
        Node answered every other name in the batch.
        """
        import struct

        store_part()
        body = json.dumps({"entries": [admitted(), admitted("NAME_HERE")]}).encode()
        container = read_tess_cache_batch(body.replace(b"NAME_HERE", b"\xe9"))
        self.assertIsNotNone(container, "a bad byte must not fail the whole batch")
        # The header's third word is the entry count: the real hit, plus the
        # substituted name as an ordinary miss.
        self.assertEqual(struct.unpack_from("<I", container, 8)[0], 2)


class BatchFramingMatchesTheAuthoritativeCodec(TessCacheTestCase):
    """The Python encoder's bytes must decode with the JS decoder that owns the format.

    Neither precondition is allowed to make this disappear quietly. A missing
    codec is a FAILURE — @text-to-cad/core ships with the app, so its absence means the
    tree is broken, not that this machine is unusual. A missing `node` is a
    failure too: the client is a JavaScript app, so anywhere this suite runs
    can run its decoder. Skipping on either is how the check went dead the
    first time.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not CADGEN_JS_CODEC.is_file():
            raise AssertionError(
                f"the authoritative tessellation-cache codec is missing: {CADGEN_JS_CODEC}. "
                "@text-to-cad/core is vendored at packages/core and ships with this app; "
                "without it the Python encoder's framing is verified by nothing."
            )
        if not shutil.which("node"):
            raise AssertionError(
                "node is not on PATH, so the authoritative decoder cannot be run. The client "
                "is a JavaScript app — anywhere this suite runs, node is installable and "
                "required; this check must not be skipped."
            )

    def decode_with_node(self, container: bytes):
        # The import specifier is a file:// URL, never a bare absolute path: a
        # Windows path like D:\...\tessellationCache.js parses as a URL with
        # scheme "d:", which node's ESM loader refuses outright.
        script = f"""
        import {{ decodeTessellationCacheBatch }} from {json.dumps(CADGEN_JS_CODEC.as_uri())};
        const bytes = Uint8Array.from(JSON.parse(process.argv[1]));
        const entries = decodeTessellationCacheBatch(bytes);
        process.stdout.write(JSON.stringify(
          entries === null ? null : entries.map((e) => (e === null ? null : Array.from(e)))));
        """
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", script, "--", json.dumps(list(container))],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.fail(f"the authoritative decoder failed (exit {result.returncode}):\n{result.stderr}")
        return json.loads(result.stdout)

    def test_hit_miss_and_refusal_decode_in_order(self):
        store_part()
        container = read_tess_cache_batch(
            json.dumps(
                {"entries": [admitted(), admitted(ABSENT_KEY), admitted("../escape")]}
            ).encode()
        )
        # A refused name and a miss are per-entry MISSES, never errors: one bad
        # key must not cost an assembly its whole round trip.
        self.assertEqual(self.decode_with_node(container), [list(PAYLOAD), None, None])

    def test_a_non_string_name_is_a_miss_and_keeps_the_container_valid(self):
        store_part()
        container = read_tess_cache_batch(
            json.dumps({"entries": [17, admitted(), None]}).encode()
        )
        self.assertEqual(self.decode_with_node(container), [None, list(PAYLOAD), None])

    def test_an_empty_request_still_produces_a_valid_container(self):
        container = read_tess_cache_batch(json.dumps({"entries": []}).encode())
        self.assertEqual(len(container), 12)
        self.assertEqual(self.decode_with_node(container), [])


if __name__ == "__main__":
    unittest.main()
