"""W16 animation: the clips `w16.py` declares, sampled to keyframes when it builds.

Every motion is computed here from `lib/kin.py`, the functions that placed each
moving part at theta = 0 and that the collision gate (`lib.collide`) samples,
so the viewer plays the kinematics the gate checked. Nothing is restated: cam
axes, chain layouts, and the belt and pump ratios come from the modules that
built those parts.

  crank           one full 720 deg cycle: 16 pistons and rods in the published
                  firing order, 4 cams at half speed, 64 valves and roller
                  followers, both chain drives link by link, the oil-pump drive,
                  the turbo rotors and every accessory pulley.
  running_reveal  the engine runs while the bodywork comes off it, holds, and
                  goes back on; nothing that moves is displaced.
  explode         staged 0..1 by system with the engine still running: the low
                  systems, then the outer ones, then heads and valvetrain bank by
                  bank, then pistons out and the crank down.

Parts are targeted by label (`#piston:3`), whole systems by the group `w16.py`
links for them (`#oil_system`). Every update is a pure function of t.
"""

from __future__ import annotations

import functools
import math

import cadgen

from lib import ancillaries as A, kin, oil_system as O, palette as P, spec as S
from lib.cams import cam_axis
from lib.valvetrain import valve_tag

CRANK_SECONDS = 6.0          # one 720 deg cycle
EXPLODE_SECONDS = 12.0       # two cycles while it comes apart
REVEAL_SECONDS = 24.0        # four cycles: off, held, back on

_X = (1.0, 0.0, 0.0)

# ---------------------------------------------------------------------------
# What turns with what
# ---------------------------------------------------------------------------

# The crank and everything bolted to it.
_CRANK = ("#crankshaft", "#crank_damper", "#damper_washer", "#damper_bolt", "#crank_sprocket_hub",
          "#crank_sprocket:1", "#crank_sprocket:2", "#flywheel", "#crank_pulley_hub", "#crank_oil_pulley",
          *(f"#flywheel_bolt:{k}" for k in range(1, 9)), *(f"#crank_pulley_bolt:{k}" for k in range(1, 7)))

# The oil pump is belt-driven off the crank's oil pulley onto its own, about an
# axis along X through OIL_PUMP_CENTRE.
_OIL_PUMP = ("#oil_pump_pulley", "#oil_pump_shaft")
_OIL_PUMP_RATIO = O.CRANK_PULLEY_D / O.PUMP_PULLEY_D

# Both wheels and the shaft nut of each turbo spin about its axis, a whole
# number of turns a cycle so the loop is seamless.
_TURBO_TURNS_PER_CYCLE = 12
_TURBO_PARTS = ("turbine_wheel", "compressor_wheel", "compressor_shaft_nut")


def _belt_ratio(radius: float) -> float:
    """A pulley's speed over the crank's: the belt's rib face wraps every wheel
    at its radius + BELT_CLEAR (`lib/ancillaries.py`), the damper's included."""
    return (A.DAMPER_R + A.BELT_CLEAR) / (radius + A.BELT_CLEAR)


# The accessory drive: every pulley turns about its own X axis at its belt ratio,
# a fractional number of turns a cycle. The plain pulleys are bodies of
# revolution, so that never shows; the water pumps' six lightening holes skip
# where a loop starts over.
_PULLEYS = (
    ("#pulley:water_pump_1", A.WP_YZ[1], _belt_ratio(A.WP_R)),
    ("#pulley:water_pump_2", A.WP_YZ[2], _belt_ratio(A.WP_R)),
    ("#pulley:alternator", A.ALT_YZ, _belt_ratio(A.ALT_R)),
    ("#pulley:idler", A.IDLER_YZ, _belt_ratio(A.IDLER_R)),
    ("#pulley:tensioner", A.TENS_YZ, _belt_ratio(A.TENS_R)),
)


def _piston_parts(n: int) -> tuple[str, ...]:
    return (f"#piston:{n}", f"#piston_ring:{n}_1", f"#piston_ring:{n}_2", f"#piston_ring:{n}_3",
            f"#wrist_pin:{n}", f"#circlip:{n}_f", f"#circlip:{n}_r")


def _rod_parts(n: int) -> tuple[str, ...]:
    return (f"#rod:{n}", f"#rod_cap:{n}", f"#rod_bolt:{n}_1", f"#rod_bolt:{n}_2",
            f"#rod_shell:{n}_upper", f"#rod_shell:{n}_lower", f"#rod_bush:{n}")


# Each cylinder with its built (theta = 0) state, which every move is relative to.
_PISTONS = [(c, kin.piston(c.number, 0.0), _piston_parts(c.number), _rod_parts(c.number))
            for c in S.CYLINDERS]

# Each camshaft turns about its own axis (through this point) with its
# sprocket, bolt and washer.
_CAMS = [((0.0, *cam_axis(bank, kind)),
          (f"#camshaft:{bank}_{kind}", f"#cam_sprocket:{bank}_{kind}",
           f"#cam_sprocket_bolt:{bank}_{kind}", f"#cam_sprocket_washer:{bank}_{kind}"))
         for bank in (1, 2) for kind in ("intake", "exhaust")]


class _Valve:
    """One valve and its follower. The STEP is the true theta = 0 state (some
    valves are open there), so lift and follower angle move relative to it."""

    def __init__(self, g: kin.ValveGeom):
        tag = valve_tag(g)
        self.g = g
        self.bank = S.bank_of(g.cyl)
        self.lift0 = kin.valve_lift(g.cyl, g.kind, 0.0)
        self.eps0 = kin.follower_angle(g, self.lift0)
        self.pivot = (g.x, g.pivot[0], g.pivot[1])
        # what lifts with the valve, what rocks with the follower, and what
        # stays seated in the head until the explode lifts it out
        self.stem = (f"#valve:{tag}", f"#valve_spring:{tag}", f"#retainer:{tag}",
                     f"#collet:{tag}_a", f"#collet:{tag}_b")
        self.follower = (f"#follower:{tag}", f"#roller:{tag}", f"#roller_axle:{tag}")
        self.seat = (f"#spring_cup:{tag}", f"#valve_guide:{tag}", f"#lash_adjuster:{tag}")


_VALVES = [_Valve(g) for g in kin.all_valves()]


def _heading(p0, p1) -> float:
    return math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))


class _Chain:
    """One bank's cam-drive chain. Link k rides from roller k to roller k + 1,
    and the chain advances f links (`kin.chain_advance`), so at crank angle
    theta link k spans loop coordinates k + f .. k + 1 + f."""

    def __init__(self, bank: int):
        self.layout = kin.chain_layout(bank)
        self.x = S.CHAIN_X[bank]
        self.links = [f"#chain_link:{bank}_{k + 1}_{'inner' if k % 2 == 0 else 'outer'}"
                      for k in range(self.layout.links)]
        rollers = self.rollers(0.0)
        self.rest = [(rollers[k], _heading(rollers[k], rollers[k + 1])) for k in range(self.layout.links)]

    def rollers(self, f: float) -> list[tuple[float, float]]:
        """Every roller centre (y, z) with the chain advanced f links, the first
        again at the end."""
        return [kin.chain_point(self.layout, k + f)[0] for k in range(self.layout.links + 1)]


_CHAINS = [_Chain(bank) for bank in (1, 2)]


# ---------------------------------------------------------------------------
# What the built document holds
# ---------------------------------------------------------------------------

# The four systems the explode and the reveal move bank by bank, as the kinds
# of part each is built from (a label's kind is the text before its colon). The
# downpipes are built with the exhaust but ride with their turbo.
_BANKED_KINDS = {
    "heads": ("head", "head_face", "head_bolt", "core_plug", "spark_plug", "spark_plug_insulator",
              "spark_plug_terminal"),
    "covers": ("cam_cover", "cam_cover_bolt", "cam_cover_flange", "cam_cover_id_pad", "cam_seal_ring",
               "coil", "coil_bolt", "coil_harness", "harness_clip", "plug_well", "plug_well_seal",
               "breather_line", "breather_spigot", "oil_filler_cap", "pcv_clamp", "pcv_clip", "pcv_hose",
               "sensor"),
    "turbos": ("centre_housing", "centre_pad", "compressor_housing", "compressor_outlet_bead",
               "compressor_shaft_nut", "compressor_wheel", "turbine_housing", "turbine_parting",
               "turbine_flange_face", "turbine_heat_band", "turbine_heat_band2", "turbine_wheel",
               "turbine_inlet_stud_1", "turbine_inlet_stud_2", "turbine_inlet_stud_3", "turbine_inlet_stud_4",
               "turbine_inlet_nut_1", "turbine_inlet_nut_2", "turbine_inlet_nut_3", "turbine_inlet_nut_4",
               "vband_clamp_compressor", "vband_clamp_turbine", "vband_tbolt_compressor", "vband_tbolt_turbine",
               "vband_nut_compressor", "vband_nut_turbine", "oil_feed_banjo", "oil_feed_eye",
               "oil_drain_bolt_1", "oil_drain_bolt_2", "wastegate_can", "wastegate_bracket",
               "wastegate_bracket_bolt_1", "wastegate_bracket_bolt_2", "wastegate_rod", "wastegate_clevis",
               "wastegate_arm", "wastegate_shaft", "downpipe_flange", "downpipe", "downpipe_vband"),
    "exhaust": ("exhaust_primary", "exhaust_trumpet", "exhaust_flange", "exhaust_flange_stud",
                "exhaust_flange_nut", "exhaust_collector", "collector_flange", "turbine_inlet_gasket",
                "exhaust_heat_shield", "heat_shield_bolt", "heat_shield_spacer"),
}
_SYSTEM_OF_KIND = {kind: system for system, kinds in _BANKED_KINDS.items() for kind in kinds}

# The crankcase casting is the block system's only cast part, so the block's
# cast group (o1.1 is the block) is the casting alone. `#block` would name the
# whole system, whose group shares the casting's name.
_BLOCK_CASTING = f"#o1.1.{P.SYSTEM_MATERIALS['block'].index('cast') + 1}"


# The banked kinds built once per cylinder: their tags lead with the cylinder's
# number. Every other banked kind is built once per bank, and its tag leads with
# the bank's.
_PER_CYLINDER = frozenset({
    "spark_plug", "spark_plug_insulator", "spark_plug_terminal", "plug_well", "plug_well_seal", "coil",
    "coil_bolt", "exhaust_primary", "exhaust_trumpet", "exhaust_flange", "exhaust_flange_stud",
    "exhaust_flange_nut",
})


def _bank_of(label: str) -> int | None:
    """The bank a part sits on, read from its label's tag: `exhaust_flange_nut:11_3`
    is cylinder 11's, `head_bolt:2_5` and `turbine_wheel:1_rear` name their bank."""
    kind, _, tag = label.partition(":")
    lead = tag.split("_")[0]
    if not lead.isdigit():
        return None
    if kind in _PER_CYLINDER:
        return S.bank_of(int(lead))
    return int(lead) if lead in ("1", "2") else None


class _Built:
    """The names a build's document holds, sorted into what the clips move."""

    def __init__(self, names: tuple[str, ...]):
        self.names = frozenset(names)
        self.banked = {(system, bank): [] for system in _BANKED_KINDS for bank in (1, 2)}
        for name in names:
            system = _SYSTEM_OF_KIND.get(name.split(":", 1)[0])
            if system is None:
                continue
            bank = _bank_of(name)
            if bank is None:
                raise ValueError(f"cannot place {name} ({system}) on a bank")
            self.banked[system, bank].append(f"#{name}")
        # what fades to expose the running gear: the crankcase casting and its
        # cast face skins. The cross bolts and ID pads of the block stay solid.
        self.block_ghost = (_BLOCK_CASTING, *(f"#{name}" for name in names if name.startswith("block_face:")))

    def present(self, *labels: str) -> tuple[str, ...]:
        """The `#label` targets of these labels that were built (the museum
        section cuts some away)."""
        return tuple(f"#{label}" for label in labels if label in self.names)


@functools.cache
def _built(names: tuple[str, ...]) -> _Built:
    return _Built(names)


def _translate(m, targets, vector) -> None:
    if targets:
        m.get(*targets).translate(vector)


# ---------------------------------------------------------------------------
# The engine turning
# ---------------------------------------------------------------------------

def _turn(m, built: _Built, theta: float) -> None:
    m.get(*_CRANK).rotate(_X, theta)
    m.get(*_OIL_PUMP).rotate(_X, theta * _OIL_PUMP_RATIO, S.OIL_PUMP_CENTRE)
    for t in S.TURBOS:
        rotor = built.present(*(f"{part}:{t['bank']}_{t['pos']}" for part in _TURBO_PARTS))
        if rotor:
            _, y, z = t["centre"]
            m.get(*rotor).rotate(_X, theta * _TURBO_TURNS_PER_CYCLE * 360.0 / 720.0, (0.0, y, z))
    for target, (y, z), ratio in _PULLEYS:
        m.get(target).rotate(_X, theta * ratio, (0.0, y, z))
    # pistons slide along their bores; rods swing about the moving pin
    for c, rest, piston, rod in _PISTONS:
        now = kin.piston(c.number, theta)
        ds = now.s - rest.s
        m.get(*piston).translate((0.0, c.axis[1] * ds, c.axis[2] * ds))
        m.get(*rod).rotate(_X, now.rod_tilt - rest.rod_tilt, (c.x, rest.pin[0], rest.pin[1])).translate(
            (0.0, now.pin[0] - rest.pin[0], now.pin[1] - rest.pin[1]))
    for centre, parts in _CAMS:
        m.get(*parts).rotate(_X, kin.cam_angle(theta), centre)
    for v in _VALVES:
        lift = kin.valve_lift(v.g.cyl, v.g.kind, theta)
        d = lift - v.lift0
        if abs(d) > 1e-9:
            m.get(*v.stem).translate((0.0, -v.g.v[0] * d, -v.g.v[1] * d))
        eps = kin.follower_angle(v.g, lift) - v.eps0
        if abs(eps) > 1e-9:
            m.get(*v.follower).rotate(_X, eps, v.pivot)
    f = kin.chain_advance(theta)
    for chain in _CHAINS:
        now = chain.rollers(f)
        for k, (link, ((y0, z0), heading0)) in enumerate(zip(chain.links, chain.rest)):
            y, z = now[k]
            handle = m.get(link)
            # a link on a straight run does not turn: below 1e-9 deg the chord
            # headings differ only by rounding, which is no turn to key
            turn = math.remainder(_heading(now[k], now[k + 1]) - heading0, 360.0)
            if abs(turn) > 1e-9:
                handle.rotate(_X, turn, (chain.x, y0, z0))
            handle.translate((0.0, y - y0, z - z0))


def _theta(t: float) -> float:
    """The crank angle at t, run on through every cycle rather than wrapped
    back to 0: a keyframe track cannot jump, and the parts that do not repeat
    every 720 deg -- each chain link moves on 40 links a cycle, the oil pump and
    the accessory pulleys turn fractional numbers of times -- would snap back."""
    return 720.0 * t / CRANK_SECONDS


# ---------------------------------------------------------------------------
# Explode
# ---------------------------------------------------------------------------

def _clamp01(v: float) -> float:
    return min(1.0, max(0.0, v))


def _smooth(t: float) -> float:
    x = _clamp01(t)
    return x * x * (3.0 - 2.0 * x)


def _stage(p: float, a: float, b: float) -> float:
    return _smooth((p - a) / (b - a))


def _scaled(v, k: float) -> tuple[float, float, float]:
    return (v[0] * k, v[1] * k, v[2] * k)


def _outboard(bank: int) -> tuple[float, float, float]:
    """Out of the head's exhaust face: away from the engine centre in the deck plane."""
    return _scaled(S.bank_m(bank), -1.0)


# The display floor sits under the engine at rest, so anything that separates
# DOWNWARD would sink through it. The deepest fall is a main bolt: 420 mm with the
# crank group plus its own 600 mm, so 1 020 mm, and the rotating parts add their
# own swing on top. The whole assembly therefore rises 1 150 mm as the sequence
# runs: every part's net z displacement then stays >= 0 and nothing ever goes
# below where it started. Pure translation, so it simply adds to each part's own
# offset (and to the parts that do not otherwise move).
_FLOOR_LIFT = 1150.0


def _floor_lift(m, p: float) -> None:
    lift = _FLOOR_LIFT * _stage(p, 0.0, 0.16)
    if lift > 0.0:
        m.get("#w16").translate((0.0, 0.0, lift))


def _explode(m, built: _Built, p: float) -> None:
    _floor_lift(m, p)
    # Stage 1a (0.02-0.16): the low systems drop first -- ancillaries (belt drive,
    # starter, mounts, dipstick) and the oil system (pan, pump, filter, tray).
    s = _stage(p, 0.02, 0.16)
    if s > 0.0:
        m.get("#ancillaries").translate((0.0, 0.0, -700.0 * s))
        m.get("#oil_system").translate((0.0, 0.0, -550.0 * s))
    # Stage 1b (0.14-0.30): induction straight up; cam covers along each bank's
    # axis (beyond where the cams and caps will end); exhaust manifolds outboard
    # along the head face normal; turbos (with their downpipes) outboard and down;
    # the cam drive forward once the belt drive is out of its way.
    s = _stage(p, 0.14, 0.30)
    if s > 0.0:
        m.get("#induction").translate((0.0, 0.0, 500.0 * s))
        m.get("#camdrive").translate((260.0 * s, 0.0, 0.0))
        for bank in (1, 2):
            _translate(m, built.banked["covers", bank], _scaled(S.bank_up(bank), 1200.0 * s))
            _translate(m, built.banked["exhaust", bank], _scaled(_outboard(bank), 280.0 * s))
            _translate(m, built.banked["turbos", bank], (0.0, S.sign_of_bank(bank) * 150.0 * s, -400.0 * s))
    # Stage 2 (0.33-0.66): heads, cams, valvetrain -- bank 1 then bank 2, along
    # each bank's own axis. Order along the axis at p = 1 (pistons come later, to
    # 220): head 420..552, valves 750, followers 850, cams 950, caps 1000, bolts 1050.
    for bank in (1, 2):
        s = _stage(p, 0.33, 0.5) if bank == 1 else _stage(p, 0.48, 0.66)
        if s <= 0.0:
            continue
        up = S.bank_up(bank)
        for kind in ("intake", "exhaust"):
            key = f"{bank}_{kind}"
            m.get(f"#camshaft:{key}").translate(_scaled(up, 950.0 * s))
            # caps and their bolts cut away in the section are not there to move
            _translate(m, built.present(*(f"cam_cap:{key}_{k}" for k in range(1, 6))), _scaled(up, 1000.0 * s))
            _translate(m, built.present(*(f"cam_cap_bolt:{key}_{k}_{end}" for k in range(1, 6) for end in "ab")),
                       _scaled(up, 1050.0 * s))
        valves = [v for v in _VALVES if v.bank == bank]
        m.get(*(part for v in valves for part in v.follower)).translate(_scaled(up, 850.0 * s))
        m.get(*(part for v in valves for part in (*v.stem, *v.seat))).translate(_scaled(up, 750.0 * s))
        # the head casting, its face skins, head bolts, spark plugs and core plugs all ride together
        _translate(m, built.banked["heads", bank], _scaled(up, 420.0 * s))
    # Stage 3 (0.68-0.85): pistons and rods out of the bores along the bank axis
    s = _stage(p, 0.68, 0.85)
    if s > 0.0:
        for c, _rest, piston, rod in _PISTONS:
            m.get(*piston, *rod).translate((0.0, c.axis[1] * 220.0 * s, c.axis[2] * 220.0 * s))
    # Stage 4 (0.84-1.0): the crank down, main caps and shells below it
    s = _stage(p, 0.84, 1.0)
    if s > 0.0:
        m.get("#crank").translate((0.0, 0.0, -420.0 * s))
        for k in range(1, 6):
            m.get(f"#main_shell:{k}_lower").translate((0.0, 0.0, -470.0 * s))
            m.get(f"#main_shell:{k}_upper").translate((0.0, 0.0, -80.0 * s))
            if k == 1:
                continue            # the front main runs in the front wall: no cap
            m.get(f"#main_cap:{k}").translate((0.0, 0.0, -520.0 * s))
            m.get(f"#main_bolt:{k}_l", f"#main_bolt:{k}_r").translate((0.0, 0.0, -600.0 * s))


# ---------------------------------------------------------------------------
# Reveal: take the obstruction away, never the moving parts
# ---------------------------------------------------------------------------
#
# Unlike the explode, this displaces NOTHING that moves. The crank, rods, pistons,
# cams, followers and valves stay exactly where they run; what comes off is the
# bodywork in front of them -- the outer systems move clear, the heads lift, and
# the crankcase casting and its cast skins fade out. The cross bolts and ID pads
# of the block stay solid, so its bolt pattern still reads.

def _reveal(m, built: _Built, p: float) -> None:
    _floor_lift(m, p)
    # 1 (0.02-0.30): everything outboard of the working parts moves clear
    s = _stage(p, 0.02, 0.30)
    if s > 0.0:
        m.get("#ancillaries").translate((0.0, 0.0, -700.0 * s))
        m.get("#oil_system").translate((0.0, 0.0, -560.0 * s))    # pan, tray, pump, filter
        m.get("#induction").translate((0.0, 0.0, 520.0 * s))
        m.get("#camdrive").translate((300.0 * s, 0.0, 0.0))       # forward off the nose
        for bank in (1, 2):
            _translate(m, built.banked["covers", bank], _scaled(S.bank_up(bank), 1200.0 * s))
            _translate(m, built.banked["exhaust", bank], _scaled(_outboard(bank), 300.0 * s))
            _translate(m, built.banked["turbos", bank], (0.0, S.sign_of_bank(bank) * 160.0 * s, -420.0 * s))
    # 2 (0.26-0.55): the heads lift off along each bank's own axis. The cams,
    # followers and valves they enclosed DO NOT MOVE -- they keep running in air.
    s = _stage(p, 0.26, 0.55)
    if s > 0.0:
        for bank in (1, 2):
            _translate(m, built.banked["heads", bank], _scaled(S.bank_up(bank), 560.0 * s))
    # 3 (0.5-0.8): the crankcase itself fades, so the crank, rods and pistons are
    # seen working inside the space it occupied.
    s = _stage(p, 0.5, 0.8)
    if s > 0.0:
        m.get(*built.block_ghost).opacity(1.0 - 0.92 * s)


# Off over 0..8 s, held apart to 16 s, back together by the end. The clip is a
# whole number of crank cycles and the ramp returns to 0, so its two ends are
# the same state and it loops seamlessly with the engine still turning.
_REVEAL_OUT = 8.0
_REVEAL_HOLD = 16.0


def _reveal_progress(t: float) -> float:
    if t <= _REVEAL_OUT:
        return _smooth(t / _REVEAL_OUT)
    if t <= _REVEAL_HOLD:
        return 1.0
    return _smooth((REVEAL_SECONDS - t) / (REVEAL_SECONDS - _REVEAL_HOLD))


# ---------------------------------------------------------------------------
# Clips
# ---------------------------------------------------------------------------

def _crank(t: float, m) -> None:
    """One full four-stroke cycle: pistons, rods, cams, valves, followers,
    chains."""
    _turn(m, _built(tuple(m.labels())), _theta(t))


def _running_reveal(t: float, m) -> None:
    """The engine runs while the bodywork comes off it, so the crank, rods,
    pistons, cams and 64 valves are seen working IN PLACE."""
    built = _built(tuple(m.labels()))
    # Kinematics FIRST, then the reveal: handles premultiply, so a part that is
    # moved clear still carries its own motion, and a part that stays put
    # simply keeps running.
    _turn(m, built, _theta(t))
    _reveal(m, built, _reveal_progress(t))


def _explode_staged(t: float, m) -> None:
    """0..1 by system with the full crank loop running throughout -- crank,
    rods, pistons, cams, 64 valves, both chains, the oil-pump drive, the turbo
    rotors and every accessory pulley. 12 s is exactly 2 crank cycles."""
    built = _built(tuple(m.labels()))
    _turn(m, built, _theta(t))
    _explode(m, built, _clamp01(t / EXPLODE_SECONDS))


ANIMATION = {
    "crank": cadgen.clip(_crank, duration=CRANK_SECONDS, label="Crank (720 deg)"),
    "running_reveal": cadgen.clip(_running_reveal, duration=REVEAL_SECONDS, label="Running cutaway"),
    "explode": cadgen.clip(_explode_staged, duration=EXPLODE_SECONDS, loop=False, label="Explode (staged)"),
}
