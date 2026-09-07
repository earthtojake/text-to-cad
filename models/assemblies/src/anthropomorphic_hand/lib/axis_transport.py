"""Kernel-free finite-radius, exactly length-neutral joint-axis crossovers.

Local joint axis is +X. All centerline records use mm/degrees and canonical
line/arc dictionaries. arc.start is a point, arc.axis a unit rotation vector.
"""
from math import ceil, cos, pi, radians, sin, sqrt

BEND_RADIUS = 3.5
TENDON_RADIUS = 0.3
GUIDE_INNER_RADIUS = 0.35
GUIDE_OUTER_RADIUS = 0.55
AXIAL_SPAN = 0.9
# Conservative shared pitch; validated by validation/check_axis_transport.py.
STATION_PITCH = 5.8


def _add(a, b):
    return [a[i] + b[i] for i in range(3)]


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _scale(a, s):
    return [s * x for x in a]


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _norm(a):
    return sqrt(sum(x*x for x in a))


def segment_length(segment):
    if segment['kind'] == 'line':
        return _norm(_sub(segment['end'], segment['start']))
    return _norm(_sub(segment['start'], segment['center'])) * abs(radians(segment['sweepDeg']))


def point_at(segment, fraction):
    start = segment['start']
    if segment['kind'] == 'line':
        return _add(start, _scale(_sub(segment['end'], start), fraction))
    vector = _sub(start, segment['center'])
    axis = segment['axis']
    angle = radians(segment['sweepDeg']) * fraction
    dot = sum(axis[i] * vector[i] for i in range(3))
    turned = _add(_add(_scale(vector, cos(angle)), _scale(_cross(axis, vector), sin(angle))), _scale(axis, dot*(1-cos(angle))))
    return _add(segment['center'], turned)


def tangent_at(segment, fraction):
    if segment['kind'] == 'line':
        vec = _sub(segment['end'], segment['start'])
    else:
        vec = _cross(segment['axis'], _sub(point_at(segment, fraction), segment['center']))
        if segment['sweepDeg'] < 0:
            vec = _scale(vec, -1)
    return _scale(vec, 1/_norm(vec))


def sample_path(path, maximum_step=0.04):
    """Return samples and certified maximum along-curve spacing.

    Every continuous path point is <= spacing/2 from some sample, including
    endpoints. Hence min(sample distances) - spacing bounds two-path clearance.
    """
    points = []
    spacing = 0.0
    for segment in path:
        length = segment_length(segment)
        count = max(1, ceil(length/maximum_step))
        spacing = max(spacing, length/count)
        points.extend(point_at(segment, k/count) for k in range(count+1))
    return points, spacing


def crossover(channel, channels, angle_deg=0.0, angle_range=(-25.0, 110.0),
              radius=BEND_RADIUS, pitch=STATION_PITCH, axial_span=AXIAL_SPAN):
    """One nonoverlapping axis station, with parent and child routing datums.

    The child outlet is biased to center its required angular sector opposite
    the fixed inlet. q is an actual joint angle; the bias is fixed geometry.
    The array and its overall axial envelope are centered at X=0.
    """
    if not 0 <= channel < channels:
        raise ValueError('channel index outside the declared array')
    angle = radians(angle_deg - sum(angle_range)/2)
    radial = [0.0, cos(angle), sin(angle)]
    station = (channel-(channels-1)/2)*pitch
    a, b = station-axial_span/2, station+axial_span/2
    inlet_center = [a, -radius, 0.0]
    inlet = {'kind': 'arc', 'center': inlet_center, 'axis': [0.0,0.0,-1.0],
             'start': [a-radius,-radius,0.0], 'sweepDeg': 90.0}
    straight = {'kind': 'line', 'start': [a,0.0,0.0], 'end': [b,0.0,0.0]}
    outlet_center = _add([b,0.0,0.0], _scale(radial,radius))
    outlet = {'kind': 'arc', 'center': outlet_center, 'axis': _cross([1.0,0.0,0.0],radial),
              'start': [b,0.0,0.0], 'sweepDeg':90.0}
    path = [inlet, straight, outlet]
    return {'channel':channel, 'path':path,
            'inlet':{'point':inlet['start'], 'tangent':tangent_at(inlet,0), 'frame':'parent'},
            'outlet':{'point':point_at(outlet,1), 'tangent':tangent_at(outlet,1), 'frame':'child'},
            'axis_interval': [a,b], 'length':sum(segment_length(s) for s in path),
            'minimum_bend_radius':radius,
            'd_length_d_joint_radian':0.0,
            'angle_range':list(angle_range)}


def array_envelope(channels, radius=BEND_RADIUS, pitch=STATION_PITCH,
                   axial_span=AXIAL_SPAN, outer_radius=GUIDE_OUTER_RADIUS):
    """Conservative bounds valid through arbitrary rotation, not tight CAD bounds."""
    half=(channels-1)*pitch/2 + axial_span/2 + radius + outer_radius
    radial=radius+outer_radius
    return {'minimum':[-half,-radial,-radial], 'maximum':[half,radial,radial],
            'size':[2*half,2*radial,2*radial], 'body_envelope_radius':outer_radius}
