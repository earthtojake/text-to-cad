"""``cad.srdf``: the SRDF document type (``cad.registry``), a MoveIt2 semantic description.

No decorator, for the reason :mod:`cad.urdf` gives. ``cad inspect robot.srdf`` (``cad.inspect``) is its
check against its URDF, a parser generated from the check's signature (``_check``), and ``cad snapshot
robot.srdf`` draws it.

An SRDF is only meaningful against its URDF. ``urdf=`` (``--urdf``) names it; without it, the
paired URDF is found from the SRDF's robot name and directory, and a missing pairing is itself
a finding.
"""

from __future__ import annotations

__all__: list[str] = []

SUFFIX = ".srdf"


from cad._internal.document_type import bind as _bind  # noqa: E402

_bind(__name__)
