"""The tendon hand's component reviews: one model per family, each its own xbf.

Joint hardware (axles, bushings, retaining rings), the drive train (motor, gearbox,
capstan, tension cartridge, the driven terminal), the wrist, the thumb metacarpal and
the runtime fixture. Each model was its own script in `models/tendon_hand/src/`; they
share nothing expensive, so none is a `@memo` and no model calls another.
"""

from cadgen import model

import build123d as bd

from lib.assembly import Body, compound
from lib.axle import make_axle, make_dowel, make_driven_axle
from lib.bushing import make_bushing
from lib.capstan import make_capstan, make_stored_tendon, make_terminal_ferrule
from lib.drive_terminal import (
    arc_tube,
    capstan_bond_bodies,
    drive_terminal_bodies,
    make_cover_screw,
    make_driven_bond_line,
    make_driven_ferrule,
    make_pulley_grub_screw,
    make_terminal_pulley_parts,
)
from lib.finish import finish
from lib.gearbox import make_gearbox_parts
from lib.layout import MCP_YAW_DRIVE_PLANES, TENDONS
from lib.motor import make_motor_case, make_motor_endcap, make_motor_shaft
from lib.phalanx import make_phalanx
from lib.pulley import make_pulley
from lib.pulley_hub_extension import representative_bodies
from lib.retaining_ring import make_retaining_ring
from lib.tension_cartridge import make_tension_cartridge
from lib.thumb_metacarpal import make_thumb_metacarpal
from lib.universal_carrier import make_universal_carrier
from lib.wrist import make_wrist_bushings, make_wrist_fixed_fork, make_wrist_palm_cradle, make_wrist_yaw_carrier


@model
def axle_review():
    """Resolved axle family: two finger stubs, a wrist journal, a locating dowel."""
    return bd.Compound(label="polished_axle_and_dowel_family", children=[
        bd.Pos(-9, 0, 0) * make_axle(3.5, label="finger_3_5mm_stub_axle"),
        bd.Pos(-4, 0, 0) * make_axle(6, label="finger_6mm_stub_axle"),
        bd.Pos(6, 0, 0) * make_axle(12, 3, label="wrist_12mm_axle"),
        bd.Pos(-6, -5, 0) * make_dowel(4, label="finger_4mm_location_dowel"),
    ])


@model
def driven_axle_review():
    """Keyed through shafts and separate universal-joint yaw stub, native +Z."""
    return bd.Compound(label="D_keyed_drive_axle_family", children=[
        bd.Pos(-6, 0, 0) * make_driven_axle(26, label="finger_26mm_through_drive_shaft"),
        make_driven_axle(20, label="finger_20mm_through_drive_shaft"),
        bd.Pos(6, 0, 0) * make_driven_axle(6, label="yaw_6mm_independent_keyed_stub"),
    ])


@model
def bushing_review():
    """Three finished bushing sizes, each a separate closed polished body."""
    return bd.Compound(label="polished_flanged_bushing_family", children=[
        bd.Pos(-10, 0, 0) * make_bushing(label="finger_eye_5mm_OD_2mm_shaft"),
        make_bushing(3.25, 1.53, 2.0, 3.55, .20, label="palm_eye_6_5mm_OD_3mm_shaft"),
        bd.Pos(12, 0, 0) * make_bushing(5.0, 3.03, 3.0, 5.45, .28, label="wrist_eye_10mm_OD_6mm_shaft"),
    ])


@model
def retaining_ring_review():
    """Isolated rings and paired in-groove fit examples, at real millimeter scale."""
    children = []
    for radius, x, length in ((1., -5., 3.5), (3., 5., 12.)):
        label = "finger" if radius == 1 else "wrist"
        ring = make_retaining_ring(radius, label=f"{label}_isolated_retaining_ring")
        children.append(bd.Pos(x, 0, 0) * ring)
        axle = make_axle(length, radius, label=f"{label}_fit_axle")
        seated = bd.Pos(0, 0, length - .6) * make_retaining_ring(radius, label=f"{label}_seated_retaining_ring")
        overlap = axle.intersect(seated)
        if overlap is not None and sum(s.volume for s in overlap.solids()) > 1e-9:
            raise ValueError(f"{label}: retaining ring intersects axle")
        children.extend([bd.Pos(x, 9, 0) * axle, bd.Pos(x, 9, 0) * seated])
    return bd.Compound(label="retaining_ring_family_and_groove_fit", children=children)


@model
def pulley_review():
    """Macro review of the five driven D-bore tendon pulley radii, in mm."""
    children = []
    for radius, x in zip((3.5, 4.5, 5.5, 7.0, 11.0), (-40, -29, -16, 0, 22)):
        wheel = make_pulley(pitch_radius=radius, bore_radius=3.03 if radius == 11 else 1.03,
                            label=f"turned_tendon_pulley_R{str(radius).replace('.', '_')}")
        children.append(bd.Pos(x, 0, 0) * wheel)
    return bd.Compound(label="turned_tendon_pulley_family", children=children)


@model
def pulley_hub_review():
    """Two separately resolved turned PIP hub-spacer bodies, assembled datums."""
    return bd.Compound(label="middle_PIP_turned_hub_spacers", children=[b.shape for b in representative_bodies()])


@model
def universal_carrier_review():
    """Middle MCP carrier with its actual adjacent phalanx and crossed drums."""
    children = [make_universal_carrier(), make_phalanx(45, 18)]
    for sign in (-1, 1):
        children.append(bd.Pos(sign * .9, 0, 0) * bd.Rot(0, 90, 0) * make_pulley(5.5, label=f"flex_drive_{sign}"))
        children.append(bd.Pos(0, 0, MCP_YAW_DRIVE_PLANES[0 if sign == 1 else 1])
                        * make_pulley(5.5, label=f"yaw_drive_{sign}"))
    return bd.Compound(label="universal_carrier_in_joint_context", children=children)


@model
def wrist_review():
    """The skeletal wrist: fixed fork, yaw carrier, palm cradle, drive drums, bushings."""
    p = [make_wrist_fixed_fork(), make_wrist_yaw_carrier(), make_wrist_palm_cradle()]
    for sign in (-1, 1):
        p.append(bd.Pos(0, -9, sign * 5.5) * make_pulley(11, bore_radius=3.03, label=f"wrist_yaw_drive_{sign}"))
        p.append(bd.Pos(sign * 14, 0, 0) * bd.Rot(0, 90, 0) * bd.Rot(0, 0, 90)
                 * make_pulley(11, bore_radius=3.03, label=f"wrist_flex_drive_{sign}"))
    p += [b for frame, b in make_wrist_bushings()]
    return bd.Compound(label="skeletal_wrist", children=p)


@model
def palm_cradle_clearance_review():
    """Strict inspection target for the headed-shaft withdrawal relief."""
    return make_wrist_palm_cradle()


@model
def thumb_metacarpal_review():
    """The thumb metacarpal frame alone."""
    return make_thumb_metacarpal()


@model
def motor_review():
    """A complete miniature motor and a separated, readable component set."""
    return bd.Compound(label="miniature_motor_family", children=[
        bd.Pos(-10, 0, 0) * make_motor_case("assembled_motor_case"),
        bd.Pos(-10, 0, 0) * make_motor_endcap("assembled_motor_endcap"),
        bd.Pos(-10, 0, 0) * make_motor_shaft("assembled_motor_shaft"),
        bd.Pos(10, 0, 0) * make_motor_case("separated_motor_case"),
        bd.Pos(10, 0, 6) * make_motor_endcap("separated_motor_endcap"),
        bd.Pos(10, 0, 15) * make_motor_shaft("separated_motor_shaft"),
    ])


@model
def gearbox_review():
    """Resolved planetary reducer in assembly and a separated display."""
    parts = make_gearbox_parts("assembled_gearbox")
    parts.extend([make_motor_case("assembled_motor_case"), make_motor_endcap("assembled_motor_endcap"),
                  make_motor_shaft("assembled_motor_shaft")])
    assembled = [bd.Pos(-10, 0, 0) * p for p in parts]
    separated = make_gearbox_parts("separated_gearbox")
    offsets = [(0, 0, 12), (0, 0, 0), (0, 0, 0), (0, 0, 5), (0, 0, 16), (0, 0, 12), (0, 0, 0), (0, 0, -5),
               (0, 0, 0), (0, 0, -5), (0, 0, 0), (0, 0, -5)]
    return bd.Compound(label="planetary_gearbox_family", children=assembled + [
        bd.Pos(12 + x, y, z) * p for p, (x, y, z) in zip(separated, offsets)])


@model
def capstan_review():
    """The six-turn storage capstan, its terminal ferrule and the stored tendon."""
    return bd.Compound(label="six_turn_storage_capstan_review",
                       children=[make_capstan(), make_terminal_ferrule(), make_stored_tendon()])


@model
def capstan_index_overlay():
    """The 48 notched capstans, placed exactly as the assembled hand places them.

    The drum turns +-70 degrees to pay a cord out, and a surface of revolution with a
    helix wound on it reads as stationary; `lib.capstan.make_capstan` cuts index marks
    at one angular position so the turn shows. One expensive prototype, 48 placed
    occurrences, each given the aluminium frame finish."""
    prototype = make_capstan()
    parts = []
    for tendon in TENDONS:
        x, y, _ = tendon["actuator_center"]
        sign = tendon["sign"]
        placement = bd.Pos(x, y, sign * 4.) * (bd.Rot(0, 0, 0) if sign == 1 else bd.Rot(0, 180, 0))
        part = placement * bd.Pos(0, 0, 29) * prototype
        part.label = f'{tendon["actuator"]}_capstan'
        part.color = prototype.color
        parts.append(Body(part, "forearm", "forearm", "capstan"))
    names = [body.name for body in parts]
    assert len(names) == len(set(names)) == 48
    return compound(parts, "capstan_index_overlay")


@model
def tension_cartridge_review():
    """A single cartridge shown upright and inverted to expose its three sensors."""
    bodies = []
    for prefix, x, rot in (("upper", -10, 0), ("underside", 10, 180)):
        bodies.extend(bd.Pos(x, 0, 0) * bd.Rot(rot, 0, 0) * s for s in make_tension_cartridge(prefix))
    return bd.Compound(label="torsional_tendon_load_cartridge_review", children=bodies)


@model
def tension_cartridge_bank_review():
    """The exact 48 forearm mounting cartridge placements, for strict validation."""
    prototype = make_tension_cartridge()
    bodies = []
    for row, y in enumerate((-252, -211, -170, -129, -88, -47)):
        for col, x in enumerate((-27, -9, 9, 27)):
            for bank, rotation in (("palmar", 0), ("dorsal", 180)):
                placement = bd.Pos(x, y, 0) * bd.Rot(0, rotation, 0)
                for i, body in enumerate(prototype):
                    placed = placement * body
                    placed.label = f'{bank}_station_{row + 1}_{col + 1}_{"spring" if i == 0 else "bonded_gauge_" + str(i)}'
                    bodies.append(placed)
    return bd.Compound(label="all_48_tension_cartridges", children=bodies)


@model
def drive_terminal_review():
    """Ten drive terminal prototypes: five pulley radii and both antagonists."""
    children = []
    for r, x in zip((3.5, 4.5, 5.5, 7., 11.), (-42, -30, -16, 2, 29)):
        bore = 3.03 if r == 11 else 1.03
        for sign, y in ((1, 0), (-1, 27)):
            phase = -60 * sign
            direction = -sign
            name = f'R{r}_{"positive" if sign == 1 else "negative"}'
            placement = bd.Pos(x, y, 0)
            wheel, cover = make_terminal_pulley_parts(r, bore, phase, direction)
            wheel.label = name + "_captured_terminal_pulley"
            cover.label = name + "_capture_cover"
            screw = make_cover_screw(r, phase, direction)
            screw.label = name + "_cover_socket_screw"
            bond = make_driven_bond_line(r, phase, direction)
            bond.label = name + "_resin_bond_line"
            children.extend(placement * body for body in (
                wheel, cover, screw, bond,
                make_driven_ferrule(r, phase, direction, name + "_curved_blind_ferrule"),
                make_pulley_grub_screw(bore, name + "_inclined_socket_grub_screw", side=sign),
                finish(arc_tube(r, .30, -r * 2.61799387799, 0, phase, direction),
                       "cord_flexion_positive" if sign == 1 else "cord_flexion_negative",
                       name + "_unchanged_tendon_wrap")))
    return bd.Compound(label="ten_captured_driven_tendon_terminal_prototypes", children=children)


@model
def drive_terminal_macro():
    """R3.5 driven terminal, assembled and with its installation cover lifted."""
    children = []
    wheel, cover = make_terminal_pulley_parts()
    ferrule = make_driven_ferrule()
    screw = make_pulley_grub_screw()
    rope = finish(arc_tube(3.5, .30, -3.5 * 2.61799387799, 0, -60, -1), "cord_flexion_positive",
                  "unchanged_R3_5_rope_wrap")
    for x, name, lift in ((-5, "assembled", 0), (5, "cover_installation", 3.0)):
        for role, part in (("pulley", wheel),
                           ("cover_screw", bd.Pos(0, 0, lift + 1. if lift else 0) * make_cover_screw()),
                           ("ferrule", bd.Pos(0, 0, 1.9 if lift else 0) * ferrule),
                           ("resin_bond_line", bd.Pos(0, 0, .9 if lift else 0) * make_driven_bond_line()),
                           ("socket_grub_screw", screw), ("tendon_wrap", rope),
                           ("capture_cover", bd.Pos(0, 0, lift) * cover)):
            body = bd.Pos(x, 0, 0) * part
            body.label = name + "_" + role
            children.append(body)
    return bd.Compound(label="R3_5_captured_driven_tendon_macro", children=children)


@model
def drive_terminal_placements():
    """All 336 driven terminal and capstan bond occurrences in the assembled neutral hand fan."""
    return bd.Compound(label="all_48_driven_tendon_terminal_assemblies",
                       children=[s for s, *_ in drive_terminal_bodies() + capstan_bond_bodies()])


@model
def runtime_fixture():
    """A real continuous swept tube, the fixture of the old flexible-animation checks."""
    centerline = bd.Edge.make_line((0, 0, 8), (60, 0, 8))
    profile = bd.Plane(origin=(0, 0, 8), z_dir=(1, 0, 0)) * bd.Circle(0.8)
    tube = bd.sweep(profile, path=centerline)
    tube.label = "continuous_swept_tube"
    tube.color = bd.Color("#ef995d")
    start = bd.Pos(0, 0, 8) * bd.Sphere(1.2)
    start.label = "fixed_start_marker"
    start.color = bd.Color("#767c84")
    return bd.Compound(children=[tube, start])


if __name__ == "__main__":
    axle_review()
    driven_axle_review()
    bushing_review()
    retaining_ring_review()
    pulley_review()
    pulley_hub_review()
    universal_carrier_review()
    wrist_review()
    palm_cradle_clearance_review()
    thumb_metacarpal_review()
    motor_review()
    gearbox_review()
    capstan_review()
    capstan_index_overlay()
    tension_cartridge_review()
    tension_cartridge_bank_review()
    drive_terminal_review()
    drive_terminal_macro()
    drive_terminal_placements()
    runtime_fixture()
