"""Fetch the benchmark's sources: each robot's STEP and its maker's URDF, and Menagerie's models.

    python src/fetch.py            # every robot
    python src/fetch.py so101      # one

Everything lands under models/mujoco/ in folders Git ignores (``upstream/``, ``menagerie/``):
nothing fetched is ever committed. A Git source is a sparse, blob-filtered clone checked out at its
pinned commit, so only the named paths are downloaded; a download is checked against its pinned
SHA-256 and refused when the bytes differ (the maker changed the file: update the pin on purpose).
Running it again is cheap: a checkout already at its commit and a file already matching its pin
are left as they are.

The standard library and ``git`` alone: it runs before anything else is installed.
"""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from sources import MENAGERIE, MENAGERIE_REPO, ROBOTS, Download, GitSource

USER_AGENT = "text-to-cad-benchmark-fetch"


def _git(*args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(["git", "-c", "gc.auto=0", "-c", "advice.detachedHead=false", *args], cwd=cwd,
                          capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(f"git {' '.join(args)} failed:\n{done.stderr.strip()}")
    return done.stdout.strip()


def checkout(source: GitSource, folder: Path) -> None:
    """``source``'s paths at its commit in ``folder``: cloned blob-filtered, sparse, no other file fetched."""
    if (folder / ".git").is_dir():
        if _git("rev-parse", "HEAD", cwd=folder) == source.commit:
            _git("sparse-checkout", "set", "--no-cone", *_patterns(source.paths), cwd=folder)
            print(f"  {folder.relative_to(MENAGERIE.parent)}: at {source.commit[:12]}")
            return
    else:
        folder.mkdir(parents=True, exist_ok=True)
        _git("init", "-q", cwd=folder)
        _git("remote", "add", "origin", source.url, cwd=folder)
    _git("config", "core.sparseCheckout", "true", cwd=folder)
    _git("sparse-checkout", "set", "--no-cone", *_patterns(source.paths), cwd=folder)
    print(f"  {folder.relative_to(MENAGERIE.parent)}: fetching {source.url} at {source.commit[:12]}")
    _git("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", source.commit, cwd=folder)
    _git("checkout", "-q", "--force", source.commit, cwd=folder)


def _patterns(paths: tuple[str, ...]) -> list[str]:
    # A folder is every file below it; a file is itself (a name may hold spaces: no globbing on it).
    return [f"/{path}*" if path.endswith("/") else f"/{path}" for path in paths]


def download(source: Download, folder: Path) -> None:
    """The zip ``source`` names, found on its page, checked against its pin and unpacked into ``folder``."""
    folder.mkdir(parents=True, exist_ok=True)
    stamp = folder / ".sha256"
    if stamp.is_file() and stamp.read_text().strip() == source.sha256:
        print(f"  {folder.relative_to(MENAGERIE.parent)}: {source.name} at {source.sha256[:12]}")
        return
    page = _get(source.page).decode("utf-8", "replace")
    links = sorted(set(re.findall(r'href="([^"]*' + re.escape(source.name) + r')"', page)))
    if not links:
        raise SystemExit(f"{source.page} no longer links {source.name}: find it there and update sources.py")
    url = urllib.parse.urljoin(source.page, links[0])
    print(f"  {folder.relative_to(MENAGERIE.parent)}: fetching {url}")
    data = _get(url)
    digest = hashlib.sha256(data).hexdigest()
    if digest != source.sha256:
        raise SystemExit(f"{source.name} is not the pinned file: sha256 {digest}, pinned {source.sha256}. "
                         f"The maker changed it; check what changed, then update the pin in sources.py")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            target = (folder / member.filename).resolve()
            if folder.resolve() not in target.parents and target != folder.resolve():
                raise SystemExit(f"{source.name} names a path outside its folder: {member.filename}")
        archive.extractall(folder)
    stamp.write_text(source.sha256 + "\n")


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def fetch(name: str) -> None:
    robot = ROBOTS[name]
    print(f"{robot.title}:")
    if isinstance(robot.cad, GitSource):
        checkout(robot.cad, robot.folder)
    else:
        download(robot.cad, robot.folder)
    vendor = robot.folder / "vendor"
    if robot.vendor_urdf == robot.cad:
        # The URDF is in the CAD's own checkout: vendor/ is that checkout, by a link.
        if not vendor.exists():
            vendor.symlink_to(".", target_is_directory=True)
    else:
        if vendor.is_symlink():
            vendor.unlink()
        checkout(robot.vendor_urdf, vendor)
    for path in (robot.step_path, robot.vendor_urdf_file):
        if not path.is_file():
            raise SystemExit(f"{path} is missing after the fetch: check the pins in sources.py")


def main(argv: list[str]) -> int:
    if shutil.which("git") is None:
        raise SystemExit("fetch needs git on PATH")
    names = argv or list(ROBOTS)
    unknown = [name for name in names if name not in ROBOTS]
    if unknown:
        raise SystemExit(f"no robot {', '.join(unknown)}: the robots are {', '.join(ROBOTS)}")
    print("MuJoCo Menagerie:")
    paths = tuple(dict.fromkeys(ROBOTS[name].menagerie for name in names))
    checkout(GitSource(MENAGERIE_REPO.url, MENAGERIE_REPO.commit, paths, MENAGERIE_REPO.license), MENAGERIE)
    for name in names:
        fetch(name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
