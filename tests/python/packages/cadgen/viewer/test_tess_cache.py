"""The viewer's read-only transport over the store's meshes, and shared TESB framing.

Ports ``tessCache.test.mjs``. The container test does not read the format by
eye — it hands the Python encoder's bytes to the AUTHORITATIVE decoder in
``packages/core``, which is where the format lives. A hand-written
assertion about offsets would pass just as happily against a subtly wrong
encoder, and the client would then silently fall back to one round trip per
component for the life of the page.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from cadgen.viewer.tess_cache import (
    TESS_CACHE_ROUTE_PREFIX,
    read_tess_cache_batch,
    read_tess_cache_entry,
    tess_cache_key_from_route_path,
)
from cadgen.store import meshes
from cadgen.store.tess_cache import tessellation_cache_dir

from tests.python.support.tessellation import tessellation_fixture

FIXTURE = tessellation_fixture()
GOOD_KEY = FIXTURE["key"]
PAYLOAD = base64.b64decode(FIXTURE["bytes"])

def admitted(key=GOOD_KEY, size=None):
    return {"tessellationInput": key, "object": FIXTURE["facts"]["object"],
            "maxBytes": len(PAYLOAD) if size is None else size}

# The authoritative codec: @text-to-cad/core in this repository. The suite is root-owned
# and runs from a checkout, so the source path is always present -- no skip.
REPO_ROOT = Path(__file__).resolve().parents[5]
CADGEN_JS_CODEC = REPO_ROOT / "packages" / "core" / "src" / "lib" / "surf" / "tessellationCache.js"


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


class NameValidation(TessCacheTestCase):
    def test_the_canonical_key_is_accepted(self):
        self.assertEqual(tess_cache_key_from_route_path(self.route(f"{GOOD_KEY}.glb")), GOOD_KEY)

    def test_traversal_separators_hidden_names_and_spaces_are_refused(self):
        # The cache lives outside every folder a file is served from, so containment
        # cannot help here: this pattern is the whole defence.
        for name in (
            "../escape.glb",
            "sub/dir.glb",
            "%2e%2e%2fescape.glb",
            "..%2Fescape.glb",
            ".hidden.glb",
            "noext",
            "",
            "a b.glb",
            "a..b.glb",
            "batch",
        ):
            with self.subTest(name=name):
                self.assertIsNone(tess_cache_key_from_route_path(self.route(name)))

    def test_a_malformed_percent_escape_is_a_refusal_not_a_crash(self):
        for name in ("%zz.glb", "%.glb", "%2.glb", "%C0%AF.glb", "%ED%A0%80.glb"):
            with self.subTest(name=name):
                self.assertIsNone(tess_cache_key_from_route_path(self.route(name)))

    def test_a_trailing_newline_does_not_sneak_past_the_anchor(self):
        # Python's `$` also matches before a trailing newline; JavaScript's does
        # not. fullmatch is what keeps the two the same.
        self.assertIsNone(tess_cache_key_from_route_path(self.route("a.glb%0A")))


class StoreRoundTrip(TessCacheTestCase):
    def test_a_stored_mesh_reads_back_exactly(self):
        meshes.write(GOOD_KEY, PAYLOAD)
        status, body = read_tess_cache_entry(self.route(f"{GOOD_KEY}.glb"))
        self.assertEqual(status, 200)
        self.assertEqual(body, PAYLOAD)

    def test_a_miss_is_404_and_a_refused_name_is_403(self):
        self.assertEqual(read_tess_cache_entry(self.route("absent-t1.glb"))[0], 404)
        self.assertEqual(read_tess_cache_entry(self.route("../escape.glb"))[0], 403)
        meshes.write(GOOD_KEY, PAYLOAD)
        self.assertEqual(read_tess_cache_entry(self.route(f"{GOOD_KEY}.tess"))[0], 403, "a mesh is a GLB body")

    def test_a_mesh_is_indexed_by_its_key_itself(self):
        meshes.write(GOOD_KEY, PAYLOAD)
        names = os.listdir(tessellation_cache_dir())
        self.assertEqual(names, [GOOD_KEY], "an index entry is keyed by the mesh key itself")


class BatchRequests(TessCacheTestCase):
    def test_a_malformed_request_is_none_so_the_route_can_answer_400(self):
        # CPython's C JSON scanner has a separate recursion guard from
        # sys.getrecursionlimit(); this remains below the HTTP metadata cap.
        depth = 10_000
        for body in (b"not json", b"[]", b'{"names":"x"}', b"{}", b'{"names":null}',
                     b'{"entries":' + b'[' * depth + b'0' + b']' * depth + b'}'):
            with self.subTest(body=body):
                self.assertIsNone(read_tess_cache_batch(body))

    def test_more_than_the_cap_is_refused(self):
        self.assertIsNone(read_tess_cache_batch(json.dumps({"entries": [admitted()] * 257}).encode()))
        self.assertIsNotNone(read_tess_cache_batch(json.dumps({"entries": []}).encode()))

    def test_one_undecodable_byte_is_a_per_entry_miss_not_a_400(self):
        """``Buffer.from(body).toString("utf8")`` substitutes; it does not throw.

        The per-entry-miss rule, applied to the BYTES. Strict decoding turned a
        single bad byte anywhere in the request into a malformed-request 400, so
        one component's name cost an assembly its entire tessellation round trip
        and dropped it to one request per component for the life of the page.
        Node answered every other name in the batch.
        """
        import struct

        meshes.write(GOOD_KEY, PAYLOAD)
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
        meshes.write(GOOD_KEY, PAYLOAD)
        container = read_tess_cache_batch(
            json.dumps(
                {"entries": [admitted(), admitted("absent-t1"), admitted("../escape")]}
            ).encode()
        )
        # A refused name and a miss are per-entry MISSES, never errors: one bad
        # key must not cost an assembly its whole round trip.
        self.assertEqual(self.decode_with_node(container), [list(PAYLOAD), None, None])

    def test_unaligned_payloads_round_trip(self):
        # 1, 2 and 3 mod 4 all exercise the padding; a decoder that advances by
        # the raw length instead of the aligned one desynchronises after the
        # first such entry.
        # Framing also accepts odd-length body readers; real GLB bodies
        # themselves are aligned. Keep this isolated from payload validation.
        entries = [bytes(range(size)) for size in (1, 2, 3, 4, 5)]
        with mock.patch("cadgen.store.tess_cache.read_tessellation_cache", side_effect=entries):
            container = read_tess_cache_batch(json.dumps({"entries": [admitted()] * 5}).encode())
        self.assertEqual(self.decode_with_node(container), [list(entry) for entry in entries])

    def test_a_non_string_name_is_a_miss_and_keeps_the_container_valid(self):
        meshes.write(GOOD_KEY, PAYLOAD)
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
