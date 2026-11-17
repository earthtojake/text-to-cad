"""``cad cache dir | prune | clean``: cad's cache, as ``uv cache dir | prune | clean`` treat uv's.

The cache is what cad makes again when it needs it, in its cache folder (``places.cache_dir``: ``CAD_CACHE_DIR``,
else ``~/.cache/cad``): the CAD kernel environment and the environments ``cad run`` makes (``base/``, one per release
and set of integrations, ``cad_server._internal.base``), the engine's bytecode, hulls, MJCF assets, integrations'
homes and kept interference measurements (``OWN``). Data is never in it: the documents the engine keeps there
(``documents/``, which a document's record points at and only that document's deletion removes) stay, as do the
records, Recents and settings in the state folder, and anything else in the folder, which may be another program's.

- ``dir``: the cache folder.
- ``prune``: what this release of cad cannot use: the environments made for another release (their marker names it,
  ``base.marked``), and the release folders of the layout of 0.11.11 and earlier (``<state>/releases/<release>``,
  ``releases.root``) but the one ``installations/current`` names, which those releases' server lines still start.
- ``clean``: all of the cache, and what ``prune`` removes; refused while a server runs, which runs from it.

Neither asks first: each says what it removed, and the disk that freed (``freed``). A folder a process runs from is
kept, and said (``releases.running``). Nothing else of cad deletes a past release's folders or environments.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

DEFAULT_PROG = "cad cache"
COMMANDS = ("dir", "prune", "clean")
# What cad keeps in its cache folder, each made again on demand (the module): ``documents/`` is data, and stays.
OWN = ("base", "pycache", "hulls", "mjcf", "homes", "interference")


def build_parser(prog: str = DEFAULT_PROG):
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog, description="cad's cache: what cad makes again when it needs it (environments, "
                                              "bytecode, meshes it derived). Never your documents or settings.")
    commands = parser.add_subparsers(dest="command", metavar="{" + ",".join(COMMANDS) + "}", required=True)
    commands.add_parser("dir", help="print where cad's cache is", description="Print where cad's cache is.")
    commands.add_parser("prune", help="remove what this release of cad cannot use",
                        description="Remove what this release of cad cannot use: environments made for other "
                                    "releases, and the release folders of 0.11.11 and earlier.")
    commands.add_parser("clean", help="remove all of cad's cache; cad makes it again as it needs it",
                        description="Remove all of cad's cache, and what prune removes; cad makes it again as it needs "
                                    "it. Refused while the cad server runs.")
    return parser


def folder() -> Path:
    """cad's cache folder."""
    from cad.engine.places import cache_dir

    return cache_dir()


def _folders(parent: Path) -> list[Path]:
    """The folders in ``parent`` (no link), by name; none where it cannot be read."""
    try:
        return sorted(Path(entry.path) for entry in os.scandir(parent) if entry.is_dir(follow_symlinks=False))
    except OSError:
        return []


def _inside(path: str, parent: Path) -> bool:
    here = os.path.normcase(os.path.realpath(path))
    return here == os.path.normcase(os.path.realpath(parent)) or here.startswith(
        os.path.normcase(os.path.realpath(parent)).rstrip(os.sep) + os.sep)


def prunable() -> tuple[list[tuple[Path, str]], list[tuple[Path, str]]]:
    """What ``prune`` removes, each with what it is, and what it keeps of that, each with why: the environments made
    for another release, and the release folders of 0.11.11 and earlier but ``installations/current``'s; a folder a
    process runs from kept."""
    from cad.engine.places import current
    from cad.engine.previous import version
    from cad_server._internal import base, releases

    found: list[tuple[Path, str]] = []
    kept: list[tuple[Path, str]] = []
    for env in _folders(base.folder()):
        release = _release(env)
        if release is not None and release != version():
            found.append((env, f"an environment of cad {release}"))
    record = current()
    for old in _folders(releases.root()):
        if record is not None and _inside(record["prefix"], old):
            kept.append((old, "the release 0.11.11 and earlier start (installations/current)"))
        else:
            found.append((old, f"cad {old.name}, of the layout of 0.11.11 and earlier"))
    return _running(found, kept)


def _release(env: Path) -> str | None:
    """The release the environment at ``env`` was made for, as its marker names it; None where none does."""
    from cad_server._internal import base

    marker = base.marked(env)
    inputs = marker.get("inputs") if marker is not None else None
    release = inputs.get("release") if isinstance(inputs, dict) else None
    return release if isinstance(release, str) else None


def _running(found: list[tuple[Path, str]], kept: list[tuple[Path, str]]):
    from cad_server._internal.releases import running

    going = []
    for path, what in found:
        if running(path, asking=os.getpid()):
            kept.append((path, "a process runs from it"))
        else:
            going.append((path, what))
    return going, kept


def freed(paths: Iterable[Path]) -> int:
    """The disk removing ``paths`` frees: each file's blocks, counted once, and only where every link to it is among
    them -- an environment's files are links into uv's own cache, which removing it does not free."""
    seen: dict[tuple, list[int]] = {}
    for path in paths:
        for parent, _folders_here, files in os.walk(path):
            for name in files:
                try:
                    found = os.lstat(os.path.join(parent, name))
                except OSError:
                    continue
                key = (found.st_dev, found.st_ino) if found.st_ino else (parent, name)
                blocks = getattr(found, "st_blocks", None)
                entry = seen.setdefault(key, [found.st_nlink or 1, 0, found.st_size if blocks is None else blocks * 512])
                entry[1] += 1
    return sum(size for links, count, size in seen.values() if count >= links)


def size(count: int) -> str:
    """A size at a glance: ``0 B``, ``8.6 KB``, ``412.0 MB``, ``1.2 GB``."""
    for unit, scale in (("GB", 2**30), ("MB", 2**20), ("KB", 2**10)):
        if count >= scale:
            return f"{count / scale:.1f} {unit}"
    return f"{count} B"


def _say(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _remove(going: list[tuple[Path, str]], kept: list[tuple[Path, str]]) -> int:
    """``going`` removed, each said, and ``kept`` said; then what that freed. 1 where one could not be removed."""
    from cad_server._internal import base

    space, failed, removed = freed(path for path, _what in going), False, 0
    for path, what in going:
        try:
            base._remove(path, what)
        except base.Refused as refused:
            _say(f"kept {path}: {refused}")
            failed = True
            continue
        removed += 1
        _say(f"removed {path} ({what})")
    for path, why in kept:
        _say(f"kept {path}: {why}")
    if failed:  # what stayed frees nothing
        space -= freed(path for path, _what in going if os.path.lexists(path))
    _say(f"{removed} removed, {size(max(0, space))} freed" if removed else "nothing removed")
    return 1 if failed else 0


def _clean() -> int:
    """All of the cache, and what ``prune`` removes, where no server runs (``client.connect``)."""
    from cad.engine import client
    from cad_server._internal import base

    try:
        running = client.connect(start=False)
    except ConnectionError as error:  # a sandbox that refuses the engine's folder: whether one runs is unknown
        sys.stderr.write(f"cad cache clean: {error}\n")
        return 1
    if running is not None:
        running.close()
        sys.stderr.write("cad cache clean: the cad server is running, from cad's cache: run `cad server stop` "
                         "first\n")
        return 1
    root, envs = folder(), base.folder()
    found = [(env, f"an environment of cad {_release(env) or 'no release it names'}") for env in _folders(envs)]
    found += [(root / name, f"cad's {name}") for name in OWN if name != base.BASE and os.path.lexists(root / name)]
    going, kept = _running(found, [])
    pruned, also = prunable()  # its release folders of 0.11.11 and earlier: the environments are all above

    def outside(entries: list[tuple[Path, str]]) -> list[tuple[Path, str]]:
        return [entry for entry in entries if not _inside(str(entry[0]), envs)]

    code = _remove(going + outside(pruned), kept + outside(also))
    with contextlib.suppress(OSError):
        for lock in envs.glob("*.lock"):  # each removed environment's lock beside it
            if not (envs / lock.stem).exists():
                lock.unlink()
        if not any(envs.iterdir()):
            envs.rmdir()
    return code


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    args = build_parser(prog).parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.command == "dir":
        _say(str(folder()))
        return 0
    if args.command == "prune":
        return _remove(*prunable())
    return _clean()


if __name__ == "__main__":
    raise SystemExit(main())
