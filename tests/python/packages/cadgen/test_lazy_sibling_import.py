"""A model runs like ``python script.py``: its folder stays on ``sys.path`` for the
whole build, so an import inside the body -- or inside a helper the body calls --
resolves exactly like one at module top, and the file it loads is still in the
closure (every first-party file is hashed when it executes).

The tom-cad migration hit the old behaviour (the folder was seeded for the module
body only and removed before the model ran): a ``lib/`` helper that imported a
sibling model inside a function failed or passed depending on what some other
module had already imported. Real CLI runs, a temp store, ``CADGEN_DAEMON=0``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT
from tests.python.support.tmp_root import temporary_directory

PIN = """
    from cadgen import step
    from cadgen import build123d as bd


    @step
    def pin():
        return bd.Cylinder(radius=2.0, height=12.0)


    if __name__ == "__main__":
        pin()
"""

GEOMETRY = """
    def pin_shape():
        # A sibling MODEL imported lazily, inside the helper the body calls.
        from pin import pin

        return pin()
"""

ARM = """
    from cadgen import step
    from cadgen import build123d as bd
    from lib import geometry


    @step
    def arm():
        p = geometry.pin_shape()
        return bd.Compound(children=[bd.Box(40, 8, 4), bd.Pos(-15, 0, 2) * p], label="arm")


    if __name__ == "__main__":
        arm()
"""

DIMS = """
    def size():
        return {size}
"""

BOX = """
    from cadgen import step
    from cadgen import build123d as bd


    @step
    def box():
        from lib import dims   # lazily, inside the body

        return bd.Box(dims.size(), 5, 5)


    if __name__ == "__main__":
        box()
"""


def _run(*argv: str, cwd: Path, cache: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in [str(REPO_ROOT / "packages" / "cadgen" / "src"), env.get("PYTHONPATH", "")] if p
    )
    env["CADGEN_CACHE_DIR"] = str(cache)
    env["CADGEN_DAEMON"] = "0"
    env.pop("CADGEN_DAEMON_CHILD", None)
    return subprocess.run(
        [sys.executable, *argv], cwd=str(cwd), env=env, capture_output=True, text=True, timeout=600
    )


class LazySiblingImport(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temporary_directory(prefix="lazy-sibling-import-")
        self.root = Path(self._tmp.name) / "proj"
        (self.root / "src" / "lib").mkdir(parents=True)
        (self.root / "src" / "lib" / "__init__.py").write_text("", encoding="utf-8")
        self.cache = Path(self._tmp.name) / "store"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, name: str, text: str) -> None:
        (self.root / "src" / name).write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")

    def test_a_helper_may_import_a_sibling_model_inside_a_function(self) -> None:
        self._write("pin.py", PIN)
        self._write("lib/geometry.py", GEOMETRY)
        self._write("arm.py", ARM)
        # cwd is the project root, NOT src/: only the seeded path can satisfy `from pin import pin`.
        result = _run("src/arm.py", cwd=self.root, cache=self.cache)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue((self.root / "src" / "arm.step").is_file())
        why = _run("-m", "cadgen.cli", "store", "why", "src/arm.py", cwd=self.root, cache=self.cache)
        self.assertEqual(0, why.returncode, why.stdout + why.stderr)
        self.assertIn("verdict current", why.stdout)
        # The lazily called child is pinned like any other child.
        self.assertIn("children (1)", why.stdout)
        self.assertIn("pin.py", why.stdout)

    def test_a_lazily_imported_helper_is_in_the_closure(self) -> None:
        self._write("lib/dims.py", DIMS.replace("{size}", "5"))
        self._write("box.py", BOX)
        result = _run("src/box.py", cwd=self.root, cache=self.cache)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        why = _run("-m", "cadgen.cli", "store", "why", "src/box.py", cwd=self.root, cache=self.cache)
        self.assertEqual(0, why.returncode, why.stdout + why.stderr)
        self.assertIn("lib/dims.py", why.stdout)
        # Edit the file the body imported lazily: the model is stale, and why names the file.
        self._write("lib/dims.py", DIMS.replace("{size}", "6"))
        why = _run("-m", "cadgen.cli", "store", "why", "src/box.py", cwd=self.root, cache=self.cache)
        self.assertEqual(1, why.returncode, why.stdout + why.stderr)
        self.assertIn("closure changed: lib/dims.py", why.stdout)


if __name__ == "__main__":
    unittest.main()
