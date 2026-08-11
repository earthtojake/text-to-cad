"""Shared geometry library for the SpaceX Starship / Super Heavy reconstruction.

DISCLAIMER: Educational, non-functional public-source reconstruction. Not
suitable for manufacture, propulsion, testing, or operational engineering.

Pinned vehicle version: Starship V2 / Block 2 (as flown Flights 7-11, 2025) —
the best-documented configuration in official public sources: itemized
official Flight 7 upgrade text, stable cross-confirmed dimensions, and five
flights of official imagery including two booster catches. The booster is
externally near-identical to Block 1; the hot-stage ring is modeled attached
(it is jettisoned after boostback in flight). See RESEARCH.md and VARIANTS.md
for the pinning rationale and V1/V3 deltas.

Only envelope numbers (9 m diameter, 71 m booster, ~50.3 m ship, 33+6 Raptor
engines) are sourced measurements used for scale. Every panel, dome position,
duct route, fin/flap proportion, and internal volume is a photogrammetric or
schematic estimate (LOW confidence). Interiors are translucent, simplified,
non-functional placeholder volumes. No tank wall construction, feedline
routing, flap actuation, TPS attachment, avionics, or valve/manifold detail
is modeled.

Coordinates (per vehicle model): centerline = Z, aft plane (engine nozzle exit
plane) = Z=0, vehicle extends +Z. The full stack composes booster + hot-stage
ring + ship along +Z. Units: millimeters, full scale. Windward side = -Y
(TPS field); leeward = +Y. Cutaways open toward +Y.

Raptor engines are linked subassemblies instanced from the sibling package
`models/renders/raptor2` (raptor2_common.build_exterior / build_vacuum_exterior);
see INSTANCE_MAP.md for the per-engine placement table.
"""

from __future__ import annotations

import sys
from math import cos, radians, sin
from pathlib import Path

from build123d import (
    Axis,
    Box,
    Color,
    Compound,
    Cylinder,
    Location,
    RegularPolygon,
    Plane,
    extrude,
)

_RAPTOR_DIR = Path(__file__).resolve().parent.parent / "raptor2"
if str(_RAPTOR_DIR) not in sys.path:
    sys.path.insert(0, str(_RAPTOR_DIR))

import raptor2_common as rc  # noqa: E402  (linked engine subassembly library)

DISPLAY_NAME = "SpaceX Starship / Super Heavy stack (educational public-source reconstruction)"

# ---------------------------------------------------------------------------
# Pinned dimensions (mm). Confidence per value; see DIMENSIONS.md.
# ---------------------------------------------------------------------------

RADIUS = 4500.0               # 9 m diameter, SpaceX published. HIGH
BOOSTER_HEIGHT = 69200.0      # Super Heavy body; 71 m published figure INCLUDES
                              # the 1.8 m vented interstage. HIGH (71 m) / LOW (split)
SHIP_HEIGHT = 52100.0         # Ship 52.1 m (V2, official Flight 7 text). HIGH
HOT_STAGE_H = 1800.0          # vented hot-staging ring, ~9 t, jettisoned in flight. HIGH
STACK_HEIGHT = BOOSTER_HEIGHT + HOT_STAGE_H + SHIP_HEIGHT  # 123.1 m (V2). HIGH

RING_H = 1830.0               # stainless barrel ring height, public figure. MEDIUM
SHELL_T = 45.0                # decorative shell thickness (NOT engineering data)

# Booster stations (photogrammetric estimates, LOW). Section order aft->fwd:
# engines/thrust section -> LOX tank -> common dome -> CH4 tank -> interstage.
B_SKIRT_TOP = 4200.0
B_LOX_TOP = 38500.0           # booster LOX tank (aft, ~2700 t) top / common dome
B_CH4_TOP = 65200.0           # booster CH4 tank (~700 t) top / forward dome
B_GRID_FIN_Z = 67000.0
# (ring radius mm, count, gimbal). Counts/gimbal split documented (3+10 gimbal,
# 20 fixed); radii are photogrammetric packing estimates, LOW.
B_ENGINE_RINGS = (
    (950.0, 3, True),
    (2300.0, 10, True),
    (3820.0, 20, False),
)
CHINE_AZ = (45.0, 135.0, 225.0, 315.0)   # 4 aero chines on the aft LOX tank. HIGH

# Ship stations (photogrammetric estimates, LOW). Section order aft->fwd:
# engine bay -> LOX tank -> common dome -> CH4 tank -> payload bay -> nosecone.
# V2: payload bay shortened to ~3 barrel rings; both header tanks in the nose.
S_SKIRT_TOP = 3600.0
S_LOX_TOP = 21000.0           # ship LOX tank (aft, ~1170 t) top / common dome
S_CH4_TOP = 33200.0           # ship CH4 tank (~330 t) top
S_PAYLOAD_TOP = 38800.0       # ~5.6 m / 3-ring payload bay (~614 m^3). MEDIUM
S_NOSE_BASE = 38800.0
S_SL_RING_R = 1300.0          # 3 gimbaling sea-level Raptors. photogrammetric LOW
S_RVAC_RING_R = 2950.0        # 3 fixed Raptor Vacuum at 120 deg. photogrammetric LOW

CUT_START_DEG = 135.0         # cutaways keep material 135..405 deg, open toward +Y
CUT_ARC_DEG = 270.0
CUT_INNER_START_DEG = 137.0
CUT_INNER_ARC_DEG = 266.0

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

COL_STEEL = Color(0.67, 0.68, 0.70, 1.0)          # stainless barrel
COL_STEEL_DARK = Color(0.52, 0.53, 0.55, 1.0)     # skirts / engine sections
COL_SEAM = Color(0.55, 0.56, 0.59, 1.0)           # ring weld seams
COL_TPS = Color(0.13, 0.13, 0.15, 1.0)            # TPS matte charcoal
COL_TILE = Color(0.17, 0.17, 0.20, 1.0)           # featured hex tiles
COL_FIN = Color(0.42, 0.41, 0.39, 1.0)            # grid fins (bare steel/alloy)
COL_RACEWAY = Color(0.36, 0.37, 0.39, 1.0)
COL_STRUCT = Color(0.44, 0.46, 0.50, 1.0)
COL_HOTSTAGE = Color(0.30, 0.31, 0.33, 1.0)

COL_LOX = Color(0.20, 0.45, 0.95, 0.45)           # LOX volumes = blue
COL_CH4 = Color(0.15, 0.75, 0.40, 0.45)           # methane volumes = green
COL_HOT = Color(0.95, 0.42, 0.12, 0.55)
COL_UNKNOWN = Color(0.62, 0.62, 0.68, 0.35)       # inferred placeholder gray
COL_PAYLOAD = Color(0.62, 0.62, 0.68, 0.25)

_label = rc._label
_group = rc._group


# ---------------------------------------------------------------------------
# Engine instancing (linked Raptor subassemblies)
# ---------------------------------------------------------------------------

_SL_ENGINE = None
_RVAC_ENGINE = None


def _sl_engine() -> Compound:
    global _SL_ENGINE
    if _SL_ENGINE is None:
        groups = rc.build_exterior()
        _SL_ENGINE = Compound(obj=groups, children=groups, label="raptor_sl")
    return _SL_ENGINE


def _rvac_engine() -> Compound:
    global _RVAC_ENGINE
    if _RVAC_ENGINE is None:
        groups = rc.build_vacuum_exterior()
        _RVAC_ENGINE = Compound(obj=groups, children=groups, label="raptor_vac")
    return _RVAC_ENGINE


def _engine_instance(base: Compound, label: str, x: float, y: float, az_deg: float) -> tuple:
    # (prototype, placement, name) for cadgen.compound_from_instances: shares
    # the prototype geometry instead of build123d .moved()'s per-instance
    # deep copy of the whole engine.
    return (base, Location((x, y, 0.0), (0, 0, az_deg)), label)


def booster_engine_positions() -> list[tuple[str, float, float, float, bool]]:
    """(label, x, y, azimuth_deg, gimbal) for the 33 booster engines."""
    positions = []
    index = 1
    for ring_number, (ring_r, count, gimbal) in enumerate(B_ENGINE_RINGS, start=1):
        for i in range(count):
            angle = 360.0 * i / count + (18.0 if ring_number == 2 else 0.0)
            a = radians(angle)
            positions.append(
                (
                    f"raptor_sl_booster_r{ring_number}_{index:02d}__instance",
                    ring_r * cos(a), ring_r * sin(a), angle, gimbal,
                )
            )
            index += 1
    return positions


def ship_engine_positions() -> list[tuple[str, str, float, float, float]]:
    """(label, variant, x, y, azimuth_deg) for the 6 ship engines."""
    positions = []
    for i in range(3):
        angle = 90.0 + 120.0 * i
        a = radians(angle)
        positions.append(
            (f"raptor_sl_ship_{i + 1:02d}__instance", "sl",
             S_SL_RING_R * cos(a), S_SL_RING_R * sin(a), angle)
        )
    for i in range(3):
        angle = 30.0 + 120.0 * i
        a = radians(angle)
        positions.append(
            (f"raptor_vac_ship_{i + 1:02d}__instance", "rvac",
             S_RVAC_RING_R * cos(a), S_RVAC_RING_R * sin(a), angle)
        )
    return positions


def make_booster_engines() -> Compound:
    from cadgen import compound_from_instances

    base = _sl_engine()
    placements = [
        _engine_instance(base, label, x, y, az)
        for label, x, y, az, _gimbal in booster_engine_positions()
    ]
    return compound_from_instances(
        "booster_engine_cluster__33_raptor_sl_instances", placements
    )


def make_ship_engines() -> Compound:
    from cadgen import compound_from_instances

    sl, rvac = _sl_engine(), _rvac_engine()
    placements = [
        _engine_instance(sl if variant == "sl" else rvac, label, x, y, az)
        for label, variant, x, y, az in ship_engine_positions()
    ]
    return compound_from_instances(
        "ship_engine_bay__3_sl_3_rvac_instances", placements
    )


# ---------------------------------------------------------------------------
# Hull primitives
# ---------------------------------------------------------------------------


def _barrel_shell(z0: float, z1: float, label: str, color: Color,
                  arc: float = 360.0, start: float = 0.0, radius: float = RADIUS,
                  thickness: float = SHELL_T):
    return rc.revolved_shell(
        [(radius - thickness, z0), (radius - thickness, z1)], thickness,
        label, color, arc, start,
    )


def _ring_seams(z0: float, z1: float, tag: str, arc: float = 360.0, start: float = 0.0,
                radius: float = RADIUS) -> list:
    """Slim proud bands at every barrel ring joint (real 1.83 m ring welds)."""
    from build123d import Torus

    parts = []
    z = z0 + RING_H
    i = 1
    while z < z1 - 100.0:
        seam = Torus(major_radius=radius + 4.0, minor_radius=9.0, major_angle=arc)
        seam = seam.locate(Location((0, 0, z), (0, 0, start)))
        parts.append(_label(seam, f"{tag}_ring_seam_{i:02d}__decorative", COL_SEAM))
        z += RING_H
        i += 1
    return parts


def _dome_outline(z_eq: float, up: bool, radius: float = RADIUS - SHELL_T,
                  aspect: float = 0.72) -> list[tuple[float, float]]:
    """Elliptical dome (r,z) outline from rim (at z_eq) to apex."""
    pts = []
    for i in range(0, 13):
        a = radians(90.0 * i / 12.0)
        r = radius * cos(a)
        dz = radius * aspect * sin(a)
        pts.append((max(r, 0.001), z_eq + dz if up else z_eq - dz))
    return pts


def _dome_shell(z_eq: float, up: bool, label: str, color: Color,
                arc: float = 360.0, start: float = 0.0, thickness: float = 40.0):
    return rc.revolved_shell(_dome_outline(z_eq, up), thickness, label, color, arc, start)


def _tank_volume(z0: float, z1: float, label: str, color: Color,
                 arc: float = 360.0, start: float = 0.0, radius: float = RADIUS - 160.0):
    """Schematic translucent propellant volume: cylinder with domed ends."""
    outline = (
        [(0.001, z0 - radius * 0.55)]
        + [(radius * sin(radians(a)), z0 - radius * 0.55 * cos(radians(a))) for a in range(15, 90, 15)]
        + [(radius, z0), (radius, z1)]
        + [(radius * cos(radians(a)), z1 + radius * 0.55 * sin(radians(a))) for a in range(15, 90, 15)]
        + [(0.001, z1 + radius * 0.55)]
    )
    return rc.revolved_solid(outline, label, color, arc, start, spline=False)


# ---------------------------------------------------------------------------
# Grid fins, flaps, hot-stage ring, TPS
# ---------------------------------------------------------------------------


def make_grid_fin(az_deg: float, index: int) -> Compound:
    """Fixed Super Heavy grid fin: frame + diagonal lattice, extending radially."""
    span, width, depth = 2600.0, 3300.0, 320.0   # photogrammetric estimates. LOW
    parts = []
    frame_bars = [
        (RADIUS + span / 2.0, 0.0, span, 130.0, "root_to_tip_a", -width / 2.0 + 65.0),
        (RADIUS + span / 2.0, 0.0, span, 130.0, "root_to_tip_b", width / 2.0 - 65.0),
        (RADIUS + 65.0, 0.0, 130.0, width, "root_bar", None),
        (RADIUS + span - 65.0, 0.0, 130.0, width, "tip_bar", None),
    ]
    for cx, _cy, lx, ly, tag, offset_y in frame_bars:
        cy = offset_y if offset_y is not None else 0.0
        parts.append(
            _label(
                Box(lx, ly, depth).locate(Location((cx, cy, 0.0))),
                f"grid_fin_{index}_frame_{tag}__photogrammetric", COL_FIN,
            )
        )
    # diagonal lattice slats (symbolic density, not the real web pattern)
    for k in range(-4, 5):
        for angle, tag in ((45.0, "d1"), (-45.0, "d2")):
            slat = Box(min(span, width) * 1.25, 60.0, depth - 60.0).locate(
                Location((RADIUS + span / 2.0, k * width / 9.0, 0.0), (0, 0, angle))
            )
            parts.append(
                _label(slat, f"grid_fin_{index}_lattice_{tag}_{k + 5:02d}__decorative", COL_FIN)
            )
    hinge = Cylinder(radius=210.0, height=700.0, rotation=(0, 90, 0)).locate(
        Location((RADIUS - 150.0, 0, 0))
    )
    parts.append(_label(hinge, f"grid_fin_{index}_hinge_boss__schematic", COL_STRUCT))
    fin = _group(f"grid_fin_{index}_group", parts)
    fin = fin.moved(Location((0, 0, B_GRID_FIN_Z), (0, 0, az_deg)))
    fin.label = f"grid_fin_{index}_group"
    return fin


def _flap(label: str, profile_xz: list[tuple[float, float]], mirror: bool,
          y_offset: float, thickness: float = 340.0, rot_z: float = 0.0) -> Compound:
    from build123d import Edge, Face, Vector, Wire

    pts = [(-x, z) if mirror else (x, z) for x, z in profile_xz]
    edges = [
        Edge.make_line(Vector(a[0], 0, a[1]), Vector(b[0], 0, b[1]))
        for a, b in zip(pts, pts[1:] + pts[:1])
    ]
    face = Face(Wire(edges))
    panel = extrude(face, amount=thickness / 2.0, both=True)
    panel = panel.moved(Location((0, y_offset, 0)))
    if rot_z:
        panel = panel.rotate(Axis.Z, rot_z)
    return _label(panel, label, COL_TPS)


def make_ship_flaps() -> Compound:
    # Aft (body) flaps: large, roots along the aft barrel, hinge plane at 180
    # deg included angle (windward-biased). photogrammetric LOW
    aft = [(3550.0, 3300.0), (8300.0, 5000.0), (8300.0, 9800.0), (6900.0, 11600.0), (3550.0, 11600.0)]
    # Forward flaps (V2): smaller, shifted toward the tip and rotated leeward
    # to a ~140 deg included angle between the pair (official Flight 7 text).
    fwd = [(2600.0, 43300.0), (5600.0, 44600.0), (5600.0, 47000.0), (4000.0, 47900.0), (2600.0, 47900.0)]
    parts = [
        _flap("aft_flap_starboard__photogrammetric", aft, False, -1150.0),
        _flap("aft_flap_port__photogrammetric", aft, True, -1150.0),
        _flap("forward_flap_starboard__v2_leeward_140deg__photogrammetric",
              fwd, False, 0.0, rot_z=20.0),
        _flap("forward_flap_port__v2_leeward_140deg__photogrammetric",
              fwd, True, 0.0, rot_z=-20.0),
    ]
    return _group("ship_flaps_group", parts)


def make_flap_root_fairings() -> list:
    parts = []
    for label, z0, z1, sign in (
        ("aft_flap_fairing_starboard", 3200.0, 11800.0, +1),
        ("aft_flap_fairing_port", 3200.0, 11800.0, -1),
    ):
        fairing = Box(900.0, 1500.0, z1 - z0).locate(
            Location((sign * (RADIUS - 250.0), -1150.0, (z0 + z1) / 2.0))
        )
        parts.append(_label(fairing, f"{label}__schematic", COL_TPS))
    return parts


def make_hot_stage_ring(z_base: float = 0.0) -> Compound:
    """Vented hot-staging adapter ring (introduced IFT-2). photogrammetric LOW."""
    parts = [
        _barrel_shell(z_base, z_base + HOT_STAGE_H, "hot_stage_ring_shell__photogrammetric",
                      COL_HOTSTAGE),
        rc.revolved_shell(
            [(RADIUS - 900.0, z_base + HOT_STAGE_H - 60.0),
             (RADIUS - 900.0, z_base + HOT_STAGE_H)],
            900.0, "hot_stage_top_deck__schematic", COL_STEEL_DARK,
        ),
    ]
    for i in range(36):
        az = 360.0 * i / 36.0
        a = radians(az)
        post = Box(160.0, 260.0, HOT_STAGE_H - 620.0).locate(
            Location((RADIUS * cos(a), RADIUS * sin(a), z_base + (HOT_STAGE_H - 500.0) / 2.0),
                     (0, 0, az))
        )
        parts.append(_label(post, f"hot_stage_vent_post_{i + 1:02d}__decorative", COL_HOTSTAGE))
    return _group("hot_stage_ring_group", parts)


def _tps_band(z0: float, z1: float, index: int, radius: float = RADIUS) -> object:
    """Windward (-Y) half-shell TPS band (arc 185deg centered on -Y)."""
    return rc.revolved_shell(
        [(radius + 8.0, z0), (radius + 8.0, z1)], 85.0,
        f"tps_windward_band_{index:02d}__schematic", COL_TPS,
        185.0, 177.5,
    )


def make_ship_tps() -> Compound:
    band_h = (S_NOSE_BASE - S_SKIRT_TOP) / 5.0
    parts = [_tps_band(S_SKIRT_TOP + i * band_h, S_SKIRT_TOP + (i + 1) * band_h, i + 1)
             for i in range(5)]
    # nosecone TPS cap: windward half of the ogive, slim offset shell
    nose = rc.revolved_shell(
        [(r + 8.0, z) for r, z in _ogive_outline()][:-1] + [(60.0, SHIP_HEIGHT - 60.0)],
        70.0, "tps_nosecone_windward__schematic", COL_TPS, 185.0, 177.5,
    )
    parts.append(nose)
    # featured hex tile array at the aft flap root region (windward)
    base_tile = extrude(
        Plane((RADIUS + 95.0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * RegularPolygon(390.0, 6),
        amount=85.0,
    )
    tiles = []
    n_tile = 0
    for row in range(6):
        z = 4700.0 + row * 690.0
        stagger = 4.6 if row % 2 else 0.0
        for col in range(18):
            az = 196.0 + stagger + col * 9.2
            if az > 344.0:
                continue
            # Place via Location (rotation composed into the occurrence
            # transform) rather than .rotate(), which bakes the rotation into
            # a new TShape: with baked rotations the ~99 tiles hash to ~33
            # distinct content-addressed components (one per azimuth) instead
            # of ONE shared hex-prism component meshed once.
            tile = base_tile.moved(Location((0, 0, z), (0, 0, az)))
            n_tile += 1
            tiles.append(_label(tile, f"tps_hex_tile_{n_tile:03d}__decorative", COL_TILE))
    parts.extend(tiles)
    return _group("ship_tps_field_group", parts)


def _ogive_outline() -> list[tuple[float, float]]:
    """Ship nosecone (r,z) outline, photogrammetric estimate."""
    return [
        (RADIUS, S_NOSE_BASE),
        (4420.0, 41500.0),
        (4150.0, 44300.0),
        (3600.0, 46800.0),
        (2750.0, 48900.0),
        (1700.0, 50600.0),
        (750.0, 51700.0),
        (0.001, SHIP_HEIGHT),
    ]


# ---------------------------------------------------------------------------
# Booster
# ---------------------------------------------------------------------------


def make_booster_hull(arc: float = 360.0, start: float = 0.0) -> Compound:
    parts = [
        _barrel_shell(150.0, B_SKIRT_TOP, "booster_aft_skirt__photogrammetric",
                      COL_STEEL_DARK, arc, start),
        _barrel_shell(B_SKIRT_TOP, BOOSTER_HEIGHT, "booster_barrel__measured_envelope",
                      COL_STEEL, arc, start),
        _dome_shell(B_LOX_TOP, True, "booster_common_dome__schematic", COL_STEEL, arc, start),
        _dome_shell(B_CH4_TOP, True, "booster_forward_dome__schematic", COL_STEEL, arc, start),
        _dome_shell(B_SKIRT_TOP - 300.0, True, "booster_thrust_dome__schematic",
                    COL_STEEL_DARK, arc, start),
    ]
    parts.extend(_ring_seams(B_SKIRT_TOP, BOOSTER_HEIGHT, "booster", arc, start))
    return _group("booster_hull_group", parts)


def make_booster_fittings() -> Compound:
    parts = []
    for az in (0.0, 180.0):
        a = radians(az)
        raceway = Box(260.0, 420.0, BOOSTER_HEIGHT - B_SKIRT_TOP - 400.0).locate(
            Location((cos(a) * (RADIUS + 130.0), sin(a) * (RADIUS + 130.0),
                      (B_SKIRT_TOP + BOOSTER_HEIGHT) / 2.0), (0, 0, az))
        )
        parts.append(
            _label(raceway, f"booster_raceway_{int(az)}deg__photogrammetric", COL_RACEWAY)
        )
    for i, az in enumerate((45.0, 135.0, 225.0, 315.0), start=1):
        parts.append(make_grid_fin(az, i))
    # 4 aerodynamic chines on the aft LOX tank (house COPVs/batteries). HIGH
    for i, az in enumerate(CHINE_AZ, start=1):
        a = radians(az)
        chine = Box(560.0, 950.0, 26500.0).locate(
            Location((cos(a) * (RADIUS + 250.0), sin(a) * (RADIUS + 250.0), 18700.0),
                     (0, 0, az))
        )
        parts.append(
            _label(chine, f"booster_chine_{i}__copv_battery_fairing__photogrammetric",
                   COL_STEEL_DARK)
        )
    for i, az in enumerate((90.0, 270.0), start=1):
        a = radians(az)
        lug = Cylinder(radius=260.0, height=900.0, rotation=(0, 90, 0)).locate(
            Location((cos(a) * (RADIUS + 220.0), sin(a) * (RADIUS + 220.0), 64200.0), (0, 0, az))
        )
        parts.append(_label(lug, f"booster_catch_hardpoint_{i}__photogrammetric", COL_STRUCT))
    for i in range(6):
        az = 55.0 + i * 12.0
        a = radians(az)
        copv = Cylinder(radius=330.0, height=3300.0).locate(
            Location((cos(a) * (RADIUS - 620.0), sin(a) * (RADIUS - 620.0), 66200.0))
        )
        parts.append(_label(copv, f"booster_copv_{i + 1}__photogrammetric_placeholder", COL_STRUCT))
    return _group("booster_fittings_group", parts)


def make_booster_interior(full_arc: bool = False) -> Compound:
    """Schematic translucent internals (cutaway); sectored to sit inside shells."""
    arc = 360.0 if full_arc else CUT_INNER_ARC_DEG
    start = 0.0 if full_arc else CUT_INNER_START_DEG
    parts = [
        _tank_volume(6800.0, 35800.0, "booster_lox_tank_volume__schematic", COL_LOX, arc, start),
        _tank_volume(41300.0, 62600.0, "booster_ch4_tank_volume__schematic", COL_CH4, arc, start),
        rc.tube([(0, 0, 41300.0), (0, 0, 20000.0), (0, 0, 5200.0)], 620.0,
                "booster_ch4_downcomer__schematic_routing", COL_CH4),
        rc.tube([(0, 0, 6800.0), (0, 0, 5600.0), (0, 0, 4400.0)], 780.0,
                "booster_lox_sump_feed__schematic_routing", COL_LOX),
    ]
    from build123d import Torus

    for ring_r, count, _g in B_ENGINE_RINGS:
        manifold = Torus(major_radius=ring_r, minor_radius=210.0).locate(Location((0, 0, 3550.0)))
        parts.append(
            _label(manifold, f"booster_engine_bay_manifold_r{int(ring_r)}__schematic", COL_LOX)
        )
    for label, x, y, az, _g in booster_engine_positions():
        block = Box(560.0, 560.0, 260.0).locate(Location((x, y, 3280.0), (0, 0, az)))
        parts.append(
            _label(block, label.replace("__instance", "_mount_block__schematic"), COL_STRUCT)
        )
    for i in range(24):
        az = 360.0 * i / 24.0
        rib = Box(70.0, 340.0, B_SKIRT_TOP - 400.0).locate(
            Location((cos(radians(az)) * (RADIUS - 260.0), sin(radians(az)) * (RADIUS - 260.0),
                      B_SKIRT_TOP / 2.0), (0, 0, az))
        )
        parts.append(_label(rib, f"booster_skirt_stringer_{i + 1:02d}__schematic", COL_STEEL_DARK))
    for i in range(8):
        az = 20.0 + i * 45.0
        a = radians(az)
        avionics = Box(700.0, 460.0, 520.0).locate(
            Location((cos(a) * (RADIUS - 700.0), sin(a) * (RADIUS - 700.0), 64600.0), (0, 0, az))
        )
        parts.append(
            _label(avionics, f"booster_avionics_module_{i + 1}__schematic_placeholder", COL_UNKNOWN)
        )
    return _group("booster_interior_group__schematic_nonfunctional", parts)


# ---------------------------------------------------------------------------
# Ship
# ---------------------------------------------------------------------------


def make_ship_hull(arc: float = 360.0, start: float = 0.0) -> Compound:
    nose_pts = _ogive_outline()
    parts = [
        _barrel_shell(150.0, S_SKIRT_TOP, "ship_aft_skirt__photogrammetric",
                      COL_STEEL_DARK, arc, start),
        _barrel_shell(S_SKIRT_TOP, S_NOSE_BASE, "ship_barrel__measured_envelope",
                      COL_STEEL, arc, start),
        rc.revolved_shell(nose_pts[:-1] + [(60.0, SHIP_HEIGHT - 55.0)], 45.0,
                          "ship_nosecone__photogrammetric", COL_STEEL, arc, start),
        _dome_shell(S_LOX_TOP, True, "ship_common_dome__schematic", COL_STEEL, arc, start),
        _dome_shell(S_CH4_TOP, True, "ship_forward_dome__schematic", COL_STEEL, arc, start),
        _dome_shell(S_SKIRT_TOP - 300.0, True, "ship_thrust_dome__schematic",
                    COL_STEEL_DARK, arc, start),
    ]
    parts.extend(_ring_seams(S_SKIRT_TOP, S_NOSE_BASE, "ship", arc, start))
    parts.extend(make_flap_root_fairings())
    raceway = Box(260.0, 420.0, S_NOSE_BASE - S_SKIRT_TOP - 400.0).locate(
        Location((0.0, RADIUS + 130.0, (S_SKIRT_TOP + S_NOSE_BASE) / 2.0))
    )
    parts.append(_label(raceway, "ship_leeward_raceway__photogrammetric", COL_RACEWAY))
    return _group("ship_hull_group", parts)


def make_ship_interior(full_arc: bool = False) -> Compound:
    arc = 360.0 if full_arc else CUT_INNER_ARC_DEG
    start = 0.0 if full_arc else CUT_INNER_START_DEG
    parts = [
        _tank_volume(6200.0, 18200.0, "ship_lox_tank_volume__schematic", COL_LOX, arc, start),
        _tank_volume(23500.0, 30500.0, "ship_ch4_tank_volume__schematic", COL_CH4, arc, start),
        rc.revolved_solid(
            [(0.001, S_CH4_TOP + 1100.0), (RADIUS - 400.0, S_CH4_TOP + 1100.0),
             (RADIUS - 400.0, S_PAYLOAD_TOP - 500.0), (0.001, S_PAYLOAD_TOP - 500.0)],
            "ship_payload_bay_volume__614m3_public_figure__schematic", COL_PAYLOAD, arc, start,
        ),
        rc.tube([(0, 0, 23500.0), (0, 0, 12000.0), (0, 0, 4400.0)], 480.0,
                "ship_ch4_downcomer__schematic_routing", COL_CH4),
        # V2 header tanks: LOX header forms the nose tip, CH4 header directly
        # below it (both-in-nose consolidation, MEDIUM confidence)
        _label(
            Cylinder(radius=900.0, height=1900.0).locate(Location((0, 0, 49900.0))),
            "ship_nose_lox_header_tank__schematic_placeholder", COL_LOX,
        ),
        _label(
            Cylinder(radius=1050.0, height=1700.0).locate(Location((0, 0, 47900.0))),
            "ship_ch4_header_tank_below_nose_lox__v2__schematic_placeholder", COL_CH4,
        ),
    ]
    for i in range(8):
        az = 15.0 + i * 45.0
        a = radians(az)
        avionics = Box(640.0, 420.0, 480.0).locate(
            Location((cos(a) * (RADIUS - 680.0), sin(a) * (RADIUS - 680.0), 34500.0), (0, 0, az))
        )
        parts.append(
            _label(avionics, f"ship_avionics_module_{i + 1}__schematic_placeholder", COL_UNKNOWN)
        )
    for tag, x, y, z in (
        ("aft_starboard", RADIUS - 850.0, -1050.0, 7200.0),
        ("aft_port", -(RADIUS - 850.0), -1050.0, 7200.0),
        ("fwd_starboard", 2500.0, 900.0, 45600.0),
        ("fwd_port", -2500.0, 900.0, 45600.0),
    ):
        block = Box(1000.0, 800.0, 1300.0).locate(Location((x, y, z)))
        parts.append(
            _label(block, f"flap_root_actuator_placeholder_{tag}__schematic_nonfunctional",
                   COL_UNKNOWN)
        )
    for label, _v, x, y, az in ship_engine_positions():
        block = Box(560.0, 560.0, 260.0).locate(Location((x, y, S_SKIRT_TOP - 320.0), (0, 0, az)))
        parts.append(
            _label(block, label.replace("__instance", "_mount_block__schematic"), COL_STRUCT)
        )
    return _group("ship_interior_group__schematic_nonfunctional", parts)


# ---------------------------------------------------------------------------
# Assemblies
# ---------------------------------------------------------------------------


def build_booster(arc: float = 360.0, start: float = 0.0, interior: bool = False) -> list[Compound]:
    groups = [make_booster_hull(arc, start), make_booster_fittings(), make_booster_engines()]
    if interior:
        groups.append(make_booster_interior())
    return groups


def build_ship(arc: float = 360.0, start: float = 0.0, interior: bool = False) -> list[Compound]:
    groups = [
        make_ship_hull(arc, start),
        make_ship_tps(),
        make_ship_flaps(),
        make_ship_engines(),
    ]
    if interior:
        groups.append(make_ship_interior())
    return groups


def _moved_group(group: Compound, dz: float) -> Compound:
    moved = group.moved(Location((0, 0, dz)))
    moved.label = group.label
    return moved


def build_stack(arc: float = 360.0, start: float = 0.0, interior: bool = False) -> list[Compound]:
    booster_groups = build_booster(arc, start, interior=interior)
    ring = make_hot_stage_ring(z_base=BOOSTER_HEIGHT)
    ship_dz = BOOSTER_HEIGHT + HOT_STAGE_H
    ship_groups = [_moved_group(g, ship_dz) for g in build_ship(arc, start, interior=interior)]
    booster = Compound(obj=booster_groups, children=booster_groups,
                       label="super_heavy_booster_assembly")
    ship = Compound(obj=ship_groups, children=ship_groups, label="starship_ship_assembly")
    return [booster, ring, ship]
