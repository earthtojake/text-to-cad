"""Internal runner for a directly-executed decorated model script.

NOT a user-facing CLI — the user interface is ``python <model>.py``, whose
``__main__`` calls the decorated model; that top-level call (cadgen.authoring)
dispatches here either in-process or through the warm daemon (tool ``"run"``).
The argv shape is ``[script, flags...]`` so the daemon can replay exactly what
the call saw.

This module exists so BOTH dispatch paths drive the one existing pipeline
(``cadgen.generation.generate_step_targets`` / ``generate_dxf_targets``) —
locks, progress records, the no-op gate, incremental package build, ``.step``
assembly — with zero forked logic.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from cadgen.metadata import normalize_mesh_numeric


def _build_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Build this CAD model (run by calling its @step/@dxf function).",
    )
    parser.add_argument("script", help="The decorated model script.")
    parser.add_argument("-o", "--output", help="Override the model's output path.")
    parser.add_argument("--force", action="store_true", help="Rebuild even when current.")
    parser.add_argument("--mesh-tolerance", type=float)
    parser.add_argument("--mesh-angular-tolerance", type=float)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", action="store_true", help="One JSON result line on stdout.")
    from cadgen._internal.cli_locking import add_lock_timeout_argument

    add_lock_timeout_argument(parser)
    return parser


def run_model_argv(argv: Sequence[str], *, prog: str = "python <model>.py") -> int:
    # The other CLI entry point: `python model.py` reaches the pipeline here,
    # never through cadgen.cli.main, so it needs the same UTF-8 streams.
    from cadgen.cli import _harden_std_stream_errors

    _harden_std_stream_errors()
    parser = _build_parser(prog)
    args = parser.parse_args(list(argv))
    script = Path(args.script).expanduser().resolve()
    if not script.is_file():
        parser.error(f"model script does not exist: {args.script}")

    from cadgen.catalog import StepImportOptions, source_from_path

    def _numeric(value: object, field_name: str) -> float | None:
        try:
            return normalize_mesh_numeric(value, field_name=field_name)
        except ValueError as exc:
            parser.error(str(exc))
        return None

    try:
        source = source_from_path(script)
        if source is None:
            raise ValueError(
                f"{script.name} declares no CAD model — decorate one function with "
                "@step or @dxf from cadgen"
            )
        if source.dxf_path is not None and source.step_path is None:
            from cadgen.generation import generate_dxf_targets

            return generate_dxf_targets(
                [str(script)],
                output=args.output,
                force=bool(args.force),
                verbose=bool(args.verbose),
            )

        from cadgen.generation import generate_step_targets

        # Native spelling on BOTH halves of the pair. ``as_posix()`` here used to
        # hand ``C:\...\model.py=C:/.../model.step`` to a parser that splits on
        # the first "=", so one invocation printed a path two different ways. An
        # explicit -o is passed through VERBATIM: it is the user's own text, and
        # round-tripping it through Path would rewrite what they typed.
        output = args.output if args.output else str(Path(source.step_path))
        return generate_step_targets(
            [f"{script}={output}"],
            step_options=StepImportOptions(
                mesh_tolerance=_numeric(args.mesh_tolerance, "mesh_tolerance"),
                mesh_angular_tolerance=_numeric(
                    args.mesh_angular_tolerance, "mesh_angular_tolerance"
                ),
            ),
            force=bool(args.force),
            verbose=bool(args.verbose),
            json_output=bool(args.json),
            lock_timeout_s=float(args.lock_timeout or 0.0),
        )
    except Exception as exc:  # noqa: BLE001 — the CLI boundary: report, do not traceback
        from cadgen._internal.cli_errors import report_cli_error

        return report_cli_error(exc, tool=prog, verbose=bool(args.verbose))


def main(argv: Sequence[str] | None = None, *, prog: str = "python <model>.py") -> int:
    import sys

    return run_model_argv(list(argv) if argv is not None else sys.argv[1:], prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
