"""``cad model <operation>``: the model document type's commands (export, snapshot, inspect, dfm, solve, plan), each of a
model's document id.

The operations and their options are ``cad_server.cli.document_types``', from the registry
(``cad.registry``); ``python -m cad_server.cli.model <operation> ...`` runs what the ``cad`` command does.
"""

from __future__ import annotations

from collections.abc import Sequence

DOCUMENT_TYPE = "model"
DEFAULT_PROG = "cad model"


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad_server.cli.document_types import type_main

    return type_main(DOCUMENT_TYPE, argv, prog)


if __name__ == "__main__":
    raise SystemExit(main())
