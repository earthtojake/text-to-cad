"""Releases of this source tree, as wheels, for the rehearsals of the install command and of cad's updates.

``release``: this source tree's library and its alias ``cad-server`` (which the updaters of 0.10.0 to 0.11.11 install a
release by) as wheels of release ``version`` (the library's ``build123d`` extra naming nothing, and no packaged
runtime: the kernel's install is uv's, and nothing here serves a page). ``forget`` takes what uv kept of such wheels
out of its cache again. Used by ``scripts/test/rehearse-update.py`` and ``scripts/test/real-install.py``, whose private
computers (``scripts/test/real_computer.py``) hold the state folder, flat, as cad keeps it.
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import stat
import tomllib
import zipfile
from pathlib import Path

from tests.python.support.paths import LIBRARY, REPO_ROOT

# Each release's wheels, by distribution: its project, its packages, and what its wheel carries at its root: cad,
# and cad-server, its alias, which the updaters of 0.10.0 to 0.11.11 install a release by.
DISTRIBUTIONS = {"cad": (LIBRARY, ("cad", "cadgen", "cad_server", "cad_mcp"), ("cad-lazy-kernel.pth",)),
                 "cad-server": (REPO_ROOT / "packages" / "aliases" / "cad-server", (), ())}


def _is_junction(path: Path) -> bool:
    """Whether ``path`` is a Windows junction. ``os.path.isjunction`` is new in Python 3.12; on 3.11 the
    entry's reparse tag says it. Nothing else has junctions."""
    if hasattr(os.path, "isjunction"):
        return os.path.isjunction(path)
    if os.name != "nt":
        return False
    try:
        return getattr(os.lstat(path), "st_reparse_tag", 0) == stat.IO_REPARSE_TAG_MOUNT_POINT
    except OSError:
        return False


def wheel(distribution: str, version: str, folder: Path, replace: dict[str, bytes] | None = None) -> Path:
    """This source tree's ``distribution`` as a wheel of release ``version``: its packages and package data
    but the built runtime (``_runtime``: nothing here serves a page), what it carries at its root, its dependencies -- the library pinned at ``version``
    -- and command as ``pyproject.toml`` declares them, and a ``build123d`` extra that names nothing. ``replace``: files
    of its packages, by their path in the wheel, given other bytes in the wheel alone (a variant of the release a
    rehearsal publishes: the source tree is never written)."""
    source, packages, roots = DISTRIBUTIONS[distribution]
    project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    stem = distribution.replace("-", "_")
    info = f"{stem}-{version}.dist-info"
    files: dict[str, bytes] = {name: (source / name).read_bytes() for name in roots}
    for top in packages:
        package = source / "src" / top
        for path in sorted(package.rglob("*")):
            parts = path.relative_to(package).parts
            if (path.is_file() and parts[0] != "_runtime" and "__pycache__" not in parts and path.suffix != ".pyc"
                    and not path.name.startswith(".")):
                files["/".join((top, *parts))] = path.read_bytes()
    for name, data in (replace or {}).items():
        if name.split("/", 1)[0] in packages:
            if name not in files:
                raise FileNotFoundError(f"{distribution} {version} has no {name} to replace")
            files[name] = data
    requirements =[f"cad=={version}" if requirement.startswith("cad==") else requirement
                    for requirement in project["dependencies"]]
    metadata = ["Metadata-Version: 2.4", f"Name: {distribution}", f"Version: {version}",
                f"Requires-Python: {project['requires-python']}",
                *(f"Requires-Dist: {requirement}" for requirement in requirements), "Provides-Extra: build123d"]
    files[f"{info}/METADATA"] = ("\n".join(metadata) + "\n").encode("utf-8")
    files[f"{info}/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: text-to-cad tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    files[f"{info}/entry_points.txt"] = ("[console_scripts]\n" + "".join(
        f"{name} = {target}\n" for name, target in project.get("scripts", {}).items())).encode("utf-8")
    record = [f"{name},sha256={base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()},{len(data)}"
              for name, data in files.items()]
    files[f"{info}/RECORD"] = ("\n".join([*record, f"{info}/RECORD,,"]) + "\n").encode("utf-8")
    out = folder / f"{stem}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return out


def release(version: str, folder: Path, replace: dict[str, bytes] | None = None) -> None:
    """Release ``version`` published to ``folder``: cad's wheel and its alias cad-server's (``replace``: as ``wheel``
    takes it)."""
    for distribution in DISTRIBUTIONS:
        wheel(distribution, version, folder, replace)


def forget(uv_cache: Path, versions: tuple[str, ...]) -> list[str]:
    """This run's wheels taken out of uv's cache: uv keeps each wheel a folder of wheels served it --
    its unpacked archive, and the index entry that names it -- after the folder is gone, about 5 MB a
    wheel. Found by what they are (``<distribution>-<version>.dist-info``, the entries named by the
    version), so nothing else of the cache is touched, and nothing at all where uv lays its cache out
    otherwise."""
    removed: list[str] = []
    root = uv_cache.resolve()
    names = [(distribution.replace("-", "_"), distribution) for distribution in DISTRIBUTIONS]
    for version in versions:
        for stem, _name in names:
            for found in root.glob(f"archive-v*/*/{stem}-{version}.dist-info"):
                shutil.rmtree(found.parent, ignore_errors=True)
                removed.append(str(found.parent))
        for entry in (entry for _stem, name in names for entry in root.glob(f"wheels-v*/index/*/{name}/{version}-*")):
            # A link to the archive (on Windows perhaps a junction: taken out, never followed), or its lock
            # or revision file; a real folder is not one of these, and is left.
            try:
                if entry.is_symlink() or _is_junction(entry):
                    try:
                        entry.unlink()
                    except OSError:
                        os.rmdir(entry)
                elif entry.is_file():
                    entry.unlink()
                else:
                    continue
            except OSError:
                continue
            removed.append(str(entry))
    for folder in (folder for _stem, name in names for folder in root.glob(f"wheels-v*/index/*/{name}")):
        for empty in (folder, folder.parent):
            try:
                empty.rmdir()  # only an empty one: an index another run shares keeps its entries
            except OSError:
                break
    return removed
