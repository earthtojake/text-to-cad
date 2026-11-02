"""``cad requirement [INTEGRATION ...] [--json]``: the exact requirement that installs this device's cad, for a
program run with a Python of its own (a project's environment, a person's interpreter) -- ``cad==0.10.0``,
``cad[build123d]==0.10.0`` with the build123d integration, or the installation's source tree or wheel where
it was made from one (``base.Installation.requirement``) -- so that Python's builds meet the device's engine
at its release (the worker contract).

Each integration is one of cad's extras (``cad._internal.integrations``: ``build123d``, ``kicad``), given
as words or a comma-separated list. An integration whose packages come from an index or a folder of wheels
beside the default index names it on a line of its own after the requirement (``--index URL``,
``--find-links URL``), as a requirements file takes them; ``--json`` says it all as data: ``requirement``,
``indexes`` and ``findLinks``. Nothing is installed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

DEFAULT_PROG = "cad requirement"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad._internal.integrations import INTEGRATIONS

    parser = argparse.ArgumentParser(
        prog=prog, allow_abbrev=False,
        description="Print the exact requirement that installs this device's cad, for a program run with a Python "
                    f"of its own: cad's integrations named ({', '.join(INTEGRATIONS)}), pinned at this device's "
                    "release. Nothing is installed.")
    parser.add_argument("integrations", nargs="*", metavar="INTEGRATION",
                        help="one of cad's integrations (an extra), or a comma-separated list of them")
    parser.add_argument("--json", action="store_true", help="the requirement, its indexes and find-links, as JSON")
    return parser


def requirement(integrations: Sequence[str]) -> dict[str, object]:
    """The requirement of this installation's cad with ``integrations`` (each checked against the library's
    table), and the indexes and folders of wheels they need: ``{"requirement", "indexes", "findLinks"}``.
    ``ValueError`` naming the known ones for one that is none."""
    from cad._internal.integrations import INTEGRATIONS
    from cad_server._internal import base

    named = sorted({part.strip() for item in integrations for part in item.split(",") if part.strip()})
    unknown = [name for name in named if name not in INTEGRATIONS]
    if unknown:
        raise ValueError(f"{', '.join(unknown)}: no integration of cad's; it has {', '.join(INTEGRATIONS)}")
    words = base.Installation.here().requirement(tuple(named))
    return {"requirement": " ".join(words),
            "indexes": [index for name in named for index in INTEGRATIONS[name].indexes],
            "findLinks": [links for name in named for links in INTEGRATIONS[name].find_links]}


def main(argv: Sequence[str] | None = None, prog: str = DEFAULT_PROG) -> int:
    args = build_parser(prog).parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        found = requirement(args.integrations)
    except ValueError as error:
        print(f"{prog}: {error}", file=sys.stderr)
        return 2
    if args.json:
        sys.stdout.write(json.dumps(found) + "\n")
        return 0
    lines = [str(found["requirement"]), *(f"--index {index}" for index in found["indexes"]),  # type: ignore[union-attr]
             *(f"--find-links {links}" for links in found["findLinks"])]  # type: ignore[union-attr]
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
