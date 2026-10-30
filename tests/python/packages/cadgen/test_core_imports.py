"""The wheel's core runs the server's path with no CAD kernel: the MCP shim, the ``cadgen`` command and
its verbs, the engine's daemon and the CAD Viewer's server import none of the kernel's modules -- not
even bound lazily -- so ``uvx --from cadgen==X cadgen mcp`` resolves the core alone, and the kernel
(the ``kernel`` extra) lives in the base, the environment models run in (``cadgen._internal.base``)."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

# The kernel extra's distributions, as their modules are named, and what build123d brings.
KERNEL = ("OCP", "build123d", "bd_materials", "threejs_materials", "matplotlib", "shapely", "lib3mf", "scipy",
          "sklearn", "IPython")
SERVER = ("cadgen.mcp.shim", "cadgen.mcp.server", "cadgen.mcp.http", "cadgen.cli", "cadgen.cli.run",
          "cadgen.cli.doctor", "cadgen.cli.setup", "cadgen.cli.server", "cadgen._internal.proxy",
          "cadgen._internal.base", "cadgen._internal.engine_daemon", "cadgen.engine.daemon",
          "cadgen.engine.client", "cadgen.engine.serve", "cadgen.viewer.engine_app", "cadgen.viewer.http_app")


class CoreTest(unittest.TestCase):
    def test_the_servers_path_imports_no_kernel_module(self) -> None:
        code = ("import importlib, json, sys\n"
                f"for name in {SERVER!r}:\n"
                "    importlib.import_module(name)\n"
                f"print(json.dumps(sorted(name for name in sys.modules if name.partition('.')[0] in {KERNEL!r})))\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout.strip().splitlines()[-1]), [])


if __name__ == "__main__":
    unittest.main()
