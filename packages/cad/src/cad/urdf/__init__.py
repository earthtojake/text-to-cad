"""``cad.urdf``: the URDF document type (``cad.registry``), a robot description.

It has no decorator: a robot description is an AUTHORED file, not a document a model makes. ``cad inspect
robot.urdf`` (``cad.inspect``) is its conformance check (``_check``), and ``cad snapshot robot.urdf``
(``cad.snapshot``) draws it.

``cad inspect``'s parser of a URDF is an ADAPTER's rather than one generated from the check's signature:
``--packages NAME=PATH`` is repeatable, and a repeatable key/value map is outside the annotation set a parser
can be derived from. It still answers with the same :class:`~cad.results.CheckResult` every check does.
"""

from __future__ import annotations

__all__: list[str] = []

SUFFIX = ".urdf"


from cad._internal.document_type import bind as _bind  # noqa: E402

_bind(__name__)
