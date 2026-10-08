"""``cadgen urdf validate`` — an ADAPTER over :func:`cadgen.urdf.validate`.

The one validator that is not a generated mirror: ``--package NAME=PATH`` is
repeatable, and a repeatable key/value map is outside the annotation set a
parser can be derived from (:mod:`cadgen._internal.cli_from_function`). So the
parser is written here, its extra option is declared in the signature-sync
policy test, and the body stays a shell: parse, call the verb, print the
Result the same way every generated CLI does.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from cadgen._internal.cli_from_function import JSON_FLAG_DEST

DEFAULT_PROG = "cadgen urdf validate"
VERB = ("cadgen.urdf", "validate")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Check one URDF robot description for conformance.",
    )
    parser.add_argument("path", metavar="PATH", type=Path, help="The .urdf file to validate.")
    parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as blocking."
    )
    parser.add_argument(
        "--packages",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Resolve package://NAME/... mesh URIs against PATH. Repeatable.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Narrate the target on stderr."
    )
    parser.add_argument(
        "--json",
        dest=JSON_FLAG_DEST,
        action="store_true",
        help="Print the result as one JSON line on stdout instead of human lines.",
    )
    return parser


def package_map(entries: Sequence[str]) -> "dict[str, Path] | None":
    """``NAME=PATH`` pairs as the map the verb takes, or None for no roots."""
    if not entries:
        return None
    roots: dict[str, Path] = {}
    for entry in entries:
        name, separator, raw = str(entry).partition("=")
        if not separator or not name.strip() or not raw.strip():
            raise ValueError(f"--packages expects NAME=PATH, got {entry!r}")
        roots[name.strip()] = Path(raw.strip()).expanduser()
    return roots


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cadgen._internal.cli_from_function import call_verb

    args = build_parser(prog).parse_args(list(argv) if argv is not None else None)
    return call_verb(
        VERB,
        lambda validate: validate(
            args.path,
            strict=bool(args.strict),
            packages=package_map(args.packages),
            verbose=bool(args.verbose),
        ),
        prog=prog,
        as_json=bool(getattr(args, JSON_FLAG_DEST)),
        verbose=bool(args.verbose),
    )


if __name__ == "__main__":
    raise SystemExit(main())
