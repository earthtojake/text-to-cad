"""Place a flat instance list as a labeled build123d ``Compound`` of linked children.

A tom assembly is authored as a flat list of ``{path, name, transform}`` instances in assembly
coordinates -- the placement data ``tom.urdf`` and the interference sweeps also read. This module
turns that list into geometry the way the model contract composes: every instance names a MODEL
(``link_plate.step`` -> the sibling model ``link_plate()``), the parent calls it and places the
result with a ``Location``. A call inside a build returns the child's geometry -- built if stale,
otherwise loaded from the store -- and the parent's result LINKS to the child's tree, so a part
placed eight times is stored once. Vendor files are models too (``sts3215.py`` wraps the purchased
servo with ``read_step``), which is what lets an assembly link to them instead of re-reading the
file per placement.

There is no cache here and no name-based module lookup: the parent imports its children explicitly
(that import is what the freshness gate tracks) and hands them in as ``models``.
"""

from __future__ import annotations

from typing import Sequence

# Attribute access through cadgen's lazy re-export: nothing here wakes the kernel at import.
import build123d as bd


def location_from_transform(transform: Sequence[float]) -> "bd.Location":
    """Build a build123d ``Location`` from a 16-element row-major transform."""
    from OCP.gp import gp_Trsf

    trsf = gp_Trsf()
    trsf.SetValues(*[float(value) for value in transform[:12]])
    return bd.Location(trsf)


