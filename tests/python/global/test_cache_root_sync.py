"""The mesh-store contract is CROSS-LANGUAGE.

cadgen writes the store's mesh entries (cadgen/store/meshes.py) and the CAD
Viewer's client keys, probes and reads them
(packages/core/src/lib/surf/tessellationCache.js). A one-sided change to the key
scheme or its tessellator-version salt would split "one store warms every
consumer" into silent misses, so each is pinned against the other here, the same
way test_render_contract_sync pins the render contract. The tolerances are not
among them: the client keeps none, and every request names the pair cadgen chose.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

ROOT = Path(__file__).resolve().parents[3]
TESSELLATION_CACHE_JS = ROOT / "packages" / "core" / "src" / "lib" / "surf" / "tessellationCache.js"


def _node() -> str:
    """The development Node that evaluates the client's half of the contract."""
    node = shutil.which("node")
    if node is None:
        raise AssertionError("node is required to evaluate the JavaScript half of the mesh-store contract")
    return node


class MeshStoreContractSyncTest(unittest.TestCase):
    def test_tessellator_version_matches_between_python_and_js(self) -> None:
        from cadgen.store.meshes import TESSELLATOR_VERSION

        source = TESSELLATION_CACHE_JS.read_text(encoding="utf-8")
        match = re.search(r"^export const TESSELLATION_VERSION = (\d+);", source, re.MULTILINE)
        assert match, "TESSELLATION_VERSION not found in tessellationCache.js"
        self.assertEqual(
            int(match.group(1)),
            TESSELLATOR_VERSION,
            "the mesh key's tessellator-version salt diverged between languages — bump "
            "TESSELLATION_VERSION (tessellationCache.js) and TESSELLATOR_VERSION "
            "(cadgen/store/meshes.py) together",
        )

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

    def test_key_scheme_carries_the_version_salt(self) -> None:
        # Policy: the key must salt the algorithm version. Grep-level pin so a
        # JS-side refactor cannot drop it without failing a Python-side gate.
        self.assertIn("-t${TESSELLATION_VERSION}-", TESSELLATION_CACHE_JS.read_text(encoding="utf-8"))

    def test_complete_tessellation_keys_match_between_python_and_js(self) -> None:
        from cadgen.store.meshes import tessellation_key

        cases = [("a" * 64, 0.0015, 0.005), ("b" * 64, 0.00001, 0.013),
                 ("a" * 64, 0.0015000000000000002, 0.005)]
        script = f'''
import fs from "node:fs";
import {{ tessellationCacheKey }} from {json.dumps(TESSELLATION_CACHE_JS.as_uri())};
console.log(JSON.stringify(JSON.parse(fs.readFileSync(0,"utf8")).map(([surfaceInput, chordTolerance, angleTolerance]) =>
  tessellationCacheKey(surfaceInput, {{chordTolerance, angleTolerance}}))));
'''
        result = subprocess.run([_node(), "--input-type=module", "-e", script],
                                input=json.dumps(cases), text=True, capture_output=True, check=True)
        self.assertEqual([tessellation_key(*case) for case in cases], json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
