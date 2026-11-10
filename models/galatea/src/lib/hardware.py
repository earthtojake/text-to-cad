"""Hardware every link shares: cap screws, the RobStride actuators, pivot caps, pushrods.

`Hardware()` builds each prototype once per run, in its own frame, so it can be placed on both
sides of the robot (`kit.inst`, `kit.mirror_tree`).

An actuator is its maker's own model: RobStride's STEP file, converted once to an xbf by
`vendor.py` and read here. Its frame: local Z is its axis, z = 0 its mounting face (the front of
its main body, where its tapped mounting holes are). The body lies behind the face (z < 0). The
parent link's mounting plate (PLATE_T thick) lies on the face and is screwed to it from the
far side, into the maker's holes. The output flange is in the middle of the face; a hub
bolted to it stands through the plate and ROTOR_PROUD past the face, where the child
link's lug bolts on, on the output flange's own bolt circle. The two smallest models are
held by countersunk screws, which show no heads.

A drive is not its own mirror image (its connectors sit to one side), and the right side of the
robot carries the same part as the left, not a reflection: `mirror_tree` places a prototype
again, turned, and each model is stood in its frame so that its mounting holes are symmetric
about the local YZ plane, which is what lets one bracket and its mirror image both meet them.

RobStride draws each drive as one solid, so the output flange in it does not turn with the
joint. The hub that bolts to the flange is this robot's part and does turn; where the flange
carries locating pins the hub is relieved in a ring over them, where a real one has holes.
"""

import math
from pathlib import Path

import build123d as bd
from cad import xbf

from . import finish, geo
from .dims import ACTUATORS, DRIVES, PLATE_T, ROTOR_PROUD, SCREWS
from .kit import frame, inst, part, proto

VENDOR = Path(__file__).resolve().parents[2] / "vendor"


def ring_positions(n, radius, phase=0.0):
    return [(radius * math.cos(math.radians(phase + 360.0 * k / n)),
             radius * math.sin(math.radians(phase + 360.0 * k / n))) for k in range(n)]


def _screw_head(size):
    d, h, af = SCREWS[size]
    head = geo.revolve([(0, 0), (d / 2, 0), (d / 2, h - 0.5), (d / 2 - 0.5, h), (0, h)])
    socket = geo.hex_prism(af, h * 0.6, origin=(0, 0, h * 0.45))
    return head - socket


def _vendor(size, spec):
    """RobStride's model of one drive, stood in the actuator's frame: mounting face at z = 0, output
    toward +Z, turned so that its tapped mounting holes lie where the screws go."""
    path = VENDOR / f"{size}.xbf"
    if not path.exists():
        raise FileNotFoundError(f"{path.name} is not in {VENDOR}: run `cad run src/vendor.py` once; it fetches "
                                "RobStride's STEP files (53 MB, from github.com/RobStride/Product_Information)")
    solids = sorted(xbf.read(path).solids(), key=lambda solid: -solid.volume)
    body = solids[0]
    for extra in solids[1:]:                       # the RS00's two connector sockets are solids of their own
        body = geo.fuse(body, extra, f"{size}'s sockets")
    return stood(size) * body


def stood(size):
    """How the maker's file stands in the actuator's frame (`dims.ACTUATORS[size]["step"]`): a prototype of
    a drive carries this as its own location, so a placement of one is the actuator's frame times this."""
    flip, face, turn = ACTUATORS[size]["step"]
    return bd.Rot(0, 0, turn) * (bd.Rot(180, 0, 0) if flip else bd.Location()) * bd.Pos(0, 0, -face)


def _sector(r0, r1, a0, a1, z0, z1, steps=6):
    """An annular sector between two radii and two angles (degrees), from z0 to z1."""
    arc = [math.radians(a0 + (a1 - a0) * k / steps) for k in range(steps + 1)]
    outline = [(r1 * math.cos(a), r1 * math.sin(a)) for a in arc] + [(r0 * math.cos(a), r0 * math.sin(a)) for a in reversed(arc)]
    return geo.plate_xy(geo.polygon(*outline), z0, z1)


def envelope(size):
    """A plain closed solid that holds the maker's model of a drive, for the checks: the exact
    intersection of two parts is beyond this machine when one of them has three thousand faces.
    Turned steps to the maker's radii, a cylinder over each screw lobe, a block over a connector
    that stands proud; `checks/drives.py` shows that each holds its drive and by how little more."""
    low = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    can = lambda radius, z0, z1: bd.Pos(0, 0, z0) * bd.Cylinder(radius, z1 - z0, align=low)
    lobes = lambda count, at, radius, z0, z1: [bd.Pos(x, y, z0) * bd.Cylinder(radius, z1 - z0, align=low)
                                                 for x, y in ring_positions(count, at, 180.0 / count)]
    ring = lambda r0, r1, z0, z1: geo.revolve([(r0, z0), (r1, z0), (r1, z1), (r0, z1)])
    if size == "RS04":
        pieces = [can(60.1, -39.1, 0.0), can(47.2, -52.3, -39.0), _sector(46.0, 58.5, 84.0, 96.0, -49.6, -41.1),
                  can(25.3, -0.5, 0.5), ring(14.9, 20.9, 0.0, 3.5)]
    elif size == "RS03":
        pieces = [can(48.3, -39.6, 0.0), _sector(44.0, 51.2, -114.0, -66.0, -39.6, 0.0), can(50.9, -2.7, 0.0),
                  can(49.4, -40.1, -36.7), can(40.3, -54.2, -39.5), *lobes(8, 49.0, 4.3, -43.7, 0.0),
                  can(35.55, -0.5, 0.25), can(35.1, 0.0, 2.5)]
    elif size == "RS06":
        pieces = [can(41.7, -33.1, 0.0), can(35.1, -49.1, -33.0), *lobes(8, 41.0, 3.2, -36.2, 0.0),
                  _sector(40.0, 43.7, 166.0, 194.0, -33.1, 0.0), can(26.55, -0.5, 0.25), can(26.1, 0.0, 1.5)]
    elif size == "RS00":
        pieces = [can(28.6, -51.2, 0.0), can(17.6, -0.5, 1.0)]
    elif size == "RS05":
        pieces = [can(23.1, -44.1, 0.0), can(23.7, -39.6, -33.2), ring(7.1, 11.9, -0.5, 3.0)]
    else:
        raise KeyError(size)
    body = pieces[0]
    for piece in pieces[1:]:
        body = body + piece
    return body


def _rotor(spec):
    """The hub bolted to the output flange, seated on the flange's face. Over locating pins it is
    relieved in a ring: the maker's solid does not turn, the hub does."""
    hub, seat = spec["hub"], spec["flange"]
    body = geo.revolve([(0.0, seat), (hub, seat), (hub, ROTOR_PROUD - 0.8), (hub - 0.8, ROTOR_PROUD), (0.0, ROTOR_PROUD)])
    if spec["pins"]:
        r, at, top = spec["pins"]
        body -= geo.revolve([(at - r - 0.4, seat - 1.0), (at + r + 0.4, seat - 1.0), (at + r + 0.4, top + 0.4), (at - r - 0.4, top + 0.4)])
    return body


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
            housing = _vendor(size, spec)
            # One homogenised density for the unit, so that the maker's solid weighs what the maker says.
            look = finish.actuator(size, spec["kg"] / (housing.volume * 1e-9))
            self.act[size] = dict(housing=proto(housing, look, stood=stood(size)), rotor=proto(_rotor(spec), "steel"))
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
        stator = [inst(protos["housing"], loc, f"{tag}_housing")]
        screw, count, pitch = spec["mount"]
        if _heads_show(spec):
            stator += [inst(self.screws[screw], loc * bd.Pos(x, y, PLATE_T - SCREWS[screw][1]), f"{screw.lower()}_screw")
                       for x, y in mount_positions(size)]
        rotor = [inst(protos["rotor"], loc, f"{tag}_output")]
        return stator, rotor

    def rotor_screws(self, size, origin, axis, lug_t, n=None, x_dir=None, sunk=0.0):
        """The screws that hold a child's lug (lug_t thick) on an actuator's output flange;
        `sunk` seats the heads that deep in counterbores (`rotor_counterbores` cuts them)."""
        screw = ACTUATORS[size]["out"][0]
        loc = frame(origin, axis, x_dir)
        return [inst(self.screws[screw], loc * bd.Pos(x, y, ROTOR_PROUD + lug_t - sunk), f"{screw.lower()}_screw")
                for x, y in rotor_positions(size, n)]


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
        for x, y in mount_positions(size):
            tool += loc * bd.Pos(x, y, PLATE_T - h) * bd.Cylinder(d / 2 + 0.4, h + 1.0, align=low)
    return tool


def mount_positions(size):
    """Where a drive's tapped mounting holes are, in its frame."""
    spec = ACTUATORS[size]
    _, count, pitch = spec["mount"]
    return ring_positions(count, pitch, spec.get("mount_at", 180.0 / count))


def rotor_pattern(size, n=None):
    """(screw size, bolt-circle radius, count) of an actuator's output flange."""
    screw, count, pitch = ACTUATORS[size]["out"]
    return screw, pitch, n or count


def rotor_positions(size, n=None):
    """Where the output flange's tapped holes are, in the hub's frame: evenly round the circle, or
    as the maker spaces them (the RS04's nine keep clear of its three pins)."""
    spec = ACTUATORS[size]
    _, count, pitch = spec["out"]
    if n is None and "out_at" in spec:
        return [(pitch * math.cos(math.radians(a)), pitch * math.sin(math.radians(a))) for a in spec["out_at"]]
    return ring_positions(n or count, pitch)


def rotor_counterbores(size, origin, axis, lug_t, n=None, x_dir=None):
    """Cutting tool: counterbores that sink the rotor screws' heads flush in a lug."""
    d, h, _ = SCREWS[ACTUATORS[size]["out"][0]]
    loc = frame(origin, axis, x_dir)
    tool = None
    for x, y in rotor_positions(size, n):
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


__all__ = ["Hardware", "envelope", "stood", "mount_positions", "pushrod", "pin", "ring_positions", "rotor_pattern", "rotor_positions", "rotor_counterbores",
           "mount_bores", "PLATE_T", "ROTOR_PROUD"]
