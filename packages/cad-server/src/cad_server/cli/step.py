"""``cad step <operation>``: the STEP document type's commands (export, snapshot, inspect, dfm).

The operations and their options are ``cad_server.cli.document_types``', from the registry
(``cad.registry``); ``python -m cad_server.cli.step <operation> ...`` runs what the ``cad`` command does.
"""

from __future__ import annotations

from collections.abc import Sequence

DOCUMENT_TYPE = "step"
DEFAULT_PROG = "cad step"


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad_server.cli.document_types import type_main

    return type_main(DOCUMENT_TYPE, argv, prog)


if __name__ == "__main__":
    raise SystemExit(main())
