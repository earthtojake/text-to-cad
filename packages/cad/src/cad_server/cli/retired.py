"""BRIDGE ONLY, deleted with the bridge in one change: what the skill text and documents of releases 0.10.0 to 0.11.10
still type, answered in a line rather than refused as an unknown command or option.

- ``cad doctor --prune`` (with its ``--all-versions`` and ``--yes``) and ``cad doctor --no-server``: taken, hidden,
  and changing nothing (``doctor_options``); with ``--prune`` the report ends with the line naming ``cad cache prune``
  (``PRUNE``).
- ``cad uninstall``, with any options: the line naming what removes cad now, and exit 2; nothing removed (``main``;
  its ``--help`` says the same line, exit 0).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

PRUNE = "`cad doctor --prune` is gone: `cad cache prune` removes what this release of cad cannot use"
UNINSTALL = ("`cad uninstall` is gone, and removed nothing: run `cad server stop`, then `uv tool uninstall cad`")


def doctor_options(parser: argparse.ArgumentParser) -> None:
    for flag in ("--prune", "--all-versions", "--no-server"):
        parser.add_argument(flag, action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-y", "--yes", action="store_true", help=argparse.SUPPRESS)


def main(argv: Sequence[str] | None = None, prog: str = "cad uninstall") -> int:
    if {"-h", "--help"} & set(sys.argv[1:] if argv is None else argv):  # asked what it is: said, as help is
        sys.stdout.write(f"usage: {prog}\n\n{UNINSTALL}\n")
        return 0
    sys.stderr.write(f"{prog}: {UNINSTALL}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
