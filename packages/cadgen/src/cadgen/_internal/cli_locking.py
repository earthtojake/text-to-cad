"""The CLI half of artifact coordination: how a command-line producer waits, reports the
wait, and answers when it decides not to wait at all.

One implementation for every artifact CLI (``step_artifact_cli``, ``dxf_artifact``,
``implicit_artifact``, and the ``gen`` path in ``_internal.generation`` -- ``export``
shares the wait notice but never takes the write lock, so it has no build to hand to a
peer), because the three things below have to agree across all of them:

* the flag name and its default, since the CAD Viewer passes ``--lock-timeout`` to whichever
  module a given entry maps to and a module that did not accept it would fail argument
  parsing rather than build;
* the wait notice, which is the only thing distinguishing a contended acquire from a hang --
  cadgen's acquire is blocking by default, so without it a queued build emits nothing on
  either stream for as long as the peer holds the lock;
* the shape of the "a peer has it" payload, which the viewer branches on.

Not in :mod:`cadgen.coordination`: that package is the cross-process protocol shared with
the viewer's long-lived server, and it has no business knowing about argparse or loggers.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from cadgen.cli_logging import CliLogger, format_elapsed

# Waiting is the CLI default on purpose: an agent that asked for a build wants the build,
# and giving up would leave it with no artifact and nothing to do about it. The viewer is
# the caller that must not block, and it passes an explicit timeout.
WAIT_FOREVER = 0.0

_LOCK_TIMEOUT_HELP = (
    "Give up after SECONDS if another run holds this model's generation lock, reporting "
    '{"ok":true,"contended":true} instead of building. 0 (the default) waits for the peer; '
    "either way the wait itself is reported on stderr."
)


def add_lock_timeout_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--lock-timeout",
        type=float,
        default=WAIT_FOREVER,
        metavar="SECONDS",
        help=_LOCK_TIMEOUT_HELP,
    )


def deadline_ms(lock_timeout_s: float | None) -> float | None:
    """``deadline_ms`` for :func:`cadgen.coordination.artifact_build`. None means block."""
    timeout = float(lock_timeout_s or 0.0)
    return timeout * 1000.0 if timeout > 0 else None


def lock_wait_notice(logger: CliLogger | None, ref: str) -> Callable[[float], None] | None:
    """A callback that says WHY the process is sitting still, while it still is.

    Repeats on the interval :mod:`cadgen.coordination.lock` applies, so a long wait keeps
    proving it is alive instead of looking wedged."""
    if logger is None:
        return None

    def notice(elapsed_s: float) -> None:
        logger.info(
            f"waiting for another run to finish building {ref} "
            f"({format_elapsed(elapsed_s)} so far)"
        )

    return notice


def contended_payload(
    *,
    source_ref: str,
    cad_ref: str = "",
    package_dir: Path | str | None = None,
    **extra: object,
) -> dict[str, object]:
    """The answer when a peer holds the lock and this run declined to wait for it.

    ``ok`` is true because nothing went wrong -- the model is being built, just not here --
    and ``contended`` is what a caller branches on. Deliberately claims no artifact: the
    peer decides what the package ends up containing.
    """
    payload: dict[str, object] = {
        "ok": True,
        "contended": True,
        "skipped": True,
        "sourceRef": source_ref,
    }
    if cad_ref:
        payload["cadPath"] = cad_ref
    if package_dir is not None:
        from cadgen.render import relative_to_cwd

        payload["packagePath"] = relative_to_cwd(Path(package_dir))
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload
