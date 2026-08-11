"""Shared geometry library for the SpaceX Raptor 2 educational reconstruction.

DISCLAIMER: Educational, non-functional public-source reconstruction. Not
suitable for manufacture, propulsion, testing, or operational engineering.

All geometry here is either scaled from publicly stated envelope dimensions or
is a photogrammetric/schematic estimate from public photographs. No proprietary
detail is modeled: no injector elements, no turbopump internals, no cooling
channel geometry, no wall thicknesses (shell thicknesses are decorative), no
valve internals. Hidden internals are simplified placeholder volumes labeled
"schematic".

Coordinates: engine centerline = Z axis, nozzle exit plane = Z=0, engine body
extends toward +Z, thrust acts along -Z. Units: millimeters, full scale.

Provenance summary (see PROVENANCE.md for the full per-component table):
- Engine height 3100 mm and envelope diameter 1300 mm: SpaceX published
  figures for Raptor (Raptor 3 announcement, raptor family pages). HIGH.
- Sea-level expansion ratio ~34-40, throat ~= exit_dia/sqrt(eps): community
  photogrammetric estimates (Everyday Astronaut, Wikipedia-indexed refs). LOW.
- Powerhead layout (twin vertical turbopumps flanking the chamber, preburners
  on top, gimbal at top center): visible in public SpaceX photos. MEDIUM,
  photogrammetric estimate.
"""

from __future__ import annotations

from math import cos, radians, sin, sqrt

from build123d import (
    Axis,
    Box,
    Circle,
    Color,
    Compound,
    Cylinder,
    Edge,
    Face,
    Location,
    Plane,
    Sphere,
    Torus,
    Vector,
    Wire,
    extrude,
    revolve,
    sweep,
)

DISPLAY_NAME = "SpaceX Raptor 2 sea-level engine (educational public-source reconstruction)"

# ---------------------------------------------------------------------------
# Published / estimated parameters (mm). Confidence noted per value.
# ---------------------------------------------------------------------------

ENGINE_HEIGHT = 3100.0        # SpaceX: Raptor height 3.1 m. HIGH (published)
EXIT_DIAMETER = 1300.0        # SpaceX: Raptor diameter 1.3 m. HIGH (published)
EXIT_RADIUS = EXIT_DIAMETER / 2.0

# Raptor 2 widened the throat at constant exit diameter (Everyday Astronaut
# comparison). FAA plume analysis gives eps=34.34 for the Raptor-1-era engine;
# community-derived Raptor 2 throat estimates cluster ~235-250 mm. We model
# 240 mm dia => effective eps ~29.3. Photogrammetric/community estimate. LOW
THROAT_RADIUS = 120.0
EXPANSION_RATIO = (EXIT_RADIUS / THROAT_RADIUS) ** 2  # ~29.3 effective. LOW

BELL_LENGTH = 1560.0          # photogrammetric estimate (~50% of height). LOW
Z_THROAT = BELL_LENGTH        # throat plane
THETA_N_DEG = 33.0            # Rao 80% bell initial angle, textbook value. schematic
THETA_E_DEG = 8.0             # Rao bell exit angle, textbook value. schematic

CHAMBER_RADIUS = 235.0        # photogrammetric estimate. LOW
Z_CHAMBER_TOP = 2160.0        # injector face plane, photogrammetric estimate. LOW

INNER_SHELL_T = 8.0           # decorative shell thickness (NOT engineering data)
JACKET_T = 12.0               # decorative jacket thickness (NOT engineering data)
WALL_T = INNER_SHELL_T + JACKET_T

Z_HEAD_TOP = 2395.0           # injector head dome apex. schematic
Z_CONE_TOP = 2700.0           # thrust cone top. photogrammetric estimate
Z_GIMBAL_TOP = 2840.0
Z_PLATE_TOP = 2880.0

PUMP_X = 430.0                # turbopump centerline offset. photogrammetric LOW
PUMP_RADIUS = 170.0
PUMP_Z0, PUMP_Z1 = 1700.0, 2450.0
PREBURNER_R = 170.0           # placeholder dome radius. schematic

INLET_PIPE_R = 110.0
Z_INLET_TOP = 3078.0
Z_FLANGE_TOP = ENGINE_HEIGHT  # vehicle interface flange top = published height

MANIFOLD_Z = 450.0            # nozzle fuel manifold ring height. photogrammetric LOW

# --- Raptor Vacuum (RVac) derived variant ------------------------------------
# Same powerhead as the sea-level engine (publicly stated family architecture);
# the nozzle extends to a vacuum expansion ratio of ~80 (Musk statement via the
# Everyday Astronaut Starbase interview, MEDIUM confidence). Exit radius and
# bell length derive from that ratio with the same Rao 80% approximation used
# for the sea-level bell — geometry status: schematic.
VAC_EXPANSION_RATIO = 80.0
VAC_EXIT_RADIUS = THROAT_RADIUS * sqrt(VAC_EXPANSION_RATIO)   # ~1073 mm. LOW
VAC_THETA_E_DEG = 5.0         # Rao exit angle for a high-ratio bell. schematic
VAC_BELL_LENGTH = 2850.0      # Rao 80% length for eps=80. schematic
VAC_DROP = VAC_BELL_LENGTH - BELL_LENGTH  # vac exit extension below the SL exit
VAC_ENGINE_HEIGHT = ENGINE_HEIGHT + VAC_DROP  # ~4390 mm; public estimates ~4.6 m. LOW

CUT_START_DEG = 135.0         # cutaway keeps material 135..405 deg, opening faces +Y
CUT_ARC_DEG = 270.0
# schematic interior volumes recess 2 deg inside the shell section faces so
# cross-sections read cleanly with no coplanar z-fighting
CUT_INNER_START_DEG = 137.0
CUT_INNER_ARC_DEG = 266.0

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

COL_BELL_OUTER = Color(0.58, 0.60, 0.63, 1.0)     # neutral steel
COL_BELL_INNER = Color(0.12, 0.12, 0.14, 1.0)     # dark nozzle interior
COL_CHAMBER = Color(0.56, 0.53, 0.49, 1.0)        # warm alloy
COL_HEAD = Color(0.62, 0.64, 0.66, 1.0)
COL_STRUCT = Color(0.44, 0.46, 0.50, 1.0)
COL_PUMP = Color(0.66, 0.68, 0.70, 1.0)
COL_DUCT = Color(0.60, 0.62, 0.65, 1.0)
COL_VALVE = Color(0.33, 0.35, 0.38, 1.0)
COL_HARNESS = Color(0.19, 0.20, 0.21, 1.0)
COL_TINT_STRAW = Color(0.62, 0.50, 0.34, 1.0)     # restrained heat tint bands
COL_TINT_BRONZE = Color(0.48, 0.38, 0.42, 1.0)
COL_TINT_BLUE = Color(0.38, 0.44, 0.54, 1.0)

# schematic flow-path palette (translucent)
COL_LOX = Color(0.20, 0.45, 0.95, 0.60)           # LOX / oxygen-rich = blue
COL_CH4 = Color(0.15, 0.75, 0.40, 0.60)           # methane / fuel-rich = green
COL_HOT = Color(0.95, 0.42, 0.12, 0.55)           # hot gas / combustion
COL_REGEN = Color(0.15, 0.75, 0.40, 0.35)         # regen band, faint green
COL_UNKNOWN = Color(0.62, 0.62, 0.68, 0.35)       # inferred / placeholder gray
COL_INJECTOR = Color(0.70, 0.70, 0.72, 0.60)      # schematic injector disk


def _label(part, label: str, color: Color | None = None):
    part.label = label
    if color is not None:
        part.color = color
    return part


def _group(label: str, parts: list) -> Compound:
    return Compound(obj=parts, children=parts, label=label)


# ---------------------------------------------------------------------------
# Nozzle contour (Rao 80% parabolic approximation -- textbook method, not
# SpaceX data; geometry status: schematic scaled to published envelope)
# ---------------------------------------------------------------------------


def _bezier_ctrl(
    exit_radius: float = EXIT_RADIUS,
    bell_length: float = BELL_LENGTH,
    theta_n_deg: float = THETA_N_DEG,
    theta_e_deg: float = THETA_E_DEG,
):
    tn, te = radians(theta_n_deg), radians(theta_e_deg)
    arc_r = 0.382 * THROAT_RADIUS
    z0 = arc_r * sin(tn)                              # downstream dist of arc end
    r0 = THROAT_RADIUS + arc_r * (1.0 - cos(tn))
    z2, r2 = bell_length, exit_radius
    # intersection of tangents from P0 (slope tan tn) and P2 (slope tan te)
    from math import tan

    m0, m2 = tan(tn), tan(te)
    z1 = (r2 - r0 + m0 * z0 - m2 * z2) / (m0 - m2)
    r1 = r0 + m0 * (z1 - z0)
    return (z0, r0), (z1, r1), (z2, r2)


def bell_gas_contour(
    samples: int = 30,
    *,
    exit_radius: float = EXIT_RADIUS,
    bell_length: float = BELL_LENGTH,
    theta_n_deg: float = THETA_N_DEG,
    theta_e_deg: float = THETA_E_DEG,
) -> list[tuple[float, float]]:
    """(r, z) points from throat (z=Z_THROAT) down to exit (z=Z_THROAT-bell_length)."""
    tn = radians(theta_n_deg)
    arc_r = 0.382 * THROAT_RADIUS
    pts: list[tuple[float, float]] = []
    n_arc = 6
    for i in range(n_arc + 1):
        a = tn * i / n_arc
        zd = arc_r * sin(a)
        r = THROAT_RADIUS + arc_r * (1.0 - cos(a))
        pts.append((r, Z_THROAT - zd))
    (z0, r0), (z1, r1), (z2, r2) = _bezier_ctrl(
        exit_radius, bell_length, theta_n_deg, theta_e_deg
    )
    for i in range(1, samples + 1):
        t = i / samples
        zd = (1 - t) ** 2 * z0 + 2 * (1 - t) * t * z1 + t**2 * z2
        r = (1 - t) ** 2 * r0 + 2 * (1 - t) * t * r1 + t**2 * r2
        pts.append((r, Z_THROAT - zd))
    return pts


def vac_bell_gas_contour(samples: int = 40) -> list[tuple[float, float]]:
    """RVac (r, z) contour from throat down to the vacuum exit plane."""
    return bell_gas_contour(
        samples,
        exit_radius=VAC_EXIT_RADIUS,
        bell_length=VAC_BELL_LENGTH,
        theta_e_deg=VAC_THETA_E_DEG,
    )


def chamber_gas_contour() -> list[tuple[float, float]]:
    """(r, z) from throat (z=Z_THROAT) up to the injector face plane."""
    pts = [(THROAT_RADIUS, Z_THROAT)]
    # upstream blend arc then taper to the cylindrical chamber barrel
    blend = [
        (THROAT_RADIUS + 4.0, Z_THROAT + 40.0),
        (THROAT_RADIUS + 35.0, Z_THROAT + 110.0),
        (150.0, 1720.0),
        (196.0, 1790.0),
        (226.0, 1855.0),
        (CHAMBER_RADIUS, 1920.0),
    ]
    pts.extend(blend)
    pts.append((CHAMBER_RADIUS, Z_CHAMBER_TOP))
    return pts


_BELL_SAMPLED = None
_VAC_BELL_SAMPLED = None


def _radius_from_samples(pts: list[tuple[float, float]], z: float) -> float:
    if z <= pts[0][1]:
        return pts[0][0]
    for (r_a, z_a), (r_b, z_b) in zip(pts, pts[1:]):
        if z_a <= z <= z_b:
            f = (z - z_a) / (z_b - z_a) if z_b > z_a else 0.0
            return r_a + (r_b - r_a) * f
    return pts[-1][0]


def bell_radius_at(z: float) -> float:
    """Gas-side bell radius at height z (0..Z_THROAT), linear interp."""
    global _BELL_SAMPLED
    if _BELL_SAMPLED is None:
        _BELL_SAMPLED = sorted(bell_gas_contour(samples=200), key=lambda p: p[1])
    return _radius_from_samples(_BELL_SAMPLED, z)


def vac_bell_radius_at(z: float) -> float:
    """RVac gas-side bell radius at height z (Z_THROAT-VAC_BELL_LENGTH..Z_THROAT)."""
    global _VAC_BELL_SAMPLED
    if _VAC_BELL_SAMPLED is None:
        _VAC_BELL_SAMPLED = sorted(vac_bell_gas_contour(samples=200), key=lambda p: p[1])
    return _radius_from_samples(_VAC_BELL_SAMPLED, z)


# ---------------------------------------------------------------------------
# Revolve / sweep helpers
# ---------------------------------------------------------------------------


def _profile_face(inner_pts: list[tuple[float, float]], thickness: float) -> Face:
    inner = [Vector(r, 0, z) for r, z in inner_pts]
    outer = [Vector(r + thickness, 0, z) for r, z in reversed(inner_pts)]
    edges = [
        Edge.make_spline(inner),
        Edge.make_line(inner[-1], outer[0]),
        Edge.make_spline(outer),
        Edge.make_line(outer[-1], inner[0]),
    ]
    return Face(Wire(edges))


def revolved_shell(
    inner_pts: list[tuple[float, float]],
    thickness: float,
    label: str,
    color: Color,
    arc_deg: float = 360.0,
    start_deg: float = 0.0,
):
    part = revolve(_profile_face(inner_pts, thickness), axis=Axis.Z, revolution_arc=arc_deg)
    if start_deg:
        part = part.rotate(Axis.Z, start_deg)
    return _label(part, label, color)


def revolved_solid(
    outline: list[tuple[float, float]],
    label: str,
    color: Color,
    arc_deg: float = 360.0,
    start_deg: float = 0.0,
    spline: bool = False,
):
    """Revolve a closed (r,z) outline (first/last on or off axis, closed by lines)."""
    pts3 = [Vector(r, 0, z) for r, z in outline]
    if spline:
        edges = [Edge.make_spline(pts3)]
    else:
        edges = [Edge.make_line(a, b) for a, b in zip(pts3, pts3[1:])]
    edges.append(Edge.make_line(pts3[-1], pts3[0]))
    part = revolve(Face(Wire(edges)), axis=Axis.Z, revolution_arc=arc_deg)
    if start_deg:
        part = part.rotate(Axis.Z, start_deg)
    return _label(part, label, color)


def tube(points: list[tuple[float, float, float]], radius: float, label: str, color: Color):
    path = Edge.make_spline([Vector(*p) for p in points])
    section = Plane(origin=path.position_at(0), z_dir=path.tangent_at(0)) * Circle(radius)
    part = sweep(section, path=path)
    return _label(part, label, color)


def _cyl_z(x: float, y: float, z0: float, z1: float, r: float, label: str, color: Color):
    part = Cylinder(radius=r, height=z1 - z0).locate(Location((x, y, (z0 + z1) / 2.0)))
    return _label(part, label, color)


# ---------------------------------------------------------------------------
# Exterior component groups
# ---------------------------------------------------------------------------


def make_nozzle_group(arc_deg: float = 360.0, start_deg: float = 0.0) -> Compound:
    gas = bell_gas_contour()
    parts = [
        revolved_shell(
            gas, INNER_SHELL_T,
            "nozzle_bell_inner_liner__dark_interior__decorative_thickness",
            COL_BELL_INNER, arc_deg, start_deg,
        ),
        revolved_shell(
            [(r + INNER_SHELL_T, z) for r, z in gas], JACKET_T,
            "nozzle_bell_regen_jacket__smooth_exterior__photogrammetric",
            COL_BELL_OUTER, arc_deg, start_deg,
        ),
    ]
    # restrained heat-tint sleeves just below the throat (decorative)
    bands = [
        (1400.0, 1525.0, COL_TINT_STRAW, "straw"),
        (1280.0, 1400.0, COL_TINT_BRONZE, "bronze"),
        (1160.0, 1280.0, COL_TINT_BLUE, "blue"),
    ]
    for z_lo, z_hi, col, name in bands:
        pts = [
            (bell_radius_at(z_lo + (z_hi - z_lo) * i / 5.0) + WALL_T + 0.5,
             z_lo + (z_hi - z_lo) * i / 5.0)
            for i in range(6)
        ]
        parts.append(
            revolved_shell(
                pts, 2.5,
                f"heat_tint_band_{name}__decorative", col, arc_deg, start_deg,
            )
        )
    # exit stiffener lip
    lip = Torus(major_radius=EXIT_RADIUS + WALL_T / 2.0 + 4.0, minor_radius=14.0,
                major_angle=arc_deg)
    lip = lip.rotate(Axis.Z, start_deg).locate(
        Location((0, 0, 14.5), (0, 0, start_deg))
    )
    parts.append(_label(lip, "nozzle_exit_stiffener_ring__photogrammetric", COL_BELL_OUTER))
    # fuel manifold ring + twin downcomers on the fuel (-X) side
    ring_r = bell_radius_at(MANIFOLD_Z) + WALL_T + 18.0
    manifold = Torus(major_radius=ring_r, minor_radius=32.0, major_angle=arc_deg)
    manifold = manifold.locate(Location((0, 0, MANIFOLD_Z), (0, 0, start_deg)))
    parts.append(
        _label(manifold, "nozzle_fuel_manifold_ring__schematic_routing", COL_DUCT)
    )
    return _group("nozzle_bell_group", parts)


def make_vacuum_nozzle_group(arc_deg: float = 360.0, start_deg: float = 0.0) -> Compound:
    """RVac extended bell: same throat, eps~80 exit, vacuum exit below Z=0."""
    gas = vac_bell_gas_contour()
    exit_z = Z_THROAT - VAC_BELL_LENGTH
    parts = [
        revolved_shell(
            gas, INNER_SHELL_T,
            "rvac_nozzle_inner_liner__dark_interior__decorative_thickness",
            COL_BELL_INNER, arc_deg, start_deg,
        ),
        revolved_shell(
            [(r + INNER_SHELL_T, z) for r, z in gas], JACKET_T,
            "rvac_nozzle_regen_jacket__smooth_exterior__schematic",
            COL_BELL_OUTER, arc_deg, start_deg,
        ),
    ]
    # single restrained heat-tint band below the throat (decorative)
    band = [
        (vac_bell_radius_at(1330.0 + 190.0 * i / 5.0) + WALL_T + 0.5,
         1330.0 + 190.0 * i / 5.0)
        for i in range(6)
    ]
    parts.append(
        revolved_shell(band, 2.5, "rvac_heat_tint_band_straw__decorative",
                       COL_TINT_STRAW, arc_deg, start_deg)
    )
    # nozzle extension seam ring (visible jacket transition on public photos)
    seam_z = Z_THROAT - 1150.0
    seam = Torus(
        major_radius=vac_bell_radius_at(seam_z) + WALL_T + 3.0,
        minor_radius=10.0, major_angle=arc_deg,
    ).locate(Location((0, 0, seam_z), (0, 0, start_deg)))
    parts.append(_label(seam, "rvac_nozzle_extension_seam_ring__photogrammetric", COL_DUCT))
    # exit stiffener lip
    lip = Torus(
        major_radius=VAC_EXIT_RADIUS + WALL_T / 2.0 + 4.0,
        minor_radius=16.0, major_angle=arc_deg,
    ).locate(Location((0, 0, exit_z + 16.5), (0, 0, start_deg)))
    parts.append(_label(lip, "rvac_exit_stiffener_ring__photogrammetric", COL_BELL_OUTER))
    # fuel manifold ring on the wider vac bell
    ring_r = vac_bell_radius_at(MANIFOLD_Z) + WALL_T + 18.0
    manifold = Torus(major_radius=ring_r, minor_radius=32.0, major_angle=arc_deg)
    manifold = manifold.locate(Location((0, 0, MANIFOLD_Z), (0, 0, start_deg)))
    parts.append(_label(manifold, "rvac_fuel_manifold_ring__schematic_routing", COL_DUCT))
    return _group("rvac_nozzle_bell_group", parts)


def make_chamber_group(arc_deg: float = 360.0, start_deg: float = 0.0) -> Compound:
    gas = chamber_gas_contour()
    parts = [
        revolved_shell(
            gas, INNER_SHELL_T,
            "chamber_inner_liner__dark_interior__decorative_thickness",
            COL_BELL_INNER, arc_deg, start_deg,
        ),
        revolved_shell(
            [(r + INNER_SHELL_T, z) for r, z in gas], JACKET_T,
            "combustion_chamber_envelope__photogrammetric",
            COL_CHAMBER, arc_deg, start_deg,
        ),
        # dark cap so the view up the nozzle ends in shadow, not bare head metal
        revolved_solid(
            [(0.0, Z_CHAMBER_TOP - 3.0), (CHAMBER_RADIUS - 0.5, Z_CHAMBER_TOP - 3.0),
             (CHAMBER_RADIUS - 0.5, Z_CHAMBER_TOP), (0.0, Z_CHAMBER_TOP)],
            "chamber_interior_cap__decorative", COL_BELL_INNER, arc_deg, start_deg,
        ),
    ]
    return _group("chamber_group", parts)


def make_injector_head(arc_deg: float = 360.0, start_deg: float = 0.0):
    outline = [
        (0.0, Z_CHAMBER_TOP),
        (CHAMBER_RADIUS + WALL_T, Z_CHAMBER_TOP),
        (CHAMBER_RADIUS + WALL_T, Z_CHAMBER_TOP + 55.0),
        (238.0, 2290.0),
        (180.0, 2350.0),
        (95.0, 2385.0),
        (0.0, Z_HEAD_TOP),
    ]
    pts3 = [Vector(r, 0, z) for r, z in outline]
    edges = [
        Edge.make_line(pts3[0], pts3[1]),
        Edge.make_line(pts3[1], pts3[2]),
        Edge.make_spline(pts3[2:]),
        Edge.make_line(pts3[-1], pts3[0]),
    ]
    part = revolve(Face(Wire(edges)), axis=Axis.Z, revolution_arc=arc_deg)
    if start_deg:
        part = part.rotate(Axis.Z, start_deg)
    return _label(part, "injector_head_dome__exterior_only__no_element_detail", COL_HEAD)


def make_thrust_structure(arc_deg: float = 360.0, start_deg: float = 0.0) -> Compound:
    cone = revolved_solid(
        [(0.0, 2360.0), (238.0, 2360.0), (150.0, Z_CONE_TOP), (0.0, Z_CONE_TOP)],
        "thrust_cone__photogrammetric", COL_STRUCT, arc_deg, start_deg,
    )
    parts = [cone]
    # four rib gussets following the cone slope
    for az in (45.0, 135.0, 225.0, 315.0):
        tri = Face(
            Wire(
                [
                    Edge.make_line(Vector(140, 0, 2700), Vector(240, 0, 2365)),
                    Edge.make_line(Vector(240, 0, 2365), Vector(140, 0, 2365)),
                    Edge.make_line(Vector(140, 0, 2365), Vector(140, 0, 2700)),
                ]
            )
        )
        plate = extrude(tri, amount=11.0, both=True)
        parts.append(
            _label(plate.rotate(Axis.Z, az), f"thrust_cone_gusset_{int(az)}deg__schematic", COL_STRUCT)
        )
    return _group("thrust_structure_group", parts)


def make_gimbal_group() -> Compound:
    parts = [
        _label(
            Box(300, 300, 140).locate(Location((0, 0, 2770))),
            "gimbal_block__simplified_exterior", COL_STRUCT,
        ),
        _label(
            Cylinder(radius=45, height=400, rotation=(0, 90, 0)).locate(Location((0, 0, 2770))),
            "gimbal_cross_pin_x__simplified", COL_STRUCT,
        ),
        _label(
            Cylinder(radius=45, height=400, rotation=(90, 0, 0)).locate(Location((0, 0, 2770))),
            "gimbal_cross_pin_y__simplified", COL_STRUCT,
        ),
        _label(
            Box(380, 380, 40).locate(Location((0, 0, 2860))),
            "vehicle_mount_plate__simplified", COL_STRUCT,
        ),
    ]
    for ex in (-170.0, 170.0):
        parts.append(
            _label(
                Box(40, 150, 170).locate(Location((ex, 0, 2765))),
                f"gimbal_ear_x{int(ex)}__simplified", COL_STRUCT,
            )
        )
    for why in (-170.0, 170.0):
        parts.append(
            _label(
                Box(150, 40, 170).locate(Location((0, why, 2765))),
                f"gimbal_ear_y{int(why)}__simplified", COL_STRUCT,
            )
        )
    for bx in (-150.0, 150.0):
        for by in (-150.0, 150.0):
            parts.append(
                _label(
                    Cylinder(radius=32, height=58).locate(Location((bx, by, 2909))),
                    f"mount_boss_{int(bx)}_{int(by)}__simplified", COL_STRUCT,
                )
            )
    return _group("gimbal_mount_group", parts)


def _make_turbopump_side(
    sign: int, propellant: str, section: bool = False, bell_r_fn=bell_radius_at
) -> Compound:
    """sign=+1 -> +X oxygen side, sign=-1 -> -X methane side.

    With section=True the housing and preburner dome are quarter-sectioned
    about their own vertical axis (opening faces +Y, matching the cutaway)
    so the schematic placeholder volumes inside become visible.
    """
    x = sign * PUMP_X
    tag = "ox" if propellant == "lox" else "fuel"
    if section:
        housing = revolved_solid(
            [(0.0, PUMP_Z0), (PUMP_RADIUS, PUMP_Z0), (PUMP_RADIUS, PUMP_Z1), (0.0, PUMP_Z1)],
            f"{tag}_turbopump_housing__exterior_placeholder__no_internals",
            COL_PUMP, CUT_ARC_DEG, CUT_START_DEG,
        ).moved(Location((x, 0, 0)))
        dome_outline = [(0.001, PUMP_Z1 - PREBURNER_R)] + [
            (PREBURNER_R * sin(radians(a)), PUMP_Z1 - PREBURNER_R * cos(radians(a)))
            for a in range(15, 180, 15)
        ] + [(0.001, PUMP_Z1 + PREBURNER_R)]
        dome = revolved_solid(
            dome_outline,
            f"{tag}_preburner_dome__exterior_placeholder__no_internals",
            COL_PUMP, CUT_ARC_DEG, CUT_START_DEG, spline=True,
        ).moved(Location((x, 0, 0)))
        housing.label = f"{tag}_turbopump_housing__exterior_placeholder__no_internals"
        dome.label = f"{tag}_preburner_dome__exterior_placeholder__no_internals"
        pump_shell_parts = [housing, dome]
    else:
        pump_shell_parts = [
            _cyl_z(x, 0, PUMP_Z0, PUMP_Z1, PUMP_RADIUS,
                   f"{tag}_turbopump_housing__exterior_placeholder__no_internals", COL_PUMP),
            _label(
                Sphere(radius=PREBURNER_R).locate(Location((x, 0, PUMP_Z1))),
                f"{tag}_preburner_dome__exterior_placeholder__no_internals", COL_PUMP,
            ),
        ]
    parts = [
        *pump_shell_parts,
        _label(
            Torus(major_radius=128, minor_radius=62).locate(Location((x, 0, 1735))),
            f"{tag}_pump_volute__simplified_exterior", COL_DUCT,
        ),
        # vertical propellant inlet from the vehicle interface into the pump top
        _cyl_z(x, 0, 2560.0, Z_INLET_TOP, INLET_PIPE_R,
               f"{propellant}_main_inlet_pipe__photogrammetric", COL_DUCT),
        _label(
            Cylinder(radius=163, height=22).locate(Location((x, 0, 3089.0))),
            f"{propellant}_vehicle_interface_flange__simplified", COL_STRUCT,
        ),
        # main valve housing around the inlet pipe with a side actuator stub
        _label(
            Box(250, 210, 170).locate(Location((x, 0, 2760))),
            f"{propellant}_main_valve_housing__schematic__no_internals", COL_VALVE,
        ),
        _label(
            Cylinder(radius=42, height=170, rotation=(90, 0, 0)).locate(
                Location((x, 105 + 85, 2760))
            ),
            f"{propellant}_valve_actuator_housing__schematic", COL_VALVE,
        ),
        # hot preburner-gas duct curving inboard into the injector head
        tube(
            [(sign * 260, 0, 2520), (sign * 235, 0, 2440), (sign * 215, 0, 2370),
             (sign * 185, 0, 2310)],
            88.0,
            f"{tag}_preburner_exhaust_duct__schematic_routing", COL_DUCT,
        ),
        # flange collar where the duct meets the head
        _label(
            Cylinder(radius=108, height=26, rotation=(0, 35 * sign, 0)).locate(
                Location((sign * 190, 0, 2315))
            ),
            f"{tag}_duct_head_flange__simplified", COL_DUCT,
        ),
    ]
    if propellant == "lox":
        parts.append(
            tube(
                [(400, 0, 1725), (330, 0, 1840), (275, 0, 2010), (247, 0, 2150)],
                70.0, "lox_main_feed_duct__schematic_routing", COL_DUCT,
            )
        )
    else:
        ring_r = bell_r_fn(MANIFOLD_Z) + WALL_T + 18.0
        mid1 = 400.0 + (ring_r - 400.0) * 0.72
        mid2 = ring_r * 0.985
        for az in (-22.0, 22.0):
            a = radians(az)
            parts.append(
                tube(
                    [
                        (-400 * cos(a), 400 * sin(a), 1720),
                        (-mid1 * cos(a), mid1 * sin(a), 1320),
                        (-mid2 * cos(a), mid2 * sin(a), 850),
                        (-ring_r * cos(a), ring_r * sin(a), MANIFOLD_Z + 40),
                    ],
                    55.0,
                    f"ch4_regen_downcomer_{'a' if az < 0 else 'b'}__schematic_routing",
                    COL_DUCT,
                )
            )
    return _group(f"{tag}_turbopump_group", parts)


def make_powerhead_groups(section: bool = False, bell_r_fn=bell_radius_at) -> list[Compound]:
    return [
        _make_turbopump_side(+1, "lox", section=section, bell_r_fn=bell_r_fn),
        _make_turbopump_side(-1, "ch4", section=section, bell_r_fn=bell_r_fn),
    ]


def make_tvc_group() -> Compound:
    parts = []
    for az in (60.0, 120.0):
        a = radians(az)
        r_mount = 208.0
        px, py = r_mount * cos(a), r_mount * sin(a)
        clevis = Box(100, 44, 120).locate(Location((px, py, 2530), (0, 0, az)))
        parts.append(_label(clevis, f"tvc_clevis_bracket_{int(az)}deg__photogrammetric", COL_STRUCT))
        pin = Cylinder(radius=16, height=90, rotation=(0, 90, 0)).locate(
            Location((px, py, 2530), (0, 0, az + 90))
        )
        parts.append(_label(pin, f"tvc_pin_{int(az)}deg__simplified", COL_HARNESS))
        housing = Cylinder(radius=40, height=230)
        housing = housing.locate(
            Location(
                (cos(a) * (r_mount + 95), sin(a) * (r_mount + 95), 2620),
                (55 * sin(a), 55 * -cos(a) * -1, 0),
            )
        )
        parts.append(
            _label(housing, f"tvc_actuator_housing_{int(az)}deg__schematic", COL_VALVE)
        )
    return _group("tvc_actuator_group", parts)


def make_avionics_group() -> Compound:
    parts = [
        _label(
            Box(260, 150, 420).locate(Location((0, -335, 2350))),
            "engine_controller_enclosure__photogrammetric_placeholder", COL_VALVE,
        )
    ]
    for az, z0, z1 in ((205.0, 2380.0, 1830.0), (335.0, 2380.0, 1830.0)):
        a = radians(az)
        pts = [
            (252 * cos(a), 252 * sin(a), z0),
            (250 * cos(a), 250 * sin(a), (z0 + z1) / 2 + 60),
            (248 * cos(a), 248 * sin(a), z1),
        ]
        parts.append(
            tube(pts, 12.0, f"harness_conduit_{int(az)}deg__decorative", COL_HARNESS)
        )
    return _group("avionics_harness_group", parts)


def build_exterior(
    arc_deg: float = 360.0, start_deg: float = 0.0, section_pumps: bool = False
) -> list[Compound]:
    """All exterior groups; arc/start section the axisymmetric shells only."""
    groups = [
        make_nozzle_group(arc_deg, start_deg),
        make_chamber_group(arc_deg, start_deg),
        _group("injector_head_group", [make_injector_head(arc_deg, start_deg)]),
        make_thrust_structure(arc_deg, start_deg),
        make_gimbal_group(),
        *make_powerhead_groups(section=section_pumps),
        make_tvc_group(),
        make_avionics_group(),
    ]
    return groups


def build_vacuum_exterior() -> list[Compound]:
    """RVac derived variant: sea-level powerhead + eps~80 extended bell.

    The whole engine is translated up by VAC_DROP so the vacuum exit plane sits
    at Z=0 (engine spans Z=0..VAC_ENGINE_HEIGHT). The real RVac is fixed-mounted
    (no TVC); the mount block is the same simplified placeholder as the SL model
    and is documented as schematic in PROVENANCE.md.
    """
    groups = [
        make_vacuum_nozzle_group(),
        make_chamber_group(),
        _group("injector_head_group", [make_injector_head()]),
        make_thrust_structure(),
        make_gimbal_group(),
        *make_powerhead_groups(bell_r_fn=vac_bell_radius_at),
        make_avionics_group(),
    ]
    moved_groups = []
    for group in groups:
        moved = group.moved(Location((0, 0, VAC_DROP)))
        moved.label = group.label
        moved_groups.append(moved)
    return moved_groups


# ---------------------------------------------------------------------------
# Schematic interior (cutaway model only) -- translucent, labeled, simplified
# ---------------------------------------------------------------------------


def build_schematic_interior() -> list[Compound]:
    gas = bell_gas_contour()
    hot_nozzle = revolved_solid(
        [(0.001, Z_THROAT)] + [(r - 2.0, z) for r, z in gas] + [(0.001, 0.0)],
        "hot_gas_expansion_volume__schematic", COL_HOT,
        CUT_INNER_ARC_DEG, CUT_INNER_START_DEG,
    )
    chamber_outline = [(0.001, Z_CHAMBER_TOP - 5.0)] + [
        (r - 2.0, z) for r, z in reversed(chamber_gas_contour())
    ] + [(0.001, Z_THROAT)]
    hot_chamber = revolved_solid(
        chamber_outline, "main_chamber_combustion_volume__schematic", COL_HOT,
        CUT_INNER_ARC_DEG, CUT_INNER_START_DEG,
    )
    regen_pts = [(bell_radius_at(z) + INNER_SHELL_T + 1.0, z) for z in
                 (80.0, 300.0, 600.0, 900.0, 1200.0, 1450.0, Z_THROAT)]
    regen_pts += [(r + INNER_SHELL_T + 1.0, z) for r, z in chamber_gas_contour()[1:]]
    regen = revolved_shell(
        regen_pts, 2.5,
        "regen_cooling_band__simplified_annulus__schematic_inferred_nonfunctional",
        COL_REGEN, CUT_INNER_ARC_DEG, CUT_INNER_START_DEG,
    )
    injector = revolved_solid(
        [(0.001, Z_CHAMBER_TOP), (CHAMBER_RADIUS - 4.0, Z_CHAMBER_TOP),
         (CHAMBER_RADIUS - 4.0, Z_CHAMBER_TOP + 38.0), (0.001, Z_CHAMBER_TOP + 38.0)],
        "schematic_injector_region__no_element_detail__nonfunctional", COL_INJECTOR,
        CUT_INNER_ARC_DEG, CUT_INNER_START_DEG,
    )
    parts = [hot_nozzle, hot_chamber, regen, injector]

    for sign, tag, col in ((+1, "ox", COL_LOX), (-1, "fuel", COL_CH4)):
        x = sign * PUMP_X
        parts.extend(
            [
                _cyl_z(
                    x, 0, PUMP_Z0 + 40, PUMP_Z1 - 10, PUMP_RADIUS - 45,
                    f"{tag}_turbopump_placeholder_volume__schematic_inferred_nonfunctional",
                    COL_UNKNOWN,
                ),
                _label(
                    Sphere(radius=PREBURNER_R - 45).locate(Location((x, 0, PUMP_Z1))),
                    f"{tag}_rich_preburner_placeholder_volume__schematic_inferred_nonfunctional",
                    col,
                ),
                tube(
                    [(x, 0, 3070), (x, 0, 2800), (x, 0, 2560)],
                    INLET_PIPE_R - 45,
                    f"{tag}_propellant_inlet_flow__schematic",
                    col,
                ),
                tube(
                    [(sign * 258, 0, 2515), (sign * 232, 0, 2435),
                     (sign * 212, 0, 2365), (sign * 182, 0, 2305)],
                    58.0,
                    f"{tag}_rich_gas_flow_to_injector__schematic",
                    col,
                ),
            ]
        )
    # LOX main feed flow + CH4 regen downcomer flow (schematic centerline tubes)
    parts.append(
        tube(
            [(400, 0, 1725), (330, 0, 1840), (275, 0, 2010), (250, 0, 2140)],
            40.0, "lox_feed_flow__schematic", COL_LOX,
        )
    )
    ring_r = bell_radius_at(MANIFOLD_Z) + WALL_T + 18.0
    parts.append(
        tube(
            [(-400, 0, 1720), (-545, 0, 1320), (-600, 0, 850), (-ring_r, 0, MANIFOLD_Z + 40)],
            32.0, "ch4_regen_supply_flow__schematic", COL_CH4,
        )
    )
    return [_group("schematic_flow_paths_group", parts)]
