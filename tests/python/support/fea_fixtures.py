"""Shared fixtures for the FEA suites (``tests/python/packages/cadgen/test_fea*.py``).

Importing this puts cadgen's source on ``sys.path`` and says whether CalculiX, which
every solve needs, is installed; the heavy imports (build123d, numpy, cadgen.fea)
stay inside the helpers, so a suite's parse tests run without it.
"""

from __future__ import annotations

import io
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr
from pathlib import Path

from tests.python.support.paths import REPO_ROOT, add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

needs_fea = unittest.skipUnless(HAVE_FEA, "netgen or CalculiX (ccx) is not installed")


#: The studies' own materials, as numbers (a study names no table material): the values a datasheet gives.
STEEL_NUMBERS = {"name": "Steel (structural, generic)", "E_MPa": 200_000.0, "nu": 0.30, "yield_MPa": 250.0,
                 "density_t_per_mm3": 7.85e-9}
AL6061_NUMBERS = {"name": "Aluminum 6061-T6", "E_MPa": 68_900.0, "nu": 0.33, "yield_MPa": 276.0,
                  "density_t_per_mm3": 2.70e-9}
AL7075_NUMBERS = {"name": "Aluminum 7075-T6", "E_MPa": 71_700.0, "nu": 0.33, "yield_MPa": 503.0,
                  "density_t_per_mm3": 2.81e-9}
PLA_NUMBERS = {"name": "PLA", "E_MPa": 3_500.0, "nu": 0.36, "yield_MPa": 60.0, "density_t_per_mm3": 1.24e-9}


@contextmanager
def quiet():
    """The solver's progress lines go to stderr; a test that is not about them keeps them out of the run's output."""
    with redirect_stderr(io.StringIO()):
        yield


def solve(step: Path, out: Path, study: dict, **options):
    """``cadgen.fea.solve`` with its progress lines silenced."""
    from cadgen import fea

    with quiet():
        return fea.solve(step, out, study=study, **options)


def reported(result) -> dict:
    """The result as ``--json`` prints it: everything a solve says, the GLB aside."""
    from cadgen._internal.cli_from_function import result_payload

    return result_payload(result)


def class_directory(cls) -> Path:
    """A temporary directory for a TestCase class's fixtures, removed after its last test."""
    tmp = tempfile.TemporaryDirectory()
    cls.addClassCleanup(tmp.cleanup)
    return Path(tmp.name)


def heavy_at_import(*modules: str) -> str:
    """The heavy modules importing ``modules`` pulls into a fresh interpreter: "" when they are stdlib-only at import."""
    code = (f"import sys; sys.path.insert(0, 'packages/cadgen/src'); import {', '.join(modules)};"
            "print(','.join(m for m in ('numpy', 'scipy', 'netgen', 'OCP') if m in sys.modules))")
    return subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()


def value_error(case: unittest.TestCase, call, *args, **kwargs) -> str:
    """The message of the ValueError ``call(*args, **kwargs)`` must raise."""
    with case.assertRaises(ValueError) as caught:
        call(*args, **kwargs)
    return str(caught.exception)


# --- STEP fixtures --------------------------------------------------------------------------------------

def _align(align: str | None):
    from build123d import Align

    return {None: None, "x": (Align.MIN, Align.CENTER, Align.CENTER), "corner": (Align.MIN, Align.MIN, Align.MIN),
            "base": (Align.CENTER, Align.CENTER, Align.MIN), "base_x": (Align.MIN, Align.CENTER, Align.MIN)}[align]


def box_step(directory: Path, name: str, size: tuple[float, float, float], align: str | None = None) -> Path:
    """A build123d box written to ``directory/name.step``: centred on the origin, or with ``align`` "x" (length
    along +x from x = 0, centred in y and z), "corner" (in the +x +y +z octant), "base" (standing on z = 0) or
    "base_x" (standing on z = 0, along +x from x = 0)."""
    from build123d import Box, export_step

    step = directory / f"{name}.step"
    aligned = _align(align)
    export_step(Box(*size) if aligned is None else Box(*size, align=aligned), str(step))
    return step


def _listing(step_or_listing):
    if isinstance(step_or_listing, (str, Path)):
        from cadgen import fea

        return fea.faces(step_or_listing)
    return step_or_listing


def planes_along(step_or_listing, axis: int = 0) -> dict[float, str]:
    """The flat faces normal to ``axis``, by their centre's coordinate along it (a STEP path or a face listing)."""
    return {face.center_mm[axis]: face.ref for face in _listing(step_or_listing).faces
            if face.surface == "plane" and face.normal is not None and abs(abs(face.normal[axis]) - 1) < 1e-6}


def ends(step_or_listing, axis: int = 0) -> tuple[str, str]:
    """The flat faces at the low and the high end of ``axis``."""
    planes = planes_along(step_or_listing, axis)
    return planes[min(planes)], planes[max(planes)]


def side_faces(step: Path) -> list[str]:
    """The faces whose normal is square to x: the sides of a bar along x."""
    return [face.ref for face in _listing(step).faces if face.normal and abs(face.normal[0]) < 1e-6]


# --- Result GLBs ----------------------------------------------------------------------------------------

def read_glb(path: Path) -> tuple[dict, bytes]:
    """A GLB's JSON chunk and its binary chunk's payload."""
    raw = Path(path).read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length]), raw[20 + length + 8:]


def glb_extras(path: Path) -> dict:
    """The result mesh's extras: its study, fields, checks and parts."""
    return read_glb(path)[0]["meshes"][0]["extras"]


def glb_attribute_names(path: Path) -> list[str]:
    return list(read_glb(path)[0]["meshes"][0]["primitives"][0]["attributes"])


def glb_array(path: Path, name: str, width: int = 1):
    """One float32 vertex attribute as a (count, width) float64 array."""
    import numpy as np

    gltf, binary = read_glb(path)
    accessor = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"][name]]
    view = gltf["bufferViews"][accessor["bufferView"]]
    data = np.frombuffer(binary, np.float32, accessor["count"] * width, view["byteOffset"])
    return data.reshape(-1, width).astype(float)
