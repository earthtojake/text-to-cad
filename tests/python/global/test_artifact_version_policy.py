"""One cache key per file type, and no hand-copied version that can drift.

Two rules, both learned the hard way.

The first: a cached artifact's version has to cover EVERYTHING about how that
artifact was produced -- the descriptor's layout and the bytes inside the payloads
it references. Split across two numbers, a fix ships half applied: the descriptor
advances while content-addressed payloads are reused unchanged, and the package
reports itself current while serving the old bytes.

The second: ``STEP_TOPOLOGY_SCHEMA_VERSION`` is a Python->JS wire contract, and the
JS client throws on a mismatch. It is declared once in each language, so nothing
but this test stops the two from drifting -- which is the same
"a second hand-copied number is how the two drift" failure that put the package
version in a stdlib-only module in the first place.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT, add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.glb_topology import STEP_TOPOLOGY_SCHEMA_VERSION
from cadgen._internal.cache_schema import CACHE_SCHEMA_VERSION

ROOT = REPO_ROOT


class TopologySchemaVersionMirrorTest(unittest.TestCase):
    def test_python_and_js_declare_the_same_topology_schema_version(self) -> None:
        source = (ROOT / "packages/cadgen-js/src/common/stepTopology.mjs").read_text(encoding="utf-8")
        match = re.search(r"STEP_TOPOLOGY_SCHEMA_VERSION\s*=\s*(\d+)", source)
        self.assertIsNotNone(match, "cadgen-js must declare STEP_TOPOLOGY_SCHEMA_VERSION")
        self.assertEqual(
            STEP_TOPOLOGY_SCHEMA_VERSION,
            int(match.group(1)),
            "cadgen and cadgen-js disagree on STEP_topology schemaVersion; the JS client throws "
            "on a mismatch, so a bump has to land in both languages together",
        )


class PackageVersionIsOneNumberPerFileTypeTest(unittest.TestCase):
    def test_the_step_cid_salt_is_the_cache_schema_version_itself(self) -> None:
        # Not merely equal to it: the same constant. A separate payload version is the
        # split this rule exists to prevent.
        from cadgen._internal import component_package

        self.assertIs(component_package.CACHE_SCHEMA_VERSION, CACHE_SCHEMA_VERSION)

    def test_no_separate_payload_version_has_reappeared(self) -> None:
        source = (
            ROOT / "packages/cadgen/src/cadgen/_internal/component_package.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            "COMPONENT_PAYLOAD_VERSION",
            source,
            "the component payload version was folded into CACHE_SCHEMA_VERSION; a second "
            "number lets a descriptor bump ship without re-emitting the payloads",
        )

    def test_each_file_type_keeps_its_own_cache_key(self) -> None:
        # Deliberately NOT one shared number: a drawing rebuild is milliseconds and a
        # large STEP assembly is tens of seconds, so a DXF change must not re-mesh every
        # STEP model on next open. The gate lives in the store KEY salt now
        # (cadgen.catalog.package_dir_for_hash), not in a descriptor check: a
        # version bump orphans old packages by key.
        source = (ROOT / "packages/cadgen/src/cadgen/catalog.py").read_text(encoding="utf-8")
        # DXF is absent by design: a generated drawing's render IS the sibling
        # .dxf the client parses, so there is no artifact to gate.
        for constant in (
            "CACHE_SCHEMA_VERSION",
        ):
            self.assertIn(
                constant,
                source,
                f"the store key salt must carry {constant} so that file type invalidates "
                "independently of the others",
            )


class DeadVersionsStayDeadTest(unittest.TestCase):
    """Versions that were stamped into a payload and never read by anything.

    A number nobody checks is not a contract; it is a value that looks load-bearing
    and invites a reader to reason about compatibility that was never enforced.
    """

    def test_dxf_render_schema_version_is_gone_from_both_languages(self) -> None:
        for relative in (
            "packages/cadgen/src/cadgen/drawing_render.py",
            "packages/cadgen-js/src/lib/dxf/parseDxf.js",
        ):
            self.assertNotIn(
                "DXF_RENDER_SCHEMA_VERSION",
                (ROOT / relative).read_text(encoding="utf-8"),
                f"{relative} stamped a version nothing ever read",
            )

    def test_viewer_server_info_schema_version_is_gone(self) -> None:
        self.assertNotIn(
            "VIEWER_SERVER_INFO_SCHEMA_VERSION",
            (ROOT / "packages/cadgen/src/cadgen/viewer/http_app.py").read_text(encoding="utf-8"),
        )

    def test_the_gltf_container_version_is_declared_once(self) -> None:
        # GLB_VERSION is the glTF 2.0 spec's container version, not ours to bump, and
        # two copies of an external constant is two places to get it wrong.
        declarations = [
            path
            for path in (ROOT / "packages/cadgen/src/cadgen/_internal").glob("*.py")
            if re.search(r"^GLB_VERSION\s*=", path.read_text(encoding="utf-8"), re.MULTILINE)
        ]
        self.assertEqual(
            ["glb_topology.py"],
            sorted(path.name for path in declarations),
        )


if __name__ == "__main__":
    unittest.main()
