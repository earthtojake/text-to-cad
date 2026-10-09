"""Animation clips: authored in Python, baked to sidecar keyframes when the model builds.

The authoring half (``cadgen.clip``, ``animation=``) is validated at decoration;
the bake (``cadgen._internal.animation_bake``) samples each clip once and reduces
the samples to tracks every renderer interpolates. What is pinned here is what a
renderer and an author depend on: the keys rebuild the motion BETWEEN samples
within the stated tolerance, a track says each value once, a target names leaves
of the written document or fails by name, and the section a sidecar carries is
checked for the shape the renderers read. The renderers' half of the
interpolation is tested in JavaScript (packages/core).
"""

from __future__ import annotations

import bisect
import contextlib
import copy
import io
import json
import math
import re
import unittest
from pathlib import Path

from tests.python.support.cad_test_roots import IsolatedCadRoots
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

import cadgen  # noqa: E402
from cadgen._internal.animation_bake import (  # noqa: E402
    LENGTH_FLOOR,
    MAX_KEY_TURN_DEG,
    OPACITY_TOLERANCE,
    TRANSFORM_TOLERANCE,
    TUBE_TURN_TOLERANCE_DEG,
    AnimationError,
    _lerp_path,
    _path_points,
    _pose_at,
    animation_targets,
    bake_animation,
    bake_clip,
    key_path,
    normalize_baked_animation,
)
from cadgen.animation import Clip, normalize_clips  # noqa: E402

# A rig as a written document names it: a base, an arm GROUP of a link and a bolt,
# and a second bolt of the same name beside them.
DESCRIPTOR = {
    "occurrences": [{"id": "o1.1"}, {"id": "o1.2.1"}, {"id": "o1.2.2"}, {"id": "o1.3"}],
    "assembly": {"root": {"id": "o1", "name": "rig", "children": [
        {"id": "o1.1", "name": "base", "children": []},
        {"id": "o1.2", "name": "arm", "children": [
            {"id": "o1.2.1", "name": "link", "children": []},
            {"id": "o1.2.2", "name": "bolt", "children": []},
        ]},
        {"id": "o1.3", "name": "bolt", "children": []},
    ]}},
}
TARGETS = animation_targets(DESCRIPTOR)
BOUNDS = ((0.0, 0.0, 0.0), (20.0, 10.0, 5.0))
CORNERS = [(x, y, z) for x in (0.0, 20.0) for y in (0.0, 10.0) for z in (0.0, 5.0)]
NAMES = "#arm, #base, #bolt, #link, #rig"


def _bake(clip_id: str, update, leaf_boxes=None, **options) -> dict:
    return bake_clip(clip_id, cadgen.clip(update, **options), TARGETS, BOUNDS, leaf_boxes)


def _worst(track: dict, t: float, corners, expected) -> float:
    """The farthest a renderer puts any of ``corners`` at ``t`` from where ``expected(point)`` says."""
    return max(math.dist(_placed(track, t, corner), expected(corner)) for corner in corners)


def _placed(track: dict, t: float, point) -> list[float]:
    """Where a renderer puts ``point`` of a transform track's parts at ``t``:
    T(pivot + d) R(q) T(-pivot), with d and the turn read between the keys."""
    times, keys, pivot = track["times"], track["transform"], track["pivot"]
    k = min(max(bisect.bisect_right(times, t) - 1, 0), len(times) - 2)
    span = times[k + 1] - times[k]
    d, r = _pose_at(keys[k], keys[k + 1], span, (t - times[k]) / span)
    arm = [c - p for c, p in zip(point, pivot)]
    return [r[3 * i] * arm[0] + r[3 * i + 1] * arm[1] + r[3 * i + 2] * arm[2] + pivot[i] + d[i] for i in range(3)]


def _value_at(track: dict, channel: str, t: float):
    """A held channel at ``t``, lerped between two numbers, as every renderer reads it."""
    times, values = track["times"], track[channel]
    k = bisect.bisect_right(times, t) - 1
    if k < 0 or k >= len(times) - 1:
        return values[max(k, 0)]
    a, b = values[k], values[k + 1]
    if a is None or b is None:
        return a
    return a + (b - a) * (t - times[k]) / (times[k + 1] - times[k])


def _line(y: float) -> dict:
    return {"normal": [0.0, 0.0, 1.0], "segments": [{"kind": "line", "start": [0.0, 0.0, 0.0], "end": [10.0, y, 0.0]}]}


def _coil(length: float, turns: int = 3, radius: float = 2.0) -> dict:
    """A coil spring's wire centerline, ``length`` tall about +Z: quarter-turn Beziers
    rising evenly, as a valve spring is built."""
    return _coil_through([length * i / (4 * turns) for i in range(4 * turns + 1)], radius)


def _coil_through(heights: list[float], radius: float = 2.0) -> dict:
    """A coil whose quarter turns end at ``heights``: each joint's handles share one
    slope, the turn's middle difference, so the wire stays tangent-continuous however
    unevenly it rises."""
    k = 4.0 / 3.0 * math.tan(math.pi / 8.0) * radius

    def at(quarter: int, z: float) -> list[float]:
        a = math.pi / 2 * quarter
        return [radius * math.cos(a), radius * math.sin(a), z]

    def slope(i: int) -> float:
        lo, hi = max(0, i - 1), min(len(heights) - 1, i + 1)
        return (heights[hi] - heights[lo]) / (hi - lo) / 3

    def ahead(quarter: int, sign: float) -> list[float]:
        a = math.pi / 2 * quarter
        return [-sign * k * math.sin(a), sign * k * math.cos(a), sign * slope(quarter)]

    segments = []
    for i in range(len(heights) - 1):
        p0, p3 = at(i, heights[i]), at(i + 1, heights[i + 1])
        p1 = [p + v for p, v in zip(p0, ahead(i, 1.0))]
        p2 = [p + v for p, v in zip(p3, ahead(i + 1, -1.0))]
        segments.append({"kind": "bezier", "points": [p0, p1, p2, p3]})
    return {"normal": [0.0, 0.0, 1.0], "segments": segments}


class DeclaringClips(unittest.TestCase):
    """``cadgen.clip`` and ``animation=`` refuse a bad declaration before anything builds."""

    def test_a_clip_is_a_frozen_declaration(self) -> None:
        def spin(t, m):
            pass

        declared = cadgen.clip(spin, duration=2, label="  Spin  ")
        self.assertEqual(Clip(update=spin, duration=2.0, loop=True, label="Spin", fps=60.0), declared)
        with self.assertRaises(AttributeError):
            declared.duration = 3  # type: ignore[misc]

    def test_a_bad_clip_is_refused_by_name(self) -> None:
        def one(t):
            pass

        def spin(t, m):
            pass

        cases = (
            (lambda: cadgen.clip(42, duration=1), "cadgen.clip needs update(t, m) as a function, got int"),
            (lambda: cadgen.clip(one, duration=1), "cadgen.clip: one() must take (t, m)"),
            (lambda: cadgen.clip(spin, duration=0), "cadgen.clip duration must be a positive number of seconds, got 0"),
            (lambda: cadgen.clip(spin, duration=-1), "cadgen.clip duration must be a positive number of seconds, got -1"),
            (lambda: cadgen.clip(spin, duration=True), "cadgen.clip duration must be a positive number of seconds, got True"),
            (lambda: cadgen.clip(spin, duration=1, fps=0), "cadgen.clip fps must be a positive number of samples a second, got 0"),
            (lambda: cadgen.clip(spin, duration=1, fps=False), "cadgen.clip fps must be a positive number of samples a second, got False"),
            (lambda: cadgen.clip(spin, duration=1, label=""), "cadgen.clip label must be a nonempty string, got ''"),
            (lambda: cadgen.clip(spin, duration=1, label="  "), "cadgen.clip label must be a nonempty string, got '  '"),
        )
        for declare, message in cases:
            with self.subTest(message=message), self.assertRaises(ValueError) as caught:
                declare()
            self.assertEqual(message, str(caught.exception))

    def test_animation_takes_a_nonempty_dict_of_clips_and_keeps_its_order(self) -> None:
        def spin(t, m):
            pass

        where = "@step animation="
        declared = cadgen.clip(spin, duration=1)
        cases = (
            ("export const clips = {};", f"{where} must be a dict of clip id -> cadgen.clip(update, duration=...), got str"),
            ({}, f"{where} must be a dict of clip id -> cadgen.clip(update, duration=...), got an empty dict"),
            ({"spin": spin}, f"{where}['spin'] must be built by cadgen.clip(update, duration=...), got function"),
            ({"": declared}, f"{where} clip ids must be nonempty strings without surrounding spaces, got ''"),
            ({3: declared}, f"{where} clip ids must be nonempty strings without surrounding spaces, got 3"),
            # Never trimmed: " spin " beside "spin" would silently be one clip.
            ({"spin": declared, " spin ": declared},
             f"{where} clip ids must be nonempty strings without surrounding spaces, got ' spin '"),
        )
        for value, message in cases:
            with self.subTest(value=value), self.assertRaises(ValueError) as caught:
                normalize_clips(value, where=where)
            self.assertEqual(message, str(caught.exception))
        self.assertIsNone(normalize_clips(None, where=where))
        self.assertEqual(["swing", "lift"], list(normalize_clips({"swing": declared, "lift": declared}, where=where)))

    def test_the_decorator_refuses_a_bad_declaration_when_it_decorates(self) -> None:
        from cadgen import step

        def model():
            return None

        with self.assertRaises(ValueError) as caught:
            step(animation="export const clips = {};")(model)
        self.assertEqual(
            "@step animation= must be a dict of clip id -> cadgen.clip(update, duration=...), got str",
            str(caught.exception),
        )


class BakingTransforms(unittest.TestCase):
    def test_a_constant_spin_about_an_off_origin_axis_is_rebuilt_between_samples(self) -> None:
        def spin(t, m):
            m.get("#link").rotate((0, 0, 1), 90 * t, (10, 0, 0))

        (track,) = _bake("spin", spin, duration=4)["tracks"]
        self.assertEqual(["o1.2.1"], track["targets"])
        # The point whose path accelerates least is on the axis.
        self.assertAlmostEqual(10.0, track["pivot"][0], places=3)
        self.assertAlmostEqual(0.0, track["pivot"][1], places=3)
        # Between keys a quaternion follows glTF's cubic curve, close to a spin but not
        # one: a whole revolution takes a few keys more than the cap on how far two
        # kept keys may turn apart, and nowhere near one per sample.
        self.assertLessEqual(len(track["times"]), 9)
        for a, b in zip(track["transform"], track["transform"][1:]):
            dot = abs(sum(x * y for x, y in zip(a[3:7], b[3:7])))
            self.assertLessEqual(math.degrees(2 * math.acos(min(1.0, dot))), MAX_KEY_TURN_DEG + 1e-3)

        # Measured where the baker measures, at the bounding box's corners, and at
        # times no sample landed on (they are 1/60 s apart).
        tolerance = max(LENGTH_FLOOR, TRANSFORM_TOLERANCE * math.dist(*BOUNDS))
        for t in (0.01, 0.37, 1.0 + 1 / 120, 2.2222, 3.99):
            angle = math.radians(90 * t)
            c, s = math.cos(angle), math.sin(angle)
            worst = max(
                math.dist(_placed(track, t, (x, y, z)), (10 + (x - 10) * c - y * s, (x - 10) * s + y * c, z))
                for x, y, z in CORNERS
            )
            with self.subTest(t=t):
                self.assertLessEqual(worst, tolerance)

    def test_identical_motion_shares_a_track_and_untouched_parts_have_none(self) -> None:
        def carry(t, m):
            m.get("#link").translate((5 * t, 0, 0))
            m.get("#o1.3").translate((5 * t, 0, 0))  # the other bolt, the same move by another name
            m.get("#base").translate((0, 0, 3))
            m.get("#o1.2.2").rotate((0, 0, 1), 0)  # touched, never moved

        tracks = {tuple(track["targets"]): track for track in _bake("carry", carry, duration=2, fps=10)["tracks"]}
        # o1.2.2, the arm's bolt, never left its rest pose: no track names it.
        self.assertEqual({("o1.1",), ("o1.2.1", "o1.3")}, set(tracks))
        # A slide at constant speed is exact between its ends.
        self.assertEqual([0.0, 2.0], tracks[("o1.2.1", "o1.3")]["times"])
        # A constant offset is one key: d = (0, 0, 3), no turn, nothing moving.
        held = tracks[("o1.1",)]
        self.assertEqual([0.0], held["times"])
        self.assertEqual([[0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 1.0, *[0.0] * 7]], held["transform"])

    def test_the_samples_hold_each_distinct_pose_and_centerline_once(self) -> None:
        # A clip that poses each part with a fresh transform makes one per part per
        # sample, and a tube's rest is the same at every sample; a bake holds every
        # sample until its tracks are reduced, and a large assembly's parent build held
        # a gigabyte of copies (radial: 1.5 million transforms, 23,000 values).
        from unittest import mock

        from cadgen._internal import animation_bake

        leaves = [f"o1.{index}" for index in range(1, 51)]
        targets = animation_targets({"occurrences": [{"id": leaf} for leaf in leaves],
                                     "assembly": {"root": {"id": "o1", "name": "rig", "children": [
                                         {"id": leaf, "name": f"p{leaf}", "children": []} for leaf in leaves]}}})

        def rise(t, m):
            for leaf in leaves[:-2]:
                m.get(f"#{leaf}").translate((0, 0, round(t)))
            for leaf in leaves[-2:]:
                m.get(f"#{leaf}").deform_tube(rest=_line(0.0), path=_line(float(round(t))))

        sampled = []

        class Recorded(animation_bake._Frame):
            __slots__ = ()

            def __init__(self) -> None:
                super().__init__()
                sampled.append(self)

        with mock.patch.object(animation_bake, "_Frame", Recorded):
            baked = bake_clip("rise", cadgen.clip(rise, duration=2, fps=10), targets, BOUNDS)
        self.assertEqual([leaves[:-2], leaves[-2:]], [track["targets"] for track in baked["tracks"]],
                         "one track moves the parts, one bends the tubes")
        poses = [pose for frame in sampled for pose in frame.transform.values()]
        self.assertEqual((len(sampled) * (len(leaves) - 2), 3), (len(poses), len(set(poses))))
        self.assertEqual(3, len({id(pose) for pose in poses}), "one object per pose, not per part and sample")
        tubes = [spec for frame in sampled for spec in frame.tube.values()]
        self.assertEqual(1, len({id(spec["rest"]) for spec in tubes}), "the rest, once")
        self.assertEqual(3, len({id(spec["path"]) for spec in tubes}), "each path it takes, once")

    def test_parts_that_move_alike_but_for_rounding_share_a_track(self) -> None:
        # One turn reached two ways -- through 30 degrees, and through two turns of 15 --
        # is equal to the last bits, and is one track.
        def swing(t, m):
            m.get("#link").rotate((0, 0, 1), 30 * t, (10, 0, 0))
            m.get("#o1.3").rotate((0, 0, 1), 15 * t, (10, 0, 0)).rotate((0, 0, 1), 15 * t, (10, 0, 0))

        (track,) = _bake("swing", swing, duration=2, fps=10)["tracks"]
        self.assertEqual(["o1.2.1", "o1.3"], track["targets"])

    def test_a_turn_left_by_rounding_never_throws_the_pivot_off_the_model(self) -> None:
        # A solver that leaves 1e-13 degrees of turn on a part it slides 400 mm: there is
        # no axis to find. Placing one anyway put the pivot ~1e17 mm out, and the key's
        # quaternion, written as no turn at all, left that lever arm's swing in d.
        def slide(t, m):
            m.get("#link").rotate((0, 0, 1), 1e-13 * (1 + t)).translate((400 * t, 0, 0))

        (track,) = _bake("slide", slide, duration=2, fps=10)["tracks"]
        center = [(lo + hi) / 2 for lo, hi in zip(*BOUNDS)]
        self.assertLessEqual(math.dist(track["pivot"], center), math.dist(*BOUNDS))
        tolerance = max(LENGTH_FLOOR, TRANSFORM_TOLERANCE * math.dist(*BOUNDS))
        for t in (0.0, 0.55, 1.0, 1.95):
            with self.subTest(t=t):
                self.assertLessEqual(_worst(track, t, CORNERS, lambda p: (p[0] + 400 * t, p[1], p[2])), tolerance)

    def test_a_part_spinning_while_carried_is_keyed_about_its_axis(self) -> None:
        # A rotor spinning about its own axis while the axis is carried sideways: about
        # that axis its keys need only the spin and the carry, each exact between keys,
        # so only the cap on how far two kept keys may turn apart splits it.
        def run(t, m):
            m.get("#link").rotate((0, 0, 1), 90 * t, (10, 0, 0)).translate((5 * t, 3 * t, 0))

        (track,) = _bake("run", run, duration=4)["tracks"]
        self.assertAlmostEqual(10.0, track["pivot"][0], places=3)
        self.assertAlmostEqual(0.0, track["pivot"][1], places=3)
        self.assertLessEqual(len(track["times"]), 9)

    def test_a_track_is_measured_at_its_own_parts_box(self) -> None:
        # A millimetre part easing through a turn about its own center: what a renderer
        # gets wrong between keys grows with the lever arm, and the part's own corners
        # are half a millimetre out, not the whole model's ten and more.
        class Boxes:
            def get(self, leaf):
                return ((9.5, -0.5, 0.0), (10.5, 0.5, 1.0)) if leaf == "o1.2.1" else None

        def ease(t, m):
            m.get("#link").rotate((0, 0, 1), 45 * (1 - math.cos(math.pi * t)), (10, 0, 0))

        whole = _bake("ease", ease, duration=2)["tracks"][0]
        own = _bake("ease", ease, leaf_boxes=Boxes(), duration=2)["tracks"][0]
        self.assertLess(len(own["times"]), len(whole["times"]))
        tolerance = max(LENGTH_FLOOR, TRANSFORM_TOLERANCE * math.dist(*BOUNDS))
        part = [(x, y, z) for x in (9.5, 10.5) for y in (-0.5, 0.5) for z in (0.0, 1.0)]
        for t in (0.25, 0.75, 1.3, 1.9):
            angle = math.radians(45 * (1 - math.cos(math.pi * t)))
            c, s = math.cos(angle), math.sin(angle)
            with self.subTest(t=t):
                self.assertLessEqual(
                    _worst(own, t, part, lambda p: (10 + (p[0] - 10) * c - p[1] * s, (p[0] - 10) * s + p[1] * c, p[2])),
                    tolerance)

    def test_a_hold_costs_its_two_ends(self) -> None:
        # An eased lift between two holds, as a teardown moves its parts. Each hold is
        # its two ends and nothing between them; the ease takes as many LINEAR keys as
        # it needs to stay within tolerance.
        def lift(t, m):
            u = min(1.0, max(0.0, t - 1.0))
            m.get("#link").translate((0, 0, 8 * u * u * (3 - 2 * u)))

        (track,) = _bake("lift", lift, duration=4)["tracks"]
        self.assertLessEqual({0.0, 1.0, 2.0, 4.0}, set(track["times"]))
        self.assertEqual([], [t for t in track["times"] if 0 < t < 1 or 2 < t < 4])
        tolerance = max(LENGTH_FLOOR, TRANSFORM_TOLERANCE * math.dist(*BOUNDS))
        for t in (0.5, 0.99, 1.37, 1.8, 2.01, 3.5):
            u = min(1.0, max(0.0, t - 1.0))
            z = 8 * u * u * (3 - 2 * u)
            with self.subTest(t=t):
                self.assertLessEqual(_worst(track, t, CORNERS, lambda p: (p[0], p[1], p[2] + z)), tolerance)

    def test_a_turn_past_ninety_degrees_between_samples_asks_for_a_higher_fps(self) -> None:
        def whirl(t, m):
            m.get("#base").rotate((0, 0, 1), 1000 * t)

        with self.assertRaises(AnimationError) as caught:
            _bake("whirl", whirl, duration=1, fps=10)
        self.assertEqual(
            "animation clip 'whirl' part o1.1 turns 100 degrees between the samples at 0 s and 0.1 s: "
            "raise the clip's fps",
            str(caught.exception),
        )


class BakingStyles(unittest.TestCase):
    def test_opacity_lerps_and_null_hands_back_to_the_material_while_visible_holds(self) -> None:
        def fade(t, m):
            if t < 1:
                m.get("#link").opacity(1 - t)  # fades out, then the material's own again
            m.get("#base").visible(t < 1)  # shown, then hidden
            if t >= 1:
                m.get("#o1.3").visible(False)  # at rest, then hidden

        tracks = _bake("fade", fade, duration=2, fps=10)["tracks"]
        (opacity,) = [track for track in tracks if "opacity" in track]
        self.assertEqual(["o1.2.1"], opacity["targets"])
        # A ramp needs its ends, not its samples, and the keys rebuild every sample.
        self.assertLessEqual(len(opacity["times"]), 4)
        for index in range(21):
            t = index / 10
            value = _value_at(opacity, "opacity", t)
            with self.subTest(t=t):
                if t < 1:
                    self.assertAlmostEqual(1 - t, value, delta=OPACITY_TOLERANCE)
                else:
                    self.assertIsNone(value)
        # Held: a key where the value changes, and nowhere else.
        self.assertEqual(
            [
                {"targets": ["o1.1"], "times": [0.0, 1.0], "visible": [True, False]},
                {"targets": ["o1.3"], "times": [0.0, 1.0], "visible": [None, False]},
            ],
            [track for track in tracks if "visible" in track],
        )

    def test_a_tube_is_keyed_so_its_skin_follows_the_clip(self) -> None:
        # A tube that swings and twists at once: no single slerp is both, so the bake
        # keys it until the skin's joints, interpolated as glTF does, stay on the clip's
        # own centerline at every sample.
        from cadgen._internal import tube_skin

        braid = {"pitch": 2.0, "depth": 0.1, "strands": 8}

        def bend(t, m):
            m.get("#link").deform_tube(
                rest=_line(0), path=_line(4 * t), twist_deg=90 * t, max_segment_length=0.5, braid=braid
            )

        (track,) = _bake("bend", bend, duration=1, fps=10)["tracks"]
        self.assertEqual((["o1.2.1"], _line(0), 0.5, braid),
                         (track["targets"], track["rest"], track["maxSegmentLength"], track["braid"]))
        self.assertEqual(([0.0, 1.0], {"path": _line(0), "twistDeg": 0.0}, {"path": _line(4), "twistDeg": 90.0}),
                         ([track["times"][0], track["times"][-1]], track["tube"][0], track["tube"][-1]))
        rest = tube_skin.compile_rest(track["rest"])
        fractions = tube_skin.joint_fractions(rest, 0.5)
        keys = [tube_skin.key_joints(key, track["rest"], rest, fractions) for key in track["tube"]]
        tolerance = max(LENGTH_FLOOR, TRANSFORM_TOLERANCE * math.dist(*BOUNDS))
        for step in range(11):
            t = step / 10
            k = min(bisect.bisect_right(track["times"], t) - 1, len(keys) - 2)
            u = (t - track["times"][k]) / (track["times"][k + 1] - track["times"][k])
            truth = tube_skin.key_joints({"path": _line(4 * t), "twistDeg": 90 * t}, track["rest"], rest, fractions)
            moved, turned = tube_skin.joint_error(tube_skin.between(keys[k], keys[k + 1], u), truth)
            with self.subTest(t=t):
                self.assertLessEqual(moved, tolerance)
                self.assertLessEqual(turned, TUBE_TURN_TOLERANCE_DEG + 1e-9)

        def release(t, m):
            if t < 0.5:
                m.get("#link").deform_tube(rest=_line(0), path=_line(4 * t))

        (released,) = _bake("release", release, duration=1, fps=10)["tracks"]
        self.assertEqual(0.5, released["times"][released["tube"].index(None)])
        self.assertIsNone(released["tube"][-1])

        def creep(t, m):
            m.get("#link").deform_tube(rest=_line(t), path=_line(t))

        with self.assertRaises(AnimationError) as caught:
            _bake("creep", creep, duration=1, fps=10)
        self.assertEqual(
            "animation clip 'creep' part o1.2.1: a tube's rest path, max_segment_length and braid "
            "must stay the same through a clip; only its path and twist move",
            str(caught.exception),
        )

    def test_a_tube_that_holds_still_is_keyed_at_the_ends_of_its_hold(self) -> None:
        # A valve spring closed for half a second, then eased shut as a cam lifts it. Its
        # first moves are within tolerance of the rest, so a key in them could stand for
        # the whole hold, and every frame of the hold would bend the spring anew; the
        # hold's two ends are one value instead, and a renderer redraws nothing through it.
        def press(t, m):
            lift = 3.0 * max(0.0, (t - 0.5) / 0.5) ** 3
            m.get("#link").deform_tube(rest=_coil(10.0), path=_coil(10.0 - lift))

        (track,) = _bake("press", press, duration=1)["tracks"]
        self.assertEqual([0.0, 0.5], track["times"][:2])
        self.assertEqual(track["tube"][0], track["tube"][1])

    def test_a_spring_that_compresses_is_keyed_as_maps_of_its_rest(self) -> None:
        # Every turn of a compressing coil closes up alike, so each pose is the rest under
        # one affine map: a key is that map's twelve numbers, not the coil again.
        def press(t, m):
            m.get("#link").deform_tube(rest=_coil(10.0), path=_coil(10.0 - 4.0 * math.sin(math.pi * t)))

        (track,) = _bake("press", press, duration=1, fps=30)["tracks"]
        self.assertGreater(len(track["times"]), 2)
        self.assertTrue(all(set(key["path"]) == {"normal", "map"} for key in track["tube"]))
        tolerance = max(LENGTH_FLOOR, TRANSFORM_TOLERANCE * math.dist(*BOUNDS))
        for sample in (4, 15, 23):  # samples the keys drop: rebuilt from two maps
            t = sample / 30
            k = bisect.bisect_right(track["times"], t) - 1
            u = (t - track["times"][k]) / (track["times"][k + 1] - track["times"][k])
            a, b = (key_path(track["rest"], track["tube"][n]["path"]) for n in (k, k + 1))
            drawn, truth = _path_points(_lerp_path(a, b, u)), _path_points(_coil(10.0 - 4.0 * math.sin(math.pi * t)))
            with self.subTest(t=t):
                self.assertLessEqual(max(math.dist(p, q) for p, q in zip(drawn, truth)), tolerance)

        # Turns closing up faster the higher they sit are no one map: past the rest pose,
        # those keys carry their own segments.
        def settle(t, m):
            heights = [10.0 * i / 12 for i in range(13)]
            m.get("#link").deform_tube(rest=_coil(10.0), path=_coil_through([z - 0.02 * t * z * z for z in heights]))

        (settled,) = _bake("settle", settle, duration=1, fps=10)["tracks"]
        self.assertEqual({"normal", "map"}, set(settled["tube"][0]["path"]))
        self.assertTrue(all(set(key["path"]) == {"normal", "segments"} for key in settled["tube"][1:]))

    def test_a_tube_path_no_renderer_could_draw_fails_with_its_time(self) -> None:
        # Squashing a coil's control points by height breaks it at every joint: the
        # handles either side stop lining up. The bake compiles every key it keeps, as
        # each renderer will, so the clip fails here, saying where and when.
        def kink(t, m):
            path = copy.deepcopy(_coil(10.0))
            for segment in path["segments"]:
                for point in segment["points"]:
                    point[2] -= 0.02 * t * point[2] ** 2
            m.get("#link").deform_tube(rest=_coil(10.0), path=path)

        with self.assertRaises(AnimationError) as caught:
            _bake("kink", kink, duration=1, fps=10)
        self.assertRegex(str(caught.exception),
                         r"^animation clip 'kink' part o1\.2\.1 at t=[0-9.]+ s: tube deformation: path is not "
                         r"tangent-continuous before segment 1$")
        # The same broken path held still for the whole clip has no changing interval to
        # be compiled in, and fails all the same.
        with self.assertRaises(AnimationError) as caught:
            _bake("held", lambda t, m: kink(1.0, m), duration=1, fps=10)
        self.assertRegex(str(caught.exception),
                         r"^animation clip 'held' part o1\.2\.1 at t=0 s: tube deformation: path is not "
                         r"tangent-continuous before segment 1$")


class ResolvingTargets(unittest.TestCase):
    def test_a_name_an_id_and_a_group_each_resolve_to_leaves(self) -> None:
        self.assertEqual(("o1.2.1", "o1.2.2"), TARGETS.resolve("#arm"))  # a group: its leaves
        self.assertEqual(("o1.2.2", "o1.3"), TARGETS.resolve("#bolt"))  # every part of that name
        self.assertEqual(("o1.2.1", "o1.2.2"), TARGETS.resolve("#o1.2"))  # an id and what is beneath it
        self.assertEqual(("o1.3",), TARGETS.resolve("#o1.3"))
        self.assertEqual(["arm", "base", "bolt", "link", "rig"], TARGETS.labels())

        def wave(t, m):
            m.get("#arm", "#bolt", "#o1.2.1").translate((0, t, 0))

        (track,) = _bake("wave", wave, duration=1, fps=10)["tracks"]
        self.assertEqual(["o1.2.1", "o1.2.2", "o1.3"], track["targets"])

    def test_a_target_that_names_nothing_fails_with_the_names_there_are(self) -> None:
        cases = {
            lambda t, m: m.get("#wheel"): f"animation target '#wheel' names no part or group; names: {NAMES}",
            lambda t, m: m.get("link"): "animation target 'link' must be a #name or an #o1.2 occurrence id",
            lambda t, m: m.get(): "m.get needs at least one #name or #occurrence id",
            lambda t, m: 1 / 0: "ZeroDivisionError: division by zero",
        }
        for update, message in cases.items():
            with self.subTest(message=message), self.assertRaises(AnimationError) as caught:
                _bake("wave", update, duration=1)
            self.assertEqual(f"animation clip 'wave' at t=0 s: {message}", str(caught.exception))
            self.assertIsInstance(caught.exception, ValueError)


class TheBakedSection(unittest.TestCase):
    """What a sidecar's ``animation`` section must be for a renderer to read it."""

    def _section(self) -> dict:
        def spin(t, m):
            m.get("#link").rotate((0, 0, 1), 45 * t, (10, 0, 0))

        def fade(t, m):
            m.get("#base").opacity(1 - t / 2)

        return bake_animation(
            {"spin": cadgen.clip(spin, duration=2, fps=10), "fade": cadgen.clip(fade, duration=2, fps=10)},
            TARGETS, BOUNDS,
        )

    def test_a_baked_section_reads_back_as_itself_in_its_declared_order(self) -> None:
        section = self._section()
        self.assertEqual(["spin", "fade"], [clip["id"] for clip in section["clips"]])
        self.assertEqual(section, normalize_baked_animation(json.loads(json.dumps(section))))
        self.assertIsNone(normalize_baked_animation({"clips": []}))
        self.assertIsNone(normalize_baked_animation(None))

    def test_any_duration_reads_back_and_ends_on_its_last_key(self) -> None:
        # Key times are written to a millionth of a second: a duration that is not a whole
        # number of them (2/3 s, pi s) is written the same way, so its last key is its end,
        # and samples a millionth apart at an absurd fps are taken once.
        def spin(t, m):
            m.get("#link").rotate((0, 0, 1), 20 * t, (10, 0, 0))

        for duration, fps in ((2 / 3, 30), (math.pi, 30), (1 / 60, 30), (2e-6, 3e6)):
            with self.subTest(duration=duration, fps=fps):
                section = bake_animation({"c": cadgen.clip(spin, duration=duration, fps=fps)}, TARGETS, BOUNDS)
                self.assertEqual(section, normalize_baked_animation(json.loads(json.dumps(section))))
                (clip,) = section["clips"]
                self.assertEqual(clip["duration"], clip["tracks"][0]["times"][-1])
        with self.assertRaisesRegex(AnimationError, r"^animation clip 'c': its duration 1e-07 s is shorter than "
                                                    r"the 1e-06 s a key's time is written to; make it longer$"):
            bake_animation({"c": cadgen.clip(spin, duration=1e-7)}, TARGETS, BOUNDS)

    def test_a_malformed_section_is_refused_with_what_is_wrong(self) -> None:
        cases = (
            (lambda s: s.update(clips={c["id"]: c for c in s["clips"]}), "the section must be {'clips': [...]}"),
            (lambda s: s["clips"][0].pop("id"), "clip 0 must have exactly id, label, duration, loop and tracks"),
            (lambda s: s["clips"][1].update(id="spin"), "clip 1 needs an id of its own, got 'spin'"),
            (lambda s: s["clips"][0].update(duration=0), "clip 'spin' needs a label, a positive duration and a boolean loop"),
            (
                lambda s: s["clips"][0]["tracks"][0].update(opacity=[1.0, 1.0]),
                "clip 'spin' track 0 must carry targets, times and exactly one of transform, opacity, visible, tube",
            ),
            (
                lambda s: s["clips"][0]["tracks"][0]["times"].reverse(),
                "clip 'spin' track 0 times must rise strictly from 0 to at most the duration",
            ),
            (lambda s: s["clips"][0]["tracks"][0].pop("pivot"), "clip 'spin' track 0 needs its pivot, three numbers"),
            (lambda s: s["clips"][0]["tracks"][0]["transform"][0].pop(), "clip 'spin' track 0 has a malformed transform value"),
            (
                lambda s: s["clips"][1]["tracks"][0]["opacity"].__setitem__(0, 1.5),
                "clip 'fade' track 0 has a malformed opacity value: 1.5",
            ),
        )
        baked = self._section()
        for damage, message in cases:
            section = copy.deepcopy(baked)
            damage(section)
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, "^" + re.escape(f"animation: {message}")):
                normalize_baked_animation(section)

    def test_a_tube_map_reads_back_only_as_twelve_numbers_over_a_rest_without_arcs(self) -> None:
        def press(t, m):
            m.get("#link").deform_tube(rest=_coil(10.0), path=_coil(10.0 - 4.0 * t))

        baked = bake_animation({"press": cadgen.clip(press, duration=1, fps=10)}, TARGETS, BOUNDS)
        self.assertEqual(baked, normalize_baked_animation(json.loads(json.dumps(baked))))
        arc = {"kind": "arc", "center": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, 1.0], "start": [2.0, 0.0, 0.0], "sweepDeg": 90.0}
        for damage in (
            lambda track: track["tube"][0]["path"]["map"].pop(),
            lambda track: track["tube"][0]["path"]["map"].__setitem__(0, "1"),
            lambda track: track["tube"][0]["path"].update(segments=[]),
            lambda track: track["rest"]["segments"].append(arc),
        ):
            section = copy.deepcopy(baked)
            damage(section["clips"][0]["tracks"][0])
            with self.subTest(damage=damage), self.assertRaisesRegex(ValueError, "^animation: clip 'press' track 0 has a malformed tube value"):
                normalize_baked_animation(section)


MODEL = '''
import cadgen
from cadgen import label_shape, step
from cadgen import build123d as bd


def swing(t, m):
    m.get("#arm").rotate((0, 0, 1), 45 * t, (10, 0, 6))


def lift(t, m):
    m.get("#base").translate((0, 0, 2 * t))


@step(animation={
    "swing": cadgen.clip(swing, duration=2, label="Swing"),
    "lift": cadgen.clip(lift, duration=1, loop=False),
})
def hinge():
    base = label_shape(bd.Box(20, 20, 4), "base")
    arm = label_shape(bd.Pos(10, 0, 6) * bd.Box(16, 4, 4), "arm")
    return bd.Compound(children=[base, arm])


if __name__ == "__main__":
    hinge()
'''


class AModelBuildBakesItsClips(unittest.TestCase):
    """The build half: a real model, its written document, its sidecar and its record."""

    def setUp(self) -> None:
        self._roots = IsolatedCadRoots(self, prefix="cadanim-")
        self._tempdir = self._roots.temporary_cad_directory(prefix="tmp-cadanim-")
        self.addCleanup(self._tempdir.cleanup)
        self.script = Path(self._tempdir.name) / "hinge.py"
        self.document = self.script.with_suffix(".step")

    def _build(self) -> str:
        from cadgen.catalog import StepImportOptions
        from cadgen.generation import generate_step_targets

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, generate_step_targets([str(self.script)], step_options=StepImportOptions(), json_output=True))
        (line,) = out.getvalue().splitlines()
        return json.loads(line)["outcome"]

    def _record(self) -> dict:
        from cadgen.store.index import model_ref
        from cadgen.store.records import read_record

        return read_record(model_ref(self.script, "hinge")) or {}

    def test_the_clips_bake_against_the_written_document_and_rebake_only_when_edited(self) -> None:
        from cadgen._internal.source_sidecar import (
            SOURCE_SIDECAR_SCHEMA_VERSION,
            read_source_sidecar,
            source_sidecar_path,
        )
        from cadgen.catalog import result_descriptor_for

        self.script.write_text(MODEL, encoding="utf-8")
        self.assertEqual("built", self._build())
        sidecar = read_source_sidecar(self.document)
        self.assertEqual(SOURCE_SIDECAR_SCHEMA_VERSION, sidecar["schemaVersion"])
        clips = sidecar["animation"]["clips"]
        # Declared swing first: the order survives into the written file, whose
        # keys are sorted -- the first clip is the one a viewer opens on.
        self.assertEqual(["swing", "lift"], [clip["id"] for clip in clips])
        self.assertEqual(("Swing", 2.0, True), (clips[0]["label"], clips[0]["duration"], clips[0]["loop"]))
        self.assertEqual(("lift", 1.0, False), (clips[1]["label"], clips[1]["duration"], clips[1]["loop"]))
        ids = {row["name"]: row["id"] for row in result_descriptor_for(self.document)["occurrences"]}
        (swing,) = clips[0]["tracks"]
        (lift,) = clips[1]["tracks"]
        self.assertEqual(([ids["arm"]], [ids["base"]]), (swing["targets"], lift["targets"]))
        self.assertEqual([10.0, 0.0], swing["pivot"][:2], "the hinge's axis is where the arm moves least")
        # The record keeps the keyframes, which is what an annotation refresh rewrites
        # the sidecar from without running the model.
        self.assertEqual(sidecar["animation"], self._record()["animation"])

        before = source_sidecar_path(self.document).read_bytes()
        self.assertEqual("current", self._build())
        self.assertEqual(before, source_sidecar_path(self.document).read_bytes())

        # An edited clip is an edited model: it rebakes, and the geometry it writes is the same.
        step_bytes = self.document.read_bytes()
        self.script.write_text(MODEL.replace("45 * t", "30 * t"), encoding="utf-8")
        self.assertEqual("built", self._build())
        rebaked = read_source_sidecar(self.document)["animation"]
        last = rebaked["clips"][0]["tracks"][0]["transform"][-1]
        self.assertAlmostEqual(60.0, math.degrees(2 * math.acos(min(1.0, abs(last[6])))), places=4)
        self.assertEqual(rebaked, self._record()["animation"])
        self.assertEqual(step_bytes, self.document.read_bytes())

        # Without animation= there is nothing left for a sidecar to carry.
        start = MODEL.index("@step(animation=")
        self.script.write_text(MODEL[:start] + "@step\n" + MODEL[MODEL.index("def hinge"):], encoding="utf-8")
        self.assertEqual("built", self._build())
        self.assertFalse(source_sidecar_path(self.document).exists())
        self.assertIsNone(self._record().get("animation"))


if __name__ == "__main__":
    unittest.main()
