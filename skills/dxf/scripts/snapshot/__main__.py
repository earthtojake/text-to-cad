"""The DXF skill's snapshot: a drawing, rendered as its 3D flat pattern.

Everything about rendering — arguments, job schema, theme, display, the headless browser —
is `cadgen.snapshot_cli`, shared with every other skill that renders. What is local is this
file: which input kinds this skill accepts, and where its own bundled browser runtime lives.

The drawing resolver makes the package current through `artifact_build(DRAWING_PACKAGE)` —
the same locked build `scripts/artifact` and the CAD Viewer run — then hands the baked
preview.glb to the shared mesh path. Sharing the CLI is what gives a drawing snapshot
--display, --job, and the full mode set, none of which the hand-written shell had.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for _runtime_path in (SCRIPTS_DIR, SCRIPTS_DIR / "packages", SCRIPTS_DIR / "packages" / "cadgen" / "src"):
    _text = str(_runtime_path)
    if _runtime_path.is_dir() and _text not in sys.path:
        sys.path.insert(0, _text)

from cadgen.snapshot_cli import run_snapshot_cli

RUNTIME_DIR = Path(__file__).resolve().parent / "runtime"
KINDS = ("dxf",)


def main(argv: list[str] | None = None) -> int:
    return run_snapshot_cli(
        list(sys.argv[1:] if argv is None else argv),
        kinds=KINDS,
        runtime_dir=RUNTIME_DIR,
    )


if __name__ == "__main__":
    raise SystemExit(main())
