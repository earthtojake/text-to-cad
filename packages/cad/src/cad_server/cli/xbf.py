"""``cad xbf <operation> ...``: the earlier spelling of ``cad model <operation> ...``, from the days the ``.xbf`` a
model is saved as was a document type of its own (``cad.registry.ALIASES``). Unlisted (``cad_server.cli._UNLISTED``).

It runs ``cad model`` itself -- the same operations, options, output, ``--json`` and exit status, byte for byte --
after one line on stderr that it is deprecated, as a deprecated integration's command says it
(``cad_server.cli.integrations``); with ``--json``, the answer alone. The skills of releases up to 0.11.17 typed
`cad xbf export`, `cad xbf inspect` and `cad xbf interference`; the next release's skills type `cad model`, and the
30-day rule keeps this spelling answering 30 days past that release at least. Nothing else of the server's names
this module: removing the spelling is removing it and its ``cad.registry.ALIASES`` entry.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

DEFAULT_PROG = "cad xbf"
# What runs: the model's own command, under its own name.
MODEL_PROG = "cad model"


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad_server._internal.cli_errors import wants_json
    from cad_server.cli.document_types import type_main

    argv = list(sys.argv[1:] if argv is None else argv)
    if not wants_json(argv):
        sys.stderr.write(f"{prog}: deprecated and will be removed: use {MODEL_PROG}\n")
    return type_main("model", argv, MODEL_PROG)


if __name__ == "__main__":
    raise SystemExit(main())
