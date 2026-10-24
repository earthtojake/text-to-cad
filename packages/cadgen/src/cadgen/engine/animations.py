"""Animations: a GLB's own choreography, in glTF's terms, baked when a declared GLB is written.

A **configuration sequence** (``mechanism.configuration_sequence``; a motion, as the structure and
the viewer say) is the mechanism's: pair values over time, AP242's interpolated configuration
sequence, kept in the document. An **animation** is the GLB's: glTF
channels on the nodes a GLB places. The harvest keeps it on the build's tree (``harvest``) and the
GLB writer bakes it (``export/animation.py``). The xbf carries the compiled tracks as a build record
on its main label beside the closure (``record``, ``document.ANIMATIONS_GUID``), which only a GLB
of the document reads: a GLB exported later from the xbf is the build's own, and every other
reader (``read_xbf``, the viewer, STEP) ignores it.

``animation(assembly, name, duration=...)`` returns a builder. Its one primitive is glTF's own:
``.channel(parts, path=, keys=[(t, value), ...], interpolation=)``, ``path`` one of
``translation``, ``rotation`` and ``scale`` and ``interpolation`` one of ``CUBICSPLINE`` (the
default), ``LINEAR`` and ``STEP``, as a glTF sampler spells them. ``.translation``, ``.rotation``
and ``.scale`` are channels from a start to an end, and ``.explode``, ``.stagger``, ``.hide`` and
``.pose`` helpers that compile to channels; every call returns the builder::

    show = animation(car, "showcase", duration=6)
    show.channel("lid", path="translation", keys=[(0, (0, 0, 0)), (1, (0, 0, 40)), (2, (0, 0, 0))])
    show.explode("body/*", radial=True, distance=40, end=2)
    show.rotation("wheel*", axis=(0, 1, 0), turns=3, start=1, end=5, interpolation="LINEAR")
    show.hide("roof", at=3)
    show.pose(at={0: "shut", 4: "open"})

A part is named as a ref's owner names it (``refs``): a label, ``hand/finger.2``, a path from the
assembly the animation is on; a name with ``*``, ``?`` or ``[`` is a glob over the occurrences below
that assembly, matched against each one's label, its segment and its path from it, the outermost of
a match taken whole. Each name, or each occurrence a glob matches, is one **reference**: its parts
move as one body. A reference's **centre** is the middle of its parts' box as built, as the GLB
meshes them.

A channel's values are the reference's own, from as built: a ``translation`` key an offset (mm, the
model's frame), a ``rotation`` key a unit quaternion ``(x, y, z, w)``, the turn about ``about``
(default its centre), a ``scale`` key a uniform factor, applied as glTF scales a node, each part
about its own origin. Between keys, ``LINEAR`` is constant speed (a quaternion slerped),
``CUBICSPLINE`` eased in and out at every key (its tangents zero) and ``STEP`` holds a key until the
next. A channel applies from its first key and holds its last; before its first key it does nothing.

How channels compose. A reference's translations add, after its rotations (each about its pivot,
the later started after the earlier), and its scale is its latest started scale channel's. A
part's place is the transforms of every reference holding it, the largest outermost -- an
assembly's after its parts', as a scene graph composes them -- after the mechanism's pose, which
is innermost: channels move a posed part. One reference's two channels of one path overlapping in
time fail the build by name; so do two ``pose`` calls overlapping, and a part whose path one glTF
channel would interpolate by ``STEP`` and by another interpolation.

Validation is ordinary: a builder call checks its own arguments (a time outside ``[0, duration]``
among them), the harvest the names it resolves (a part no occurrence is, a mechanism state or joint
the mechanism lacks), the overlaps and the interpolations. Nothing here imports the kernel.
"""

from __future__ import annotations

import fnmatch
import math
from dataclasses import dataclass
from typing import Any

__all__ = ["ANIMATIONS", "Animation", "AnimationError", "INTERPOLATIONS", "Resolved", "Track", "animation",
           "from_json", "from_record", "harvest", "record", "to_json"]

# The attribute an assembly's animations live in, by name: plain values (the memo keys them).
ANIMATIONS = "xbf_animations"
INTERPOLATIONS = ("CUBICSPLINE", "LINEAR", "STEP")
CHANNEL_PATHS = ("translation", "rotation", "scale")
_GLOB = set("*?[")
_ZERO = (0.0, 0.0, 0.0)
# Which glTF paths a channel writes: a rotation turns a part about a pivot, so it moves it too.
PATHS = {"translation": ("translation",), "rotation": ("translation", "rotation"), "scale": ("scale",),
         "pose": ("translation", "rotation")}


class AnimationError(ValueError):
    """An animation the build will not keep, said by name."""


# --- authoring -------------------------------------------------------------------------------


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise TypeError(f"{what} is a number, not {value!r}")
    return float(value)


def _numbers(value: Any, count: int, what: str, shape: str) -> tuple[float, ...]:
    try:
        found = tuple(value)
    except TypeError:
        raise TypeError(f"{what} is {shape}, not {value!r}") from None
    if len(found) != count:
        raise TypeError(f"{what} is {shape}, not {value!r}")
    return tuple(_number(item, what) for item in found)


def _vector(value: Any, what: str) -> tuple[float, float, float]:
    return _numbers(value, 3, what, "(x, y, z)")  # type: ignore[return-value]


def _unit(value: Any, what: str) -> tuple[float, float, float]:
    vector = _vector(value, what)
    length = math.sqrt(sum(c * c for c in vector))
    if length < 1e-12:
        raise ValueError(f"{what} {vector} has no direction")
    return tuple(c / length for c in vector)  # type: ignore[return-value]


def _parts(parts: Any, where: str) -> tuple[str, ...]:
    found = (parts,) if isinstance(parts, str) else None
    if found is None:
        try:
            found = tuple(parts)
        except TypeError:
            raise TypeError(f"{where}: parts is a name, a path or a glob, or a list of them, not {parts!r}") from None
    if not found or not all(isinstance(part, str) and part.strip() for part in found):
        raise TypeError(f"{where}: parts is a name, a path or a glob, or a list of them, not {parts!r}")
    return tuple(part.strip() for part in found)


class Animation:
    """One animation of an assembly, as its calls build it: each call adds channels and returns the
    builder. What it holds is kept on the assembly as plain values (``ANIMATIONS``): per channel its
    path, its references, its interpolation, its keys, what it says beyond them (``extra``) and its
    name for errors."""

    def __init__(self, assembly: Any, name: str, duration: float) -> None:
        self.assembly, self.name, self.duration = assembly, name, duration
        self._channels: list[tuple] = []
        self._store()

    def __repr__(self) -> str:
        return f"<animation {self.name!r}: {self.duration:g} s, {len(self._channels)} channels>"

    def _store(self) -> None:
        held = dict(self.assembly.__dict__.get(ANIMATIONS) or {})
        held[self.name] = (self.duration, tuple(self._channels))
        self.assembly.__dict__[ANIMATIONS] = held

    def _where(self, call: str) -> str:
        return f"animation {self.name!r}: {call}"

    def _time(self, value: Any, what: str, where: str) -> float:
        found = _number(value, f"{where}: {what}")
        if not 0.0 <= found <= self.duration:
            raise ValueError(f"{where}: {what} {found:g} s is outside the animation's 0 to {self.duration:g} s")
        return found

    def _interpolation(self, interpolation: Any, where: str) -> str:
        if interpolation not in INTERPOLATIONS:
            raise ValueError(f"{where}: interpolation is one of {', '.join(INTERPOLATIONS)}, not {interpolation!r}")
        return interpolation

    def _span(self, start: Any, end: Any, interpolation: str, where: str) -> tuple[float, float]:
        begin = self._time(start, "start", where)
        finish = self._time(self.duration if end is None else end, "end", where)
        if finish < begin or (finish == begin and interpolation != "STEP"):
            raise ValueError(f"{where}: end {finish:g} s is not after start {begin:g} s")
        return begin, finish

    def _ramp(self, start: float, end: float, interpolation: str, first: Any, last: Any) -> tuple:
        """The keys of a channel from ``start`` to ``end``: one, a STEP's jump, where they coincide."""
        return ((end, last),) if start == end else ((start, first), (end, last))

    def _add(self, path: str, refs: tuple[str, ...], interpolation: str, keys: tuple, extra: Any,
             label: str) -> "Animation":
        self._channels.append((path, refs, interpolation, keys, extra, label))
        self._store()
        return self

    def channel(self, parts: Any, *, path: str, keys: Any, interpolation: str = "CUBICSPLINE",
                about: Any = None) -> "Animation":
        """glTF's channel on ``parts``: ``path`` (``translation``, ``rotation`` or ``scale``) through
        ``keys``, ``[(t, value), ...]`` in increasing time, by ``interpolation`` (``CUBICSPLINE``,
        ``LINEAR`` or ``STEP``). A translation's value is an offset from as built (mm), a
        rotation's a unit quaternion ``(x, y, z, w)``, the turn about ``about`` (default the
        reference's centre), a scale's a uniform factor (1 as built)."""
        where = self._where(f"{path} channel of {parts!r}")
        refs = _parts(parts, where)
        if path not in CHANNEL_PATHS:
            raise ValueError(f"{where}: path is one of {', '.join(CHANNEL_PATHS)}, not {path!r}")
        interpolation = self._interpolation(interpolation, where)
        try:
            rows = list(keys)
        except TypeError:
            raise TypeError(f"{where}: keys are [(t, value), ...], not {keys!r}") from None
        if not rows:
            raise ValueError(f"{where} has no key")
        found = []
        for at, row in enumerate(rows):
            if not isinstance(row, (tuple, list)) or len(row) != 2:
                raise TypeError(f"{where}: key {at} is (t, value), not {row!r}")
            t = self._time(row[0], f"key {at}'s time", where)
            if found and t <= found[-1][0]:
                raise ValueError(f"{where}: key {at} at {t:g} s is not after the one before it")
            what = f"{where}: key {at}'s value"
            if path == "translation":
                value: Any = _vector(row[1], what)
            elif path == "rotation":
                value = _numbers(row[1], 4, what, "a quaternion (x, y, z, w)")
                norm = math.sqrt(sum(c * c for c in value))
                if abs(norm - 1.0) > 1e-6:
                    raise ValueError(f"{what} {value} is not a unit quaternion")
            else:
                value = _number(row[1], what)
                if value < 0:
                    raise ValueError(f"{what} is a factor of 0 or more, not {value:g}")
            found.append((t, value))
        if path == "rotation":
            extra: Any = ("quaternion", None if about is None else _vector(about, f"{where}: about"))
        elif about is not None:
            raise TypeError(f"{where}: about= is a rotation's")
        else:
            extra = None
        return self._add(path, refs, interpolation, tuple(found), extra, where)

    def translation(self, parts: Any, *, by: Any = None, to: Any = None, start: Any = 0.0, end: Any = None,
                    interpolation: str = "CUBICSPLINE") -> "Animation":
        """A translation channel moving ``parts`` from ``start`` to ``end``: ``by`` a vector (mm,
        the model's frame), or ``to`` a point their centre reaches."""
        where = self._where(f"translation of {parts!r}")
        refs = _parts(parts, where)
        if (by is None) == (to is None):
            raise TypeError(f"{where} takes by= or to=: one of them")
        interpolation = self._interpolation(interpolation, where)
        begin, finish = self._span(start, end, interpolation, where)
        if by is not None:
            return self._add("translation", refs, interpolation,
                             self._ramp(begin, finish, interpolation, _ZERO, _vector(by, f"{where}: by")), None, where)
        return self._add("translation", refs, interpolation, self._ramp(begin, finish, interpolation, _ZERO, _ZERO),
                         ("to", _vector(to, f"{where}: to")), where)

    def rotation(self, parts: Any, *, axis: Any, turns: Any = None, by: Any = None, to: Any = None, about: Any = None,
                 start: Any = 0.0, end: Any = None, interpolation: str = "CUBICSPLINE") -> "Animation":
        """A rotation channel turning ``parts`` about ``axis`` (the model's frame) through a point,
        ``about`` (default their centre), from ``start`` to ``end``: ``turns`` whole turns, ``by``
        degrees, or ``to`` degrees from as built (the reference's earlier turns about the same axis
        counted). The right-hand rule gives the sense; a turn of any size is kept whole."""
        where = self._where(f"rotation of {parts!r}")
        refs = _parts(parts, where)
        given = [(kind, value) for kind, value in (("turns", turns), ("by", by), ("to", to)) if value is not None]
        if len(given) != 1:
            raise TypeError(f"{where} takes turns=, by= or to=: one of them")
        kind, value = given[0]
        degrees = _number(value, f"{where}: {kind}") * (360.0 if kind == "turns" else 1.0)
        unit = _unit(axis, f"{where}: axis")
        pivot = None if about is None else _vector(about, f"{where}: about")
        interpolation = self._interpolation(interpolation, where)
        begin, finish = self._span(start, end, interpolation, where)
        return self._add("rotation", refs, interpolation, self._ramp(begin, finish, interpolation, 0.0, degrees),
                         ("degrees", unit, pivot, kind == "to"), where)

    def scale(self, parts: Any, *, to: Any, start: Any = 0.0, end: Any = None,
              interpolation: str = "CUBICSPLINE") -> "Animation":
        """A scale channel taking each of ``parts`` from its scale at ``start`` to ``to`` (1 as
        built) at ``end``, uniformly about its own origin, as glTF scales a node."""
        where = self._where(f"scale of {parts!r}")
        refs = _parts(parts, where)
        factor = _number(to, f"{where}: to")
        if factor < 0:
            raise ValueError(f"{where}: to is a factor of 0 or more, not {factor:g}")
        interpolation = self._interpolation(interpolation, where)
        begin, finish = self._span(start, end, interpolation, where)
        # None: the reference's scale where the channel starts, which the bake knows.
        return self._add("scale", refs, interpolation, self._ramp(begin, finish, interpolation, None, factor), None,
                         where)

    def hide(self, parts: Any, *, at: Any) -> "Animation":
        """A helper: ``parts`` out of view from ``at`` seconds. glTF has no visibility channel, so
        it compiles to a ``STEP`` scale channel to 0; ``scale(parts, to=1, start=t, end=t,
        interpolation="STEP")`` brings them back."""
        where = self._where(f"hide of {parts!r}")
        refs = _parts(parts, where)
        when = self._time(at, "at", where)
        return self._add("scale", refs, "STEP", ((when, 0.0),), None, where)

    def pose(self, *, at: Any, interpolation: str = "CUBICSPLINE") -> "Animation":
        """A helper driving the mechanism: ``at={t: pose}``, each ``pose`` a mechanism state's name or
        ``{joint or coupling: value}`` (the rest as built). It compiles to translation and rotation
        channels on every part the mechanism moves, placed by forward kinematics with the joint
        values interpolated between the keys (``CUBICSPLINE`` eased in and out at each). Before its
        first time the mechanism stands at the first pose, after the last at the last."""
        where = self._where("pose")
        interpolation = self._interpolation(interpolation, where)
        if not isinstance(at, dict) or not at:
            raise TypeError(f"{where}: at is {{t: mechanism state or joint values}}, not {at!r}")
        keys = []
        for t in sorted(at, key=lambda t: _number(t, f"{where}: a time")):
            pose = at[t]
            when = self._time(t, "a time", where)
            if isinstance(pose, str):
                keys.append((when, pose))
            elif isinstance(pose, dict):
                values = []
                for label, value in pose.items():
                    if not isinstance(label, str):
                        raise TypeError(f"{where}: at {when:g} s: a joint is named by its label, not {label!r}")
                    numbers = (value,) if isinstance(value, (int, float)) and not isinstance(value, bool) else value
                    try:
                        values.append((label, tuple(_number(v, f"{where}: at {when:g} s: joint {label!r}")
                                                    for v in numbers)))
                    except TypeError:
                        raise TypeError(f"{where}: at {when:g} s: joint {label!r} takes a number, or a sequence of "
                                        f"numbers for a joint of several values, not {value!r}") from None
                keys.append((when, tuple(values)))
            else:
                raise TypeError(f"{where}: at {when:g} s is a mechanism state's name or a dict of joint values, "
                                f"not {pose!r}")
        return self._add("pose", (), interpolation, tuple(keys), None, where)

    def stagger(self, parts: Any, *, by: Any, step: Any, start: Any = 0.0, each: Any = None,
                interpolation: str = "CUBICSPLINE") -> "Animation":
        """A helper: each of ``parts`` in turn moved ``by`` a vector, the first from ``start``, each
        next ``step`` seconds after the one before, each taking ``each`` seconds (default
        ``step``). It compiles to a translation channel per reference, a glob's in the tree's
        order."""
        where = self._where(f"stagger of {parts!r}")
        refs = _parts(parts, where)
        interpolation = self._interpolation(interpolation, where)
        gap = _number(step, f"{where}: step")
        length = gap if each is None else _number(each, f"{where}: each")
        if gap < 0 or length <= 0:
            raise ValueError(f"{where}: step is 0 or more seconds and each more than 0")
        begin = self._time(start, "start", where)
        self._time(begin + length, "the first move's end", where)
        return self._add("stagger", refs, interpolation, ((begin, _ZERO), (begin + length, _vector(by, f"{where}: by"))),
                         gap, where)

    def explode(self, parts: Any, *, direction: Any = None, radial: Any = None, distance: Any, start: Any = 0.0,
                end: Any = None, interpolation: str = "CUBICSPLINE") -> "Animation":
        """A helper moving ``parts`` apart from ``start`` to ``end``: along ``direction``, each by
        ``distance`` times its rank along it (their centres in order; the first stays), or
        ``radial`` -- a point, or True for the middle of their centres -- each ``distance`` away
        from it along the line through its centre. It compiles to a translation channel per
        reference."""
        where = self._where(f"explode of {parts!r}")
        refs = _parts(parts, where)
        if (direction is None) == (radial is None or radial is False):
            raise TypeError(f"{where} takes direction= or radial=: one of them")
        reach = _number(distance, f"{where}: distance")
        interpolation = self._interpolation(interpolation, where)
        begin, finish = self._span(start, end, interpolation, where)
        if direction is not None:
            extra: tuple = ("explode", "direction", _unit(direction, f"{where}: direction"), reach)
        else:
            extra = ("explode", "radial", None if radial is True else _vector(radial, f"{where}: radial"), reach)
        return self._add("translation", refs, interpolation, self._ramp(begin, finish, interpolation, _ZERO, _ZERO),
                         extra, where)


def animation(assembly: Any, name: str, *, duration: Any) -> Animation:
    """An animation of ``assembly`` named ``name``, ``duration`` seconds long (the length its GLB
    animation's ``extras`` say, as a configuration sequence's): the builder its channels are added
    to (see the module). Baked into a GLB the model declares, and kept in its xbf as a build record
    a GLB of the document bakes again; naming one again starts it afresh."""
    import build123d as bd

    if not isinstance(assembly, bd.Shape):
        raise TypeError(f"animation() takes the assembly whose parts it moves, not {type(assembly).__name__}")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("an animation's name is a non-empty string")
    seconds = _number(duration, f"animation {name!r}: duration")
    if seconds <= 0:
        raise ValueError(f"animation {name!r}: duration is a number of seconds above 0, not {duration!r}")
    return Animation(assembly, name, seconds)


# --- harvest ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Track:
    """One channel resolved: its path (``translation``, ``rotation``, ``scale``, or ``pose`` for
    the mechanism's), its interpolation, its keys, its references (each the occurrence paths of
    its parts, from the document's root), what it says beyond its keys (``extra``: see
    ``export/animation.py``), its name for errors and its place among the animation's calls. A
    stagger is already its translations, one per reference; a pose's keys are every pair's values."""

    path: str
    interpolation: str
    keys: tuple
    groups: tuple[tuple[tuple[int, ...], ...], ...]
    extra: Any
    label: str
    order: int

    @property
    def start(self) -> float:
        return self.keys[0][0]

    @property
    def end(self) -> float:
        return self.keys[-1][0]


@dataclass(frozen=True)
class Resolved:
    """An animation as the GLB writer bakes it: its name, its duration and its channels."""

    name: str
    duration: float
    tracks: tuple[Track, ...]


def to_json(resolved: dict[str, Resolved] | None) -> list[dict[str, Any]] | None:
    """A build's animations (``harvest``) as plain JSON, every track's fields as they are, its
    tuples as lists: the build record the xbf carries (``record``). ``from_json`` gives back the
    same values, so a GLB baked from them is the GLB the build's tree bakes. None for none."""
    if not resolved:
        return None
    return [{"name": item.name, "duration": item.duration,
             "tracks": [[track.path, track.interpolation, track.keys, track.groups, track.extra, track.label,
                         track.order] for track in item.tracks]} for item in resolved.values()]


def from_json(rows: list[dict[str, Any]] | None) -> dict[str, Resolved] | None:
    """``to_json``'s animations again, by name, every list a tuple as the harvest made it."""
    if not rows:
        return None

    def tupled(value: Any) -> Any:
        if isinstance(value, dict):
            return {name: tupled(item) for name, item in value.items()}
        return tuple(tupled(item) for item in value) if isinstance(value, list) else value

    return {row["name"]: Resolved(row["name"], float(row["duration"]),
                                  tuple(Track(path, interpolation, tupled(keys), tupled(groups), tupled(extra), label,
                                              order)
                                        for path, interpolation, keys, groups, extra, label, order in row["tracks"]))
            for row in rows}


def record(resolved: dict[str, Resolved] | None) -> str | None:
    """A build's animations as the xbf's main label holds them: ``to_json``'s rows as ASCII JSON
    text, in the build's order, with no spaces. None for none, and the document holds no record."""
    import json

    rows = to_json(resolved)
    return None if rows is None else json.dumps(rows, separators=(",", ":"), allow_nan=False)


def from_record(text: str | None) -> dict[str, Resolved] | None:
    """The animations a document's record holds (``record``), by name; None for none."""
    import json

    return from_json(json.loads(text)) if text else None


def _occurrence_tree(tree: Any) -> tuple[Any, dict[tuple[int, ...], Any]]:
    """The document's occurrences as a ref tree (``refs.Node``), each named as the document names
    it and holding its occurrence path; and each node by its path."""
    from cadgen.engine import refs
    from cadgen.engine.document import Assembly

    nodes: dict[tuple[int, ...], Any] = {}

    def visit(prototype: Any, parent: Any, name: str, path: tuple[int, ...]) -> Any:
        node = refs.Node(name, path, not isinstance(prototype, Assembly), parent)
        nodes[path] = node
        if isinstance(prototype, Assembly):
            for at, component in enumerate(prototype.components, 1):
                held = component.prototype
                node.children.append(visit(held, node, component.name or held.name or f"{name}.{at}", path + (at - 1,)))
        return node

    root = visit(tree.root, None, tree.root.name, ())
    refs._segments(root)
    return root, nodes


def _relative(base: Any, node: Any) -> str:
    steps = node.path()
    return "/".join(step.segment for step in steps[steps.index(base) + 1:])


def _shown(node: Any) -> str:
    return "/".join(step.segment for step in node.path())


def _resolve(base: Any, ref: str, where: str) -> list[Any]:
    """The occurrences ``ref`` names under ``base`` (see the module), each once, in tree order."""
    from cadgen.engine import refs

    if _GLOB & set(ref):
        below = [node for node in base.walk() if node is not base]
        hits = {id(node) for node in below
                if fnmatch.fnmatchcase(node.segment, ref) or fnmatch.fnmatchcase(node.label, ref)
                or fnmatch.fnmatchcase(_relative(base, node), ref)}
        found = [node for node in below if id(node) in hits
                 and not any(id(parent) in hits for parent in node.path()[:-1])]
        if not found:
            raise AnimationError(f"{where}: the glob {ref!r} matches no part or assembly of {_shown(base)}")
        return found
    try:
        file, selectors = refs.parse(ref)
    except refs.RefError as error:
        raise AnimationError(f"{where}: {error}") from None
    if file is not None or len(selectors) != 1 or selectors[0].owner is None or selectors[0].element is not None:
        raise AnimationError(f"{where}: {ref!r} names one part or assembly, as a ref's owner does (hand/finger.2, "
                             "palm): no element, no document")
    found = refs.owners(base, selectors[0].owner)
    if not found:
        raise AnimationError(f"{where}: {_shown(base)} has no part or assembly {ref}; nearest: "
                             f"{refs._nearest(base, ref)}")
    if len(found) > 1:
        raise AnimationError(f"{where}: {ref} names {len(found)} occurrences: "
                             f"{', '.join(_relative(base, node) for node in found[:8])}")
    return found


def _leaves(node: Any) -> tuple[tuple[int, ...], ...]:
    return tuple(found.payload for found in node.walk() if found.part)


def harvest(result: Any, tree: Any, root_path: tuple[int, ...], mechanism: Any) -> dict[str, Resolved] | None:
    """Every animation on the result's assemblies, resolved against the document's tree (see the
    module), by name -- a name two assemblies share taken with the path of each -- or None.
    ``mechanism`` is the document's (``mechanism.harvest``), which ``pose`` drives."""
    from cadgen.engine import mechanism as kinematics

    held = [(obj, path, found) for obj, path in kinematics._objects(result, root_path)
            if (found := obj.__dict__.get(ANIMATIONS))]
    if not held:
        return None
    _root, nodes = _occurrence_tree(tree)
    counts: dict[str, int] = {}
    for _obj, _path, found in held:
        for name in found:
            counts[name] = counts.get(name, 0) + 1
    motions = set(mechanism.motions) if mechanism is not None else set()
    block = None
    resolved: dict[str, Resolved] = {}
    for _obj, path, found in held:
        base = nodes[path]
        for name, (duration, raw) in found.items():
            key = name if counts[name] == 1 else f"{_shown(base)}:{name}"
            if key in motions:
                raise AnimationError(f"animation {key!r} has the name of a configuration sequence of the mechanism: "
                                     "give it its own")
            tracks: list[Track] = []
            for order, (channel, refs_, interpolation, keys, extra, label) in enumerate(raw):
                if channel == "pose":
                    if block is None:
                        if mechanism is None or not mechanism.pairs:
                            raise AnimationError(f"{label}: the model has no paired joints to pose")
                        from cadgen.engine.document import _matrix

                        block = kinematics.block(mechanism, [], lambda at: _matrix(kinematics._occurrence(tree, at)[0]))
                    poses = []
                    for when, pose in keys:
                        given = pose if isinstance(pose, str) else {joint: values for joint, values in pose}
                        try:
                            values, _named = kinematics.resolve(block, given)
                        except kinematics.KinematicsError as error:
                            raise AnimationError(f"{label}: at {when:g} s: {error}") from None
                        poses.append((when, tuple(sorted(values.items()))))
                    tracks.append(Track("pose", interpolation, tuple(poses), (), None, label, order))
                    continue
                groups = [node for ref in refs_ for node in _resolve(base, ref, label)]
                if channel == "stagger":
                    gap = extra
                    (begin, zero), (finish, vector) = keys
                    for at, node in enumerate(groups):
                        shift = at * gap
                        if finish + shift > duration + 1e-9:
                            raise AnimationError(f"{label}: {_relative(base, node)}'s move ends at "
                                                 f"{finish + shift:g} s, past the animation's {duration:g} s")
                        tracks.append(Track("translation", interpolation, ((begin + shift, zero), (finish + shift, vector)),
                                            (_leaves(node),), None, f"{label} ({_relative(base, node)})", order))
                else:
                    tracks.append(Track(channel, interpolation, keys, tuple(_leaves(node) for node in groups), extra,
                                        label, order))
            _check(tracks, key, nodes, mechanism)
            resolved[key] = Resolved(key, duration, tuple(tracks))
    return resolved


def _check(tracks: list[Track], name: str, nodes: dict[tuple[int, ...], Any], mechanism: Any) -> None:
    """Two channels of a path overlapping on one reference, two poses overlapping, a rotation
    ``to=`` after a turn about another axis, and a part one glTF channel would interpolate by
    ``STEP`` and by another interpolation: refused by name."""

    def shown(leaves: tuple[tuple[int, ...], ...]) -> str:
        first = _shown(nodes[leaves[0]])
        return first if len(leaves) == 1 else f"{len(leaves)} parts from {first}"

    spans: dict[tuple, list[Track]] = {}
    for track in tracks:
        for group in track.groups or ((),):
            spans.setdefault((track.path, frozenset(group)), []).append(track)
    for (path, group), held in spans.items():
        held.sort(key=lambda track: (track.start, track.end, track.order))
        for a, b in zip(held, held[1:]):
            if max(a.start, b.start) < min(a.end, b.end) or a.end == b.end or b.start < a.end:
                what = "the mechanism" if path == "pose" else shown(tuple(sorted(group)))
                raise AnimationError(f"animation {name!r}: {a.label} ({a.start:g} to {a.end:g} s) and {b.label} "
                                     f"({b.start:g} to {b.end:g} s) both drive the {path} of {what}: one glTF "
                                     "channel each, in turn")
        if path == "rotation":
            axes: list[tuple] = []
            for track in held:
                if track.extra[0] != "degrees":
                    axes.append(())
                    continue
                _kind, axis, _pivot, absolute = track.extra
                if absolute and any(not other or abs(abs(sum(a * b for a, b in zip(axis, other))) - 1.0) > 1e-9
                                    for other in axes):
                    raise AnimationError(f"animation {name!r}: {track.label} turns to an angle about {axis} after a "
                                         "turn about another axis: give it by= degrees")
                axes.append(axis)
    moved: set[tuple[int, ...]] = set()
    if mechanism is not None and any(track.path == "pose" for track in tracks):
        moved = {path for at, link in enumerate(mechanism.links) if at != mechanism.ground for path in link.members}
    interpolations: dict[tuple[tuple[int, ...], str], dict[str, str]] = {}
    for track in tracks:
        if track.path == "pose":
            leaves = [leaf for leaf, node in nodes.items()
                      if node.part and any(leaf[:n] in moved for n in range(len(leaf) + 1))]
        else:
            leaves = [leaf for group in track.groups for leaf in group]
        for leaf in leaves:
            for path in PATHS[track.path]:
                interpolations.setdefault((leaf, path), {}).setdefault(track.interpolation, track.label)
    for (leaf, path), held_by in interpolations.items():
        if "STEP" in held_by and len(held_by) > 1:
            other = next(kind for kind in held_by if kind != "STEP")
            raise AnimationError(f"animation {name!r}: the {path} of {shown((leaf,))} is STEP by {held_by['STEP']} "
                                 f"and {other} by {held_by[other]}: a glTF channel has one interpolation")
