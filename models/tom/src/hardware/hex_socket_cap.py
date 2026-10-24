"""ISO 4762 hex socket head cap screws, the ordered 12.9 alloy-steel hardware.

Dimensions are the ISO 4762 maxima, which the ordered kits measure at or just
under (iexcell lists M3 5.50 x 2.93 and M2 3.80 x 1.93): M2 dk 3.8, k 2.0,
s 1.5, t 1.0; M3 dk 5.5, k 3.0, s 2.5, t 1.3. Both lengths are fully threaded,
which the joints need - a 2.032 mm bracket sits above a 2.1 mm horn plate, so an
unthreaded shank would leave nothing engaged.

Authored rather than pinned: no supplier STEP was found for these, and the
geometry is four primitives. As with the rest of this assembly's hardware the
thread is a smooth major-diameter envelope, for conservative fit checks. The
socket is a plain hexagonal recess, not a tolerance profile.

Bearing face at Z=0 with the head above it; insertion points along -Z.
"""
import math
import build123d as bd
from lib.materials import SCREW_COLOR

# thread diameter, under-head length, head diameter, head height, socket AF, socket depth
GEOMETRY = {
    'hex_socket_m2x6': (2.0, 6.0, 3.8, 2.0, 1.5, 1.0),
    'hex_socket_m3x5': (3.0, 5.0, 5.5, 3.0, 2.5, 1.3),
}


def _cap_screw(label):
    thread_d, length, head_d, head_h, socket_af, socket_depth = GEOMETRY[label]
    head = bd.Solid.make_cylinder(head_d / 2, head_h)
    shank = bd.Solid.make_cylinder(thread_d / 2, length,
                                   bd.Plane(origin=(0, 0, -length)))
    # Across-flats AF is twice the apothem, so the circumradius is AF/sqrt(3).
    recess = bd.extrude(bd.RegularPolygon(socket_af / math.sqrt(3), 6),
                        amount=socket_depth).moved(bd.Pos(0, 0, head_h - socket_depth))
    screw = head.fuse(shank).cut(recess).clean()
    if len(screw.solids()) != 1 or not screw.is_valid:
        raise ValueError(f'{label} must be one valid solid')
    screw.label = label
    screw.color = SCREW_COLOR
    return screw


def hex_socket_m2x6():
    return _cap_screw('hex_socket_m2x6')


def hex_socket_m3x5():
    return _cap_screw('hex_socket_m3x5')
