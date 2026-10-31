"""The package's three sides, by where their code runs, and what each may import.

- **The library**: what a model imports and what runs in a worker -- the model API, the kernel-side
  engine, the document model and the protocol a client speaks. It runs in the CAD kernel environment,
  where the server is not installed, so it imports no module of the server's or the shim's, not even
  lazily: every import a library module makes, at its top or in a function, is of the library.
- **The server**: what runs in the daemon or a ``cadgen`` command -- the daemon, the registry, the HTTP
  API, the CAD Viewer's and the CAD app's servers, every verb, the environment makers, telemetry. It runs
  in the core, where the CAD kernel is not installed, so importing every module of it loads no kernel
  module, not even bound lazily (the kernel extra lives in the base: ``cadgen._internal.base``).
- **The shim**: the stdio transport an agent app starts (``cad_mcp``), the standard library alone.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT, add_repo_path

add_repo_path("packages/cadgen/src")

SRC = REPO_ROOT / "packages" / "cadgen" / "src"

# The kernel extra's distributions, as their modules are named, and what build123d brings.
KERNEL = ("OCP", "build123d", "bd_materials", "threejs_materials", "matplotlib", "shapely", "lib3mf", "scipy",
          "sklearn", "IPython")
# The server's modules, by name (a package names its submodules too): run in the daemon or a command.
SERVER = ("cadgen.cli", "cadgen.viewer", "cadgen.mcp", "cadgen.engine.daemon", "cadgen.engine.registry",
          "cadgen.engine.models", "cadgen.engine.cache", "cadgen.engine.cli", "cadgen.engine.__main__",
          "cadgen.analytics", "cadgen.updates", "cadgen.settings", "cadgen.language", "cadgen.assets", "cadgen.jobs",
          "cadgen.drawing_payload", "cadgen.robot_payload",
          *(f"cadgen._internal.{name}" for name in (
              "api", "base", "channel", "cli_errors", "cli_from_function", "editable", "engine_daemon", "engine_host",
              "engine_telemetry", "file_lock", "installations", "kernel_load_hint", "launch", "leftovers", "picker",
              "primitive_mesh", "providers", "proxy", "releases", "shared_read", "switch", "telemetry_send", "update")))
SHIM = "cad_mcp"
# What a model's process and a worker import first: none of them may bring a module of the server's.
MODEL_ENTRY_POINTS = ("cadgen", "cadgen.engine", "cadgen.engine.api", "cadgen.engine.model", "cadgen.engine.build",
                      "cadgen.engine.worker", "cadgen.engine.client", "cadgen.engine.serve", "cadgen.engine.reader",
                      "cadgen.engine.render.service", "cadgen.engine.snapshot", "cadgen.ap242", "cadgen.gltf",
                      "cadgen.geometry", "cadgen.flatten", "cadgen.eng_drawing", "cadgen.urdf", "cadgen.sdf",
                      "cadgen.srdf")


def module_name(path: Path) -> str:
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def modules(top: str) -> dict[str, Path]:
    return {module_name(path): path for path in sorted((SRC / top).rglob("*.py")) if "_runtime" not in path.parts}


def of_server(name: str) -> bool:
    return any(name == prefix or name.startswith(prefix + ".") for prefix in SERVER)


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
                          env={**os.environ, "PYTHONPATH": str(SRC)})
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


class SidesTest(unittest.TestCase):
    def test_the_partition_names_modules_that_are_there(self) -> None:
        found = modules("cadgen")
        for prefix in SERVER:
            with self.subTest(prefix=prefix):
                self.assertTrue(any(name == prefix or name.startswith(prefix + ".") for name in found),
                                f"{prefix} names no module")

    def test_the_library_imports_no_module_of_the_server_or_the_shim(self) -> None:
        offenders = []
        for name, path in modules("cadgen").items():
            if of_server(name):
                continue
            for line, imported in imports(name, path):
                if of_server(imported) or imported == SHIM or imported.startswith(SHIM + "."):
                    offenders.append(f"{name}:{line} -> {imported}")
        self.assertEqual(offenders, [])

    def test_a_models_process_loads_no_module_of_the_server_or_the_shim(self) -> None:
        code = ("import importlib, json, sys\n"
                f"for name in {MODEL_ENTRY_POINTS!r}:\n"
                "    importlib.import_module(name)\n"
                "print(json.dumps(sorted(name for name in sys.modules if name.startswith(('cadgen', 'cad_mcp')))))\n")
        self.assertEqual([name for name in loaded(code) if of_server(name) or name.partition(".")[0] == SHIM], [])

    def test_the_server_imports_no_kernel_module(self) -> None:
        server = sorted(name for name in modules("cadgen") if of_server(name) and not name.endswith("__main__"))
        self.assertGreater(len(server), 60)
        code = ("import importlib, json, sys\n"
                f"for name in {server!r}:\n"
                "    importlib.import_module(name)\n"
                f"print(json.dumps(sorted(name for name in sys.modules if name.partition('.')[0] in {KERNEL!r})))\n")
        self.assertEqual(loaded(code), [])

    def test_the_shim_imports_the_standard_library_and_itself_alone(self) -> None:
        offenders = []
        for name, path in modules(SHIM).items():
            for line, imported in imports(name, path):
                root = imported.partition(".")[0]
                if root != SHIM and root not in sys.stdlib_module_names and root != "__future__":
                    offenders.append(f"{name}:{line} -> {imported}")
        self.assertEqual(offenders, [])
        shim = sorted(name for name in modules(SHIM) if not name.endswith("__main__"))
        # What the environment loads at its start (a checkout's .pth binds the lazy kernel) is not the shim's.
        code = ("import importlib, json, sys\n"
                "before = set(sys.modules)\n"
                f"for name in {shim!r}:\n"
                "    importlib.import_module(name)\n"
                "print(json.dumps(sorted(name for name in set(sys.modules) - before "
                "if name.partition('.')[0] == 'cadgen')))\n")
        self.assertEqual(loaded(code), [])


if __name__ == "__main__":
    unittest.main()
