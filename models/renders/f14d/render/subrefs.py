#!/usr/bin/env python3
"""Emit the SUBPARTS ref block for f14d.params.js from the built package.

The second act of the teardown separates parts INSIDE the wings and the aft
section, and those are addressed by leaf occurrence id -- there is no name
selector in a sidecar ref, only an occurrence list ("#o1.3.1.21,o1.3.1.22,...").
Hand-maintaining ~100 ids is not viable, so they are generated from
assembly.json by name pattern and pasted in.

REGENERATE AFTER ANY REBUILD THAT CHANGES LEAF COUNTS:

    python render/subrefs.py > /tmp/subparts.js   # then paste into f14d.params.js

Anything mirrored port/stbd is split into two groups, because one ref moves
every occurrence it matches by the SAME vector -- a single "wingtips" group
would push the port tip outboard and the starboard tip straight through the
wing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
ASSEMBLY = PROJECT / "__cadgen__" / "models" / "f14d.step.py" / "assembly.json"

# group name -> (parent occurrence prefix, name patterns, side filter or None)
GROUPS = [
    ("slats", "o1.3", (r"wing_slat", r"slat_track", r"slat_actuator_fairing"), None),
    ("flaps", "o1.3", (r"wing_flap", r"flap_track_fairing"), None),
    ("spoilers", "o1.3", (r"wing_spoiler",), None),
    ("tip_port", "o1.3", (r"wingtip_",), "port"),
    ("tip_stbd", "o1.3", (r"wingtip_",), "stbd"),
    ("sb_dorsal", "o1.7", (r"speedbrake_dorsal",), None),
    ("sb_ventral_port", "o1.7", (r"speedbrake_ventral_port",), None),
    ("sb_ventral_stbd", "o1.7", (r"speedbrake_ventral_stbd",), None),
    ("beavertail", "o1.7", (r"beavertail",), None),
    ("tailhook", "o1.7", (r"tailhook",), None),
]


def main() -> int:
    occurrences = json.loads(ASSEMBLY.read_text())["occurrences"]
    print("const SUBPARTS = {")
    for name, prefix, patterns, side in GROUPS:
        ids = [
            o["id"]
            for o in occurrences
            if o["id"].startswith(prefix + ".")
            and any(re.match(p, o["name"]) for p in patterns)
            and (side is None or f":{side}" in o["name"])
        ]
        if not ids:
            raise SystemExit(f"no occurrences matched {name}")
        print(f'  {name}: "#{",".join(ids)}",   // {len(ids)} occurrences')
    print("};")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
