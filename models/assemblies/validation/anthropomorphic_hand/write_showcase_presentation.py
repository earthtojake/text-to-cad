"""Write the hand's showcase render module: the tendons and actuators drive it.

The module this writes is `STEP/anthropomorphic_hand/<name>.step.js`, loaded by
the viewer and by `cadgen step snapshot --animation`/`--video`.

The point of this model is that finger motion comes from a cord being spooled in
a forearm, so an animation that moves the phalanges and leaves the cords behind
shows the wrong thing. Everything here follows from that:

1. THE TIMELINE LIVES HERE, not in the module. Poses are sampled on one grid and
   everything else — routes, payout, body frames — is solved on that same grid,
   so the cords cannot drift out of step with the fingers.
2. THE ROUTES ARE SOLVED, not approximated. `lib.hand_routing.full_tendon_routes`
   takes a pose and the capstan rotations and returns all 48 posed centerlines,
   asserting its own joins; at pose zero it reproduces `NEUTRAL_ROUTES` to the
   bit, so it IS the code that owns this geometry. A render module cannot call
   it — it is Python, and re-deriving routing in JavaScript would fork the one
   solver — so the solved poses are baked here and the module interpolates
   between them. Only ~13% of the control numbers move, so a keyframe is small.
3. THE PAYOUT IS THE MECHANISM'S OWN EQUATION. `lib.actuator_payout.solve_rotation`
   solves L_forearm(q) + L_downstream(pose) = L_total(neutral) per tendon: the
   capstan turns exactly enough to keep the cord's total length constant. That
   angle both re-cuts the forearm wrap and turns the spool.
4. THE ACTUATOR PARTS MOVE BY `lib.actuator_kinematics.actuator_transform`. That
   function is small, fixed, and covered by `check_actuator_kinematics.py`, so
   the module carries a faithful port of it rather than a baked matrix per part
   per keyframe; `ACTUATOR_SAMPLES` pins the port against this Python.

The one thing not solved here is WRIST motion. `full_tendon_routes` needs a
wrist packet measured for the pose, and that transport solve is the expensive
checkpointed job — so the showcase moves fingers and thumb, where the neutral
packet is exact, and does not pretend about the wrist.
"""
import copy
import gzip
import hashlib
import json
import math
import sys
import time as time_module
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'src/anthropomorphic_hand'
sys.path.insert(0, str(SOURCE))

from lib.actuator_kinematics import INPUT_ROLES, OUTPUT_ROLES, actuator_transform  # noqa: E402
from lib.actuator_payout import solve_rotation  # noqa: E402
from lib.forearm_routing import forearm_route  # noqa: E402
from lib.hand_routing import full_tendon_routes  # noqa: E402
from lib.layout import FINGERS, JOINTS, NEUTRAL_FINGER_FAN, TENDONS  # noqa: E402
from lib.neutral_routes import NEUTRAL_ROUTES  # noqa: E402
from lib.path_analysis import path_length  # noqa: E402

# Only the document whose body list this generator reads. A clip's targets are
# checked against the compiled tree at LOAD — a label the document does not
# carry is an error, not a silent no-op — and the earlier revisions are
# different body sets, so they keep the static presentation they already have.
TARGETS = ('hand_mechanical_candidate_r13',)

TENDON_BY_NAME = {tendon['name']: tendon for tendon in TENDONS}

# Poses per second. The pose functions are smooth, so linear interpolation
# between samples this close stays well under a tenth of a degree; the cost is
# one route solve (tens of seconds) per sample, run across a process pool.
KEYFRAME_RATE = 4.0
# Coordinates are rounded to keep a keyframe small. A join survives any rounding
# — consecutive segments meet at numbers that are EQUAL before it and therefore
# equal after it — and the tangent turn that rounding would introduce is undone
# by the module's own seal, which makes the two handles at a join exactly
# collinear whatever their inputs. So this is set by what the eye needs, not by
# `compileTubePath`: a micron, on a cord 0.3 mm across.
COORD_DECIMALS = 3


# --- the choreography -------------------------------------------------------
# A motion is a pure function of u in [0, 1]. Fingers and thumb only: see the
# wrist note in this file's docstring.

def clamp01(value):
    return max(0.0, min(1.0, value))


def ease(value):
    u = clamp01(value)
    return u * u * (3 - 2 * u)


def pulse(u, rise=0.3, fall=0.3):
    t = clamp01(u)
    if t < rise:
        return ease(t / rise)
    if t > 1 - fall:
        return ease((1 - t) / fall)
    return 1.0


FINGER_NAMES = ('index', 'middle', 'ring', 'little')


def curl(pose, finger, amount):
    """One finger's three flexion joints, in the ratio a tendon-driven finger takes."""
    a = clamp01(amount)
    pose[f'{finger}_mcp_flexion'] = 88 * a
    pose[f'{finger}_pip'] = 105 * a
    pose[f'{finger}_dip'] = 72 * a


def spread(pose, amount):
    pose['index_mcp_abduction'] = -18 * amount
    pose['middle_mcp_abduction'] = -4 * amount
    pose['ring_mcp_abduction'] = 12 * amount
    pose['little_mcp_abduction'] = 23 * amount


def thumb_oppose(pose, amount):
    a = clamp01(amount)
    pose['thumb_cmc_abduction'] = 40 * a
    pose['thumb_cmc_flexion'] = 52 * a
    pose['thumb_mcp_flexion'] = 40 * a
    pose['thumb_ip'] = 30 * a


def fist_pose(u):
    pose = {}
    close = pulse(u, 0.35, 0.35)
    # The little finger leads and the index trails, as a real hand closes.
    for index, finger in enumerate(FINGER_NAMES):
        curl(pose, finger, clamp01(close * 1.25 - (3 - index) * 0.08))
    thumb_oppose(pose, max(0.0, close - 0.25) / 0.75)
    spread(pose, -0.35 * close)
    return pose


def wave_pose(u):
    pose = {}
    # A travelling wave: each finger curls a beat after the last.
    for index, finger in enumerate(FINGER_NAMES):
        phase = clamp01(u * 1.5 - index * 0.11)
        curl(pose, finger, math.sin(math.pi * clamp01(phase * 1.4)) ** 2)
    thumb_oppose(pose, 0.15 * pulse(u))
    return pose


def pinch_pose(u):
    pose = {}
    close = pulse(u, 0.4, 0.4)
    curl(pose, 'index', 0.42 * close)
    curl(pose, 'middle', 0.12 * close)
    thumb_oppose(pose, close)
    pose['thumb_mcp_abduction'] = -10 * close
    pose['index_mcp_abduction'] = -14 * close
    return pose


def spread_pose(u):
    pose = {}
    spread(pose, pulse(u, 0.35, 0.35))
    for finger in FINGER_NAMES:
        curl(pose, finger, 0.06 * pulse(u))
    thumb_oppose(pose, 0.1 * pulse(u))
    return pose


MOTIONS = (
    {'id': 'fist', 'label': 'Make a fist', 'seconds': 6.0, 'pose': fist_pose},
    {'id': 'wave', 'label': 'Finger roll', 'seconds': 7.0, 'pose': wave_pose},
    {'id': 'pinch', 'label': 'Thumb-to-index pinch', 'seconds': 6.0, 'pose': pinch_pose},
    {'id': 'spread', 'label': 'Splay and gather', 'seconds': 5.0, 'pose': spread_pose},
)
TOUR_SECONDS = sum(motion['seconds'] for motion in MOTIONS)


def tour_pose(t):
    start = 0.0
    for motion in MOTIONS:
        if t < start + motion['seconds']:
            return motion['pose']((t - start) / motion['seconds'])
        start += motion['seconds']
    return MOTIONS[-1]['pose'](1.0)


def keyframe_times():
    """The one time grid, closing on the tour's own end."""
    count = int(round(TOUR_SECONDS * KEYFRAME_RATE))
    return [round(index / KEYFRAME_RATE, 6) for index in range(count + 1)]


# --- solving ----------------------------------------------------------------

def wrist_packet():
    """The measured wrist span, lifted out of the frozen neutral routes.

    Exactly what `generate_final_fist_packet.py` hands the solver. It is the one
    input `full_tendon_routes` cannot derive, and it is only valid for the pose
    it was measured at — which is why the wrist stays put here.
    """
    return [
        {'name': route['name'],
         'path': copy.deepcopy(next(group['path'] for group in route['groups']
                                    if group['label'] == route['name'] + '_wrist_guide'))}
        for route in NEUTRAL_ROUTES
    ]


def solve_pose(pose):
    """The solver's own posed routes, and the payout each one demands.

    Only the expensive part lives here, because this is what the cache holds:
    `full_tendon_routes` for the pose, and the capstan rotation that keeps each
    cord's total length constant. Re-cutting the forearm at that rotation is
    cheap and is done in `build`, where changing it does not cost a re-solve.
    """
    routes = full_tendon_routes(wrist_packet(), pose=pose)
    neutral_length = {route['name']: route['length_mm'] for route in NEUTRAL_ROUTES}
    for route in routes:
        route['capstan_rotation'] = solve_rotation(
            route['name'], path_length(route['path']) - neutral_length[route['name']])
    return routes


def split_cubic(segment):
    """A cubic Bezier as two cubics, exactly (de Casteljau at the midpoint)."""
    p = [np.array(point, dtype=float) for point in segment['points']]
    a, b, c = (p[0] + p[1]) / 2, (p[1] + p[2]) / 2, (p[2] + p[3]) / 2
    d, e = (a + b) / 2, (b + c) / 2
    mid = (d + e) / 2
    return [{'kind': 'bezier', 'points': [[*p[0]], [*a], [*d], [*mid]]},
            {'kind': 'bezier', 'points': [[*mid], [*e], [*c], [*p[3]]]}]


# The stored wrap is quarter-turn Beziers plus a partial (capstan_path.stored_path),
# so its COUNT depends on how much rope is on the drum: twelve at rest, one more
# as the spool takes rope in. The module rebuilds every keyframe from one
# template, so the count has to be constant — and it can be, exactly: splitting a
# cubic at its midpoint reproduces the same curve as two cubics. Every wrap is
# split up to the most any pose in range needs, which changes no geometry at all.
WRAP_SEGMENTS = 13
IDENTITY_3X4 = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0.]


def normalize_wrap(path, target=WRAP_SEGMENTS):
    segments = list(path)
    if len(segments) > target:
        raise AssertionError(f'wrap has {len(segments)} segments, past the {target} ceiling')
    while len(segments) < target:
        longest = max(range(len(segments)),
                      key=lambda index: np.linalg.norm(
                          np.array(segments[index]['points'][3])
                          - np.array(segments[index]['points'][0])))
        segments[longest:longest + 1] = split_cubic(segments[longest])
    return segments


def wind_forearm(route, rotation):
    """Re-cut the drum end of one route at the payout angle.

    Without this the spool turns under a cord that does not move with it, which
    on a model whose whole point is that a motor spools a tendon reads as the
    cord being painted on. `forearm_route` gives the rope actually on the drum
    at that rotation; normalizing the wrap's segment count keeps the shape the
    module's template expects.
    """
    forearm = forearm_route(TENDON_BY_NAME[route['name']], rotation)
    groups = [dict(group) for group in forearm['groups']]
    for group in groups:
        if group['label'].endswith('_capstan_wrap'):
            group['path'] = normalize_wrap(group['path'])
    tail = route['groups'][len(forearm['groups']):]
    return groups + [dict(group) for group in tail]


def _solve_worker(job):
    time, pose = job
    routes = solve_pose(pose)
    return (time,
            [[{'label': group['label'], 'path': group['path']} for group in route['groups']]
             for route in routes],
            [route['capstan_rotation'] for route in routes])


def group_points(group):
    points = []
    for segment in group['path']:
        if segment['kind'] == 'bezier':
            points.extend(segment['points'])
        elif segment['kind'] == 'line':
            points.extend([segment['start'], segment['end']])
        else:
            points.extend([segment['center'], segment['start']])
    return np.array(points, dtype=float)


def rigid_fit(source, target):
    """The rigid transform taking `source` points onto `target` (Kabsch).

    A guide that bridges two frames is placed by the ROUTING, not by a link, so
    the solver never says where it ends up — and riding it on either neighbouring
    frame throws it out of the hand. What it does ride is the span it guides, and
    that span's own rigid motion is exactly this fit. Returns a 3x4 row-major
    transform, or None when the span is too degenerate to fit (a straight run of
    two points cannot pin a rotation about its own axis, and does not need to).
    """
    if len(source) < 3:
        return None
    source_center = source.mean(axis=0)
    target_center = target.mean(axis=0)
    a = source - source_center
    b = target - target_center
    if np.linalg.norm(a) < 1e-9:
        return None
    u, _, vt = np.linalg.svd(a.T @ b)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    rotation = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    translation = target_center - rotation @ source_center
    return [*rotation[0], translation[0], *rotation[1], translation[1], *rotation[2], translation[2]]


def solve_timeline(times):
    """Solved paths for every keyframe, cached on the inputs that produce them.

    A solve is tens of seconds per pose and the encoding below it changed more
    than once; caching the SOLVER's own output — not the encoded numbers — means
    an encoding change costs nothing. The key covers the timeline and every
    routing source, so editing a motion or the solver re-solves.
    """
    # The routing sources and the timeline, NOT this file: how a solved route is
    # encoded for the module changed more than once, and re-solving for that
    # would be nine minutes to reach identical geometry.
    sources = sorted(SOURCE.glob('lib/*.py'))
    key = hashlib.sha256(json.dumps({
        'shape': 'groups+payout v2',
        'times': times,
        'poses': [tour_pose(time) for time in times],
        'sources': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
    }, sort_keys=True).encode()).hexdigest()
    cache = HERE / 'showcase_routes.cache.json.gz'
    if cache.exists():
        saved = json.loads(gzip.decompress(cache.read_bytes()))
        if saved.get('key') == key:
            print(f'reusing {len(saved["frames"])} solved keyframes from {cache.name}', flush=True)
            return [(entry['t'], entry['paths'], entry['q']) for entry in saved['frames']]
    print(f'solving {len(times)} keyframes over {TOUR_SECONDS:.0f}s at {KEYFRAME_RATE:g}/s',
          flush=True)
    started = time_module.perf_counter()
    solved = []
    with ProcessPoolExecutor() as pool:
        for done, row in enumerate(pool.map(_solve_worker, [(t, tour_pose(t)) for t in times]), 1):
            solved.append(row)
            print(f'  keyframe {done}/{len(times)} at {row[0]:.2f}s', flush=True)
    elapsed = time_module.perf_counter() - started
    print(f'solved {len(times)} keyframes in {elapsed / 60:.1f} min '
          f'({elapsed / len(times):.1f}s each, wall)', flush=True)
    cache.write_bytes(gzip.compress(json.dumps(
        {'key': key, 'seconds': elapsed,
         'frames': [{'t': t, 'paths': paths, 'q': q} for t, paths, q in solved]},
        separators=(',', ':')).encode()))
    return solved


# --- the number vector a route's geometry is --------------------------------
# One flat list per route, so a keyframe is a diff against neutral rather than a
# second copy of every path. Arcs carry a sweep as well as points: a joint's
# drive wrap changes how far it wraps, not only where it sits.

# A FIXED number of pieces per arc, not one per so many degrees: the drive wrap
# at a joint sweeps further as the joint moves, so a count derived from the
# sweep would change the segment count between keyframes — which is exactly what
# the module's single template cannot absorb. Four pieces hold the widest wrap
# here to a fraction of a micron, well inside the 0.3 mm tendon.
ARC_PIECES = 4


def arc_to_beziers(segment, pieces=ARC_PIECES):
    """A circular arc as a chain of cubic Beziers.

    An arc is center + axis + start + sweep, and NONE of those interpolate: the
    module blends two solved keyframes number by number, and between two arcs
    whose axes differ by up to 13 degrees the blended start no longer lies in
    the blended axis's plane — which `compileTubePath` refuses, rightly. A
    Bezier carries explicit endpoints instead, and endpoints shared between
    consecutive segments blend to the same place, so the chain stays joined
    whatever the blend does.
    """
    center = np.array(segment['center'], dtype=float)
    axis = np.array(segment['axis'], dtype=float)
    axis = axis / np.linalg.norm(axis)
    radial = np.array(segment['start'], dtype=float) - center
    radius = float(np.linalg.norm(radial))
    sweep = math.radians(float(segment['sweepDeg']))
    count = pieces
    step = sweep / count

    def at(angle):
        c, s = math.cos(angle), math.sin(angle)
        point = center + c * radial + s * np.cross(axis, radial)
        tangent = -s * radial + c * np.cross(axis, radial)
        return point, tangent / np.linalg.norm(tangent)

    # The classic cubic fit: control points (4/3)tan(phi/4) of a radius along
    # the end tangents, which touches the arc at both ends and at its midpoint.
    handle = radius * (4.0 / 3.0) * math.tan(abs(step) / 4.0) * (1 if step >= 0 else -1)
    out = []
    for index in range(count):
        p0, t0 = at(index * step)
        p3, t3 = at((index + 1) * step)
        out.append({'kind': 'bezier', 'points': [
            [*p0], [*(p0 + t0 * handle)], [*(p3 - t3 * handle)], [*p3]]})
    return out


def flatten_arcs(path):
    return [out for segment in path
            for out in (arc_to_beziers(segment) if segment['kind'] == 'arc' else [segment])]


def segment_numbers(segment):
    if segment['kind'] == 'bezier':
        return [value for point in segment['points'] for value in point]
    if segment['kind'] == 'line':
        return [*segment['start'], *segment['end']]
    raise ValueError(f"unknown segment kind {segment['kind']} (arcs are flattened first)")


def path_numbers(path):
    return [value for segment in flatten_arcs(path) for value in segment_numbers(segment)]


def path_template(path):
    return [segment['kind'] for segment in flatten_arcs(path)]


# --- emission ---------------------------------------------------------------

def joint_table():
    return [{'name': j.name, 'parent': j.parent, 'origin': list(j.origin),
             'axis': list(j.axis), 'limits': list(j.limits), 'system': j.system}
            for j in JOINTS]


def fan_table():
    return {f.name: {'deg': NEUTRAL_FINGER_FAN[f.name],
                     'origin': [f.x, f.base_y, 0.],
                     'parent': 'palm_cup' if f.name == 'little' else 'wrist_flexion'}
            for f in FINGERS}


def tendon_table():
    """What the module needs to place an actuator part and name a rope."""
    return [{'name': t['name'], 'joint': t['joint'], 'sign': t['sign'],
             'center': [t['actuator_center'][0], t['actuator_center'][1], t['sign'] * 4.0]}
            for t in TENDONS]


def actuator_bodies(rows):
    """Body name -> [tendon index, role], for every part a capstan moves.

    `actuator_transform` returns None for fixed hardware (the motor case, the
    tie screws), and those bodies are simply absent here rather than carried
    with an identity.
    """
    moving = set(OUTPUT_ROLES) | set(INPUT_ROLES)
    table = {}
    for index, tendon in enumerate(TENDONS):
        prefix = tendon['actuator'] + '_'
        for row in rows:
            name = row['name']
            if not name.startswith(prefix):
                continue
            role = name[len(prefix):]
            if role in moving or role.startswith('gearbox_planet_'):
                table[name] = [index, role]
    return table


def actuator_samples():
    """(tendon, role, q) -> the matrix THIS Python produces, to pin the port."""
    samples = []
    for index in (0, 17, 47):
        for role in ('capstan', 'gearbox_sun', 'gearbox_planet_2', 'gearbox_planet_pin_3'):
            for q in (-1.1, 0.37):
                matrix = actuator_transform(TENDONS[index], role, q)
                samples.append({'tendon': index, 'role': role, 'q': q,
                                'm': [round(float(v), 9) for v in matrix.reshape(-1)]})
    return samples


def frame_bodies(rows):
    """(frame -> body names, bodies the routing places rather than a frame).

    Every body the build calls `variable` is placed by a ROUTING result: the 48
    tendons and the guides that carry them. A guide named after a route group in
    a real frame is bolted to that link and rides it; a guide named after a
    `variable` group is a compensating span BRIDGING two frames and re-seats as
    the joint moves, so riding it on either neighbour swings it out of the hand.
    """
    guide_frame = {group['label']: group['frame']
                   for route in NEUTRAL_ROUTES for group in route['groups']}
    tendons = {tendon['name'] for tendon in TENDONS}
    by_frame = {}
    routed = []
    unresolved = []
    for row in rows:
        name, frame = row['name'], row['frame']
        if name in tendons:
            continue
        if frame == 'variable':
            frame = guide_frame.get(name)
            if frame is None:
                unresolved.append(name)
                continue
            if frame == 'variable':
                routed.append(name)
                continue
        if frame == 'forearm':
            continue
        by_frame.setdefault(frame, []).append(name)
    assert not unresolved, f'bodies with no route group: {unresolved[:8]}'
    return {frame: sorted(names) for frame, names in sorted(by_frame.items())}, sorted(routed)


def wound_path(groups, rotation):
    return [segment for group in wind_forearm({'name': groups['name'], 'groups': groups['groups']},
                                              rotation)
            for segment in group['path']]


def build(rows):
    times = keyframe_times()
    neutral = solve_pose({})
    neutral_groups = [{'name': route['name'], 'groups': route['groups']} for route in neutral]
    base = [path_numbers(wound_path(groups, 0.0)) for groups in neutral_groups]
    templates = [path_template(wound_path(groups, 0.0)) for groups in neutral_groups]
    solved = {time: (groups, q) for time, groups, q in solve_timeline(times)}

    # The drum end is re-cut at the payout angle here rather than in the solve,
    # so changing how the rope is wound costs no re-solve.
    encoded = {}
    for time in times:
        groups, rotations = solved[time]
        encoded[time] = [
            path_numbers(wound_path({'name': TENDONS[index]['name'], 'groups': route_groups},
                                    rotations[index]))
            for index, route_groups in enumerate(groups)
        ]

    # Guides that bridge two frames ride the span they guide (see rigid_fit).
    guide_of_group = {}
    for route in NEUTRAL_ROUTES:
        for group in route['groups']:
            if group['frame'] == 'variable':
                guide_of_group[group['label']] = True
    guide_names = [row['name'] for row in rows if row['name'] in guide_of_group]
    neutral_span = {}
    for route in neutral:
        for group in route['groups']:
            if group['label'] in guide_of_group:
                neutral_span[group['label']] = group_points(group)
    guide_motion = {}
    for time in times:
        placements = {}
        for route_groups in solved[time][0]:
            for group in route_groups:
                label = group['label']
                if label not in neutral_span:
                    continue
                fit = rigid_fit(neutral_span[label], group_points(group))
                if fit is not None and max(abs(fit[3]), abs(fit[7]), abs(fit[11])) > 1e-9:
                    placements[label] = [round(value, 6) for value in fit]
        guide_motion[time] = placements
    moving_guides = sorted({label for placements in guide_motion.values() for label in placements}
                           & set(guide_names))

    # The module reconstructs every keyframe from ONE segment template, so a
    # route whose shape changed under a pose would be silently truncated by the
    # zip below. It is an error instead.
    for time in times:
        for index, numbers in enumerate(encoded[time]):
            if len(numbers) != len(base[index]):
                raise AssertionError(
                    f'{TENDONS[index]["name"]} changes segment structure at t={time}: '
                    f'{len(numbers)} numbers against the neutral {len(base[index])}')

    # Which numbers move at all. A route is mostly forearm and the forearm is
    # ground, so this is where a keyframe gets small.
    varying = []
    for index, neutral_numbers in enumerate(base):
        varying.append(sorted({
            position
            for time in times
            for position, (a, b) in enumerate(zip(encoded[time][index], neutral_numbers))
            if abs(a - b) > 1e-6
        }))
    total = sum(len(numbers) for numbers in base)
    moving = sum(len(positions) for positions in varying)
    print(f'{moving}/{total} route numbers move ({100 * moving / total:.0f}%)', flush=True)

    keyframes = []
    for time in times:
        numbers, rotations = encoded[time], solved[time][1]
        keyframes.append({
            't': time,
            'pose': {key: round(value, 4) for key, value in tour_pose(time).items() if value},
            'q': [round(value, 6) for value in rotations],
            'v': [round(numbers[index][position], COORD_DECIMALS)
                  for index, positions in enumerate(varying)
                  for position in positions],
            'g': [value
                  for label in moving_guides
                  for value in (guide_motion[time].get(label) or IDENTITY_3X4)],
        })
    frames, routed = frame_bodies(rows)
    return {
        'joints': joint_table(),
        'fan': fan_table(),
        'tendons': tendon_table(),
        'actuatorBodies': actuator_bodies(rows),
        'actuatorSamples': actuator_samples(),
        'frames': frames,
        'routed': routed,
        'ropeTemplates': templates,
        'ropeBase': [[round(value, COORD_DECIMALS) for value in numbers] for numbers in base],
        'ropeVarying': varying,
        'ropeNormals': [[t['sign'], 0, 0] for t in TENDONS],
        'ropeNames': [t['name'] for t in TENDONS],
        'guides': moving_guides,
        'motions': [{'id': m['id'], 'label': m['label'], 'seconds': m['seconds']} for m in MOTIONS],
        'keyframes': keyframes,
    }


def write_module(path, data, runtime):
    dumps = lambda value: json.dumps(value, separators=(',', ':'))  # noqa: E731
    text = (
        '// Generated by validation/anthropomorphic_hand/write_showcase_presentation.py.\n'
        '// The timeline, the solved tendon routes and the payout all come from there;\n'
        '// edit the generator and its showcase_runtime.js, never this file.\n'
        f'const JOINTS = {dumps(data["joints"])};\n'
        'const JOINT_BY_NAME = Object.fromEntries(JOINTS.map((j) => [j.name, j]));\n'
        f'const FAN = {dumps(data["fan"])};\n'
        f'const FRAME_BODIES = {dumps(data["frames"])};\n'
        f'const TENDONS = {dumps(data["tendons"])};\n'
        f'const ACTUATOR_BODIES = {dumps(data["actuatorBodies"])};\n'
        f'const ACTUATOR_SAMPLES = {dumps(data["actuatorSamples"])};\n'
        f'const ROPE_NAMES = {dumps(data["ropeNames"])};\n'
        f'const ROPE_NORMALS = {dumps(data["ropeNormals"])};\n'
        f'const ROPE_TEMPLATES = {dumps(data["ropeTemplates"])};\n'
        f'const ROPE_BASE = {dumps(data["ropeBase"])};\n'
        f'const ROPE_VARYING = {dumps(data["ropeVarying"])};\n'
        f'const GUIDE_BODIES = {dumps(data["guides"])};\n'
        f'const MOTIONS = {dumps(data["motions"])};\n'
        f'const KEYFRAMES = {dumps(data["keyframes"])};\n'
        + runtime
    )
    path.write_text(text)
    return len(text)


def main():
    rows = json.loads((HERE / 'mechanical_candidate_r13_frames.json').read_text())
    runtime = (HERE / 'showcase_runtime.js').read_text()
    data = build(rows)
    folder = ROOT / 'STEP/anthropomorphic_hand'
    for name in TARGETS:
        size = write_module(folder / f'{name}.step.js', data, runtime)
    print(f'wrote {len(TARGETS)} render module(s), {size / 1024:.0f} KB: '
          f'{sum(len(v) for v in data["frames"].values())} bodies on {len(data["frames"])} frames, '
          f'{len(data["actuatorBodies"])} actuator parts, {len(data["guides"])} fitted guides, '
          f'{len(data["keyframes"])} keyframes')


if __name__ == '__main__':
    main()
