"""``cad kicad_pcb <operation>``: the KiCad PCB document type's commands (export, snapshot, inspect, check).

The operations and their options are ``cad_server.cli.document_types``', from the registry
(``cad.registry``); ``python -m cad_server.cli.kicad_pcb <operation> ...`` runs what the ``cad`` command does.
"""

from __future__ import annotations

from collections.abc import Sequence

DOCUMENT_TYPE = "kicad_pcb"
DEFAULT_PROG = "cad kicad_pcb"


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad_server.cli.document_types import type_main

    return type_main(DOCUMENT_TYPE, argv, prog)


if __name__ == "__main__":
    raise SystemExit(main())
