"""A pinned command, ``cad +<version>[@<name>] <verb> ...``: read by the version it names.

A command can name the version it is for (``cad +X``), and the copy of the text that ran it can name where that
copy came from too (``cad +X@codex``). The ``cad`` command (``~/.local/bin/cad``, written by
``cad_server._internal.installations``) reads only that first word: where version X is installed it runs X's own
``cad`` with the whole command line; where it is not, it says so (``not_installed``, exit 3) and does nothing else --
it installs nothing, names no install command and uses no network. It never runs another version for a pin. With no
pin it runs the newest version installed (``none_installed`` where there is none). So the version that reads a pin is
the one it names, and here it is read:

1. ``take``: the pin taken off the command line (``parse``: ``+``, a version -- a digit, then digits, letters,
   ``.``, ``+``, ``_`` or ``-`` -- then, optionally, ``@`` and a name, ``places.CHANNEL``; ``@default`` is none).
   Anything else that starts with ``+`` is refused (``bad_pin``, exit 2).
2. ``check``: the pin names this version (``own``), or it is refused (``other_version``, exit 5): a version never
   runs a command pinned to another. Its ``@name`` is this command's channel from here (``places.set_channel``): a
   label alone, which every request to the engine carries for telemetry (``cad.engine.client``), ``cad run`` hands
   its program, and which turns the update notice off (``cad_server.cli``). Nothing else is decided by it.

The words the ``cad`` command says itself -- a word that is no pin, a version not installed, none installed -- are
this module's (``bad_pin``, ``bad_channel``, ``not_installed``, ``none_installed``): the command's text is made from
them (``installations``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from cad.engine import places

__all__ = ["PIN", "Pin", "bad_channel", "bad_pin", "check", "none_installed", "not_installed", "other_version",
           "own", "parse", "released", "take"]

# The characters of a release's name, as the ``cad`` command tells one (``released``).
RELEASED = re.compile(r"[0-9.abcoprst]+")
# A pin: ``+``, then the version and, after an ``@``, the name, each checked by its own rule (``parse``).
PIN = re.compile(r"\+(?P<version>[^@]*)(?:@(?P<channel>.*))?", re.DOTALL)


@dataclass(frozen=True)
class Pin:
    """A pin as it was read: the ``version`` it names, its ``channel`` (the ``@name``; None for none), and the
    ``word`` it was written as."""

    version: str
    channel: str | None
    word: str


# --- the words ------------------------------------------------------------------------------------------


def bad_pin(word: str) -> str:
    return (f"'{word}' is not a pin: a pin is + and a version (a digit, then digits, letters, '.', '+', '_' or "
            "'-'), then, optionally, @ and a name")


def bad_channel(word: str) -> str:
    return (f"'{word}' names no channel: a name after @ is a lower-case letter or digit, then up to 31 lower-case "
            "letters, digits, '.', '_' or '-'")


def not_installed(version: str) -> str:
    """A pinned version that is not installed on this computer: said by the ``cad`` command, exit 3."""
    return f"text-to-cad {version} is not installed on this computer."


def none_installed() -> str:
    """A command with no pin where no version is installed: said by the ``cad`` command, exit 3."""
    return "text-to-cad is not installed on this computer."


def other_version(mine: str | None, version: str) -> str:
    """A pin read by another version than the one it names (``other_version``)."""
    if mine is None:
        return (f"this cad-server is a source tree that runs as no version, and the command is pinned to text-to-cad "
                f"{version}: run it through the cad command, or name this tree's version in "
                f"{places.INSTALLATION_ENV}")
    return (f"this is text-to-cad {mine}, and the command is pinned to text-to-cad {version}: run it through the "
            f"cad command, which runs {version}")


# --- reading it -----------------------------------------------------------------------------------------


def _failure(words: str, reason: str):
    from cad_server._internal.cli_errors import Failure

    return Failure(words, reason)


def parse(word: str) -> Pin:
    """``word`` as a pin (``+<version>[@<name>]``; ``@default`` names none), or the failure ``bad_pin`` saying why
    it is none."""
    found = PIN.fullmatch(word)
    if found is None or not places.VERSION.fullmatch(found["version"]):
        raise _failure(bad_pin(word), "bad_pin")
    channel = found["channel"]
    if channel is not None and channel != places.DEFAULT_CHANNEL and not places.CHANNEL.fullmatch(channel):
        raise _failure(bad_channel(word), "bad_pin")
    return Pin(found["version"], None if channel in (None, places.DEFAULT_CHANNEL) else channel, word)


def take(argv: Sequence[str]) -> tuple[Pin | None, list[str]]:
    """The pin a command line starts with, taken off it, and the rest: ``(None, argv)`` for one with no pin. A
    first word that starts with ``+`` and is no pin is the failure ``bad_pin``."""
    words = list(argv)
    if words[:1] and words[0].startswith("+"):
        return parse(words[0]), words[1:]
    return None, words


def own() -> str | None:
    """The version this process is: the installed version it belongs to (``places.versioned``), else the one
    its installation registers as (``installations.own_version``: a release's own, a development install's
    name); None for a source tree run as no version."""
    from cad_server._internal.installations import own_version

    return places.versioned() or own_version()


def check(pin: Pin) -> None:
    """``pin`` names this version, or the failure ``other_version``; then its name is this command's channel
    (``places.set_channel``)."""
    mine = own()
    if mine != pin.version:
        raise _failure(other_version(mine, pin.version), "other_version")
    places.set_channel(pin.channel)


def released(version: str) -> bool:
    """Whether ``version`` is a release's name by its characters alone -- digits, ``.``, and the letters of
    ``a``, ``b``, ``rc`` and ``post`` -- as the ``cad`` command's own text tells it (``installations``): one it
    runs with no name told. Any other (a development build's, ``<release>-dev.<stamp>``) is told its name as it runs
    (``places.INSTALLATION_ENV``), which its code cannot know by itself."""
    return RELEASED.fullmatch(version) is not None
