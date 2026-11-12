"""``cad omega <operation>``: the omega integration's commands on a GSL model (check).

The operations and their options are ``cad_server.cli.integrations``', from the registry
(``cad.registry``); ``python -m cad_server.cli.omega <operation> ...`` runs what the ``cad`` command does.
"""

from __future__ import annotations

from collections.abc import Sequence

INTEGRATION = "omega"
DEFAULT_PROG = "cad omega"


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad_server.cli.integrations import integration_main

    return integration_main(INTEGRATION, argv, prog)


if __name__ == "__main__":
    raise SystemExit(main())
