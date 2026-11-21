"""``python -m cad.quiddity._recogniser``: quiddity's recognition of each STEP handed in, answered as it is done.

The child process of a part's features (``cad.quiddity._process``, which says why it is a process of its own): the
one module that imports quiddity. It speaks frames on its standard input and output (``_frames``):

* out, first: ``{"quiddity": "<its version>"}`` once quiddity is imported, or ``{"reason": "not_installed",
  "detail": ...}`` where this Python has none, and it ends;
* in: one part's STEP, its bytes; an empty frame, or the end of the input, ends it;
* out, for each: ``{"document": <quiddity's recognition document>, "anchors": <its anchors>}``, both quiddity's
  own, untouched (``quiddity.recognise``'s ``document``; ``quiddity.anchors``: a point it proves on each face, by
  which the parent checks whose face is whose), or ``{"reason": "refused" | "failed", "detail": ...}``: quiddity's
  refusal of the input in its words (a ``ValueError``), or whatever else it raised (a panic in its Rust is a
  ``quiddity.QuiddityError``).

The frames cross on descriptors of the child's own: its standard input is the null device from its start
(``cad.engine.places.standard_input_aside``) and whatever quiddity's native code prints goes to standard error.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from cad.quiddity._frames import read, send

__all__ = ["main"]


def _one(quiddity: Any, step: bytes) -> dict[str, Any]:
    try:
        recognised = quiddity.recognise(step)
        anchored = quiddity.anchors(step)
    except ValueError as error:  # quiddity's refusal of the input, in its words
        return {"reason": "refused", "detail": str(error)}
    except Exception as error:  # noqa: BLE001 -- a panic in its Rust (QuiddityError), or anything else: said by the parent
        return {"reason": "failed", "detail": f"{type(error).__name__}: {error}"}
    try:
        return {"document": json.loads(recognised)["document"], "anchors": json.loads(anchored)}
    except (ValueError, KeyError, TypeError) as error:
        return {"reason": "failed", "detail": f"quiddity's answer does not read: {type(error).__name__}: {error}"}


def main() -> int:
    from cad.engine.places import standard_input_aside

    # The frames' pipes on descriptors of this module's own, before quiddity loads: standard input is the null
    # device to whatever it loads, and what native code prints goes to stderr, never into the frames.
    frames_in = os.fdopen(standard_input_aside(), "rb")
    sys.stdout.flush()
    frames_out = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    try:
        import quiddity
    except Exception as error:  # noqa: BLE001 -- no quiddity here, or one that does not load: said by the parent
        send(frames_out, {"reason": "not_installed", "detail": f"{type(error).__name__}: {error}"})
        return 0
    send(frames_out, {"quiddity": str(quiddity.__version__)})
    while True:
        step = read(frames_in)
        if not step:
            return 0
        send(frames_out, _one(quiddity, step))


if __name__ == "__main__":
    sys.exit(main())
