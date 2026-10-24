"""The engine stands alone: it imports nothing of cadgen but itself, and a build loads
nothing of cadgen beyond what importing the package itself loads."""

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

ENGINE = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src" / "cadgen" / "engine"
SRC = ENGINE.parent.parent
# Law 3: what the engine imports besides itself and the standard library. Pillow is the renderer's
# rasteriser (a dependency of the cadgen wheel already). OCCT draws every snapshot, of every kind,
# so no module drives a browser.
LIBRARIES = {"OCP", "build123d", "numpy", "PIL"}
# By module, what one imports beyond those: ezdxf, build123d's own DXF library, which the DXF
# export writes and checks a drawing with.
BESIDES = {"export/dxf.py": {"ezdxf"}}


class StandaloneTest(unittest.TestCase):
    def test_every_engine_module_imports_only_the_engine_of_cadgen(self) -> None:
        offenders = []
        files = sorted(ENGINE.rglob("*.py"))
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
                    if node.module == "cadgen":
                        names = [f"cadgen.{alias.name}" for alias in node.names]
                for name in names:
                    if (name == "cadgen" or name.startswith("cadgen.")) and not (
                            name == "cadgen.engine" or name.startswith("cadgen.engine.")):
                        offenders.append(f"{path.relative_to(ENGINE)}: {name}")
                if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) in (
                        "import_module", "__import__"):
                    for argument in node.args[:1]:
                        if isinstance(argument, ast.Constant) and str(argument.value).startswith("cadgen") \
                                and not str(argument.value).startswith("cadgen.engine"):
                            offenders.append(f"{path.relative_to(ENGINE)}: {argument.value}")
        self.assertEqual(offenders, [])

    def test_every_engine_module_imports_only_the_standard_library_and_the_engine_s_libraries(self) -> None:
        offenders = []
        for path in sorted(ENGINE.rglob("*.py")):
            name = path.relative_to(ENGINE).as_posix()
            allowed = set(sys.stdlib_module_names) | LIBRARIES | {"cadgen"} | BESIDES.get(name, set())
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
                if isinstance(node, ast.Import):
                    roots = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                    roots = [node.module.split(".")[0]]
                else:
                    continue
                offenders += [f"{name}: {root}" for root in roots if root not in allowed]
        self.assertEqual(offenders, [])

    def test_a_build_loads_no_cadgen_module_but_the_engine(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "part.py"
            script.write_text(textwrap.dedent("""
                import build123d as bd
                from cadgen.engine import xbf, step, stl

                @xbf("XBF/part.xbf")
                @step("part.step")
                @stl("part.stl")
                def part():
                    return bd.Box(1, 2, 3) - bd.Cylinder(0.3, 5)
            """), encoding="utf-8")
            code = textwrap.dedent(f"""
                import json, sys
                import cadgen
                baseline = {{name for name in sys.modules if name.startswith("cadgen")}}
                from pathlib import Path
                from cadgen.engine.build import build
                from cadgen.engine import document, serve, mesh
                reports = build(Path({str(script)!r}))
                document.load(Path({folder!r}) / "XBF/part.xbf").structure()
                loaded = {{name for name in sys.modules if name.startswith("cadgen")}} - baseline
                print(json.dumps({{"ok": reports[0]["ok"], "extra": sorted(loaded)}}))
            """)
            env = {**os.environ, "PYTHONPATH": str(SRC)}
            done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=folder)
            self.assertEqual(done.returncode, 0, done.stderr)
            answer = json.loads(done.stdout.strip().splitlines()[-1])
            self.assertTrue(answer["ok"])
            self.assertEqual([name for name in answer["extra"] if not name.startswith("cadgen.engine")], [])


if __name__ == "__main__":
    unittest.main()
