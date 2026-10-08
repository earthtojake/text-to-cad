"""The CAD views' features a person can turn off: the feature rows of the app menu (the logo over any
open model), in both CAD apps (the viewer's ``/__cad/features``, which ``cadgen mcp``'s views reach
through its tunnel). Each feature is on until the person turns it off, and their choice is kept as
the ``features`` section of their settings (``cadgen/settings.py``: ``settings.json`` in the state
directory), so it is one choice for every CAD view -- every tab, both apps -- across reloads and
restarts. A feature is named as the page names it (``quickEdit``), and a new one is a line of
``DEFAULTS``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cadgen.settings import read_section, update_section

LOG = logging.getLogger("cadgen.features")

SECTION = "features"  # this module's part of the settings file
# Every feature a person can turn off, and its value until they do.
DEFAULTS: dict[str, bool] = {
    "quickEdit": True,  # Quick Edit: the note to the agent at the viewport's top-right
}


def read(*, path: Path | None = None) -> dict[str, bool]:
    """Every feature, as the person set it or as it starts. A settings file that cannot be read
    now reads as no choice made: every feature at its default."""
    try:
        kept = read_section(SECTION, path=path)
    except OSError:
        LOG.debug("could not read the features in %s", path, exc_info=True)
        kept = {}
    return {name: kept[name] if isinstance(kept.get(name), bool) else default for name, default in DEFAULTS.items()}


def change(choices: Any, *, path: Path | None = None) -> dict[str, bool]:
    """Keep the person's choices (``{feature: on}``) under the settings lock, beside every other
    setting, and answer every feature as it now is. Raises ``ValueError`` for a feature this
    module does not know or a value that is not on or off, and ``OSError`` when the settings cannot
    be written."""
    if not isinstance(choices, dict) or any(name not in DEFAULTS or type(on) is not bool for name, on in choices.items()):
        raise ValueError(f"features are {{name: true|false}} for {', '.join(DEFAULTS)}")
    if choices:
        update_section(SECTION, lambda kept: {**kept, **choices}, path=path)
    return read(path=path)
