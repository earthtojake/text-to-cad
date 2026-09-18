"""Teaching error for the removed inspect CLI. No legacy checks execute."""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None, *, prog: str | None = None) -> int:
    sys.stderr.write(
        "cadgen step inspect has been removed. Use a Python script with "
        "'from cadgen import read_scene' and 'from cadgen.geometry import "
        "closest_points, overlap_volume, topology_errors'. "
        "Resolve geometry with scene.resolve(ref).shape(); choose checks and thresholds in Python.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
