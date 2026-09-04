"""Where a build's advisory progress record lives.

One derivation, imported by BOTH the producer (cadgen) and the reader (the CAD Viewer's
server), so the two cannot disagree about which file to look at.

Records live in the daemon's state directory, not in the store: they describe a
PROCESS (a run in flight), not content, and the store holds only content and the
pointers to it (STORE.md §7). For a build scope ``<key>`` (``cadgen.catalog.build_scope``,
derived from the model path) the files are::

    <state>/progress/<key>.json             the run rewriting the model's outputs
    <state>/progress/<key>.generator.json   a run occupying its generator (an export)

The names are fixed per scope, which is what lets an arbitrary reader find them without
being told anything but the model. The records are advisory: a crashed run leaves its
last write behind, and readers age it out (``cadgen.viewer.build_progress``).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

PROGRESS_SUFFIX = ".json"
GENERATOR_PROGRESS_SUFFIX = ".generator.json"


def state_dir() -> Path:
    """The daemon's state directory: the address, the auth key, and these records.

    Same derivation as ``cadgen.daemon.transport.state_dir`` (which imports this one).
    ``CADGEN_DAEMON_STATE_DIR`` overrides it (tests isolate their records that way);
    otherwise ``tempfile.gettempdir()``, which answers correctly on every platform.
    """
    override = os.environ.get("CADGEN_DAEMON_STATE_DIR", "").strip()
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "cadgen-daemon"


def progress_dir() -> Path:
    return state_dir() / "progress"


def progress_path(scope: str) -> Path:
    """The record describing the most recent run that REWRITES the scope's model."""
    return progress_dir() / f"{scope}{PROGRESS_SUFFIX}"


def generator_progress_path(scope: str) -> Path:
    """The record for a run that occupies the model's generator but rewrites nothing.
    Separate from :func:`progress_path` so it cannot overwrite a live build's."""
    return progress_dir() / f"{scope}{GENERATOR_PROGRESS_SUFFIX}"
