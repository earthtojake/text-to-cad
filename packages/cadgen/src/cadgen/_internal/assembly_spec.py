"""Catalog path utilities and identity-transform constants.

A model entry is shape-only (no ``instances``/``children`` envelope), so there
is no assembly-recipe parser here — just the catalog-path helpers and the
identity-transform constants that ``step_topology_artifact``, ``step_targets``,
and ``generation`` import.
"""

from __future__ import annotations

from pathlib import Path

from cadgen.catalog import find_source_by_cad_ref


STEP_SUFFIXES = (".step", ".stp")

IDENTITY_TRANSFORM: tuple[float, ...] = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


def find_step_path(cad_ref: str) -> Path | None:
    source = find_source_by_cad_ref(cad_ref)
    if source is not None and source.step_path is not None:
        return source.step_path.resolve()
    return None


def resolve_cad_source_path(cad_ref: str) -> tuple[str, Path] | None:
    source = find_source_by_cad_ref(cad_ref)
    if source is not None and source.step_path is not None:
        return "step", source.step_path
    return None


def multiply_transforms(left: tuple[float, ...], right: tuple[float, ...]) -> tuple[float, ...]:
    product: list[float] = []
    for row in range(4):
        for column in range(4):
            total = 0.0
            for offset in range(4):
                total += left[(row * 4) + offset] * right[(offset * 4) + column]
            product.append(total)
    return tuple(product)
