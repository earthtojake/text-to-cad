"""The three distributions, by where their code runs, and what each may import.

- **The library** (``texttocad``: ``cad``, and ``cadgen``, its earlier name): what a model imports and
  what runs in a worker -- the model API, the kernel-side engine, the document model and the protocol
  a client speaks. It runs in the CAD kernel environment, where the server is not installed, so it
  imports no module of the server's or the shim's, not even lazily: every import a library module
  makes, at its top or in a function, is of the library.
- **The server** (``texttocad-server``: ``cad_server``): what runs in the daemon or a command -- the
  daemon, the registry, the HTTP API, the CAD Viewer's and the CAD app's servers, every verb, the
  environment makers, telemetry. It runs in the core, where the CAD kernel is not installed, so
  importing every module of it loads no kernel module, not even bound lazily (the build123d extra lives in
  the base: ``cad_server._internal.base``). Of the library it imports the modules that need no kernel.
- **The shim** (``texttocad-mcp``: ``cad_mcp``): the stdio transport an agent app starts, the standard
  library alone.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import LIBRARY, REPO_ROOT, SERVER, SHIM, SOURCE_PATH, add_sources

add_sources()

# Each distribution's source tree and the top-level packages it holds.
TREES = {LIBRARY / "src": ("cad", "cadgen"), SERVER / "src": ("cad_server",), SHIM / "src": ("cad_mcp",)}
SERVER_PACKAGE, SHIM_PACKAGE = "cad_server", "cad_mcp"
# The build123d extra's distributions, as their modules are named, and what build123d brings.
KERNEL = ("OCP", "build123d", "bd_materials", "threejs_materials", "matplotlib", "shapely", "lib3mf", "scipy",
          "sklearn", "IPython")
# What a model's process and a worker import first: none of them may bring a module of the server's.
MODEL_ENTRY_POINTS = ("cadgen", "cad", "cad.engine", "cad.engine.api", "cad.engine.model", "cad.engine.build",
                      "cad.engine.worker", "cad.engine.client", "cad.engine.serve", "cad.engine.reader",
                      "cad.engine.render.service", "cad.engine.snapshot", "cad.ap242", "cad.gltf",
                      "cad.geometry", "cad.flatten", "cad.eng_drawing", "cad.urdf", "cad.sdf",
                      "cad.srdf")


def module_name(source: Path, path: Path) -> str:
    parts = list(path.relative_to(source).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def modules(top: str) -> dict[str, Path]:
    """The modules of the top-level package ``top``, from the source tree that holds it."""
    source = next(source for source, tops in TREES.items() if top in tops)
    return {module_name(source, path): path for path in sorted((source / top).rglob("*.py"))
            if "_runtime" not in path.parts}


def of(package: str, name: str) -> bool:
    return name == package or name.startswith(package + ".")


def imports(name: str, path: Path) -> list[tuple[int, str]]:
    """Every module ``path`` imports -- at its top or in a function, and by ``importlib.import_module`` of
    a literal name -- as ``(line, module)``: a ``from X import Y`` names ``X.Y`` too, which is a module
    when ``Y`` is one."""
    package = name.split(".") if path.name == "__init__.py" else name.split(".")[:-1]
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            module = ".".join(base + ([node.module] if node.module else []))
            found += [(node.lineno, module)] + [(node.lineno, f"{module}.{alias.name}") for alias in node.names]
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "import_module" \
                and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            found.append((node.lineno, node.args[0].value))
    return found


def loaded(code: str) -> list[str]:
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO_ROOT,
                          env={**os.environ, "PYTHONPATH": SOURCE_PATH})
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


class SidesTest(unittest.TestCase):
    def test_each_distribution_holds_its_own_packages_alone(self) -> None:
        for source, tops in TREES.items():
            with self.subTest(source=source.relative_to(REPO_ROOT).as_posix()):
                found = sorted(path.name for path in source.iterdir()
                               if path.is_dir() and not path.name.endswith(".egg-info") and path.name != "__pycache__")
                self.assertEqual(found, sorted(tops))

    def test_the_library_imports_no_module_of_the_server_or_the_shim(self) -> None:
        offenders = []
        for top in ("cad", "cadgen"):
            for name, path in modules(top).items():
                for line, imported in imports(name, path):
                    if of(SERVER_PACKAGE, imported) or of(SHIM_PACKAGE, imported):
                        offenders.append(f"{name}:{line} -> {imported}")
        self.assertEqual(offenders, [])

    def test_a_models_process_loads_no_module_of_the_server_or_the_shim(self) -> None:
        code = ("import importlib, json, sys\n"
                f"for name in {MODEL_ENTRY_POINTS!r}:\n"
                "    importlib.import_module(name)\n"
                f"print(json.dumps(sorted(name for name in sys.modules if name.partition('.')[0] in "
                f"{(SERVER_PACKAGE, SHIM_PACKAGE)!r})))\n")
        self.assertEqual(loaded(code), [])

    def test_the_server_imports_no_kernel_module(self) -> None:
        server = sorted(name for name in modules(SERVER_PACKAGE) if not name.endswith("__main__"))
        self.assertGreater(len(server), 60)
        code = ("import importlib, json, sys\n"
                f"for name in {server!r}:\n"
                "    importlib.import_module(name)\n"
                f"print(json.dumps(sorted(name for name in sys.modules if name.partition('.')[0] in {KERNEL!r})))\n")
        self.assertEqual(loaded(code), [])

    def test_the_shim_imports_the_standard_library_and_itself_alone(self) -> None:
        offenders = []
        for name, path in modules(SHIM_PACKAGE).items():
            for line, imported in imports(name, path):
                root = imported.partition(".")[0]
                if root != SHIM_PACKAGE and root not in sys.stdlib_module_names and root != "__future__":
                    offenders.append(f"{name}:{line} -> {imported}")
        self.assertEqual(offenders, [])
        shim = sorted(name for name in modules(SHIM_PACKAGE) if not name.endswith("__main__"))
        # What the environment loads at its start (a checkout's .pth binds the lazy kernel) is not the shim's.
        code = ("import importlib, json, sys\n"
                "before = set(sys.modules)\n"
                f"for name in {shim!r}:\n"
                "    importlib.import_module(name)\n"
                "print(json.dumps(sorted(name for name in set(sys.modules) - before "
                f"if name.partition('.')[0] in {('cad', 'cadgen', SERVER_PACKAGE)!r})))\n")
        self.assertEqual(loaded(code), [])


if __name__ == "__main__":
    unittest.main()
