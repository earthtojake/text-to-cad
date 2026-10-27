"""Find a user-installed KiCad CLI. Viewing boards requires no KiCad installation."""
from __future__ import annotations
import os
import shutil
import sys
from pathlib import Path
from cadgen._internal import tool_probe

KICAD_MINIMUM = (9, 0)

class KicadMissingError(RuntimeError):
    """No usable KiCad command line."""

def install_hint() -> str:
    return "install KiCad 9 or newer from https://www.kicad.org/download/, or set CADGEN_KICAD_CLI to its kicad-cli"

def find_kicad_cli() -> Path:
    explicit = os.environ.get("CADGEN_KICAD_CLI", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return path
        raise KicadMissingError(f"CADGEN_KICAD_CLI names {path}, which is not a file: {install_hint()}")
    for name in ("kicad-cli", "kicad-cli-nightly"):
        found = shutil.which(name)
        if found:
            return Path(found)
    if sys.platform == "darwin":
        found = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
        if found.is_file():
            return found
    if sys.platform.startswith("win"):
        folder = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "KiCad"
        if folder.is_dir():
            for version in sorted(folder.iterdir(), key=lambda p: tool_probe.version_tuple(p.name), reverse=True):
                found = version / "bin/kicad-cli.exe"
                if found.is_file():
                    return found
    raise KicadMissingError(f"KiCad's kicad-cli was not found: {install_hint()}")

def kicad_version(cli: Path) -> str | None:
    return tool_probe.version(cli, "version", r"(\d+\.\d+\.\d+)")

def check_version(cli: Path, version: str | None) -> str:
    if version is not None and tool_probe.version_tuple(version)[:2] >= KICAD_MINIMUM:
        return version
    raise KicadMissingError(f"{cli} reports {version or 'no version'}; cadgen needs KiCad 9 or newer: {install_hint()}")
