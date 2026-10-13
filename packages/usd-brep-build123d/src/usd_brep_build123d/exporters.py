"""USD in and out: usd-brep's exact interchange is OpenUSD's BrepArray (omniSolid schema)."""
from __future__ import annotations

import contextlib
import os

import usd_brep as ub

from .topology import Compound, Part, Shape, flatten


@contextlib.contextmanager
def quiet_native_stderr():
    """usd-brep's bundled OpenUSD prints a warning per library when it cannot find a ``pxr``
    Python package; errors still arrive as Python exceptions."""
    try:
        saved = os.dup(2)
    except OSError:
        yield
        return
    try:
        with open(os.devnull, "w") as null:
            os.dup2(null.fileno(), 2)
            yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)


def _breps(to_export) -> list:
    parts = []
    for obj in flatten([to_export]):
        if isinstance(obj, Compound) and obj.children:
            parts.extend(_breps(list(obj.children)))
        elif isinstance(obj, Shape) and obj._brep is not None:
            parts.append(obj._brep)
        else:
            raise TypeError(f"cannot export {type(obj).__name__} to USD")
    return parts


def export_usd(to_export, file_path) -> None:
    """Write exact B-rep (one BrepArray prim per part) to ``.usda``, ``.usdc`` or ``.usd``."""
    breps = [b.copy() for b in _breps(to_export)]  # a copy: export caches UV trims on its input
    with quiet_native_stderr():
        if len(breps) == 1:
            ub.usd.export_brep(breps[0], os.fspath(file_path))
        else:
            ub.usd.export_breps(breps, os.fspath(file_path))


def import_usd(file_path) -> Part:
    """Every BrepArray prim of a USD file: one part, or a Compound of several."""
    with quiet_native_stderr():
        breps = ub.usd.import_breps(os.fspath(file_path))
    parts = [Part(b) for b in breps]
    if not parts:
        raise ValueError(f"{file_path} has no BrepArray prim")
    return parts[0] if len(parts) == 1 else Compound(parts)
