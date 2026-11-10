"""Hardware every link shares: cap screws, the rotary actuator family, pivot caps, pushrods.

`Hardware()` builds each prototype once per run, in its own frame and symmetric about its
local YZ plane, so it can be placed on both sides of the robot (`kit.inst`, `kit.mirror_tree`).

An actuator's frame: local Z is its axis, z = 0 its mounting face. The stator's body lies
behind the face (z < 0); the output flange passes forward through the parent link's
mounting plate (PLATE_T thick) and stands ROTOR_PROUD past the face, where the child
link's lug bolts on. Stator screws sit on the back of the mounting flange; rotor screws
on the child's lug. The shaft is hollow: cables cross every joint on its axis.
"""

import math

import build123d as bd

from . import geo
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
    R, L, r_out, bore, ring = spec["R"], spec["L"], spec["r_out"], spec["bore"], spec["ring"]
    r_body = R - ring                 # fin tips
    r_root = r_body - min(3.2, 0.09 * R + 0.6)
    r_back = r_body - 1.0
    rb = bore + 1.5
    z_back = -(L - 7.0)
    pitch = 5.2 if R > 30 else 4.0
    fin = pitch / 2
    pts = [(rb, -L), (r_back - 1.0, -L), (r_back, -L + 1.0), (r_back, z_back), (r_root, z_back)]
    z = z_back
    while z + pitch <= -8.5:
        pts += [(r_root, z + fin), (r_body, z + fin), (r_body, z + pitch), (r_root, z + pitch)]
        z += pitch
    pts += [(r_root, -6.0), (R, -6.0), (R, -1.0), (R - 1.0, 0.0), (r_out + 1.0, 0.0), (r_out + 1.0, -4.0), (rb, -4.0)]
    return geo.revolve(pts)


def _cap(spec):
    R, L, bore, ring = spec["R"], spec["L"], spec["bore"], spec["ring"]
    r_cap = R - ring - 3.0
    t = 5.0 if R > 30 else 4.0
    dome_r = max(bore + 4.0, 0.42 * R)
    pts = [(bore, -L), (r_cap, -L), (r_cap, -L - t + 1.0), (r_cap - 1.0, -L - t), (dome_r + 1.5, -L - t),
           (dome_r, -L - t - 2.0), (bore, -L - t - 2.0)]
    cap = geo.revolve(pts)
    # Power/EtherCAT connector on the rim, at local +Y.
    w, d = 0.52 * R, 0.24 * R
    plug = bd.Pos(0, r_cap - d / 2 - 1.0, -L - t - 1.5) * bd.Box(w, d, 3.0)
    return cap + plug


def _cover(spec):
    """An ivory dress cover over the middle of the end cap, for the drives that show."""
    R, L, bore, ring = spec["R"], spec["L"], spec["bore"], spec["ring"]
    t = 5.0 if R > 30 else 4.0
    dome_r = max(bore + 4.0, 0.42 * R)
    r_c = min(dome_r + 2.0, (R - ring - 3.0) - 0.24 * R - 1.5)      # inside the connector on the rim
    z0 = -L - t - 2.0
    return geo.revolve([(bore + 2.0, z0), (r_c, z0), (r_c, z0 - 2.0), (r_c - 1.5, z0 - 3.5), (bore + 2.0, z0 - 3.5)])


def _rotor(spec):
    r_out, bore = spec["r_out"], spec["bore"]
    pts = [(bore, -4.0), (r_out, -4.0), (r_out, ROTOR_PROUD - 0.8), (r_out - 0.8, ROTOR_PROUD), (bore, ROTOR_PROUD)]
    return geo.revolve(pts)


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
            self.act[size] = dict(
                housing=proto(_housing(spec), "bronze"),
                cap=proto(_cap(spec), "graphite"),
                rotor=proto(_rotor(spec), "steel"),
                cover=proto(_cover(spec), "ivory"),
            )
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

    def pivot_cap(self, radius, origin, axis, finish="bronze_trim", label="pivot_cap"):
        key = (round(radius, 2), finish)
        if key not in self._caps:
            self._caps[key] = proto(_pivot_cap(radius), finish)
        return inst(self._caps[key], frame(origin, axis), label)

    # -- actuators ----------------------------------------------------------------------
    def actuator(self, size, origin, axis, x_dir=None, cap=True, cover=False, name=None):
        """Place an actuator: its mounting face at `origin`, output toward `axis`.

        Returns (stator_parts, rotor_parts): the stator's go in the parent link, the
        output flange in the child link. `cover` adds the ivory dress cover.
        """
        if name in DRIVES and DRIVES[name][0] != size:
            raise ValueError(f"{name} is an {DRIVES[name][0]} in dims.DRIVES, not an {size}")
        spec, protos = ACTUATORS[size], self.act[size]
        loc = frame(origin, axis, x_dir)
        tag = name or size.lower()
        stator = [inst(protos["housing"], loc, f"{tag}_housing")]
        if cap:
            stator.append(inst(protos["cap"], loc, f"{tag}_cap"))
        if cover:
            stator.append(inst(protos["cover"], loc, f"{tag}_cover"))
        stator += self.bolt_circle(spec["screw"], loc, spec["R"] - spec["ring"] / 2, spec["n"], phase=90.0 / spec["n"],
                                   z=-6.0, flip=True)
        rotor = [inst(protos["rotor"], loc, f"{tag}_output")]
        return stator, rotor

    def rotor_screws(self, size, origin, axis, lug_t, n=None, x_dir=None, sunk=0.0):
        """The screws that hold a child's lug (lug_t thick) on an actuator's output flange;
        `sunk` seats the heads that deep in counterbores (`rotor_counterbores` cuts them)."""
        screw, radius, count = rotor_pattern(size, n)
        return self.bolt_circle(screw, frame(origin, axis, x_dir), radius, count, z=ROTOR_PROUD + lug_t - sunk)


def rotor_pattern(size, n=None):
    """(screw size, bolt-circle radius, count) of an actuator's output flange."""
    spec = ACTUATORS[size]
    screw = "M3" if spec["r_out"] < 16 else "M4" if spec["r_out"] < 30 else "M5"
    head_r = SCREWS[screw][0] / 2
    return screw, spec["r_out"] - head_r - 1.6, n or max(6, spec["n"] - 2)


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


__all__ = ["Hardware", "pushrod", "pin", "ring_positions", "rotor_pattern", "rotor_counterbores", "PLATE_T", "ROTOR_PROUD"]
