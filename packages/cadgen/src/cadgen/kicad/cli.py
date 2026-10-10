"""Running ``kicad-cli``, and reading what it reports.

Every run is isolated twice over:

- **its own folder.** ``kicad-cli`` writes beside the files it reads (a
  ``.kicad_prl`` of local settings, a saved board), so cadgen only ever runs it
  on copies staged in a temporary folder, never in a person's project;
- **its own settings.** ``KICAD_CONFIG_HOME`` points at a folder this process
  owns, so a person's KiCad preferences (a colour theme, a library table) can
  change neither a check nor a picture, and a run never writes to them.

Reports are KiCad's JSON (``erc.v1.json``, ``drc.v1.json``), read into
:class:`Finding`s whose positions are already in the board script's
coordinates.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, Sequence

from cadgen.kicad.install import KicadInstall
from cadgen.kicad.phrasing import Finding, FindingItem, summarize

__all__ = ["Finding", "KicadRunError", "erc_findings", "drc_findings", "run_kicad_cli"]

_TIMEOUT_SECONDS = 600
_NOISE = ("Fontconfig error",)

_config_lock = threading.Lock()
_config_home: Path | None = None


class KicadRunError(RuntimeError):
    """``kicad-cli`` failed; the message carries what it said."""


def _private_config() -> Path:
    """This process's KiCad settings folder, made once and removed at exit."""
    global _config_home
    with _config_lock:
        if _config_home is None or not _config_home.is_dir():
            _config_home = Path(tempfile.mkdtemp(prefix="cadgen-kicad-config-"))
            atexit.register(shutil.rmtree, _config_home, True)
        return _config_home


def config_home() -> Path:
    return _private_config()


def _quiet(text: str) -> str:
    return "\n".join(line for line in (text or "").splitlines() if line.strip() and not line.startswith(_NOISE))


def run_kicad_cli(install: KicadInstall, args: Sequence[str], *, cwd: Path, timeout: float = _TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    """Run ``kicad-cli args`` in ``cwd`` with cadgen's isolation. Raises on a failed run."""
    env = dict(os.environ)
    env.update(install.library_env())
    env["KICAD_CONFIG_HOME"] = str(_private_config())
    try:
        completed = subprocess.run(
            [str(install.cli), *args],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise KicadRunError(f"kicad-cli {' '.join(args[:3])} did not finish in {timeout:g} s") from None
    except OSError as error:
        raise KicadRunError(f"kicad-cli could not be started ({error})") from None
    # kicad-cli exits 5 when a check found violations and was asked to say so;
    # cadgen reads the report instead, so any other non-zero exit is a failure.
    if completed.returncode not in (0, 5):
        said = _quiet(completed.stderr) or _quiet(completed.stdout) or f"exit status {completed.returncode}"
        raise KicadRunError(f"kicad-cli {' '.join(args[:3])} failed: {said}")
    return completed


def _items(raw: list, to_script: Callable[[float, float], tuple[float, float]] | None) -> tuple:
    items = []
    for item in raw or []:
        position = item.get("pos")
        point = None
        if isinstance(position, dict) and to_script is not None:
            point = to_script(float(position.get("x", 0.0)), float(position.get("y", 0.0)))
        items.append(FindingItem(text=str(item.get("description", "")), at=point))
    return tuple(items)


def _unique(findings: list[Finding]) -> list[Finding]:
    """Findings in KiCad's order, each once: a through-hole pad's DRC fires per copper layer."""
    return list(dict.fromkeys(findings))


def erc_findings(report: Path) -> list[Finding]:
    """The violations in an ERC report (schematic positions are page positions, kept as is)."""
    data = json.loads(Path(report).read_text())
    found: list[Finding] = []
    for sheet in data.get("sheets", []):
        for violation in sheet.get("violations", []):
            kind = str(violation.get("type", ""))
            description = str(violation.get("description", ""))
            items = _items(violation.get("items", []), None)
            found.append(
                Finding(
                    check="erc",
                    severity=str(violation.get("severity", "error")),
                    type=kind,
                    description=description,
                    items=items,
                    summary=summarize("erc", kind, description, [item.text for item in items]),
                )
            )
    return _unique(found)


def drc_findings(report: Path, *, to_script: Callable[[float, float], tuple[float, float]] | None) -> list[Finding]:
    """Violations, unconnected items and parity issues in a DRC report."""
    data = json.loads(Path(report).read_text())
    found: list[Finding] = []
    for key, check in (("violations", "drc"), ("unconnected_items", "unconnected"), ("schematic_parity", "parity")):
        for violation in data.get(key, []) or []:
            kind = str(violation.get("type", ""))
            description = str(violation.get("description", ""))
            items = _items(violation.get("items", []), to_script)
            found.append(
                Finding(
                    check=check,
                    severity=str(violation.get("severity", "error")),
                    type=kind,
                    description=description,
                    items=items,
                    summary=summarize(check, kind, description, [item.text for item in items]),
                )
            )
    return _unique(found)
