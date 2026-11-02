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
    said = (f"cad here is {here if known else 'unknown'}, worker {spelled(theirs)}; {SERVER} {server} speaks "
            f"{spelled(ours)}")
    newer = _compared(here, server) if known else -1
    if newer == 0:
        # One release of two contracts: a build of it changed what its worker says (a checkout that moved
        # the protocol and kept its version). Neither update moves either one: one build of both does.
        return f"{said}: both are {server}, but different builds of it: use one build of both"
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
    neither registers nor moves the device's server. ``cad update`` reaches a final release alone: a
    pre-release or a development build is named, with no way that cannot reach it."""
    said = f"update {SERVER} to {release}"
    return said if _preview(release) else f"{said}: run `{COMMAND} update`"


# A release as PEP 440 spells one (its normal forms and their spellings): an epoch, the release, a
# pre-release, a post-release, a development release and a local label, each but the release optional --
# ``0.10.0``, ``0.10.1rc1.dev2``, ``0.10.0.post1``, an installation's ``0.10.0-dev.123``.
_RELEASE = re.compile(
    r"v?(?:(?P<epoch>\d+)!)?(?P<release>\d+(?:\.\d+)*)"
    r"(?:[-_.]?(?P<pre>alpha|beta|preview|pre|rc|a|b|c)[-_.]?(?P<pre_n>\d+)?)?"
    r"(?:-(?P<post_n1>\d+)|[-_.]?(?P<post>post|rev|r)[-_.]?(?P<post_n2>\d+)?)?"
    r"(?:[-_.]?(?P<dev>dev)[-_.]?(?P<dev_n>\d+)?)?"
    r"(?:\+[a-z0-9]+(?:[-_.][a-z0-9]+)*)?")
# The pre-releases in PEP 440's order.
_PRE = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}
_LAST, _FIRST = float("inf"), float("-inf")


def _parsed(release: Any) -> Any:
    found = _RELEASE.fullmatch(release.strip().lower()) if isinstance(release, str) else None
    return found


def _order(release: Any) -> tuple[Any, ...] | None:
    """A release as PEP 440 sorts it (``0.10.0`` before ``0.10.2``; ``0.10.1.dev1`` before
    ``0.10.1rc1.dev2`` before ``0.10.1rc1`` before ``0.10.1`` before ``0.10.1.post1``), or None for
    one that is no release. A local label is not ordered."""
    found = _parsed(release)
    if found is None:
        return None
    numbers = [int(part) for part in found["release"].split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    post = found["post"] is not None or found["post_n1"] is not None
    dev = found["dev"] is not None
    if found["pre"] is not None:
        pre: tuple[Any, ...] = (_PRE[found["pre"]], int(found["pre_n"] or 0))
    else:
        pre = (_FIRST,) if dev and not post else (_LAST,)  # a release's own development builds come first
    return (int(found["epoch"] or 0), tuple(numbers), pre,
            (int(found["post_n1"] or found["post_n2"] or 0),) if post else (_FIRST,),
            (int(found["dev_n"] or 0),) if dev else (_LAST,))


def _preview(release: Any) -> bool:
    """Whether ``release`` is a pre-release or a development build, which ``cad update`` does not reach."""
    found = _parsed(release)
    return found is not None and (found["pre"] is not None or found["dev"] is not None)


def _compared(one: Any, other: Any) -> int:
    """1 when the release ``one`` is newer than ``other``, -1 when older, 0 when they are one release
    or either is none."""
    first, second = _order(one), _order(other)
    if first is None or second is None or first == second:
        return 0
    return 1 if first > second else -1
