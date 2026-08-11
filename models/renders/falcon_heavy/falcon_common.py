"""Shared geometry library for the SpaceX Falcon Heavy educational reconstruction.

DISCLAIMER: Educational, non-functional public-source reconstruction. Not
suitable for manufacture, propulsion, testing, or operational engineering.

Scale anchors are published envelope figures (height 70 m, width 12.2 m, core
dia 3.66 m, fairing 5.2 x 13.1 m — SpaceX Falcon pages / User's Guide). All
station positions, internal volumes, and hardware shapes beyond those anchors
are photogrammetric or schematic estimates (LOW confidence) and are labeled
as such. Tank walls, separation hardware, avionics, COPV counts, and feed
routing are NOT modeled — schematic placeholder volumes only.

Coordinates: vehicle centerline = Z, first-stage Merlin nozzle exit plane
= Z=0, +Z up. Units mm, full scale. Side boosters at X = ±3660.
"""

from __future__ import annotations

from math import cos, radians, sin

from build123d import (
    Axis, Box, Color, Compound, Cylinder, Edge, Face, Location, Sphere,
    Vector, Wire, revolve,
)

import merlin_common as eng

DISPLAY_NAME = "SpaceX Falcon Heavy (educational public-source reconstruction)"

# ---------------------------------------------------------------------------
# Published anchors (mm) — see RESEARCH.md / DIMENSIONS.md
# ---------------------------------------------------------------------------

CORE_R = 1830.0            # core dia 3.66 m. HIGH (published)
VEHICLE_H = 70000.0        # height 70 m. HIGH (published)
CORE_PITCH = 3660.0        # side-booster centerline offset. derived from 12.2 m width
FAIRING_R = 2600.0         # fairing dia 5.2 m. HIGH (published)
FAIRING_L = 13100.0        # fairing length 13.1 m. HIGH (published)

# Station layout (photogrammetric estimates, LOW):
Z_SKIRT_TOP = 2600.0       # aft skirt / octaweb top
Z_BOOSTER_TOP = 42000.0    # booster tank top
Z_INTER_TOP = 48500.0      # interstage top (center core)
Z_S2_TOP = VEHICLE_H - FAIRING_L + 150.0   # second stage top ~56.9 m
Z_RP1_TOP = 17000.0        # S1 RP-1 tank (lower) top. schematic
Z_LOX_BOT = 17500.0        # S1 LOX tank (upper) bottom. schematic
OCTAWEB_R = 1290.0         # outer engine circle radius. cluster-fit estimate

COL_WHITE = Color(0.92, 0.92, 0.93, 1.0)
COL_SOOT = Color(0.78, 0.78, 0.79, 1.0)
COL_BLACK = Color(0.10, 0.10, 0.11, 1.0)
COL_BAY = Color(0.16, 0.16, 0.17, 1.0)
COL_METAL = Color(0.55, 0.57, 0.60, 1.0)
COL_TITAN = Color(0.48, 0.47, 0.50, 1.0)
COL_LEG = Color(0.20, 0.20, 0.22, 1.0)
COL_NIOB = Color(0.27, 0.26, 0.28, 1.0)
COL_LOX = Color(0.20, 0.45, 0.95, 0.45)
COL_RP1 = Color(0.85, 0.60, 0.15, 0.45)
COL_GRAY = Color(0.62, 0.62, 0.68, 0.40)
COL_GUIDE = Color(0.55, 0.57, 0.62, 0.45)

CUT_START, CUT_ARC = 135.0, 270.0     # cutaway opening faces +Y


def _lab(part, label, color=None):
    part.label = label
    if color is not None:
        part.color = color
    return part


def _grp(label, parts):
    return Compound(obj=parts, children=parts, label=label)


def _tube_z(x, y, z0, z1, r, label, color, hollow_t=0.0):
    if hollow_t > 0.0:
        outline = [(r - hollow_t, z0), (r, z0), (r, z1), (r - hollow_t, z1)]
        pts3 = [Vector(px, 0, pz) for px, pz in outline]
        edges = [Edge.make_line(a, b) for a, b in zip(pts3, pts3[1:])]
        edges.append(Edge.make_line(pts3[-1], pts3[0]))
        part = revolve(Face(Wire(edges)), axis=Axis.Z, revolution_arc=360)
        part = part.moved(Location((x, y, 0)))
    else:
        part = Cylinder(radius=r, height=z1 - z0).locate(Location((x, y, (z0 + z1) / 2)))
    return _lab(part, label, color)


def _dome(x, y, z, r, up, label, color, squash=0.55):
    outline = [(0.001, z)] + [
        (r * sin(radians(a)), z + up * squash * r * cos(radians(a)))
        for a in range(80, -1, -10)
    ]
    outline = [(0.001, z + up * squash * r)] + [
        (r * sin(radians(a)), z + up * squash * r * cos(radians(a))) for a in range(10, 91, 10)
    ] + [(0.001, z)]
    pts3 = [Vector(px, 0, pz) for px, pz in outline]
    edges = [Edge.make_spline(pts3[:-1]), Edge.make_line(pts3[-2], pts3[-1]),
             Edge.make_line(pts3[-1], pts3[0])]
    part = revolve(Face(Wire(edges)), axis=Axis.Z, revolution_arc=360)
    return _lab(part.moved(Location((x, y, 0))), label, color)


# ---------------------------------------------------------------------------
# Engine cluster (linked Merlin 1D instances)
# ---------------------------------------------------------------------------

_ENGINE_PROTO = None


def engine_prototype() -> Compound:
    """One reduced-detail Merlin 1D built from the vendored linked library."""
    global _ENGINE_PROTO
    if _ENGINE_PROTO is None:
        eng.DETAIL_BOLTS = False
        groups = [
            eng.make_nozzle_assembly(),
            eng.make_chamber_assembly(),
            eng.make_thrust_structure(),
            eng.make_turbopump_assembly(),
            eng.make_gas_generator_assembly(),
            eng.make_turbine_exhaust_assembly(),
        ]
        _ENGINE_PROTO = _grp("merlin1d_linked_prototype", groups)
    return _ENGINE_PROTO


def make_engine_cluster(core_x: float, core_tag: str) -> Compound:
    """Octaweb 8-around-1; outer pumps oriented tangentially to clear neighbors.

    Instances share the prototype geometry via cadgen.compound_from_instances
    (O(1) OCCT placements); build123d .moved() deep-copies the ~70-solid
    engine per instance, which dominated stack compose time.
    """
    from cadgen import compound_from_instances

    proto = engine_prototype()
    placements = [
        (proto, Location((core_x, 0, 0), (0, 0, 90)),
         f"merlin1d_instance_{core_tag}_center__linked"),
    ]
    for i in range(8):
        az = i * 45.0
        a = radians(az)
        placements.append(
            (
                proto,
                Location((core_x + OCTAWEB_R * cos(a), OCTAWEB_R * sin(a), 0), (0, 0, az + 90)),
                f"merlin1d_instance_{core_tag}_outer_{i + 1}__linked",
            )
        )
    return compound_from_instances(
        f"{core_tag}_engine_cluster__octaweb_9x_merlin1d", placements
    )


def make_mvac() -> Compound:
    """Merlin Vacuum derivative: linked powerhead + schematic niobium skirt.

    MVac exit diameter is publicly conflicting (2.4-3.3 m); modeled 2.9 m,
    labeled estimate. Nozzle is a schematic two-cone extension, NOT a sourced
    contour."""
    eng.DETAIL_BOLTS = False
    parts = [
        eng.make_chamber_assembly(),
        eng.make_thrust_structure(),
        eng.make_turbopump_assembly(),
        eng.make_gas_generator_assembly(),
    ]
    regen = [(eng.THROAT_RADIUS, eng.Z_THROAT),
             (eng.THROAT_RADIUS + 30.0, eng.Z_THROAT - 120.0),
             (330.0, 800.0), (560.0, 200.0), (700.0, 0.0)]
    parts.append(_grp("mvac_nozzle_group", [
        eng.revolved_shell(regen, 16.0,
                           "mvac_regen_nozzle_section__schematic", eng.COL_BELL_OUTER),
        eng.revolved_shell(
            [(700.0, 0.0), (1000.0, -800.0), (1250.0, -1700.0), (1450.0, -2700.0)],
            10.0, "mvac_niobium_skirt__estimate_2p9m_exit", COL_NIOB),
        _lab(Cylinder(radius=1462, height=60).locate(Location((0, 0, -2700))),
             "mvac_exit_stiffener__decorative", COL_NIOB),
    ]))
    return _grp("mvac_engine__linked_derivative_schematic", parts)


# ---------------------------------------------------------------------------
# Booster (one core)
# ---------------------------------------------------------------------------


def make_booster(core_x: float, tag: str, center: bool,
                 arc=360.0, start=0.0, sectioned=False) -> list[Compound]:
    s = []  # structure parts
    # aft skirt / engine bay (heat-darkened)
    s.append(_tube_z(core_x, 0, 1800.0, Z_SKIRT_TOP + 500, CORE_R,
                     f"{tag}_aft_skirt_octaweb_shell__photogrammetric", COL_BAY,
                     hollow_t=60.0))
    s.append(_lab(Cylinder(radius=CORE_R - 55, height=90).locate(
        Location((core_x, 0, Z_SKIRT_TOP + 460))),
        f"{tag}_engine_bay_heat_shield_deck__schematic", COL_BAY))
    # tank barrel (white; sectioned for center-core cutaway)
    if sectioned:
        barrel = eng.revolved_solid(
            [(CORE_R - 40, Z_SKIRT_TOP + 500), (CORE_R, Z_SKIRT_TOP + 500),
             (CORE_R, Z_BOOSTER_TOP), (CORE_R - 40, Z_BOOSTER_TOP)],
            f"{tag}_tank_barrel__white_livery__photogrammetric", COL_WHITE, arc, start)
        s.append(barrel.moved(Location((core_x, 0, 0))))
        s[-1].label = f"{tag}_tank_barrel__white_livery__photogrammetric"
    else:
        s.append(_tube_z(core_x, 0, Z_SKIRT_TOP + 500, Z_BOOSTER_TOP, CORE_R,
                         f"{tag}_tank_barrel__white_livery__photogrammetric", COL_WHITE))
    # tank joint bands
    for i, z in enumerate((Z_RP1_TOP, Z_LOX_BOT, 30000.0, Z_BOOSTER_TOP - 600)):
        s.append(_tube_z(core_x, 0, z, z + 260.0, CORE_R + 18,
                         f"{tag}_tank_band_{i + 1:02d}__decorative", COL_SOOT,
                         hollow_t=18.0))
    # raceways (2 per core)
    for j, az in enumerate((25.0, 205.0)):
        a = radians(az)
        s.append(_lab(
            Box(170, 130, Z_BOOSTER_TOP - 3400).locate(Location(
                (core_x + (CORE_R + 60) * cos(a), (CORE_R + 60) * sin(a),
                 (Z_BOOSTER_TOP + 3100) / 2), (0, 0, az))),
            f"{tag}_raceway_{j + 1}__photogrammetric", COL_WHITE))
        for k in range(6):
            z = 6000.0 + k * 6000.0
            s.append(_lab(Box(220, 180, 300).locate(Location(
                (core_x + (CORE_R + 60) * cos(a), (CORE_R + 60) * sin(a), z), (0, 0, az))),
                f"{tag}_raceway_clamp_{j + 1}_{k + 1:02d}__decorative", COL_SOOT))
    # SpaceX-style decal bars + flag panel (decorative livery)
    s.append(_lab(Box(90, 2400, 420).locate(Location(
        (core_x + CORE_R - 12, 0, 24000.0))),
        f"{tag}_logo_panel__decorative_livery", COL_BLACK))
    s.append(_lab(Box(90, 900, 560).locate(Location(
        (core_x + CORE_R - 12, 1400, 36000.0))),
        f"{tag}_flag_panel__decorative_livery", COL_BLACK))
    # landing legs (4, stowed)
    legs = []
    for i, az in enumerate((45.0, 135.0, 225.0, 315.0)):
        a = radians(az)
        lx, ly = core_x + (CORE_R + 130) * cos(a), (CORE_R + 130) * sin(a)
        legs.append(_lab(
            Box(300, 900, 11500).locate(Location((lx, ly, 8400.0), (0, 0, az))),
            f"{tag}_landing_leg_{i + 1}__stowed__photogrammetric", COL_LEG))
        legs.append(_lab(
            Box(340, 1100, 900).locate(Location((lx + 40 * cos(a), ly + 40 * sin(a), 3050.0), (0, 0, az))),
            f"{tag}_leg_hold_down_shoe_{i + 1}__schematic", COL_LEG))
        legs.append(_lab(
            Box(260, 700, 1500).locate(Location((lx, ly, 14700.0), (0, 0, az))),
            f"{tag}_leg_upper_fairing_{i + 1}__photogrammetric", COL_WHITE))
    # grid fins (4, stowed flat)
    fins = []
    for i, az in enumerate((35.0, 145.0, 215.0, 325.0)):
        a = radians(az)
        fx, fy = core_x + (CORE_R + 170) * cos(a), (CORE_R + 170) * sin(a)
        fz = Z_BOOSTER_TOP - 1500.0
        fins.append(_lab(Box(120, 2000, 1450).locate(Location((fx, fy, fz), (0, 0, az))),
                         f"{tag}_grid_fin_frame_{i + 1}__titanium__photogrammetric", COL_TITAN))
        for k in range(4):
            fins.append(_lab(
                Box(130, 60, 1350).locate(Location(
                    (fx, fy - 750 + k * 500, fz), (0, 0, az))),
                f"{tag}_grid_fin_rib_{i + 1}_{k + 1}__schematic", COL_TITAN))
        fins.append(_lab(
            Cylinder(radius=210, height=420, rotation=(0, 90, 0)).locate(
                Location((fx - 200 * cos(a), fy - 200 * sin(a), fz), (0, 0, az))),
            f"{tag}_grid_fin_actuator_hub_{i + 1}__schematic", COL_TITAN))
    groups = [
        _grp(f"{tag}_structure_group", s),
        _grp(f"{tag}_landing_legs_group", legs),
        _grp(f"{tag}_grid_fins_group", fins),
        make_engine_cluster(core_x, tag),
    ]
    # top: interstage (center) or nosecone (side)
    if center:
        inter = []
        if sectioned:
            shell = eng.revolved_solid(
                [(CORE_R - 40, Z_BOOSTER_TOP), (CORE_R, Z_BOOSTER_TOP),
                 (CORE_R, Z_INTER_TOP), (CORE_R - 40, Z_INTER_TOP)],
                "interstage_shell__black_livery__photogrammetric", COL_BLACK, arc, start)
            inter.append(shell.moved(Location((core_x, 0, 0))))
            inter[-1].label = "interstage_shell__black_livery__photogrammetric"
        else:
            inter.append(_tube_z(core_x, 0, Z_BOOSTER_TOP, Z_INTER_TOP, CORE_R,
                                 "interstage_shell__black_livery__photogrammetric",
                                 COL_BLACK))
        for i in range(3):
            inter.append(_lab(
                Box(500, 380, 300).locate(Location(
                    (core_x - CORE_R + 320, -500 + i * 500, Z_INTER_TOP - 900))),
                f"interstage_avionics_module_{i + 1}__schematic_placeholder", COL_GRAY))
        groups.append(_grp("interstage_group", inter))
    else:
        nose = eng.revolved_solid(
            [(0.001, Z_BOOSTER_TOP)]
            + [(max(0.001, CORE_R * (1 - (t / 16.0) ** 1.8)),
                Z_BOOSTER_TOP + 6500.0 * t / 16.0) for t in range(17)],
            f"{tag}_nosecone__white__photogrammetric", COL_WHITE)
        groups.append(_grp(f"{tag}_nosecone_group",
                           [nose.moved(Location((core_x, 0, 0)))]))
        groups[-1].children[0].label = f"{tag}_nosecone__white__photogrammetric"
    return groups


def make_attachments() -> Compound:
    """Side-booster attach hardware (schematic blocks/struts)."""
    parts = []
    for sx, side in ((-1.0, "port"), (1.0, "starboard")):
        parts.append(_lab(Box(2100, 600, 800).locate(
            Location((sx * CORE_PITCH / 2, 0, Z_BOOSTER_TOP - 900))),
            f"{side}_nose_attach_block__schematic__no_internals", COL_METAL))
        for j, z in enumerate((3300.0, 4600.0)):
            parts.append(_lab(
                Cylinder(radius=140, height=1900, rotation=(0, 90, 0)).locate(
                    Location((sx * CORE_PITCH / 2, 0, z))),
                f"{side}_aft_attach_strut_{j + 1}__schematic__no_internals", COL_METAL))
    return _grp("booster_attachment_group", parts)


# ---------------------------------------------------------------------------
# Second stage + fairing
# ---------------------------------------------------------------------------


def make_second_stage(arc=360.0, start=0.0, sectioned=False) -> Compound:
    parts = [make_mvac().moved(Location((0, 0, 43200.0)))]
    parts[0].label = "mvac_engine__linked_derivative_schematic"
    if sectioned:
        shell = eng.revolved_solid(
            [(CORE_R - 40, Z_INTER_TOP), (CORE_R, Z_INTER_TOP),
             (CORE_R, Z_S2_TOP), (CORE_R - 40, Z_S2_TOP)],
            "second_stage_barrel__white__photogrammetric", COL_WHITE, arc, start)
        parts.append(shell)
    else:
        parts.append(_tube_z(0, 0, Z_INTER_TOP, Z_S2_TOP, CORE_R,
                             "second_stage_barrel__white__photogrammetric", COL_WHITE))
    parts.append(_tube_z(0, 0, Z_S2_TOP - 7000, Z_S2_TOP - 6800, CORE_R + 15,
                         "s2_tank_band__decorative", COL_SOOT, hollow_t=15.0))
    parts.append(_lab(Box(150, 120, 7400).locate(
        Location((CORE_R + 50, 300, Z_S2_TOP - 3800))),
        "s2_raceway__photogrammetric", COL_WHITE))
    return _grp("second_stage_group", parts)


def make_fairing(arc=360.0, start=0.0, sectioned=False) -> Compound:
    z0 = Z_S2_TOP - 200.0
    zc = z0 + 6500.0
    profile = [(CORE_R, z0), (FAIRING_R, z0 + 2500.0), (FAIRING_R, zc)] + [
        (FAIRING_R * (1 - (t / 8.0) ** 1.7) + 250.0 * (t / 8.0) ** 1.7,
         zc + (VEHICLE_H - zc) * t / 8.0) for t in range(1, 9)
    ]
    a_used = arc if sectioned else 360.0
    s_used = start if sectioned else 0.0
    shell = eng.revolved_shell(profile, 60.0,
                               "fairing_shell__composite__published_envelope",
                               COL_WHITE, a_used, s_used)
    parts = [shell]
    for az in (90.0, 270.0):
        a = radians(az)
        parts.append(_lab(
            Box(120, 90, VEHICLE_H - z0 - 3000).locate(Location(
                ((FAIRING_R - 10) * cos(a), (FAIRING_R - 10) * sin(a),
                 z0 + (VEHICLE_H - z0) / 2 - 800), (0, 0, az))),
            f"fairing_half_seam_{int(az)}deg__photogrammetric", COL_SOOT))
    parts.append(_tube_z(0, 0, z0, z0 + 350, FAIRING_R + 20,
                         "fairing_base_ring__schematic", COL_SOOT, hollow_t=25.0))
    return _grp("payload_fairing_group", parts)


# ---------------------------------------------------------------------------
# Schematic interiors (cutaway entry only)
# ---------------------------------------------------------------------------


def build_center_interior() -> list[Compound]:
    parts = [
        _tube_z(0, 0, 3000.0, Z_RP1_TOP - 300, CORE_R - 90,
                "s1_rp1_tank_volume__schematic_nonfunctional", COL_RP1),
        _tube_z(0, 0, Z_LOX_BOT + 300, Z_BOOSTER_TOP - 900, CORE_R - 90,
                "s1_lox_tank_volume__schematic_nonfunctional", COL_LOX),
        _tube_z(0, 0, 3000.0, Z_LOX_BOT + 300, 260.0,
                "lox_transfer_tube__simplified_schematic", COL_LOX),
        _dome(0, 0, Z_RP1_TOP - 300, CORE_R - 90, +1,
              "s1_common_dome__schematic", COL_GRAY),
        _dome(0, 0, Z_BOOSTER_TOP - 900, CORE_R - 90, +1,
              "s1_lox_forward_dome__schematic", COL_GRAY),
    ]
    for i in range(4):
        a = radians(45 + i * 90)
        parts.append(_lab(
            Cylinder(radius=280, height=1600).locate(
                Location((1150 * cos(a), 1150 * sin(a), 19500.0))),
            f"copv_helium_bottle_{i + 1}__supported_placeholder__nonfunctional",
            COL_GRAY))
    for i in range(8):
        a = radians(i * 45)
        parts.append(_lab(
            Box(1050, 160, 1500).locate(
                Location((760 * cos(a), 760 * sin(a), 1900.0), (0, 0, i * 45))),
            f"octaweb_radial_frame_{i + 1}__schematic", COL_METAL))
    parts.extend([
        _tube_z(0, 0, 49000.0, 52500.0, CORE_R - 110,
                "s2_lox_tank_volume__schematic_nonfunctional", COL_LOX),
        _tube_z(0, 0, 53000.0, Z_S2_TOP - 500, CORE_R - 110,
                "s2_rp1_tank_volume__schematic_nonfunctional", COL_RP1),
        eng.revolved_solid(
            [(0.001, Z_S2_TOP + 100), (900.0, Z_S2_TOP + 100), (420.0, Z_S2_TOP + 1800),
             (0.001, Z_S2_TOP + 1800)],
            "payload_adapter_cone__schematic_placeholder", COL_GRAY),
        _lab(Box(2100, 2100, 3200).locate(Location((0, 0, Z_S2_TOP + 3600))),
             "payload_placeholder__educational", COL_GRAY),
        _lab(Box(900, 700, 500).locate(Location((0, -700, Z_INTER_TOP - 2500))),
             "separation_interface_block__schematic__no_internals", COL_GRAY),
    ])
    return [_grp("schematic_interior_group", parts)]


# ---------------------------------------------------------------------------
# Full vehicle
# ---------------------------------------------------------------------------


def build_vehicle(cutaway: bool = False) -> list[Compound]:
    arc, start = (CUT_ARC, CUT_START) if cutaway else (360.0, 0.0)
    groups = []
    groups += [ _grp("center_core_group",
                     make_booster(0.0, "core", True, arc, start, sectioned=cutaway)) ]
    groups += [ _grp("port_booster_group", make_booster(-CORE_PITCH, "port", False)) ]
    groups += [ _grp("starboard_booster_group", make_booster(CORE_PITCH, "stbd", False)) ]
    groups.append(make_attachments())
    groups.append(make_second_stage(arc, start, sectioned=cutaway))
    groups.append(make_fairing(arc, start, sectioned=cutaway))
    if cutaway:
        groups += build_center_interior()
    return groups
