"""Ordered actuator exit paths, before the wrist transport region.

Each of four columns carries six ropes on each forearm face. Proximal
actuators feed the outermost height tier so later exits stay beneath the
ropes already passing them. No physical clearance is inferred from order:
the validation program checks the resulting paths and actual bodies.
"""
from lib.layout import TENDONS
from lib.capstan_path import stored_path, endpoint, tangent
import numpy as np


def forearm_route(tendon, capstan_rotation=0.):
    x, y, z = tendon['capstan_center']
    sign = tendon['sign']
    row = round((y + 252.) / 41.)
    lane = tendon['bundle_lane']
    height = sign * (43. - 1.2 * row)
    # The groove and terminal rotate together. The free lead follows the
    # exact changing axial exit and its finite helix pitch, with no kink.
    local=stored_path(capstan_rotation)
    transform=np.diag([sign,1.,sign]); center=np.array([x,y,z])
    wrap=[{'kind':'bezier','points':(np.asarray(s['points'])@transform.T+center).tolist()} for s in local]
    end=endpoint(local)@transform.T+center
    direction=tangent(local)@transform.T
    lead = {'kind': 'line', 'start': end.tolist(), 'end': (end+5.*direction).tolist()}
    p0 = lead['end']
    p3 = [lane, y+30., height]
    exit_curve = {'kind': 'bezier', 'points': [p0, (np.asarray(p0)+10.*direction).tolist(),
                                               [lane, y+20., height], p3]}
    trunk = {'kind': 'line', 'start': p3, 'end': [lane, -12., height]}
    return {'name': tendon['name'], 'path': [*wrap, lead, exit_curve, trunk],
            'groups': [
                {'label': tendon['name']+'_capstan_wrap', 'path': wrap, 'frame': 'forearm', 'guide': 'capstan'},
                {'label': tendon['name']+'_capstan_lead', 'path': [lead], 'frame': 'forearm', 'guide': None},
                {'label': tendon['name']+'_exit_guide', 'path': [exit_curve], 'frame': 'forearm', 'guide': 'open_saddle'},
                {'label': tendon['name']+'_forearm_run', 'path': [trunk], 'frame': 'forearm', 'guide': None}],
            'inlet': wrap[0]['points'][0], 'outlet': trunk['end'],
            'start_normal': (np.array([np.cos(capstan_rotation),np.sin(capstan_rotation),0.])@transform.T).tolist()}


def forearm_routes():
    return [forearm_route(tendon) for tendon in TENDONS]
