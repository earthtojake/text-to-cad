"""Shared geometry library for the Starship + Mechazilla launch complex.

This is a HELPER module (imported by the entry generators in this folder),
not a buildable entry itself - it defines no `gen_step()`. The entry files
`starship_mechazilla.step.py` (full assembly), `starship.step.py`,
`super_heavy.step.py`, `mechazilla_tower.step.py`, and `launch_mount.step.py`
each `import starship_mechazilla_parts` and compose one or more of the build
functions below, so every component shares one source of truth for geometry,
coordinates, palette, and the child-order ref contracts their `.params.js`
animation sidecars depend on. All components are authored at their native
full-stack world coordinates (booster aft at z~=19.6 m, ship at z~=91 m) so a
component's geometry is byte-identical whether built alone or in the assembly.

Evidence-grounded technical concept of the Starbase Pad A-style launch
complex with the full stack on the orbital launch mount:

- Launch tower ("Mechazilla"): ~146 m lattice tower (published ~146 m /
  480 ft), chopstick catch arms (~36 m class, incl. rear tails) on a
  rail-guided carriage, quick-disconnect (QD) arm with umbilical plate and
  hood, drawworks cables from the tower-top house, X-braced trusswork,
  service platforms with railings, cable trays, standpipes, and a lightning
  mast.
- Orbital launch mount (OLM): ~18 m six-leg steel table with 20 hold-down
  clamps around the booster aft flange, water-cooled flame deflector with
  supply piping, deluge ring main, and a booster quick-disconnect housing.
- Super Heavy booster: 9 m x ~71 m stainless body with ring weld bands,
  4 fixed grid fins, catch/lift pins, external raceway, vents, vented
  hot-stage ring with blast-shield dome, and 33 Raptor engines
  (3 + 10 gimbaled inner, 20 fixed outer).
- Starship upper stage: 9 m x ~52 m body, ogive nose, windward black
  thermal-tile shell, forward and aft flaps with hinge fairings, catch pins,
  vents, and 3 sea-level + 3 vacuum Raptors.

Engine reuse: bell geometry is composed from the sibling one-shot engine
reconstructions - the booster and RVac bells sample
`raptor2/raptor2_common.py` Rao contours (`bell_gas_contour`,
`vac_bell_gas_contour`) and the ship sea-level bells sample the analytic
slope-blend contour from `raptor3/raptor3.step.py` (`bell_radius`). Powerheads
are reduced-order placeholders (full ~300-part raptor3 detail x 39 engines
would be unusable); engines are mostly enclosed by the mount and skirts.

Where photos do not resolve detail, proportions are photogrammetric
estimates; nothing fictional is added. No logos or markings.

Conventions:
- Units: millimeters, full scale. Scene is ~157 m tall.
- Origin: vehicle/OLM centerline at ground level, +Z up.
- The tower stands at -X; thermal tiles face +X (leeward toward the tower is
  the QD/umbilical side); chopstick arms straddle the vehicle along Y.
- Repeated hardware (braces, beams, weld bands, clamps, engines, railing
  parts) is built once per size and instanced with `.moved()` for
  content-addressed dedup. No `.bounding_box()` calls on shared shapes.
"""

import importlib.util
from math import atan2, cos, degrees, hypot, radians, sin
from pathlib import Path

from build123d import (
    Axis,
    Box,
    BuildLine,
    BuildPart,
    BuildSketch,
    Circle,
    Color,
    Compound,
    Cone,
    Cylinder,
    FilletPolyline,
    Line,
    Location,
    Plane,
    Polyline,
    Pos,
    Rotation,
    Sphere,
    Spline,
    Torus,
    Vector,
    make_face,
    revolve,
    sweep,
)

# --------------------------------------------------------------------------
# Sibling one-shot engine concept reuse (path-loaded, see module docstring)
# --------------------------------------------------------------------------

_ONE_SHOTS = Path(__file__).resolve().parent.parent


def _load_module(rel_path, name):
    spec = importlib.util.spec_from_file_location(name, _ONE_SHOTS / rel_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_R2 = _load_module("raptor2/raptor2_common.py", "raptor2_common")
_R3 = _load_module("raptor3/raptor3.step.py", "raptor3.step")

# --------------------------------------------------------------------------
# Palette (technical concept: dark structural steel, stainless, black tiles)
# --------------------------------------------------------------------------

COL_TOWER = Color(0.17, 0.175, 0.185)     # painted structural steel
COL_TOWER_DARK = Color(0.12, 0.125, 0.13)  # braces / rails
COL_OLM = Color(0.15, 0.155, 0.16)        # launch table plate steel
COL_CLAMP = Color(0.24, 0.24, 0.25)       # hold-down clamp housings
COL_DEFLECTOR = Color(0.48, 0.49, 0.51)   # water-cooled deflector plate
COL_STAINLESS = Color(0.60, 0.61, 0.63)   # 304L rings
COL_BAND = Color(0.575, 0.585, 0.605)     # ring weld bands (subtle)
COL_TILE = Color(0.055, 0.055, 0.065)     # thermal tiles
COL_FIN = Color(0.42, 0.40, 0.38)         # grid fin steel (heat tinted)
COL_BELL = Color(0.12, 0.115, 0.11)       # engine bells
COL_ENGINE = Color(0.28, 0.28, 0.30)      # engine powerhead placeholders
COL_MECH = Color(0.30, 0.31, 0.33)        # machined mechanisms / pins
COL_PAD = Color(0.08, 0.08, 0.085)        # catch pads / rubber / cables
COL_PIPE = Color(0.33, 0.34, 0.36)        # service piping
COL_QD = Color(0.26, 0.27, 0.29)          # QD hardware
COL_GRATE = Color(0.22, 0.225, 0.235)     # platform grating
COL_INNER = Color(0.50, 0.51, 0.53)       # internal tank domes / structure

# --------------------------------------------------------------------------
# Master layout (mm) - published/estimated dimensions noted inline
# --------------------------------------------------------------------------

R_BODY = 4500.0                 # 9 m vehicle diameter (published)

OLM_TOP = 19000.0               # ~18-19 m launch table deck (estimate)
BOOSTER_BASE = 19600.0          # aft flange seat on hold-down clamps
BOOSTER_BARREL_TOP = 87600.0    # ~71 m booster incl. hot-stage ring
HSR_TOP = 90600.0               # hot-stage ring top (ship interface)
SHIP_BARREL_TOP = 119500.0
SHIP_TIP = 142700.0             # ~52 m ship -> stack top ~123 m over mount

TOWER_CX = -22000.0             # tower centerline offset from pad axis
TOWER_HALF = 6000.0             # half of the ~12 m square tower footprint
TOWER_TOP = 143000.0            # lattice top (tower ~146 m incl. house)
HOUSE_TOP = 146600.0
PANEL_COUNT = 20                # lattice bays
PANEL_H = TOWER_TOP / PANEL_COUNT

CARRIAGE_Z = 96000.0            # chopstick carriage centre (stacked config)
QD_Z = 91800.0                  # ship QD arm level
ARM_TOE_DEG = 2.6               # chopstick toe-in


# --------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------


def _part(shape, label, color):
    shape.label = label
    shape.color = color
    return shape


def _grp(name, children):
    return Compound(label=name, children=list(children))


def vcyl(r, z0, z1, x=0.0, y=0.0):
    return Cylinder(r, z1 - z0).moved(Pos(x, y, (z0 + z1) / 2.0))


def box_at(l, w, h, x, y, z, rz=0.0):
    loc = Location((x, y, z)) * Location((0, 0, 0), (0, 0, rz))
    return Box(l, w, h).moved(loc)


def revolve_poly(points, arc=360.0):
    """Revolve a closed (r, z) polyline profile around +Z."""
    with BuildPart() as bp:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(*points, close=True)
            make_face()
        revolve(axis=Axis.Z, revolution_arc=arc)
    return bp.part


def revolve_spline_shell(points, wall, arc=360.0):
    """Revolve a smooth spline wall profile (outer contour + radial wall)."""
    inner = [(r - wall, z) for r, z in reversed(points)]
    with BuildPart() as bp:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Spline(*points)
                Line(points[-1], inner[0])
                Spline(*inner)
                Line(inner[-1], points[0])
            make_face()
        revolve(axis=Axis.Z, revolution_arc=arc)
    return bp.part


def pipe(points, r, bend=400.0):
    """Sweep a circular section along a filleted polyline (retry ladder)."""
    pts = [Vector(*p) for p in points]
    tangent = (pts[1] - pts[0]).normalized()
    radii = [bend, bend * 0.6, bend * 0.35, bend * 0.15] if bend > 0 else [0.0]
    last = None
    for radius in radii:
        try:
            with BuildPart() as bp:
                with BuildLine():
                    if len(pts) == 2 or radius <= 0:
                        Polyline(*pts)
                    else:
                        FilletPolyline(*pts, radius=radius)
                with BuildSketch(Plane(origin=pts[0], z_dir=tangent)):
                    Circle(r)
                sweep()
            return bp.part
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise last


def ring(r_out, r_in, z0, z1):
    return revolve_poly([(r_in, z0), (r_out, z0), (r_out, z1), (r_in, z1)])


# --------------------------------------------------------------------------
# Engine LOD prototypes (contours reused from raptor2/raptor3 one-shots)
# --------------------------------------------------------------------------


def _bell_shell(contour, wall):
    pts = sorted(contour, key=lambda p: p[1])
    return revolve_spline_shell(pts, wall)


def _make_sl_engine_r2(detail):
    """Sea-level Raptor LOD from the raptor2_common Rao contour.

    detail 0: bell + powerhead drum. detail 1: + pumps, dome, gimbal block.
    """
    parts = [_part(_bell_shell(_R2.bell_gas_contour(samples=20), 45.0),
                   "bell", COL_BELL)]
    parts.append(_part(vcyl(430.0, _R2.Z_THROAT - 60.0, 2450.0), "powerhead", COL_ENGINE))
    if detail:
        parts.append(_part(Torus(_R2.THROAT_RADIUS + 60.0, 70.0).moved(Pos(0, 0, _R2.Z_THROAT)),
                           "throat_band", COL_ENGINE))
        parts.append(_part(vcyl(195.0, 1750.0, 2600.0, 480.0, 0.0), "turbopump:ox", COL_ENGINE))
        parts.append(_part(vcyl(195.0, 1750.0, 2600.0, -480.0, 0.0), "turbopump:fuel", COL_ENGINE))
        parts.append(_part(Sphere(400.0).moved(Pos(0, 0, 2550.0)), "lox_dome", COL_ENGINE))
        parts.append(_part(Box(520.0, 520.0, 420.0).moved(Pos(0, 0, 2950.0)),
                           "gimbal_block", COL_MECH))
    return _grp("raptor_sl", parts)


def _make_sl_engine_r3():
    """Ship sea-level Raptor LOD using the raptor3 analytic bell contour."""
    contour = [(_R3.bell_radius(z), z) for z in (
        0.0, 120.0, 280.0, 460.0, 660.0, 860.0, 1040.0, 1160.0, 1230.0, 1250.0)]
    parts = [_part(_bell_shell(contour, 45.0), "bell", COL_BELL)]
    parts.append(_part(vcyl(430.0, 1200.0, 2450.0), "powerhead", COL_ENGINE))
    parts.append(_part(vcyl(195.0, 1500.0, 2600.0, 480.0, 0.0), "turbopump:ox", COL_ENGINE))
    parts.append(_part(vcyl(195.0, 1500.0, 2600.0, -480.0, 0.0), "turbopump:fuel", COL_ENGINE))
    parts.append(_part(Sphere(400.0).moved(Pos(0, 0, 2550.0)), "lox_dome", COL_ENGINE))
    parts.append(_part(Box(520.0, 520.0, 420.0).moved(Pos(0, 0, 2950.0)),
                       "gimbal_block", COL_MECH))
    return _grp("raptor_sl_r3", parts)


def _make_rvac_engine():
    """Raptor vacuum LOD from raptor2_common's eps~80 contour (exit below 0)."""
    parts = [_part(_bell_shell(_R2.vac_bell_gas_contour(samples=24), 40.0),
                   "vac_bell", COL_BELL)]
    parts.append(_part(vcyl(430.0, _R2.Z_THROAT - 60.0, 2450.0), "powerhead", COL_ENGINE))
    parts.append(_part(Sphere(380.0).moved(Pos(0, 0, 2500.0)), "lox_dome", COL_ENGINE))
    parts.append(_part(Torus(700.0, 60.0).moved(Pos(0, 0, 600.0)),
                       "nozzle_stiffener", COL_BELL))
    return _grp("raptor_vacuum", parts)


ENGINE_SL_HI = _make_sl_engine_r2(detail=1)
ENGINE_SL_LO = _make_sl_engine_r2(detail=0)
ENGINE_SL_SHIP = _make_sl_engine_r3()
ENGINE_RVAC = _make_rvac_engine()


def _place(proto, label, x, y, z, rz=0.0):
    inst = proto.moved(Location((x, y, z)) * Location((0, 0, 0), (0, 0, rz)))
    inst.label = label
    return inst


# --------------------------------------------------------------------------
# Orbital launch mount
# --------------------------------------------------------------------------


def _olm_legs():
    parts = []
    leg = Box(2400.0, 2400.0, 15800.0)
    foot = Box(3400.0, 3400.0, 1000.0)
    for i in range(6):
        a = radians(30.0 + i * 60.0)
        x, y = 8800.0 * cos(a), 8800.0 * sin(a)
        parts.append(_part(leg.moved(Location((x, y, 8900.0), (0, 0, degrees(a)))),
                           f"olm_leg:{i + 1}", COL_OLM))
        parts.append(_part(foot.moved(Location((x, y, 500.0), (0, 0, degrees(a)))),
                           f"olm_leg_foot:{i + 1}", COL_OLM))
    return _grp("olm_legs", parts)


def _olm_table():
    parts = [
        _part(ring(7300.0, 4950.0, 16000.0, 19000.0), "olm_table_ring", COL_OLM),
        _part(ring(7400.0, 7150.0, 18300.0, 19250.0), "olm_deck_edge_guard", COL_OLM),
    ]
    clamp = Box(800.0, 620.0, 1150.0)
    for i in range(20):
        a = radians(i * 18.0)
        x, y = 5250.0 * cos(a), 5250.0 * sin(a)
        parts.append(_part(clamp.moved(Location((x, y, 19550.0), (0, 0, degrees(a)))),
                           f"hold_down_clamp:{i + 1}", COL_CLAMP))
    return _grp("olm_table_and_clamps", parts)


def _olm_deflector():
    return _grp("olm_flame_deflector", [
        _part(vcyl(1300.0, 0.0, 9800.0), "deflector_pedestal", COL_OLM),
        _part(revolve_poly([(120.0, 12500.0), (5200.0, 9200.0), (5200.0, 8500.0), (120.0, 11500.0)]),
              "flame_deflector", COL_DEFLECTOR),
    ])


def _olm_water_system():
    parts = []
    for i in range(6):
        a = radians(30.0 + i * 60.0)
        p0 = (4800.0 * cos(a), 4800.0 * sin(a), 8800.0)
        p1 = (8200.0 * cos(a), 8200.0 * sin(a), 1600.0)
        p2 = (9200.0 * cos(a), 9200.0 * sin(a), 900.0)
        parts.append(_part(pipe([p0, p1, p2], 340.0, bend=900.0),
                           f"deflector_water_main:{i + 1}", COL_PIPE))
    parts.append(_part(Torus(6200.0, 300.0).moved(Pos(0, 0, 15400.0)),
                       "deluge_ring_main", COL_PIPE))
    for sx, tag in ((1.0, "east"), (-1.0, "west")):
        parts.append(_part(pipe(
            [(sx * 6200.0, 0.0, 15400.0), (sx * 8800.0, 0.0, 9000.0), (sx * 8800.0, 0.0, 800.0)],
            280.0, bend=1200.0), f"deluge_riser:{tag}", COL_PIPE))
    return _grp("olm_water_deluge_system", parts)


def _olm_qd():
    return _grp("olm_booster_quick_disconnect", [
        _part(box_at(1600.0, 2400.0, 2600.0, -6600.0, 0.0, 20300.0),
              "booster_qd_housing", COL_QD),
        _part(box_at(900.0, 1400.0, 1500.0, -5350.0, 0.0, 20200.0),
              "booster_qd_plate", COL_MECH),
    ])


def build_olm():
    """Child order (launch_mount sidecar refs): 1 legs, 2 table+clamps,
    3 flame deflector, 4 water/deluge system, 5 booster QD."""
    return _grp("orbital_launch_mount", [
        _olm_legs(),
        _olm_table(),
        _olm_deflector(),
        _olm_water_system(),
        _olm_qd(),
    ])


# --------------------------------------------------------------------------
# Super Heavy booster
# --------------------------------------------------------------------------


def _make_grid_fin():
    """Fixed Super Heavy grid fin: horizontal waffle panel on a radial shaft.

    Local frame: +X radial outward, Y tangential, Z vertical; body skin at x=0.
    """
    parts = []
    span, depth, th = 4800.0, 2300.0, 500.0
    x0 = 350.0
    parts.append(_part(box_at(depth, 160.0, th, x0 + depth / 2, -span / 2, 0.0),
                       "fin_rim:left", COL_FIN))
    parts.append(_part(box_at(depth, 160.0, th, x0 + depth / 2, span / 2, 0.0),
                       "fin_rim:right", COL_FIN))
    parts.append(_part(box_at(160.0, span, th, x0 + depth - 80.0, 0.0, 0.0),
                       "fin_rim:outer", COL_FIN))
    parts.append(_part(box_at(160.0, span, th, x0 + 80.0, 0.0, 0.0),
                       "fin_rim:inner", COL_FIN))
    for i in range(7):
        y = -span / 2 + (i + 1) * span / 8
        parts.append(_part(box_at(depth - 200.0, 70.0, th - 60.0, x0 + depth / 2, y, 0.0),
                           f"fin_lattice_t:{i + 1}", COL_FIN))
    for i in range(3):
        x = x0 + (i + 1) * depth / 4
        parts.append(_part(box_at(70.0, span - 200.0, th - 60.0, x, 0.0, 0.0),
                           f"fin_lattice_r:{i + 1}", COL_FIN))
    parts.append(_part(Cylinder(270.0, 1100.0, rotation=(0, 90, 0)).moved(Pos(-150.0, 0, 0)),
                       "fin_shaft", COL_MECH))
    parts.append(_part(box_at(950.0, 760.0, 640.0, -420.0, 0.0, 0.0),
                       "fin_actuator_housing", COL_MECH))
    return _grp("grid_fin", parts)


GRID_FIN = _make_grid_fin()
WELD_BAND = Cylinder(R_BODY + 12.0, 90.0)


def _weld_bands(name, z0, z1, step=1750.0):
    out = []
    z = z0
    i = 1
    while z < z1:
        out.append(_part(WELD_BAND.moved(Pos(0, 0, z)), f"{name}:{i}", COL_BAND))
        z += step
        i += 1
    return out


def _dome(r, rise, z_base, samples=7):
    """Solid ellipsoidal dome cap bulging upward from z_base."""
    pts = [(r * cos(radians(a)), z_base + rise * sin(radians(a)))
           for a in [i * 90.0 / (samples - 1) for i in range(samples)]]
    profile = pts + [(0.0, z_base + rise), (0.0, z_base)]
    return revolve_poly([(max(px, 0.0), pz) for px, pz in profile])


def _booster_shell():
    """Sub-group 1: everything rigidly part of the booster skin."""
    parts = []
    parts.append(_part(ring(R_BODY + 90.0, R_BODY - 200.0, BOOSTER_BASE, 20100.0),
                       "aft_hold_down_flange", COL_STAINLESS))
    parts.append(_part(vcyl(R_BODY, 20100.0, BOOSTER_BARREL_TOP), "booster_tank_barrel", COL_STAINLESS))
    parts += _weld_bands("booster_ring_weld", 21850.0, BOOSTER_BARREL_TOP - 200.0)
    parts.append(_part(vcyl(R_BODY - 80.0, 21900.0, 22150.0), "engine_bay_shield", COL_OLM))

    for sy, tag in ((1.0, "port"), (-1.0, "starboard")):
        parts.append(_part(
            Cylinder(360.0, 900.0, rotation=(90 if sy > 0 else -90, 0, 0)).moved(
                Pos(0, sy * (R_BODY + 350.0), 84200.0)),
            f"catch_pin:{tag}", COL_MECH))
        parts.append(_part(box_at(900.0, 700.0, 500.0, 0.0, sy * (R_BODY + 180.0), 84800.0, rz=90.0),
                           f"catch_pin_gusset:{tag}", COL_MECH))

    parts.append(_part(pipe([(-R_BODY - 260.0, 0.0, 20600.0), (-R_BODY - 260.0, 0.0, 85800.0)],
                            300.0, bend=0), "booster_raceway", COL_MECH))
    for i, z in enumerate((23000.0, 39000.0, 55000.0, 71000.0, 84600.0)):
        parts.append(_part(box_at(500.0, 900.0, 700.0, -R_BODY - 120.0, 0.0, z),
                           f"raceway_standoff:{i + 1}", COL_MECH))
    for tag, az, z in (("lox_vent", 150.0, 85800.0), ("ch4_vent", 210.0, 84000.0),
                       ("aft_vent_1", 60.0, 22500.0), ("aft_vent_2", 300.0, 22500.0)):
        a = radians(az)
        x, y = (R_BODY + 140.0) * cos(a), (R_BODY + 140.0) * sin(a)
        parts.append(_part(
            Cylinder(190.0, 800.0, rotation=(0, 90, degrees(a))).moved(Pos(x, y, z)),
            f"booster_{tag}", COL_MECH))
    for i, (az, z) in enumerate(((200.0, 22800.0), (160.0, 54000.0), (185.0, 84200.0))):
        a = radians(az)
        x, y = (R_BODY + 30.0) * cos(a), (R_BODY + 30.0) * sin(a)
        parts.append(_part(
            Cylinder(520.0, 90.0, rotation=(0, 90, degrees(a))).moved(Pos(x, y, z)),
            f"booster_access_hatch:{i + 1}", COL_BAND))
    return _grp("booster_shell", parts)


def _booster_interior():
    """Sub-group 2: internal tank structure (revealed by the exploded view).

    Super Heavy: LOX tank below, CH4 tank above a common dome; the CH4
    downcomer runs through the LOX tank to the engine manifold.
    """
    parts = [
        _part(_dome(4300.0, 1300.0, 22400.0), "thrust_section_dome", COL_INNER),
        _part(_dome(4380.0, 1600.0, 56000.0), "lox_ch4_common_dome", COL_INNER),
        _part(_dome(4380.0, 1600.0, 84200.0), "ch4_forward_dome", COL_INNER),
        _part(vcyl(600.0, 23200.0, 56400.0), "ch4_downcomer", COL_INNER),
        _part(Cone(1000.0, 620.0, 900.0).moved(Pos(0, 0, 23000.0)),
              "downcomer_engine_manifold", COL_INNER),
        _part(Torus(4250.0, 130.0).moved(Pos(0, 0, 40000.0)), "lox_slosh_baffle", COL_INNER),
        _part(Torus(4250.0, 130.0).moved(Pos(0, 0, 70000.0)), "ch4_slosh_baffle", COL_INNER),
    ]
    return _grp("booster_interior", parts)


def _hot_stage_ring():
    """Sub-group 3: vented interstage (separates upward in the exploded view)."""
    parts = []
    parts.append(_part(ring(R_BODY + 60.0, R_BODY - 260.0, BOOSTER_BARREL_TOP, 87950.0),
                       "hot_stage_lower_flange", COL_STAINLESS))
    for i in range(20):
        a = radians(i * 18.0)
        parts.append(_part(
            box_at(360.0, 540.0, 2300.0, 4380.0 * cos(a), 4380.0 * sin(a), 89100.0,
                   rz=degrees(a)),
            f"hot_stage_column:{i + 1}", COL_STAINLESS))
    parts.append(_part(ring(R_BODY + 60.0, R_BODY - 260.0, 90250.0, HSR_TOP),
                       "hot_stage_upper_flange", COL_STAINLESS))
    parts.append(_part(
        revolve_poly([(120.0, 91250.0), (4250.0, 90400.0), (4250.0, 90250.0), (120.0, 91100.0)]),
        "hot_stage_blast_dome", COL_OLM))
    return _grp("hot_stage_ring", parts)


def build_booster():
    """Child order contract (sidecar refs): 1 shell, 2 interior, 3 hot-stage
    ring, 4-7 grid fins, 8-40 engines (3 center, 10 middle, 20 outer)."""
    children = [_booster_shell(), _booster_interior(), _hot_stage_ring()]

    for i, az in enumerate((45.0, 135.0, 225.0, 315.0)):
        inst = GRID_FIN.moved(
            Location((R_BODY * cos(radians(az)), R_BODY * sin(radians(az)), 85200.0),
                     (0, 0, az)))
        inst.label = f"grid_fin:{i + 1}"
        children.append(inst)

    exit_z = 18900.0
    for i in range(3):
        a = radians(i * 120.0)
        children.append(_place(ENGINE_SL_HI, f"raptor_center:{i + 1}",
                               1400.0 * cos(a), 1400.0 * sin(a), exit_z, rz=i * 120.0))
    for i in range(10):
        a = radians(18.0 + i * 36.0)
        children.append(_place(ENGINE_SL_HI, f"raptor_middle:{i + 1}",
                               2650.0 * cos(a), 2650.0 * sin(a), exit_z, rz=18.0 + i * 36.0))
    for i in range(20):
        a = radians(9.0 + i * 18.0)
        children.append(_place(ENGINE_SL_LO, f"raptor_outer:{i + 1}",
                               3780.0 * cos(a), 3780.0 * sin(a), exit_z, rz=9.0 + i * 18.0))

    return _grp("super_heavy_booster", children)



# --------------------------------------------------------------------------
# Starship upper stage
# --------------------------------------------------------------------------

NOSE_PTS = [
    (4500.0, SHIP_BARREL_TOP), (4380.0, 124000.0), (4050.0, 128000.0),
    (3480.0, 132000.0), (2700.0, 136000.0), (1750.0, 139500.0),
    (820.0, 141800.0), (260.0, 142550.0),
]


def _ship_shell():
    """Sub-group 1: ship barrel skin, skirt, catch pins, aft hardware."""
    parts = []
    parts.append(_part(ring(R_BODY + 40.0, R_BODY - 220.0, HSR_TOP, 91250.0),
                       "ship_aft_skirt_ring", COL_STAINLESS))
    parts.append(_part(vcyl(R_BODY, 91250.0, SHIP_BARREL_TOP), "ship_tank_barrel", COL_STAINLESS))
    parts += _weld_bands("ship_ring_weld", 93000.0, SHIP_BARREL_TOP - 200.0)

    for sy, tag in ((1.0, "port"), (-1.0, "starboard")):
        parts.append(_part(
            Cylinder(300.0, 750.0, rotation=(-sy * 90.0, 0, 0)).moved(
                Pos(0, sy * (R_BODY + 280.0), 118600.0)),
            f"ship_catch_pin:{tag}", COL_MECH))
        parts.append(_part(box_at(800.0, 600.0, 450.0, 0.0, sy * (R_BODY + 140.0), 119200.0, rz=90.0),
                           f"ship_catch_gusset:{tag}", COL_MECH))
    parts.append(_part(
        Cylinder(520.0, 90.0, rotation=(0, 90, 195.0)).moved(
            Pos((R_BODY + 30.0) * cos(radians(195.0)), (R_BODY + 30.0) * sin(radians(195.0)),
                95500.0)),
        "ship_access_hatch", COL_BAND))
    parts.append(_part(
        Cylinder(160.0, 650.0, rotation=(0, 90, 250.0)).moved(
            Pos((R_BODY + 120.0) * cos(radians(250.0)), (R_BODY + 120.0) * sin(radians(250.0)),
                93500.0)),
        "ship_aft_vent", COL_MECH))
    return _grp("ship_shell", parts)


def _ship_nose():
    """Sub-group 2: nosecone, tip, nose tiles, nose vents, forward flaps."""
    parts = []
    with BuildPart() as bp:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Spline(*NOSE_PTS)
                Polyline(NOSE_PTS[-1], (0.0, 142650.0), (0.0, SHIP_BARREL_TOP), NOSE_PTS[0])
            make_face()
        revolve(axis=Axis.Z)
    parts.append(_part(bp.part, "ship_nosecone", COL_STAINLESS))
    parts.append(_part(Sphere(300.0).moved(Pos(0, 0, 142500.0)), "nose_tip_cap", COL_STAINLESS))

    nose_tile_outer = [(r + 62.0, z) for r, z in NOSE_PTS[:7]]
    nose_tile_inner = [(r + 4.0, z) for r, z in reversed(NOSE_PTS[:7])]
    with BuildPart() as bp:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Spline(*nose_tile_outer)
                Line(nose_tile_outer[-1], nose_tile_inner[0])
                Spline(*nose_tile_inner)
                Line(nose_tile_inner[-1], nose_tile_outer[0])
            make_face()
        revolve(axis=Axis.Z, revolution_arc=192.0)
    parts.append(_part(bp.part.moved(Rotation(0, 0, 96.0)), "tile_shell_nose", COL_TILE))

    for tag, az, z, rr in (("nose_vent_1", 195.0, 138800.0, 1900.0),
                           ("nose_vent_2", 165.0, 137400.0, 2350.0)):
        a = radians(az)
        parts.append(_part(
            Cylinder(160.0, 650.0, rotation=(0, 90, degrees(a))).moved(
                Pos((rr + 120.0) * cos(a), (rr + 120.0) * sin(a), z)),
            f"ship_{tag}", COL_MECH))

    for sy, tag in ((1.0, "port"), (-1.0, "starboard")):
        az = sy * 116.0
        r_nose = 3300.0
        floc2 = (Location((0, 0, 0), (0, 0, az))
                 * Pos(r_nose + 300.0, sy * -250.0, 133200.0)
                 * Location((0, 0, 0), (0, 9.0, sy * -10.0)))
        parts.append(_part(Box(420.0, 2700.0, 5200.0).moved(floc2),
                           f"forward_flap:{tag}", COL_TILE))
        floc3 = (Location((0, 0, 0), (0, 0, az))
                 * Pos(r_nose + 60.0, sy * -1250.0, 133200.0)
                 * Location((0, 0, 0), (0, 9.0, 0)))
        parts.append(_part(Box(650.0, 800.0, 5600.0).moved(floc3),
                           f"forward_flap_hinge_fairing:{tag}", COL_STAINLESS))
    return _grp("ship_nose", parts)


def _ship_barrel_tiles():
    """Sub-group 3: windward barrel tile shell (explodes radially +X)."""
    barrel_tiles = revolve_poly(
        [(R_BODY + 5.0, 91400.0), (R_BODY + 70.0, 91400.0),
         (R_BODY + 70.0, SHIP_BARREL_TOP), (R_BODY + 5.0, SHIP_BARREL_TOP)],
        arc=192.0).moved(Rotation(0, 0, 96.0))
    return _grp("ship_barrel_tiles", [_part(barrel_tiles, "tile_shell_barrel", COL_TILE)])


def _ship_interior():
    """Sub-group 4: tank domes, LOX header tank, transfer tube, baffle."""
    parts = [
        _part(_dome(4300.0, 1400.0, 93400.0), "ship_thrust_dome", COL_INNER),
        _part(_dome(4380.0, 1500.0, 106500.0), "ship_common_dome", COL_INNER),
        _part(_dome(4380.0, 1500.0, 117300.0), "ship_forward_dome", COL_INNER),
        _part(Torus(4250.0, 120.0).moved(Pos(0, 0, 100000.0)), "ship_slosh_baffle", COL_INNER),
        _part(Cone(620.0, 1450.0, 2200.0).moved(Pos(0, 0, 131000.0)),
              "header_tank_support_cone", COL_INNER),
        _part(Sphere(1500.0).moved(Pos(0, 0, 133200.0)), "lox_header_tank", COL_INNER),
        _part(vcyl(350.0, 94200.0, 131000.0), "header_transfer_tube", COL_INNER),
    ]
    return _grp("ship_interior", parts)


def _aft_flap(sy, tag):
    """Sub-groups 5-6: aft flap + hinge fairing (explode radially)."""
    az = sy * 116.0
    loc = (Location((0, 0, 0), (0, 0, az))
           * Pos(R_BODY + 330.0, sy * -350.0, 95600.0)
           * Location((0, 0, 0), (0, 0, sy * -12.0)))
    flap = _part(Box(560.0, 3400.0, 7600.0).moved(loc), f"aft_flap:{tag}", COL_TILE)
    floc = Location((0, 0, 0), (0, 0, az)) * Pos(R_BODY + 120.0, sy * -1650.0, 95600.0)
    fairing = _part(Box(800.0, 1000.0, 8200.0).moved(floc),
                    f"aft_flap_hinge_fairing:{tag}", COL_STAINLESS)
    return _grp(f"aft_flap_assembly_{tag}", [flap, fairing])


def build_ship():
    """Child order contract (sidecar refs): 1 shell, 2 nose, 3 barrel tiles,
    4 interior, 5-6 aft flaps, 7-9 SL engines, 10-12 RVac engines."""
    children = [
        _ship_shell(),
        _ship_nose(),
        _ship_barrel_tiles(),
        _ship_interior(),
        _aft_flap(1.0, "port"),
        _aft_flap(-1.0, "starboard"),
    ]

    # Engines: 3 raptor3-contour sea-level + 3 raptor2-contour vacuum.
    for i in range(3):
        a = radians(i * 120.0)
        children.append(_place(ENGINE_SL_SHIP, f"ship_raptor_sl:{i + 1}",
                               1350.0 * cos(a), 1350.0 * sin(a), 91600.0, rz=i * 120.0))
    for i in range(3):
        a = radians(60.0 + i * 120.0)
        children.append(_place(ENGINE_RVAC, f"ship_raptor_vac:{i + 1}",
                               3150.0 * cos(a), 3150.0 * sin(a), 92790.0, rz=60.0 + i * 120.0))

    return _grp("starship_upper_stage", children)



# --------------------------------------------------------------------------
# Launch tower (Mechazilla)
# --------------------------------------------------------------------------


def _tower_columns():
    parts = []
    col = Box(1000.0, 1000.0, TOWER_TOP)
    foot = Box(2200.0, 2200.0, 900.0)
    splice = Box(1260.0, 1260.0, 420.0)
    for i, (sx, sy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        x = TOWER_CX + sx * TOWER_HALF
        y = sy * TOWER_HALF
        parts.append(_part(col.moved(Pos(x, y, TOWER_TOP / 2)), f"tower_chord:{i + 1}", COL_TOWER))
        parts.append(_part(foot.moved(Pos(x, y, 450.0)), f"tower_anchor:{i + 1}", COL_TOWER))
        # Bolted chord splice plates every other lattice bay.
        for k in range(2, PANEL_COUNT, 2):
            parts.append(_part(splice.moved(Pos(x, y, k * PANEL_H)),
                               f"chord_splice:{i + 1}:{k}", COL_TOWER_DARK))
    return parts


def _tower_lattice():
    parts = []
    span = 2.0 * TOWER_HALF
    beam_y = Box(400.0, span, 500.0)     # beams on +/-X faces run along Y
    beam_x = Box(span, 400.0, 500.0)     # beams on +/-Y faces run along X
    diag_len = hypot(span, PANEL_H)
    diag_ang = degrees(atan2(PANEL_H, span))
    diag = Box(diag_len, 320.0, 260.0)

    for k in range(1, PANEL_COUNT + 1):
        z = k * PANEL_H
        for sx in (1, -1):
            parts.append(_part(
                beam_y.moved(Pos(TOWER_CX + sx * TOWER_HALF, 0.0, z - 250.0)),
                f"tower_beam_x{'p' if sx > 0 else 'm'}:{k}", COL_TOWER))
        for sy in (1, -1):
            parts.append(_part(
                beam_x.moved(Pos(TOWER_CX, sy * TOWER_HALF, z - 250.0)),
                f"tower_beam_y{'p' if sy > 0 else 'm'}:{k}", COL_TOWER))
        zc = z - PANEL_H / 2.0
        for sx in (1, -1):
            for sgn in (1, -1):
                loc = (Pos(TOWER_CX + sx * TOWER_HALF, 0.0, zc)
                       * Location((0, 0, 0), (sgn * diag_ang, 0, 90.0)))
                parts.append(_part(diag.moved(loc),
                                   f"tower_brace_x{'p' if sx > 0 else 'm'}:{k}:{1 if sgn > 0 else 2}",
                                   COL_TOWER_DARK))
        for sy in (1, -1):
            for sgn in (1, -1):
                loc = (Pos(TOWER_CX, sy * TOWER_HALF, zc)
                       * Location((0, 0, 0), (0, sgn * diag_ang, 0)))
                parts.append(_part(diag.moved(loc),
                                   f"tower_brace_y{'p' if sy > 0 else 'm'}:{k}:{1 if sgn > 0 else 2}",
                                   COL_TOWER_DARK))
    return parts


def _tower_top_house():
    parts = [
        _part(box_at(13500.0, 13500.0, 3600.0, TOWER_CX, 0.0, TOWER_TOP + 1800.0),
              "tower_top_house", COL_TOWER),
        _part(Cylinder(950.0, 3200.0, rotation=(90, 0, 0)).moved(
            Pos(TOWER_CX, 0.0, HOUSE_TOP + 950.0)), "drawworks_drum", COL_MECH),
        _part(Cone(380.0, 130.0, 9500.0).moved(Pos(TOWER_CX, 0.0, HOUSE_TOP + 4750.0)),
              "lightning_mast", COL_TOWER_DARK),
        _part(vcyl(60.0, HOUSE_TOP + 9500.0, HOUSE_TOP + 11000.0, TOWER_CX, 0.0),
              "lightning_finial", COL_MECH),
    ]
    return parts


def _tower_rails():
    """Static rails + full-height hoist cables (valid for any carriage z)."""
    parts = []
    rail_x = TOWER_CX + TOWER_HALF + 750.0
    for sy in (1, -1):
        parts.append(_part(box_at(500.0, 450.0, 140000.0, rail_x, sy * 5300.0, 70000.0),
                           f"carriage_rail:{'p' if sy > 0 else 'm'}", COL_TOWER_DARK))
    for sy in (1, -1):
        parts.append(_part(
            vcyl(70.0, 3600.0, TOWER_TOP, rail_x + 800.0, sy * 2000.0),
            f"drawworks_cable:{'p' if sy > 0 else 'm'}", COL_PAD))
    return parts


def build_carriage():
    """Chopstick carriage: rides the rails (animated as one rigid group)."""
    parts = []
    rail_x = TOWER_CX + TOWER_HALF + 750.0
    cz = CARRIAGE_Z
    parts.append(_part(box_at(2100.0, 14200.0, 4800.0, rail_x + 1200.0, 0.0, cz),
                       "carriage_frame", COL_MECH))
    truck = Box(1500.0, 1100.0, 1500.0)
    for sy in (1, -1):
        for dz in (1650.0, -1650.0):
            parts.append(_part(truck.moved(Pos(rail_x + 150.0, sy * 5300.0, cz + dz)),
                               f"carriage_truck:{'p' if sy > 0 else 'm'}:{1 if dz > 0 else 2}",
                               COL_TOWER_DARK))
    parts.append(_part(box_at(1400.0, 9000.0, 900.0, rail_x + 1500.0, 0.0, cz + 2850.0),
                       "carriage_cable_yoke", COL_MECH))
    return _grp("chopstick_carriage", parts)


# Chopstick pivot coordinates - the sidecar mirrors these for live arm yaw.
ARM_PIVOT_X = TOWER_CX + TOWER_HALF + 2300.0
ARM_PIVOT_Y = 6500.0
ARM_PIVOT_Z = CARRIAGE_Z - 400.0


def build_chopstick_arm(sy, tag):
    """One catch arm: stepped box girder with toe-in, pads, tail, actuator.

    Returned as its own rigid group so the sidecar can yaw it about the
    vertical pivot axis at (ARM_PIVOT_X, sy*ARM_PIVOT_Y).
    """
    parts = []
    px = ARM_PIVOT_X
    py = sy * ARM_PIVOT_Y
    pz = ARM_PIVOT_Z
    toe = -sy * ARM_TOE_DEG

    pivot_loc = Location((px, py, pz)) * Location((0, 0, 0), (0, 0, toe))
    segs = ((9500.0, 2200.0, 3400.0, 0.0), (9000.0, 1800.0, 2800.0, 9250.0),
            (9000.0, 1300.0, 2100.0, 18250.0))
    for i, (length, w, h, x0) in enumerate(segs):
        parts.append(_part(
            Box(length, w, h).moved(pivot_loc * Pos(x0 + length / 2.0, 0.0, 0.0)),
            f"arm_{tag}_segment:{i + 1}", COL_TOWER))
        # External plate stiffener ribs on both girder webs.
        for j in range(4):
            xr = x0 + (j + 1) * length / 5.0
            for sw in (1.0, -1.0):
                parts.append(_part(
                    Box(260.0, 130.0, h + 220.0).moved(pivot_loc * Pos(xr, sw * (w / 2.0 + 60.0), 0.0)),
                    f"arm_{tag}_rib:{i + 1}:{j + 1}:{'o' if sw > 0 else 'i'}", COL_TOWER_DARK))
    parts.append(_part(Box(18200.0, 340.0, 280.0).moved(pivot_loc * Pos(9200.0, 0.0, 1850.0)),
                       f"arm_{tag}_top_rail", COL_TOWER_DARK))
    # Catch/lift pads near the tip and mid-span (vehicle rests on these).
    for i, x0 in enumerate((20500.0, 25400.0)):
        parts.append(_part(Box(2000.0, 1100.0, 340.0).moved(pivot_loc * Pos(x0, 0.0, 1220.0)),
                           f"arm_{tag}_pad_plate:{i + 1}", COL_MECH))
        parts.append(_part(Box(1500.0, 900.0, 260.0).moved(pivot_loc * Pos(x0, 0.0, 1520.0)),
                           f"arm_{tag}_pad:{i + 1}", COL_PAD))
    # Pivot pin, rear tail and slew actuator back to the carriage.
    parts.append(_part(vcyl(560.0, pz - 2000.0, pz + 2000.0, px, py), f"arm_{tag}_pivot", COL_MECH))
    parts.append(_part(Box(4200.0, 2000.0, 3000.0).moved(pivot_loc * Pos(-2400.0, 0.0, 0.0)),
                       f"arm_{tag}_tail", COL_TOWER))
    act0 = (px - 3600.0, py - sy * 900.0, pz - 300.0)
    act1 = (px - 900.0, sy * 3600.0, pz - 300.0)
    parts.append(_part(pipe([act1, act0], 300.0, bend=0), f"arm_{tag}_actuator", COL_MECH))
    parts.append(_part(pipe([act0, (px - 4400.0, py - sy * 1150.0, pz - 300.0)], 140.0, bend=0),
                       f"arm_{tag}_actuator_rod", COL_STAINLESS))
    return _grp(f"chopstick_arm_{tag}", parts)


# QD arm pivot (vertical axis) - mirrored by the sidecar for retraction.
QD_PIVOT_X = TOWER_CX + TOWER_HALF + 900.0
QD_PIVOT_Y = -3800.0


def build_qd_arm():
    parts = []
    base_x = QD_PIVOT_X
    parts.append(_part(vcyl(650.0, QD_Z - 2600.0, QD_Z + 2600.0, base_x, QD_PIVOT_Y),
                       "qd_pivot_column", COL_TOWER))
    boom_from = (base_x + 300.0, -3600.0, QD_Z)
    boom_to = (-5150.0, -900.0, QD_Z)
    yaw = degrees(atan2(boom_to[1] - boom_from[1], boom_to[0] - boom_from[0]))
    length = hypot(boom_to[0] - boom_from[0], boom_to[1] - boom_from[1])
    boom_loc = Location(boom_from) * Location((0, 0, 0), (0, 0, yaw))
    parts.append(_part(Box(length, 1400.0, 2000.0).moved(boom_loc * Pos(length / 2.0, 0, 0)),
                       "qd_boom", COL_QD))
    parts.append(_part(Box(500.0, 2700.0, 3300.0).moved(boom_loc * Pos(length + 150.0, 0, 0)),
                       "qd_umbilical_plate", COL_MECH))
    for i, dz in enumerate((650.0, -250.0)):
        parts.append(_part(
            Cylinder(280.0, 900.0, rotation=(0, 90, yaw)).moved(
                boom_loc * Pos(length + 550.0, 0, dz)),
            f"qd_umbilical_duct:{i + 1}", COL_PIPE))
    parts.append(_part(Box(3200.0, 2400.0, 550.0).moved(boom_loc * Pos(length - 1450.0, 0, 1900.0)),
                       "qd_hood", COL_QD))
    parts.append(_part(pipe(
        [(base_x + 500.0, -3300.0, QD_Z + 1500.0), (-2500.0, -1500.0, QD_Z + 1750.0)],
        150.0, bend=0), "qd_retract_strut", COL_MECH))
    parts.append(_part(pipe(
        [(base_x + 800.0, -3900.0, QD_Z - 900.0), (-1500.0, -2400.0, QD_Z - 1500.0),
         (-4200.0, -1200.0, QD_Z - 900.0)],
        170.0, bend=1500.0), "qd_service_loop", COL_PAD))
    return _grp("ship_quick_disconnect_arm", parts)


def _tower_platforms_and_services():
    parts = []
    deck = Box(13600.0, 2800.0, 350.0)
    rail_len = 13600.0
    post = Cylinder(60.0, 1100.0)
    back_x = TOWER_CX - TOWER_HALF - 1500.0
    for i, z in enumerate((15000.0, 38000.0, 60000.0, 82000.0, 110000.0, 128000.0)):
        parts.append(_part(deck.moved(Location((back_x, 0.0, z), (0, 0, 90.0))),
                           f"service_platform:{i + 1}", COL_GRATE))
        for j in range(6):
            y = -6200.0 + j * 2480.0
            parts.append(_part(post.moved(Pos(back_x - 1250.0, y, z + 725.0)),
                               f"platform_post:{i + 1}:{j + 1}", COL_TOWER_DARK))
        for k, dz in enumerate((1150.0, 650.0)):
            parts.append(_part(
                Cylinder(50.0, rail_len, rotation=(90, 0, 0)).moved(
                    Pos(back_x - 1250.0, 0.0, z + dz)),
                f"platform_rail:{i + 1}:{k + 1}", COL_TOWER_DARK))

    # Vertical cable trays and standpipes on the tower flanks.
    for sy, tag in ((1, "north"), (-1, "south")):
        parts.append(_part(
            box_at(500.0, 280.0, 138000.0, TOWER_CX, sy * (TOWER_HALF + 640.0), 69500.0),
            f"cable_tray:{tag}", COL_TOWER_DARK))
    for i, (dx, r) in enumerate(((-2400.0, 260.0), (-1500.0, 210.0), (-700.0, 170.0))):
        parts.append(_part(vcyl(r, 800.0, 139000.0, TOWER_CX + dx, TOWER_HALF + 900.0),
                           f"tower_standpipe:{i + 1}", COL_PIPE))

    parts.append(_part(box_at(6200.0, 4200.0, 3600.0, TOWER_CX - TOWER_HALF - 3100.0, 0.0, 1800.0),
                       "drawworks_winch_house", COL_TOWER))
    return parts


def build_tower_static():
    parts = []
    parts += _tower_columns()
    parts += _tower_lattice()
    parts += _tower_top_house()
    parts += _tower_rails()
    parts += _tower_platforms_and_services()
    return _grp("mechazilla_launch_tower", parts)


def build_tower_group():
    """Standalone tower system for `mechazilla_tower.step.py`.

    Child order (tower sidecar refs): 1 static tower, 2 carriage,
    3 chopstick arm port (+Y), 4 chopstick arm starboard (-Y), 5 QD arm.
    Matches root children #o1.1..#o1.5 of the full assembly, so the
    chopstick-close animation targets the same rigid groups.
    """
    return _grp("mechazilla_tower_system", [
        build_tower_static(),
        build_carriage(),
        build_chopstick_arm(1.0, "port"),
        build_chopstick_arm(-1.0, "starboard"),
        build_qd_arm(),
    ])


# --------------------------------------------------------------------------
# Root assembly
# --------------------------------------------------------------------------


def build_scene():
    """Root child order is the sidecar ref contract (#o1..#o8):

    1 mechazilla_launch_tower (static), 2 chopstick_carriage,
    3 chopstick_arm_port, 4 chopstick_arm_starboard,
    5 ship_quick_disconnect_arm, 6 orbital_launch_mount,
    7 super_heavy_booster, 8 starship_upper_stage.
    """
    return _grp("starship_mechazilla_launch_complex", [
        build_tower_static(),
        build_carriage(),
        build_chopstick_arm(1.0, "port"),
        build_chopstick_arm(-1.0, "starboard"),
        build_qd_arm(),
        build_olm(),
        build_booster(),
        build_ship(),
    ])
