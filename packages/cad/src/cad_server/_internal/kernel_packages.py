"""A script's own packages on the WebAssembly kernel: the pure-Python ones, in a folder of their own.

A program ``cad run`` runs on the WebAssembly kernel (``cad_server.cli.run``) has the kernel folder's packages --
the kernel's binding, build123d, numpy, scipy and what they need -- and no environment of its own to install into:
no package with native code built for another platform runs there. What its ``# /// script`` header or ``--with``
names beyond those is resolved by uv, and each package the kernel folder does not carry is installed, alone, into a
folder in the cache (``kernel-packages/<key>``, keyed by the requirements and the kernel folder's own making),
which the program's path then holds. A package that is not pure Python is refused in one line that names it,
before the program starts; nothing is left of a folder that was not finished.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from cad_server._internal import base

__all__ = ["MARKER", "ensure", "provided"]

MARKER = "packages.json"
_PINNED = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)")


def _name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def provided(kernel: dict[str, Any]) -> dict[str, str]:
    """The packages the kernel folder carries, by normalized name: each one's version."""
    found: dict[str, str] = {}
    for site in sorted((Path(kernel["prefix"]) / "lib").glob("python*/site-packages")):
        for info in site.glob("*.dist-info"):
            name, _, version = info.name[:-len(".dist-info")].rpartition("-")
            if name:
                found[_name(name)] = version
    return found


def _python(kernel: dict[str, Any]) -> str:
    try:
        return str(json.loads((Path(kernel["prefix"]) / base.WASM_MARKER).read_text(encoding="utf-8")).get("python") or "3.14")
    except (OSError, ValueError):
        return "3.14"


def _uv(step: list[str], folder: Path) -> subprocess.CompletedProcess:
    return base._uv(step, folder)


def _said(done: subprocess.CompletedProcess) -> str:
    lines = [line.strip() for line in (done.stderr or "").splitlines() if line.strip()]
    return lines[-1] if lines else f"uv exited {done.returncode}"


def _impure(folder: Path) -> list[str]:
    """The packages installed in ``folder`` that are not pure Python, by name: a wheel says it (its ``WHEEL``:
    ``Root-Is-Purelib``, and a tag for any platform)."""
    found = []
    for info in sorted(folder.glob("*.dist-info")):
        try:
            text = (info / "WHEEL").read_text(encoding="utf-8")
        except OSError:
            text = ""
        tags = re.findall(r"(?mi)^Tag:\s*(\S+)", text)
        pure = re.search(r"(?mi)^Root-Is-Purelib:\s*true", text) is not None and tags and all(
            tag.endswith("-none-any") for tag in tags)
        if not pure:
            found.append(info.name[:-len(".dist-info")].rpartition("-")[0])
    return found


def ensure(kernel: dict[str, Any], requirements: tuple[str, ...], told: Callable[[str], None]) -> Path | None:
    """The folder holding what ``requirements`` name beyond the kernel folder's own packages (see the module),
    made first where it is not; None where they name nothing. ``base.Refused`` in one line where one cannot be
    resolved, or has native code."""
    if not requirements:
        return None
    from cad.engine import places

    carried, python = provided(kernel), _python(kernel)
    key = hashlib.sha256(json.dumps([sorted(requirements), sorted(carried.items()), python]).encode()).hexdigest()[:16]
    folder = places.cache_dir() / "kernel-packages" / key
    if (folder / MARKER).is_file():
        return folder
    uv = base.find_uv()
    staged = folder.with_name(f"{folder.name}.making-{os.getpid()}")
    shutil.rmtree(staged, ignore_errors=True)
    staged.mkdir(parents=True)
    try:
        asked = staged / "requirements.in"
        asked.write_text("".join(f"{line}\n" for line in requirements), encoding="utf-8")
        told("resolving the script's own packages for the WebAssembly kernel: " + ", ".join(requirements))
        resolved = _uv([uv, "pip", "compile", str(asked), "--python-version", python, "--only-binary", ":all:",
                        "--no-header", "--no-annotate", "--quiet"], staged)
        if resolved.returncode:
            raise base.Refused("the script's own packages do not resolve for the WebAssembly kernel, which runs "
                               f"pure-Python packages and its own: {_said(resolved)}", "other")
        pinned = [match.groups() for match in map(_PINNED.match, resolved.stdout.splitlines()) if match]
        wanted = [f"{name}=={version}" for name, version in pinned if _name(name) not in carried]
        asked.unlink()
        if wanted:
            done = _uv([uv, "pip", "install", "--target", str(staged), "--no-deps", "--only-binary", ":all:",
                        "--python-version", python, "--quiet", *wanted], staged)
            if done.returncode:
                raise base.Refused(f"the script's own packages could not be installed: {_said(done)}", "other")
            native = _impure(staged)
            if native:
                raise base.Refused(f"{', '.join(native)} {'has' if len(native) == 1 else 'have'} native code, which "
                                   "the WebAssembly kernel does not run: a script there uses pure-Python packages "
                                   "and the ones the kernel carries (numpy, scipy and the rest)", "other")
        (staged / MARKER).write_text(json.dumps({"requirements": sorted(requirements), "installed": wanted,
                                                 "python": python}, indent=1) + "\n", encoding="utf-8")
        folder.parent.mkdir(parents=True, exist_ok=True)
        try:
            staged.rename(folder)
        except OSError:
            if not (folder / MARKER).is_file():  # another run made it meanwhile: its own is as good
                raise
    finally:
        shutil.rmtree(staged, ignore_errors=True)
    return folder
