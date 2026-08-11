"""SpaceX Raptor 3 - evidence-grounded CAD reconstruction (concept model).

A dense technical reconstruction of the Raptor 3 full-flow staged-combustion
methalox engine, held as close as practical to publicly documented evidence:

- Overall envelope: 3.1 m tall, 1.3 m nozzle exit diameter (SpaceX published
  Raptor 3 length/diameter figures, Aug 2024).
- Sea-level bell, expansion ratio ~34.3 -> throat diameter ~222 mm.
- Full-flow staged combustion: a fuel-rich preburner drives the methane
  turbopump, an oxygen-rich preburner drives the LOX turbopump, and both
  turbine exhausts enter the main injector as hot gas through short, fat
  transfer ducts (no gas is dumped overboard).
- Torch igniters on both preburners; coaxial-swirl main injector implied by
  the injector head/dome stack (internal elements not modeled).
- Raptor 3 signatures: no external heat shield or shroud, most secondary
  plumbing and sensor runs folded into the castings, welded joints replacing
  many bolted flanges, integrated cast powerhead (SX500-class superalloy),
  smooth dark oxidized-inconel thrust chamber and nozzle.
- Regenerative cooling loop plumbing follows the documented cycle: methane
  pump discharge -> external downcomers -> nozzle inlet manifold -> (channel
  flow inside the wall, not modeled) -> chamber collection manifold ->
  preburner and injector fuel feeds.
- Electric thrust-vector-control actuators, compact two-axis gimbal cross on
  the engine centerline, vehicle interface plate at the very top.

Where photos do not resolve internals, routing is inferred strictly from the
documented FFSC cycle - no fantasy hardware. No logos or markings.

Conventions:
- Units: millimeters.
- Origin: engine centerline at the nozzle exit plane. +Z points up toward the
  vehicle interface (interface plate top face at z ~= 3100).
- Fuel (methane) side hardware sits at -X, oxygen side at +X.
- Repeated hardware (bolts, sensors, clamps, weld beads) is built once per
  size and instanced with `.moved()` so content-addressed meshing dedups it.
  No `.bounding_box()` calls on shared shapes; every placement is analytic.
"""

from math import cos, radians, sin, tan

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
    Locations,
    Plane,
    Polyline,
    Pos,
    RegularPolygon,
    Sphere,
    Spline,
    Torus,
    Vector,
    extrude,
    make_face,
    revolve,
    sweep,
)

# --------------------------------------------------------------------------
# Palette (technical concept render: oxidized inconel, dark castings, steel)
# --------------------------------------------------------------------------

COL_NOZZLE = Color(0.10, 0.095, 0.09)     # oxidized regen-cooled bell
COL_CHAMBER = Color(0.12, 0.115, 0.11)    # chamber jacket, slightly lighter
COL_CAST = Color(0.20, 0.20, 0.22)        # SX500-class cast housings
COL_CAST_DARK = Color(0.14, 0.14, 0.16)   # preburner / turbine casings
COL_DUCT = Color(0.13, 0.13, 0.14)        # large welded ducts
COL_STEEL = Color(0.40, 0.41, 0.43)       # machined steel details
COL_INCONEL = Color(0.22, 0.20, 0.18)     # heat-tinted inconel manifolds
COL_PIPE = Color(0.38, 0.39, 0.41)        # small-bore stainless lines
COL_COPPER = Color(0.50, 0.34, 0.20)      # copper-alloy manifold blocks
COL_GOLD = Color(0.55, 0.45, 0.26)        # brazed / plated fittings
COL_BLACK = Color(0.055, 0.055, 0.06)     # harness, actuators, insulation
COL_BOLT = Color(0.36, 0.36, 0.39)        # fasteners
COL_WELD = Color(0.30, 0.28, 0.26)        # weld beads
COL_BLUE = Color(0.15, 0.28, 0.50)        # anodized caps (sparingly)
COL_GIMBAL = Color(0.27, 0.28, 0.30)      # gimbal / interface structure

# --------------------------------------------------------------------------
# Key documented dimensions (mm)
# --------------------------------------------------------------------------

ENGINE_HEIGHT = 3100.0          # published Raptor 3 length
EXIT_RADIUS = 650.0             # published 1.3 m diameter
THROAT_RADIUS = 111.0           # exit_r / sqrt(34.34) - published area ratio
THROAT_Z = 1250.0               # bell length (sea-level bell proportion)
CHAMBER_RADIUS = 185.0          # ~2.8 area contraction ratio
CHAMBER_TOP_Z = 1844.0
WALL = 16.0                     # visual regen jacket wall

FTP_X = -330.0                  # methane turbopump axis
OTP_X = 330.0                   # LOX turbopump axis

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
    """Vertical cylinder spanning z0..z1 centered on (x, y)."""
    return Cylinder(r, z1 - z0).moved(Pos(x, y, (z0 + z1) / 2.0))


def revolve_poly(points, arc=360.0):
    """Revolve a closed (r, z) polyline profile around the +Z axis."""
    with BuildPart() as bp:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(*points, close=True)
            make_face()
        revolve(axis=Axis.Z, revolution_arc=arc)
    return bp.part


def revolve_shell(points, wall):
    """Revolve a smooth spline wall profile (single seamless surface)."""
    inner = [(r - wall, z) for r, z in reversed(points)]
    with BuildPart() as bp:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Spline(*points)
                Line(points[-1], inner[0])
                Spline(*inner)
                Line(inner[-1], points[0])
            make_face()
        revolve(axis=Axis.Z)
    return bp.part


def pipe(points, r, bend=70.0):
    """Sweep a circular section along a filleted 3D polyline.

    Falls back to smaller corner radii when a requested fillet does not fit
    the local segment lengths (cast-elbow look instead of a failed build).
    """
    pts = [Vector(*p) for p in points]
    tangent = (pts[1] - pts[0]).normalized()
    radii = [bend, bend * 0.7, bend * 0.5, bend * 0.3, 20.0] if bend > 0 else [0.0]
    last_error = None
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
        except Exception as exc:  # noqa: BLE001 - retry with a tighter bend
            last_error = exc
    raise last_error


def hex_prism(r, h):
    return extrude(RegularPolygon(r, 6), amount=h)


def make_bolt(shank_r, shank_l, head_r, head_h):
    """Hex bolt, head base at z=0 (head up, shank pointing down)."""
    return hex_prism(head_r, head_h) + vcyl(shank_r, -shank_l, 0.0)


BOLT_M12 = make_bolt(6.0, 30.0, 11.0, 9.0)
BOLT_M16 = make_bolt(8.0, 40.0, 14.0, 11.0)
BOLT_M8 = make_bolt(4.0, 20.0, 7.5, 6.5)


def bolt_ring(proto, name, cx, cy, z, ring_r, count, start=0.0):
    out = []
    for i in range(count):
        a = radians(start + i * 360.0 / count)
        inst = proto.moved(Location((cx + ring_r * cos(a), cy + ring_r * sin(a), z)))
        out.append(_part(inst, f"{name}:{i + 1}", COL_BOLT))
    return out


def bellows(x, y, z0, z1, core_r, conv_r, count, color=COL_STEEL):
    """Flex-joint bellows: core tube plus stacked convolution tori."""
    parts = [_part(vcyl(core_r, z0, z1, x, y), "bellows_core", color)]
    span = z1 - z0
    for i in range(count):
        zi = z0 + span * (i + 0.5) / count
        t = Torus(core_r + conv_r * 0.55, conv_r).moved(Pos(x, y, zi))
        parts.append(_part(t, f"bellows_convolution:{i + 1}", color))
    return parts


def weld_bead(x, y, z, major, minor=6.0):
    return Torus(major, minor).moved(Pos(x, y, z))


SENSOR_PROTO = hex_prism(17.0, 10.0) + vcyl(12.0, 10.0, 32.0) + vcyl(5.0, 32.0, 40.0)
CLAMP_PROTO = Box(28.0, 22.0, 14.0)


# --------------------------------------------------------------------------
# Nozzle bell (regeneratively cooled, ~34.3:1 sea-level bell)
# --------------------------------------------------------------------------

# Parabolic bell: wall angle blends from ~38 deg at the throat to ~8 deg at
# the exit (thrust-optimized truncated bell), matching the published 34.3:1
# sea-level expansion ratio at a 1.3 m exit.
_S_EXIT = tan(radians(8.0))
_BELL_C = EXIT_RADIUS - THROAT_RADIUS - _S_EXIT * THROAT_Z
_BELL_K = 2.2


def bell_radius(z):
    """Analytic bell contour radius at height z (z=0 exit, z=THROAT_Z throat)."""
    return (THROAT_RADIUS + _S_EXIT * (THROAT_Z - z)
            + _BELL_C * (1.0 - (z / THROAT_Z) ** _BELL_K))


BELL_PTS = [(round(bell_radius(z), 1), z) for z in (
    0.0, 80.0, 180.0, 300.0, 420.0, 540.0, 660.0, 780.0, 890.0, 990.0,
    1080.0, 1150.0, 1200.0, 1235.0, 1250.0)]


def build_nozzle():
    bell = _part(revolve_shell(BELL_PTS, WALL), "nozzle_bell", COL_NOZZLE)

    exit_ring = _part(
        Torus(EXIT_RADIUS - 4.0, 13.0).moved(Pos(0, 0, 10.0)),
        "nozzle_exit_stiffener_ring", COL_NOZZLE)
    throat_band = _part(
        Torus(THROAT_RADIUS + 10.0, 16.0).moved(Pos(0, 0, THROAT_Z)),
        "throat_closeout_band", COL_CHAMBER)

    # Methane regen inlet manifold ring partway down the bell.
    man_z = 520.0
    man_r = bell_radius(man_z) + 16.0
    manifold = _part(
        Torus(man_r, 26.0).moved(Pos(0, 0, man_z + 10.0)),
        "regen_inlet_manifold", COL_INCONEL)

    return _grp("nozzle_assembly", [bell, exit_ring, throat_band, manifold])


# --------------------------------------------------------------------------
# Combustion chamber + collection manifold
# --------------------------------------------------------------------------

CHAMBER_PTS = [
    (111.0, 1248.0), (118.0, 1285.0), (132.0, 1320.0), (152.0, 1360.0),
    (170.0, 1400.0), (182.0, 1440.0), (185.0, 1470.0), (185.0, CHAMBER_TOP_Z),
]


def build_chamber():
    pts = CHAMBER_PTS + [(185.0, 1650.0)]
    pts.sort(key=lambda p: p[1])
    liner = _part(revolve_shell(pts, WALL), "combustion_chamber_jacket", COL_CHAMBER)

    collector = _part(
        Torus(207.0, 26.0).moved(Pos(0, 0, 1810.0)),
        "regen_collection_manifold", COL_INCONEL)

    return _grp("combustion_chamber", [liner, collector])


# --------------------------------------------------------------------------
# Injector head, LOX dome, hot-gas entries
# --------------------------------------------------------------------------


def build_injector_head():
    parts = []
    flange = _part(vcyl(232.0, 1840.0, 1895.0), "injector_head_flange", COL_CAST)
    body = _part(vcyl(205.0, 1895.0, 1965.0), "injector_body", COL_CAST)
    parts += [flange, body]
    parts += bolt_ring(BOLT_M12, "bolt_injector_flange", 0, 0, 1895.0, 214.0, 24)
    parts.append(_part(Torus(216.0, 16.0).moved(Pos(0, 0, 1935.0)),
                       "injector_fuel_manifold", COL_COPPER))

    # LOX dome: quarter-ellipse revolve (a=200, b=120) on top of the body.
    dome_pts = [(200.0 * cos(radians(a)), 1965.0 + 120.0 * sin(radians(a)))
                for a in range(0, 91, 15)]
    dome_profile = [(200.0, 1965.0)] + dome_pts[1:] + [(0.0, 2085.0), (0.0, 1965.0)]
    dome = _part(revolve_poly(dome_profile), "lox_dome", COL_CAST)
    parts.append(dome)

    neck = _part(vcyl(85.0, 2073.0, 2200.0), "lox_dome_inlet_neck", COL_CAST)
    neck_flange = _part(vcyl(120.0, 2200.0, 2225.0), "lox_inlet_flange", COL_STEEL)
    parts += [neck, neck_flange]
    parts += bolt_ring(BOLT_M12, "bolt_lox_inlet_flange", 0, 0, 2225.0, 105.0, 12)

    return _grp("injector_head", parts)


# --------------------------------------------------------------------------
# Turbopump stacks (vertical: inducer -> volute -> turbine -> preburner)
# --------------------------------------------------------------------------


def _volute(px, scroll_r, minor_r, zc):
    """Pump volute scroll: 320-degree partial revolve of a circular section."""
    with BuildPart() as bp:
        with BuildSketch(Plane.XZ):
            with Locations((scroll_r, zc)):
                Circle(minor_r)
        revolve(axis=Axis.Z, revolution_arc=320.0)
    return bp.part.moved(Pos(px, 0, 0))


def _turbine_ribs(px, ring_r, z, count, rib=(70.0, 16.0, 60.0)):
    out = []
    proto = Box(*rib)
    for i in range(count):
        a = i * 360.0 / count
        loc = Location((px, 0, 0)) * Location((0, 0, 0), (0, 0, a)) * Location((ring_r, 0, z))
        out.append(_part(proto.moved(loc), f"turbine_cooling_rib:{i + 1}", COL_CAST_DARK))
    return out


def _torch_igniter(name, p0, p1, r=20.0):
    body = _part(pipe([p0, p1], r, bend=0), f"{name}_torch_igniter", COL_STEEL)
    d = (Vector(*p1) - Vector(*p0)).normalized()
    tip = Vector(*p1) + d * 18.0
    cap = _part(Sphere(r * 0.72).moved(Pos(tip.X, tip.Y, tip.Z)),
                f"{name}_igniter_exciter", COL_GOLD)
    return [body, cap]


def build_fuel_turbopump():
    x = FTP_X
    parts = []

    # Inlet flange + inducer housing (fed from the CH4 downcomer).
    parts.append(_part(vcyl(90.0, 1912.0, 1930.0, x), "ftp_inlet_flange", COL_STEEL))
    parts += bolt_ring(BOLT_M8, "bolt_ftp_inlet", x, 0, 1930.0, 79.0, 10)
    parts.append(_part(
        Cone(68.0, 98.0, 100.0).moved(Pos(x, 0, 1980.0)),
        "ftp_inducer_housing", COL_CAST))

    # HP methane pump volute + interstage spacer.
    parts.append(_part(_volute(x, 132.0, 58.0, 2065.0), "ftp_hp_volute", COL_CAST))
    parts.append(_part(vcyl(120.0, 2115.0, 2135.0, x), "ftp_interstage_ring", COL_STEEL))

    # Turbine housing with radial cooling ribs.
    parts.append(_part(vcyl(150.0, 2130.0, 2225.0, x), "ftp_turbine_housing", COL_CAST_DARK))
    parts += _turbine_ribs(x, 140.0, 2178.0, 10)

    # Fuel-rich preburner: flange, barrel, dome.
    parts.append(_part(vcyl(140.0, 2225.0, 2245.0, x), "fpb_mount_flange", COL_STEEL))
    parts += bolt_ring(BOLT_M12, "bolt_fpb_flange", x, 0, 2245.0, 128.0, 12)
    parts.append(_part(vcyl(118.0, 2245.0, 2475.0, x), "fuel_preburner_barrel", COL_CAST_DARK))
    dome_pts = [(118.0 * cos(radians(a)), 2475.0 + 60.0 * sin(radians(a)))
                for a in range(0, 91, 15)]
    dome_profile = [(118.0, 2475.0)] + dome_pts[1:] + [(0.0, 2535.0), (0.0, 2475.0)]
    parts.append(_part(revolve_poly(dome_profile).moved(Pos(x, 0, 0)),
                       "fuel_preburner_dome", COL_CAST_DARK))
    parts.append(_part(Torus(122.0, 10.0).moved(Pos(x, 0, 2480.0)),
                       "fpb_dome_weld_ring", COL_WELD))
    parts.append(_part(vcyl(26.0, 2528.0, 2560.0, x), "fpb_service_boss", COL_STEEL))

    # Fuel preburner oxidizer valve (FPOV) + electric actuator on the dome.
    parts.append(_part(vcyl(36.0, 2520.0, 2600.0, x, 55.0), "fpov_valve_body", COL_STEEL))
    parts.append(_part(Box(75.0, 60.0, 55.0).moved(Pos(x, 55.0, 2630.0)),
                       "fpov_electric_actuator", COL_BLACK))
    parts.append(_part(vcyl(9.0, 2600.0, 2640.0, x, 55.0), "fpov_drive_shaft", COL_STEEL))

    parts += _torch_igniter("fpb", (x + 35.0, -70.0, 2500.0), (x + 78.0, -118.0, 2570.0))

    # Main fuel valve + discharge manifold block under the volute exit.
    parts.append(_part(pipe([(x, -148.0, 2065.0), (x, -250.0, 1985.0)], 48.0, bend=0),
                       "ftp_discharge_duct", COL_CAST))
    parts.append(_part(Sphere(72.0).moved(Pos(x, -240.0, 1995.0)), "main_fuel_valve", COL_CAST))
    parts.append(_part(Box(96.0, 100.0, 82.0).moved(Pos(x, -352.0, 1995.0)),
                       "mfv_electric_actuator", COL_BLACK))
    parts.append(_part(
        Cylinder(30.0, 60.0, rotation=(90, 0, 0)).moved(Pos(x, -300.0, 1995.0)),
        "mfv_drive_coupling", COL_STEEL))
    parts.append(_part(Box(110.0, 95.0, 110.0).moved(Pos(x, -265.0, 1930.0)),
                       "fuel_distribution_block", COL_COPPER))

    # Braces tying the pump casing to the injector head.
    for sy, tag in ((1.0, "port"), (-1.0, "starboard")):
        parts.append(_part(
            pipe([(x + 30.0, sy * 90.0, 2040.0), (x + 115.0, sy * 58.0, 1905.0)], 16.0, bend=0),
            f"ftp_head_brace:{tag}", COL_STEEL))

    return _grp("fuel_turbopump", parts)


def build_ox_turbopump():
    x = OTP_X
    parts = []

    parts.append(_part(vcyl(104.0, 1912.0, 1930.0, x), "otp_inlet_flange", COL_STEEL))
    parts += bolt_ring(BOLT_M8, "bolt_otp_inlet", x, 0, 1930.0, 92.0, 12)
    parts.append(_part(
        Cone(78.0, 112.0, 110.0).moved(Pos(x, 0, 1985.0)),
        "otp_inducer_housing", COL_CAST))

    parts.append(_part(_volute(x, 148.0, 64.0, 2075.0), "otp_hp_volute", COL_CAST))
    parts.append(_part(vcyl(132.0, 2130.0, 2150.0, x), "otp_interstage_ring", COL_STEEL))

    parts.append(_part(vcyl(165.0, 2145.0, 2245.0, x), "otp_turbine_housing", COL_CAST_DARK))
    parts += _turbine_ribs(x, 155.0, 2195.0, 12)

    parts.append(_part(vcyl(152.0, 2245.0, 2265.0, x), "opb_mount_flange", COL_STEEL))
    parts += bolt_ring(BOLT_M12, "bolt_opb_flange", x, 0, 2265.0, 140.0, 12)
    parts.append(_part(vcyl(130.0, 2265.0, 2525.0, x), "ox_preburner_barrel", COL_CAST_DARK))
    dome_pts = [(130.0 * cos(radians(a)), 2525.0 + 62.0 * sin(radians(a)))
                for a in range(0, 91, 15)]
    dome_profile = [(130.0, 2525.0)] + dome_pts[1:] + [(0.0, 2587.0), (0.0, 2525.0)]
    parts.append(_part(revolve_poly(dome_profile).moved(Pos(x, 0, 0)),
                       "ox_preburner_dome", COL_CAST_DARK))
    parts.append(_part(Torus(134.0, 11.0).moved(Pos(x, 0, 2530.0)),
                       "opb_dome_weld_ring", COL_WELD))
    parts.append(_part(vcyl(28.0, 2580.0, 2614.0, x), "opb_service_boss", COL_STEEL))

    parts.append(_part(vcyl(38.0, 2570.0, 2655.0, x, 55.0), "opov_valve_body", COL_STEEL))
    parts.append(_part(Box(75.0, 60.0, 55.0).moved(Pos(x, 55.0, 2685.0)),
                       "opov_electric_actuator", COL_BLACK))
    parts.append(_part(vcyl(9.0, 2655.0, 2695.0, x, 55.0), "opov_drive_shaft", COL_STEEL))

    parts += _torch_igniter("opb", (x - 35.0, -70.0, 2545.0), (x - 78.0, -118.0, 2615.0), r=22.0)

    for sy, tag in ((1.0, "port"), (-1.0, "starboard")):
        parts.append(_part(
            pipe([(x - 30.0, sy * 90.0, 2050.0), (x - 115.0, sy * 58.0, 1905.0)], 16.0, bend=0),
            f"otp_head_brace:{tag}", COL_STEEL))

    return _grp("ox_turbopump", parts)


# --------------------------------------------------------------------------
# Main oxidizer valve above the LOX dome
# --------------------------------------------------------------------------


def build_main_ox_valve():
    parts = [
        _part(Sphere(95.0).moved(Pos(0, 0, 2290.0)), "main_ox_valve", COL_CAST),
        _part(Box(140.0, 100.0, 85.0).moved(Pos(0, 150.0, 2290.0)),
              "mov_electric_actuator", COL_BLACK),
        _part(Cylinder(30.0, 70.0, rotation=(90, 0, 0)).moved(Pos(0, 90.0, 2290.0)),
              "mov_drive_coupling", COL_STEEL),
        _part(vcyl(24.0, 2380.0, 2420.0), "mov_position_sensor", COL_STEEL),
        _part(vcyl(16.0, 2420.0, 2438.0), "mov_sensor_cap", COL_BLUE),
    ]
    return _grp("main_ox_valve_assembly", parts)


# --------------------------------------------------------------------------
# Propellant + hot-gas plumbing (documented FFSC cycle routing)
# --------------------------------------------------------------------------


def build_plumbing():
    parts = []

    # Hot-gas transfer ducts: turbine exhaust -> injector head (both sides).
    parts.append(_part(pipe(
        [(FTP_X, 0, 2178.0), (-282.0, 0, 2045.0), (-205.0, 0, 1968.0), (-148.0, 0, 1952.0)],
        75.0, bend=40.0), "fuel_rich_transfer_duct", COL_DUCT))
    parts.append(_part(pipe(
        [(OTP_X, 0, 2190.0), (282.0, 0, 2050.0), (205.0, 0, 1970.0), (148.0, 0, 1953.0)],
        80.0, bend=40.0), "ox_rich_transfer_duct", COL_DUCT))

    # Methane downcomers: fuel distribution block -> nozzle regen manifold.
    man_z = 530.0
    man_r = bell_radius(520.0) + 16.0
    end_a = radians(115.0)
    for sgn, tag, waypoints in (
        (-1.0, "starboard", [
            (FTP_X, -285.0, 1900.0), (-420.0, -330.0, 1700.0), (-350.0, -430.0, 1150.0),
            (-240.0, -465.0, 700.0),
            (man_r * cos(-end_a), man_r * sin(-end_a), man_z + 15.0)]),
        (1.0, "port", [
            (FTP_X, -285.0, 1900.0), (-480.0, -140.0, 1750.0), (-470.0, 180.0, 1400.0),
            (-330.0, 400.0, 950.0), (-230.0, 462.0, 640.0),
            (man_r * cos(end_a), man_r * sin(end_a), man_z + 15.0)]),
    ):
        parts.append(_part(pipe(waypoints, 30.0, bend=110.0),
                           f"fuel_downcomer:{tag}", COL_DUCT))

    # Regen return riser: collection manifold -> fuel preburner inlet.
    parts.append(_part(pipe(
        [(-195.0, -71.0, 1810.0), (-280.0, -160.0, 2000.0), (-360.0, -140.0, 2250.0),
         (-368.0, -70.0, 2400.0), (-352.0, -20.0, 2450.0)],
        26.0, bend=70.0), "fpb_fuel_feed_riser", COL_PIPE))

    # Injector fuel feed: collection manifold -> injector body.
    parts.append(_part(pipe(
        [(194.0, 71.0, 1810.0), (240.0, 95.0, 1890.0), (188.0, 42.0, 1945.0)],
        24.0, bend=45.0), "injector_fuel_feed", COL_PIPE))

    # Cross-feed: small fuel line to the ox preburner (FFSC fuel-lean flow).
    parts.append(_part(pipe(
        [(159.0, -133.0, 1810.0), (300.0, -190.0, 2050.0), (390.0, -140.0, 2300.0),
         (355.0, -45.0, 2430.0)],
        18.0, bend=55.0), "opb_fuel_cross_feed", COL_PIPE))

    # HP LOX main duct: OTP volute -> main ox valve.
    parts.append(_part(pipe(
        [(OTP_X, -170.0, 2075.0), (240.0, -235.0, 2140.0), (95.0, -185.0, 2245.0),
         (0.0, -60.0, 2280.0)],
        50.0, bend=70.0), "hp_lox_main_duct", COL_CAST))

    # HP LOX feed to the ox preburner.
    parts.append(_part(pipe(
        [(OTP_X, 168.0, 2075.0), (400.0, 180.0, 2260.0), (385.0, 95.0, 2430.0),
         (348.0, 35.0, 2470.0)],
        34.0, bend=60.0), "opb_lox_feed", COL_CAST))

    # Small LOX line to the fuel preburner (ox-lean flow).
    parts.append(_part(pipe(
        [(OTP_X, 150.0, 2110.0), (180.0, 260.0, 2350.0), (-100.0, 270.0, 2520.0),
         (-290.0, 95.0, 2540.0)],
        16.0, bend=55.0), "fpb_lox_cross_feed", COL_PIPE))

    # Torch igniter methane feed lines (fuel distribution block taps).
    parts.append(_part(pipe(
        [(FTP_X, -260.0, 1985.0), (-300.0, -180.0, 2200.0), (-268.0, -125.0, 2480.0),
         (-255.0, -118.0, 2560.0)],
        8.0, bend=40.0), "fpb_torch_feed_line", COL_PIPE))
    parts.append(_part(pipe(
        [(OTP_X, 120.0, 2110.0), (300.0, -60.0, 2350.0), (262.0, -110.0, 2560.0),
         (256.0, -115.0, 2600.0)],
        8.0, bend=40.0), "opb_torch_feed_line", COL_PIPE))

    # Chamber pressure sense lines: injector body -> transducer bosses.
    parts.append(_part(pipe(
        [(196.0, 30.0, 1930.0), (172.0, 118.0, 1870.0), (150.0, 148.0, 1845.0)],
        6.0, bend=25.0), "chamber_sense_line:port", COL_PIPE))
    parts.append(_part(pipe(
        [(-196.0, 30.0, 1930.0), (-172.0, 118.0, 1870.0), (-150.0, 148.0, 1845.0)],
        6.0, bend=25.0), "chamber_sense_line:starboard", COL_PIPE))

    # LOX downcomer: vehicle inlet -> OTP inducer inlet (prominent +X duct).
    parts.append(_part(pipe(
        [(210.0, 0.0, 2940.0), (445.0, 65.0, 2780.0), (555.0, 90.0, 2400.0),
         (555.0, 90.0, 2050.0), (460.0, 30.0, 1865.0), (336.0, 0.0, 1900.0)],
        80.0, bend=90.0), "lox_feed_downcomer", COL_DUCT))

    # CH4 downcomer: vehicle inlet -> FTP inducer inlet (prominent -X duct).
    parts.append(_part(pipe(
        [(-210.0, 0.0, 2940.0), (-345.0, 60.0, 2830.0), (-495.0, 105.0, 2620.0),
         (-520.0, 110.0, 2300.0), (-520.0, 110.0, 2000.0), (-455.0, 60.0, 1855.0),
         (-336.0, 0.0, 1892.0)],
        58.0, bend=90.0), "ch4_feed_downcomer", COL_DUCT))

    # Weld beads on the straight downcomer runs.
    for z in (2180.0, 2380.0):
        parts.append(_part(weld_bead(555.0, 90.0, z, 82.0, 7.0),
                           f"weld_bead_lox_downcomer:{int(z)}", COL_WELD))
    for z in (2050.0, 2250.0):
        parts.append(_part(weld_bead(-520.0, 110.0, z, 60.0, 6.0),
                           f"weld_bead_ch4_downcomer:{int(z)}", COL_WELD))

    return _grp("propellant_plumbing", parts)


# --------------------------------------------------------------------------
# Vehicle inlets (flanges + flex bellows through the interface plate)
# --------------------------------------------------------------------------


def build_inlets():
    parts = []

    # LOX inlet (+X): flange on the interface plate, bellows below.
    parts.append(_part(vcyl(100.0, 3078.0, 3100.0, 210.0), "lox_inlet_flange", COL_STEEL))
    parts += bolt_ring(BOLT_M12, "bolt_lox_vehicle_inlet", 210.0, 0, 3100.0, 88.0, 12)
    parts.append(_part(vcyl(78.0, 2940.0, 3078.0, 210.0), "lox_inlet_tube", COL_STEEL))
    for i, p in enumerate(bellows(210.0, 0.0, 2952.0, 3032.0, 78.0, 15.0, 5)):
        p.label = f"lox_inlet_{p.label}"
        parts.append(p)

    # CH4 inlet (-X).
    parts.append(_part(vcyl(80.0, 3078.0, 3100.0, -210.0), "ch4_inlet_flange", COL_STEEL))
    parts += bolt_ring(BOLT_M8, "bolt_ch4_vehicle_inlet", -210.0, 0, 3100.0, 70.0, 12)
    parts.append(_part(vcyl(58.0, 2940.0, 3078.0, -210.0), "ch4_inlet_tube", COL_STEEL))
    for i, p in enumerate(bellows(-210.0, 0.0, 2952.0, 3032.0, 58.0, 13.0, 5)):
        p.label = f"ch4_inlet_{p.label}"
        parts.append(p)

    return _grp("propellant_inlets", parts)


# --------------------------------------------------------------------------
# Thrust frame, gimbal cross, vehicle interface plate
# --------------------------------------------------------------------------


def build_gimbal_mount():
    parts = []

    # Four tapered thrust struts: injector flange -> gimbal ring.
    for i, az in enumerate((45.0, 135.0, 225.0, 315.0)):
        a = radians(az)
        p0 = (214.0 * cos(a), 214.0 * sin(a), 1890.0)
        p1 = (140.0 * cos(a), 140.0 * sin(a), 2830.0)
        parts.append(_part(pipe([p0, p1], 26.0, bend=0),
                           f"thrust_strut:{int(az)}", COL_CAST))

    parts.append(_part(Torus(140.0, 20.0).moved(Pos(0, 0, 2838.0)),
                       "gimbal_support_ring", COL_CAST))

    # Two-axis gimbal cross.
    parts.append(_part(Box(200.0, 120.0, 70.0).moved(Pos(0, 0, 2880.0)),
                       "gimbal_lower_yoke", COL_GIMBAL))
    parts.append(_part(
        Cylinder(34.0, 240.0, rotation=(0, 90, 0)).moved(Pos(0, 0, 2915.0)),
        "gimbal_pin_x", COL_STEEL))
    parts.append(_part(
        Cylinder(34.0, 240.0, rotation=(90, 0, 0)).moved(Pos(0, 0, 2915.0)),
        "gimbal_pin_y", COL_STEEL))
    parts.append(_part(Box(120.0, 200.0, 70.0).moved(Pos(0, 0, 2950.0)),
                       "gimbal_upper_yoke", COL_GIMBAL))

    parts.append(_part(vcyl(95.0, 2985.0, 3040.0), "gimbal_adapter_column", COL_GIMBAL))
    parts.append(_part(vcyl(310.0, 3040.0, 3078.0), "vehicle_interface_plate", COL_GIMBAL))
    parts += bolt_ring(BOLT_M16, "bolt_vehicle_interface", 0, 0, 3078.0, 278.0, 12)

    return _grp("thrust_frame_and_gimbal", parts)


# --------------------------------------------------------------------------
# Electric TVC actuators (interface plate rim -> injector head lugs)
# --------------------------------------------------------------------------


def build_tvc():
    """Compact electric TVC actuators bridging the vehicle interface plate to
    outrigger lugs on the gimbal support ring (engine-side stubs of the
    vehicle-side actuation, matching the clean Raptor 3 exterior)."""
    parts = []
    for az, tag in ((135.0, "pitch"), (225.0, "yaw")):
        a = radians(az)
        upper = Vector(280.0 * cos(a), 280.0 * sin(a), 3005.0)
        lower = Vector(172.0 * cos(a), 172.0 * sin(a), 2852.0)
        axis_dir = (lower - upper).normalized()
        length = (lower - upper).length
        split = upper + axis_dir * (length * 0.62)

        parts.append(_part(Box(70.0, 50.0, 46.0).moved(
            Location((280.0 * cos(a), 280.0 * sin(a), 3022.0), (0, 0, az))),
            f"tvc_upper_lug:{tag}", COL_GIMBAL))
        parts.append(_part(Box(64.0, 46.0, 52.0).moved(
            Location((178.0 * cos(a), 178.0 * sin(a), 2842.0), (0, 0, az))),
            f"tvc_ring_outrigger:{tag}", COL_CAST))

        parts.append(_part(pipe([tuple(upper), tuple(split)], 36.0, bend=0),
                           f"tvc_actuator_body:{tag}", COL_BLACK))
        parts.append(_part(pipe([tuple(split), tuple(lower)], 15.0, bend=0),
                           f"tvc_actuator_rod:{tag}", COL_STEEL))
        parts.append(_part(Sphere(30.0).moved(Pos(upper.X, upper.Y, upper.Z)),
                           f"tvc_upper_eye:{tag}", COL_STEEL))
        parts.append(_part(Sphere(24.0).moved(Pos(lower.X, lower.Y, lower.Z)),
                           f"tvc_lower_eye:{tag}", COL_STEEL))

        motor_at = upper + axis_dir * (length * 0.30)
        radial = Vector(cos(a), sin(a), 0.0)
        motor_pos = motor_at + radial * 44.0
        parts.append(_part(Box(80.0, 62.0, 62.0).moved(
            Location((motor_pos.X, motor_pos.Y, motor_pos.Z), (0, 0, az))),
            f"tvc_motor_housing:{tag}", COL_BLACK))

    return _grp("tvc_actuators", parts)


# --------------------------------------------------------------------------
# Engine controller, harness runs, cable clamps
# --------------------------------------------------------------------------


def build_avionics():
    parts = []
    cx, cy = -40.0, 330.0

    parts.append(_part(Box(280.0, 80.0, 380.0).moved(Pos(cx, cy, 2350.0)),
                       "engine_controller", COL_BLACK))
    for i in range(8):
        parts.append(_part(
            Box(270.0, 14.0, 8.0).moved(Pos(cx, cy + 47.0, 2210.0 + i * 40.0)),
            f"controller_heatsink_fin:{i + 1}", COL_BLACK))
    for i in range(5):
        parts.append(_part(vcyl(14.0, 2130.0, 2162.0, cx - 120.0 + i * 60.0, cy),
                           f"controller_connector:{i + 1}", COL_STEEL))

    # Mounting legs down to the thrust struts.
    parts.append(_part(pipe([(cx - 60.0, cy - 40.0, 2450.0), (-120.0, 130.0, 2500.0)],
                            12.0, bend=0), "controller_leg:aft", COL_STEEL))
    parts.append(_part(pipe([(cx + 70.0, cy - 40.0, 2380.0), (118.0, 125.0, 2450.0)],
                            12.0, bend=0), "controller_leg:fwd", COL_STEEL))

    harness = [
        ("harness_mov", [(cx - 60.0, cy - 10.0, 2140.0), (-80.0, 280.0, 2200.0),
                         (-30.0, 190.0, 2280.0)]),
        ("harness_fpov", [(cx - 120.0, cy, 2500.0), (-260.0, 260.0, 2600.0),
                          (-322.0, 110.0, 2638.0)]),
        ("harness_opov", [(cx + 120.0, cy, 2500.0), (240.0, 260.0, 2640.0),
                          (322.0, 110.0, 2692.0)]),
        ("harness_chamber_sensors", [(cx, cy - 10.0, 2160.0), (-20.0, 300.0, 1960.0),
                                     (60.0, 260.0, 1850.0), (150.0, 150.0, 1848.0)]),
        ("harness_nozzle_sensors", [(cx + 40.0, cy - 20.0, 2150.0), (140.0, 290.0, 1860.0),
                                    (120.0, 200.0, 1500.0), (160.0, 300.0, 1050.0),
                                    (200.0, 430.0, 650.0), (215.0, 462.0, 560.0)]),
        ("harness_igniters", [(cx - 100.0, cy - 10.0, 2200.0), (-260.0, 200.0, 2350.0),
                              (-300.0, -40.0, 2480.0), (-262.0, -100.0, 2540.0)]),
    ]
    for name, pts in harness:
        parts.append(_part(pipe(pts, 11.0, bend=45.0), name, COL_BLACK))

    clamp_spots = [
        (120.0, 200.0, 1500.0), (160.0, 300.0, 1050.0), (-25.0, 305.0, 2050.0),
        (245.0, 262.0, 2600.0), (-262.0, 262.0, 2560.0), (60.0, 300.0, 1900.0),
        (200.0, 430.0, 650.0),
    ]
    for i, (x, y, z) in enumerate(clamp_spots):
        parts.append(_part(CLAMP_PROTO.moved(Location((x, y, z))),
                           f"harness_clamp:{i + 1}", COL_STEEL))

    return _grp("avionics_and_harness", parts)


# --------------------------------------------------------------------------
# Sensors and small fittings
# --------------------------------------------------------------------------


def build_sensors():
    spots = [
        ("pt_chamber:port", 146.0, 146.0, 1836.0, COL_STEEL),
        ("pt_chamber:starboard", -146.0, 146.0, 1836.0, COL_STEEL),
        ("tc_fpb_dome", FTP_X, -40.0, 2530.0, COL_STEEL),
        ("tc_opb_dome", OTP_X, -40.0, 2582.0, COL_STEEL),
        ("pt_ftp_volute", -235.0, 80.0, 2115.0, COL_STEEL),
        ("pt_otp_volute", 235.0, 80.0, 2130.0, COL_STEEL),
        ("pt_hot_gas_duct", 200.0, 60.0, 2000.0, COL_STEEL),
        ("pt_regen_manifold", -146.0, -146.0, 1836.0, COL_STEEL),
    ]
    parts = []
    for name, x, y, z, col in spots:
        parts.append(_part(SENSOR_PROTO.moved(Location((x, y, z))), name, col))
    # Two anodized service-port caps (small color accents seen on hardware).
    parts.append(_part(vcyl(12.0, 2140.0, 2158.0, -260.0, -95.0), "service_port_cap:fuel", COL_BLUE))
    parts.append(_part(vcyl(12.0, 2150.0, 2168.0, 260.0, -95.0), "service_port_cap:ox", COL_BLUE))

    # Torch-igniter spark exciter boxes on the head flange, with HV leads.
    parts.append(_part(Box(92.0, 58.0, 52.0).moved(Pos(0.0, 254.0, 1925.0)),
                       "igniter_exciter:fuel_side", COL_BLACK))
    parts.append(_part(Box(92.0, 58.0, 52.0).moved(Pos(0.0, -254.0, 1925.0)),
                       "igniter_exciter:ox_side", COL_BLACK))
    parts.append(_part(pipe(
        [(-30.0, 250.0, 1950.0), (-180.0, 210.0, 2200.0), (-262.0, -60.0, 2450.0),
         (-252.0, -112.0, 2555.0)],
        7.0, bend=40.0), "exciter_lead:fpb", COL_BLACK))
    parts.append(_part(pipe(
        [(30.0, -250.0, 1950.0), (200.0, -230.0, 2250.0), (268.0, -140.0, 2480.0),
         (254.0, -116.0, 2600.0)],
        7.0, bend=40.0), "exciter_lead:opb", COL_BLACK))
    return _grp("sensors_and_fittings", parts)


# --------------------------------------------------------------------------
# Root assembly
# --------------------------------------------------------------------------


def build_engine():
    return _grp("raptor3_engine", [
        build_nozzle(),
        build_chamber(),
        build_injector_head(),
        build_fuel_turbopump(),
        build_ox_turbopump(),
        build_main_ox_valve(),
        build_plumbing(),
        build_inlets(),
        build_gimbal_mount(),
        build_tvc(),
        build_avionics(),
        build_sensors(),
    ])


def gen_step():
    return {
        "shape": build_engine(),
        "params": "raptor3.params.js",
    }
