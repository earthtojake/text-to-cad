"""``cadgen snapshot`` — render any supported input, routed by suffix.

The polymorphic door: where a format door accepts only its own kinds, this one
accepts every kind at once and lets the suffix decide, which is also what a
mixed-format ``--job`` packet needs.

Its verb is the UNION shape — the STEP surface plus ``joint_values`` — so the
CLI is GENERATED like every other command in the schema
(:mod:`cadgen._internal.cli_from_function`), and nothing about a snapshot's
arguments is written down twice.

The verb lives here rather than on a ``cadgen.snapshot`` namespace because
there is no polymorphic FORMAT: `cadgen snapshot` is a routing convenience over
the seven real doors, and the public namespaces stay one-per-format.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cadgen._internal.cli_from_function import generated_main, generated_parser
from cadgen._internal.snapshot_door import polymorphic_snapshot_verb

DEFAULT_PROG = "cadgen snapshot"
VERB = ("cadgen.cli.snapshot", "snapshot")

#: Every kind at once. Which kinds each format door takes is
#: :data:`cadgen._internal.snapshot_door.DOOR_KINDS`, beside the verbs it binds.
snapshot = polymorphic_snapshot_verb()


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    return generated_parser(VERB, prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    return generated_main(VERB, argv, prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
