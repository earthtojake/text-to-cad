"""Shared geometry library for the SpaceX Merlin 1D educational reconstruction.

DISCLAIMER: Educational, non-functional public-source reconstruction. Not
suitable for manufacture, propulsion, testing, or operational engineering.

All geometry is either scaled from publicly stated envelope figures or is a
photogrammetric/schematic estimate from public photographs. No proprietary
detail is modeled: no injector elements (the pintle TYPE is public; its
geometry is not modeled), no turbopump or gas-generator internals, no cooling
channel geometry, no wall thicknesses (shell thicknesses are decorative), no
valve internals. Hidden internals are simplified placeholder volumes labeled
"schematic". Small repeated features (bolts, clamps, bands, bellows rings)
are DECORATIVE visual richness, not sourced hardware.

Coordinates: engine centerline = Z, nozzle exit plane = Z=0, engine extends
toward +Z, thrust acts along -Z. Units: millimeters, full scale.

Provenance summary (full table in PROVENANCE.md):
- Engine height ~2.92 m, mass ~470 kg class, thrust/Isp/chamber pressure:
  public SpaceX / Falcon User's Guide / Wikipedia-indexed figures. Scale only.
- Sea-level expansion ratio ~16, throat ~260 mm derived from thrust/Pc:
  community estimates. LOW confidence.
- Gas-generator cycle layout (side-mounted single-shaft turbopump, GG on top,
  turbine exhaust duct down the bell): public photos/explainers. MEDIUM for
  topology, LOW for positions.
"""

from __future__ import annotations

from math import cos, radians, sin

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
    revolve,
    sweep,
)

DISPLAY_NAME = "SpaceX Merlin 1D sea-level engine (educational public-source reconstruction)"

# ---------------------------------------------------------------------------
# Published / estimated parameters (mm). Confidence noted per value.
# ---------------------------------------------------------------------------

ENGINE_HEIGHT = 2920.0        # ~2.92 m public figure for Merlin 1D. MEDIUM
EXIT_DIAMETER = 1040.0        # derived: throat est. x sqrt(eps~16). LOW
EXIT_RADIUS = EXIT_DIAMETER / 2.0

# No official throat figure. F = Cf*Pc*At with ~845 kN SL, ~9.7 MPa, Cf~1.6
# gives throat ~260 mm dia. Community/derived estimate. LOW
THROAT_RADIUS = 130.0
EXPANSION_RATIO = (EXIT_RADIUS / THROAT_RADIUS) ** 2   # ~16 effective. LOW

BELL_LENGTH = 1165.0          # 80% Rao length for eps~16 at Rt=130. schematic
Z_THROAT = BELL_LENGTH
THETA_N_DEG = 30.0            # Rao initial parabola angle, textbook. schematic
THETA_E_DEG = 9.0             # Rao exit angle, textbook. schematic

CHAMBER_RADIUS = 215.0        # contraction ~2.7 area ratio. LOW estimate
Z_CHAMBER_TOP = 1750.0        # injector face plane. photogrammetric LOW

INNER_SHELL_T = 7.0           # decorative shell thickness (NOT engineering data)
JACKET_T = 11.0               # decorative jacket thickness (NOT engineering data)
WALL_T = INNER_SHELL_T + JACKET_T

Z_DOME_TOP = 1985.0           # injector/LOX dome apex. schematic
Z_CONE_TOP = 2300.0           # thrust cone top. photogrammetric LOW
Z_GIMBAL_TOP = 2440.0
Z_PLATE_TOP = 2480.0

# Single-shaft turbopump beside the chamber on +X. photogrammetric LOW
TP_X = 470.0
TP_RADIUS = 150.0
TP_Z0, TP_Z1 = 1130.0, 1900.0
GG_Z0, GG_Z1 = 1900.0, 2130.0  # gas generator atop the turbopump. LOW

EXHAUST_DUCT_R = 95.0          # turbine exhaust duct radius. photogrammetric LOW

CUT_START_DEG = 135.0          # cutaway keeps material 135..405, opening faces +Y
CUT_ARC_DEG = 270.0
CUT_INNER_START_DEG = 137.0    # interior volumes recess 2 deg inside shell faces
CUT_INNER_ARC_DEG = 266.0

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

COL_BELL_OUTER = Color(0.45, 0.46, 0.49, 1.0)     # dark oxidized regen bell
COL_BELL_INNER = Color(0.10, 0.10, 0.12, 1.0)     # dark nozzle interior
COL_CHAMBER = Color(0.58, 0.56, 0.52, 1.0)        # warm alloy chamber
COL_DOME = Color(0.66, 0.67, 0.69, 1.0)
COL_STRUCT = Color(0.46, 0.48, 0.52, 1.0)
COL_PUMP = Color(0.70, 0.72, 0.74, 1.0)           # bright aluminum pump
COL_GG = Color(0.42, 0.42, 0.45, 1.0)
COL_DUCT = Color(0.60, 0.62, 0.65, 1.0)
COL_EXHAUST = Color(0.30, 0.29, 0.30, 1.0)        # heat-stained exhaust duct
COL_VALVE = Color(0.34, 0.36, 0.39, 1.0)
COL_HARNESS = Color(0.18, 0.19, 0.20, 1.0)
COL_BOLT = Color(0.55, 0.56, 0.58, 1.0)
COL_CLAMP = Color(0.38, 0.39, 0.41, 1.0)
COL_SENSOR = Color(0.25, 0.27, 0.30, 1.0)
COL_TINT_STRAW = Color(0.60, 0.48, 0.33, 1.0)     # restrained heat tint
COL_TINT_BRONZE = Color(0.47, 0.37, 0.41, 1.0)
COL_TINT_BLUE = Color(0.37, 0.43, 0.53, 1.0)

# schematic flow palette (translucent)
COL_LOX = Color(0.20, 0.45, 0.95, 0.60)           # LOX = blue
COL_RP1 = Color(0.85, 0.60, 0.15, 0.60)           # RP-1 = amber
COL_HOT = Color(0.95, 0.42, 0.12, 0.55)           # hot gas = orange/red
COL_REGEN = Color(0.85, 0.60, 0.15, 0.35)         # regen band, faint amber
COL_UNKNOWN = Color(0.62, 0.62, 0.68, 0.35)       # inferred placeholder gray
COL_INJECTOR = Color(0.70, 0.70, 0.72, 0.60)


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


def _bezier_ctrl():
    from math import tan

    tn, te = radians(THETA_N_DEG), radians(THETA_E_DEG)
    arc_r = 0.382 * THROAT_RADIUS
    z0 = arc_r * sin(tn)
    r0 = THROAT_RADIUS + arc_r * (1.0 - cos(tn))
    z2, r2 = BELL_LENGTH, EXIT_RADIUS
    m0, m2 = tan(tn), tan(te)
    z1 = (r2 - r0 + m0 * z0 - m2 * z2) / (m0 - m2)
    r1 = r0 + m0 * (z1 - z0)
    return (z0, r0), (z1, r1), (z2, r2)


def bell_gas_contour(samples: int = 30) -> list[tuple[float, float]]:
    """(r, z) points from throat (z=Z_THROAT) down to exit (z=0)."""
    tn = radians(THETA_N_DEG)
    arc_r = 0.382 * THROAT_RADIUS
    pts: list[tuple[float, float]] = []
    n_arc = 6
    for i in range(n_arc + 1):
        a = tn * i / n_arc
        pts.append((THROAT_RADIUS + arc_r * (1.0 - cos(a)), Z_THROAT - arc_r * sin(a)))
    (z0, r0), (z1, r1), (z2, r2) = _bezier_ctrl()
    for i in range(1, samples + 1):
        t = i / samples
        zd = (1 - t) ** 2 * z0 + 2 * (1 - t) * t * z1 + t**2 * z2
        r = (1 - t) ** 2 * r0 + 2 * (1 - t) * t * r1 + t**2 * r2
        pts.append((r, Z_THROAT - zd))
    return pts


def chamber_gas_contour() -> list[tuple[float, float]]:
    """(r, z) from throat (z=Z_THROAT) up to the injector face plane."""
    return [
        (THROAT_RADIUS, Z_THROAT),
        (THROAT_RADIUS + 4.0, Z_THROAT + 35.0),
        (THROAT_RADIUS + 30.0, Z_THROAT + 95.0),
        (170.0, 1310.0),
        (200.0, 1380.0),
        (CHAMBER_RADIUS, 1450.0),
        (CHAMBER_RADIUS, Z_CHAMBER_TOP),
    ]


_BELL_SAMPLED = None


def bell_radius_at(z: float) -> float:
    global _BELL_SAMPLED
    if _BELL_SAMPLED is None:
        _BELL_SAMPLED = sorted(bell_gas_contour(samples=200), key=lambda p: p[1])
    pts = _BELL_SAMPLED
    if z <= pts[0][1]:
        return pts[0][0]
    for (r_a, z_a), (r_b, z_b) in zip(pts, pts[1:]):
        if z_a <= z <= z_b:
            f = (z - z_a) / (z_b - z_a) if z_b > z_a else 0.0
            return r_a + (r_b - r_a) * f
    return pts[-1][0]


# ---------------------------------------------------------------------------
# Revolve / sweep / detail helpers
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


def revolved_shell(inner_pts, thickness, label, color, arc_deg=360.0, start_deg=0.0):
    part = revolve(_profile_face(inner_pts, thickness), axis=Axis.Z, revolution_arc=arc_deg)
    if start_deg:
        part = part.rotate(Axis.Z, start_deg)
    return _label(part, label, color)


def revolved_solid(outline, label, color, arc_deg=360.0, start_deg=0.0, spline=False):
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


def tube(points, radius, label, color):
    path = Edge.make_spline([Vector(*p) for p in points])
    section = Plane(origin=path.position_at(0), z_dir=path.tangent_at(0)) * Circle(radius)
    part = sweep(section, path=path)
    return _label(part, label, color)


def _cyl_z(x, y, z0, z1, r, label, color):
    part = Cylinder(radius=r, height=z1 - z0).locate(Location((x, y, (z0 + z1) / 2.0)))
    return _label(part, label, color)


def bolt_ring(parts, *, cx, cy, z, ring_r, count, prefix, bolt_r=7.0, bolt_h=18.0,
              color=COL_BOLT, phase_deg=0.0):
    """Append `count` decorative bolt studs on a circle. Purely visual."""
    for i in range(count):
        a = radians(phase_deg + i * 360.0 / count)
        parts.append(
            _label(
                Cylinder(radius=bolt_r, height=bolt_h).locate(
                    Location((cx + ring_r * cos(a), cy + ring_r * sin(a), z))
                ),
                f"{prefix}_bolt_{i + 1:02d}__decorative", color,
            )
        )


def bellows_stack(parts, *, cx, cy, z0, count, pitch, major_r, minor_r, prefix,
                  color=COL_DUCT):
    """Append a stack of thin tori reading as a flex-bellows joint. Decorative."""
    for i in range(count):
        parts.append(
            _label(
                Torus(major_radius=major_r, minor_radius=minor_r).locate(
                    Location((cx, cy, z0 + i * pitch))
                ),
                f"{prefix}_convolution_{i + 1:02d}__decorative", color,
            )
        )


def band_ring(parts, *, z, inner_r, width, thickness, label, color):
    parts.append(
        revolved_solid(
            [(inner_r, z), (inner_r + thickness, z), (inner_r + thickness, z + width),
             (inner_r, z + width)],
            label, color,
        )
    )


# ---------------------------------------------------------------------------
# Nozzle assembly
# ---------------------------------------------------------------------------


def make_nozzle_assembly(arc_deg=360.0, start_deg=0.0) -> Compound:
    gas = bell_gas_contour()
    parts = [
        revolved_shell(
            gas, INNER_SHELL_T,
            "nozzle_liner__dark_interior__decorative_thickness",
            COL_BELL_INNER, arc_deg, start_deg,
        ),
        revolved_shell(
            [(r + INNER_SHELL_T, z) for r, z in gas], JACKET_T,
            "nozzle_regen_jacket__photogrammetric",
            COL_BELL_OUTER, arc_deg, start_deg,
        ),
    ]
    # brazed stiffening band rings down the bell (decorative)
    for i, z in enumerate((150.0, 340.0, 530.0, 720.0, 900.0, 1060.0)):
        r = bell_radius_at(z) + WALL_T + 0.5
        parts.append(
            revolved_solid(
                [(r, z), (r + 8.0, z), (r + 8.0, z + 26.0), (r, z + 26.0)],
                f"bell_stiffener_band_{i + 1:02d}__decorative", COL_BELL_OUTER,
                arc_deg, start_deg,
            )
        )
    # restrained heat-tint sleeves just below the throat (decorative)
    for z_lo, z_hi, col, name in (
        (1050.0, 1140.0, COL_TINT_STRAW, "straw"),
        (960.0, 1050.0, COL_TINT_BRONZE, "bronze"),
        (870.0, 960.0, COL_TINT_BLUE, "blue"),
    ):
        pts = [
            (bell_radius_at(z_lo + (z_hi - z_lo) * i / 5.0) + WALL_T + 0.6,
             z_lo + (z_hi - z_lo) * i / 5.0)
            for i in range(6)
        ]
        parts.append(
            revolved_shell(pts, 2.2, f"heat_tint_band_{name}__decorative", col,
                           arc_deg, start_deg)
        )
    # exit stiffener lip
    lip = Torus(major_radius=EXIT_RADIUS + WALL_T / 2.0 + 3.0, minor_radius=12.0,
                major_angle=arc_deg)
    parts.append(
        _label(lip.locate(Location((0, 0, 12.5), (0, 0, start_deg))),
               "nozzle_exit_stiffener_ring__photogrammetric", COL_BELL_OUTER)
    )
    return _group("nozzle_assembly", parts)


# ---------------------------------------------------------------------------
# Chamber + injector dome assembly
# ---------------------------------------------------------------------------


def make_chamber_assembly(arc_deg=360.0, start_deg=0.0) -> Compound:
    gas = chamber_gas_contour()
    parts = [
        revolved_shell(
            gas, INNER_SHELL_T,
            "chamber_liner__dark_interior__decorative_thickness",
            COL_BELL_INNER, arc_deg, start_deg,
        ),
        revolved_shell(
            [(r + INNER_SHELL_T, z) for r, z in gas], JACKET_T,
            "chamber_envelope__photogrammetric", COL_CHAMBER, arc_deg, start_deg,
        ),
        # dark cap so the view up the nozzle ends in shadow
        revolved_solid(
            [(0.0, Z_CHAMBER_TOP - 3.0), (CHAMBER_RADIUS - 0.5, Z_CHAMBER_TOP - 3.0),
             (CHAMBER_RADIUS - 0.5, Z_CHAMBER_TOP), (0.0, Z_CHAMBER_TOP)],
            "chamber_interior_cap__decorative", COL_BELL_INNER, arc_deg, start_deg,
        ),
    ]
    # chamber stiffening bands
    for i, z in enumerate((1470.0, 1560.0, 1650.0)):
        band_ring(parts, z=z, inner_r=CHAMBER_RADIUS + WALL_T + 0.5, width=24.0,
                  thickness=7.0, label=f"chamber_band_{i + 1:02d}__decorative",
                  color=COL_CHAMBER)
    # injector dome (exterior only, no element detail) + LOX dome cap
    dome_outline = [
        (0.0, Z_CHAMBER_TOP),
        (CHAMBER_RADIUS + WALL_T, Z_CHAMBER_TOP),
        (CHAMBER_RADIUS + WALL_T, Z_CHAMBER_TOP + 45.0),
        (205.0, 1875.0),
        (140.0, 1945.0),
        (70.0, 1975.0),
        (0.0, Z_DOME_TOP),
    ]
    pts3 = [Vector(r, 0, z) for r, z in dome_outline]
    edges = [
        Edge.make_line(pts3[0], pts3[1]),
        Edge.make_line(pts3[1], pts3[2]),
        Edge.make_spline(pts3[2:]),
        Edge.make_line(pts3[-1], pts3[0]),
    ]
    dome = revolve(Face(Wire(edges)), axis=Axis.Z, revolution_arc=arc_deg)
    if start_deg:
        dome = dome.rotate(Axis.Z, start_deg)
    parts.append(_label(dome, "injector_dome__exterior_only__no_element_detail", COL_DOME))
    # dome flange + bolt circle
    band_ring(parts, z=Z_CHAMBER_TOP + 2.0, inner_r=CHAMBER_RADIUS + WALL_T,
              width=20.0, thickness=16.0,
              label="injector_dome_flange__photogrammetric", color=COL_DOME)
    bolt_ring(parts, cx=0, cy=0, z=Z_CHAMBER_TOP + 12.0,
              ring_r=CHAMBER_RADIUS + WALL_T + 8.0, count=24,
              prefix="dome_flange")
    # LOX dome inlet on top center with flange + bolts
    parts.append(_cyl_z(0, 0, Z_DOME_TOP - 15.0, Z_DOME_TOP + 110.0, 62.0,
                        "lox_dome_inlet_neck__photogrammetric", COL_DOME))
    parts.append(_cyl_z(0, 0, Z_DOME_TOP + 110.0, Z_DOME_TOP + 128.0, 88.0,
                        "lox_dome_inlet_flange__simplified", COL_STRUCT))
    bolt_ring(parts, cx=0, cy=0, z=Z_DOME_TOP + 132.0, ring_r=76.0, count=12,
              prefix="lox_inlet_flange", bolt_r=6.0, bolt_h=14.0)
    return _group("chamber_assembly", parts)


# ---------------------------------------------------------------------------
# Thrust structure / gimbal
# ---------------------------------------------------------------------------


def make_thrust_structure(arc_deg=360.0, start_deg=0.0) -> Compound:
    parts = [
        revolved_solid(
            [(0.0, 1990.0), (150.0, 1990.0), (95.0, Z_CONE_TOP), (0.0, Z_CONE_TOP)],
            "thrust_cone__photogrammetric", COL_STRUCT, arc_deg, start_deg,
        )
    ]
    for az in (45.0, 135.0, 225.0, 315.0):
        tri = Face(
            Wire(
                [
                    Edge.make_line(Vector(88, 0, Z_CONE_TOP), Vector(152, 0, 1995)),
                    Edge.make_line(Vector(152, 0, 1995), Vector(88, 0, 1995)),
                    Edge.make_line(Vector(88, 0, 1995), Vector(88, 0, Z_CONE_TOP)),
                ]
            )
        )
        from build123d import extrude

        plate = extrude(tri, amount=9.0, both=True)
        parts.append(
            _label(plate.rotate(Axis.Z, az),
                   f"thrust_cone_gusset_{int(az)}deg__schematic", COL_STRUCT)
        )
    parts.extend(
        [
            _label(Box(210, 210, 120).locate(Location((0, 0, 2360))),
                   "gimbal_block__simplified_exterior", COL_STRUCT),
            _label(Cylinder(radius=34, height=300, rotation=(0, 90, 0)).locate(
                Location((0, 0, 2360))), "gimbal_cross_pin_x__simplified", COL_STRUCT),
            _label(Cylinder(radius=34, height=300, rotation=(90, 0, 0)).locate(
                Location((0, 0, 2360))), "gimbal_cross_pin_y__simplified", COL_STRUCT),
            _label(Box(280, 280, 36).locate(Location((0, 0, 2462))),
                   "vehicle_mount_plate__simplified", COL_STRUCT),
        ]
    )
    for ex in (-120.0, 120.0):
        parts.append(_label(Box(34, 110, 130).locate(Location((ex, 0, 2355))),
                            f"gimbal_ear_x{int(ex)}__simplified", COL_STRUCT))
        parts.append(_label(Box(110, 34, 130).locate(Location((0, ex, 2355))),
                            f"gimbal_ear_y{int(ex)}__simplified", COL_STRUCT))
    for bx in (-105.0, 105.0):
        for by in (-105.0, 105.0):
            parts.append(
                _label(Cylinder(radius=24, height=46).locate(Location((bx, by, 2503))),
                       f"mount_boss_{int(bx)}_{int(by)}__simplified", COL_STRUCT)
            )
    bolt_ring(parts, cx=0, cy=0, z=2484.0, ring_r=118.0, count=16,
              prefix="mount_plate", bolt_r=6.0, bolt_h=12.0)
    # TVC actuator brackets + housings at azimuth 60/120 (photogrammetric)
    for az in (60.0, 120.0):
        a = radians(az)
        r_mount = 140.0
        px, py = r_mount * cos(a), r_mount * sin(a)
        parts.append(
            _label(Box(80, 36, 95).locate(Location((px, py, 2210), (0, 0, az))),
                   f"tvc_clevis_bracket_{int(az)}deg__photogrammetric", COL_STRUCT)
        )
        parts.append(
            _label(Cylinder(radius=13, height=70, rotation=(0, 90, 0)).locate(
                Location((px, py, 2210), (0, 0, az + 90))),
                f"tvc_pin_{int(az)}deg__simplified", COL_HARNESS)
        )
        housing = Cylinder(radius=33, height=200).locate(
            Location((cos(a) * (r_mount + 80), sin(a) * (r_mount + 80), 2295),
                     (55 * sin(a), 55 * cos(a), 0))
        )
        parts.append(_label(housing, f"tvc_actuator_housing_{int(az)}deg__schematic",
                            COL_VALVE))
        cap = Sphere(radius=34).locate(
            Location((cos(a) * (r_mount + 118), sin(a) * (r_mount + 118), 2380))
        )
        parts.append(_label(cap, f"tvc_actuator_rod_end_{int(az)}deg__decorative",
                            COL_VALVE))
    return _group("thrust_structure_assembly", parts)


# ---------------------------------------------------------------------------
# Turbopump + gas generator (+X side) — exterior placeholders only
# ---------------------------------------------------------------------------


def make_turbopump_assembly(section: bool = False) -> Compound:
    parts: list = []
    if section:
        housing = revolved_solid(
            [(0.0, TP_Z0), (TP_RADIUS, TP_Z0), (TP_RADIUS, TP_Z1), (0.0, TP_Z1)],
            "turbopump_housing__exterior_placeholder__no_internals",
            COL_PUMP, CUT_ARC_DEG, CUT_START_DEG,
        ).moved(Location((TP_X, 0, 0)))
        housing.label = "turbopump_housing__exterior_placeholder__no_internals"
        parts.append(housing)
    else:
        parts.append(_cyl_z(TP_X, 0, TP_Z0, TP_Z1, TP_RADIUS,
                            "turbopump_housing__exterior_placeholder__no_internals",
                            COL_PUMP))
    # pump section details (all exterior placeholders / decorative)
    parts.append(
        _label(Torus(major_radius=118, minor_radius=54).locate(
            Location((TP_X, 0, 1640))),
            "lox_pump_volute__simplified_exterior", COL_PUMP)
    )
    parts.append(
        _label(Torus(major_radius=118, minor_radius=54).locate(
            Location((TP_X, 0, 1420))),
            "rp1_pump_volute__simplified_exterior", COL_PUMP)
    )
    parts.append(
        revolved_solid(
            [(0.001, TP_Z0 - 90.0), (95.0, TP_Z0 - 20.0), (120.0, TP_Z0), (0.001, TP_Z0)],
            "turbine_housing__exterior_placeholder__no_internals", COL_EXHAUST,
            spline=False,
        ).moved(Location((TP_X, 0, 0)))
    )
    parts[-1].label = "turbine_housing__exterior_placeholder__no_internals"
    # inducer cap on top
    parts.append(
        _label(Sphere(radius=118).locate(Location((TP_X, 0, TP_Z1))),
               "pump_inlet_dome__exterior_placeholder", COL_PUMP)
    )
    # flange rings + bolt circles at the pump section joints
    for i, z in enumerate((1330.0, 1530.0, 1740.0)):
        band_ring(parts, z=z, inner_r=TP_RADIUS - 2.0, width=22.0, thickness=14.0,
                  label=f"pump_case_flange_{i + 1:02d}__decorative", color=COL_PUMP)
        bolt_ring(parts, cx=TP_X, cy=0, z=z + 11.0, ring_r=TP_RADIUS + 12.0 - 2.0,
                  count=16, prefix=f"pump_flange_{i + 1:02d}", bolt_r=5.5, bolt_h=12.0)
    # mounting brackets tying the pump to the chamber
    for i, z in enumerate((1500.0, 1700.0)):
        parts.append(
            _label(Box(190, 46, 16).locate(Location((TP_X - 220, 0, z))),
                   f"pump_mount_bracket_{i + 1:02d}__schematic", COL_STRUCT)
        )
    # speed-sensor-like module
    parts.append(
        _label(Cylinder(radius=16, height=55, rotation=(0, 90, 0)).locate(
            Location((TP_X + TP_RADIUS + 25, 40, 1250))),
            "pump_sensor_module__decorative", COL_SENSOR)
    )
    return _group("turbopump_assembly", parts)


def make_gas_generator_assembly() -> Compound:
    parts = [
        _cyl_z(TP_X, 0, GG_Z0, GG_Z1, 88.0,
               "gas_generator_body__exterior_placeholder__no_internals", COL_GG),
        _label(Sphere(radius=88.0).locate(Location((TP_X, 0, GG_Z1))),
               "gas_generator_dome__exterior_placeholder__no_internals", COL_GG),
    ]
    band_ring(parts, z=GG_Z0 + 30.0, inner_r=88.0, width=20.0, thickness=12.0,
              label="gg_flange__decorative", color=COL_GG)
    bolt_ring(parts, cx=TP_X, cy=0, z=GG_Z0 + 40.0, ring_r=104.0, count=12,
              prefix="gg_flange", bolt_r=5.0, bolt_h=11.0)
    # GG propellant feed lines from the pump volutes
    parts.append(
        tube([(TP_X + 100, 40, 1660), (TP_X + 130, 60, 1810), (TP_X + 80, 40, 1960),
              (TP_X + 40, 20, 2020)], 24.0,
             "gg_lox_feed_line__schematic_routing", COL_DUCT)
    )
    parts.append(
        tube([(TP_X + 100, -40, 1440), (TP_X + 150, -70, 1700), (TP_X + 90, -45, 1975),
              (TP_X + 45, -22, 2030)], 22.0,
             "gg_fuel_feed_line__schematic_routing", COL_DUCT)
    )
    # GG valve bodies
    for i, (dy, name) in enumerate(((70.0, "gg_lox_valve"), (-70.0, "gg_fuel_valve"))):
        parts.append(
            _label(Box(90, 70, 80).locate(Location((TP_X + 60, dy, 2035))),
                   f"{name}_housing__schematic__no_internals", COL_VALVE)
        )
    return _group("gas_generator_assembly", parts)


def make_turbine_exhaust_assembly() -> Compound:
    """The distinctive Merlin turbine-exhaust duct running down beside the bell."""
    parts = [
        tube(
            [(TP_X, 0, TP_Z0 - 100), (TP_X + 40, 0, 950), (620, 0, 620),
             (660, 0, 300), (665, 0, 90)],
            EXHAUST_DUCT_R, "turbine_exhaust_duct__photogrammetric", COL_EXHAUST,
        ),
        # exit skirt cone
        revolved_solid(
            [(EXHAUST_DUCT_R - 6.0, 0.0), (EXHAUST_DUCT_R + 26.0, 0.0),
             (EXHAUST_DUCT_R + 6.0, 120.0), (EXHAUST_DUCT_R - 6.0, 120.0)],
            "exhaust_duct_exit_skirt__photogrammetric", COL_EXHAUST,
        ).moved(Location((665, 0, 8))),
    ]
    parts[-1].label = "exhaust_duct_exit_skirt__photogrammetric"
    # bellows expansion joint below the turbine
    bellows_stack(parts, cx=TP_X + 6, cy=0, z0=985.0, count=7, pitch=16.0,
                  major_r=EXHAUST_DUCT_R + 8.0, minor_r=7.0,
                  prefix="exhaust_bellows", color=COL_EXHAUST)
    # duct support brackets to the bell bands
    for i, (z, bx) in enumerate(((640.0, 585.0), (320.0, 645.0))):
        parts.append(
            _label(Box(120, 30, 14).locate(Location((bx - 60, 0, z))),
                   f"exhaust_duct_bracket_{i + 1:02d}__schematic", COL_STRUCT)
        )
    # partial heat-shield wrap panel behind the duct
    shield = revolved_solid(
        [(bell_radius_at(500.0) + WALL_T + 12.0, 380.0),
         (bell_radius_at(500.0) + WALL_T + 16.0, 380.0),
         (bell_radius_at(700.0) + WALL_T + 16.0, 700.0),
         (bell_radius_at(700.0) + WALL_T + 12.0, 700.0)],
        "exhaust_heat_shield_panel__photogrammetric", COL_EXHAUST,
        arc_deg=70.0, start_deg=-35.0,
    )
    parts.append(shield)
    return _group("turbine_exhaust_assembly", parts)


# ---------------------------------------------------------------------------
# Propellant feed + valves
# ---------------------------------------------------------------------------


def make_feed_assembly() -> Compound:
    parts = []
    # LOX main feed: vehicle top -> down to pump inlet dome
    parts.append(
        tube([(TP_X, 0, 2905), (TP_X, 0, 2450), (TP_X, 0, 2080)], 80.0,
             "lox_main_feed_line__photogrammetric", COL_DUCT)
    )
    parts.append(_cyl_z(TP_X, 0, 2892.0, 2912.0, 118.0,
                        "lox_vehicle_interface_flange__simplified", COL_STRUCT))
    bolt_ring(parts, cx=TP_X, cy=0, z=2916.0, ring_r=102.0, count=12,
              prefix="lox_interface", bolt_r=6.0, bolt_h=12.0)
    # LOX high-pressure discharge: pump -> injector dome top
    parts.append(
        tube([(TP_X - 100, 30, 1680), (330, 60, 1830), (160, 30, 1990),
              (60, 8, 2065)], 46.0,
             "lox_discharge_duct__schematic_routing", COL_DUCT)
    )
    # RP-1 main feed into lower pump
    parts.append(
        tube([(TP_X + 240, 0, 2905), (TP_X + 250, 0, 2400), (TP_X + 210, 0, 1800),
              (TP_X + 150, 0, 1460)], 58.0,
             "rp1_main_feed_line__photogrammetric", COL_DUCT)
    )
    parts.append(_cyl_z(TP_X + 240, 0, 2892.0, 2912.0, 92.0,
                        "rp1_vehicle_interface_flange__simplified", COL_STRUCT))
    bolt_ring(parts, cx=TP_X + 240, cy=0, z=2916.0, ring_r=78.0, count=12,
              prefix="rp1_interface", bolt_r=5.5, bolt_h=12.0)
    # RP-1 discharge to nozzle regen inlet manifold ring near throat
    manifold_r = bell_radius_at(1080.0) + WALL_T + 16.0
    parts.append(
        _label(Torus(major_radius=manifold_r, minor_radius=26.0).locate(
            Location((0, 0, 1080))),
            "regen_inlet_manifold_ring__schematic_routing", COL_DUCT)
    )
    parts.append(
        tube([(TP_X - 105, -35, 1420), (400, -120, 1260), (manifold_r * 0.82,
              -manifold_r * 0.5, 1110)], 34.0,
             "rp1_regen_supply_duct__schematic_routing", COL_DUCT)
    )
    # main valves with actuator caps + position-indicator domes
    for name, (vx, vy, vz) in (
        ("lox_main_valve", (TP_X, 0, 2250)),
        ("rp1_main_valve", (TP_X + 225, 0, 2100)),
    ):
        parts.append(_label(Box(170, 150, 130).locate(Location((vx, vy, vz))),
                            f"{name}_housing__schematic__no_internals", COL_VALVE))
        parts.append(
            _label(Cylinder(radius=34, height=120, rotation=(90, 0, 0)).locate(
                Location((vx, vy + 130, vz))),
                f"{name}_actuator__schematic", COL_VALVE)
        )
        parts.append(
            _label(Sphere(radius=22).locate(Location((vx, vy + 195, vz))),
                   f"{name}_position_indicator__decorative", COL_SENSOR)
        )
    # flex bellows on the LOX feed below the vehicle interface
    bellows_stack(parts, cx=TP_X, cy=0, z0=2560.0, count=6, pitch=15.0,
                  major_r=90.0, minor_r=6.5, prefix="lox_feed_bellows")
    bellows_stack(parts, cx=TP_X + 240, cy=0, z0=2500.0, count=6, pitch=15.0,
                  major_r=68.0, minor_r=6.0, prefix="rp1_feed_bellows")
    return _group("propellant_feed_assembly", parts)


# ---------------------------------------------------------------------------
# Harness, sensors, ignition
# ---------------------------------------------------------------------------


def make_harness_assembly() -> Compound:
    parts = [
        _label(Box(200, 120, 300).locate(Location((-90, -330, 1980))),
               "engine_controller_enclosure__photogrammetric_placeholder", COL_VALVE)
    ]
    # cable runs hugging the chamber, with clamp blocks along them
    runs = [
        ("harness_run_a", 205.0, 1830.0, 1250.0),
        ("harness_run_b", 250.0, 1830.0, 1250.0),
        ("harness_run_c", 290.0, 1800.0, 1150.0),
    ]
    for name, az, z_top, z_bot in runs:
        a = radians(az)
        r_top, r_bot = 238.0, bell_radius_at(z_bot) + WALL_T + 14.0
        pts = [
            (r_top * cos(a), r_top * sin(a), z_top),
            ((r_top + 20) * cos(a), (r_top + 20) * sin(a), (z_top + z_bot) / 2),
            (r_bot * cos(a), r_bot * sin(a), z_bot),
        ]
        parts.append(tube(pts, 10.0, f"{name}__decorative", COL_HARNESS))
        for i in range(4):
            t = (i + 1) / 5.0
            cx = pts[0][0] + (pts[2][0] - pts[0][0]) * t
            cy = pts[0][1] + (pts[2][1] - pts[0][1]) * t
            cz = z_top + (z_bot - z_top) * t
            parts.append(
                _label(Box(30, 30, 16).locate(Location((cx, cy, cz), (0, 0, az))),
                       f"{name}_clamp_{i + 1:02d}__decorative", COL_CLAMP)
            )
    # sensor-like modules on the chamber and dome
    for i, (az, z) in enumerate(((30.0, 1620.0), (150.0, 1560.0), (255.0, 1700.0),
                                 (330.0, 1690.0), (200.0, 1620.0), (110.0, 1780.0))):
        a = radians(az)
        r = 246.0
        parts.append(
            _label(
                Cylinder(radius=13, height=42, rotation=(0, 90, 0)).locate(
                    Location((r * cos(a), r * sin(a), z), (0, 0, az))
                ),
                f"sensor_module_{i + 1:02d}__decorative", COL_SENSOR,
            )
        )
    # TEA-TEB ignition line to the injector dome (publicly known ignition method)
    parts.append(
        tube([(-140, -300, 1990), (-90, -180, 2020), (-30, -60, 2050)], 9.0,
             "teateb_ignition_line__schematic_routing", COL_HARNESS)
    )
    parts.append(
        _label(Cylinder(radius=26, height=70).locate(Location((-150, -320, 2140))),
               "teateb_charge_canister__schematic_placeholder", COL_SENSOR)
    )
    return _group("harness_ignition_assembly", parts)


# ---------------------------------------------------------------------------
# Full exterior
# ---------------------------------------------------------------------------


def build_exterior(arc_deg=360.0, start_deg=0.0, section_pumps=False) -> list[Compound]:
    return [
        make_nozzle_assembly(arc_deg, start_deg),
        make_chamber_assembly(arc_deg, start_deg),
        make_thrust_structure(arc_deg, start_deg),
        make_turbopump_assembly(section=section_pumps),
        make_gas_generator_assembly(),
        make_turbine_exhaust_assembly(),
        make_feed_assembly(),
        make_harness_assembly(),
    ]


# ---------------------------------------------------------------------------
# Schematic interior (cutaway only) — translucent, labeled, simplified
# ---------------------------------------------------------------------------


def build_schematic_interior() -> list[Compound]:
    gas = bell_gas_contour()
    parts = [
        revolved_solid(
            [(0.001, Z_THROAT)] + [(r - 2.0, z) for r, z in gas] + [(0.001, 0.0)],
            "hot_gas_expansion_volume__schematic", COL_HOT,
            CUT_INNER_ARC_DEG, CUT_INNER_START_DEG,
        ),
        revolved_solid(
            [(0.001, Z_CHAMBER_TOP - 5.0)]
            + [(r - 2.0, z) for r, z in reversed(chamber_gas_contour())]
            + [(0.001, Z_THROAT)],
            "main_chamber_combustion_volume__schematic", COL_HOT,
            CUT_INNER_ARC_DEG, CUT_INNER_START_DEG,
        ),
    ]
    regen_pts = [(bell_radius_at(z) + INNER_SHELL_T + 1.0, z) for z in
                 (60.0, 250.0, 500.0, 750.0, 1000.0, Z_THROAT)]
    regen_pts += [(r + INNER_SHELL_T + 1.0, z) for r, z in chamber_gas_contour()[1:]]
    parts.append(
        revolved_shell(
            regen_pts, 2.4,
            "regen_cooling_band__simplified_annulus__schematic_inferred_nonfunctional",
            COL_REGEN, CUT_INNER_ARC_DEG, CUT_INNER_START_DEG,
        )
    )
    parts.append(
        revolved_solid(
            [(0.001, Z_CHAMBER_TOP), (CHAMBER_RADIUS - 4.0, Z_CHAMBER_TOP),
             (CHAMBER_RADIUS - 4.0, Z_CHAMBER_TOP + 30.0), (0.001, Z_CHAMBER_TOP + 30.0)],
            "schematic_injector_region__no_element_detail__nonfunctional",
            COL_INJECTOR, CUT_INNER_ARC_DEG, CUT_INNER_START_DEG,
        )
    )
    # placeholder volumes inside the sectioned turbopump / GG
    parts.extend(
        [
            _cyl_z(TP_X, 0, 1560.0, 1880.0, TP_RADIUS - 42.0,
                   "lox_pump_placeholder_volume__schematic_inferred_nonfunctional",
                   COL_LOX),
            _cyl_z(TP_X, 0, 1350.0, 1540.0, TP_RADIUS - 42.0,
                   "rp1_pump_placeholder_volume__schematic_inferred_nonfunctional",
                   COL_RP1),
            _cyl_z(TP_X, 0, TP_Z0 + 20.0, 1330.0, TP_RADIUS - 42.0,
                   "turbine_placeholder_volume__schematic_inferred_nonfunctional",
                   COL_UNKNOWN),
            _cyl_z(TP_X, 0, GG_Z0 + 15.0, GG_Z1 + 40.0, 52.0,
                   "gas_generator_placeholder_volume__schematic_inferred_nonfunctional",
                   COL_HOT),
        ]
    )
    # color-coded flow tubes (schematic centerlines)
    parts.append(
        tube([(TP_X, 0, 2890), (TP_X, 0, 2300), (TP_X, 0, 1960)], 38.0,
             "lox_feed_flow__schematic", COL_LOX)
    )
    parts.append(
        tube([(TP_X - 100, 30, 1680), (330, 60, 1830), (160, 30, 1990),
              (55, 8, 2060)], 26.0, "lox_discharge_flow__schematic", COL_LOX)
    )
    parts.append(
        tube([(TP_X + 240, 0, 2890), (TP_X + 250, 0, 2300), (TP_X + 210, 0, 1800),
              (TP_X + 150, 0, 1500)], 30.0, "rp1_feed_flow__schematic", COL_RP1)
    )
    manifold_r = bell_radius_at(1080.0) + WALL_T + 16.0
    parts.append(
        tube([(TP_X - 105, -35, 1420), (400, -120, 1260),
              (manifold_r * 0.82, -manifold_r * 0.5, 1110)], 20.0,
             "rp1_regen_supply_flow__schematic", COL_RP1)
    )
    parts.append(
        tube([(TP_X, 0, TP_Z0 - 60), (TP_X + 40, 0, 950), (620, 0, 620),
              (660, 0, 300), (665, 0, 60)], 55.0,
             "turbine_exhaust_flow__schematic", COL_HOT)
    )
    return [_group("schematic_flow_paths_assembly", parts)]
