"""Building a STEP document's tree must never require Node.

STEP is the core build path: it is what the CAD skill runs for every generated model, and
it is pure OCP/build123d. The DXF package is the one that bakes its
preview in a JS builder, and cadgen resolves Node lazily -- ``cad_node_executable()`` is
called at build time, not import time -- precisely so a STEP-only environment never needs
it.

That property is easy to lose by accident. ``cadgen.step_artifact`` already IMPORTS the
Node bridge transitively (step_artifact -> component_package -> generation ->
drawing_package -> node_runtime), so a static import check would report a dependency that
does not exist in practice, and adding one Node call inside the shared generation path
would break STEP for everyone with no test to catch it.

So this asserts the behaviour instead: point ``CADGEN_NODE`` at a path that is not an
executable, which makes ``cad_node_executable()`` raise ``NodeUnavailable`` the moment
anything tries to resolve Node, and build a STEP package. If the build succeeds, nothing
on the STEP path went looking for Node.

Runs in a subprocess: the build imports OCP, and the env var has to be set for the whole
process rather than patched around one call.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from unittest import mock
from tests.python.support.tmp_root import generated_cad_directory

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CADGEN_SRC = str(_REPO_ROOT / "packages" / "cadgen" / "src")

_MODEL = """\
from build123d import BuildPart, Box, Cylinder, Mode


from cadgen import step
@step
def model():
    with BuildPart() as part:
        Box(30, 20, 10)
        Cylinder(radius=4, height=10, mode=Mode.SUBTRACT)
    return part.part


if __name__ == "__main__":
    model()
"""

_PROBE = """
import json, sys
sys.path.insert(0, {src!r})

from cadgen.generation import generate_step_targets

exit_code = generate_step_targets([{model!r}])
print(json.dumps({{"ok": exit_code == 0, "exit_code": exit_code}}))
"""


class StepBuildsWithoutNodeTests(unittest.TestCase):
    def test_a_step_package_builds_with_node_unresolvable(self):
        with generated_cad_directory(prefix="step-no-node-") as tmp:
            root = Path(tmp)
            model = root / "block.py"
            model.write_text(_MODEL, encoding="utf-8")

            env = {**os.environ, "CADGEN_DAEMON": "0", "CADGEN_CACHE_DIR": str(root / "store")}
            # Not an executable, so cad_node_executable() raises NodeUnavailable rather than
            # falling back to PATH. Any attempt to reach Node fails loudly.
            env["CADGEN_NODE"] = str(root / "definitely-not-node")

            proc = subprocess.run(
                [sys.executable, "-c", _PROBE.format(src=_CADGEN_SRC, model=str(model), root=str(root))],
                capture_output=True,
                text=True,
                cwd=str(root),
                env=env,
            )

            self.assertEqual(
                0,
                proc.returncode,
                "Building a STEP package reached for Node. STEP is pure OCP/build123d and "
                "must stay buildable without a Node toolchain.\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{textwrap.indent(proc.stderr, '  ')}",
            )
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
            self.assertTrue(payload.get("ok"))

            from cadgen.catalog import result_tree_for
            from cadgen.store.trees import tree_complete
            with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": env["CADGEN_CACHE_DIR"]}):
                tree = result_tree_for(root / "block.step")
                self.assertTrue(tree and tree_complete(tree), f"No complete geometry tree under {root}")
            self.assertFalse((root / "store/index/surface").exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
