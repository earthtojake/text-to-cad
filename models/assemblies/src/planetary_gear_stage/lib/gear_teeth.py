"""Gear-tooth helpers for the planetary gear stage (plain module: no @step here)."""

from __future__ import annotations

from math import cos, sin, tau


def polar_point(radius: float, angle: float) -> tuple[float, float]:
    return (radius * cos(angle), radius * sin(angle))


def trapezoid_tooth_profile(
    *,
    teeth: int,
    root_radius: float,
    tip_radius: float,
    phase: float,
    root_span_fraction: float = 0.72,
    tip_span_fraction: float = 0.38,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    pitch_angle = tau / teeth

    for tooth_index in range(teeth):
        center_angle = phase + tooth_index * pitch_angle
        points.extend(
            (
                polar_point(root_radius, center_angle - root_span_fraction * pitch_angle / 2.0),
                polar_point(tip_radius, center_angle - tip_span_fraction * pitch_angle / 2.0),
                polar_point(tip_radius, center_angle + tip_span_fraction * pitch_angle / 2.0),
                polar_point(root_radius, center_angle + root_span_fraction * pitch_angle / 2.0),
            )
        )

    return points
