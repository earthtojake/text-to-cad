"""``cad fork LINK [FOLDER]`` -- the files of a shared file, written into a folder of this computer's
(``cad_server.sharing``; the engine's **Sharing**).

LINK is a share's view link (``<origin>/<id>``), its files' link (``<origin>/<id>.zip``), or its id alone, of the share
service ``CAD_SHARE_URL`` names (``https://cad.fun`` by default). This process downloads ``<origin>/<id>.zip``
(``sharing.download``), as ``cad share`` uploads, so an agent app's sandbox sees the connection and its network rules
apply; the server is never asked. Its files go into FOLDER (``./<its name>`` by default: the folder the zip holds),
which is refused where it is there and holds anything, and every entry is refused that would land outside it (an
absolute path, a ``..``, a drive, a link: ``sharing.zip_entries``); they are written beside it first and moved in once
all are whole, so a refused or broken zip leaves nothing (``sharing.unpack``). A model's ``.xbf`` is among them, so the
model is there at once, read as any ``.xbf`` is, with nothing run. It keeps a record of the fork (``sharing.fork_record``:
the link, the folder and the shared file in it, ``sharing.shared_file``), asked of the running server as ``cad share``
keeps its records, so that the share's link names that file here wherever cad takes a document (``sharing.copy_of``).
It says what it wrote, the file it is of and the script that builds it, and where what built it (``Cad-Share-Made``)
differs from this computer's cad and libraries, which a build here records (``_here``). It runs nothing, and adds no
project and no file to the library: the next steps it prints are ``cad viewer FOLDER/<file>``, which shows it as it
was shared, and, of a model, ``cad run FOLDER/<script>``, which builds it here, since someone else's code is the
person's to run. ``--json`` answers in one object.

A share this computer made (``sharing.made_here``: a live record of that origin and id, whose file is still where it
was shared from) is downloaded by no one: the command writes nothing, FOLDER included, and says where its files are --
the file, and a model's root and the script among its files -- which is where to work on them (``_local``).
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DEFAULT_PROG = "cad fork"
DESCRIPTION = (
    "Write the files of a shared file into a folder: a model's .xbf, its script, the modules of its project and the "
    "files it reads, at their paths there; a file document's file. LINK is the share's link (https://cad.fun/<id>), "
    "its files' link (<link>.zip) or its id. It runs nothing: it says what it wrote and where what built it differs "
    "from this computer's cad and libraries, then the commands that show it and build it, for the person to run. It "
    "keeps a record of the fork, so the share's link names the shared file here wherever cad takes a document. A "
    "share this computer made is not downloaded: it says where its files are, to work on them there, and writes "
    "nothing.")
# How long this computer's CAD kernel environment may take to say its libraries.
VERSIONS_SECONDS = 60.0
# What a build records of its libraries and its Python, asked of the CAD kernel environment's own Python.
_VERSIONS = ("import json; from cad.engine import previous as p; "
             "print(json.dumps({**p._libraries(), 'python': p._platform()['python']}))")


def build_parser(prog: str = DEFAULT_PROG):
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog=prog, description=DESCRIPTION)
    parser.add_argument("link", metavar="LINK", help="the share's link, its files' link (.zip), or its id")
    parser.add_argument("folder", nargs="?", metavar="FOLDER",
                        help="where its files go: a folder not there yet, or an empty one (default: ./<its name>); "
                             "not used for a share this computer made")
    parser.add_argument("--json", action="store_true", help="answer in one JSON object")
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad_server._internal.cli_errors import Failure, classify, write

    args = build_parser(prog).parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        return _fork(args.link, args.folder, as_json=args.json, prog=prog)
    except Failure as failure:
        return write(classify(failure), prog=prog, as_json=args.json)
    except Exception as error:
        # A crash of cad's own: the dispatcher's to report, as every command's (``cad_server.cli``): under --json
        # ``internal_error``, else its traceback the person's.
        if not args.json:
            raise
        from cad_server.cli import _report

        _report(error)
        return write(Failure(f"{type(error).__name__}: {error}", "internal_error"), prog=prog, as_json=True)


def _refused_folder(folder: Path) -> None:
    """The failure of a FOLDER that is not one a fork writes into: a file, or a folder that holds anything."""
    from cad_server._internal.cli_errors import Failure

    if folder.is_dir():
        if any(folder.iterdir()):
            raise Failure(f"{folder} holds files already: fork into a new folder, or an empty one", "invalid_argument")
    elif os.path.lexists(folder):
        raise Failure(f"{folder} is a file: fork into a new folder, or an empty one", "invalid_argument")


def _fork(link: str, given: str | None, *, as_json: bool, prog: str) -> int:
    import zipfile

    from cad_server import sharing
    from cad_server._internal.api import share_url
    from cad_server._internal.cli_errors import Failure

    service = share_url()
    found = sharing.fork_link(link, service)
    if found is None:
        # Not said back: a mistyped link may still hold a share's id or secret.
        raise Failure("that is no share's link: a share's link is <origin>/<id>, its files' <origin>/<id>.zip, and "
                      f"an id alone is one of {service}", "invalid_argument")
    origin, ident = found
    mine = sharing.made_here(origin, ident)
    if mine is not None:
        return _local(mine, given, as_json=as_json)
    if given is not None:
        _refused_folder(Path(given))
    told = threading.Lock()

    def waiting(seconds: float) -> None:
        if told.acquire(blocking=False):
            print(f"{prog}: the share service asks this computer to wait {seconds:.0f} seconds: waiting",
                  file=sys.stderr, flush=True)

    shown = given if given is not None else "its folder"
    with tempfile.TemporaryFile() as archive:
        try:
            said = sharing.download(origin, ident, archive, waiting=waiting)
        except sharing.Refused as refusal:
            if refusal.status == 404:
                raise Failure("This shared model has expired or was deleted.", "not_found") from None
            raise Failure(f"the share service refused {refusal.what} ({refusal.status}): {refusal.error}"
                          + (f"; {refusal.hint}" if refusal.hint else "")) from None
        except sharing.Unreachable as error:
            from cad_server.cli.share import _unreached

            raise Failure(_unreached(origin, error)) from None
        except sharing.Damaged as error:
            raise Failure(f"the share's files did not arrive as a share's zip: {error}") from None
        archive.seek(0)
        try:
            with zipfile.ZipFile(archive) as opened:
                top, entries = sharing.zip_entries(opened)
                shown = given if given is not None else top
                folder = Path(shown)
                if given is None:
                    _refused_folder(folder)
                written = sharing.unpack(opened, entries, folder)
        except (zipfile.BadZipFile, sharing.Damaged) as error:
            raise Failure(f"the share's files did not arrive as a share's zip: {error}") from None
        except OSError as error:
            raise Failure(f"could not write the share's files into {shown}: {error.strerror or error}") from None
    paths = [path for path, _size in written]
    entry = said["entry"] if said["entry"] in paths else None
    shared = sharing.shared_file(folder, paths, entry)
    try:
        sharing.keep(fork=sharing.fork_record(origin, ident, folder, shared))
    except OSError as error:
        print(f"{prog}: warning: this computer could not keep a record of the fork ({error}), so the share's link "
              "names no copy of it here: name its files by their paths", file=sys.stderr, flush=True)
    made, here = said["made"], _here()
    differs = [{"name": name, "made": value, "here": here[name]} for name, value in (made or {}).items()
               if name in here and here[name] is not None and here[name] != value]
    unknown = [name for name in (made or {}) if name in here and here[name] is None]
    step = ([_command("viewer", os.path.join(shown, *shared.split("/")))] if shared is not None else []) \
        + ([_command("run", os.path.join(shown, *entry.split("/")))] if entry is not None else [])
    size = sum(count for _path, count in written)
    if as_json:
        print(json.dumps({"ok": True, "local": False, "folder": os.path.abspath(folder), "name": top,
                          "files": {"count": len(written), "bytes": size, "paths": paths}, "file": shared,
                          "entry": entry, "made": made, "here": here, "differs": differs, "next": step},
                         separators=(",", ":")), flush=True)
        return 0
    from cad_server.cli.share import _size

    print(f"Forked {top} into {shown}: {len(written)} file{'s' if len(written) != 1 else ''}, {_size(size)}"
          + (f"; it is {shared}" if shared is not None else "")
          + (f"; its script is {entry}" if entry is not None else ""), flush=True)
    if made is not None:
        if differs:
            there = ", ".join(f"{row['name']} {row['made']}" for row in differs)
            ours = ", ".join(f"{row['name']} {row['here']}" for row in differs)
            print(f"Made with {there}, where this computer has {ours}: a build here may differ from the shared view")
        elif not unknown:
            print("Made with the cad and libraries this computer has")
        if unknown:
            print(f"Made with {', '.join(name + ' ' + made[name] for name in unknown)}: this computer's CAD kernel "
                  "environment is made with its first build, so those were not compared")
    if entry is not None:
        shows = f"{step[0]} shows it as it was shared; " if shared is not None else ""
        print(f"Nothing was run: the code is someone else's, the person's to read and run. Next: {shows}"
              f"{step[-1]} builds it here", flush=True)
    elif step:
        print(f"Next: {step[0]}", flush=True)
    return 0


def _local(record: dict[str, Any], given: str | None, *, as_json: bool) -> int:
    """A share this computer made, its file where it was shared from (``sharing.made_here``'s ``record``): where its
    files are -- the file, and a model's root and the script among them -- and that nothing was downloaded or written,
    FOLDER (``given``) neither. The next step is the one that builds or shows it there: these files are this
    computer's own."""
    files = record.get("files") or {}
    root, entry, own = files.get("root"), files.get("entry"), record["document"]["path"]
    name = record["document"]["name"]
    script = os.path.join(root, *entry.split("/")) if isinstance(root, str) and isinstance(entry, str) else None
    step = [_command("run", script)] if script is not None else [_command("viewer", own)]
    if as_json:
        print(json.dumps({"ok": True, "local": True, "name": name, "file": own, "root": root, "entry": entry,
                          "ignored": given, "next": step}, separators=(",", ":")), flush=True)
        return 0
    where = f"it is {own}" + (f", its files in {root}, its script {script}" if script is not None else "")
    print(f"{name} was shared from this computer: {where}. Nothing was downloaded"
          + (f", and {given} was not written" if given is not None else "") + "; work there.", flush=True)
    return 0


def _command(verb: str, path: str) -> str:
    """``cad <verb> PATH``, as a person pastes it into this platform's shell."""
    from cad.engine.said import COMMAND

    return f"{COMMAND} {verb} {subprocess.list2cmdline([path]) if os.name == 'nt' else shlex.quote(path)}"


def _here() -> dict[str, str | None]:
    """This computer's cad and libraries, by the names a build's closure records them (``made``'s): this release
    (``cad``), the CAD kernel environment's libraries and Python, asked of its own Python where it is made (each None
    where it is not yet, or does not say), and the system and the architecture."""
    import platform

    from cad.engine import previous

    found: dict[str, str | None] = {"cad": previous.version(), **dict.fromkeys(previous.KEYED_LIBRARIES),
                                    "python": None, "system": platform.system(), "arch": platform.machine()}
    try:
        from cad_server._internal import base

        environment = base.ensure(make=False)
    except Exception:  # noqa: BLE001 - not made, or not to be made here: its libraries are not compared
        return found
    if environment is None:
        return found
    if environment.own:
        told: Any = {**previous._libraries(), "python": platform.python_version()}
    else:
        try:
            done = subprocess.run([environment.python, "-I", "-c", _VERSIONS], stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=VERSIONS_SECONDS)
            told = json.loads(done.stdout.strip().splitlines()[-1]) if done.returncode == 0 else {}
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            told = {}
    for name, value in (told.items() if isinstance(told, dict) else ()):
        if name in found and isinstance(value, str) and name not in ("cad", "system", "arch"):
            found[name] = value
    return found


if __name__ == "__main__":
    raise SystemExit(main())
