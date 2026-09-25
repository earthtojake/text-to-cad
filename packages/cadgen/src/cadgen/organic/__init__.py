"""Mesh/CAD integration helpers for organic models and mechanical connections.

These helpers operate on explicit geometry in ordinary Python recipes. They
do not change the build123d return contract of cadgen's model decorators.
Heavy dependencies are imported only when an operation is called.
"""

from .mesh import (
    boolean, from_cad, inspect_mesh, load_mesh, prepare_mesh, split_plane,
    stl_roundtrip, write_mesh, write_scene,
)
from .motion import RotationGrid, carve_clearance, check_motion, clearance_envelope
from .joints import BallSocket, ball_socket
from .smoothing import smooth_clearance_envelope

__all__ = [
    "BallSocket", "RotationGrid", "ball_socket", "boolean", "carve_clearance",
    "check_motion", "clearance_envelope", "from_cad", "inspect_mesh",
    "load_mesh", "prepare_mesh", "smooth_clearance_envelope", "split_plane", "stl_roundtrip", "write_mesh", "write_scene",
]
