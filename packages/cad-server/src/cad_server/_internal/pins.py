"""A pinned command, ``cad +<version>[@<channel>] <verb> ...``: read by the version it names.

Every command a skill runs pins the skill's release, and a copy a store delivers names its channel too
(``@<channel>``; none is the default channel). The ``cad`` command (``~/.local/bin/cad``, written by
``cad_server._internal.installations``) reads only that first word: it runs that version's own ``cad`` with
the whole command line, installing the version first, through its own release, where it is missing, and never
runs another version for it. So the version that reads a pin is the one it names, and here it is read:

1. ``take``: the pin taken off the command line (``parse``: ``+``, a version -- a digit, then digits, letters,
   ``.``, ``+``, ``_`` or ``-`` -- then, optionally, ``@`` and a channel, ``places.CHANNEL``; ``@default`` is the
   default channel). Anything else that starts with ``+`` is refused (``bad_pin``, exit 2).
2. ``check``: the pin names this version (``own``), or it is refused (``other_version``, exit 5): a version never
   runs a command pinned to another. The channel is this command's from here (``places.set_channel``), which
   every request to the engine carries (``cad.engine.client``) and ``cad run`` hands its program.
3. ``apply``: the version's channel made to run it, for a process that is an installed version
   (``places.versioned``; a process with no version -- a checkout, a test's device, an installation of the layout
   before 0.12 -- moves nothing). The channel's pointer (``pointers``) read, no lock taken: equal, the command
   runs; older than the pin's version, the pin is stale (``stale_pin``, exit 4: the chat's copy of the skill is
   older than the one installed); newer, or the channel's first use, the channel moved (``versions.move``) -- the
   default channel, where the install command has run here (its receipt), by the updater's own sequence
   (``update_default``: the move and the apps step), so the install command's other copies get the matching text,
   whatever the automatic-update switch says -- and then the command runs. A move this shell
   cannot make (a sandbox that will not let it write the state folder) is ``cannot_install_here`` (exit 3).

Help, ``--version`` and a read-only report (``cad doctor --check``) do no work and read no pointer.

The words each refusal says, and its reason, are this module's alone (``stale``, ``not_installed``,
``development``, ``bad_pin``, ``bad_channel``, ``other_version``): the ``cad`` command's own text says the same
words where it says them first (a pin to a version not installed, or older than its channel's; a word that is
no pin), held equal by a test.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from cad.engine import places

__all__ = ["PIN", "Pin", "apply", "bad_channel", "bad_pin", "cannot_move", "check", "development", "not_installed",
           "other_version", "own", "parse", "released", "stale", "take", "update_default"]

# The characters of a release's name, as the ``cad`` command tells one (``released``).
RELEASED = re.compile(r"[0-9.abcoprst]+")
# A pin: ``+``, then the version and, after an ``@``, the channel, each checked by its own rule (``parse``).
PIN = re.compile(r"\+(?P<version>[^@]*)(?:@(?P<channel>.*))?", re.DOTALL)


@dataclass(frozen=True)
class Pin:
    """A pin as it was read: the ``version`` it names, its ``channel`` (None: the default channel), and the
    ``word`` it was written as."""

    version: str
    channel: str | None
    word: str

    @property
    def label(self) -> str:
        """The channel as a message names it: its name, or ``default``."""
        return self.channel or places.DEFAULT_CHANNEL


# --- the words ------------------------------------------------------------------------------------------


def bad_pin(word: str) -> str:
    return (f"'{word}' is not a pin: a pin is + and a version (a digit, then digits, letters, '.', '+', '_' or "
            "'-'), then, for a channel, @ and its name")


def bad_channel(word: str) -> str:
    return (f"'{word}' names no channel: a channel is a lower-case letter or digit, then up to 31 lower-case "
            "letters, digits, '.', '_' or '-'")


def stale(version: str, channel: str | None, now: str) -> str:
    """A pin older than its channel's version (``stale_pin``)."""
    return (f"this command is for text-to-cad {version}, and its channel ({channel or places.DEFAULT_CHANNEL}) is "
            f"on text-to-cad {now} now: read the skill again, or start a new chat")


def not_installed(version: str, why: str, system: str | None = None) -> str:
    """A pinned version missing, which this shell could not install (``cannot_install_here``): the install line
    for this computer (or ``system``, an ``os.name``) to run outside the sandbox."""
    from cad_server._internal.versions import add_command

    return (f"text-to-cad {version} is not installed, and could not be installed from this shell ({why}). Run this "
            f"outside the sandbox, or with its permission, then run the command again: {add_command(version, system)}")


def development(version: str) -> str:
    """A pinned version missing that is no release (a development build's name): no index has it."""
    return (f"text-to-cad {version} is not installed, and it is no release: a development version is installed "
            "from its own checkout alone (scripts/install/dev_install.py)")


def other_version(mine: str | None, version: str) -> str:
    """A pin read by another version than the one it names (``other_version``)."""
    if mine is None:
        return (f"this cad-server is a source tree that runs as no version, and the command is pinned to text-to-cad "
                f"{version}: run it through the cad command, or name this tree's version in "
                f"{places.INSTALLATION_ENV}")
    return (f"this is text-to-cad {mine}, and the command is pinned to text-to-cad {version}: run it through the "
            f"cad command, which runs {version}")


def cannot_move(pin: Pin, why: str) -> str:
    """A pinned version present whose channel this shell cannot move to it (``cannot_install_here``)."""
    return (f"text-to-cad {pin.version} is installed, but this shell cannot move the {pin.label} channel to it "
            f"({why}): run the command again outside the sandbox, or with its permission")


# --- reading it -----------------------------------------------------------------------------------------


def _failure(words: str, reason: str):
    from cad_server._internal.cli_errors import Failure

    return Failure(words, reason)


def parse(word: str) -> Pin:
    """``word`` as a pin (``+<version>[@<channel>]``; ``@default`` is the default channel), or the failure
    ``bad_pin`` saying why it is none."""
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
    """``pin`` names this version, or the failure ``other_version``; then this command is on its channel
    (``places.set_channel``)."""
    mine = own()
    if mine != pin.version:
        raise _failure(other_version(mine, pin.version), "other_version")
    places.set_channel(pin.channel)


# --- the channel moved ----------------------------------------------------------------------------------


def apply(pin: Pin, *, told: Callable[[str], None] | None = None) -> None:
    """The pin's channel made to run this version (see the module): nothing for a process that is no installed
    version of the pin's; else returns when the command may run, and raises the failure it is (``stale_pin``,
    ``cannot_install_here``, ``failed``) when not."""
    from cad_server._internal import pointers, versions

    if places.versioned() != pin.version:
        return
    now = pointers.read(pin.channel)
    if now == pin.version:
        return
    if now is not None and versions.older(pin.version, now):
        raise _failure(stale(pin.version, pin.channel, now), "stale_pin")
    try:
        if pin.channel is None and (places.state_dir() / pointers.RECEIPT).is_file():
            moved = update_default(pin.version, told=told)
        else:
            moved = versions.move(pin.channel, pin.version, told=told)
    except OSError as error:  # the install lock, in a state folder this shell may not write
        raise _failure(cannot_move(pin, f"{error.strerror or error}"), "cannot_install_here") from None
    if moved.kind in ("same", "moved"):
        return
    if moved.kind == "stale":
        raise _failure(stale(pin.version, pin.channel, moved.old or "?"), "stale_pin")
    if moved.kind == "cannot":
        raise _failure(cannot_move(pin, moved.error or "it cannot be done from this shell"), "cannot_install_here")
    raise _failure(f"text-to-cad {pin.version} could not be started for the {pin.label} channel: {moved.error}",
                   "failed")


def update_default(version: str, *, told: Callable[[str], None] | None = None):
    """The default channel updated to ``version`` now, by the updater's own sequence (``cad_server._internal.update``):
    a pin newer than the default channel's version on a device where the install command has run (its receipt),
    whatever the automatic-update switch says -- a pin is an explicit request for its version, and the switch
    governs background updates alone. Run by ``version`` itself (the pinned command's own process, present
    already): the ``cad`` command, the move (``versions.move``), and the apps step, so the install command's other
    copies of the plugin get the matching text too; a store's copy is left alone. Each line is said to ``told``
    (else on stderr); an app that fails is said and fails nothing. What the move did (``versions.Moved``)."""
    import argparse
    import sys

    from cad_server._internal import versions
    from cad_server.cli import setup

    if own() != version or not released(version):
        # Only a version runs its own setup, and a development version's apps step is its checkout's to run
        # (scripts/install/dev_install.py): the channel moved alone.
        return versions.move(None, version, told=told)

    class Said:
        def write(self, text: str) -> None:
            for line in text.splitlines():
                if line.strip():
                    (told or (lambda words: print(f"cad: {words}", file=sys.stderr, flush=True)))(line.rstrip())

        def flush(self) -> None:
            pass

    args = argparse.Namespace(dry_run=False, json=False, only=None, no_telemetry=False, engine_update=False)
    installer = setup.Installer(args, [], 0, "default", [], "cad")
    installer.out = Said()
    moved = installer.update_own()
    if moved is None:  # a source tree that is no version: the move alone
        return versions.move(None, version, told=told)
    return moved


def released(version: str) -> bool:
    """Whether ``version`` is a release's name by its characters alone -- digits, ``.``, and the letters of
    ``a``, ``b``, ``rc`` and ``post`` -- as the ``cad`` command's own text tells it (``installations``): one it
    installs from the index where it is missing, and runs with no name told. Any other (a development build's,
    ``<release>-dev.<stamp>``) is installed only from its own checkout, and told its name as it runs
    (``places.INSTALLATION_ENV``), which its code cannot know by itself."""
    return RELEASED.fullmatch(version) is not None
