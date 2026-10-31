"""The library's engine stands alone: it imports nothing of the packages but itself, and a build loads
nothing of them beyond what importing the library itself loads. The engine's modules the server runs
-- the daemon, the registry, the live models' book, the document cache and the verbs as commands --
are the server's (``cad_server.engine``, ``test_core_imports``), which takes its application and
telemetry from its own composition root."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import LIBRARY, SOURCE_PATH

ENGINE = LIBRARY / "src" / "cad" / "engine"
# The packages' import names: the library (its earlier name, an alias of it, among them), the server
# and the shim.
OURS = {"cad", "cadgen", "cad_server", "cad_mcp"}
# Law 3: what the engine imports besides itself and the standard library. Pillow is the renderer's
# rasteriser (a dependency of the library's kernel already). OCCT draws every snapshot, of every kind,
# so no module drives a browser.
LIBRARIES = {"OCP", "build123d", "bd_materials", "threejs_materials", "numpy", "PIL"}
# By module, what one imports beyond those: ezdxf, build123d's own DXF library, which the DXF
# export writes and checks a drawing with.
BESIDES = {"export/dxf.py": {"ezdxf"}}


def library_files() -> list[Path]:
    return sorted(ENGINE.rglob("*.py"))


def ours_beyond_the_engine(name: str) -> bool:
    """Whether the module ``name`` is the packages' own and not the library's engine."""
    return name.split(".")[0] in OURS and not (name == "cad.engine" or name.startswith("cad.engine."))


class StandaloneTest(unittest.TestCase):
    def test_every_engine_module_imports_only_the_engine_of_the_packages(self) -> None:
        offenders = []
        files = library_files()
        self.assertGreater(len(files), 10)
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        offenders.append(f"{path.name}: a relative import")
                        continue
                    names = [node.module or ""]
                    if node.module in OURS:
                        names = [f"{node.module}.{alias.name}" for alias in node.names]
                for name in names:
                    if ours_beyond_the_engine(name):
                        offenders.append(f"{path.relative_to(ENGINE)}: {name}")
                if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) in (
                        "import_module", "__import__"):
                    for argument in node.args[:1]:
                        if isinstance(argument, ast.Constant) and ours_beyond_the_engine(str(argument.value)):
                            offenders.append(f"{path.relative_to(ENGINE)}: {argument.value}")
        self.assertEqual(offenders, [])

    def test_every_engine_module_imports_only_the_standard_library_and_the_engine_s_libraries(self) -> None:
        offenders = []
        for path in library_files():
            name = path.relative_to(ENGINE).as_posix()
            allowed = set(sys.stdlib_module_names) | LIBRARIES | {"cad"} | BESIDES.get(name, set())
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
                if isinstance(node, ast.Import):
                    roots = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                    roots = [node.module.split(".")[0]]
                else:
                    continue
                offenders += [f"{name}: {root}" for root in roots if root not in allowed]
        self.assertEqual(offenders, [])

    def test_a_build_loads_no_module_of_the_packages_but_the_engine(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "part.py"
            script.write_text(textwrap.dedent("""
                import build123d as bd
                from cad.engine import xbf, step, stl

                @xbf("XBF/part.xbf")
                @step("part.step")
                @stl("part.stl")
                def part():
                    return bd.Box(1, 2, 3) - bd.Cylinder(0.3, 5)
            """), encoding="utf-8")
            code = textwrap.dedent(f"""
                import json, sys
                import cad
                ours = {sorted(OURS)!r}
                baseline = {{name for name in sys.modules if name.split(".")[0] in ours}}
                from pathlib import Path
                from cad.engine.build import build
                from cad.engine import document, serve, mesh
                reports = build(Path({str(script)!r}))
                document.load(Path({folder!r}) / "XBF/part.xbf").structure()
                loaded = {{name for name in sys.modules if name.split(".")[0] in ours}} - baseline
                print(json.dumps({{"ok": reports[0]["ok"], "extra": sorted(loaded)}}))
            """)
            env = {**os.environ, "PYTHONPATH": SOURCE_PATH}
            done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=folder)
            self.assertEqual(done.returncode, 0, done.stderr)
            answer = json.loads(done.stdout.strip().splitlines()[-1])
            self.assertTrue(answer["ok"])
            self.assertEqual([name for name in answer["extra"] if ours_beyond_the_engine(name)], [])


if __name__ == "__main__":
    unittest.main()
