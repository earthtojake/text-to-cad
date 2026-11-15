"""The hosted install script, started by ``cad setup --engine-update`` once the site serves this release's.

``--engine-update`` (``cad_server.cli.setup``) starts this program, detached, never waited on: it waits until the
site's ``install.py`` -- the program the hosted ``install.sh`` and ``install.ps1`` download and run -- names this
release or a later one as its fallback (its ``FALLBACK = "X"`` line), then runs the install script once, and ends.
A release reaches PyPI, the install branches and the version feed before the docs site that serves the script is
deployed; an updater of 0.10.0 to 0.11.10 that reads the feed in that gap runs this release's ``--engine-update``
once, and the script of the release before would not do what this release's does, with nothing to try again. So
the site is asked at once and then after a growing delay (``DELAYS``, about an hour in all); a site that never names the release within that, an address that cannot be read, or a script that cannot
start: nothing is run, and nothing is said (no one reads this program's output). The standard library alone.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence

# The program the hosted install script downloads and runs, whose fallback release says which release it installs.
URL = "https://www.texttocad.dev/install.py"
# The delays between asks of the site, in seconds: growing, about an hour in all, then it gives up.
DELAYS = (15.0, 30.0, 60.0, 120.0, 240.0, 480.0, 600.0, 600.0, 600.0, 600.0)
ASK_SECONDS = 20.0
MOST_BYTES = 1 << 20
FALLBACK = re.compile(r'^FALLBACK = "([0-9][0-9A-Za-z.+_-]*)"[ \t]*$', re.M)


def release(version: str) -> tuple[int, ...] | None:
    """The release numbers ``version`` starts with (``0.11.11`` of ``0.11.11`` and of a development build of it,
    ``0.11.11-dev.<stamp>``), or None for a name that starts with none. A release is always ``X.Y.Z``."""
    found = re.match(r"[0-9]+(?:\.[0-9]+)*", version or "")
    return tuple(int(part) for part in found.group().split(".")) if found else None


def _padded(numbers: tuple[int, ...], size: int) -> tuple[int, ...]:
    return numbers + (0,) * (size - len(numbers))


def serves(url: str, version: str, *, seconds: float = ASK_SECONDS) -> bool:
    """Whether the ``install.py`` at ``url`` names ``version``'s release, or a later one, as its fallback. False for
    one that cannot be read, or names none."""
    wanted = release(version)
    if wanted is None:
        return False
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "cad-engine-update", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(request, timeout=seconds) as answer:
            text = answer.read(MOST_BYTES).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:  # not found, or not yet: its body closed
        error.close()
        return False
    except (OSError, ValueError):
        return False
    found = FALLBACK.search(text)
    named = release(found.group(1)) if found else None
    if named is None:
        return False
    size = max(len(named), len(wanted))
    return _padded(named, size) >= _padded(wanted, size)


def wait(url: str, version: str, *, delays: Sequence[float] = DELAYS,
         sleep: Callable[[float], None] = time.sleep) -> bool:
    """Whether the site at ``url`` serves ``version``'s install script (``serves``): asked at once, then after each of
    ``delays``; False once they are spent."""
    if serves(url, version):
        return True
    for delay in delays:
        sleep(delay)
        if serves(url, version):
            return True
    return False


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m cad_server._internal.install_script VERSION URL -- COMMAND...``: ``COMMAND`` run once the
    ``install.py`` at ``URL`` names ``VERSION`` or later (``wait``); on Windows a ``COMMAND`` of one word is a command
    line, run as it is written. Always 0: no one waits on this program."""
    words = list(sys.argv[1:] if argv is None else argv)
    if len(words) < 4 or words[2] != "--":
        return 0
    version, url, command = words[0], words[1], words[3:]
    try:
        if not wait(url, version):
            return 0
        subprocess.run(command[0] if os.name == "nt" and len(command) == 1 else command, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except (OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
