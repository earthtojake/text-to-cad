"""W16 explode: the old `explode` and `running_reveal` clips, as GLB animations.

The original's choreography (`lib/animgen.py`'s `ANIMATION_JS`, embedded in `w16.py`) moved
whole systems and per-bank sets of parts by straight, eased translations while the crank
kept turning. Here both clips are GLB animations (`cadgen.gltf`), each the original's
tables exactly: the crank cycle posed at every key (`kinematics.pose`, the engine turning
throughout), and every part or system the old clips moved translated after the pose, so a
part moved clear still carries its own motion:

- the floor lift: every system rises 1,150 mm at the start of either clip, so nothing
  that separates downward sinks below where the engine stood;
- `explode`: the ancillaries and the oil system down, the induction up, the cam drive
  forward, per bank the cam covers (out along the bank's centreline), the exhaust
  (outboard and down) and the turbos with their downpipes (outboard and down); then per
  bank the heads, cams, caps, bolts, followers and valve train out along the bank's
  centreline, each at its own distance (head 420, valves 750, followers 850, cams 950,
  caps 1000, bolts 1050); the pistons and rods out of their bores; the crank down with
  its bearings below it;
- `running_reveal`: everything outboard of the working parts clear, the heads lifted off,
  and nothing that moves displaced; the crankcase casting and its face skins, which the
  old clip faded to 8 % opacity, are hidden while it is clear (a GLB has no opacity
  channel: `.hide` scales a part to 0).
"""

from __future__ import annotations

import math

from cadgen.gltf import animation

from lib import kin, kinematics as K, spec as S
from lib.valvetrain import valve_tag

EXPLODE_SECONDS = 12.0              # the staged explode, 0..1, two crank cycles
REVEAL_SECONDS = 24.0               # off, held, back on: four crank cycles, so it loops exactly
REVEAL_OUT, REVEAL_HOLD = 8.0, 16.0
FLOOR_LIFT = 1150.0

_R = math.sqrt(0.5)
BANK_UP = {1: (0.0, _R, _R), 2: (0.0, -_R, _R)}          # each bank's centreline, out of the vee
EXHAUST_OUT = {1: (0.0, _R, -_R), 2: (0.0, -_R, -_R)}    # along each head's exhaust face, outboard and down
_DOWN, _UP, _FORWARD = (0.0, 0.0, -1.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)

_TURBO_ROTOR = ("turbine_wheel:", "compressor_wheel:", "compressor_shaft_nut:")
_KEY_STEP = 0.05     # s between the sampled keys of a clip's translations
_POSE_STEP = 0.02    # s between its poses of the crank cycle (2.4 deg of crank)


def _bank_of_label(label: str) -> int | None:
    """The bank a part of the heads, covers, turbos or exhaust belongs to, by its label: a
    tag `1` or `2`, or one starting `1_` or `2_` (`head:2`, `turbine_wheel:1_rear`,
    `head_bolt:2_7`, `cam_cover_bolt:2_inner_3`), names its bank; any other number is a
    cylinder's (1-8 bank 1, 9-16 bank 2). The original's rule took a bank from `B_...`
    only before front, rear, intake or exhaust, so it sent bank 2's head bolts, head face
    skins and cam-cover bolts out along bank 1's centreline: they go with their bank now."""
    tag = label.split(":", 1)[1] if ":" in label else ""
    head = tag.split("_")[0]
    if head in ("1", "2"):
        return int(head)
    if head.isdigit():
        return S.bank_of(int(head))
    return None


def _leaves(group) -> list:
    return [node for node in group.descendants if not node.children]


def explode_sets(systems) -> dict[str, list]:
    """{heads_B, covers_B, turbos_B, exhaust_B}: each system's parts by bank, the downpipes
    riding with their turbo (the original's `EXPL` table)."""
    found: dict[str, list] = {f"{name}_{bank}": [] for name in ("heads", "covers", "turbos", "exhaust")
                              for bank in (1, 2)}
    for name in ("heads", "covers", "turbos", "exhaust"):
        for part in _leaves(systems[name]):
            bank = _bank_of_label(part.label)
            if bank is None:
                raise LookupError(f"cannot place {part.label!r} ({name}) on a bank")
            target = "turbos" if name == "exhaust" and part.label.split(":")[0] in ("downpipe", "downpipe_vband") \
                else name
            found[f"{target}_{bank}"].append(part)
    return found


class _Moves:
    """The parts and systems the clips move, by the old clips' names for them, each a list of
    occurrence paths from the engine's root (a part cut away by the section is left out)."""

    def __init__(self, engine):
        self.root = engine.label
        self.systems = K.systems_of(engine)
        self.leaves = {part.label: part for part in _leaves(engine)}
        self.sets = explode_sets(self.systems)

    def path(self, node) -> str:
        steps = []
        while node.parent is not None:
            siblings = [child for child in node.parent.children if child.label == node.label]
            steps.append(node.label if len(siblings) == 1 else f"{node.label}.{siblings.index(node) + 1}")
            node = node.parent
        return "/".join([self.root, *reversed(steps)])

    def system(self, name: str) -> str:
        return f"{self.root}/{name}"

    def parts(self, *labels: str) -> list[str]:
        return [self.path(self.leaves[label]) for label in labels if label in self.leaves]

    def bank_set(self, name: str, bank: int) -> list[str]:
        """``name``'s parts of ``bank`` (`heads`, `covers`, `exhaust`, `turbos`), the turbos'
        rotors left out: they turn on their centre housings, which the set carries."""
        return [self.path(part) for part in self.sets[f"{name}_{bank}"]
                if not (name == "turbos" and part.label.startswith(_TURBO_ROTOR))]


# --- the choreography ---------------------------------------------------------------------

def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


def _stage(p: float, a: float, b: float) -> float:
    """Eased 0 before ``a``, 1 after ``b``."""
    return _smooth((p - a) / (b - a))


def _scaled(vector, amount: float) -> tuple[float, float, float]:
    return tuple(c * amount for c in vector)


def _floor(moves: _Moves, p: float) -> list[tuple[list[str], tuple]]:
    lift = FLOOR_LIFT * _stage(p, 0.0, 0.16)
    return [([moves.system(name)], (0.0, 0.0, lift)) for name in moves.systems]


def explode_moves(moves: _Moves, p: float) -> list[tuple[list[str], tuple]]:
    """The staged explode at progress ``p`` (0..1), the original's ``explode(m, p)``: each
    (references, translation) it makes."""
    found = _floor(moves, p)
    low = _stage(p, 0.02, 0.16)
    found += [([moves.system("ancillaries")], _scaled(_DOWN, 700.0 * low)),
              ([moves.system("oil_system")], _scaled(_DOWN, 550.0 * low))]
    outer = _stage(p, 0.14, 0.30)
    found += [([moves.system("induction")], _scaled(_UP, 500.0 * outer)),
              ([moves.system("camdrive")], _scaled(_FORWARD, 260.0 * outer))]
    for bank in (1, 2):
        up, sign = BANK_UP[bank], 1.0 if bank == 1 else -1.0
        found += [(moves.bank_set("covers", bank), _scaled(up, 1200.0 * outer)),
                  (moves.bank_set("exhaust", bank), _scaled(EXHAUST_OUT[bank], 280.0 * outer)),
                  (moves.bank_set("turbos", bank), (0.0, sign * 150.0 * outer, -400.0 * outer))]
        top = _stage(p, 0.33, 0.5) if bank == 1 else _stage(p, 0.48, 0.66)
        kinds = ("intake", "exhaust")
        tags = [valve_tag(g) for g in kin.all_valves() if S.bank_of(g.cyl) == bank]
        found += [
            (moves.parts(*(f"camshaft:{bank}_{kind}" for kind in kinds)), _scaled(up, 950.0 * top)),
            (moves.parts(*(f"cam_cap:{bank}_{kind}_{k}" for kind in kinds for k in range(1, 6))),
             _scaled(up, 1000.0 * top)),
            (moves.parts(*(f"cam_cap_bolt:{bank}_{kind}_{k}_{side}" for kind in kinds for k in range(1, 6)
                           for side in ("a", "b"))), _scaled(up, 1050.0 * top)),
            (moves.parts(*(f"{kind}:{tag}" for tag in tags for kind in ("follower", "roller", "roller_axle"))),
             _scaled(up, 850.0 * top)),
            (moves.parts(*(f"{kind}:{tag}" for tag in tags
                           for kind in ("valve", "valve_spring", "retainer", "spring_cup", "valve_guide",
                                        "lash_adjuster")),
                         *(f"collet:{tag}_{side}" for tag in tags for side in ("a", "b"))),
             _scaled(up, 750.0 * top)),
            (moves.bank_set("heads", bank), _scaled(up, 420.0 * top)),
        ]
    out = _stage(p, 0.68, 0.85)
    for c in S.CYLINDERS:
        n = c.number
        found.append((moves.parts(f"piston:{n}", f"piston_ring:{n}_1", f"piston_ring:{n}_2", f"piston_ring:{n}_3",
                                  f"wrist_pin:{n}", f"circlip:{n}_f", f"circlip:{n}_r", f"rod:{n}", f"rod_cap:{n}",
                                  f"rod_bolt:{n}_1", f"rod_bolt:{n}_2", f"rod_shell:{n}_upper",
                                  f"rod_shell:{n}_lower", f"rod_bush:{n}"),
                      (0.0, c.axis[1] * K.PISTON_OUT * out, c.axis[2] * K.PISTON_OUT * out)))
    bottom = _stage(p, 0.84, 1.0)
    found += [([moves.system("crank")], _scaled(_DOWN, 420.0 * bottom)),
              (moves.parts(*(f"main_shell:{k}_lower" for k in range(1, 6))), _scaled(_DOWN, 470.0 * bottom)),
              (moves.parts(*(f"main_shell:{k}_upper" for k in range(1, 6))), _scaled(_DOWN, 80.0 * bottom)),
              (moves.parts(*(f"main_cap:{k}" for k in range(2, 6))), _scaled(_DOWN, 520.0 * bottom)),
              (moves.parts(*(f"main_bolt:{k}_{side}" for k in range(2, 6) for side in ("l", "r"))),
               _scaled(_DOWN, 600.0 * bottom))]
    return found


def reveal_moves(moves: _Moves, p: float) -> list[tuple[list[str], tuple]]:
    """The running cutaway at progress ``p`` (0..1), the original's ``reveal(m, p)``: the
    floor lift, everything outboard of the working parts clear (0.02-0.30) and the heads
    lifted off (0.26-0.55); nothing that moves is displaced."""
    found = _floor(moves, p)
    clear = _stage(p, 0.02, 0.30)
    found += [([moves.system("ancillaries")], _scaled(_DOWN, 700.0 * clear)),
              ([moves.system("oil_system")], _scaled(_DOWN, 560.0 * clear)),
              ([moves.system("induction")], _scaled(_UP, 520.0 * clear)),
              ([moves.system("camdrive")], _scaled(_FORWARD, 300.0 * clear))]
    lift = _stage(p, 0.26, 0.55)
    for bank in (1, 2):
        sign = 1.0 if bank == 1 else -1.0
        found += [(moves.bank_set("covers", bank), _scaled(BANK_UP[bank], 1200.0 * clear)),
                  (moves.bank_set("exhaust", bank), _scaled(EXHAUST_OUT[bank], 300.0 * clear)),
                  (moves.bank_set("turbos", bank), (0.0, sign * 160.0 * clear, -420.0 * clear)),
                  (moves.bank_set("heads", bank), _scaled(BANK_UP[bank], 560.0 * lift))]
    return found


def reveal_progress(t: float) -> float:
    """Apart over 0..8 s, held to 16 s, back by 24 s: 0 at both ends, so the clip loops."""
    if t <= REVEAL_OUT:
        return _smooth(t / REVEAL_OUT)
    if t <= REVEAL_HOLD:
        return 1.0
    return _smooth((REVEAL_SECONDS - t) / (REVEAL_SECONDS - REVEAL_HOLD))


def _theta(t: float) -> float:
    """The crank never stops: 720 deg every CRANK_SECONDS, run on (no wrap, so every joint's
    value is continuous; a whole number of cycles per clip)."""
    return 720.0 * t / K.CRANK_SECONDS


def _times(duration: float, step: float) -> list[float]:
    count = round(duration / step)
    return [duration * i / count for i in range(count + 1)]


def _clip(engine, name: str, duration: float, turbo_tags, moves_at) -> object:
    """The GLB animation ``name``: the crank cycle posed every ``_POSE_STEP``, and each
    reference's translation, the sum of every move that names it, sampled every
    ``_KEY_STEP`` as LINEAR keys (a key whose neighbours hold its value dropped)."""
    show = animation(engine, name, duration=duration)
    show.pose(at={t: K.pose(_theta(t), turbo_tags) for t in _times(duration, _POSE_STEP)}, interpolation="LINEAR")
    times = _times(duration, _KEY_STEP)
    offsets: dict[str, list[tuple[float, float, float]]] = {}
    for at, t in enumerate(times):
        for refs, vector in moves_at(t):
            for ref in refs:
                row = offsets.setdefault(ref, [(0.0, 0.0, 0.0)] * len(times))
                row[at] = tuple(a + b for a, b in zip(row[at], vector))
    last = len(times) - 1
    for ref, row in offsets.items():
        if any(any(offset) for offset in row):
            keys = [(times[i], row[i]) for i in range(len(times))
                    if i in (0, last) or not row[i - 1] == row[i] == row[i + 1]]
            show.channel(ref, path="translation", keys=keys, interpolation="LINEAR")
    return show


def explode_animation(engine, turbo_tags) -> None:
    """`explode`: the staged explode over EXPLODE_SECONDS with the crank cycle running
    throughout (two cycles)."""
    moves = _Moves(engine)
    _clip(engine, "explode", EXPLODE_SECONDS, turbo_tags,
          lambda t: explode_moves(moves, min(1.0, max(0.0, t / EXPLODE_SECONDS))))


def running_reveal_animation(engine, turbo_tags) -> None:
    """`running_reveal`: the cutaway off, held and back on over REVEAL_SECONDS while the crank
    cycle runs (four cycles); the crankcase casting and its face skins hidden while the old
    clip had them faded past half (0.5 < its fade's stage, from p = 0.65 out to p = 0.65
    back)."""
    moves = _Moves(engine)
    show = _clip(engine, "running_reveal", REVEAL_SECONDS, turbo_tags,
                 lambda t: reveal_moves(moves, reveal_progress(t)))
    ghost = moves.parts(*sorted(label for label in moves.leaves
                                if moves.leaves[label].parent is moves.systems["block"]
                                and (label == "block" or label.startswith("block_face"))))
    out = next(t for t in _times(REVEAL_OUT, 0.01) if reveal_progress(t) >= 0.65)
    back = REVEAL_SECONDS - out * (REVEAL_SECONDS - REVEAL_HOLD) / REVEAL_OUT
    show.hide(ghost, at=out)
    show.scale(ghost, to=1, start=back, end=back, interpolation="STEP")
