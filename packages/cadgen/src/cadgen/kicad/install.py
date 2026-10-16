"""Where ``kicad-cli`` is, and whether it is a KiCad cadgen can drive.

cadgen never installs KiCad. It finds one ``kicad-cli``, in this order:

1. ``CADGEN_KICAD_CLI``, the full path of the ``kicad-cli`` to use;
2. ``PATH``: ``kicad-cli-nightly`` first, then ``kicad-cli``. Ubuntu's nightly
   package puts the nightly's wrapper on ``PATH`` under the first name, so it
   wins over a stable ``kicad-cli`` installed beside it;
3. the places KiCad's own installers put it, which kicad-python knows
   (:func:`cadgen.kipy.server.find_kicad_cli`): the macOS app bundle,
   ``Program Files\\KiCad\\<version>`` on Windows (highest version).

The minimum is :data:`KICAD_MINIMUM`, 10.99: the nightly, the first KiCad whose
``kicad-cli api-server`` runs the API headless (KiCad 10.0's ``kicad-cli`` has no
such command). :func:`check_version` is the one judge of a version; callers ask
it where the version is free -- ``cadgen.pcb`` from the server's own
``get_version()`` once it is up, the DRC door from ``kicad-cli version`` before
an eight-second check. Nothing here runs at import; :func:`find_kicad_cli` runs
nothing at all.

What is found is what a command runs; what the API server runs is :func:`unwrap`
of it. Ubuntu's nightly package puts a shell wrapper on ``PATH`` (``kicad-cli-nightly``
sources ``/usr/share/kicad-nightly/kicad-nightly.env`` for ``LD_LIBRARY_PATH`` and
``KICAD_PATH``, then runs ``/usr/lib/kicad-nightly/bin/kicad-cli`` without ``exec``),
and a signal to that shell stops the shell alone: the server it started lives on,
330 MB resident, until the machine is rebooted. A command that runs to its end
(``version``, ``pcb drc``) is fine through the wrapper; the server, which is
stopped with a signal, is started as the binary in the wrapper's environment.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from cadgen._internal import tool_probe

__all__ = [
    "KICAD_MINIMUM",
    "KicadMissingError",
    "check_version",
    "find_kicad_cli",
    "install_hint",
    "kicad_version",
]

#: The oldest KiCad whose ``kicad-cli`` serves the API headless: ``(major, minor)``.
KICAD_MINIMUM = (10, 99)


class KicadMissingError(RuntimeError):
    """No usable KiCad: none found, or one too old. The message says what to do."""


def install_hint() -> str:
    """How to get a KiCad cadgen can drive on this platform, as one sentence a person can act on."""
    if sys.platform == "darwin":
        return (
            "install the KiCad nightly (the KiCad 11 API) from https://www.kicad.org/download/macos/, "
            "or set CADGEN_KICAD_CLI to its kicad-cli"
        )
    if sys.platform.startswith("win"):
        return (
            "install the KiCad nightly (the KiCad 11 API) from https://www.kicad.org/download/windows/, "
            "or set CADGEN_KICAD_CLI to its kicad-cli.exe"
        )
    return (
        "install the KiCad nightly (Ubuntu: `sudo add-apt-repository ppa:kicad/kicad-dev-nightly && "
        "sudo apt install kicad-nightly kicad-nightly-footprints`; others: "
        "https://www.kicad.org/download/linux/), or set CADGEN_KICAD_CLI to its kicad-cli"
    )


def find_kicad_cli() -> Path:
    """The ``kicad-cli`` this process uses, or :class:`KicadMissingError` saying where it looked.

    Runs nothing: whether what it found is new enough is :func:`check_version`'s
    question, asked once a version is in hand.
    """
    explicit = os.environ.get("CADGEN_KICAD_CLI", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return path
        raise KicadMissingError(f"CADGEN_KICAD_CLI names {path}, which is not a file: {install_hint()}")
    for name in ("kicad-cli-nightly", "kicad-cli"):
        found = shutil.which(name)
        if found:
            return Path(found)
    from cadgen.kipy.server import find_kicad_cli as installer_default

    try:
        return Path(installer_default())
    except FileNotFoundError:
        raise KicadMissingError(
            "KiCad's command line, kicad-cli, was not found (CADGEN_KICAD_CLI is unset, neither "
            f"kicad-cli-nightly nor kicad-cli is on PATH, and KiCad is not in its usual install folder): {install_hint()}"
        ) from None


def unwrap(cli: Path) -> tuple[Path, dict[str, str]]:
    """The program to run for ``cli`` and the environment it needs: ``cli`` itself and
    nothing, unless ``cli`` is a wrapper like Ubuntu's ``kicad-cli-nightly`` -- a shell
    script whose every line sources an environment file (``. FILE``) or runs one program
    on the arguments (``PROGRAM "$@"``), with no ``exec``. Only exactly that shape is
    unwrapped; the environment is the files' ``NAME=VALUE`` lines, ``export`` or not."""
    try:
        text = cli.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("#!"):
            return cli, {}
        program: Path | None = None
        environment: dict[str, str] = {}
        for line in text.splitlines()[1:]:
            words = line.split()
            if not words or words[0].startswith("#"):
                continue
            if words[0] in (".", "source") and len(words) == 2:
                environment.update(_environment_file(Path(words[1])))
            elif len(words) == 2 and words[1] == '"$@"' and program is None:
                program = Path(words[0])
            else:
                return cli, {}
    except (OSError, ValueError):
        return cli, {}
    if program is None or not program.is_file():
        return cli, {}
    return program, environment


def _environment_file(path: Path) -> dict[str, str]:
    variables: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip().removeprefix("export ").strip()
        name, equals, value = line.partition("=")
        if equals and name.isidentifier():
            variables[name] = value.strip().strip("\"'")
    return variables


def kicad_version(cli: Path) -> str | None:
    """What ``kicad-cli version`` reports (``10.99.0``), or ``None`` when it does not run."""
    return tool_probe.version(cli, "version", r"(\d+\.\d+\.\d+)")


def check_version(cli: Path, version: str | None) -> str:
    """``version`` when it is :data:`KICAD_MINIMUM` or newer; else :class:`KicadMissingError`
    naming ``cli``, what it is, and what cadgen needs."""
    if version is not None and tool_probe.version_tuple(version)[:2] >= KICAD_MINIMUM:
        return version
    minimum = ".".join(str(part) for part in KICAD_MINIMUM)
    said = f"is KiCad {version}" if version else "did not answer `kicad-cli version`"
    raise KicadMissingError(
        f"{cli} {said}; cadgen needs KiCad {minimum} (the nightly, whose kicad-cli serves the API "
        f"headless) or newer: {install_hint()}"
    )
