"""The CAD skill's snapshot: STEP models and their generators, plus direct meshes.

Everything about rendering — arguments, job schema, theme, display, the headless browser —
is `cadgen.snapshot_cli`, shared with every other skill that renders. What is local is this
file: which input kinds this skill accepts, and where its own bundled browser runtime lives.

`.implicit.js` and `.urdf`/`.srdf`/`.sdf` used to resolve here too. They belong to the
implicit-cad and urdf/srdf/sdf skills now; handing one to this CLI names the skill that
renders it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Warm-daemon shim: must run BEFORE the cadgen imports below (which load cadgen/OCP at
# module import time). The daemon sets CADGEN_DAEMON_CHILD so it never recurses; the
# stdlib-only client keeps the cold path overhead-free. STEP is the only format with an
# OCP build to warm, so this stays in the CAD skill rather than moving to the shared CLI.
if os.environ.get("CADGEN_WARM") == "1" and not os.environ.get("CADGEN_DAEMON_CHILD"):
    _daemon_scripts_dir = str(Path(__file__).resolve().parents[1])
    if _daemon_scripts_dir not in sys.path:
        sys.path.insert(0, _daemon_scripts_dir)
    from cadgen_daemon.client import run_via_daemon

    _warm_exit = run_via_daemon("snapshot", sys.argv[1:], os.getcwd())
    if _warm_exit is not None:
        raise SystemExit(_warm_exit)

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for _runtime_path in (SCRIPTS_DIR, SCRIPTS_DIR / "packages", SCRIPTS_DIR / "packages" / "cadgen" / "src"):
    _text = str(_runtime_path)
    if _runtime_path.is_dir() and _text not in sys.path:
        sys.path.insert(0, _text)

from cadgen.snapshot_cli import run_snapshot_cli

RUNTIME_DIR = Path(__file__).resolve().parent / "runtime"
KINDS = ("step", "stp", "3mf", "glb", "stl")


def main(argv: list[str] | None = None) -> int:
    return run_snapshot_cli(
        list(sys.argv[1:] if argv is None else argv),
        kinds=KINDS,
        runtime_dir=RUNTIME_DIR,
    )


if __name__ == "__main__":
    raise SystemExit(main())
