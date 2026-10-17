"""The part-store contract is CROSS-LANGUAGE.

cadgen writes each part's record and the two objects it names (cadgen/store/parts.py;
the display mesh's codec is cadgen/store/meshes.py) and the CAD Viewer's client reads
them (packages/core/src/lib/parts/tessellationCache.js) by the key a view names. The
client derives no key and keeps no tolerance, so what is pinned here is what each side
must take of the other: a body's bound, and a record cadgen stores being a row the
client reads whole -- its fields, and the decoded size both sides compute -- naming a
body the client matches to it. A one-sided change would split "one store warms every
consumer" into silent misses.
"""

from __future__ import annotations

import base64
import json
import os
import re
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

ROOT = Path(__file__).resolve().parents[3]
TESSELLATION_CACHE_JS = ROOT / "packages" / "core" / "src" / "lib" / "parts" / "tessellationCache.js"


def _unmeshed_part(fixture: dict) -> tuple[str, bytes, bytes]:
    """Another part, whose mesh leaves its second face undrawn: its record counts it."""
    from cadgen.store.meshes import encode_payload

    floats = lambda *values: struct.pack(f"<{len(values)}f", *values)  # noqa: E731
    key = "3" * 64 + fixture["key"][64:]
    glb = encode_payload(
        part=key, positions=floats(0, 0, 0, 2, 0, 0, 0, 3, 0), normals=floats(0, 0, 1, 0, 0, 1, 0, 0, 1),
        indices=struct.pack("<3I", 0, 1, 2),
        face_ranges=[{"ord": 1, "indexStart": 0, "indexCount": 3}, {"ord": 2, "indexStart": 3, "indexCount": 0}],
        edges=[], bounds={"min": [0, 0, 0], "max": [2, 3, 0]}, unmeshed_faces=[2],
    )
    return key, glb, base64.b64decode(fixture["selectors"])


class PartStoreContractSyncTest(unittest.TestCase):
    def test_json_bound_matches_between_python_and_js(self) -> None:
        # A body's JSON chunk grows with its face colour palette, so its bound is
        # a limit on the components either side takes: a body cadgen stores and
        # the client refuses is a component the Viewer can never draw.
        from cadgen.store.meshes import MAX_JSON_BYTES

        source = TESSELLATION_CACHE_JS.read_text(encoding="utf-8")
        match = re.search(r"^export const MESH_MAX_JSON_BYTES = (\d+) \* 1024 \* 1024;", source, re.MULTILINE)
        assert match, "MESH_MAX_JSON_BYTES not found in tessellationCache.js"
        self.assertEqual(
            int(match.group(1)) * 1024 * 1024,
            MAX_JSON_BYTES,
            "MESH_MAX_JSON_BYTES (tessellationCache.js) diverged from MAX_JSON_BYTES "
            "(cadgen/store/meshes.py) — change both together",
        )

    def test_a_record_cadgen_stores_is_a_row_the_client_reads_whole(self) -> None:
        from cadgen.store import parts
        from tests.python.support.tessellation import node, part_fixture, store_part

        fixture = part_fixture()
        key, glb, table = _unmeshed_part(fixture)
        with tempfile.TemporaryDirectory() as store, mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": store}):
            stored = {fixture["key"]: (store_part(fixture), fixture["glb"]),
                      key: (parts._write(key, glb, table), base64.b64encode(glb).decode("ascii"))}
            self.assertEqual({part: parts.probe(part) for part in stored}, {part: row[0] for part, row in stored.items()})
        self.assertEqual(stored[key][0]["glb"]["unmeshedFaceCount"], 1)
        script = f'''
import fs from "node:fs";
import {{ partMeshMatches, partRow }} from {json.dumps(TESSELLATION_CACHE_JS.as_uri())};
console.log(JSON.stringify(JSON.parse(fs.readFileSync(0, "utf8")).map(([part, record, glb]) => {{
  const row = partRow(part, record);
  return [row, row !== null && partMeshMatches(new Uint8Array(Buffer.from(glb, "base64")), row)];
}})));
'''
        result = subprocess.run([node(), "--input-type=module", "-e", script],
                                input=json.dumps([[part, record, body] for part, (record, body) in stored.items()]),
                                text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout),
                         [[{"part": part, **record}, True] for part, (record, _body) in stored.items()])


if __name__ == "__main__":
    unittest.main()
