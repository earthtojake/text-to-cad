"""The work coordinate system of a setup: how the part sits under the tool.

A setup's ``orientation`` names the part direction the tool comes from (``+Z``: from above, the part as modelled;
``-Z``: flipped; ``+X``: lying so its +X side faces up; ...) or a 3+2 tilt ``{"a_deg", "c_deg"}`` (the table turned
C about Z, then tilted A about X); or a planar face of the part (``"#o1.f4"``, on a mill or router): the tool looks
down the face's outward normal, the part turned by the smallest rotation that brings that normal to +Z (a half turn
about X for -Z), resolved against the part by :func:`with_face_orientations` into a :class:`FaceOrientation`. On a
mill4/mill5 a face its rotary axes reach is that rotary position, as a fixed orientation is; one they cannot reach is a
re-fixture by hand, in the smallest rotation. Its ``origin`` puts WCS zero on the stock's or the part's box (in the setup's WCS
axes): at its top, middle or bottom (``stock-top-*``, ``stock-center``, ``stock-bottom-*``, and the same for
``part``), at the centre of that level or its corner (min X, min Y); or at a part point ``{"xyz": [...]}``. Every
toolpath is planned and posted in WCS; the GLB maps it back.

:class:`WCS` is the transform: ``to_wcs(p) = R p - o`` and ``from_wcs(w) = R^T (w + o)``, both over (N, 3) numpy
arrays in mm, with ``R`` a proper rotation (part -> WCS axes) and ``o`` the origin in rotated coordinates. A lathe
setup is the identity: the spindle axis is the part's Z, and the IR stores (radius, 0, axial z).

Stdlib at import; numpy inside.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cadgen._internal.cam.job_errors import CamJobError

__all__ = ["FaceOrientation", "WCS", "build_wcs", "rotation_for", "rotation_to", "with_face_orientations"]

_AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
#: For each tool direction, the part direction that becomes WCS +X (the rest follows by the right-hand rule).
_WCS_X = {"+Z": (1.0, 0.0, 0.0), "-Z": (1.0, 0.0, 0.0), "+X": (0.0, 1.0, 0.0), "-X": (0.0, -1.0, 0.0),
          "+Y": (-1.0, 0.0, 0.0), "-Y": (1.0, 0.0, 0.0)}


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


@dataclass(frozen=True)
class FaceOrientation:
    """A setup turned onto a planar face: the job's selector, the face's outward normal (part coordinates, unit) and,
    on a mill4/mill5 whose rotary axes reach it, the rotary position (``(("a_deg", ..), ("c_deg", ..))``)."""

    ref: str
    normal: tuple[float, float, float]
    rotary: tuple[tuple[str, float], ...] | None = None

    def __str__(self) -> str:
        return self.ref


def rotation_to(direction) -> tuple[tuple[float, float, float], ...]:
    """The rows of ``R`` for a tool axis ``direction`` (part coordinates): the smallest rotation that takes the part's
    +Z to it (Rodrigues), a half turn about X for -Z."""
    x, y, z = (float(v) for v in direction)
    norm = math.sqrt(x * x + y * y + z * z)
    x, y, z = x / norm, y / norm, z / norm
    if z > 1.0 - 1e-12:
        return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    if z < -1.0 + 1e-12:
        return ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0))
    k = 1.0 / (1.0 + z)
    # The setup's axes in part coordinates are the columns of I + K + K^2/(1+c), K the cross matrix of Z x d.
    return ((1.0 - x * x * k, -x * y * k, -x), (-x * y * k, 1.0 - y * y * k, -y), (x, y, z))


def rotation_for(orientation: object) -> tuple[tuple[float, float, float], ...]:
    """The rows of ``R`` (WCS X, Y, Z axes written in part coordinates) for an orientation."""
    if isinstance(orientation, FaceOrientation):
        if orientation.rotary is not None:
            return rotation_for(dict(orientation.rotary))
        return rotation_to(orientation.normal)
    if isinstance(orientation, str) and "#" in orientation:
        raise CamJobError(f"orientation {orientation} names a face: read the part first (with_face_orientations)")
    if isinstance(orientation, dict):
        a = math.radians(orientation.get("a_deg", 0.0))
        b = math.radians(orientation.get("b_deg", 0.0))
        c = math.radians(orientation.get("c_deg", 0.0))
        # Table turned by C about Z, then tilted by A about X (or B about Y): R = Rx(a) Ry(b) Rz(c).
        rz = ((math.cos(c), -math.sin(c), 0.0), (math.sin(c), math.cos(c), 0.0), (0.0, 0.0, 1.0))
        ry = ((math.cos(b), 0.0, math.sin(b)), (0.0, 1.0, 0.0), (-math.sin(b), 0.0, math.cos(b)))
        rx = ((1.0, 0.0, 0.0), (0.0, math.cos(a), -math.sin(a)), (0.0, math.sin(a), math.cos(a)))

        def mul(m, n):
            return tuple(tuple(sum(m[i][k] * n[k][j] for k in range(3)) for j in range(3)) for i in range(3))

        return mul(rx, mul(ry, rz))
    sign = 1.0 if orientation[0] == "+" else -1.0
    z = tuple(sign * v for v in _AXES[orientation[1]])
    x = _WCS_X[orientation]
    y = _cross(z, x)
    return (x, y, z)


@dataclass(frozen=True)
class WCS:
    setup_id: str
    #: Rows: WCS X, Y, Z in part coordinates.
    rotation: tuple[tuple[float, float, float], ...]
    #: The WCS origin in rotated coordinates (``to_wcs(p) = R p - origin``).
    origin: tuple[float, float, float]
    #: Rotary positions to post for a 3+2 setup (``{"a": 30.0, "c": 90.0}``); empty for a fixed orientation.
    rotary_deg: tuple[tuple[str, float], ...] = ()
    orientation: object = "+Z"

    def _r(self):
        import numpy as np

        return np.asarray(self.rotation, dtype=float)

    def to_wcs(self, points):
        """Part points (N, 3) mm -> WCS."""
        import numpy as np

        return np.asarray(points, dtype=float) @ self._r().T - np.asarray(self.origin)

    def from_wcs(self, points):
        """WCS points (N, 3) mm -> part coordinates."""
        import numpy as np

        return (np.asarray(points, dtype=float) + np.asarray(self.origin)) @ self._r()

    def vectors_to_wcs(self, vectors):
        import numpy as np

        return np.asarray(vectors, dtype=float) @ self._r().T

    def vectors_from_wcs(self, vectors):
        import numpy as np

        return np.asarray(vectors, dtype=float) @ self._r()

    @property
    def tool_axis(self) -> tuple[float, float, float]:
        """The tool's +Z in part coordinates (the direction the tool comes from)."""
        return tuple(self.rotation[2])

    @property
    def origin_part_mm(self) -> list[float]:
        """Where WCS zero is, in part coordinates."""
        r = self.rotation
        o = self.origin
        return [round(sum(r[k][i] * o[k] for k in range(3)), 6) for i in range(3)]

    def matrix(self) -> list[list[float]]:
        """The 4x4 part -> WCS matrix, row-major, for the GLB's extras."""
        rows = [list(row) + [-self.origin[i]] for i, row in enumerate(self.rotation)]
        return [[round(v, 9) for v in row] for row in rows] + [[0.0, 0.0, 0.0, 1.0]]


def build_wcs(setup, *, stock_points, part_points, machine=None) -> WCS:
    """The WCS of ``setup`` (a :class:`~cadgen._internal.cam.job.Setup`), given the stock's and the part's points
    (any (N, 3) arrays in part mm whose bounds are theirs: box corners, mesh vertices). On a mill4/mill5 (``machine``
    given) a fixed orientation the rotary axes reach is that rotary position, and every rotary axis is posted
    (``multiaxis.orientation_rotary``)."""
    import numpy as np

    indexed = None
    if isinstance(setup.orientation, FaceOrientation):
        indexed = dict(setup.orientation.rotary) if setup.orientation.rotary is not None else None
    elif machine is not None:
        from cadgen._internal.cam.multiaxis import orientation_rotary

        indexed = orientation_rotary(setup.orientation, machine)
    rotation = rotation_for(indexed if indexed is not None else setup.orientation)
    r = np.asarray(rotation)
    origin = setup.origin
    if isinstance(origin, dict):
        o = r @ np.asarray(origin["xyz"], dtype=float)
    else:
        source = stock_points if origin.startswith("stock") else part_points
        rotated = np.asarray(source, dtype=float) @ r.T
        if not len(rotated):
            raise CamJobError(f"setup '{setup.id}': there is no stock to put the origin on")
        low, high = rotated.min(axis=0), rotated.max(axis=0)
        z = high[2] if "-top-" in origin else low[2] if "-bottom-" in origin else (low[2] + high[2]) / 2.0
        if origin.endswith("corner"):
            o = np.array([low[0], low[1], z])
        else:
            o = np.array([(low[0] + high[0]) / 2.0, (low[1] + high[1]) / 2.0, z])
    rotary = ()
    if indexed is not None:
        rotary = tuple((axis[0], float(value)) for axis, value in indexed.items())
    elif isinstance(setup.orientation, dict):
        rotary = tuple((axis[0], float(value)) for axis, value in setup.orientation.items() if value)
    return WCS(setup_id=setup.id, rotation=tuple(tuple(float(v) for v in row) for row in rotation),
               origin=tuple(float(v) for v in o), rotary_deg=rotary, orientation=setup.orientation)


def with_face_orientations(job, part):
    """``job`` with each setup turned onto a face (``"orientation": "#o1.f4"``) resolved against ``part`` into a
    :class:`FaceOrientation`; the job itself when none is (and a job already resolved). A face that is not on the part,
    or not planar, is a teaching error."""
    from dataclasses import replace

    if not any(isinstance(s.orientation, str) and "#" in s.orientation for s in job.setups):
        return job
    setups = []
    for setup in job.setups:
        if isinstance(setup.orientation, str) and "#" in setup.orientation:
            setup = replace(setup, orientation=_face_orientation(setup, part, job.machine))
        setups.append(setup)
    return replace(job, setups=tuple(setups))


def _face_orientation(setup, part, machine) -> FaceOrientation:
    where = f"setups[{setup.index}].orientation"
    ref = setup.orientation
    face = part.face(ref, where)
    if face.surface != "plane" or face.normal is None:
        raise CamJobError(f"{where}: {ref} is a {face.surface} face, which has no one normal to look down; a setup "
                          "turns onto a planar face (cadgen cam features lists them), or use +Z..-Y or a tilt")
    normal = tuple(float(v) for v in face.normal)
    length = math.sqrt(sum(v * v for v in normal))
    normal = tuple(v / length for v in normal)
    rotary = None
    from cadgen._internal.cam.multiaxis import _solutions, _within, rotary_axes

    axes = rotary_axes(machine)
    if axes:
        # As a fixed orientation on a mill4/mill5: the first rotary position its limits allow, else a re-fixture.
        for solution in _solutions(normal, axes, {axis: 0.0 for axis in axes}):
            rounded = {axis: round(value, 9) + 0.0 for axis, value in solution.items()}
            if all(_within(machine, axis, value) for axis, value in rounded.items()):
                rotary = tuple((f"{axis}_deg", value) for axis, value in rounded.items())
                break
    return FaceOrientation(ref=ref, normal=normal, rotary=rotary)
