"""Notched capstans, as a native overlay over the frozen assembled bodies.

The drum turns +-70 degrees to pay a cord out, and nothing about it says so: it
is a surface of revolution, and the six-turn rope wound on it is a helix, which
is ALSO very nearly invariant under rotation about its own axis. Every faster
part -- the shaft at 4x, the planets at 2x the carrier -- is enclosed inside a
static case. So the one mechanism the whole model exists to show reads as
stationary in every render and every animation.

`lib.capstan.make_capstan` now cuts index marks at one angular position. This
script places 48 occurrences of the notched drum exactly as `lib.assembly` does
and writes them as a standalone document, so `hand_mechanical_candidate_r13`
can bring them in through `native_integration.overlay(..., replace=True)` --
the same mechanism the four existing repair documents use. That path archives
by content hash and computes its own digest, so no frozen certificate is
re-stamped and no body count changes: 48 capstans in, the same 48 out.
"""
import json
from pathlib import Path

from cadgen import build123d as bd, step
from lib.capstan import make_capstan
from lib.layout import TENDONS

HERE = Path(__file__).resolve().parent
FRAMES = HERE.parents[0] / 'validation/mechanical_candidate_r13_frames.json'


def capstan_records():
    """The overlay's records, taken from the assembled body table rather than
    re-derived, so frame/system/kind cannot drift from what r13 already has."""
    rows = {row['name']: row for row in json.loads(FRAMES.read_text())}
    records = []
    for tendon in TENDONS:
        name = f'{tendon["actuator"]}_capstan'
        row = rows[name]
        records.append(dict(name=name, frame=row['frame'], system=row['system'], kind=row['kind']))
    assert len(records) == 48, len(records)
    return records


@step(out='../STEP/capstan_index_overlay.step')
def capstan_index_overlay():
    # One expensive prototype, 48 placed occurrences -- and the placement is
    # lib.assembly's, character for character, or the drums land somewhere the
    # rope does not reach. Capstans carry system 'forearm', so the per-finger
    # fan that assembly applies afterwards does not touch them.
    prototype = make_capstan()
    parts = []
    for tendon in TENDONS:
        x, y, _ = tendon['actuator_center']
        sign = tendon['sign']
        placement = bd.Pos(x, y, sign * 4.) * (bd.Rot(0, 0, 0) if sign == 1 else bd.Rot(0, 180, 0))
        part = placement * bd.Pos(0, 0, 29) * prototype
        part.label = f'{tendon["actuator"]}_capstan'
        part.color = prototype.color
        if getattr(prototype, 'cad_material', None):
            part.cad_material = dict(prototype.cad_material)
        parts.append(part)
    names = [p.label for p in parts]
    assert len(names) == len(set(names)) == 48
    result = bd.Compound(children=parts)
    result.label = 'capstan_index_overlay'
    return result


if __name__ == '__main__':
    capstan_index_overlay()
    print(json.dumps(capstan_records()[:2], indent=2))
