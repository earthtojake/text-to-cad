"""What the library counts for telemetry, told to the server's telemetry where the server installed it.

The library sends nothing and keeps nothing: a drawing made, and a mistake of cadgen's own code met making
one, are handed to ``TELEMETRY`` -- the server's ``cadgen.analytics``, which its commands install here
(``cadgen._internal.engine_telemetry.install``) -- and dropped where none is installed: a model's own
process, in the CAD kernel environment, has only the library. Neither ever fails, nor changes, what it
counts.
"""

from __future__ import annotations

from typing import Any

# The server's telemetry (``cadgen.analytics``: ``report`` and ``hand_over``), or None: nothing is counted.
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
