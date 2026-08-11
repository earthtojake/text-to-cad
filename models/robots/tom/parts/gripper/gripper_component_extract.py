from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_CACHE_HOME = REPO_ROOT / ".cache"
_CACHE_HOME.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(_CACHE_HOME))
os.environ.setdefault("EZDXF_CACHE_HOME", str(_CACHE_HOME / "ezdxf"))

import build123d
from build123d.topology import downcast
from build123d.topology.shape_core import shapetype

CAD_SCRIPT_PATH = Path(__file__).resolve().parents[5] / "skills" / "cad" / "scripts"
if str(CAD_SCRIPT_PATH) not in sys.path:
    sys.path.insert(0, str(CAD_SCRIPT_PATH))

from cadgen_common.package_path import ensure_cadgen_package_path

ensure_cadgen_package_path()

from cadgen.step_scene import located_shape, load_step_scene, occurrence_selector_id


SOURCE_STEP = Path(__file__).resolve().with_name("tom_gripper.step")


def _cast_shape(obj: object) -> build123d.Shape:
    occt_shape = downcast(obj)
    shape_name = build123d.Shape.shape_LUT[shapetype(occt_shape)]
    shape_type = getattr(build123d, shape_name)
    return shape_type.cast(occt_shape)


def _safe_label(text: str | None, fallback: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", text or "").strip("_")
    return value or fallback


def _leaf_color(scene: object, leaf: object) -> tuple[float, float, float, float] | None:
    leaf_color = getattr(leaf, "color", None)
    if leaf_color is not None:
        return leaf_color
    prototype_key = getattr(leaf, "prototype_key", None)
    prototype_color = scene.prototype_colors.get(prototype_key)
    if prototype_color is not None:
        return prototype_color
    return None


def _find_node(nodes: list[object], selector: str) -> object:
    stack = list(reversed(nodes))
    while stack:
        node = stack.pop()
        if occurrence_selector_id(node) == selector:
            return node
        stack.extend(reversed(node.children))
    raise RuntimeError(f"Selector {selector} not found in {SOURCE_STEP}")


def _leaf_nodes(node: object) -> list[object]:
    leaves: list[object] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if current.prototype_key is not None:
            leaves.append(current)
        stack.extend(reversed(current.children))
    return leaves


def _selector_matches(selector: str, parent_selector: str) -> bool:
    return selector == parent_selector or selector.startswith(f"{parent_selector}.")


def _compound_from_leaves(
    scene: object,
    leaves: list[object],
    *,
    label: str,
) -> build123d.Compound:
    children: list[build123d.Shape] = []
    for leaf in leaves:
        if leaf.prototype_key not in scene.prototype_shapes:
            raise RuntimeError(f"Leaf {occurrence_selector_id(leaf)} has no prototype shape")
        child = _cast_shape(located_shape(scene.prototype_shapes[leaf.prototype_key], leaf.location))
        child.label = _safe_label(
            leaf.source_name or leaf.name,
            occurrence_selector_id(leaf).replace(".", "_"),
        )
        color = _leaf_color(scene, leaf)
        if color is not None:
            child.color = build123d.Color(*color)
        children.append(child)

    if not children:
        raise RuntimeError(f"No gripper shapes extracted for {label}")
    return build123d.Compound(obj=children, children=children, label=label)


def extract_occurrences(selectors: tuple[str, ...], *, label: str) -> build123d.Compound:
    if not SOURCE_STEP.exists():
        raise FileNotFoundError(f"Missing gripper source STEP: {SOURCE_STEP}")

    scene = load_step_scene(SOURCE_STEP)
    leaves: list[object] = []
    for selector in selectors:
        leaves.extend(_leaf_nodes(_find_node(scene.roots, selector)))
    return _compound_from_leaves(scene, leaves, label=label)


def extract_all_except(excluded_selectors: tuple[str, ...], *, label: str) -> build123d.Compound:
    if not SOURCE_STEP.exists():
        raise FileNotFoundError(f"Missing gripper source STEP: {SOURCE_STEP}")

    scene = load_step_scene(SOURCE_STEP)
    leaves: list[object] = []
    for root in scene.roots:
        for leaf in _leaf_nodes(root):
            selector = occurrence_selector_id(leaf)
            if any(_selector_matches(selector, excluded) for excluded in excluded_selectors):
                continue
            leaves.append(leaf)
    return _compound_from_leaves(scene, leaves, label=label)
