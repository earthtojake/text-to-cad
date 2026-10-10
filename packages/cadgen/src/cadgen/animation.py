"""Animation clips: authored in Python, baked to keyframes when the model builds.

The ``animation=`` kwarg on ``@step`` takes a dict of clip id -> :func:`clip`::

    def spin(t, m):
        m.get("#rotor").rotate((0, 0, 1), 90 * t)

    @step(out="../STEP/motor.step", animation={"spin": cadgen.clip(spin, duration=4)})
    def motor(): ...

When the model builds, ``update(t, m)`` is called at ``fps`` samples a second
from ``t = 0`` to ``t = duration`` with ``m``, the model handle. Every sample
starts from rest, so ``update`` must be a pure function of ``t``. The samples
become KEYFRAMES in the model's sidecar; the viewer, snapshots and GLB exports
interpolate them, and no animation code ships with a model.

``m.get(*targets)`` takes ``#name`` (the part or group of that name) or
``#o1.2`` (an occurrence id), each with everything beneath it, and returns a
handle on their union. A name several nodes share raises, listing numbered
aliases (``#bolt_1``, ``#bolt_2``) that each name one, and so does a target
that names nothing. ``m.labels()`` lists the names. A handle's methods chain:

    .rotate(axis, degrees, origin=(0, 0, 0))
    .translate(vector)
    .transform(matrix)        # a rigid 4x4, row-major, translation in the last column
    .opacity(value)           # 0..1
    .visible(flag)
    .deform_tube(rest=..., path=..., twist_deg=0, max_segment_length=1, braid=None)

Transform calls PREMULTIPLY: a later call acts in world space on the
already-moved part, so a spin about a part's own center followed by an orbit
about the assembly origin makes the spin ride the orbit. ``deform_tube`` bends
a swept tube body from its ``rest`` centerline onto ``path``; a centerline is
``{"normal": [x, y, z], "segments": [...]}`` of ``line`` (start, end), ``arc``
(center, axis, start, sweepDeg) and ``bezier`` (four points) segments that
meet with matching tangents.

This module must import light (no OCP, no numpy): it runs in the
decoration-time pre-gate window. Sampling happens at build time
(``cadgen._internal.animation_bake``).
"""

from __future__ import annotations

import inspect
import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping

__all__ = ["Clip", "clip", "normalize_clips"]

# Samples a second the build evaluates a clip at, unless the clip says otherwise.
DEFAULT_FPS = 60.0


@dataclass(frozen=True)
class Clip:
    """One named motion: ``update(t, m)`` over ``duration`` seconds."""

    update: Callable[[float, Any], None]
    duration: float
    loop: bool = True
    label: str | None = None
    fps: float = DEFAULT_FPS


def _fail(message: str) -> ValueError:
    return ValueError(message)


def clip(
    update: Callable[[float, Any], None],
    *,
    duration: float,
    loop: bool = True,
    label: str | None = None,
    fps: float = DEFAULT_FPS,
) -> Clip:
    """Declare a clip: ``update(t, m)`` sampled ``fps`` times a second over
    ``duration`` seconds. ``loop=False`` holds the last pose at the end;
    ``label`` is what the viewer lists (the clip's id by default)."""
    if not callable(update):
        raise _fail(f"cadgen.clip needs update(t, m) as a function, got {type(update).__name__}")
    try:
        inspect.signature(update).bind(0.0, None)
    except TypeError:
        raise _fail(f"cadgen.clip: {getattr(update, '__name__', 'update')}() must take (t, m)") from None
    except ValueError:
        pass  # a builtin or C callable without a readable signature: called as (t, m) at build
    for name, value, minimum in (("duration", duration, 0.0), ("fps", fps, 0.0)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= minimum:
            raise _fail(f"cadgen.clip {name} must be a positive number of {'seconds' if name == 'duration' else 'samples a second'}, got {value!r}")
    if not isinstance(loop, bool):
        raise _fail(f"cadgen.clip loop must be True or False, got {loop!r}")
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise _fail(f"cadgen.clip label must be a nonempty string, got {label!r}")
    return Clip(update=update, duration=float(duration), loop=loop, label=label.strip() if label else None, fps=float(fps))


def normalize_clips(value: object, *, where: str) -> dict[str, Clip] | None:
    """Validate an ``animation=`` declaration at decoration time: a nonempty
    dict of clip id -> :func:`clip`. Targets resolve when the model builds."""
    if value is None:
        return None
    if not isinstance(value, Mapping) or not value:
        raise _fail(
            f"{where} must be a dict of clip id -> cadgen.clip(update, duration=...), "
            f"got {type(value).__name__ if not isinstance(value, Mapping) else 'an empty dict'}"
        )
    clips: dict[str, Clip] = {}
    for clip_id, entry in value.items():
        if not isinstance(clip_id, str) or not clip_id or clip_id != clip_id.strip():
            raise _fail(f"{where} clip ids must be nonempty strings without surrounding spaces, got {clip_id!r}")
        if not isinstance(entry, Clip):
            raise _fail(f"{where}[{clip_id!r}] must be built by cadgen.clip(update, duration=...), got {type(entry).__name__}")
        clips[clip_id] = entry
    return clips
