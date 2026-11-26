"""``cad snapshot``: a verb on a file, its type by its suffix (``cad_server.cli.verbs``); ``python -m
cad_server.cli.snapshot ...`` runs what the ``cad`` command does."""

from __future__ import annotations

from collections.abc import Sequence

VERB = "snapshot"
DEFAULT_PROG = "cad snapshot"


def build_parser(prog: str = DEFAULT_PROG):
    """The verb's parser, every type's options (``cad_server.cli.verbs.build_parser``)."""
    from cad_server.cli.verbs import build_parser as verb_parser

    return verb_parser(VERB, prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    import sys

    from cad_server.cli.verbs import dispatch as run

    return run(VERB, list(sys.argv[1:] if argv is None else argv), prog)


if __name__ == "__main__":
    raise SystemExit(main())
