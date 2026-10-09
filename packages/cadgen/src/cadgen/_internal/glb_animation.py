"""A baked clip as glTF animation: the animated GLB export's half of choreography.

The bake (``animation_bake``) writes a clip's keys as glTF's own, so this works
nothing out: each track goes into the file as it stands, on its own key times,
and a glTF player draws what every CAD view draws from the same keys. What maps,
and how:

  transform  a PIVOT: a node at ``pivot + d`` turned by ``q`` -- the keys and their
             rates, CUBICSPLINE -- over a child at ``-pivot`` that carries the
             track's parts, exactly as the bake measured them.
  opacity    glTF has no animated channel for it. Refused unless the request
             drops it, and then baked STATIC at ``start`` as a material alpha.
  visible    the same: refused, or dropped by leaving out what is hidden at start.
  tube       a SKIN (``tube_skin``): joints along the centerline, whose translations
             and rotations are the keys' joints, LINEAR, and the tube's own mesh,
             refined and bound to them. A braided finish is a shader, so the file
             carries the cord's shape and motion and a smooth surface.

``start`` and ``seconds`` cut every track to one window: the keys inside it, and
one at each end -- the key there, as written, when the end falls on one, else what
the track's interpolation puts there; a looping clip repeats its keys to fill the
window. Times are re-based to zero, so the file opens on its
window's first moment, and each node's own transform is its pose there.

Pure: no filesystem, no kernel. A clip's tracks name document occurrence ids, the
same ids the export's per-occurrence nodes carry. Geometry is glTF's Y-up metres;
a document is Z-up millimetres, so every position goes (x, y, z) -> (x, z, -y) *
1e-3 and every quaternion (x, y, z, w) -> (x, z, -y, w), the same change of basis.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from cadgen._internal import tube_skin
from cadgen._internal.mesh_animation import DROPPABLE_EFFECTS, MAX_LOOP_REPEATS

CAD_TO_GLB_SCALE = 0.001
# Two keys of one track closer than this are one moment: the window's edge falling
# on a key keeps the key.
TIME_EPSILON = 1e-6


def _seconds(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{text or '0'}s"


def _summarize(ids, limit: int = 6) -> str:
    ordered = sorted(ids)
    shown = ", ".join(ordered[:limit])
    return shown if len(ordered) <= limit else f"{shown} and {len(ordered) - limit} more"


def gltf_point(p: Sequence[float]) -> list[float]:
    """A document point in glTF space."""
    return [CAD_TO_GLB_SCALE * p[0], CAD_TO_GLB_SCALE * p[2], -CAD_TO_GLB_SCALE * p[1]]


def gltf_quaternion(q: Sequence[float]) -> list[float]:
    """A document rotation in glTF space: B q B^-1 for the proper rotation B."""
    return [q[0], q[2], -q[1], q[3]]


@dataclass(frozen=True)
class Window:
    """The span of a clip a request exports."""

    start: float
    seconds: float
    duration: float
    loop: bool
    warnings: tuple[str, ...] = ()


def resolve_window(request: Mapping[str, Any], clip: Mapping[str, Any]) -> Window:
    """``seconds`` defaults to the span the clip still HAS from ``start`` (a whole
    cycle for a looping clip)."""
    start = float(request.get("start") or 0.0)
    duration = max(float(clip.get("duration") or 0.0), 0.001)
    if start >= duration:
        raise ValueError(
            f"animation start {_seconds(start)} is at or past the end of a {_seconds(duration)} clip: "
            "the file would hold one pose"
        )
    looping = clip.get("loop") is not False
    raw_seconds = request.get("seconds")
    seconds = (duration if looping else duration - start) if raw_seconds is None else float(raw_seconds)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError(f"animation seconds must be a positive number, got {raw_seconds!r}")
    if looping and (start + seconds) / duration > MAX_LOOP_REPEATS:
        raise ValueError(
            f"animation {_seconds(seconds)} from {_seconds(start)} repeats a {_seconds(duration)} clip "
            f"past {MAX_LOOP_REPEATS} times"
        )
    warnings = []
    if not looping and (start + seconds) - duration > 1e-9:
        warnings.append(
            f"animation covers {_seconds(start)}..{_seconds(start + seconds)} of a {_seconds(duration)} "
            "clip that does not loop: past its end the file holds its final pose"
        )
    return Window(start, seconds, duration, looping, tuple(warnings))


def windowed(times: Sequence[float], values: Sequence[Any], window: Window,
             mix: Callable[[Any, Any, float, float], Any]) -> tuple[list[float], list[Any]]:
    """A track's keys over ``window``, re-based to zero: a looping clip's keys
    repeated, the keys inside the window, and one at each edge -- the key there as
    written, or what ``mix`` (the track's interpolation, given two keys, the fraction
    between them and their span in seconds) puts between two."""
    duration, loop = window.duration, window.loop
    first, last = window.start, window.start + window.seconds

    def at(local: float) -> Any:
        k = bisect.bisect_right(times, local) - 1
        # A moment on a key is that key as written, its tangents too: drawn through
        # ``mix``, a transform key's rate would lose the part the sidecar's curve uses.
        for near in (k, k + 1):
            if 0 <= near < len(times) and abs(times[near] - local) <= TIME_EPSILON:
                return values[near]
        if k < 0:
            return values[0]
        if k >= len(times) - 1:
            return values[-1]
        span = times[k + 1] - times[k]
        return mix(values[k], values[k + 1], (local - times[k]) / span, span)

    moments: list[tuple[float, Any]] = []
    # A track keyed to its clip's end meets the next cycle's first key there; one that
    # stops short holds its last value up to the seam, where the next cycle begins.
    seamless = times[-1] >= duration - TIME_EPSILON
    cycle = 0
    while True:
        offset = cycle * duration if loop else 0.0
        if loop and cycle and not seamless and first + TIME_EPSILON < offset - TIME_EPSILON < last - TIME_EPSILON:
            moments.append((offset - TIME_EPSILON, values[-1]))
        for t, value in zip(times, values):
            moment = offset + t
            if loop and cycle and seamless and t <= TIME_EPSILON:
                continue  # one cycle's end is the next one's start
            if first + TIME_EPSILON < moment < last - TIME_EPSILON:
                moments.append((moment, value))
        if not loop or offset + duration >= last:
            break
        cycle += 1

    def edge(moment: float) -> Any:
        if not loop:
            return at(min(moment, duration))
        cycles, local = divmod(moment, duration)
        # The very end of a cycle is its last pose, not the next cycle's first.
        if local <= TIME_EPSILON and cycles > 0:
            return at(duration)
        return at(local)

    out_times = [0.0, *(moment - first for moment, _ in moments), window.seconds]
    out_values = [edge(first), *(value for _, value in moments), edge(last)]
    return out_times, out_values


def _transform_mix(a: Sequence[float], b: Sequence[float], u: float, span: float) -> list[float]:
    """A transform key a fraction ``u`` of the way between two, as glTF's CUBICSPLINE
    sampler draws it: the value, and its rate there (the quaternion's, of the
    normalized curve)."""
    u2, u3 = u * u, u * u * u
    h = (2 * u3 - 3 * u2 + 1, span * (u3 - 2 * u2 + u), 3 * u2 - 2 * u3, span * (u3 - u2))
    dh = ((6 * u2 - 6 * u) / span, 3 * u2 - 4 * u + 1, (6 * u - 6 * u2) / span, 3 * u2 - 2 * u)
    value = [h[0] * a[n] + h[1] * a[7 + n] + h[2] * b[n] + h[3] * b[7 + n] for n in range(7)]
    rate = [dh[0] * a[n] + dh[1] * a[7 + n] + dh[2] * b[n] + dh[3] * b[7 + n] for n in range(7)]
    q, dq = np.asarray(value[3:]), np.asarray(rate[3:])
    size = float(np.linalg.norm(q))
    unit = q / size
    turn = (dq - unit * float(unit @ dq)) / size
    return [*value[:3], *unit.tolist(), *rate[:3], *turn.tolist()]


@dataclass
class Pivot:
    """One transform track: a node at pivot + d turned by q, over a child at -pivot
    that holds the track's parts, played by CUBICSPLINE samplers. Each list is
    glTF-space, one row per time, flattened: the values, and the rates going in to
    and out of each key (equal but either side of a hold, where they are zero)."""

    members: tuple[str, ...]
    times: list
    translations: list
    rotations: list
    child_translation: list
    translations_in: list = field(default_factory=list)
    translations_out: list = field(default_factory=list)
    rotations_in: list = field(default_factory=list)
    rotations_out: list = field(default_factory=list)

    @property
    def rest_translation(self) -> list:
        return self.translations[:3]

    @property
    def rest_rotation(self) -> list:
        return self.rotations[:4]


@dataclass
class Skin:
    """One tube track as a glTF skin: its joints' poses over the window (glTF space,
    (times, joints, 3) and (times, joints, 4)), each joint's inverse bind, and what
    binds a mesh to it (``rest_path``, ``spacing``, ``fractions``, ``rest``: the
    document-space rest joints). ``parent`` is the pivot that also moves the tube's
    parts, if one does."""

    members: tuple[str, ...]
    rest_path: dict
    spacing: float
    fractions: np.ndarray
    rest: tube_skin.Joints
    times: list
    translations: np.ndarray
    rotations: np.ndarray
    inverse_binds: np.ndarray  # (joints, 16), column-major
    braid: bool
    parent: int | None = None


@dataclass
class GltfClip:
    """A clip over one window, in glTF's terms."""

    name: str
    seconds: float
    pivots: list = field(default_factory=list)
    skins: list = field(default_factory=list)
    opacity: dict = field(default_factory=dict)  # occurrence -> its opacity at start (dropped)
    hidden: set = field(default_factory=set)  # occurrences hidden at start (dropped)
    warnings: list = field(default_factory=list)


def find_clip(animation: Mapping[str, Any], clip_id: str) -> Mapping[str, Any]:
    """The clip ``clip_id`` names in a sidecar ``animation`` section."""
    clips = list((animation or {}).get("clips") or [])
    for clip in clips:
        if clip.get("id") == clip_id:
            return clip
    declared = [str(clip.get("id")) for clip in clips]
    raise ValueError(
        f"Unknown animation clip: {clip_id}. This model declares: {', '.join(declared)}" if declared
        else f"Unknown animation clip: {clip_id}. This model declares no animation clips"
    )


def _skin(track: Mapping[str, Any], window: Window) -> Skin:
    rest_path = track["rest"]
    rest = tube_skin.compile_rest(rest_path)
    spacing = float(track["maxSegmentLength"])
    fractions = tube_skin.joint_fractions(rest, spacing)
    keys = tube_skin.continuous([tube_skin.key_joints(key, rest_path, rest, fractions) for key in track["tube"]])
    times, poses = windowed(track["times"], keys, window, lambda a, b, u, _span: tube_skin.between(a, b, u))
    poses = tube_skin.continuous(poses)
    count = len(fractions)
    translations = np.stack([pose.translations for pose in poses])  # (k, n, 3) document
    rotations = np.stack([pose.rotations for pose in poses])  # (k, n, 4) document
    translations = np.stack([translations[..., 0], translations[..., 2], -translations[..., 1]], axis=-1)
    translations *= CAD_TO_GLB_SCALE
    rotations = np.stack([rotations[..., 0], rotations[..., 2], -rotations[..., 1], rotations[..., 3]], axis=-1)
    rest_joints = tube_skin.joints_on(rest, fractions)
    rest_gltf = tube_skin.Joints(
        np.stack([rest_joints.translations[:, 0], rest_joints.translations[:, 2], -rest_joints.translations[:, 1]],
                 axis=1) * CAD_TO_GLB_SCALE,
        np.stack([rest_joints.rotations[:, 0], rest_joints.rotations[:, 2], -rest_joints.rotations[:, 1],
                  rest_joints.rotations[:, 3]], axis=1),
    )
    return Skin(
        members=tuple(track["targets"]), rest_path=dict(rest_path), spacing=spacing, fractions=fractions,
        rest=rest_joints, times=times, translations=translations, rotations=rotations,
        inverse_binds=tube_skin.inverse_binds(rest_gltf).reshape(count, 16), braid=bool(track.get("braid")),
    )


def _pivot(members: tuple[str, ...], times: list, keys: list, pivot: Sequence[float]) -> Pivot:
    """A transform track's windowed keys as a glTF pivot."""
    translations, rotations, rates, turns = [], [], [], []
    previous = None
    for key in keys:
        q, dq = gltf_quaternion(key[3:7]), gltf_quaternion(key[10:14])
        if previous is not None and sum(p * c for p, c in zip(previous, q)) < 0:
            q, dq = [-c for c in q], [-c for c in dq]  # the side of the key before
        previous = q
        translations.append(gltf_point([pivot[n] + key[n] for n in range(3)]))
        rotations.append(q)
        rates.append([CAD_TO_GLB_SCALE * key[7], CAD_TO_GLB_SCALE * key[9], -CAD_TO_GLB_SCALE * key[8]])
        turns.append(dq)
    rates_in, rates_out = [list(rate) for rate in rates], [list(rate) for rate in rates]
    turns_in, turns_out = [list(turn) for turn in turns], [list(turn) for turn in turns]
    for k in range(len(keys) - 1):
        # A hold -- one pose two keys running, as a window's seam can add -- stays still.
        if translations[k] == translations[k + 1] and rotations[k] == rotations[k + 1]:
            rates_out[k] = rates_in[k + 1] = [0.0] * 3
            turns_out[k] = turns_in[k + 1] = [0.0] * 4
    flat = lambda rows: [c for row in rows for c in row]  # noqa: E731
    return Pivot(members, times, flat(translations), flat(rotations), gltf_point([-c for c in pivot]),
                 flat(rates_in), flat(rates_out), flat(turns_in), flat(turns_out))


def clip_to_gltf(clip: Mapping[str, Any], window: Window, *, drop: Sequence[str] = ()) -> GltfClip:
    """One clip over one window, as glTF pivots and skins. An effect glTF cannot
    animate is refused by name unless ``drop`` names it."""
    clip_id = str(clip.get("id"))
    dropped = {str(name).strip() for name in drop}
    unknown = sorted(dropped - set(DROPPABLE_EFFECTS))
    if unknown:
        raise ValueError(
            f"animation drop names {', '.join(unknown)}, which is not an effect this export can bake "
            f"static; droppable effects: {', '.join(DROPPABLE_EFFECTS)}"
        )
    out = GltfClip(name=clip_id, seconds=window.seconds, warnings=list(window.warnings))
    effects: dict[str, set] = {"opacity": set(), "visible": set()}
    for track in clip.get("tracks") or []:
        if "transform" in track:
            times, keys = windowed(track["times"], track["transform"], window, _transform_mix)
            pivot = track["pivot"]
            out.pivots.append(_pivot(tuple(track["targets"]), times, keys, pivot))
        elif "tube" in track:
            out.skins.append(_skin(track, window))
        else:
            effect = "opacity" if "opacity" in track else "visible"
            effects[effect].update(track["targets"])
            if effect in dropped:
                if effect == "opacity":
                    _, values = windowed(track["times"], track["opacity"], window,
                                         lambda a, b, u, _span: a if a is None or b is None else a + (b - a) * u)
                    if values[0] is not None:
                        for target in track["targets"]:
                            out.opacity[target] = float(values[0])
                else:
                    _, values = windowed(track["times"], track["visible"], window, lambda a, b, u, _span: a)
                    if values[0] is False:
                        out.hidden.update(track["targets"])
    for effect, ids in effects.items():
        if not ids:
            continue
        if effect not in dropped:
            raise ValueError(
                f"clip {clip_id} animates .{effect}() on {_summarize(ids)}, and glTF has no standard "
                f'animated channel for it. Pass drop: ["{effect}"] to bake the value at start into the '
                "file instead, or animate the occurrence's transform rather than its appearance"
            )
        out.warnings.append(
            f".{effect}() is not an animated glTF channel: {_summarize(ids)} carries its value at "
            "start, frozen for the whole clip"
        )
    braided = sorted({member for skin in out.skins if skin.braid for member in skin.members})
    if braided:
        out.warnings.append(
            f"{_summarize(braided)} carries a braid: the strand pattern is a shader, not geometry, "
            "so the exported cord has the right shape and motion and a smooth surface"
        )
    moved = {member: index for index, pivot in enumerate(out.pivots) for member in pivot.members}
    for skin in out.skins:
        parents = {moved.get(member) for member in skin.members}
        if len(parents) > 1:
            raise ValueError(
                f"clip {clip_id} bends {_summarize(skin.members)} as one tube while moving them apart: a "
                "glTF skin's joints move as one"
            )
        skin.parent = parents.pop()
    hidden_and_moving = sorted(member for member in out.hidden if member in moved)
    if hidden_and_moving:
        out.warnings.append(
            f"{_summarize(hidden_and_moving)} moves in this clip and is hidden at start: dropping "
            ".visible() omits the occurrence from the file, and a node that is not there carries no motion"
        )
    return out


def restrict_to_nodes(clip: GltfClip, nodes: set[str]) -> GltfClip:
    """The clip narrowed to the nodes the file holds. An occurrence whose component
    produced no triangles is in the document and not in the file: it goes from the
    pivots that carried it, by name, and a pivot left carrying nothing goes too."""
    missing = sorted({member for pivot in clip.pivots for member in pivot.members if member not in nodes})
    if not missing:
        return clip
    pivots = []
    for pivot in clip.pivots:
        members = tuple(member for member in pivot.members if member in nodes)
        if members:
            pivot.members = members
            pivots.append(pivot)
    kept = {id(pivot): index for index, pivot in enumerate(pivots)}
    for skin in clip.skins:
        if skin.parent is not None:
            skin.parent = kept.get(id(clip.pivots[skin.parent]))
    clip.pivots = pivots
    clip.warnings.append(f"{_summarize(missing)} moves in this clip but has no geometry in the "
                         "export, so the file carries no node to animate for it")
    return clip
