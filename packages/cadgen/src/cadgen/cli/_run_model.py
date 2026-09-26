"""Internal runner for a directly-executed decorated model script.

NOT a user-facing CLI — the user interface is ``python <model>.py``, whose
``__main__`` calls the decorated model; that top-level call (cadgen.authoring)
dispatches here either in-process or through the warm daemon (tool ``"run"``).
The argv shape is ``[script, flags...]`` so the daemon can replay exactly what
the call saw.

This module exists so BOTH dispatch paths drive the one existing pipeline
(``cadgen.generation.generate_step_targets`` / ``generate_dxf_targets``) —
progress records, the no-op gate, incremental package build, ``.step``
assembly — with zero forked logic.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from cadgen.metadata import normalize_mesh_numeric


def _tolerance(field_name: str):
    """An argparse ``type=`` over the ONE mesh-numeric normaliser (cadgen.metadata),
    so a run-level flag is refused by the same rule, in the same words, as a
    decorator argument or a door's flag -- and refused while the flags are parsed,
    before any handoff to the daemon."""

    def parse(text: str) -> float:
        try:
            value = float(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{field_name} must be a number (got {text!r})") from None
        try:
            return normalize_mesh_numeric(value, field_name=field_name)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from None

    parse.__name__ = field_name
    return parse


def _build_parser(prog: str) -> argparse.ArgumentParser:
    """The per-run FLAGS of ``python <model>.py``.

    Flags only: the script is how the user got here, never something they pass,
    so it is not an argument of this parser (the internal argv carries it as its
    first item and :func:`run_model_argv` takes it off). ``--model`` is the
    pipeline's own routing flag -- which model of a file holding several this job
    builds -- and is hidden: a user selects a model by calling it in ``__main__``.
    """
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Build this CAD model: gate, build, and write every output its decorators "
            "declare. Reached by calling the decorated function in __main__."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("--model", metavar="FUNCTION", help=argparse.SUPPRESS)
    parser.add_argument("--force", action="store_true", help="Rebuild even when current.")
    parser.add_argument(
        "--mesh-tolerance",
        type=_tolerance("mesh_tolerance"),
        metavar="CHORD",
        help=(
            "For this run only, write every declared mesh at this chord tolerance, "
            "overriding the declarations' own. RELATIVE to each component's bounding "
            "diagonal, not millimetres (default 1.5e-3)."
        ),
    )
    parser.add_argument(
        "--mesh-angular-tolerance",
        type=_tolerance("mesh_angular_tolerance"),
        metavar="RADIANS",
        help=(
            "For this run only, write every declared mesh at this max normal spread "
            "across a triangle edge, in radians (default 0.35)."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress and timing on stderr, and a full traceback on failure.",
    )
    parser.add_argument("--json", action="store_true", help="One JSON result line on stdout.")
    return parser


def check_user_flags(flags: Sequence[str], *, prog: str, called: str) -> list[str]:
    """Parse what the USER typed after ``python <model>.py`` and return the flags
    to forward to the pipeline. Runs in the process the user started, before any
    handoff, so ``--help`` and a usage error behave identically warm and cold:
    they end the run here (exit 0 / exit 2) instead of becoming a daemon job that
    "succeeds" without building anything.

    ``called`` is the decorated function ``__main__`` called. ``--model`` is not a
    selector: a script builds what its ``__main__`` calls, so naming a different
    model is refused rather than built and then reported as a missing result.
    """
    parser = _build_parser(prog)
    args = parser.parse_args(list(flags))
    if args.model is not None and args.model != called:
        parser.error(
            f"--model is cadgen's internal routing flag, not a model selector: this run "
            f"builds {called}() because the script's __main__ block calls it. To build "
            f"{args.model}(), call {args.model}() in __main__ -- a file may hold several "
            "models, and each call builds one."
        )
    forwarded: list[str] = []
    skip = False
    for token in flags:
        if skip:
            skip = False
            continue
        if token == "--model":
            skip = True
            continue
        if token.startswith("--model="):
            continue
        forwarded.append(token)
    return forwarded


def run_model_argv(argv: Sequence[str], *, prog: str = "python <model>.py") -> int:
    # The other CLI entry point: `python model.py` reaches the pipeline here,
    # never through cadgen.cli.main, so it needs the same UTF-8 streams.
    from cadgen.cli import _harden_std_stream_errors

    _harden_std_stream_errors()
    parser = _build_parser(prog)
    items = list(argv)
    if not items or items[0].startswith("-"):
        parser.error("internal: the model script must be the first argument")
    args = parser.parse_args(items[1:])
    script = Path(items[0]).expanduser().resolve()
    if not script.is_file():
        parser.error(f"model script does not exist: {items[0]}")

    # Where this process's build-tree events go. A transient worker (CADGEN_EVENTS=1)
    # writes them as lines its parent reads back; a daemon worker already relays them
    # as frames; a root that reached here directly (`python -m cadgen.cli._run_model`)
    # renders the tree itself.
    from cadgen.cli_tree import build_tree
    from cadgen.daemon import executors

    if os.environ.get("CADGEN_EVENTS") == "1" and not executors.sink_installed():
        executors.install_line_sink()
    with build_tree(json_lines=bool(args.json)), executors.root_context():
        return _run(args, script, prog)


def _run(args: argparse.Namespace, script: Path, prog: str) -> int:

    from cadgen.catalog import StepImportOptions, source_from_path

    try:
        function = getattr(args, "model", None)
        source = source_from_path(script, function=function)
        # The pipeline's target: the script, or ``script::fn`` for one model of a
        # file holding several (cadgen.store.index.model_ref).
        target = f"{script}::{function}" if function else str(script)
        if source is None:
            raise ValueError(
                f"{script.name} declares no CAD model — decorate one function with "
                "@step, @dxf, or a mesh decorator (@stl/@glb/@threemf) from cadgen"
            )
        if source.dxf_path is not None and source.step_path is None:
            from cadgen.generation import generate_dxf_targets

            return generate_dxf_targets(
                [target],
                force=bool(args.force),
                verbose=bool(args.verbose),
                json_output=bool(args.json),
            )

        from cadgen.generation import generate_step_targets

        # The model's ``out=`` is the ONE spelling of where its document goes:
        # there is no per-run override (the record is keyed by the script, and
        # two documents for one model would be two truths).
        return generate_step_targets(
            [target],
            # Already normalised by the parser (`_tolerance`). A run-level flag
            # overrides every declaration's tolerance for THIS run only.
            step_options=StepImportOptions(
                mesh_tolerance=args.mesh_tolerance,
                mesh_angular_tolerance=args.mesh_angular_tolerance,
            ),
            force=bool(args.force),
            verbose=bool(args.verbose),
            json_output=bool(args.json),
        )
    except Exception as exc:  # noqa: BLE001 — the CLI boundary: report, do not traceback
        # The ONE failure envelope, shared with every generated door: under
        # --json a failure is `{"ok": false, "error": ...}` on stdout.
        from cadgen._internal.cli_from_function import report_failure

        return report_failure(exc, prog=prog, as_json=bool(args.json), verbose=bool(args.verbose))


def main(argv: Sequence[str] | None = None, *, prog: str = "python <model>.py") -> int:
    import sys

    return run_model_argv(list(argv) if argv is not None else sys.argv[1:], prog=prog)


if __name__ == "__main__":
    if os.environ.get("CADGEN_EVENTS") == "1":
        # The transient executor starts this module in a fresh interpreter.
        # Establish the witness before main can load any model. The event flag
        # selects that bootstrap mode; trust comes from this startup ordering.
        from cadgen import memoization

        memoization.install(trusted_worker=True)
    code = main()
    if os.environ.get("CADGEN_EVENTS") == "1":
        # A transient worker (cadgen.daemon.executors): its parent is waiting on this
        # exit, and tearing down an interpreter with OCP loaded costs ~0.3 s of
        # destructors that free nothing anyone will use. Flush and leave.
        import sys

        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except (OSError, ValueError):
                pass
        os._exit(int(code or 0))
    raise SystemExit(code)
