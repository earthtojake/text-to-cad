#!/usr/bin/env python3
"""Emit the act-2 SUBS ref lists for STEP/f14d.step.js from the built package.

The second act of the teardown separates parts INSIDE the wings and the aft
section, and those are addressed by leaf occurrence id -- the animation handle
takes a label or an occurrence list ("o1.3.1.21,o1.3.1.22,..."), and there is
no name pattern that says "every slat track on both wings". Hand-maintaining
~100 ids is not viable, so they are generated from assembly.json by name
pattern and pasted into the SUBS table.

REGENERATE AFTER ANY REBUILD THAT CHANGES LEAF COUNTS:

    python render/subrefs.py > tmp/subrefs.txt   # then update SUBS in STEP/f14d.step.js

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
STEP = PROJECT / "STEP" / "f14d.step"


def _assembly_json() -> Path:
    """The built package's descriptor.

    Render packages are content-keyed under the user cache now, so the path is
    asked for rather than guessed at (it used to be hardcoded at a
    ``__cadgen__/`` directory beside the model, which no longer exists).
    """
    from cadgen.catalog import render_package_dir

    return Path(render_package_dir(STEP)) / "assembly.json"

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
    assembly = _assembly_json()
    if not assembly.is_file():
        raise SystemExit(f"no built package for {STEP.name}; run `python src/f14d.py` first")
    occurrences = json.loads(assembly.read_text())["occurrences"]
    print("// ref values for the SUBS table in STEP/f14d.step.js")
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
        print(f'{name}: ref: "{",".join(ids)}"   // {len(ids)} occurrences')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
