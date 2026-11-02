"""The language the CAD views read in: the app menu's Language row, in both CAD apps (the viewer's
``/api/v1/settings``, which ``cad-mcp``'s views reach through its tunnel). By default a view infers
it from its context -- the browser's languages, or its host's locale -- and this module keeps only
the person's override: the ``language`` section of their settings (``cad_server/settings.py``:
``settings.json`` in the state directory), so it is one choice for every CAD view -- every tab, both
apps -- across reloads and restarts. Choosing Automatic removes it. A locale is named as the page
names it (``zh-CN``), and a new one is a line of ``LOCALES`` beside its dictionary.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cad_server.settings import read_section, update_section

LOG = logging.getLogger("cad_server.language")

SECTION = "language"  # this module's part of the settings file
# Every locale the views speak, as their dictionaries name them (`@cad/ui/i18n`).
LOCALES: tuple[str, ...] = ("en", "zh-CN", "zh-TW", "ja", "ko")


def read(*, path: Path | None = None) -> dict[str, str | None]:
    """The person's language (``{"locale": "zh-CN"}``), or ``{"locale": None}`` for Automatic. A
    settings file that cannot be read now, or a locale this cadgen does not speak, reads as
    Automatic."""
    try:
        kept = read_section(SECTION, path=path)
    except OSError:
        LOG.debug("could not read the language in %s", path, exc_info=True)
        kept = {}
    locale = kept.get("locale")
    return {"locale": locale if locale in LOCALES else None}


def change(choice: Any, *, path: Path | None = None) -> dict[str, str | None]:
    """Keep the person's language (``{"locale": "<one of LOCALES>"}``) under the state folder's one lock,
    beside every other setting, or forget it (``{"locale": null}``: Automatic), and answer it as it
    now is. Raises ``ValueError`` for anything else, and ``OSError`` when the settings cannot be
    written."""
    if not isinstance(choice, dict) or set(choice) != {"locale"} or (choice["locale"] is not None and choice["locale"] not in LOCALES):
        raise ValueError(f"a language is {{\"locale\": null or one of {', '.join(LOCALES)}}}")
    locale = choice["locale"]
    update_section(SECTION, lambda kept: None if locale is None else {**kept, "locale": locale}, path=path)
    return read(path=path)
