"""``python -m cad._internal.cam VERB``: one :mod:`cad.cam` verb, run in this process, the CAD kernel's environment.

The server's ``cad cam`` commands run here (``cad_server._internal.kernel_verb``): their own process has no CAD
kernel, and a CAM verb reads the part's exact faces with OCCT. The verb's keyword arguments come in on stdin as one
JSON object; its result goes out on stdout as one JSON line, ``{"result": <its type's name in cad.results>,
"fields": <the dataclass as a dict>}``. What the verb says on stderr (``verbose``'s stages) is the command's stderr.
"""

from __future__ import annotations

import dataclasses
import json
import sys

VERBS = ("features", "plan")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in VERBS:
        print(f"usage: python -m cad._internal.cam {{{','.join(VERBS)}}} < KEYWORDS.json", file=sys.stderr)
        return 2
    from cad import cam

    keywords = json.loads(sys.stdin.read() or "{}")
    result = getattr(cam, args[0])(**keywords)
    sys.stdout.write(json.dumps({"result": type(result).__name__, "fields": dataclasses.asdict(result)},
                                default=str, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
