"""``cad.mjcf._source``: the MJCF reader, which is the engine's (``cad.engine.mjcf_source``, where the
stills read it too), with its findings as the validation family's (``cad._internal.findings``).

Everything of the reader is re-exported under its name here, so the type's check, the server's robot
payload and the tests read ``cad.mjcf._source``; ``read_mjcf`` alone is wrapped, to answer a
``FindingsReport``. The standard library alone, as every module of the family is.
"""

from __future__ import annotations

from pathlib import Path

from cad._internal.findings import FindingsReport
from cad.engine.mjcf_source import (ARTICULATED, DRAWN_GROUPS, GEOM_TYPES, JOINT_TYPES, MESH_SUFFIXES, MJCF_SUFFIXES,
                                    PRIMITIVES, Articulation, LinkJoint, MjcfBody, MjcfError, MjcfGeom, MjcfJoint,
                                    MjcfMesh, MjcfModel, Visual, articulate, is_mjcf_file)
from cad.engine.mjcf_source import read_mjcf as _read_mjcf

__all__ = ["ARTICULATED", "Articulation", "DRAWN_GROUPS", "GEOM_TYPES", "JOINT_TYPES", "LinkJoint", "MESH_SUFFIXES",
           "MJCF_SUFFIXES", "PRIMITIVES", "MjcfBody", "MjcfError", "MjcfGeom", "MjcfJoint", "MjcfMesh", "MjcfModel",
           "Visual", "articulate", "is_mjcf_file", "read_mjcf"]


def read_mjcf(path: Path) -> tuple[MjcfModel | None, FindingsReport]:
    """``path`` read as an MJCF (``cad.engine.mjcf_source.read_mjcf``): the model and every finding as a
    ``FindingsReport``; the model None where an error stops the read."""
    model, found = _read_mjcf(path)
    report = FindingsReport()
    for finding in found.all_findings():
        report.add(finding.severity, finding.code, finding.message, path=finding.path, hint=finding.hint)  # type: ignore[arg-type]
    return model, report
