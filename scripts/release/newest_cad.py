#!/usr/bin/env python3
"""Whether PyPI's newest cad can take what the install command hands it: asked before the docs site, which serves
that command, is deployed to production.

    python3 scripts/release/newest_cad.py

The install command (``scripts/install/``, served as texttocad.dev/install.sh, install.ps1 and install.py) installs
PyPI's newest cad and hands the agent apps to its ``cad plugin install``; on a computer whose cad has no such command
(0.11.12 and 0.11.13, which run the install command themselves) it runs the newest release's instead, outside any
installed tool: ``uv tool run --no-config --managed-python --python 3.14 cad@latest plugin install``
(``HAND_OVER``). Either way PyPI's newest cad must have the command. Served while it has none -- this tree deployed
after the command merged and before the release that carries it -- every install ends in a failure.

So uv is asked for exactly that command with ``--help`` after it (``ASKED``): uv resolves ``cad@latest`` as it does
on a person's computer, so the answer is about what PyPI serves now, never about this tree. A cad with the command
prints the command's help and exits 0; one without it exits 2 (``invalid choice: 'install'``). Neither runs
anything of an install: a command's help does no work, and the question is put in a home folder of its own, made
for it and removed after it, with nothing naming a folder of cad's elsewhere (``private``), so nothing of it could
reach an agent app of the machine it runs on. ``cad --version`` then names the release that answered.

Exit 0 where the newest cad has the command. Exit 1, after what uv and cad said, with one line on stderr saying
why and what to do: where it has none (ship the release that carries it first), and where it could not be asked
(uv is not on PATH, PyPI was not reached, the newest cad does not start). It needs uv and the network.
``deploy-docs.yml`` runs it before a production deploy; ``tests/python/global/test_newest_cad.py`` holds it, with a
stand-in uv.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# The newest release's cad, run by uv outside any installed tool, and what the install command hands it
# (``scripts/install/install.py``: ``hand_over``; ``tests/python/global/test_install_script.py`` holds the two to
# one command).
NEWEST = ("tool", "run", "--no-config", "--managed-python", "--python", "3.14", "cad@latest")
HAND_OVER = (*NEWEST, "plugin", "install")
# What is asked: the command's help, which runs nothing; and which release answered.
ASKED = (*HAND_OVER, "--help")
VERSION = (*NEWEST, "--version")
# How a cad's parser refuses a command it has not (argparse, exit status 2).
NO_COMMAND = "invalid choice: 'install'"
# How long uv may take: a fresh machine downloads Python and cad's dependencies first.
SECONDS = 600
# The variables that name a home folder, each set to the question's own; and the ones that name a folder of cad's
# or of a person's settings elsewhere, which go.
HOMES = ("HOME", "USERPROFILE")
ELSEWHERE = ("XDG_", "CAD_")


def private(environ: dict[str, str], home: Path) -> dict[str, str]:
    """``environ`` for a question put in ``home`` and nowhere else: the home folder ``home`` (on Windows its
    application data too), no variable naming a folder of cad's or of a person's settings elsewhere, and telemetry
    off. PATH, the proxy and uv's own variables stay: uv is found, and reaches PyPI, as it would."""
    found = {key: value for key, value in environ.items() if not key.upper().startswith(ELSEWHERE)}
    found.update({name: str(home) for name in HOMES})
    found.update({"APPDATA": str(home / "AppData" / "Roaming"), "LOCALAPPDATA": str(home / "AppData" / "Local"),
                  "DO_NOT_TRACK": "1"})
    return found


def ask(uv: str, words: tuple[str, ...], environ: dict[str, str]) -> tuple[int, str]:
    """``uv <words>`` run with nothing to read: its exit status (124 where it did not end in ``SECONDS``, 127 where
    it could not start) and everything it printed."""
    try:
        done = subprocess.run([uv, *words], env=environ, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", timeout=SECONDS)
    except subprocess.TimeoutExpired as error:
        said = error.stdout.decode("utf-8", "replace") if isinstance(error.stdout, bytes) else error.stdout or ""
        return 124, said
    except OSError as error:
        return 127, f"{type(error).__name__}: {error}\n"
    return done.returncode, done.stdout


def lacks(code: int, said: str) -> bool:
    """Whether the answer to ``ASKED`` is a cad's own refusal of a command it has not."""
    return code == 2 and NO_COMMAND in said


def verdict(code: int, said: str, release: str) -> str | None:
    """Why the site must not be deployed, by the answer to ``ASKED`` (``code``, ``said``) from the cad that calls
    itself ``release``; None where that cad has the command."""
    if code == 0:
        return None
    asked = "`uv " + " ".join(ASKED) + "`"
    if lacks(code, said):
        return (f"PyPI's newest cad ({release}) has no `cad plugin install`, which this ref's install command hands "
                "the agent apps to: deployed now, every install from the site would fail. Ship the release of cad "
                "that carries the command first (Publish Release deploys the site itself, once PyPI lists it); "
                "nothing is deployed.")
    why = f"no answer in {SECONDS // 60} minutes" if code == 124 else f"exit status {code}; what it said is above"
    return (f"PyPI's newest cad could not be asked whether it has `cad plugin install` ({asked}: {why}), and this "
            "ref's install command hands the agent apps to it: nothing is deployed. Where PyPI or uv's downloads "
            "were not reached, run this again; where the newest cad does not start, ship a release that does first.")


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0]).parse_args(argv)
    uv = shutil.which("uv")
    if uv is None:
        print("error: uv is not on PATH, so PyPI's newest cad could not be asked whether it has `cad plugin "
              "install`: install uv (https://docs.astral.sh/uv/), then run this again.", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="newest-cad-", ignore_cleanup_errors=True) as home:
        environ = private(dict(os.environ), Path(home))
        code, said = ask(uv, ASKED, environ)
        # A cad answered, yes or no: which one (uv has it now, and downloads nothing more).
        answered = code == 0 or lacks(code, said)
        named = re.search(r"(?m)^cad \S+$", ask(uv, VERSION, environ)[1]) if answered else None
    release = named.group() if named else "its release was not read"
    sys.stderr.write(said if said.endswith("\n") or not said else said + "\n")
    problem = verdict(code, said, release)
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 1
    print(f"PyPI's newest cad ({release}) has `cad plugin install`: the install command can hand over to it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
