"""The SRDF skill's snapshot: a robot description, rendered from its link meshes.

Everything about rendering — arguments, job schema, theme, display, the headless browser —
is `cadgen.snapshot_cli`, shared with every other skill that renders. What is local is this
file: which input kinds this skill accepts, and where its own bundled browser runtime lives.

A robot has no artifact to build. The browser parser resolves each link mesh against the
description's own URL and the shared mesh path renders the result, so there is nothing to
generate and no generation lock to take — unlike STEP and DXF, which build a package first.

Robots are authored in METRES while the CAD profile assumes millimetres, so the resolver
defaults this input to the robot scene scale; a robot frames like a robot without the
caller having to know the unit convention. Pose it with the job field "jointValues" (joint
name to degrees, defaulting to the rest pose).
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
KINDS = ("srdf",)


def main(argv: list[str] | None = None) -> int:
    return run_snapshot_cli(
        list(sys.argv[1:] if argv is None else argv),
        kinds=KINDS,
        runtime_dir=RUNTIME_DIR,
    )


if __name__ == "__main__":
    raise SystemExit(main())
