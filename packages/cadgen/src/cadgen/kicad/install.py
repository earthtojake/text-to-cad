"""Where KiCad is: ``kicad-cli``, the libraries it ships, and its simulator.

cadgen never installs KiCad. It finds one, in this order:

1. ``CADGEN_KICAD_CLI``, the full path of a ``kicad-cli`` to use;
2. ``kicad-cli`` on ``PATH``;
3. the places KiCad's own installers put it: ``/Applications/KiCad`` and
   ``~/Applications/KiCad`` on macOS, ``Program Files\\KiCad\\<version>`` on
   Windows, ``/usr/bin`` and ``/usr/local/bin`` on Linux.

The libraries come from KiCad's own variables when they are set
(``KICAD10_SYMBOL_DIR``, ``KICAD10_FOOTPRINT_DIR``, ``KICAD10_3DMODEL_DIR``),
and otherwise from beside the ``kicad-cli`` that was found. A KiCad older
than :data:`KICAD_MAJOR` is refused: cadgen writes that release's file formats
and reads its reports.

Nothing here runs at import; :func:`find_kicad` does the work once per process
for a given ``kicad-cli``.
"""

from __future__ import annotations

import ctypes.util
import functools
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "KICAD_MAJOR",
    "KicadInstall",
    "KicadMissingError",
    "find_kicad",
    "install_hint",
]

#: The KiCad release whose formats cadgen writes and whose reports it reads.
KICAD_MAJOR = 10


class KicadMissingError(RuntimeError):
    """No usable KiCad: none found, or one too old. The message says what to do."""


@dataclass(frozen=True)
class KicadInstall:
    cli: Path
    version: str
    symbol_dir: Path | None
    footprint_dir: Path | None
    model_dir: Path | None
    ngspice: Path | None

    @property
    def major(self) -> int:
        return _major(self.version)

    def library_env(self) -> dict[str, str]:
        """KiCad's library variables, for a ``kicad-cli`` run that resolves 3D models."""
        env = {}
        for name, path in (
            ("SYMBOL_DIR", self.symbol_dir),
            ("FOOTPRINT_DIR", self.footprint_dir),
            ("3DMODEL_DIR", self.model_dir),
        ):
            if path is not None:
                for major in sorted({KICAD_MAJOR, self.major}):
                    env[f"KICAD{major}_{name}"] = str(path)
        return env


def install_hint() -> str:
    """How to get KiCad on this platform, as one sentence a person can act on."""
    if sys.platform == "darwin":
        return (
            "install KiCad 10 (`brew install --cask kicad`, or the disk image from "
            "https://www.kicad.org/download/macos/), or set CADGEN_KICAD_CLI to its kicad-cli"
        )
    if sys.platform.startswith("win"):
        return (
            "install KiCad 10 from https://www.kicad.org/download/windows/, "
            "or set CADGEN_KICAD_CLI to its kicad-cli.exe"
        )
    return (
        "install KiCad 10 (Ubuntu: `sudo add-apt-repository ppa:kicad/kicad-10.0-releases && "
        "sudo apt install kicad`; others: https://www.kicad.org/download/linux/), "
        "or set CADGEN_KICAD_CLI to its kicad-cli"
    )


def _major(version: str) -> int:
    try:
        return int(str(version).strip().split(".")[0])
    except (ValueError, IndexError):
        return 0


def _candidates() -> list[Path]:
    found: list[Path] = []
    explicit = os.environ.get("CADGEN_KICAD_CLI", "").strip()
    if explicit:
        return [Path(explicit).expanduser()]
    on_path = shutil.which("kicad-cli")
    if on_path:
        found.append(Path(on_path))
    if sys.platform == "darwin":
        for root in (Path("/Applications"), Path.home() / "Applications"):
            found.append(root / "KiCad" / "KiCad.app" / "Contents" / "MacOS" / "kicad-cli")
    elif sys.platform.startswith("win"):
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        versions = sorted((program_files / "KiCad").glob("*/bin/kicad-cli.exe"), reverse=True)
        found.extend(versions)
    else:
        found.extend([Path("/usr/bin/kicad-cli"), Path("/usr/local/bin/kicad-cli")])
    return found


def _library_dir(cli: Path, kind: str, major: int) -> Path | None:
    """``kind`` is ``symbols``, ``footprints`` or ``3dmodels``."""
    variable = {"symbols": "SYMBOL_DIR", "footprints": "FOOTPRINT_DIR", "3dmodels": "3DMODEL_DIR"}[kind]
    for name in (f"KICAD{major}_{variable}", f"KICAD{KICAD_MAJOR}_{variable}"):
        value = os.environ.get(name, "").strip()
        if value and Path(value).expanduser().is_dir():
            return Path(value).expanduser().resolve()
    resolved = cli.resolve()
    candidates = [
        resolved.parent.parent / "SharedSupport" / kind,  # macOS app bundle
        resolved.parent.parent / "share" / "kicad" / kind,  # Windows, and a Linux prefix
        Path("/usr/share/kicad") / kind,
        Path("/usr/local/share/kicad") / kind,
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _ngspice(cli: Path) -> Path | None:
    explicit = os.environ.get("CADGEN_NGSPICE", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    resolved = cli.resolve()
    for candidate in (
        resolved.parent.parent / "Frameworks" / "libngspice.0.dylib",  # macOS app bundle
        resolved.parent.parent / "PlugIns" / "sim" / "libngspice.0.dylib",
        resolved.parent / "libngspice-0.dll",  # Windows
    ):
        if candidate.is_file():
            return candidate
    # A bare name (``libngspice.so.0``) is what the system loader resolves.
    found = ctypes.util.find_library("ngspice")
    return Path(found) if found else None


@functools.lru_cache(maxsize=8)
def _probe(cli: str, stamp: tuple[int, int]) -> str | None:
    del stamp  # part of the cache key: a reinstalled kicad-cli is probed again
    try:
        completed = subprocess.run(
            [cli, "version"], capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    version = (completed.stdout or "").strip().splitlines()
    return version[-1].strip() if completed.returncode == 0 and version else None


def find_kicad() -> KicadInstall:
    """The KiCad this process uses, or :class:`KicadMissingError` saying why not."""
    too_old: list[str] = []
    for candidate in _candidates():
        try:
            stat = candidate.stat()
        except OSError:
            continue
        version = _probe(str(candidate), (stat.st_mtime_ns, stat.st_size))
        if version is None:
            continue
        if _major(version) < KICAD_MAJOR:
            too_old.append(f"{candidate} is KiCad {version}")
            continue
        major = _major(version)
        install = KicadInstall(
            cli=candidate,
            version=version,
            symbol_dir=_library_dir(candidate, "symbols", major),
            footprint_dir=_library_dir(candidate, "footprints", major),
            model_dir=_library_dir(candidate, "3dmodels", major),
            ngspice=_ngspice(candidate),
        )
        # The libraries a board reads are its inputs wherever KiCad is installed: a
        # KiCad update that changes a footprint makes the boards using it stale.
        from cadgen._internal.filetrace import claim_inputs

        for folder in (install.symbol_dir, install.footprint_dir):
            if folder is not None:
                claim_inputs(folder)
        return install
    if too_old:
        raise KicadMissingError(
            f"cadgen needs KiCad {KICAD_MAJOR} or newer, but {'; '.join(too_old)}: {install_hint()}"
        )
    raise KicadMissingError(f"KiCad's command line, kicad-cli, was not found: {install_hint()}")
