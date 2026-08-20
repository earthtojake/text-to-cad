"""What a CAD generator can say about its own progress.

``gen_step()`` is called with no arguments and is usually the longest phase of a build --
ten minutes for the F-14, against two for meshing everything it produced. Until this module
it had no way to say anything: the build reported "Building geometry" once, at the start,
and then went silent until the generator returned. The viewer and the CLI both showed a
stalled bar for the entire run.

Nothing here is required. A generator that says nothing behaves exactly as it always has,
and outside a build (a plain ``python model.step.py``, a test) every call is a no-op -- so
instrumentation costs a generator nothing at import time and never needs guarding.

Two shapes, matching the two things a phase can honestly report::

    from cadgen.progress import report, track

    def gen_step():
        for name, module in track(SYSTEMS, label=lambda pair: pair[0]):
            ...                      # -> "Building geometry  4/13  engines"

    def gen_step():
        report("lofting the skin")   # -> "Building geometry  lofting the skin"
        ...

:func:`track` gives a real fraction when the work list has a length; :func:`report` names
the sub-unit in flight when it does not. Neither invents a number.

A caveat worth knowing before reading too much into a count: units are rarely equal in
cost. The F-14's 13 systems include one airframe loft that is over half the phase, so
``1/13`` sits for minutes and then several tick past in seconds. The count is true; it is
just not linear in time, and no reporting layer can make it so.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Iterator, Sized

from cadgen.coordination import current_build

__all__ = ["report", "track"]


def report(detail: str) -> None:
    """Name the part of the model being built right now.

    For a phase with no countable work list. The label replaces whatever was showing; it
    does not accumulate.
    """
    run = current_build()
    if run is not None:
        run.detail(str(detail or ""))


def _label_for(item: Any, label: Callable[[Any], str] | None) -> str:
    if label is not None:
        try:
            return str(label(item) or "")
        except Exception:  # noqa: BLE001 - a label must never break a build
            return ""
    return item if isinstance(item, str) else ""


def track(
    items: Iterable[Any], *, label: Callable[[Any], str] | None = None
) -> Iterator[Any]:
    """Iterate ``items``, reporting the build's way through them.

    The count advances when an item's work is DONE (after the loop body returns), while the
    label names the item in flight -- so a reader sees "3 finished, now on engines" rather
    than claiming an item is complete the moment it starts.

    ``items`` is only measured when it already has a length. A lazy iterable is passed
    through lazily and reported by label alone, because consuming it here to obtain a
    denominator would change when the caller's work actually runs.
    """
    run = current_build()
    if run is None:
        yield from items
        return
    if isinstance(items, Sized):
        total = len(items)
        if total:
            run.set_total(total)
    for item in items:
        run.detail(_label_for(item, label))
        yield item
        run.advance()
