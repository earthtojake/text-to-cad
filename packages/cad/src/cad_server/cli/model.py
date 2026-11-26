"""``cad model <operation> ...``: the earlier spelling of ``cad xbf <operation> ...``, from the days the ``.xbf`` a
model is saved as had no document type of its own named for it (``cad.registry.ALIASES``). Unlisted
(``cad_server.cli._UNLISTED``).

It runs ``cad xbf`` itself -- the same operations, options, output, ``--json`` and exit status, byte for byte, under
``cad xbf``'s name -- after one line on stderr that it is deprecated, as a deprecated integration's command says it
(``cad_server.cli.integrations``); with ``--json``, the answer alone. The skills of releases up to 0.12 typed
`cad model export`, `cad model inspect` and `cad model interference`; the next release's skills type `cad xbf`, and the
30-day rule keeps this spelling answering 30 days past that release at least. Nothing else of the server's names
this module: removing the spelling is removing it and its ``cad.registry.ALIASES`` entry.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

DEFAULT_PROG = "cad model"
# What runs: the XBF type's own command, under its own name.
XBF_PROG = "cad xbf"


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad_server._internal.cli_errors import wants_json
    from cad_server.cli.document_types import type_main

    argv = list(sys.argv[1:] if argv is None else argv)
    if not wants_json(argv):
        sys.stderr.write(f"{prog}: deprecated and will be removed: use {XBF_PROG}\n")
    return type_main("xbf", argv, XBF_PROG)


if __name__ == "__main__":
    raise SystemExit(main())
