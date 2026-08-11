"""Generate HIERARCHY.md from the actual gen_step() compound trees.

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Run:  PYTHONPATH=<repo>/packages/cadpy/src <venv-python> gen_hierarchy.py
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ENTRIES = ["falcon_heavy", "falcon_heavy_cutaway", "falcon_heavy_exploded"]

DISCLAIMER = (
    "> **Educational, non-functional public-source reconstruction. Not suitable "
    "for manufacture, propulsion, testing, or operational engineering.**"
)


def _load_shape(name: str):
    path = HERE / f"{name}.step.py"
    spec = importlib.util.spec_from_file_location(f"{name}.step", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    envelope = module.gen_step()
    return envelope["shape"] if isinstance(envelope, dict) else envelope


def _leaves(compound):
    children = list(getattr(compound, "children", []) or [])
    if not children:
        return [compound]
    result = []
    for child in children:
        result.extend(_leaves(child))
    return result


def _collapse(labels: list[str]) -> list[str]:
    """Collapse numbered repeats (bolt_01..bolt_24) into one line with a count."""
    import re

    counted = Counter(re.sub(r"_\d+(?=__|$)", "_NN", label) for label in labels)
    lines = []
    for pattern, count in counted.items():
        if count == 1:
            lines.append(f"- `{pattern.replace('_NN', '_01')}`")
        else:
            lines.append(f"- `{pattern}` × {count}")
    return lines


def main() -> int:
    out = [
        "# Falcon Heavy Reconstruction — Part Hierarchy",
        "",
        DISCLAIMER,
        "",
        "Generated from the live `gen_step()` compound trees by `gen_hierarchy.py`;",
        "numbered repeats are collapsed with `_NN` and a count. Labels carry their",
        "geometry status (`__photogrammetric`, `__schematic`, `__decorative`,",
        "`__placeholder`, `__nonfunctional`) — see PROVENANCE.md for the key.",
        "",
    ]
    for name in ENTRIES:
        shape = _load_shape(name)
        all_leaves = _leaves(shape)
        out.append(f"## `{name}.step.py` — {len(all_leaves)} parts")
        out.append("")
        for group in shape.children:
            leaves = _leaves(group)
            out.append(f"### {group.label} ({len(leaves)} parts)")
            out.append("")
            out.extend(_collapse([leaf.label or "(unlabeled)" for leaf in leaves]))
            out.append("")
    (HERE / "HIERARCHY.md").write_text("\n".join(out), encoding="utf-8")
    print(f"wrote HIERARCHY.md ({sum(1 for line in out if line.startswith('-'))} lines of parts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
