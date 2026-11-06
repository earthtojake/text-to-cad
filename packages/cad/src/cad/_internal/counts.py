"""What the library counts for telemetry, told to the server's telemetry where the server installed it.

The library sends nothing and keeps nothing: a drawing made, and a mistake of cadgen's own code met making
one, are handed to ``TELEMETRY`` -- the server's ``cad_server.analytics``, which its commands install here
(``cad_server._internal.engine_telemetry.install``) -- and dropped where none is installed: a model's own
process, in the CAD kernel environment, has only the library. Neither ever fails, nor changes, what it
counts.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

# The server's telemetry (``cad_server.analytics``: ``report`` and ``hand_over``), or None: nothing is counted.
TELEMETRY: Any = None


def report(error: BaseException, where: str, **options: Any) -> None:
    """A mistake of cadgen's own code, told to the server's telemetry (``analytics.report``). Never raises."""
    if TELEMETRY is None:
        return
    try:
        TELEMETRY.report(error, where, **options)
    except Exception:  # noqa: BLE001 - a crash report never adds a failure to one
        pass


def hand_over(counts: dict[str, Any]) -> None:
    """What a model's process counted (``{"features": ["drawing"]}``), kept with a command's counts by the
    server's telemetry (``analytics.hand_over``). Never raises."""
    if TELEMETRY is None:
        return
    try:
        TELEMETRY.hand_over(counts)
    except Exception:  # noqa: BLE001 - a count never fails what it counts
        pass


def counted(run: Callable[..., Any], feature: str) -> Callable[..., Any]:
    """``run``, a script's document decorator (``@eng_drawing``, ``@work_instruction``), counted as
    ``feature`` (the server's ``FEATURES``): a document made (``hand_over``), or a mistake in cadgen's own
    code making one (``report``). Neither ever changes what the document does."""

    @functools.wraps(run)
    def made(*args: Any, **kwargs: Any) -> Any:
        try:
            document = run(*args, **kwargs)
        except Exception as error:
            report(error, "build", bugs_only=True)  # the person's own mistakes are theirs
            raise
        hand_over({"features": [feature]})
        return document

    return made
