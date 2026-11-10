"""Hardware every link shares: cap screws, the RobStride actuators, pivot caps, pushrods.

`Hardware()` builds each prototype once per run, in its own frame and symmetric about its
local YZ plane, so it can be placed on both sides of the robot (`kit.inst`, `kit.mirror_tree`).

An actuator's frame: local Z is its axis, z = 0 its mounting face (the front of its main
body, where its tapped mounting holes are). The body lies behind the face (z < 0). The
parent link's mounting plate (PLATE_T thick) lies on the face and is screwed to it from the
far side, on the maker's bolt circle. The output flange is in the middle of the face; a hub
bolted to it stands through the plate and ROTOR_PROUD past the face, where the child
link's lug bolts on, on the output flange's own bolt circle. The two smallest models are
plain cans held by countersunk screws, which show no heads.
"""

import math

import build123d as bd

from . import finish, geo
from .dims import ACTUATORS, DRIVES, PLATE_T, ROTOR_PROUD, SCREWS
from .kit import frame, inst, part, proto


def ring_positions(n, radius, phase=0.0):
    return [(radius * math.cos(math.radians(phase + 360.0 * k / n)),
             radius * math.sin(math.radians(phase + 360.0 * k / n))) for k in range(n)]


def _screw_head(size):
    d, h, af = SCREWS[size]
    head = geo.revolve([(0, 0), (d / 2, 0), (d / 2, h - 0.5), (d / 2 - 0.5, h), (0, h)])
    socket = geo.hex_prism(af, h * 0.6, origin=(0, 0, h * 0.45))
    return head - socket


def _housing(spec):
    """The main body: a plain can to the maker's diameter and length, its register proud of the
    mounting face, and the ribs its mounting screws run in where the model has them."""
    (rf, lf), (rp, hp), hub = spec["front"], spec["pilot"], spec["hub"]
    bore = hub + 0.6
    pts = [(bore, -4.0), (bore, hp), (rp, hp), (rp, 0.0)] if rp > bore + 1.0 else [(bore, -4.0), (bore, 0.0)]
    pts += [(rf - 0.8, 0.0), (rf, -0.8), (rf, -lf + 0.8), (rf - 0.8, -lf), (0.0, -lf), (0.0, -4.0)]
    body = geo.revolve(pts)
    if spec["ears"]:
        _, count, pitch = spec["mount"]
        for x, y in ring_positions(count, pitch, 180.0 / count):
            body += bd.Pos(x, y, -lf / 2) * bd.Cylinder(spec["ears"] - pitch, lf)
    return body


def _cap(spec):
    """The rear cover, over the driver board, with its connector on the rim at local +Y."""
    (_, lf), (rr, lr) = spec["front"], spec["rear"]
    cover = geo.revolve([(0.0, -lf), (rr, -lf), (rr, -lf - lr + 1.0), (rr - 1.0, -lf - lr), (0.0, -lf - lr)])
    plug = bd.Pos(0, rr + 0.5, -lf - lr / 2) * bd.Box(0.5 * rr, 5.0, max(lr - 5.0, 3.0))
    return cover + plug


def _rotor(spec):
    """The output: the actuator's own flange and the hub bolted to it, as one turned part."""
    hub = spec["hub"]
    return geo.revolve([(0.0, -4.0), (hub, -4.0), (hub, ROTOR_PROUD - 0.8), (hub - 0.8, ROTOR_PROUD), (0.0, ROTOR_PROUD)])


def _pivot_cap(radius):
    """A low cover over a passive pivot's bearing: turned, with a centre boss."""
    h = max(3.0, 0.16 * radius + 1.5)
    pts = [(0, 0), (radius, 0), (radius, h * 0.55), (radius - h * 0.45, h), (radius * 0.45, h),
           (radius * 0.38, h + 1.2), (0, h + 1.2)]
    return geo.revolve(pts)


class Hardware:
    """The shared prototypes, built once per run."""

    def __init__(self):
        self.screws = {size: proto(_screw_head(size), "black_oxide") for size in SCREWS}
        self.act = {}
        for size, spec in ACTUATORS.items():
            housing, cap = _housing(spec), _cap(spec)
            # One homogenised density for the unit, so that housing and cover weigh what the maker says.
            look = finish.actuator(size, spec["kg"] / ((housing.volume + cap.volume) * 1e-9))
            self.act[size] = dict(housing=proto(housing, look), cap=proto(cap, look), rotor=proto(_rotor(spec), "steel"))
        self._caps = {}

    # -- fasteners ----------------------------------------------------------------------
    def screw(self, size, origin, axis, label=None):
        """One cap-screw head seated at `origin`, its top toward `axis`."""
        return inst(self.screws[size], frame(origin, axis), label or f"{size.lower()}_screw")

    def bolt_circle(self, size, loc, radius, n, phase=0.0, z=0.0, flip=False, label=None):
        """n screw heads on a circle in the plane local z = `z` of `loc`, heads toward local +Z
        (or -Z with `flip`)."""
        turn = bd.Rot(180, 0, 0) if flip else bd.Location()
        return [inst(self.screws[size], loc * bd.Pos(x, y, z) * turn, label or f"{size.lower()}_screw")
                for x, y in ring_positions(n, radius, phase)]

    def pivot_cap(self, radius, origin, axis, finish="joint", label="pivot_cap"):
        key = (round(radius, 2), finish)
        if key not in self._caps:
            self._caps[key] = proto(_pivot_cap(radius), finish)
        return inst(self._caps[key], frame(origin, axis), label)

    # -- actuators ----------------------------------------------------------------------
    def actuator(self, size, origin, axis, x_dir=None, name=None, turn=0.0):
        """Place an actuator: its mounting face at `origin`, output toward `axis`, turned
        `turn` degrees about its axis.

        Returns (stator_parts, rotor_parts): the stator's go in the parent link, with the
        screws that hold its mounting plate to the actuator's face, their heads sunk flush
        in the plate's far side (`mount_bores` cuts the counterbores); the output goes in the
        child link.
        """
        if name in DRIVES and DRIVES[name][0] != size:
            raise ValueError(f"{name} is an {DRIVES[name][0]} in dims.DRIVES, not an {size}")
        spec, protos = ACTUATORS[size], self.act[size]
        loc = frame(origin, axis, x_dir) * bd.Rot(0, 0, turn)
        tag = name or size.lower()
        stator = [inst(protos["housing"], loc, f"{tag}_housing"), inst(protos["cap"], loc, f"{tag}_cap")]
        screw, count, pitch = spec["mount"]
        if _heads_show(spec):
            stator += self.bolt_circle(screw, loc, pitch, count, phase=180.0 / count, z=PLATE_T - SCREWS[screw][1])
        rotor = [inst(protos["rotor"], loc, f"{tag}_output")]
        return stator, rotor

    def rotor_screws(self, size, origin, axis, lug_t, n=None, x_dir=None, sunk=0.0):
        """The screws that hold a child's lug (lug_t thick) on an actuator's output flange;
        `sunk` seats the heads that deep in counterbores (`rotor_counterbores` cuts them)."""
        screw, radius, count = rotor_pattern(size, n)
        return self.bolt_circle(screw, frame(origin, axis, x_dir), radius, count, z=ROTOR_PROUD + lug_t - sunk)


def _heads_show(spec):
    """The three larger models are held by cap screws; the two small cans by countersunk ones, which show no heads."""
    return spec["front"][0] > 30.0


def mount_bores(size, origin, axis, x_dir=None, turn=0.0):
    """Cutting tool for an actuator's mounting plate: the register's hole, and the counterbores
    that sink its mounting screws' heads flush in the plate's far side."""
    spec = ACTUATORS[size]
    screw, count, pitch = spec["mount"]
    d, h, _ = SCREWS[screw]
    loc = frame(origin, axis, x_dir) * bd.Rot(0, 0, turn)
    low = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    tool = loc * bd.Pos(0, 0, -1.0) * bd.Cylinder(max(spec["pilot"][0], spec["hub"]) + 0.6, PLATE_T + 2.0, align=low)
    if _heads_show(spec):
        for x, y in ring_positions(count, pitch, 180.0 / count):
            tool += loc * bd.Pos(x, y, PLATE_T - h) * bd.Cylinder(d / 2 + 0.4, h + 1.0, align=low)
    return tool


def rotor_pattern(size, n=None):
    """(screw size, bolt-circle radius, count) of an actuator's output flange."""
    screw, count, pitch = ACTUATORS[size]["out"]
    return screw, pitch, n or count


def rotor_counterbores(size, origin, axis, lug_t, n=None, x_dir=None):
    """Cutting tool: counterbores that sink the rotor screws' heads flush in a lug."""
    screw, radius, count = rotor_pattern(size, n)
    d, h, _ = SCREWS[screw]
    loc = frame(origin, axis, x_dir)
    tool = None
    for x, y in ring_positions(count, radius):
        bore = loc * bd.Pos(x, y, ROTOR_PROUD + lug_t - h) * bd.Cylinder(
            d / 2 + 0.4, h + 1.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        tool = bore if tool is None else tool + bore
    return tool


def pushrod(p0, p1, tube_r, eye_r, eye_w, pin_r, pin_axis=(1.0, 0.0, 0.0), label="pushrod", finish="titanium",
            nut_af=None):
    """A pushrod with a rod-end eye at each end: p0 and p1 are the pin centres, the eyes'
    bores lie along `pin_axis`. A jam nut (`nut_af` across flats) locks each rod end; it is
    kept narrower than the eye, so the rod swings between a clevis's cheeks."""
    nut_af = nut_af or 2.08 * tube_r
    a, b = bd.Vector(*p0), bd.Vector(*p1)
    u = (b - a).normalized()
    neck = eye_r * 0.8
    body = geo.rod(tuple(a + u * neck), tuple(b - u * neck), tube_r)
    for centre, sign in ((a, 1.0), (b, -1.0)):
        eye = geo.cyl(eye_r, eye_w, tuple(centre), pin_axis, centered=True)
        shank = geo.rod(tuple(centre + u * (sign * eye_r * 0.5)), tuple(centre + u * (sign * (neck + 14.0))), tube_r * 0.72)
        nut = geo.hex_prism(nut_af, 5.0, origin=tuple(centre + u * (sign * (neck + 8.0))), axis=tuple(u * sign))
        body = body + eye + shank + nut
    for centre in (a, b):
        body = body - geo.cyl(pin_r, eye_w + 4.0, tuple(centre), pin_axis, centered=True)
    return part(body, label, finish)


def pin(origin, axis, radius, length, head_r=None, head_t=2.5, label="pin", finish="steel"):
    """A headed pivot pin from `origin` along `axis`; the head sits behind the origin."""
    body = geo.cyl(radius, length, origin, axis)
    if head_r:
        o = bd.Vector(*origin) - bd.Vector(*axis).normalized() * head_t
        body = body + geo.cyl(head_r, head_t, tuple(o), axis)
    return part(body, label, finish)


__all__ = ["Hardware", "pushrod", "pin", "ring_positions", "rotor_pattern", "rotor_counterbores", "mount_bores", "PLATE_T",
           "ROTOR_PROUD"]
