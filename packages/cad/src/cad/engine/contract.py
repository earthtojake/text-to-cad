"""The worker contract: what a script's worker and the server say to each other, which the library and
the server both state (``CONTRACT``), and the Python a build comes from (``interpreter``).

A model's script names, in each order it sends that starts or reaches a script's worker, the Python it
runs in: its executable, its environment, this library's release and its contract (``interpreter``).
The server builds the script in a warm worker running that Python when its environment is not the
server's own, so the packages of the environment the script was launched from import in the worker
too. A script in a base the server made (``cad run``'s: ``places.HOME``) names none, and is built in the
server's own environment.

The contract is three things, any of which a release may change:

- ``PROTOCOL``, the number of what a worker and the server say to each other: the requests a worker
  answers, the frames it answers in (``worker``, ``frames``) and the reports a build answers with.
  Bumped whenever a release changes any of them.
- The document format the worker writes (``previous.FORMAT``, ``xbf/N``), which the server's own
  kernel processes read.
- The CAD kernel it builds with: OCP's major.minor (``KERNEL``), the one the library pins
  (``cadquery-ocp-novtk``), whose shapes and documents the server's kernel processes read back.

The server refuses an order whose contract is not its own before it starts any worker, in one line
naming which package to update, and to what release (``refusal``): a refusal with a remedy, and no
window in which the newer side answers the older. Equal contracts of different releases build, and the
script then says once which package to update for the other's fixes (``notice``). The library's side is
the cad package in the caller's environment, and no installer is named: the person or the agent has
their own way. The server's side is ``cad-server`` and its one way, ``cad update``: installing it into a
project's environment neither registers nor moves the device's server.
"""

from __future__ import annotations

import re
import sys
from typing import Any

from cad.engine.previous import FORMAT, version
from cad.engine.said import COMMAND, SERVER

__all__ = ["CONTRACT", "KERNEL", "PROTOCOL", "interpreter", "notice", "refusal", "release", "spelled"]

# The number of what a script's worker and the server say to each other. Bumped by a release that
# changes a request a worker answers, a frame it answers in, or the reports a build answers with.
PROTOCOL = 1
# OCP's major.minor: the CAD kernel the library pins (``cadquery-ocp-novtk>=8.0,<8.1``), whose shapes
# and documents cross between a worker and the server's own kernel processes.
KERNEL = "8.0"
# The contract, as an order carries it and the server compares it, key by key.
CONTRACT: dict[str, Any] = {"protocol": PROTOCOL, "format": FORMAT, "kernel": f"OCP {KERNEL}"}


def release() -> str:
    """This library's release: the one declared beside its code (``previous.version``)."""
    return version()


def interpreter() -> dict[str, Any] | None:
    """What an order says of the Python it comes from, so the server builds its script there: the
    executable, its environment (``sys.prefix``), this library's release and its contract. None in a
    base the server made (``places.HOME``: ``cad run``'s, and its own kernel processes'), whose scripts
    the server builds in its own environment, and where Python names no executable of its own."""
    from cad.engine import places

    if places.HOME is not None or not sys.executable:
        return None
    return {"executable": sys.executable, "prefix": sys.prefix, "release": release(), "contract": dict(CONTRACT)}


def spelled(contract: Any) -> str:
    """A contract in words: ``contract 1 (xbf/9, OCP 8.0)``; one that is no contract, said so."""
    if not isinstance(contract, dict) or not all(key in contract for key in CONTRACT):
        return "contract unknown"
    return f"contract {contract['protocol']} ({contract['format']}, {contract['kernel']})"


def refusal(named: Any, *, ours: dict[str, Any] | None = None, server: str | None = None) -> str | None:
    """The one line the server refuses an order with when the contract its caller names
    (``interpreter``'s) is not the server's own (``ours``, by default this library's, of the release
    ``server``): which package to update, and to what release -- the cad package in the caller's
    environment to the server's release, never naming an installer; or ``cad-server`` to the caller's,
    by the server's one way, ``cad update`` (installing it in a project's environment neither registers
    nor moves the device's server). None when they speak one contract, whatever their releases."""
    ours = CONTRACT if ours is None else ours
    server = release() if server is None else server
    named = named if isinstance(named, dict) else {}
    theirs = named.get("contract")
    if isinstance(theirs, dict) and all(theirs.get(key) == value for key, value in ours.items()):
        return None
    here = named.get("release")
    known = isinstance(here, str) and _order(here) is not None
    newer = (_compared(here, server) or _compared_contracts(theirs, ours)) if known else -1
    said = (f"cad here is {here if known else 'unknown'}, worker {spelled(theirs)}; {SERVER} {server} speaks "
            f"{spelled(ours)}")
    if newer > 0:
        return f"{said}: {_server_to(here)}"
    return f"{said}: {_library_to(server)}"


def notice(server: Any, here: str | None = None) -> str | None:
    """The line a run says once when the server that built its script is another release of one
    contract: which side to update, and to what release, for the other's fixes; None for one release,
    or two whose order cannot be told."""
    here = release() if here is None else here
    newer = _compared(here, server) if isinstance(server, str) else 0
    if newer < 0:
        return f"cad here is {here}; {SERVER} is {server}: {_library_to(server)} for its fixes and features"
    if newer > 0:
        return f"cad here is {here}; {SERVER} is {server}: {_server_to(here)}"
    return None


def _library_to(release: str) -> str:
    """The library's side updated: the cad package, said so, so no one reads it as the server's
    ``cad update``, which moves the server and leaves the library behind; no installer named."""
    return f"update the cad package in this environment to {release}"


def _server_to(release: str) -> str:
    """The server's side updated, by its one way: installing ``cad-server`` into a project's environment
    neither registers nor moves the device's server."""
    return f"update {SERVER} to {release}: run `{COMMAND} update`"


# A release's phases in PEP 440's order: a development release first, then the pre-releases, the final
# release (no suffix), and a post-release last.
_PHASES = {"dev": 0, "a": 1, "alpha": 1, "b": 2, "beta": 2, "c": 3, "rc": 3, "pre": 3, "preview": 3, "post": 5}
_FINAL = 4
_RELEASE = re.compile(r"v?(\d+(?:\.\d+)*)(?:[-_.]?([a-z]+)[-_.]?(\d*))?(?:\+.*)?")


def _order(release: str) -> tuple[tuple[int, ...], int, int] | None:
    """A release as it sorts (``0.10.0`` before ``0.10.2``, ``0.10.0rc1`` before ``0.10.0``), or None
    for one that is no release."""
    found = _RELEASE.fullmatch(release.strip().lower()) if isinstance(release, str) else None
    if found is None:
        return None
    numbers = [int(part) for part in found.group(1).split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    phase = _PHASES.get(found.group(2)) if found.group(2) else _FINAL
    if phase is None:
        return None
    return tuple(numbers), phase, int(found.group(3) or 0)


def _compared(one: str, other: str) -> int:
    """1 when the release ``one`` is newer than ``other``, -1 when older, 0 when they are one release
    or either is none."""
    first, second = _order(one), _order(other)
    if first is None or second is None or first == second:
        return 0
    return 1 if first > second else -1


def _compared_contracts(theirs: Any, ours: dict[str, Any]) -> int:
    """Of two releases that do not say which is newer: whose contract is, the protocol first, then the
    format, then the kernel; a contract that is none is the older."""
    def key(contract: Any) -> tuple[int, ...] | None:
        if not isinstance(contract, dict):
            return None
        try:
            return (int(contract["protocol"]), *(int(part) for part in re.findall(r"\d+", str(contract["format"]))),
                    *(int(part) for part in re.findall(r"\d+", str(contract["kernel"]))))
        except (KeyError, TypeError, ValueError):
            return None

    first, second = key(theirs), key(ours)
    if first is None or second is None or first == second:
        return -1 if first is None and second is not None else 0
    return 1 if first > second else -1
