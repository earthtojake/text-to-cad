"""``cad kicad <operation>``: the kicad integration's commands, KiCad's own checks of its files: ``drc`` of a board
(``cad kicad drc board.kicad_pcb``) and ``erc`` of a schematic (``cad kicad erc sheet.kicad_sch``).

The operations and their options are ``cad_server.cli.integrations``', from the registry
(``cad.registry``); ``python -m cad_server.cli.kicad <operation> ...`` runs what the ``cad`` command does.
"""

from __future__ import annotations

from collections.abc import Sequence

INTEGRATION = "kicad"
DEFAULT_PROG = "cad kicad"


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad_server.cli.integrations import integration_main

    return integration_main(INTEGRATION, argv, prog)


if __name__ == "__main__":
    raise SystemExit(main())
