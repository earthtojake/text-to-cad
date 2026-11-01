#!/usr/bin/env python3
"""What a release uploads to PyPI of one of its distributions, and what its GitHub Release attaches:
this run's files of that project, checked file by file against what PyPI already holds of the version.

    python3 scripts/release/pypi_release.py --project NAME --version X.Y.Z --built DIR --upload DIR --released DIR
    python3 scripts/release/pypi_release.py --project NAME --version X.Y.Z --wait

A release is four projects on PyPI (``PROJECTS``), uploaded in that order, each listed by PyPI's index
before the next goes (``--wait``): the library first, since the server and the alias pin it at their own
release, then the server, the shim and the alias. Of ``--built`` (every file the run built), only
``--project``'s files are this call's: a wheel or sdist whose name is the project's, normalized, then the
version.

A file of this run's that PyPI does not hold is copied to ``--upload`` (the PyPI step uploads that
folder, and nothing else) and to ``--released``. A file PyPI already holds -- a resumed release, its
upload done by an earlier run -- is not uploaded again: PyPI's own bytes are downloaded into
``--released`` and checked against the sha256 PyPI lists for them, so the GitHub Release attaches
exactly what PyPI serves, never a rebuild of it. A file PyPI holds of the version that this run did
not build fails the run: what the release would name is then not what it built. Prints
``upload=true|false`` (whether ``--upload`` holds anything) for ``$GITHUB_OUTPUT``.

``--wait`` asks PyPI's simple index, what uv resolves a pin through, until it lists the version: every
ten seconds, for ten minutes at most.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# The release's projects on PyPI, in the order they go up.
PROJECTS = ("cad", "cad-server", "cad-mcp", "cadgen")
INDEX = "https://pypi.org/pypi"
SIMPLE = "https://pypi.org/simple"
TIMEOUT = 60
WAIT_SECONDS, WAIT_TRIES = 10, 60


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized(project: str) -> str:
    """A project's name as its wheel's and sdist's file names spell it (``cad-server`` is
    ``cad_server``)."""
    return re.sub(r"[-_.]+", "_", project).lower()


def files_of(project: str, version: str, built: list[str]) -> list[str]:
    """The files of ``built`` that are ``project``'s at ``version``: ``<name>-<version>-...whl`` and
    ``<name>-<version>.tar.gz``."""
    stem = f"{normalized(project)}-{version}"
    return sorted(name for name in built if name.startswith((f"{stem}-", f"{stem}.tar.gz")))


def held(project: str, version: str) -> dict[str, dict[str, str]]:
    """The files PyPI holds of ``project`` at ``version``: {filename: {"sha256", "url"}} ({} when it holds none)."""
    try:
        with urllib.request.urlopen(f"{INDEX}/{project}/{version}/json", timeout=TIMEOUT) as answer:
            found = json.load(answer)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {}
        raise
    return {item["filename"]: {"sha256": item["digests"]["sha256"], "url": item["url"]} for item in found.get("urls", [])}


def plan(built: list[str], on_pypi: dict[str, dict[str, str]]) -> tuple[list[str], list[str], list[str]]:
    """(this run's files to upload, files to take from PyPI, files PyPI holds that this run did not build)."""
    upload = sorted(name for name in built if name not in on_pypi)
    take = sorted(name for name in built if name in on_pypi)
    foreign = sorted(name for name in on_pypi if name not in built)
    return upload, take, foreign


def download(url: str, expected: str, destination: Path) -> None:
    """PyPI's file at ``url`` into ``destination``, refused unless its sha256 is ``expected``."""
    temporary = destination.with_name(destination.name + ".part")
    with urllib.request.urlopen(url, timeout=TIMEOUT) as answer, temporary.open("wb") as stream:
        shutil.copyfileobj(answer, stream)
    if sha256(temporary) != expected:
        temporary.unlink()
        raise SystemExit(f"{destination.name}: PyPI's file does not match the sha256 PyPI lists for it")
    temporary.replace(destination)


def listed(project: str, version: str) -> bool:
    """Whether PyPI's simple index lists ``project`` at ``version``."""
    request = urllib.request.Request(f"{SIMPLE}/{project}/", headers={"Accept": "application/vnd.pypi.simple.v1+json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            return version in json.load(answer).get("versions", [])
    except (urllib.error.URLError, ValueError, TimeoutError):
        return False


def wait(project: str, version: str, *, tries: int = WAIT_TRIES, pause: float = WAIT_SECONDS) -> int:
    for attempt in range(tries):
        if listed(project, version):
            print(f"PyPI's index lists {project} {version}.", file=sys.stderr)
            return 0
        if attempt + 1 < tries:
            time.sleep(pause)
    print(f"PyPI's index still does not list {project} {version} {round(tries * pause / 60)} minutes after the upload.",
          file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--project", required=True, choices=PROJECTS)
    parser.add_argument("--version", required=True)
    parser.add_argument("--wait", action="store_true", help="wait until PyPI's index lists the version")
    parser.add_argument("--built", type=Path)
    parser.add_argument("--upload", type=Path)
    parser.add_argument("--released", type=Path)
    options = parser.parse_args(argv)
    if options.wait:
        return wait(options.project, options.version)
    if not (options.built and options.upload and options.released):
        parser.error("--built, --upload and --released go together, without --wait")
    everything = sorted(path.name for path in options.built.iterdir() if path.is_file())
    built = files_of(options.project, options.version, everything)
    if not built:
        raise SystemExit(f"no distribution of {options.project} {options.version} under {options.built}")
    on_pypi = held(options.project, options.version)
    upload, take, foreign = plan(built, on_pypi)
    if foreign:
        raise SystemExit(f"PyPI holds {', '.join(foreign)} of {options.project} {options.version}, "
                         "which this run did not build")
    options.upload.mkdir(parents=True, exist_ok=True)
    options.released.mkdir(parents=True, exist_ok=True)
    for name in upload:
        shutil.copy2(options.built / name, options.upload / name)
        shutil.copy2(options.built / name, options.released / name)
        print(f"{name}: not on PyPI yet, uploaded by this run", file=sys.stderr)
    for name in take:
        download(on_pypi[name]["url"], on_pypi[name]["sha256"], options.released / name)
        rebuilt = "" if sha256(options.built / name) == on_pypi[name]["sha256"] else " (this run's rebuild differs: PyPI's is attached)"
        print(f"{name}: already on PyPI, its bytes checked and attached{rebuilt}", file=sys.stderr)
    print(f"upload={'true' if upload else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
