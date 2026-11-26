"""``cad cache dir | prune | clean``: cad's cache, as ``uv cache dir | prune | clean`` treat uv's.

The cache is what cad makes again when it needs it, in its cache folder (``places.cache_dir``: ``CAD_CACHE_DIR``,
else ``~/.cache/cad``): the CAD kernel environment and the environments ``cad run`` makes (``base/``, one per release
and set of integrations, ``cad_server._internal.base``), the engine's bytecode, hulls, MJCF assets, integrations'
homes and kept interference measurements (``OWN``), and what the engine derived of each document (``documents/<id>/``:
the file's note and picture, a KiCad board's plots, kept checks, a shared file's view bundle and where its share's
files are). The records, Recents and settings in the state folder stay, and anything else in the folder, which may be
another program's.

- ``dir``: the cache folder.
- ``prune``: what no file and no release of cad needs: the environments made for another release (their marker names
  it, ``base.marked``); the release folders of the layout of 0.11.11 and earlier (``<state>/releases/<release>``,
  ``releases.root``) but the one ``installations/current`` names, which those releases' server lines still start; a
  document's folder whose file is gone (its note names the file, ``library.Notes``), and one whose note names none (a
  note an earlier build wrote) or that has none, once nothing in it has been written for ``UNUSED_DAYS``
  (``documents``); and the meshes kept by the geometry they are of, the least recently used first, past
  ``MESH_BYTES`` (``meshes``).
- ``clean``: all of the cache but the documents' folders (``OWN``), and what ``prune`` removes; refused while a
  server runs, which runs from it.

Neither asks first: each says what it removed, and the disk that freed (``freed``). Neither removes what is in use:
a folder a process runs from is kept, and said (``releases.running``), and so is a document's folder a share of its
file is being made in, whose share holds its lock the while (``sharing.held``), with its view bundle's meshes. Nothing
else of the cache is held open by a running engine (a hull is read whole, and a note, a picture and a kept check are
written whole), so ``prune`` runs beside a server rather than being refused. Nothing else of cad deletes a past
release's folders or environments.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

DEFAULT_PROG = "cad cache"
COMMANDS = ("dir", "prune", "clean")
#: How long a document's folder whose note names no file -- one a build wrote before a note named its file, or one with
#: no note -- goes unwritten before ``prune`` removes it: a month, longer than a share lives (7 days) and than a
#: project is left for a holiday, so what goes is what a person has left behind. Its file may be there still: what the
#: folder held (the file's count and picture, kept checks, a board's plots, a share's view) is made again as the file
#: is next opened, built, checked or shared, and the note it writes then names it.
UNUSED_DAYS = 30
#: The most disk the meshes kept by the geometry they are of may take: each shared file's part meshes in its view
#: bundle (``documents/<id>/view/``, a board's STEP models' bundles in it too) and each part's convex hulls
#: (``hulls/``). A gibibyte is about what the CAD kernel's own environment takes, so the meshes never cost more than the
#: kernel does: room for the part meshes of a dozen large shared assemblies, or the hulls of thousands of parts. Past
#: it the meshes used longest ago (read or written: ``places.used``) go first, each made again when it is next needed
#: -- a part's mesh by the engine in seconds as its file is shared again, its hulls by CoACD in minutes, once.
MESH_BYTES = 2**30
# What cad keeps in its cache folder, each made again on demand (the module): ``documents/`` is its documents', and stays.
OWN = ("base", "pycache", "hulls", "mjcf", "homes", "interference")


def build_parser(prog: str = DEFAULT_PROG):
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog, description="cad's cache: what cad makes again when it needs it (environments, "
                                              "bytecode, meshes it derived). Never your documents or settings.")
    commands = parser.add_subparsers(dest="command", metavar="{" + ",".join(COMMANDS) + "}", required=True)
    commands.add_parser("dir", help="print where cad's cache is", description="Print where cad's cache is.")
    commands.add_parser("prune", help="remove what no file and no release of cad needs",
                        description="Remove what no file and no release of cad needs: environments made for other "
                                    "releases; the release folders of 0.11.11 and earlier; the cache's folder of a "
                                    f"file that is gone, and of a file no note names once unused for {UNUSED_DAYS} "
                                    f"days; and, past {size(MESH_BYTES)}, the meshes cad keeps by geometry (shared "
                                    "files' part meshes, parts' hulls) used longest ago: about what the CAD kernel "
                                    "takes, each made again when next needed. What is in use stays: an environment a "
                                    "process runs from, a file's folder while it is being shared.")
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


def _noted(found: Path) -> str | None:
    """The file whose folder of the cache ``found`` is, as its note names it (``library.Notes``); None where its note
    names none (one an earlier build wrote), names another folder's file, or does not read, or there is no note."""
    from cad.engine.ids import file_id
    from cad_server.engine.library import NOTE, SCHEMA

    try:
        note = json.loads((found / NOTE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    path = note.get("path") if isinstance(note, dict) and note.get("schema") == SCHEMA else None
    if not isinstance(path, str) or not os.path.isabs(path):
        return None
    try:
        return path if file_id(path) == found.name else None
    except (OSError, ValueError):
        return None


def _written(found: Path) -> float:
    """When anything in the folder ``found`` was last written: the newest modification time of it and of every entry
    under it."""
    newest = 0.0
    for parent, folders, files in os.walk(found):
        for name in (os.curdir, *folders, *files):
            with contextlib.suppress(OSError):
                newest = max(newest, os.lstat(os.path.join(parent, name)).st_mtime)
    return newest


def documents(now: float | None = None) -> list[tuple[Path, str]]:
    """The documents' folders ``prune`` removes, each with what it is: one whose file, as its note names it, is gone;
    one whose note names no file, or that has none, nothing in it written for ``UNUSED_DAYS``. A folder whose file is
    there stays, whatever its age."""
    from cad.engine.ids import is_id
    from cad_server.engine.library import DOCUMENTS

    now = time.time() if now is None else now
    found: list[tuple[Path, str]] = []
    for kept in _folders(folder() / DOCUMENTS):
        if not is_id(kept.name):
            continue  # no document's: another program's, or a person's
        path = _noted(kept)
        if path is not None:
            if not os.path.isfile(path):
                found.append((kept, f"what the cache kept of {path}, which is gone"))
        elif now - _written(kept) >= UNUSED_DAYS * 86400:
            found.append((kept, f"what the cache kept of a file no note names, unwritten for {UNUSED_DAYS} days"))
    return found


def _stat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except OSError:
        return None


def _disk(found: os.stat_result) -> int:
    """The disk a file takes: its blocks where the system says them, else its size."""
    blocks = getattr(found, "st_blocks", None)
    return found.st_size if blocks is None else blocks * 512


def meshes(leaving: Iterable[Path] = ()) -> tuple[list[tuple[Path, int]], int]:
    """The meshes ``prune`` removes, each with the disk it takes, the least recently used first, and the disk all the
    meshes take: of the meshes kept by the geometry they are of (``MESH_BYTES``) -- each view bundle's part meshes
    (``parts/<key>/<tessellation>.xbm``, a board's STEP models' bundles' too) and each part's hulls
    (``hulls/<digest>.npz``) -- the ones used longest ago (the later of a mesh's last read and last write:
    ``places.used``) past the cap, once ``leaving`` (documents' folders ``prune`` removes) are gone."""
    from cad_server.engine.library import DOCUMENTS
    from cad_server.sharing import VIEW

    root = folder()
    gone = {os.path.normcase(str(path)) for path in leaving}
    held: list[tuple[float, str, Path, int]] = []

    def hold(path: Path) -> None:
        with contextlib.suppress(OSError):
            found = os.lstat(path)
            held.append((max(found.st_atime, found.st_mtime), str(path), path, _disk(found)))

    for document in _folders(root / DOCUMENTS):
        if os.path.normcase(str(document)) in gone:
            continue
        for parent, _folders_here, files in os.walk(document / VIEW):
            if Path(parent).parent.name == "parts":  # a part's folder, parts/<key>/
                for name in files:
                    if name.endswith(".xbm"):
                        hold(Path(parent) / name)
    with contextlib.suppress(OSError):
        for entry in os.scandir(root / "hulls"):
            if entry.name.endswith(".npz") and entry.is_file(follow_symlinks=False):
                hold(Path(entry.path))
    total = sum(disk for _when, _name, _path, disk in held)
    over, left = [], total
    for _when, _name, path, disk in sorted(held):
        if left <= MESH_BYTES:
            break
        over.append((path, disk))
        left -= disk
    return over, total


def _document_of(path: Path) -> Path | None:
    """The document's folder of the cache that ``path`` is in, or None for a path in none."""
    from cad_server.engine.library import DOCUMENTS

    root = folder() / DOCUMENTS
    try:
        inside = Path(path).relative_to(root)
    except ValueError:
        return None
    return root / inside.parts[0] if len(inside.parts) > 1 else None


def _drop_document(found: Path, what: str) -> None:
    """A document's folder of the cache removed, whole, under the lock a share of its file holds (``sharing.held``):
    ``sharing.Busy`` while a share of it is being made, which keeps it. Its view bundle and where its share's files are
    go with it; the share's link and keys are the library's, so a later share of a file at that path makes the view
    again."""
    from cad_server import sharing
    from cad_server._internal import base

    with sharing.held(found):
        for entry in list(os.scandir(found)):
            if entry.name != sharing.LOCK:
                base._remove(Path(entry.path), what)
    # The lock goes with the folder as it is let go: it holds none of a share's files now.


def _drop_meshes(going: list[tuple[Path, int]]) -> tuple[list[tuple[Path, int]], list[tuple[Path, str]]]:
    """``going``'s meshes removed, a view bundle's under its file's share's lock (``sharing.held``), which keeps those
    of a file being shared: the meshes removed, each with the disk it took, and what was kept, with why."""
    from cad_server import sharing

    removed: list[tuple[Path, int]] = []
    kept: list[tuple[Path, str]] = []
    by_folder: dict[Path | None, list[tuple[Path, int]]] = {}
    for path, disk in going:
        by_folder.setdefault(_document_of(path), []).append((path, disk))

    def drop(meshes_here: list[tuple[Path, int]]) -> None:
        for path, disk in meshes_here:
            try:
                path.unlink()
            except OSError:
                continue  # gone meanwhile, or held open where the system keeps an open file (Windows): it frees nothing
            removed.append((path, disk))
            with contextlib.suppress(OSError):
                path.parent.rmdir()  # its part's folder, where it held no other file

    for document, meshes_here in by_folder.items():
        if document is None:
            drop(meshes_here)
            continue
        try:
            with sharing.held(document):
                drop(meshes_here)
        except sharing.Busy:
            kept.append((document, "a share of its file is being made"))
        except FileNotFoundError:
            continue  # its folder went meanwhile
    return removed, kept


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


def _remove(going: list[tuple[Path, str]], kept: list[tuple[Path, str]],
            over: list[tuple[Path, int]] | None = None) -> int:
    """``going`` removed, each said, then ``over``'s meshes, said in one line, and ``kept`` said; then what that freed.
    A document's folder a share of its file is being made in is kept, and said. 1 where one could not be removed."""
    from cad_server import sharing
    from cad_server._internal import base
    from cad_server.engine.library import DOCUMENTS

    space, failed, removed = freed(path for path, _what in going), False, 0
    for path, what in going:
        try:
            if path.parent == folder() / DOCUMENTS:
                _drop_document(path, what)
            else:
                base._remove(path, what)
        except sharing.Busy:
            kept.append((path, "a share of its file is being made"))
            continue
        except base.Refused as refused:
            _say(f"kept {path}: {refused}")
            failed = True
            continue
        except OSError as error:  # a document's folder this user may not change
            _say(f"kept {path}: {error}")
            failed = True
            continue
        removed += 1
        _say(f"removed {path} ({what})")
    space -= freed(path for path, _what in going if os.path.lexists(path))  # what stayed frees nothing
    if over:
        used = {path: max(found.st_atime, found.st_mtime) for path, found in
                ((path, _stat(path)) for path, _disk in over) if found is not None}
        dropped, held = _drop_meshes(over)
        kept += held
        if dropped:
            disk = sum(taken for _path, taken in dropped)
            removed, space = removed + len(dropped), space + disk
            when = [used[path] for path, _taken in dropped if path in used]
            last = time.strftime("%Y-%m-%d", time.localtime(max(when))) if when else "long ago"
            _say(f"removed {len(dropped)} {'mesh' if len(dropped) == 1 else 'meshes'} last used {last} or before "
                 f"({size(disk)}): the meshes cad keeps by geometry are held to {size(MESH_BYTES)}, the least recently "
                 "used going first")
    for path, why in kept:
        _say(f"kept {path}: {why}")
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
        going, kept = prunable()
        gone = documents()
        return _remove(going + gone, kept, meshes(path for path, _what in gone)[0])
    return _clean()


if __name__ == "__main__":
    raise SystemExit(main())
