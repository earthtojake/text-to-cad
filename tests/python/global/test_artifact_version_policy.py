"""No hand-copied version that can drift, and no number nobody reads.

A number stamped into a payload that nothing checks is not a contract; it is a value that
looks load-bearing and invites a reader to reason about compatibility that was never enforced.
And an external constant (the glTF container's framing) declared twice is two places to get
it wrong.
"""

from __future__ import annotations

import re
import unittest

from tests.python.support.paths import REPO_ROOT

ROOT = REPO_ROOT


class DeadVersionsStayDeadTest(unittest.TestCase):
    """Versions that were stamped into a payload and never read by anything.

    A number nobody checks is not a contract; it is a value that looks load-bearing
    and invites a reader to reason about compatibility that was never enforced.
    """

    def test_viewer_server_info_schema_version_is_gone(self) -> None:
        self.assertNotIn(
            "VIEWER_SERVER_INFO_SCHEMA_VERSION",
            (ROOT / "packages/cadgen/src/cadgen/viewer/http_app.py").read_text(encoding="utf-8"),
        )

    def test_the_glb_container_is_declared_once(self) -> None:
        # The container's magic, version and chunk types are the glTF 2.0 spec's, not ours
        # to bump, and two copies of an external constant is two places to get it wrong:
        # the one GLB cadgen writes outside the engine (a robot primitive's mesh) is framed in
        # cadgen._internal.primitive_mesh. cadgen.engine is the one exception: it is standalone
        # by law (it imports nothing of cadgen outside itself) and writes its own GLB, so it
        # declares the container once more, in its GLB writer.
        package = ROOT / "packages/cadgen/src/cadgen"
        magic = re.compile(r"0x46546c67|b[\"']glTF[\"']", re.IGNORECASE)
        declarations = sorted(
            path.relative_to(package).as_posix()
            for path in package.rglob("*.py")
            if magic.search(path.read_text(encoding="utf-8"))
        )
        self.assertEqual(["_internal/primitive_mesh.py", "engine/export/glb.py"], declarations)


if __name__ == "__main__":
    unittest.main()
