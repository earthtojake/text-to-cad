"""The WebAssembly kernel's folder, made by the engine on first need.

Where a person's settings choose the WebAssembly kernel and name no folder for it, the engine makes one, once, as
it makes the native base: every file the lock shipped with cad names (``kernel_host/lock.json``: Pyodide's core
and one wheel per package, each with its URL and its sha256) is downloaded into the cache and checked against its
sha256, the wheels are unpacked into the folder's ``site-packages``, cad's own host is put beside them
(``python.mjs``, ``bootstrap.py``), and a launcher is written that runs it under the Node found on ``PATH``
(24 or later). Where the lock names the view core (``viewcore``: one archive of its folder as ``make.mjs`` lays it
out, its job server ``hosts/node/serve.mjs`` and its module ``dist/viewcore.wasm``), it is unpacked into ``core/``
and ``bin/viewcore`` runs its job server: the engine's pools and its stills are the view core's then
(``core_pool``, ``render.core``); without it the pools are kernel processes and a still is refused. The folder is ``kernel/<key>`` in the cache, its key a digest of the lock, the host and the Node:
another release's lock makes another folder. It is made beside its place and moved there whole, so one that
exists is complete; a download kept from an earlier try is used again once its sha256 is checked.

A making that cannot finish says why in one line that says what to do (``base.Refused``): no Node, a file that
cannot be fetched, a file that is not the one the lock names.
"""

from __future__ import annotations

import functools
import hashlib
import http.client
import json
import os
import re
import shlex
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
_SERVE = "hosts/node/serve.mjs"  # the view core's job server, in its archive and in ``core/``
# A texture image a slim wheel leaves out: any but a colour map (``color.png``), which a material's colour is read off
# (threejs-materials' ``interpolate_color``, as a part is given one).
_TEXTURES = re.compile(r"(^|/)(?!color\.)[^/]*\.(png|jpe?g|webp|exr|hdr|ktx2?|tiff?)$", re.IGNORECASE)
_BY_HAND = ("or make the folder by hand and name it in the settings (\"kernel\": {\"kind\": \"wasm\", \"folder\": "
            "PATH})")


def lock() -> dict[str, Any]:
    """The lock shipped with cad: what a kernel folder is made of."""
    return json.loads((_HOST / "lock.json").read_text(encoding="utf-8"))


def node() -> str:
    """The Node on ``PATH``, ``NODE`` or later; ``base.Refused`` in one line where there is none. Each Node's version
    is asked of it once a process (``_version``)."""
    found = shutil.which("node")
    if found is None:
        raise base.Refused(f"the WebAssembly kernel runs under Node {NODE} or later, and no node is on PATH: install "
                           "Node (nodejs.org) and ask again", "other")
    said = _version(found)
    major = re.match(r"v(\d+)\.", said)
    if major is None or int(major[1]) < NODE:
        raise base.Refused(f"the WebAssembly kernel runs under Node {NODE} or later, and the node on PATH "
                           f"({found}) is {said or 'one that does not say its version'}: install a newer Node and "
                           "ask again", "other")
    return found


@functools.lru_cache(maxsize=8)
def _version(program: str) -> str:
    """What ``program --version`` says, asked once a process for each Node (a kernel process starts on each)."""
    try:
        return subprocess.run([program, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


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
    """One of the lock's files in ``downloads``, by its sha256: fetched where it is not there, hashed as it comes and
    put in its place only once it is the file the lock names, so a file there is always one that was checked (another
    process's download of it is its own, beside it, until it is checked too)."""
    kept = downloads / item["sha256"]
    if kept.is_file():
        digest = hashlib.sha256()
        with open(kept, "rb") as read:
            for block in iter(lambda: read.read(1 << 20), b""):
                digest.update(block)
        if digest.hexdigest() == item["sha256"]:
            return kept
        kept.unlink(missing_ok=True)  # damaged since: fetched again
    told(f"downloading {item['file']}")
    partial = kept.with_name(f"{kept.name}.part-{os.getpid()}")
    digest, size, expected = hashlib.sha256(), 0, None
    try:
        with urllib.request.urlopen(item["url"], timeout=120) as answer:  # noqa: S310
            length = answer.headers.get("Content-Length")
            expected = int(length) if length and length.isdigit() else None
            try:
                out = open(partial, "wb")
            except OSError as error:
                raise _Disk(error) from None
            with out:
                for block in iter(lambda: answer.read(1 << 20), b""):
                    digest.update(block)
                    size += len(block)
                    try:
                        out.write(block)
                    except OSError as error:
                        raise _Disk(error) from None
    except _Disk as disk:
        partial.unlink(missing_ok=True)
        raise base.Refused(f"the WebAssembly kernel's {item['file']} could not be written to {downloads} "
                           f"({disk.error.strerror or disk.error}): free some room and ask again", "other") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as error:
        partial.unlink(missing_ok=True)
        why = getattr(error, "reason", None) or getattr(error, "strerror", None) or type(error).__name__
        raise base.Refused(f"the WebAssembly kernel's {item['file']} could not be downloaded from "
                           f"{item['url']} ({why}): connect to the network and ask again, {_BY_HAND}",
                           "network") from None
    if expected is not None and size < expected:
        partial.unlink(missing_ok=True)
        raise base.Refused(f"the WebAssembly kernel's {item['file']} stopped downloading from {item['url']} after "
                           f"{size} of {expected} bytes: connect to the network and ask again, {_BY_HAND}", "network")
    if digest.hexdigest() != item["sha256"]:
        partial.unlink(missing_ok=True)
        raise base.Refused(f"the WebAssembly kernel's {item['file']}, downloaded from {item['url']}, is not the file "
                           f"this release of cad names (sha256 {digest.hexdigest()[:16]}..., expected "
                           f"{item['sha256'][:16]}...): ask again to download it afresh, {_BY_HAND}", "other")
    partial.replace(kept)
    return kept


class _Disk(Exception):
    """A download's file that could not be written (a full disk): no failure of the network's."""

    def __init__(self, error: OSError) -> None:
        super().__init__(str(error))
        self.error = error


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


def _swept(folder: Path) -> None:
    """What a making that was killed left in ``folder`` (``<key>.making-<pid>``, ``<sha256>.part-<pid>``), where that
    process is gone."""
    for left in folder.glob("*"):
        found = re.search(r"\.(?:making|part)-(\d+)$", left.name)
        if found is None or _alive(int(found[1])):
            continue
        if left.is_dir():
            shutil.rmtree(left, ignore_errors=True)
        else:
            left.unlink(missing_ok=True)


def _unpacked(wheel: Path, site: Path, slim: bool) -> None:
    """A wheel's files in ``site``; ``slim``: without its texture images but its colour maps (``_TEXTURES``)."""
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
    _swept(downloads)
    _swept(folder.parent)
    viewcore = pinned.get("viewcore")
    told(f"making the WebAssembly CAD kernel, once: {len(pinned['core']) + len(pinned['packages'])} files of "
         f"Pyodide {pinned['pyodide']}" + (", and the view core" if viewcore else ""))
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
        launcher.write_text(f'#!/bin/sh\nCAD_KERNEL_HOME={shlex.quote(str(folder))} exec {shlex.quote(runs)} '
                            f'{shlex.quote(str(folder / "host" / "python.mjs"))} "$@"\n', encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        if viewcore:
            _unpacked(_fetched(viewcore, downloads, told), staged / "core", False)
            if not (staged / "core" / _SERVE).is_file() or not (staged / "core" / "dist" / "viewcore.wasm").is_file():
                raise base.Refused(f"the view core's {viewcore['file']} holds no {_SERVE} and dist/viewcore.wasm: "
                                   f"{_BY_HAND}", "other")
            serve = staged / "bin" / "viewcore"
            serve.write_text(f'#!/bin/sh\nexec {shlex.quote(runs)} {shlex.quote(str(folder / "core" / _SERVE))} "$@"\n',
                             encoding="utf-8")
            serve.chmod(serve.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        (staged / base.WASM_MARKER).write_text(json.dumps({
            "schema": base.WASM_SCHEMA, "pyodide": pinned["pyodide"], "python": pinned["python"],
            "pins": hashlib.sha256(json.dumps(pinned, sort_keys=True).encode()).hexdigest(), "node": runs,
            "deferred": list(pinned.get("deferred") or []), "core": viewcore["sha256"] if viewcore else None}, indent=1)
            + "\n", encoding="utf-8")
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
