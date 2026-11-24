"""``cad xbf <operation> FILE``: the older spelling of ``cad model <operation> FILE.xbf``, unlisted
(``cad_server.cli._UNLISTED``) and kept only for the skill text of releases up to 0.11.17.

It is ``cad model`` under this name: the same operations, options, output and exit status. Nothing else of the
server's names this module: removing the spelling is removing it and its ``_UNLISTED`` entry.
"""

from __future__ import annotations

from collections.abc import Sequence

DEFAULT_PROG = "cad xbf"


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad_server.cli.document_types import type_main

    return type_main("model", argv, prog)


if __name__ == "__main__":
    raise SystemExit(main())
