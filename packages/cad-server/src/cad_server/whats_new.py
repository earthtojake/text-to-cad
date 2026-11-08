"""What's new: the dialog a CAD view shows once after an update to a release whose notes say what it
brought. The notes are the views' own copy, in their language, shipped in the pages this server serves
(nothing is read from the network); this module keeps which releases' notes the person has seen: the
``whats_new`` section of their settings (``cad_server/settings.py``: ``settings.json`` in the state
directory), ``{"seen": ["0.11"]}``, each release by its minor version, so a dismissal in one view holds
in every view of both apps. ``/api/v1/settings`` answers it with the minor this installation runs
(``release``), and a view shows the notes of the newest release at or before it that is newer than every
one seen (``@cad/ui/whats-new``).

A person who never used an earlier release is shown nothing new. The first time a release finds no
section -- a new device, or settings an earlier release wrote, which had none -- it decides once which it
is, and keeps the answer: a device with an installation of an earlier release on record
(``installations/<version>.json``, 0.10.0's on Windows in the local application data, 0.8's where it left
them), a record naming a release or a development build of one, was updated, ``{"seen": []}``; any other
is a new person's, who has seen everything up to this
release, ``{"seen": ["<this release>"]}``. ``cad setup`` decides it as it sets a release up, before the
update collects the records of the releases before; a view's read decides it where setup never ran.
Settings that cannot be read or written show nothing: a dismissal that could not be kept would ask again
at every view.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from cad_server.settings import update_section

LOG = logging.getLogger("cad_server.whats_new")

SECTION = "whats_new"  # this module's part of the settings file
MINOR = re.compile(r"[0-9]+\.[0-9]+")
_LEADING = re.compile(r"([0-9]+)\.([0-9]+)")


def minor(version: Any) -> str | None:
    """A version's release by its minor (``0.11.2``, ``0.11.0-dev.3``, ``0.11.0rc1``: ``0.11``), or None."""
    found = _LEADING.match(version) if isinstance(version, str) else None
    return f"{int(found[1])}.{int(found[2])}" if found else None


def _order(release: str) -> tuple[int, int]:
    major, second = release.split(".")
    return int(major), int(second)


def running() -> str | None:
    """The minor of the release this installation runs as (``cad.engine.places.installation``: a
    development install's own name, else its release's)."""
    from cad_server.analytics import installation_version

    return minor(installation_version())


def _installed() -> list[str]:
    """The version of every installation on record on this device: this state folder's, 0.10.0's in
    Windows' local application data, and 0.8's where it left them."""
    from cad_server._internal import installations

    found: list[str] = []
    for read in (installations.records, installations.appdata, installations.earlier):
        try:
            found += [record["version"] for record in read()]
        except Exception:  # noqa: BLE001 - a record that cannot be read is no evidence either way
            LOG.debug("could not read the installations of %s", read.__name__, exc_info=True)
    return found


def _release(version: Any) -> str | None:
    """The release an installation on record is of, by its minor: a release's version
    (``installations.RELEASE``) or a development build of one (``<release>-dev.<time>``), as
    ``cad.engine.places.registered`` reads a record. None for any other name, such as a test's own
    installation (``0.0.0+test``), which is no release's."""
    from cad_server._internal.installations import RELEASE

    named = version.split("-dev.", 1)[0] if isinstance(version, str) else ""
    return minor(named) if RELEASE.fullmatch(named) else None


def _seen(value: Any) -> list[str]:
    """The releases a section names as seen: minors only, once each, oldest first."""
    kept = {item for item in value if isinstance(item, str) and MINOR.fullmatch(item)} if isinstance(value, list) else set()
    return sorted(kept, key=_order)


def _decided(kept: dict[str, Any], release: str, installed: Callable[[], Iterable[str]]) -> dict[str, Any]:
    """The section as it stays: a kept one as it is, else the decision a release makes once."""
    if isinstance(kept.get("seen"), list):
        return kept
    updated = any((found := _release(version)) and _order(found) < _order(release) for version in installed())
    return {**kept, "seen": [] if updated else [release]}


def read(*, path: Path | None = None, release: str | None = None,
         installed: Callable[[], Iterable[str]] = _installed) -> dict[str, Any]:
    """The releases whose notes the person has seen, and the one this installation runs
    (``{"seen": ["0.11"], "release": "0.11"}``), decided and kept once where the settings have no
    section yet. Settings that cannot be read or written answer this release seen: nothing shows."""
    release = release or running()
    if release is None:
        return {"seen": [], "release": None}
    try:
        section = update_section(SECTION, lambda kept: _decided(kept, release, installed), path=path) or {}
    except OSError:
        LOG.debug("could not keep what's new in %s", path, exc_info=True)
        return {"seen": [release], "release": release}
    return {"seen": _seen(section.get("seen")), "release": release}


def change(choice: Any, *, path: Path | None = None, release: str | None = None) -> dict[str, Any]:
    """Keep the releases a view says the person has seen (``{"seen": ["0.11"]}``; the ``release`` a
    read answered may ride along and is ignored) beside those kept, under the state folder's one lock --
    a release once seen stays seen, whichever view put back what -- and answer as ``read``. Raises
    ``ValueError`` for anything else, and ``OSError`` when the settings cannot be written."""
    if not isinstance(choice, dict) or "seen" not in choice or not set(choice) <= {"seen", "release"} \
            or not isinstance(choice["seen"], list) or not all(isinstance(item, str) and MINOR.fullmatch(item)
                                                               for item in choice["seen"]):
        raise ValueError('a what\'s new change is {"seen": ["<major>.<minor>", ...]}')
    update_section(SECTION, lambda kept: {**kept, "seen": _seen(_seen(kept.get("seen")) + choice["seen"])}, path=path)
    return read(path=path, release=release)


def settle(*, path: Path | None = None, release: str | None = None) -> None:
    """Decide, once, whether this device was updated or is a new person's (``cad setup``, as it sets a
    release up): never fails what it rides on."""
    try:
        read(path=path, release=release)
    except Exception:  # noqa: BLE001 - what's new never fails the setup it rides on
        LOG.debug("could not settle what's new", exc_info=True)

