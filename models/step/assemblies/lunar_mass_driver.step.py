"""SpaceX-inspired lunar mass driver launch complex - speculative concept.

Speculative concept scene (NOT a reconstruction of announced hardware): a
reusable lunar logistics launcher that electromagnetically accelerates cargo
canisters along a modular coil track built on the lunar surface. Framed as
industrial launch infrastructure for satellites, bulk cargo, and deep-space
industrial payloads.

Scene conventions:
- Units: millimeters. The scene is a compressed diorama (~200 m track) so the
  whole installation stays readable at thumbnail scale.
- Origin: start of the coil track (s = 0) at terrain level; the track runs
  along +X. Terrain top surface is z = 0. +Z is up.
- The track centerline is flat until a circular vertical easement curve of
  radius `track_curve_radius` pitches it up to `track_elevation_angle` at the
  muzzle. `track_frame()` is the single source of truth for that profile; the
  JS sidecar mirrors the same math for sled animation.
- Repeated units (track segments, coils, rovers, wings, pylons) are built once
  and instanced with `.moved()` so content-addressed meshing dedups them.
  Never call `.bounding_box()` on shared shapes here; all placements are
  analytic.
"""

from dataclasses import dataclass
from math import atan2, cos, degrees, radians, sin

from build123d import Box, Color, Compound, Cone, Cylinder, Location, Sphere, Torus


# --------------------------------------------------------------------------
# Named scene parameters
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MassDriverParams:
    """Named parameters of the lunar mass driver concept scene.

    Geometry parameters change the built STEP. Presentation parameters
    (`coil_glow_intensity`, `payload_release_angle`,
    `acceleration_visual_intensity`, `lunar_dust_level`, visibility toggles,
    `accent_color_palette`, `cutaway_fraction`, `exploded_distance`) also have
    live viewer-time controls in `lunar_mass_driver.params.js`; their values
    here set the baked defaults. Regenerating with a different
    `track_segment_count`, `service_gantry_count`, `radiator_panel_count`,
    `rover_count`, or `solar_farm_area` changes occurrence ids, so the sidecar
    feature table mirrors the defaults below.
    """

    # Track
    track_length: float = 180_000.0            # coil-tunnel arc length (mm)
    track_segment_count: int = 12              # repeating coil segments
    track_curve_radius: float = 220_000.0      # vertical easement radius (mm)
    track_elevation_angle: float = 10.0        # muzzle pitch (deg)
    coil_count_per_segment: int = 5
    coil_glow_intensity: float = 0.85          # 0..2, baked coil brightness + viewer emissive default
    rail_spacing: float = 1_800.0              # guide rail center-to-center (mm)

    # Sled and payload
    sled_length: float = 9_000.0
    sled_levitation_gap: float = 120.0         # rail top to carriage underside (mm)
    payload_canister_diameter: float = 2_400.0
    payload_canister_length: float = 6_000.0
    payload_release_angle: float = 10.0        # visual departure angle (deg), sidecar default
    acceleration_visual_intensity: float = 0.8  # 0..1, sidecar launch-glow default

    # Site infrastructure
    service_gantry_count: int = 3
    gantry_position: float = 0.0               # 0 = boom docked over track, 1 = slewed away
    dust_shield_height: float = 2_600.0        # shield top above deck (mm)
    foundation_anchor_depth: float = 2_000.0   # regolith anchor pile depth below grade (mm)
    solar_farm_area: float = 1_800.0           # total wing area (m^2)
    solar_panel_deploy_angle: float = 25.0     # wing tilt from horizontal (deg)
    radiator_panel_count: int = 8
    radiator_panel_angle: float = 60.0         # deploy angle from horizontal (deg)
    power_cable_density: int = 3               # conduit runs per tray/trunk
    control_tower_height: float = 18_000.0
    rover_count: int = 4

    # Presentation / composition
    starship_lander_visibility: bool = True
    lunar_dust_level: float = 0.5              # 0..1 plume prominence
    earth_visibility: bool = True
    accent_color_palette: str = "spacex"       # spacex | aurora | ember
    cutaway_fraction: float = 0.0              # leading fraction of segments built with low shields
    exploded_distance: float = 0.0             # 0..1 baked static explode of root groups


DEFAULTS = MassDriverParams()

# Fixed layout constants derived once (not user parameters).
DECK_HEIGHT = 2_400.0        # deck top above terrain on the flat run (mm)
BED_THICKNESS = 800.0
BED_WIDTH = 4_200.0
APRON_LENGTH = 18_000.0      # breech loading apron behind s = 0 (no coils)
SLED_HOME_S = -9_000.0       # baked sled center position (on the apron)
COIL_MAJOR_R = 2_200.0
COIL_MINOR_R = 220.0
COIL_CENTER_Z = 1_600.0      # coil center above deck top (local z)
ROAD_Y = -10_000.0
PAD_CENTER = (25_000.0, -32_000.0)
GANTRY_PIVOT_Y = 6_500.0
GANTRY_XS = (20_000.0, 36_000.0, 52_000.0)   # extended by pattern for higher counts
GANTRY_RETRACT_DEG = 120.0
CRANE_X = -9_000.0
RADIATOR_ROW_Y = -23_000.0
RADIATOR_HINGE_Z = 1_500.0
RADIATOR_X0 = 42_000.0
RADIATOR_PITCH = 7_000.0
SOLAR_ROW_YS = (25_000.0, 34_000.0, 43_000.0)
SOLAR_X0 = 60_000.0
SOLAR_PITCH = 17_500.0  # > wing width so adjacent panels never touch
SOLAR_WING_W = 16_000.0      # along X (m^2 sizing uses W * H)
SOLAR_WING_H = 6_500.0
TOWER_POS = (2_000.0, 14_000.0)
EARTH_POS = (150_000.0, 55_000.0, 65_000.0)
TRUNK_Y = -5_200.0

# Accent palettes: coil glow, power conduits, safety markings (linear RGB).
ACCENT_PALETTES = {
    "spacex": {"coil": (0.14, 0.52, 1.00), "conduit": (0.00, 0.78, 0.90), "marking": (0.82, 0.06, 0.06)},
    "aurora": {"coil": (0.10, 0.90, 0.72), "conduit": (0.55, 0.35, 1.00), "marking": (0.92, 0.92, 0.96)},
    "ember":  {"coil": (1.00, 0.45, 0.10), "conduit": (1.00, 0.72, 0.18), "marking": (0.92, 0.92, 0.96)},
}

# Static explode directions per root group (unit vectors, scaled by
# exploded_distance * EXPLODE_SCALE). Mirrored by the JS sidecar.
EXPLODE_SCALE = 14_000.0
EXPLODE_DIRS = {
    "terrain": (0.0, 0.0, -0.5),
    "earth": (0.0, 0.0, 0.4),
    "track": (0.0, 0.0, 0.35),
    "foundations": (0.0, 0.0, -0.2),
    "sled": (0.0, 0.0, 1.0),
    "gantries": (0.0, 0.8, 0.3),
    "loading": (-0.6, -0.5, 0.2),
    "lander": (0.3, -0.9, 0.2),
    "tower": (-0.5, 0.7, 0.3),
    "solar": (0.2, 0.9, 0.35),
    "radiators": (0.2, -0.9, 0.35),
    "power": (0.0, -0.6, -0.15),
    "rovers": (0.0, -0.4, 0.15),
    "drones": (0.0, 0.0, 0.8),
    "dust": (0.0, 0.0, 0.1),
}

# Base colors (linear RGB, matching starship_common conventions).
COL_TERRAIN = Color(0.30, 0.30, 0.31, 1.0)
COL_TERRAIN_DARK = Color(0.22, 0.22, 0.23, 1.0)
COL_PAD = Color(0.42, 0.42, 0.44, 1.0)
COL_WHITE = Color(0.86, 0.87, 0.89, 1.0)      # matte white industrial modules
COL_WHITE_DIM = Color(0.72, 0.73, 0.76, 1.0)
COL_STEEL = Color(0.64, 0.65, 0.68, 1.0)      # stainless Starship-derived hardware
COL_STEEL_DARK = Color(0.48, 0.49, 0.52, 1.0)
COL_RAIL = Color(0.55, 0.57, 0.62, 1.0)
COL_BLACK = Color(0.055, 0.055, 0.065, 1.0)   # radiator panels
COL_GOLD = Color(0.85, 0.60, 0.16, 1.0)       # thermal blankets
COL_SOLAR = Color(0.07, 0.11, 0.30, 1.0)
COL_GLASS = Color(0.05, 0.75, 0.90, 0.45)     # control-room glazing
COL_DUST = Color(1.00, 0.44, 0.14, 1.0)       # orange dust plumes (alpha set per level)
COL_EARTH = Color(0.16, 0.36, 0.85, 1.0)
COL_EARTH_HAZE = Color(0.92, 0.95, 1.00, 0.85)


def _palette(p: MassDriverParams) -> dict:
    return ACCENT_PALETTES.get(p.accent_color_palette, ACCENT_PALETTES["spacex"])


def _rgba(rgb, alpha: float = 1.0) -> Color:
    return Color(rgb[0], rgb[1], rgb[2], alpha)


def _tinted(part, label: str, color: Color):
    part.label = label
    part.color = color
    return part


def _grp(label: str, parts: list) -> Compound:
    return Compound(obj=parts, children=parts, label=label)


def _inst(base, label: str, loc: Location):
    copy = base.moved(loc)
    copy.label = label
    return copy


def _yaw_pitch_loc(pos, pitch_deg: float = 0.0, yaw_deg: float = 0.0) -> Location:
    """Translate, then yaw about +Z, then pitch the +X axis up by pitch_deg."""
    loc = Location(pos)
    if yaw_deg:
        loc = loc * Location((0, 0, 0), (0, 0, yaw_deg))
    if pitch_deg:
        # Rotating about +Y by -pitch maps +X toward +Z (pitches the nose up).
        loc = loc * Location((0, 0, 0), (0, -pitch_deg, 0))
    return loc


# --------------------------------------------------------------------------
# Track centerline profile (mirrored by lunar_mass_driver.params.js)
# --------------------------------------------------------------------------


def track_frame(p: MassDriverParams, s: float) -> tuple[float, float, float]:
    """Deck-top centerline frame at arc length s: (x, z, pitch_rad).

    Flat at DECK_HEIGHT until the vertical easement (radius
    track_curve_radius) lifts the final run to track_elevation_angle. Negative
    s covers the flat breech apron.
    """
    theta = radians(p.track_elevation_angle)
    arc = p.track_curve_radius * theta
    s0 = max(0.0, p.track_length - arc)
    if theta <= 0.0 or s <= s0:
        return s, DECK_HEIGHT, 0.0
    phi = min(theta, (s - s0) / p.track_curve_radius)
    x = s0 + p.track_curve_radius * sin(phi)
    z = DECK_HEIGHT + p.track_curve_radius * (1.0 - cos(phi))
    # Past the muzzle (only used for terminal placement), continue straight.
    if s > p.track_length:
        extra = s - p.track_length
        x += extra * cos(theta)
        z += extra * sin(theta)
    return x, z, phi


def _chord_frame(p: MassDriverParams, sa: float, sb: float) -> tuple[tuple[float, float, float], float]:
    """Midpoint position and pitch (deg) of the straight chord from sa to sb."""
    xa, za, _ = track_frame(p, sa)
    xb, zb, _ = track_frame(p, sb)
    mid = ((xa + xb) / 2.0, 0.0, (za + zb) / 2.0)
    pitch = degrees(atan2(zb - za, xb - xa))
    return mid, pitch


# --------------------------------------------------------------------------
# Track segments
# --------------------------------------------------------------------------


def _make_track_segment(p: MassDriverParams, seg_len: float, cutaway: bool) -> Compound:
    """One repeating coil segment, local origin at deck-top center.

    Child order is load-bearing for sidecar refs:
    1 bed, 2 rail_left, 3 rail_right, 4 coil_array, 5 magnet_housing_array,
    6 dust_shield_left, 7 dust_shield_right, 8 cable_tray, 9 cooling_loop_left,
    10 cooling_loop_right, 11 safety_markings.
    """
    pal = _palette(p)
    glow = min(1.0, max(0.0, p.coil_glow_intensity / 2.0))
    coil_rgb = tuple(c + (1.0 - c) * 0.45 * glow for c in pal["coil"])
    shield_h = p.dust_shield_height * (0.15 if cutaway else 1.0)

    bed = _tinted(
        Box(seg_len, BED_WIDTH, BED_THICKNESS).moved(Location((0, 0, -BED_THICKNESS / 2))),
        "track_bed_truss_module", COL_WHITE,
    )

    rail = Box(seg_len, 260, 220)
    rail_left = _tinted(rail.moved(Location((0, +p.rail_spacing / 2, 110))), "guide_rail_left", COL_RAIL)
    rail_right = _tinted(rail.moved(Location((0, -p.rail_spacing / 2, 110))), "guide_rail_right", COL_RAIL)

    n_coil = max(1, p.coil_count_per_segment)
    coil_pitch = seg_len / n_coil
    coil = Torus(COIL_MAJOR_R, COIL_MINOR_R).moved(Location((0, 0, 0), (0, 90, 0)))
    yoke = Box(700, 5_400, 1_900)
    coils = []
    yokes = []
    for k in range(n_coil):
        x = -seg_len / 2 + coil_pitch * (k + 0.5)
        coils.append(_inst(coil, f"accelerator_coil_{k + 1:02d}", Location((x, 0, COIL_CENTER_Z))))
        yokes.append(_inst(yoke, f"superconducting_magnet_housing_{k + 1:02d}", Location((x, 0, 100))))
        yokes[-1].color = COL_WHITE_DIM
    for c in coils:
        c.color = _rgba(coil_rgb)
    coil_array = _grp("coil_array", coils)
    yoke_array = _grp("magnet_housing_array", yokes)

    shield = Box(seg_len, 160, BED_THICKNESS + shield_h)
    shield_z = (shield_h - BED_THICKNESS) / 2
    shield_left = _tinted(shield.moved(Location((0, +2_780, shield_z))), "dust_shield_left", COL_WHITE)
    shield_right = _tinted(shield.moved(Location((0, -2_780, shield_z))), "dust_shield_right", COL_WHITE)

    tray_parts = [
        _tinted(Box(seg_len, 700, 160).moved(Location((0, -3_400, -650))), "cable_tray_channel", COL_STEEL_DARK)
    ]
    n_pipe = max(1, p.power_cable_density)
    pipe = Cylinder(150, seg_len).moved(Location((0, 0, 0), (0, 90, 0)))
    for k in range(n_pipe):
        y = -3_400 + (k - (n_pipe - 1) / 2.0) * 320
        tray_parts.append(_inst(pipe, f"power_conduit_{k + 1:02d}", Location((0, y, -450))))
        tray_parts[-1].color = _rgba(pal["conduit"])
    cable_tray = _grp("cable_tray", tray_parts)

    cool = Cylinder(140, seg_len).moved(Location((0, 0, 0), (0, 90, 0)))
    cooling_left = _inst(cool, "cooling_loop_left", Location((0, +2_400, 950)))
    cooling_left.color = COL_STEEL
    cooling_right = _inst(cool, "cooling_loop_right", Location((0, -2_400, 950)))
    cooling_right.color = COL_STEEL

    mark = Box(600, BED_WIDTH, 60)
    markings = _grp(
        "safety_markings",
        [
            _inst(mark, "deck_marking_fore", Location((seg_len / 2 - 350, 0, 30))),
            _inst(mark, "deck_marking_aft", Location((-seg_len / 2 + 350, 0, 30))),
        ],
    )
    for child in markings.children:
        child.color = _rgba(pal["marking"])

    return _grp(
        "coil_track_segment",
        [bed, rail_left, rail_right, coil_array, yoke_array,
         shield_left, shield_right, cable_tray, cooling_left, cooling_right, markings],
    )


def _make_breech_terminal(p: MassDriverParams, pal: dict) -> Compound:
    """Open loading apron behind s=0: deck, rails, backstop, buffers."""
    cx = -APRON_LENGTH / 2
    parts = [
        _tinted(Box(APRON_LENGTH, BED_WIDTH, BED_THICKNESS)
                .moved(Location((cx, 0, DECK_HEIGHT - BED_THICKNESS / 2))), "breech_apron_deck", COL_WHITE),
        _tinted(Box(APRON_LENGTH, 260, 220)
                .moved(Location((cx, +p.rail_spacing / 2, DECK_HEIGHT + 110))), "breech_rail_left", COL_RAIL),
        _tinted(Box(APRON_LENGTH, 260, 220)
                .moved(Location((cx, -p.rail_spacing / 2, DECK_HEIGHT + 110))), "breech_rail_right", COL_RAIL),
        _tinted(Box(1_000, 5_400, 4_500)
                .moved(Location((-APRON_LENGTH - 500, 0, DECK_HEIGHT + 1_450))), "breech_backstop_wall", COL_WHITE_DIM),
        _tinted(Cylinder(320, 1_600).moved(Location((0, 0, 0), (0, 90, 0)))
                .moved(Location((-APRON_LENGTH + 800, +p.rail_spacing / 2, DECK_HEIGHT + 700))),
                "breech_buffer_left", COL_STEEL_DARK),
        _tinted(Cylinder(320, 1_600).moved(Location((0, 0, 0), (0, 90, 0)))
                .moved(Location((-APRON_LENGTH + 800, -p.rail_spacing / 2, DECK_HEIGHT + 700))),
                "breech_buffer_right", COL_STEEL_DARK),
    ]
    stripe = _tinted(Box(APRON_LENGTH, 300, 60)
                     .moved(Location((cx, 0, DECK_HEIGHT + 30))), "breech_centerline_marking", _rgba(pal["marking"]))
    parts.append(stripe)
    return _grp("breech_loading_terminal", parts)


def _make_muzzle_terminal(p: MassDriverParams, pal: dict) -> Compound:
    """Exit aperture ring and supports at the elevated end of the track."""
    x_e, z_e, pitch = track_frame(p, p.track_length + 1_200.0)
    pitch_deg = degrees(pitch)
    ring = _tinted(Torus(2_900, 300).moved(Location((0, 0, 0), (0, 90, 0))), "muzzle_exit_ring", COL_GOLD)
    ring = _inst(ring, "muzzle_exit_ring", _yaw_pitch_loc((x_e, 0, z_e + COIL_CENTER_Z), pitch_deg))
    ring.color = COL_GOLD
    halo = _inst(Torus(3_300, 90).moved(Location((0, 0, 0), (0, 90, 0))), "muzzle_marking_ring",
                 _yaw_pitch_loc((x_e, 0, z_e + COIL_CENTER_Z), pitch_deg))
    halo.color = _rgba(pal["marking"])
    # Legs rise to the ring's widest points (y = +/- major radius, ring center height).
    leg_h = z_e + COIL_CENTER_Z + 150.0
    leg = Box(600, 600, leg_h)
    legs = [
        _inst(leg, "muzzle_support_leg_left", Location((x_e, +2_900, leg_h / 2))),
        _inst(leg, "muzzle_support_leg_right", Location((x_e, -2_900, leg_h / 2))),
    ]
    for one in legs:
        one.color = COL_WHITE_DIM
    xf, zf, pf = track_frame(p, p.track_length - 4_000.0)
    fin = Box(3_600, 220, 1_100)
    fins = [
        _inst(fin, "brake_fin_left", _yaw_pitch_loc((xf, +2_950, zf + 550), degrees(pf))),
        _inst(fin, "brake_fin_right", _yaw_pitch_loc((xf, -2_950, zf + 550), degrees(pf))),
    ]
    for one in fins:
        one.color = _rgba(pal["marking"])
    return _grp("muzzle_terminal", [ring, halo, *legs, *fins])


def make_track_group(p: MassDriverParams) -> Compound:
    seg_len = p.track_length / p.track_segment_count
    pal = _palette(p)
    cut_count = int(round(min(1.0, max(0.0, p.cutaway_fraction)) * p.track_segment_count))
    seg_full = _make_track_segment(p, seg_len, cutaway=False)
    seg_cut = _make_track_segment(p, seg_len, cutaway=True) if cut_count else None

    segments = []
    for i in range(p.track_segment_count):
        sa, sb = i * seg_len, (i + 1) * seg_len
        mid, pitch = _chord_frame(p, sa, sb)
        base = seg_cut if (seg_cut is not None and i < cut_count) else seg_full
        segments.append(_inst(base, f"track_segment_{i + 1:02d}", _yaw_pitch_loc(mid, pitch)))

    segments.append(_make_breech_terminal(p, pal))
    segments.append(_make_muzzle_terminal(p, pal))
    return _grp("electromagnetic_launch_track", segments)


def make_foundation_group(p: MassDriverParams) -> Compound:
    """Pylon pairs + regolith anchor piles at every segment boundary."""
    seg_len = p.track_length / p.track_segment_count
    boundaries = [-APRON_LENGTH, -APRON_LENGTH / 2] + [i * seg_len for i in range(p.track_segment_count + 1)]
    pile = Cylinder(350, p.foundation_anchor_depth)
    parts = []
    for j, s in enumerate(boundaries):
        x, z, _ = track_frame(p, min(s, p.track_length))
        h = z - BED_THICKNESS + 150.0  # overlap 150 into the bed underside
        pylon = Box(800, 800, h)
        for side, y in (("left", 1_600.0), ("right", -1_600.0)):
            parts.append(_inst(pylon, f"foundation_pylon_{j + 1:02d}_{side}", Location((x, y, h / 2))))
            parts[-1].color = COL_WHITE_DIM
            parts.append(_inst(pile, f"regolith_anchor_pile_{j + 1:02d}_{side}",
                               Location((x, y, -p.foundation_anchor_depth / 2))))
            parts[-1].color = COL_STEEL_DARK
    return _grp("regolith_anchored_foundations", parts)


# --------------------------------------------------------------------------
# Sled + payload
# --------------------------------------------------------------------------


def sled_home_position(p: MassDriverParams) -> tuple[float, float, float]:
    x, z, _ = track_frame(p, SLED_HOME_S)
    return x, 0.0, z


RAIL_TOP = 220.0
SKID_HEIGHT = 200.0
PLATE_THICKNESS = 300.0
SADDLE_HEIGHT = 500.0
SADDLE_NEST = 250.0  # how deep the canister nests into the saddle V


def payload_axis_height(p: MassDriverParams) -> float:
    """Canister axis height above deck top (local z), stacked from the rail.

    rail top + levitation gap + skid + deck plate + saddle + canister radius,
    less the saddle nesting depth. With the default coil aperture (inner
    radius 1980 about z=1600) the canister diameter must stay <= ~2500.
    """
    return (RAIL_TOP + p.sled_levitation_gap + SKID_HEIGHT + PLATE_THICKNESS
            + SADDLE_HEIGHT + p.payload_canister_diameter / 2 - SADDLE_NEST)


def make_sled_group(p: MassDriverParams) -> Compound:
    """Levitated sled at its baked home pose on the breech apron.

    Children: 1 acceleration_carriage, 2 payload_cradle, 3 payload_canister.
    Local origin at sled center on the deck top; everything must clear the
    coil aperture (inner radius COIL_MAJOR_R - COIL_MINOR_R about
    (y=0, z=COIL_CENTER_Z)).
    """
    pal = _palette(p)
    gap = p.sled_levitation_gap
    skid_z = RAIL_TOP + gap + SKID_HEIGHT / 2  # levitation pads hover over the rails
    plate_z0 = RAIL_TOP + gap + SKID_HEIGHT
    plate_mid = plate_z0 + PLATE_THICKNESS / 2

    carriage_parts = [
        _tinted(Box(p.sled_length, 2_400, PLATE_THICKNESS)
                .moved(Location((0, 0, plate_mid))), "carriage_deck_plate", COL_WHITE),
    ]
    skid = Box(1_600, 460, SKID_HEIGHT)
    for i, x in enumerate((-p.sled_length / 2 + 1_000, p.sled_length / 2 - 1_000)):
        for side, y in (("left", p.rail_spacing / 2), ("right", -p.rail_spacing / 2)):
            skid_inst = _inst(skid, f"levitation_skid_{i + 1}_{side}", Location((x, y, skid_z)))
            skid_inst.color = _rgba(pal["coil"])
            carriage_parts.append(skid_inst)
    nose = Cone(1_050, 120, 1_900).moved(Location((0, 0, 0), (0, 90, 0)))
    carriage_parts.append(_inst(nose, "sled_nose_fairing", Location((p.sled_length / 2 + 950, 0, plate_mid))))
    carriage_parts[-1].color = COL_WHITE
    tail = Cone(1_050, 320, 1_100).moved(Location((0, 0, 0), (0, -90, 0)))
    carriage_parts.append(_inst(tail, "sled_tail_fairing", Location((-p.sled_length / 2 - 550, 0, plate_mid))))
    carriage_parts[-1].color = COL_WHITE
    carriage = _grp("acceleration_carriage", carriage_parts)

    saddle = Box(700, 2_200, SADDLE_HEIGHT)
    pin = Box(300, 300, 700)
    axis_z = payload_axis_height(p)
    cradle_parts = []
    for i, x in enumerate((-1_800.0, 1_800.0)):
        cradle_parts.append(_inst(saddle, f"payload_saddle_{i + 1}",
                                  Location((x, 0, plate_z0 + PLATE_THICKNESS + SADDLE_HEIGHT / 2))))
        cradle_parts[-1].color = COL_WHITE_DIM
        for side, y in (("left", 1_250.0), ("right", -1_250.0)):
            cradle_parts.append(_inst(pin, f"payload_clamp_pin_{i + 1}_{side}",
                                      Location((x, y, axis_z))))
            cradle_parts[-1].color = _rgba(pal["marking"])
    cradle = _grp("payload_cradle", cradle_parts)

    r = p.payload_canister_diameter / 2
    length = p.payload_canister_length
    body = _tinted(Cylinder(r, length).moved(Location((0, 0, 0), (0, 90, 0)))
                   .moved(Location((0, 0, axis_z))), "payload_canister_body", COL_STEEL)
    dome = _tinted(Sphere(r, arc_size1=0).moved(Location((0, 0, 0), (0, 90, 0)))
                   .moved(Location((length / 2, 0, axis_z))), "payload_canister_nose_dome", COL_STEEL)
    collar = _tinted(Cylinder(r * 0.62, 260).moved(Location((0, 0, 0), (0, 90, 0)))
                     .moved(Location((-length / 2 - 130, 0, axis_z))), "payload_docking_collar", COL_STEEL_DARK)
    # Bands sit proud of the skin by ~25 mm while keeping coil-aperture clearance.
    band = Torus(r - 30, 55).moved(Location((0, 0, 0), (0, 90, 0)))
    band_a = _inst(band, "thermal_blanket_band_fore", Location((length * 0.22, 0, axis_z)))
    band_a.color = COL_GOLD
    band_b = _inst(band, "thermal_blanket_band_aft", Location((-length * 0.22, 0, axis_z)))
    band_b.color = COL_GOLD
    stripe = _inst(Torus(r - 40, 40).moved(Location((0, 0, 0), (0, 90, 0))),
                   "payload_marking_ring", Location((-length * 0.40, 0, axis_z)))
    stripe.color = _rgba(pal["marking"])
    canister = _grp("payload_canister", [body, dome, collar, band_a, band_b, stripe])

    sled = _grp("levitated_payload_sled", [carriage, cradle, canister])
    return _inst(sled, "levitated_payload_sled", Location(sled_home_position(p)))


# --------------------------------------------------------------------------
# Service gantries, loading station, lander
# --------------------------------------------------------------------------


def gantry_positions(p: MassDriverParams) -> list[float]:
    n = max(0, p.service_gantry_count)
    xs = list(GANTRY_XS)
    while len(xs) < n:
        xs.append(xs[-1] + 16_000.0)
    return xs[:n]


def _make_gantry(p: MassDriverParams, pal: dict) -> Compound:
    """Cantilever service gantry; local origin at the slew-column axis on grade.

    The boom points -Y (over the track). Retraction slews the whole group
    about the local +Z axis (sidecar rotates by gantry_position * 120 deg).
    """
    parts = [
        _tinted(Box(3_000, 3_000, 2_800).moved(Location((0, 0, 1_400))), "gantry_pedestal", COL_WHITE),
        _tinted(Cylinder(700, 5_800).moved(Location((0, 0, 2_800 + 2_900))), "gantry_slew_column", COL_WHITE_DIM),
        _tinted(Box(900, 9_600, 700).moved(Location((0, -GANTRY_PIVOT_Y + 1_800, 8_100))), "gantry_service_boom", COL_WHITE),
        _tinted(Box(700, 700, 1_500).moved(Location((0, -GANTRY_PIVOT_Y, 7_300))), "gantry_tool_head", _rgba(pal["marking"])),
        _tinted(Box(800, 1_100, 900).moved(Location((0, -GANTRY_PIVOT_Y + 4_000, 7_300))), "gantry_service_pod_inner", COL_GOLD),
        _tinted(Box(800, 1_100, 900).moved(Location((0, -GANTRY_PIVOT_Y + 6_800, 7_300))), "gantry_service_pod_outer", COL_STEEL_DARK),
    ]
    return _grp("service_gantry", parts)


def make_gantry_group(p: MassDriverParams) -> Compound:
    pal = _palette(p)
    base = _make_gantry(p, pal)
    slew = min(1.0, max(0.0, p.gantry_position)) * GANTRY_RETRACT_DEG
    gantries = []
    for i, x in enumerate(gantry_positions(p)):
        loc = Location((x, GANTRY_PIVOT_Y, 0)) * Location((0, 0, 0), (0, 0, slew))
        gantries.append(_inst(base, f"service_gantry_{i + 1:02d}", loc))
    return _grp("service_gantry_row", gantries)


def make_loading_station_group(p: MassDriverParams) -> Compound:
    """Breech-side platform and payload transfer crane (children: platform, crane)."""
    pal = _palette(p)
    plat_parts = [
        _tinted(Box(9_000, 3_400, DECK_HEIGHT).moved(Location((CRANE_X, -6_600, DECK_HEIGHT / 2))),
                "loading_platform_deck", COL_WHITE),
        _tinted(Box(2_600, 3_000, 1_200).moved(Location((CRANE_X - 5_800, -6_600, 600))),
                "loading_stair_lower", COL_WHITE_DIM),
        _tinted(Box(2_600, 3_000, 2_400 - 1_200).moved(Location((CRANE_X - 4_200, -6_600, 1_200 + 600))),
                "loading_stair_upper", COL_WHITE_DIM),
        _tinted(Box(1_800, 1_800, 1_900).moved(Location((CRANE_X + 3_200, -6_600, DECK_HEIGHT + 950))),
                "loading_control_kiosk", COL_GOLD),
        _tinted(Box(9_000, 200, 200).moved(Location((CRANE_X, -8_200, DECK_HEIGHT + 1_000))),
                "platform_guard_rail", _rgba(pal["marking"])),
    ]
    platform = _grp("loading_platform", plat_parts)

    beam_y0, beam_y1 = -13_000.0, 5_800.0
    beam_mid = (beam_y0 + beam_y1) / 2
    crane_parts = [
        _tinted(Box(1_100, 1_100, 9_100).moved(Location((CRANE_X - 2_600, beam_y1, 4_550))),
                "crane_leg_north_fore", COL_WHITE),
        _tinted(Box(1_100, 1_100, 9_100).moved(Location((CRANE_X + 2_600, beam_y1, 4_550))),
                "crane_leg_north_aft", COL_WHITE),
        _tinted(Box(1_100, 1_100, 9_100).moved(Location((CRANE_X - 2_600, beam_y0, 4_550))),
                "crane_leg_south_fore", COL_WHITE),
        _tinted(Box(1_100, 1_100, 9_100).moved(Location((CRANE_X + 2_600, beam_y0, 4_550))),
                "crane_leg_south_aft", COL_WHITE),
        _tinted(Box(1_300, beam_y1 - beam_y0 + 1_100, 900)
                .moved(Location((CRANE_X - 2_600, beam_mid, 9_550))), "crane_bridge_beam_fore", COL_WHITE),
        _tinted(Box(1_300, beam_y1 - beam_y0 + 1_100, 900)
                .moved(Location((CRANE_X + 2_600, beam_mid, 9_550))), "crane_bridge_beam_aft", COL_WHITE),
        _tinted(Box(6_800, 1_600, 700).moved(Location((CRANE_X, 0, 9_450))), "crane_trolley", COL_STEEL_DARK),
        _tinted(Box(4_400, 1_900, 420).moved(Location((CRANE_X, 0, 7_700))), "crane_spreader_bar", COL_GOLD),
    ]
    crane = _grp("payload_transfer_crane", crane_parts)
    return _grp("payload_loading_station", [platform, crane])


def make_lander_group(p: MassDriverParams) -> Compound:
    """Starship-derived cargo lander on its pad (stub marker if hidden)."""
    px, py = PAD_CENTER
    if not p.starship_lander_visibility:
        stub = _tinted(Cylinder(600, 120).moved(Location((px, py, 60))), "cargo_lander_omitted_marker", COL_PAD)
        return _grp("starship_cargo_lander", [stub])

    hull_r, hull_h = 4_500.0, 16_000.0
    base_z = 250.0 + 2_300.0  # pad top + leg stance height
    parts = [
        _tinted(Cylinder(hull_r, hull_h).moved(Location((px, py, base_z + hull_h / 2))),
                "lander_hull_barrel", COL_STEEL),
        _tinted(Sphere(hull_r, arc_size1=0).moved(Location((px, py, base_z + hull_h))),
                "lander_nose_dome", COL_STEEL),
        _tinted(Cone(4_900, 4_500, 2_300).moved(Location((px, py, base_z - 1_150))),
                "lander_engine_skirt", COL_STEEL_DARK),
        _tinted(Torus(hull_r + 10, 240).moved(Location((px, py, base_z + hull_h * 0.62))),
                "lander_thermal_blanket_band", COL_GOLD),
        # Cargo door and payload hand-off cradle face the service road (+Y side).
        _tinted(Box(3_200, 500, 6_000).moved(Location((px, py + hull_r - 100, base_z + hull_h * 0.42))),
                "lander_cargo_bay_door", COL_STEEL_DARK),
        _tinted(Box(2_600, 2_400, 700).moved(Location((px, py + hull_r + 1_600, base_z + 900))),
                "lander_payload_cradle", COL_GOLD),
    ]
    for k in range(3):
        ang = radians(90 + 120 * k)
        bx, by = px + 2_400 * cos(ang), py + 2_400 * sin(ang)
        parts.append(_tinted(Cone(700, 260, 1_500).moved(Location((bx, by, base_z - 2_050))),
                             f"lander_engine_bell_{k + 1}", COL_STEEL_DARK))
    for k in range(4):
        ang = radians(45 + 90 * k)
        lx, ly = px + (hull_r + 900) * cos(ang), py + (hull_r + 900) * sin(ang)
        # Tilt the strut top inward (-X before yaw) so it meets the hull.
        leg = Box(500, 500, 5_200).moved(Location((0, 0, 0), (0, -24, 0))) \
            .moved(Location((0, 0, 0), (0, 0, degrees(ang))))
        parts.append(_inst(leg, f"lander_leg_{k + 1}", Location((lx, ly, 2_450))))
        parts[-1].color = COL_STEEL_DARK
        parts.append(_tinted(Cylinder(750, 240).moved(Location((lx + 950 * cos(ang), ly + 950 * sin(ang), 370))),
                             f"lander_leg_pad_{k + 1}", COL_STEEL_DARK))
    return _grp("starship_cargo_lander", parts)


# --------------------------------------------------------------------------
# Tower, solar farm, radiators, power, rovers, drones, dust, terrain, earth
# --------------------------------------------------------------------------


def make_tower_group(p: MassDriverParams) -> Compound:
    pal = _palette(p)
    tx, ty = TOWER_POS
    h = p.control_tower_height
    parts = [
        _tinted(Box(5_200, 5_200, 1_400).moved(Location((tx, ty, 700))), "tower_base_bunker", COL_WHITE),
        _tinted(Cylinder(1_800, h - 1_400).moved(Location((tx, ty, 1_400 + (h - 1_400) / 2))),
                "tower_shaft", COL_WHITE),
        _tinted(Cylinder(3_200, 2_600).moved(Location((tx, ty, h + 1_300))), "tower_control_cab", COL_WHITE),
        _tinted(Cylinder(3_260, 900).moved(Location((tx, ty, h + 1_300))), "tower_window_band", COL_GLASS),
        _tinted(Cone(3_200, 900, 1_100).moved(Location((tx, ty, h + 2_600 + 550))), "tower_roof", COL_WHITE_DIM),
        _tinted(Cylinder(120, 3_200).moved(Location((tx, ty, h + 3_150 + 1_600))), "tower_antenna_mast", COL_STEEL),
        _tinted(Sphere(360).moved(Location((tx, ty, h + 3_150 + 3_300))), "tower_beacon", _rgba(pal["marking"])),
        _tinted(Cone(1_150, 150, 700).moved(Location((0, 0, 0), (0, 55, 0)))
                .moved(Location((tx + 2_500, ty + 2_500, h + 2_900))), "tower_relay_dish", COL_GOLD),
    ]
    return _grp("launch_control_tower", parts)


def solar_wing_centers(p: MassDriverParams) -> list[tuple[float, float]]:
    wing_area_m2 = (SOLAR_WING_W / 1_000.0) * (SOLAR_WING_H / 1_000.0)
    count = max(2, int(round(p.solar_farm_area / wing_area_m2)))
    rows = len(SOLAR_ROW_YS)
    per_row = -(-count // rows)  # ceil division
    centers = []
    for w in range(count):
        row, col = divmod(w, per_row)
        centers.append((SOLAR_X0 + col * SOLAR_PITCH, SOLAR_ROW_YS[row % rows]))
    return centers


def make_solar_group(p: MassDriverParams) -> Compound:
    """Combiner skid + solar wings. Wing children: 1 mast, 2 panel (tilted)."""
    pal = _palette(p)
    # Mast tall enough that a fully deployed (90 deg) panel edge clears grade.
    mast = _tinted(Cylinder(320, 3_200).moved(Location((0, 0, 1_600))), "wing_mast", COL_WHITE_DIM)
    panel = Box(SOLAR_WING_W, SOLAR_WING_H, 140)
    panel = panel.moved(Location((0, 0, 0), (-p.solar_panel_deploy_angle, 0, 0)))
    panel = _tinted(panel.moved(Location((0, 0, 3_400))), "wing_panel", COL_SOLAR)
    wing = _grp("solar_wing", [mast, panel])

    skid = _grp("solar_combiner_skid", [
        _tinted(Box(4_200, 2_600, 1_700).moved(Location((SOLAR_X0 - 9_000, SOLAR_ROW_YS[0], 850))),
                "combiner_cabinet", COL_WHITE),
        _tinted(Cylinder(160, 9_000).moved(Location((0, 0, 0), (90, 0, 0)))
                .moved(Location((SOLAR_X0 - 9_000, SOLAR_ROW_YS[0] - 6_000, 400))),
                "combiner_feeder_conduit", _rgba(pal["conduit"])),
    ])
    wings = [skid]
    for w, (x, y) in enumerate(solar_wing_centers(p)):
        wings.append(_inst(wing, f"solar_wing_{w + 1:02d}", Location((x, y, 0))))
    return _grp("solar_farm", wings)


def radiator_panel_xs(p: MassDriverParams) -> list[float]:
    return [RADIATOR_X0 + i * RADIATOR_PITCH for i in range(max(1, p.radiator_panel_count))]


def make_radiator_group(p: MassDriverParams) -> Compound:
    """Radiator rack (child 1) + deployable black panels (children 2..N+1).

    Panels hinge about the manifold line (X axis at y=RADIATOR_ROW_Y,
    z=RADIATOR_HINGE_Z); baked at radiator_panel_angle above horizontal.
    """
    xs = radiator_panel_xs(p)
    length = xs[-1] - xs[0] + RADIATOR_PITCH
    rack = _grp("radiator_manifold_rack", [
        _tinted(Cylinder(260, length).moved(Location((0, 0, 0), (0, 90, 0)))
                .moved(Location(((xs[0] + xs[-1]) / 2, RADIATOR_ROW_Y, RADIATOR_HINGE_Z))),
                "radiator_manifold_pipe", COL_STEEL),
        _tinted(Box(length, 900, 500).moved(Location(((xs[0] + xs[-1]) / 2, RADIATOR_ROW_Y, 250))),
                "radiator_rack_sill", COL_WHITE_DIM),
    ])
    # Panel is authored lying flat pointing -Y from the hinge; rotating about
    # +X by -angle raises the free (-Y) edge above the horizon.
    flat = Box(5_200, 4_600, 120).moved(Location((0, -2_300, 0)))
    tilted = flat.moved(Location((0, 0, 0), (-p.radiator_panel_angle, 0, 0)))
    panels = [rack]
    for i, x in enumerate(xs):
        panels.append(_inst(tilted, f"radiator_panel_{i + 1:02d}",
                            Location((x, RADIATOR_ROW_Y, RADIATOR_HINGE_Z))))
        panels[-1].color = COL_BLACK
    return _grp("radiator_array", panels)


def make_power_group(p: MassDriverParams) -> Compound:
    """Cryo/power skids, main cyan trunk run, supports, and track risers."""
    pal = _palette(p)
    parts = []
    for i, x in enumerate((38_000.0, 66_000.0, 94_000.0)):
        skid_parts = [
            _tinted(Box(6_000, 3_500, 2_200).moved(Location((x, -16_000, 1_100))),
                    "skid_cabinet", COL_WHITE),
            _tinted(Cylinder(750, 4_800).moved(Location((0, 0, 0), (0, 90, 0)))
                    .moved(Location((x, -15_400, 2_950))), "skid_cryo_tank_fore", COL_GOLD),
            _tinted(Cylinder(750, 4_800).moved(Location((0, 0, 0), (0, 90, 0)))
                    .moved(Location((x, -16_900, 2_950))), "skid_cryo_tank_aft", COL_STEEL),
            _tinted(Cylinder(170, 10_400).moved(Location((0, 0, 0), (90, 0, 0)))
                    .moved(Location((x, -16_000 + 5_200 + 200, 400))), "skid_feeder_conduit", _rgba(pal["conduit"])),
        ]
        parts.append(_grp(f"cryo_power_skid_{i + 1:02d}", skid_parts))

    substation = _grp("breech_substation", [
        _tinted(Box(4_600, 3_000, 2_400).moved(Location((-16_000, TRUNK_Y, 1_200))), "substation_hall", COL_WHITE),
        _tinted(Cylinder(900, 1_900).moved(Location((-17_600, TRUNK_Y + 900, 3_350))), "substation_capacitor_a", COL_GOLD),
        _tinted(Cylinder(900, 1_900).moved(Location((-14_400, TRUNK_Y + 900, 3_350))), "substation_capacitor_b", COL_GOLD),
    ])
    parts.append(substation)

    trunk_len = 196_000.0
    trunk_cx = -16_000.0 + trunk_len / 2
    n_pipe = max(1, p.power_cable_density)
    trunk_pipe = Cylinder(180, trunk_len).moved(Location((0, 0, 0), (0, 90, 0)))
    trunk_parts = []
    for k in range(n_pipe):
        y = TRUNK_Y + (k - (n_pipe - 1) / 2.0) * 520
        trunk_parts.append(_inst(trunk_pipe, f"trunk_conduit_{k + 1:02d}", Location((trunk_cx, y, 330))))
        trunk_parts[-1].color = _rgba(pal["conduit"])
    support = Box(900, n_pipe * 520 + 500, 260)
    seg_len = p.track_length / p.track_segment_count
    for j in range(14):
        x = -15_000.0 + j * 15_000.0
        trunk_parts.append(_inst(support, f"trunk_support_{j + 1:02d}", Location((x, TRUNK_Y, 130))))
        trunk_parts[-1].color = COL_WHITE_DIM
    parts.append(_grp("power_trunk_run", trunk_parts))

    riser_parts = []
    for j in range(p.track_segment_count + 1):
        s = j * seg_len
        x, z, _ = track_frame(p, s)
        h = z - BED_THICKNESS - 330.0 + 200.0  # overlap into the bed underside
        riser_parts.append(_tinted(Cylinder(150, h).moved(Location((x, TRUNK_Y, 330 + h / 2))),
                                   f"track_power_riser_{j + 1:02d}", _rgba(pal["conduit"])))
        jumper = Cylinder(120, 1_800).moved(Location((0, 0, 0), (90, 0, 0)))
        riser_parts.append(_tinted(jumper.moved(Location((x, TRUNK_Y + 900, 330 + h - 300))),
                                   f"track_power_jumper_{j + 1:02d}", _rgba(pal["conduit"])))
    parts.append(_grp("track_power_risers", riser_parts))
    return _grp("power_distribution_system", parts)


def rover_home_poses(p: MassDriverParams) -> list[tuple[float, float, float]]:
    """(x, y, yaw_deg) per rover; rover 1 is the payload transporter parked
    under the crane spur, yawed 90 deg so it fits between the crane legs."""
    poses = [(CRANE_X, -11_500.0, 90.0)]
    n = max(1, p.rover_count)
    for k in range(1, n):
        poses.append((26_000.0 + 42_000.0 * (k - 1), ROAD_Y, 0.0))
    return poses[:n]


def _make_rover(pal: dict) -> Compound:
    parts = [
        _tinted(Box(4_500, 2_600, 700).moved(Location((0, 0, 950))), "rover_chassis", COL_WHITE),
        _tinted(Box(3_400, 2_200, 240).moved(Location((-300, 0, 1_420))), "rover_cargo_deck", COL_STEEL_DARK),
        _tinted(Box(500, 500, 1_300).moved(Location((1_800, 0, 1_950))), "rover_sensor_mast", COL_WHITE_DIM),
        _tinted(Sphere(300).moved(Location((1_800, 0, 2_750))), "rover_sensor_pod", COL_GLASS),
        _tinted(Box(900, 2_400, 160).moved(Location((-2_050, 0, 1_180))), "rover_radiator_flap", COL_BLACK),
    ]
    wheel = Cylinder(550, 420).moved(Location((0, 0, 0), (90, 0, 0)))
    for i, x in enumerate((-1_600.0, 0.0, 1_600.0)):
        for side, y in (("left", 1_500.0), ("right", -1_500.0)):
            parts.append(_inst(wheel, f"rover_wheel_{i + 1}_{side}", Location((x, y, 550))))
            parts[-1].color = COL_TERRAIN_DARK
    return _grp("construction_rover", parts)


def make_rover_group(p: MassDriverParams) -> Compound:
    pal = _palette(p)
    base = _make_rover(pal)
    rovers = []
    for k, (x, y, yaw) in enumerate(rover_home_poses(p)):
        rovers.append(_inst(base, f"construction_rover_{k + 1:02d}",
                            Location((x, y, 0)) * Location((0, 0, 0), (0, 0, yaw))))
    return _grp("autonomous_rover_fleet", rovers)


DRONE_HOMES = ((40_000.0, 3_200.0, 9_000.0), (120_000.0, -3_200.0, 12_500.0))


def make_drone_group(p: MassDriverParams) -> Compound:
    pal = _palette(p)
    body = _tinted(Box(950, 950, 480), "drone_body", COL_WHITE)
    cam = _tinted(Sphere(240).moved(Location((0, 0, -380))), "drone_camera_ball", COL_GLASS)
    parts = [body, cam]
    for i, (ax, ay) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        arm = Box(900, 160, 120).moved(Location((0, 0, 0), (0, 0, degrees(atan2(ay, ax)))))
        parts.append(_inst(arm, f"drone_arm_{i + 1}", Location((ax * 620, ay * 620, 120))))
        parts[-1].color = COL_WHITE_DIM
        parts.append(_tinted(Cylinder(420, 60).moved(Location((ax * 1_050, ay * 1_050, 220))),
                             f"drone_rotor_{i + 1}", COL_STEEL_DARK))
    drone = _grp("inspection_drone", parts)
    drones = []
    for k, (x, y, z) in enumerate(DRONE_HOMES):
        drones.append(_inst(drone, f"inspection_drone_{k + 1:02d}", Location((x, y, z))))
    return _grp("inspection_drone_flight", drones)


DUST_PLUMES = (
    ("pad_dust_plume", PAD_CENTER[0] + 9_500.0, PAD_CENTER[1] + 4_000.0, 5_200.0, 3_200.0),
    ("muzzle_dust_plume", 176_000.0, -4_800.0, 6_800.0, 4_200.0),
)


def make_dust_group(p: MassDriverParams) -> Compound:
    """Schematic translucent regolith plumes; alpha follows lunar_dust_level."""
    level = min(1.0, max(0.0, p.lunar_dust_level))
    alpha = 0.08 + 0.34 * level
    scale = 0.5 + 0.5 * level
    parts = []
    for label, x, y, r, h in DUST_PLUMES:
        plume = Cone(220, r * scale, h * scale).moved(Location((x, y, h * scale / 2)))
        parts.append(_tinted(plume, label, Color(1.0, 0.44, 0.14, alpha)))
    for k, (x, y, _yaw) in enumerate(rover_home_poses(p)):
        plume = Cone(120, 1_100 * scale, 1_500 * scale).moved(
            Location((x - 2_900, y, 1_500 * scale / 2)))
        parts.append(_tinted(plume, f"rover_dust_plume_{k + 1:02d}", Color(1.0, 0.44, 0.14, alpha)))
    return _grp("regolith_dust_plumes", parts)


CRATERS = ((20_000.0, 34_000.0, 9_000.0), (120_000.0, -34_000.0, 12_500.0), (172_000.0, -20_000.0, 7_000.0))
BOULDERS = ((-14_000.0, 18_000.0, 1_100.0), (60_000.0, -32_000.0, 900.0),
            (140_000.0, 20_000.0, 1_300.0), (170_000.0, 12_000.0, 800.0))


def make_terrain_group(p: MassDriverParams) -> Compound:
    pal = _palette(p)
    parts = [
        _tinted(Box(228_000, 96_000, 4_000).moved(Location((86_000, 0, -2_000))),
                "lunar_terrain_slab", COL_TERRAIN),
        _tinted(Box(210_000, 3_600, 120).moved(Location((80_000, ROAD_Y, 60))),
                "service_road", COL_TERRAIN_DARK),
        _tinted(Cylinder(14_000, 250).moved(Location((PAD_CENTER[0], PAD_CENTER[1], 125))),
                "landing_pad", COL_PAD),
        _tinted(Torus(12_500, 90).moved(Location((PAD_CENTER[0], PAD_CENTER[1], 260))),
                "landing_pad_marking_ring", _rgba(pal["marking"])),
    ]
    for k, (x, y, r) in enumerate(CRATERS):
        parts.append(_tinted(Torus(r, r * 0.09).moved(Location((x, y, 40))),
                             f"crater_rim_{k + 1}", COL_TERRAIN_DARK))
        parts.append(_tinted(Cylinder(r * 0.9, 70).moved(Location((x, y, 20))),
                             f"crater_floor_{k + 1}", COL_TERRAIN_DARK))
    for k, (x, y, r) in enumerate(BOULDERS):
        parts.append(_tinted(Sphere(r).moved(Location((x, y, r * 0.35))),
                             f"boulder_{k + 1}", COL_TERRAIN_DARK))
    return _grp("lunar_terrain", parts)


def make_earth_group(p: MassDriverParams) -> Compound:
    if not p.earth_visibility:
        stub = _tinted(Sphere(200).moved(Location(EARTH_POS)), "earth_omitted_marker", COL_EARTH)
        return _grp("earth_in_sky", [stub])
    # Blue globe with two faint cloud-band rings; no enclosing haze shell
    # (a translucent outer sphere renders as a washed-out white ball).
    band = Torus(6_700, 450)
    band_a = _inst(band, "earth_cloud_band_north",
                   Location(EARTH_POS) * Location((0, 0, 2_050), (12, 0, 0)))
    band_a.color = COL_EARTH_HAZE
    band_b = _inst(band, "earth_cloud_band_south",
                   Location(EARTH_POS) * Location((0, 0, -2_050), (-8, 0, 0)))
    band_b.color = COL_EARTH_HAZE
    parts = [
        _tinted(Sphere(7_000).moved(Location(EARTH_POS)), "earth_globe", COL_EARTH),
        band_a,
        band_b,
    ]
    return _grp("earth_in_sky", parts)


# --------------------------------------------------------------------------
# Scene assembly
# --------------------------------------------------------------------------


def build_scene(p: MassDriverParams = DEFAULTS) -> Compound:
    """Full mass-driver scene. Root child order is the sidecar ref contract:

    1 lunar_terrain, 2 earth_in_sky, 3 electromagnetic_launch_track,
    4 regolith_anchored_foundations, 5 levitated_payload_sled,
    6 service_gantry_row, 7 payload_loading_station, 8 starship_cargo_lander,
    9 launch_control_tower, 10 solar_farm, 11 radiator_array,
    12 power_distribution_system, 13 autonomous_rover_fleet,
    14 inspection_drone_flight, 15 regolith_dust_plumes.
    """
    groups = [
        make_terrain_group(p),
        make_earth_group(p),
        make_track_group(p),
        make_foundation_group(p),
        make_sled_group(p),
        make_gantry_group(p),
        make_loading_station_group(p),
        make_lander_group(p),
        make_tower_group(p),
        make_solar_group(p),
        make_radiator_group(p),
        make_power_group(p),
        make_rover_group(p),
        make_drone_group(p),
        make_dust_group(p),
    ]

    dist = min(1.0, max(0.0, p.exploded_distance)) * EXPLODE_SCALE
    if dist > 0.0:
        keys = ["terrain", "earth", "track", "foundations", "sled", "gantries", "loading",
                "lander", "tower", "solar", "radiators", "power", "rovers", "drones", "dust"]
        exploded = []
        for key, group in zip(keys, groups):
            dx, dy, dz = EXPLODE_DIRS[key]
            moved = group.moved(Location((dx * dist, dy * dist, dz * dist)))
            moved.label = group.label
            exploded.append(moved)
        groups = exploded

    return Compound(
        obj=groups,
        children=groups,
        label="lunar_mass_driver_launch_complex__speculative_concept",
    )
# --------------------------------------------------------------------------
# STEP entry
# --------------------------------------------------------------------------

DISPLAY_NAME = "Lunar mass driver launch complex (SpaceX-inspired speculative concept)"


def gen_step():
    return {
        "shape": build_scene(DEFAULTS),
        "params": "lunar_mass_driver.params.js",
    }
