"""Catalog path utilities and identity-transform constants.

Historically this module also parsed Python ``gen_step()`` assembly recipes
(``instances`` / ``children`` envelopes) into a typed ``AssemblySpec`` tree.
That contract is gone — ``gen_step()`` is shape-only — and the parser was
deleted with it. Only the catalog-path helpers and the identity-transform
constants survive, kept here so the established import paths in
``step_artifacts``, ``step_targets``, and ``generation`` continue to resolve.
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
    if source is not None and source.kind in {"part", "assembly"}:
        return source.step_path.resolve() if source.step_path is not None else None
    return None


def resolve_cad_source_path(cad_ref: str) -> tuple[str, Path] | None:
    source = find_source_by_cad_ref(cad_ref)
    if source is not None:
        if source.kind == "assembly":
            return "assembly", source.source_path
        if source.kind == "part":
            step_path = source.step_path
            return ("part", step_path) if step_path is not None else None
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
