"""Manual B-rep corpus for photographic Preview review, never a CI fixture.

Millimetres, Z up. The four scenes deliberately exercise different material and
light-transport problems rather than a shared primitive arrangement.
"""
import copy
import math

import build123d as bd
from bd_materials import FinishedMaterial, glass, metals
from bd_materials.core import RangeMaterial
from threejs_materials import PbrProperties
from cadgen import model, paint


def coating(name, **values):
    return FinishedMaterial(RangeMaterial(name=name, density=None), pbr=PbrProperties.create(name, **values))


def appearance(material, **values):
    result = copy.deepcopy(material)
    result.pbr = result.pbr.override(**values)
    return result


BLUE = coating("Regulator powder coat", color="#145d89", metalness=0.0, roughness=0.27, clearcoat=0.25)
BLACK = coating("Moulded engineering polymer", color="#15191d", roughness=0.47)
GREEN = coating("Green solder mask", color="#134a38", roughness=0.36, clearcoat=0.2)
WHITE = coating("Ceramic dial", color="#ede8db", roughness=0.3)
ALUMINIUM = appearance(metals.aluminum(metals.Alu.G6061_T6), color="#c0c5ca", metalness=1, roughness=0.24, anisotropy=0.45)
STEEL = appearance(metals.stainless(metals.Stainless.G304_ANNEALED), color="#c2c7cc", metalness=1, roughness=0.16)
BRASS = appearance(metals.brass(metals.Brass.C360_HALF_HARD), color="#cba35b", metalness=1, roughness=0.23)
COPPER = appearance(metals.copper(metals.Copper.C110_ANNEALED), roughness=0.2)
# Preserve this review scene's original soda-lime absorption and opaque base alpha.
GLASS = appearance(glass.soda_lime(), color="#ffffff", roughness=0.025, transmission=1.0,
                   attenuation_color=(0.822786, 0.930111, 0.871367), attenuation_distance=0.05, dispersion=0)


def finish(part, label, material):
    part.label = label
    part.material = material
    # Native material assignment infers transparency for glass; the physical
    # transmission model needs an opaque authored base colour instead.
    color = material.pbr.to_dict()["values"].get("color", (1, 1, 1))
    part.color = bd.Color(*color, 1)
    return part


def rounded_plate(width, depth, height, radius=3):
    return bd.extrude(bd.RectangleRounded(width, depth, radius), amount=height)


def tube(outer, inner, height):
    return bd.Cylinder(outer, height, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)) - bd.Cylinder(inner, height + 2, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(bd.Pos(0, 0, -1))


def socket_screw():
    stem = bd.Cylinder(2.8, 10, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    head = bd.Pos(0, 0, 8) * bd.Cylinder(4.8, 4, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    body = stem + head
    recess = bd.Pos(0, 0, 9.5) * bd.extrude(bd.RegularPolygon(2.3, 6), amount=4)
    return finish(body - recess, "socket_cap_screw", STEEL)


@model
def machined_bearing_housing():
    body = rounded_plate(108, 78, 20, 5)
    body = bd.fillet(body.edges().filter_by(bd.Axis.Z, reverse=True), 0.8)
    body += bd.Pos(0, 0, 18) * bd.Cylinder(29, 21, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    cuts = [bd.Pos(0, 0, -1) * bd.Cylinder(18, 42, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)),
            bd.Pos(0, 0, 33) * bd.Cylinder(23, 8, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))]
    for x in (-42, 42):
        for y in (-26, 26):
            cuts.extend([bd.Pos(x, y, -1) * bd.Cylinder(3.5, 24, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)),
                         bd.Pos(x, y, 14) * bd.Cylinder(6.5, 8, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))])
    for x in (-39, 39):
        cuts.append(bd.Pos(x, 0, 11) * rounded_plate(13, 24, 12, 4))
    body = finish(body - cuts, "counterbored_machined_housing", ALUMINIUM)
    paint(body, body.faces().filter_by(bd.Axis.Z)[-1:], appearance(ALUMINIUM, roughness=0.12))
    bearing = finish(bd.Pos(0, 0, 21) * tube(17.95, 12.5, 12), "bronze_bearing", BRASS)
    seal = finish(bd.Pos(0, 0, 32.7) * tube(22.5, 17.8, 1.8), "retaining_seal", BLACK)
    screw = socket_screw()
    screws = [bd.Pos(x, y, 6) * screw for x in (-42, 42) for y in (-26, 26)]
    return bd.Compound(children=[body, bearing, seal, *screws], label="machined_bearing_housing")


@model
def painted_pressure_regulator():
    housing = bd.Cylinder(30, 51, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    housing += bd.Pos(0, 0, 7) * rounded_plate(69, 49, 8, 7)
    housing -= bd.Pos(0, 0, 44) * bd.Cylinder(23, 10, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    housing = finish(housing, "painted_body", BLUE)
    knob = bd.Pos(0, 0, 49) * bd.Cylinder(24, 18, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    for i in range(20):
        a = i * math.tau / 20
        knob -= bd.Pos(24 * math.cos(a), 24 * math.sin(a), 50) * bd.Cylinder(1.6, 16, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    knob = finish(knob, "ribbed_adjustment_knob", BLACK)
    ports = []
    for sign in (-1, 1):
        fitting = bd.extrude(bd.RegularPolygon(10, 6), amount=12) + bd.Pos(0, 0, 11) * tube(7, 4.5, 10)
        fitting = bd.Pos(sign * 28, 0, 27) * bd.Rot(0, sign * 90, 0) * fitting
        ports.append(finish(fitting, "brass_port", BRASS))
    # The gauge's local Z axis faces the camera (-Y).
    place = bd.Pos(0, -28, 35) * bd.Rot(90, 0, 0)
    bezel = finish(place * tube(20, 17, 8), "polished_gauge_bezel", STEEL)
    dial = finish(place * bd.Pos(0, 0, 5.8) * bd.Cylinder(16.8, 0.7), "ivory_pressure_dial", WHITE)
    ticks = []
    for i in range(25):
        a = math.radians(-140 + i * 280 / 24)
        tick = bd.Pos(13 * math.sin(a), 13 * math.cos(a), 6.4) * bd.Rot(0, 0, -math.degrees(a)) * bd.Box(0.65, 2.8 if i % 3 == 0 else 1.6, 0.2)
        ticks.append(finish(place * tick, "dial_tick", BLACK))
    needle = finish(place * bd.Pos(-3, 2, 6.7) * bd.Rot(0, 0, -45) * bd.Box(0.9, 15, 0.3), "red_indicator_needle", coating("Red enamel", color="#c32123", roughness=0.27))
    crystal = finish(place * bd.Pos(0, 0, 7.4) * bd.Cylinder(16.7, 0.7), "gauge_glass", GLASS)
    screw = socket_screw()
    screws = [bd.Pos(x, y, 6) * screw for x in (-26, 26) for y in (-15, 15)]
    return bd.Compound(children=[housing, knob, *ports, bezel, dial, *ticks, needle, crystal, *screws], label="painted_pressure_regulator")


@model
def glass_sample_vessel():
    shell = bd.Cylinder(31, 72, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    shell -= bd.Pos(0, 0, 3) * bd.Cylinder(28, 71, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    shell += bd.Pos(0, 0, 70) * tube(32.3, 27.5, 5)
    shell = finish(shell, "thick_walled_glass_vessel", GLASS)
    liquid_material = coating("Amber sample liquid", color="#efb546", roughness=0.03, ior=1.333, transmission=0.92, attenuation_color="#b8671e", attenuation_distance=0.07)
    liquid = finish(bd.Pos(0, 0, 3.1) * bd.Cylinder(27.8, 39, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)), "amber_liquid", liquid_material)
    contents = []
    for x, y, z in [(-10, -6, 11), (8, 5, 12), (0, 0, 25)]:
        contents.append(finish(bd.Pos(x, y, z) * bd.Sphere(7.5), "metal_sample_ball", STEEL))
    lid = bd.Pos(0, 48, 0) * bd.Cylinder(33, 9, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    for i in range(36):
        a = i * math.tau / 36
        lid -= bd.Pos(33 * math.cos(a), 48 + 33 * math.sin(a), 1) * bd.Cylinder(0.8, 7, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    lid = finish(lid, "knurled_aluminium_lid", ALUMINIUM)
    seal = finish(bd.Pos(0, 48, 9) * tube(29, 26, 1.5), "lid_seal", BLACK)
    return bd.Compound(children=[shell, liquid, *contents, lid, seal], label="glass_sample_vessel")


@model
def mixed_material_instrument():
    enclosure = rounded_plate(116, 82, 24, 7)
    enclosure -= bd.Pos(0, 0, 3) * rounded_plate(108, 74, 24, 5)
    enclosure = finish(enclosure, "open_die_cast_enclosure", ALUMINIUM)
    pcb = rounded_plate(98, 64, 1.7, 3)
    for x in (-42, 42):
        for y in (-25, 25):
            pcb -= bd.Pos(x, y, -1) * bd.Cylinder(2.1, 4, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    pcb = finish(bd.Pos(0, 0, 7) * pcb, "populated_green_pcb", GREEN)
    parts = [enclosure, pcb]
    for x in (-42, 42):
        for y in (-25, 25):
            parts.append(finish(bd.Pos(x, y, 3) * tube(3.7, 1.7, 4), "brass_standoff", BRASS))
            parts.append(bd.Pos(x, y, 0) * socket_screw())
    chip = finish(bd.Pos(-17, 0, 11) * bd.Box(27, 25, 5), "control_ic", BLACK)
    parts.append(chip)
    for y in (-14, 14):
        for i in range(12):
            parts.append(finish(bd.Pos(-29 + i * 2.1, y, 9.5) * bd.Box(0.7, 4, 1), "tin_lead", STEEL))
    for x, y in [(25, -16), (25, 3)]:
        parts.append(finish(bd.Pos(x, y, 8.8) * bd.Cylinder(7, 16, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)), "electrolytic_capacitor", BLACK))
        parts.append(finish(bd.Pos(x, y, 24.8) * bd.Cylinder(6.4, 0.4), "scored_capacitor_top", ALUMINIUM))
    sink = bd.Pos(18, 19, 8.8) * bd.Box(30, 20, 3, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    for y in range(-8, 10, 3):
        sink += bd.Pos(18, 19 + y, 11.8) * bd.Box(30, 1.2, 13, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    parts.append(finish(sink, "finned_aluminium_heatsink", ALUMINIUM))
    # A short copper wound inductor is modelled as separate circular turns.
    for i in range(9):
        parts.append(finish(bd.Pos(-25, 22, 10 + i * 0.9) * tube(7.3, 6.3, 0.75), "copper_coil_turn", COPPER))
    return bd.Compound(children=parts, label="mixed_material_instrument")


if __name__ == "__main__":
    machined_bearing_housing()
    painted_pressure_regulator()
    glass_sample_vessel()
    mixed_material_instrument()
