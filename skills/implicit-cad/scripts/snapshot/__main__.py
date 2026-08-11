"""The implicit skill's snapshot: an .implicit.js model, raymarched.

Everything about rendering — arguments, job schema, theme, display, the headless browser —
is `cadgen.snapshot_cli`, shared with every other skill that renders. What is local is this
file: which input kinds this skill accepts, and where its own bundled browser runtime lives.

This replaces a standalone 978-line Node CLI with its own Playwright driver, its own render
runtime and its own job schema. The browser side was already unified — cadjs's
headlessRenderEntry dispatches implicit jobs to implicitjs — so only the driver disagreed,
and disagreeing was the whole cost: a different job schema, a different theme option, no
--display at all.

An implicit model is ALWAYS raymarched. It is never rendered from a baked GLB export, so
there is no artifact to build and nothing for this skill to coordinate — which is why it
takes no generation lock while the STEP and DXF snapshots do.
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
KINDS = ("implicit",)


def main(argv: list[str] | None = None) -> int:
    return run_snapshot_cli(
        list(sys.argv[1:] if argv is None else argv),
        kinds=KINDS,
        runtime_dir=RUNTIME_DIR,
    )


if __name__ == "__main__":
    raise SystemExit(main())
