"""Smoke-test cadgen[organic] from an isolated wheel install.

Install only the wheel and dependencies named by its organic extra, pinning
Trimesh to the declared lower bound. This catches a missing direct dependency
or a minimum version whose mesh-copy contract is too old.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def run(command: list[str], *, cwd: Path) -> str:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(
            f"{command[0]} exited {result.returncode}:\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout.strip()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: check-organic-wheel.py <cadgen.whl>")
    wheel = Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="cadgen-organic-wheel-") as folder:
        root = Path(folder)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
             "--no-deps", str(wheel)], cwd=root)
        requirements = run([str(python), "-c", """
from importlib.metadata import requires
for requirement in requires("cadgen"):
    if 'extra == "organic"' in requirement or "extra == 'organic'" in requirement:
        print(requirement.split(";", 1)[0].strip())
"""], cwd=root).splitlines()
        if not requirements:
            raise RuntimeError("Wheel declares no cadgen[organic] dependencies")
        trimesh_requirement = next(
            (item for item in requirements if item.startswith("trimesh>=")), None
        )
        if trimesh_requirement is None or "," in trimesh_requirement:
            raise RuntimeError("Wheel needs a single explicit Trimesh lower bound")
        minimum_trimesh = trimesh_requirement.split(">=", 1)[1]
        requirements = [
            f"trimesh=={minimum_trimesh}" if item == trimesh_requirement else item
            for item in requirements
        ]
        run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
             *requirements], cwd=root)
        output = run([str(python), "-c", """
import pathlib
import sys
from importlib.metadata import version
import cadgen
import numpy as np
import trimesh
from cadgen.organic import prepare_mesh

assert pathlib.Path(cadgen.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve())
assert version("trimesh") == sys.argv[1]
colored = trimesh.creation.box()
rgba = np.tile([0.5, 0.5, 0.5, 0.399], (len(colored.vertices), 1))
colored.vertex_attributes["cadgen_color_linear"] = rgba
copied = colored.copy()
np.testing.assert_array_equal(copied.vertex_attributes["cadgen_color_linear"], rgba)
copied.vertex_attributes["cadgen_color_linear"][0, 3] = 0.4
assert colored.vertex_attributes["cadgen_color_linear"][0, 3] == 0.399
damaged = trimesh.creation.box()
damaged.update_faces(np.arange(len(damaged.faces)) != 0)
repaired, audit = prepare_mesh(damaged, fill_small_holes=True)
assert repaired.is_volume and audit["added_cap_triangles"] == 1
print("wheel organic extra: minimum Trimesh copy and hole repair passed")
""", minimum_trimesh], cwd=root)
        print(output)


if __name__ == "__main__":
    main()
