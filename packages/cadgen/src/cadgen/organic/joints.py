"""Parameterized CAD ball-and-socket coupon, awaiting physical fit calibration."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .mesh import _positive


@dataclass(frozen=True)
class BallSocket:
    """CAD shapes in mm with the ball centre at the origin and stem along -Z."""

    male: Any
    socket: Any
    socket_blank: Any
    socket_void: Any
    parameters: dict[str, float]


def ball_socket(*, ball_radius_mm: float = 5.0, radial_clearance_mm: float = 0.2,
                neck_radius_mm: float = 2.3, stem_length_mm: float = 12.0,
                wall_mm: float = 2.4, mouth_z_mm: float = -2.5,
                slit_width_mm: float = 0.8) -> BallSocket:
    """Create male and slotted socket CAD solids; no universal fit guarantee.

    socket_void MUST also be subtracted from organic material surrounding a
    fused socket. Otherwise the imported solid fills its cavity and slots.
    ``mouth_z_mm`` defines the plane below the ball centre where the socket
    ends; a negative value retains more than a hemisphere.
    """
    from cadgen import build123d as bd

    r = _positive(ball_radius_mm, "ball_radius_mm")
    gap = _positive(radial_clearance_mm, "radial_clearance_mm")
    neck = _positive(neck_radius_mm, "neck_radius_mm")
    stem = _positive(stem_length_mm, "stem_length_mm")
    wall = _positive(wall_mm, "wall_mm")
    slit = _positive(slit_width_mm, "slit_width_mm")
    mouth = float(mouth_z_mm)
    inner = r + gap
    outer = inner + wall
    if not math.isfinite(mouth) or not -inner < mouth < 0:
        raise ValueError("mouth_z_mm must be negative and inside the inner sphere")
    opening = math.sqrt(inner ** 2 - mouth ** 2)
    if not neck < opening < r:
        raise ValueError("Mouth must admit the neck and retain the ball")
    if stem <= outer or slit >= wall:
        raise ValueError("Stem must extend beyond the socket; slit must be narrower than its wall")
    male = bd.Sphere(r) + bd.Pos(0, 0, -stem / 2) * bd.Cylinder(neck, stem)
    # The box cuts the outer sphere flush at the designed retaining lip.
    cap = bd.Pos(0, 0, (outer + mouth) / 2) * bd.Box(4 * outer, 4 * outer, outer - mouth)
    blank = bd.Sphere(outer) & cap
    cavity = bd.Sphere(inner)
    entry = bd.Pos(0, 0, (mouth - 2 * outer) / 2) * bd.Cylinder(opening, mouth + 2 * outer)
    void = cavity + entry
    slot_top = 0.35 * inner
    for angle in (0, 120, 240):
        slot = bd.Pos(0, outer / 2, (mouth + slot_top) / 2) * bd.Box(
            slit, 2 * outer, slot_top - mouth + 0.02)
        void = void + bd.Rot(0, 0, angle) * slot
    socket = blank - void
    for name, shape in (("ball_stem", male), ("socket", socket),
                        ("socket_blank", blank), ("socket_void", void)):
        shape.label = name
        if not shape.is_valid or shape.volume <= 0:
            raise ValueError(f"Invalid CAD joint solid: {name}")
    return BallSocket(male, socket, blank, void, {
        "ball_radius_mm": r, "radial_clearance_mm": gap, "neck_radius_mm": neck,
        "stem_length_mm": stem, "wall_mm": wall, "mouth_z_mm": mouth,
        "mouth_radius_mm": opening, "slit_width_mm": slit,
    })
