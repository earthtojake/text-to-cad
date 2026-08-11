from __future__ import annotations

from contextlib import contextmanager
import copy
import importlib.util
import math
import os
import sys
from pathlib import Path

import build123d


PARTS_DIR = Path(__file__).resolve().parent
V2_DIR = PARTS_DIR.parent
TOM_DIR = V2_DIR


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a floating point number, got {raw!r}") from exc


ALUMINUM_5052_SHEET_THICKNESS_MM = _env_float(
    "TOM_V2_ALUMINUM_5052_SHEET_THICKNESS_MM",
    25.4 * 0.063,
)
ALUMINUM_5052_YIELD_MPA = _env_float("TOM_V2_ALUMINUM_5052_YIELD_MPA", 193.0)
PRINTABLE_EFFECTIVE_STRENGTH_MPA = _env_float(
    "TOM_V2_PRINTABLE_EFFECTIVE_STRENGTH_MPA",
    21.449805890625,
)
PRINTABLE_BENDING_STRENGTH_MATCH_THICKNESS_MM = (
    ALUMINUM_5052_SHEET_THICKNESS_MM
    * math.sqrt(ALUMINUM_5052_YIELD_MPA / PRINTABLE_EFFECTIVE_STRENGTH_MPA)
)
PRINTABLE_EQUIVALENT_THICKNESS_MM = float(
    os.environ.get(
        "TOM_V2_PRINTABLE_THICKNESS_MM",
        f"{PRINTABLE_BENDING_STRENGTH_MATCH_THICKNESS_MM:.9f}",
    )
)
PRINTABLE_COLOR = build123d.Color(0.72, 0.74, 0.72, 1.0)


def _module_path(module_name: str) -> Path:
    # Entry generators are <name>.step.py; fall back to <name>.py for non-entry helper modules.
    step_entry = PARTS_DIR / f"{module_name}.step.py"
    return step_entry if step_entry.is_file() else PARTS_DIR / f"{module_name}.py"


@contextmanager
def loaded_v2_module(
    module_name: str,
    *,
    sheet_thickness_mm: float | None = None,
    case_span_centering_offset_mm: float | None = None,
    link_bracket_height_mm: float | None = None,
):
    old_env = os.environ.get("TOM_V2_SHEET_THICKNESS_MM")
    old_case_offset_env = os.environ.get("TOM_V2_CASE_SPAN_CENTERING_OFFSET_MM")
    old_link_height_env = os.environ.get("TOM_V2_LINK_BRACKET_OVERALL_HEIGHT_MM")
    if sheet_thickness_mm is None:
        os.environ.pop("TOM_V2_SHEET_THICKNESS_MM", None)
    else:
        os.environ["TOM_V2_SHEET_THICKNESS_MM"] = f"{sheet_thickness_mm:.9f}"
    if case_span_centering_offset_mm is None:
        os.environ.pop("TOM_V2_CASE_SPAN_CENTERING_OFFSET_MM", None)
    else:
        os.environ["TOM_V2_CASE_SPAN_CENTERING_OFFSET_MM"] = (
            f"{case_span_centering_offset_mm:.9f}"
        )
    if link_bracket_height_mm is None:
        os.environ.pop("TOM_V2_LINK_BRACKET_OVERALL_HEIGHT_MM", None)
    else:
        os.environ["TOM_V2_LINK_BRACKET_OVERALL_HEIGHT_MM"] = (
            f"{link_bracket_height_mm:.9f}"
        )

    stale_modules = {module_name}
    if module_name == "link_bracket":
        stale_modules.add("link_common")
    previous_modules = {name: sys.modules.get(name) for name in stale_modules}
    for name in stale_modules:
        sys.modules.pop(name, None)

    old_sys_path = list(sys.path)
    for path in (TOM_DIR, V2_DIR, PARTS_DIR):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    module_file = _module_path(module_name)
    synthetic_name = (
        f"_tom_v2_variant_{module_name}_"
        f"{abs(hash((module_file, sheet_thickness_mm, case_span_centering_offset_mm, link_bracket_height_mm)))}"
    )
    spec = importlib.util.spec_from_file_location(synthetic_name, module_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_file}")
    module = importlib.util.module_from_spec(spec)

    try:
        sys.modules[module_name] = module
        sys.modules[synthetic_name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path[:] = old_sys_path
        sys.modules.pop(synthetic_name, None)
        for name in stale_modules:
            sys.modules.pop(name, None)
            previous = previous_modules[name]
            if previous is not None:
                sys.modules[name] = previous
        if old_env is None:
            os.environ.pop("TOM_V2_SHEET_THICKNESS_MM", None)
        else:
            os.environ["TOM_V2_SHEET_THICKNESS_MM"] = old_env
        if old_case_offset_env is None:
            os.environ.pop("TOM_V2_CASE_SPAN_CENTERING_OFFSET_MM", None)
        else:
            os.environ["TOM_V2_CASE_SPAN_CENTERING_OFFSET_MM"] = old_case_offset_env
        if old_link_height_env is None:
            os.environ.pop("TOM_V2_LINK_BRACKET_OVERALL_HEIGHT_MM", None)
        else:
            os.environ["TOM_V2_LINK_BRACKET_OVERALL_HEIGHT_MM"] = old_link_height_env


def mirror_y(shape: build123d.Shape) -> build123d.Shape:
    mirrored = copy.deepcopy(shape)
    mirrored = mirrored.mirror(build123d.Plane.XZ)
    return mirrored


def finish_part(shape: build123d.Shape, label: str, *, printable: bool = False) -> build123d.Shape:
    shape.label = label
    if printable:
        shape.color = PRINTABLE_COLOR
    return shape
