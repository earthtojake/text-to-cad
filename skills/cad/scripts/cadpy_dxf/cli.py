from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import sys

if __package__ in {None, ""}:
    scripts_dir = Path(__file__).resolve().parents[1]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

from cadpy_common.package_path import ensure_cadpy_package_path

ensure_cadpy_package_path()


def generate_dxf_targets(*args, **kwargs):
    from cadpy.generation import generate_dxf_targets as generate

    return generate(*args, **kwargs)


def run_tool_cli(*args, **kwargs):
    from cadpy.generation import run_tool_cli as run

    return run(*args, **kwargs)


def main(argv: Sequence[str] | None = None) -> int:
    return run_tool_cli(
        argv,
        prog="dxf",
        description="Generate explicit DXF targets from Python sources.",
        action=generate_dxf_targets,
        target_help="Explicit Python source file or SOURCE.py=OUTPUT.dxf pair defining gen_dxf() to generate.",
        output_help="Write the generated DXF file to this path. Valid only with one plain generated Python target.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
