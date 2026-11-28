"""The WebAssembly kernel's folder, made by the engine on first need.

Where a person's settings choose the WebAssembly kernel and name no folder for it, the engine makes one, once, as
it makes the native base: every file the lock shipped with cad names (``kernel_host/lock.json``: Pyodide's core
and one wheel per package, each with its URL and its sha256) is downloaded into the cache and checked against its
sha256, the wheels are unpacked into the folder's ``site-packages``, cad's own host is put beside them
(``python.mjs``, ``bootstrap.py``), and a launcher is written that runs it under the Node found on ``PATH``
(24 or later). The folder is ``kernel/<key>`` in the cache, its key a digest of the lock, the host and the Node:
another release's lock makes another folder. It is made beside its place and moved there whole, so one that
exists is complete; a download kept from an earlier try is used again once its sha256 is checked.

A making that cannot finish says why in one line that says what to do (``base.Refused``): no Node, a file that
cannot be fetched, a file that is not the one the lock names.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

from cad_server._internal import base

__all__ = ["NODE", "ensure", "lock", "node"]

#: The Node a kernel folder runs under, by its major version (``python.mjs`` refuses an earlier one).
NODE = 24
_HOST = Path(__file__).with_name("kernel_host")
_TEXTURES = re.compile(r"\.(png|jpe?g|webp|exr|hdr|ktx2?|tiff?)$", re.IGNORECASE)
_BY_HAND = ("or make the folder by hand and name it in the settings (\"kernel\": {\"kind\": \"wasm\", \"folder\": "
            "PATH})")


def lock() -> dict[str, Any]:
    """The lock shipped with cad: what a kernel folder is made of."""
    return json.loads((_HOST / "lock.json").read_text(encoding="utf-8"))


def node() -> str:
    """The Node on ``PATH``, ``NODE`` or later; ``base.Refused`` in one line where there is none."""
    found = shutil.which("node")
    if found is None:
        raise base.Refused(f"the WebAssembly kernel runs under Node {NODE} or later, and no node is on PATH: install "
                           "Node (nodejs.org) and ask again", "other")
    try:
        said = subprocess.run([found, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        said = ""
    major = re.match(r"v(\d+)\.", said)
    if major is None or int(major[1]) < NODE:
        raise base.Refused(f"the WebAssembly kernel runs under Node {NODE} or later, and the node on PATH "
                           f"({found}) is {said or 'one that does not say its version'}: install a newer Node and "
                           "ask again", "other")
    return found


def _key(pinned: dict[str, Any], runs: str) -> str:
    digest = hashlib.sha256(json.dumps(pinned, sort_keys=True).encode())
    for name in ("python.mjs", "bootstrap.py"):
        digest.update((_HOST / name).read_bytes())
    digest.update(runs.encode())
    return digest.hexdigest()[:16]


def where(pinned: dict[str, Any] | None = None, runs: str | None = None) -> Path:
    """The kernel folder's place in the cache, for the lock ``pinned`` under the Node ``runs``."""
    from cad.engine import places

    return places.cache_dir() / "kernel" / _key(pinned or lock(), runs or node())


def _fetched(item: dict[str, Any], downloads: Path, told: Callable[[str], None]) -> Path:
    """One of the lock's files in ``downloads``, by its sha256: fetched where it is not there, and checked."""
    kept = downloads / item["sha256"]
    if not kept.is_file():
        told(f"downloading {item['file']}")
        partial = kept.with_name(f"{kept.name}.part-{os.getpid()}")
        try:
            with urllib.request.urlopen(item["url"], timeout=120) as answer, open(partial, "wb") as out:  # noqa: S310
                shutil.copyfileobj(answer, out)
        except (urllib.error.URLError, OSError, ValueError) as error:
            partial.unlink(missing_ok=True)
            why = getattr(error, "reason", None) or getattr(error, "strerror", None) or error
            raise base.Refused(f"the WebAssembly kernel's {item['file']} could not be downloaded from "
                               f"{item['url']} ({why}): connect to the network and ask again, {_BY_HAND}",
                               "network") from None
        partial.replace(kept)
    digest = hashlib.sha256()
    with open(kept, "rb") as read:
        for block in iter(lambda: read.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != item["sha256"]:
        kept.unlink(missing_ok=True)
        raise base.Refused(f"the WebAssembly kernel's {item['file']}, downloaded from {item['url']}, is not the file "
                           f"this release of cad names (sha256 {digest.hexdigest()[:16]}..., expected "
                           f"{item['sha256'][:16]}...): ask again to download it afresh, {_BY_HAND}", "other")
    return kept


def _unpacked(wheel: Path, site: Path, slim: bool) -> None:
    """A wheel's files in ``site``; ``slim``: without its texture images, which no build reads."""
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            if member.is_dir() or (slim and _TEXTURES.search(member.filename)):
                continue
            target = (site / member.filename).resolve()
            if site.resolve() not in target.parents:
                raise base.Refused(f"{wheel.name} names a file outside the folder it is unpacked in", "other")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as read, open(target, "wb") as out:
                shutil.copyfileobj(read, out)


def _compiled(folder: Path) -> None:
    """Each module's bytecode beside it, written by the kernel's own Python (a start then compiles nothing). A
    folder whose bytecode could not be written still runs: its first imports are the slower."""
    site = next(iter(sorted((folder / "lib").glob("python*/site-packages"))), None)
    if site is None:
        return
    try:
        subprocess.run([str(folder / "bin" / "python"), "-m", "compileall", "-q", str(site)], capture_output=True,
                       timeout=1800, env={**os.environ, "CAD_KERNEL_HOME": str(folder)})
    except (OSError, subprocess.TimeoutExpired):
        pass


def ensure(*, make: bool = True, told: Callable[[str], None] | None = None) -> Path | None:
    """The kernel folder (see the module), made first where it is not and ``make``; None where it is not and
    ``make`` is false. ``base.Refused`` in one line where it cannot be made."""
    pinned = lock()
    try:
        runs = node()
    except base.Refused:
        if not make:
            return None
        raise
    folder = where(pinned, runs)
    if (folder / base.WASM_MARKER).is_file():
        return folder
    if not make:
        return None
    told = told or (lambda line: None)
    from cad.engine import places

    downloads = places.cache_dir() / "kernel" / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    told(f"making the WebAssembly CAD kernel, once: {len(pinned['core']) + len(pinned['packages'])} files of "
         f"Pyodide {pinned['pyodide']}")
    staged = folder.with_name(f"{folder.name}.making-{os.getpid()}")
    shutil.rmtree(staged, ignore_errors=True)
    try:
        (staged / "pyodide").mkdir(parents=True)
        for item in pinned["core"]:
            shutil.copyfile(_fetched(item, downloads, told), staged / "pyodide" / item["file"])
        site = staged / "lib" / f"python{pinned['python']}" / "site-packages"
        site.mkdir(parents=True)
        for item in pinned["packages"]:
            _unpacked(_fetched(item, downloads, told), site, bool(item.get("slim")))
        (staged / "host").mkdir()
        for name in ("python.mjs", "bootstrap.py"):
            shutil.copyfile(_HOST / name, staged / "host" / name)
        (staged / "bin").mkdir()
        launcher = staged / "bin" / "python"
        # The launcher names its own folder as it will stand and the Node it runs.
        launcher.write_text(f'#!/bin/sh\nCAD_KERNEL_HOME="{folder}" exec "{runs}" "{folder / "host" / "python.mjs"}" "$@"\n',
                            encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        (staged / base.WASM_MARKER).write_text(json.dumps({
            "schema": base.WASM_SCHEMA, "pyodide": pinned["pyodide"], "python": pinned["python"],
            "pins": hashlib.sha256(json.dumps(pinned, sort_keys=True).encode()).hexdigest(), "node": runs,
            "deferred": list(pinned.get("deferred") or []), "core": None}, indent=1) + "\n", encoding="utf-8")
        folder.parent.mkdir(parents=True, exist_ok=True)
        try:
            staged.rename(folder)
        except OSError:
            if not (folder / base.WASM_MARKER).is_file():  # another process made it meanwhile: its own is as good
                raise
            return folder
    finally:
        shutil.rmtree(staged, ignore_errors=True)
    told("compiling the kernel's Python modules, once")
    _compiled(folder)
    return folder
