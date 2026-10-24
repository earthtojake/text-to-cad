#!/usr/bin/env python3
"""What a release uploads to PyPI, and what its GitHub Release attaches: this run's distribution,
checked file by file against what PyPI already holds of the version.

    python3 scripts/release/pypi_release.py --version X.Y.Z --built DIR --upload DIR --released DIR

A file of this run's that PyPI does not hold is copied to ``--upload`` (the PyPI step uploads that
folder, and nothing else) and to ``--released``. A file PyPI already holds -- a resumed release, its
upload done by an earlier run -- is not uploaded again: PyPI's own bytes are downloaded into
``--released`` and checked against the sha256 PyPI lists for them, so the GitHub Release attaches
exactly what PyPI serves, never a rebuild of it. A file PyPI holds of the version that this run did
not build fails the run: what the release would name is then not what it built. Prints
``upload=true|false`` (whether ``--upload`` holds anything) for ``$GITHUB_OUTPUT``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = "cadgen"
INDEX = "https://pypi.org/pypi"
TIMEOUT = 60


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def held(version: str) -> dict[str, dict[str, str]]:
    """The files PyPI holds of ``version``: {filename: {"sha256", "url"}} ({} when it holds none)."""
    try:
        with urllib.request.urlopen(f"{INDEX}/{PROJECT}/{version}/json", timeout=TIMEOUT) as answer:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--version", required=True)
    parser.add_argument("--built", type=Path, required=True)
    parser.add_argument("--upload", type=Path, required=True)
    parser.add_argument("--released", type=Path, required=True)
    options = parser.parse_args(argv)
    built = sorted(path.name for path in options.built.iterdir() if path.is_file())
    if not built:
        raise SystemExit(f"no distribution under {options.built}")
    on_pypi = held(options.version)
    upload, take, foreign = plan(built, on_pypi)
    if foreign:
        raise SystemExit(f"PyPI holds {', '.join(foreign)} of {PROJECT} {options.version}, which this run did not build")
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
