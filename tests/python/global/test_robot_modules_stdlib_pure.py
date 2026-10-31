"""The URDF/SRDF/SDF VALIDATION family in cadgen must stay stdlib-pure.

These modules are deliberately extraction-ready: robot-description validation is a
text/XML problem, not a CAD-kernel problem, and keeping the family free of
OCP/build123d/numpy is what preserves the option of breaking it back out of cadgen
(or running it in an environment without the heavy dependency set). A heavy import
added in passing would silently destroy that property — every suite would still
pass, because the test environment has the kernel installed.

Static check over the AST (not an import-time sys.modules probe) so an offending
import is caught even when it is lazy, conditional, or function-local. Drawing a robot
is the engine's (`cadgen snapshot` draws one), outside this family.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
# Where each package of the family lives: the library's and the server's source trees.
LIBRARY_SRC = REPO_ROOT / "packages" / "texttocad" / "src"
SERVER_SRC = REPO_ROOT / "packages" / "texttocad-server" / "src"
OURS = ("cad", "cad_server", "cadgen")

FAMILY = [
    LIBRARY_SRC / "cad" / name for name in (
        "urdf_source.py",
        "srdf_source.py",
        "srdf_validation.py",
        "sdf_source.py",
        "sdf_validation.py",
        "sdf_external.py",
        "findings.py",
        "xml_common.py",
        # The public namespaces the CLIs are shells over (packages/texttocad/README.md, law 6).
        # They are the family's front door now, so they inherit its purity rule.
        "urdf.py",
        "srdf.py",
        "sdf.py",
        "_internal/validation_door.py",
        "engine/mesh_uri.py",  # what every reader of a mesh reference resolves it with
    )
] + [SERVER_SRC / "cad_server" / "cli" / name for name in ("urdf_validate.py", "srdf_validate.py", "sdf_validate.py")]

# Heavy roots that would break extraction-readiness. The packages themselves are allowed only
# for the family's own light members (findings, xml_common, and each other).
FORBIDDEN_ROOTS = {"OCP", "build123d", "numpy", "ocp_tessellate", "ezdxf", "playwright"}
ALLOWED_CADGEN = {
    "cad.findings",
    "cad.xml_common",
    "cad.urdf_source",
    "cad.srdf_source",
    "cad.srdf_validation",
    "cad.sdf_source",
    "cad.sdf_validation",
    "cad.sdf_external",
    "cad_server.cli",  # shared CLI plumbing, itself lazy
    "cad.results",  # the typed line protocol: dataclasses and pathlib only
    "cad._internal.validation_door",  # findings -> ValidationResult, stdlib only
    "cad_server._internal.cli_from_function",  # argparse over a signature, stdlib only
    # A mesh reference's scheme and local file, read the same way by the engine's stills
    # (which may import nothing of the library outside the engine): stdlib only.
    "cad.engine.mesh_uri",
}

# What importing the family must not drag in. `cadgen urdf validate` runs on machines with
# none of these installed.
HEAVY_AT_IMPORT = ("OCP", "build123d", "playwright", "numpy", "ezdxf")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            # `from cad.engine import mesh_uri` imports the submodule, not the package's surface.
            submodules = {f"{node.module}.{alias.name}" for alias in node.names}
            found.update(submodules if submodules <= ALLOWED_CADGEN else {node.module})
    return found


class RobotModulesStdlibPure(unittest.TestCase):
    def test_family_files_exist(self) -> None:
        missing = [str(path.relative_to(REPO_ROOT)) for path in FAMILY if not path.is_file()]
        self.assertEqual(missing, [], "family member moved or deleted — update FAMILY")

    def test_no_heavy_imports_anywhere_in_the_family(self) -> None:
        offenders: list[str] = []
        for path in FAMILY:
            rel = path.relative_to(REPO_ROOT).as_posix()
            for module in sorted(_imports(path)):
                root = module.split(".")[0]
                if root in FORBIDDEN_ROOTS:
                    offenders.append(f"{rel}: {module}")
                elif root in OURS and module not in ALLOWED_CADGEN:
                    offenders.append(f"{rel}: {module} (not in the allowed light set)")
        self.assertEqual(
            offenders,
            [],
            "the robot-description family must stay stdlib-pure (extraction-ready); "
            "move heavy work out or extend ALLOWED_CADGEN only for light modules",
        )


class ImportCost(unittest.TestCase):
    """Importing the family must stay free.

    Run in a subprocess: this one has the CAD stack loaded already.
    """

    def test_the_namespaces_import_without_the_heavy_stack(self) -> None:
        code = (
            "import sys, cad.urdf, cad.srdf, cad.sdf;"
            f"print('HEAVY:' + ','.join(m for m in {HEAVY_AT_IMPORT!r} if m in sys.modules))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(LIBRARY_SRC), "PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("HEAVY:\n", proc.stdout)


if __name__ == "__main__":
    unittest.main()
