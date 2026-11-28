"""``cad share`` -- a file shared for anyone with its link to open in the hosted viewer, and to download the files that
made it, with no sign-in, for 7 days after its last share (``cad_server.sharing``; the engine's **Sharing**).

- ``cad share FILE [--yes]``: FILE a CAD file the viewer opens (a document id the engine names a file by, and a
  share's link the file this computer's copy of it is, are taken too), turned at once into the file's canonical path,
  which the share is of. A model is shared by its ``.xbf``: what goes is its view, the ``.xbf`` itself and the files of the build
  closure it holds -- its script, the modules of its project the build imported and the files it read
  (``sharing.model_sources``) --; a file document's view and the file itself, with a robot description's mesh files
  and a KiCad board's or schematic's project -- its project file, its local libraries, a board's 3D models, a
  schematic's sheets (``sharing.file_sources``). The running
  server writes the view bundle into the file's folder in cad's cache, over the one it wrote there last, from what it
  answers the file's page. This process uploads the files the share lacks, in packs, and commits the share
  (``sharing.send``) -- never the server, so an agent app's sandbox sees the connection and its network rules apply. A
  model whose files are not what its ``.xbf`` was made from -- a file its build read whose bytes are not the ones its
  closure holds the digest of, its script or a module modified after the ``.xbf`` was written (or its last run here, a
  run that takes the ``.xbf`` whole writing nothing) --, or whose script or a module is gone, is refused in a line
  naming the file and ``cad run`` of its script. A script is refused in a line naming the
  ``.xbf`` to share. One ``cad share`` of a file runs at a time: another waits ``LOCK_SECONDS``, saying so, then is
  refused in a line. It prints one line of what travelled, the folder its files go from (``sharing.root_of``: the
  file's project, never the home folder) with each file's path there, a line for what was left out, the view link,
  the files' link, the delete link and the expiry; the first share's refusal says the same folder, paths and files
  left out. The same file shared again from this computer is the same share: the
  link stays, the 7 days start again, and only what changed travels; a file that moved is another file, with a link
  of its own. Where the service refuses its names (403), or the library's entry of the file holds no share there that
  is live, with its keys, it is a new share. A folder is refused: it has no bundle.
- The first share on a computer needs the person's yes: without ``--yes`` it is refused, in lines an agent can
  pass on (what goes -- the code and the files that made it, which anyone with the link can download, and the view --,
  where, who can open it, for how long, how to delete it), naming the same command with ``--yes``, which records the
  agreement. ``cad share off`` refuses every share, ``--yes`` or not, until ``cad share on``.
- ``cad share status``: whether sharing is on, whether this computer agreed, and its live shares with their links.
- ``cad share delete FILE|LINK [--yes]``: the share of a file this computer shared, or the share a link names (a
  delete link, or the view link of a share this computer keeps), deleted from the service, asked first as every
  command that destroys is (``cad_server._internal.consent``); what it kept in the file's folder of cad's cache goes
  with it.

``--json`` answers in one JSON object. Writes of the agreement, the setting, a share in its file's entry of the library
and the cache's folders are the running server's where one answers (``sharing.keep``), as every write of the library
is, else this process's. A share's id and its secrets are said only inside the two links: never in any other line.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import threading
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

DEFAULT_PROG = "cad share"
ACTIONS = ("status", "on", "off", "delete")
DESCRIPTION = (
    "Share a file: anyone with its link opens it in the hosted viewer, and downloads the files that made it (the "
    "link's .zip, which `cad import` writes into a folder), with no sign-in, until 7 days after its last share. "
    "FILE is "
    "a CAD file the viewer opens; a model is shared by its .xbf. What goes is the file, the files "
    "that made it -- a model's script, the modules of its project that it imports and the files it reads, as its .xbf "
    "records them (run it again after an edit); a robot description's mesh files; a KiCad board's or schematic's "
    "project file, local libraries, 3D models and sheets -- and its view: its shapes as meshes with their names, "
    "measurements and joints, a board's layers in 2D (its 3D is a GLB of its own: `cad export BOARD board.glb`, "
    "then share that), a schematic's sheets. Never an installed library, nor a file outside its project (the folder "
    "the viewer has as a project, or its checkout; never the home folder), which it names as it leaves it out; it says "
    "the folder its files go from and each one's path there. Sharing it again keeps the link "
    "and sends only what changed. The first share on a computer needs the person's yes (--yes). `status` says whether "
    "sharing is on and lists this computer's live shares; `on` and `off` turn it on and off; `delete` removes a "
    "share.")
KINDS = {"xbf": "a model", "step": "a STEP", "stl": "an STL", "glb": "a GLB", "threemf": "a 3MF", "3mf": "a 3MF",
         "dxf": "a DXF", "urdf": "a URDF", "srdf": "an SRDF", "kicad_pcb": "a KiCad board",
         "kicad_sch": "a KiCad schematic"}
MESHES = frozenset({"stl", "glb", "threemf", "3mf"})
# What of a KiCad project a share of a board or a schematic holds beside the file itself.
PROJECT = {"kicad_pcb": "its project file, local libraries and 3D models",
           "kicad_sch": "its sheets, project file and local symbol libraries"}
# How long a share waits for another ``cad share`` of the same file to end before it is refused.
LOCK_SECONDS = 60.0


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog=prog, description=DESCRIPTION,
                            usage=f"%(prog)s [-h] FILE [--yes] [--json]\n       {prog} status|on|off [--json]\n"
                                  f"       {prog} delete FILE|LINK [--yes] [--json]")
    parser.add_argument("target", metavar="FILE",
                        help="a CAD file the viewer opens (a model's .xbf; a folder has no bundle to share); or "
                             "status, on, off or delete")
    parser.add_argument("link", nargs="?", metavar="FILE|LINK",
                        help="after delete: the file this computer shared, or a share's delete link")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="share: the person agreed to sharing, kept for this computer; the first share on a "
                             "computer never asks, and without it is refused, saying what goes; delete: delete without "
                             "asking, which a terminal asks and nothing else (an agent, a pipe, --json) runs without it")
    parser.add_argument("--json", action="store_true", help="answer in one JSON object")
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad_server._internal.cli_errors import Failure, classify, write

    words = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser(prog)
    args = parser.parse_args(words)
    if args.target in ACTIONS[:3] and (args.link is not None or args.yes):
        parser.error(f"`{prog} {args.target}` takes no {'argument' if args.link is not None else '--yes'}")
    if args.target == "delete" and args.link is None:
        parser.error("delete names the file this computer shared, or a share's delete link")
    if args.target not in ACTIONS and args.link is not None:
        parser.error(f"unrecognized arguments: {args.link}")
    try:
        if args.target == "status":
            return _status(args.json)
        if args.target in ("on", "off"):
            return _switch(args.target, args.json)
        if args.target == "delete":
            return _delete(args.link, yes=args.yes, as_json=args.json, prog=prog, words=words)
        return _share(args.target, yes=args.yes, as_json=args.json, prog=prog, words=words)
    except (Failure, ConnectionError) as failure:
        # ``ConnectionError``: the engine not reached (none runs, one of another release), said in its one line.
        return write(classify(failure), prog=prog, as_json=args.json)
    except Exception as error:
        # A crash of cad's own: the dispatcher's to report, as every command's (``cad_server.cli``): under --json
        # ``internal_error``, else its traceback the person's.
        if not args.json:
            raise
        from cad_server.cli import _report

        _report(error)
        return write(Failure(f"{type(error).__name__}: {error}", "internal_error"), prog=prog, as_json=True)


# --- share ---------------------------------------------------------------------------------------------------------


def _target(target: str) -> tuple[str, str]:
    """What FILE|ID names, as ``(the file's canonical path, its type's id)``: a share's link this computer's copy of it
    (``engine.cli.linked``), a document id the file the engine names by it (``_located``), else a path read from this
    folder. Refused by the failure contract, as ``cad viewer`` refuses a FILE, where it is no file a share is of: a
    model's script (its ``.xbf`` is, which running it writes), a path that is not there, a folder, a file of no
    document type."""
    import shlex

    from cad.engine.ids import canonical, is_id
    from cad.registry import type_of
    from cad_server._internal.cli_errors import Failure
    from cad_server.engine.cli import linked

    target = str(linked(target))
    script = target.partition("::")[0]
    if script.lower().endswith(".py"):
        raise Failure(f"{target} is a model's script, not a CAD file: share the model's .xbf, which running it writes "
                      f"(`cad run {shlex.quote(script)}`)", "wrong_type")
    path = _located(target) if is_id(target) else os.path.abspath(os.path.join(os.getcwd(),
                                                                                os.path.expanduser(target)))
    if os.path.isdir(path):
        raise Failure(f"{target} is a folder, which has no view bundle: share one of its files", "wrong_type")
    if not os.path.exists(path):
        raise Failure(f"no such file: {target}", "not_found")
    found = type_of(path)
    if found is None or not os.path.isfile(path):
        raise Failure(f"no CAD file at {path}", "wrong_type")
    return canonical(path), found.id


def _located(ident: str) -> str:
    """The file the engine names by the document id ``ident``: a model's ``.xbf`` (the one a live worker's row names,
    else the file the id is of), any other file's path (``inspect``'s ``build`` query, which builds nothing); the
    engine's refusal where the id names nothing."""
    from cad.engine import api
    from cad_server._internal.cli_errors import classify

    try:
        found = api.inspect(ident, query="build", progress=False)
    except (ValueError, RuntimeError, OSError) as error:
        raise classify(error) from None
    told = (found.get("file") or {}).get("path") if isinstance(found, dict) else None
    live = ((found.get("live") or {}).get("source") or {}).get("xbf") if isinstance(found, dict) else None
    return str(told or live or "")


def _goes(kind: str, sources: Any) -> str:
    """What a share of a file of ``kind`` (its type's id) takes of it, in words: its files (``sources``), which
    anyone with the link can download, and its view."""
    count = len(sources.files)
    if kind == "xbf":
        code = count - 1  # the .xbf is one of them
        files = (f"the model's .xbf, its code and the files it reads ({count} files)" if code else
                 "the model's .xbf")
    elif kind in PROJECT and count > 1:
        files = f"the file itself and {PROJECT[kind]} ({count} files)"
    elif count > 1:
        files = f"the file itself with {count - 1} file{'s' if count != 2 else ''} it draws from beside it"
    else:
        files = "the file itself"
    view = ("its shapes as meshes, with their names, measurements and joints" if kind in ("xbf", "step") else
            "its drawing" if kind == "dxf" else "its links, joints and meshes" if kind in ("urdf", "srdf") else
            "its layers as KiCad draws them, in 2D" if kind == "kicad_pcb" else
            "its sheets as KiCad draws them" if kind == "kicad_sch" else "the mesh as the viewer draws it")
    return f"{files}, which anyone with the link can download, and its view: {view}"


def agreement_lines(service: str, command: str, goes: str, sources: Any = None) -> list[str]:
    """What the first share says, refused, for the person to agree to: what goes (``goes``: ``_goes``), from where and
    by which paths, and what is left out (``sources``: ``_files``), where, who can open it, for how long, how to
    delete it, and the command that goes on once they agree."""
    from cad_server import sharing

    return [
        "sharing needs the person's yes, once on this computer; nothing was uploaded.",
        f"  What goes: {goes}. Never an installed library.",
        *(f"  {line}" for line in (_files(sources) if sources is not None else [])),
        f"  Where: {service}, which keeps it encrypted under a key made from the link, and keeps neither the link "
        "nor the key.",
        "  Who: anyone with the link can open it and download its files, with no sign-in.",
        f"  How long: until {sharing.EXPIRY_DAYS} days after its last share (sharing it again keeps the link, sends "
        f"only what changed and starts the {sharing.EXPIRY_DAYS} days again).",
        "  Delete: the delete link it prints removes it, as does `cad share delete FILE`.",
        f"Ask the person; once they agree, run `{command}`. `cad share off` turns sharing off on this computer.",
    ]


@contextlib.contextmanager
def _locked(document: str, name: str, prog: str) -> Iterator[Path]:
    """The file's folder in cad's cache (``sharing.folder_of``), made by the running server where one answers
    (``sharing.keep``), with its lock held for the block: one ``cad share`` of a file at a time. Where another holds
    it, a line says so and the lock is waited for ``LOCK_SECONDS``; then the command is refused in a line."""
    from cad_server import sharing
    from cad_server._internal.cli_errors import Failure

    def made() -> Path:
        try:
            return Path(sharing.keep(folder=document)["folder"])
        except (OSError, KeyError, TypeError) as error:
            raise Failure(f"could not make the share's folder in cad's cache: {error}") from None

    def waiting() -> None:
        print(f"{prog}: another `cad share` of {name} runs on this computer: waiting for it to end, "
              f"{LOCK_SECONDS:.0f} seconds at most", file=sys.stderr, flush=True)

    folder = made()
    with contextlib.ExitStack() as stack:
        try:
            stack.enter_context(sharing.held(folder, wait=LOCK_SECONDS, waiting=waiting, make=made))
        except sharing.Busy:
            raise Failure(f"another `cad share` of {name} has run on this computer for {LOCK_SECONDS:.0f} seconds "
                          "and goes on: share it again once it ends") from None
        except OSError as error:
            raise Failure(f"could not lock the share's folder in cad's cache ({folder}): "
                          f"{error.strerror or error}") from None
        yield folder


def _made(xbf: str) -> float:
    """When the model whose ``.xbf`` is at ``xbf`` was last made here: the file's time, or, where a live worker of
    this engine holds the model and its last run is later, that run's (``model_info``'s ``builtAt``): a run that takes
    the ``.xbf`` whole, its key the model's, writes nothing."""
    from cad.engine.client import request
    from cad.engine.ids import canonical, file_id

    made = os.stat(xbf).st_mtime
    try:
        answer = request({"op": "model_info", "id": file_id(xbf)}, start=False) or {}
    except ConnectionError:
        answer = {}
    model = answer.get("model") if isinstance(answer, dict) else None
    told = (model or {}).get("source") or {}
    if isinstance(told.get("xbf"), str) and canonical(told["xbf"]) == xbf \
            and isinstance(model.get("builtAt"), (int, float)):
        made = max(made, float(model["builtAt"]))
    return made


def _sources(path: str, kind: str) -> tuple[Any, float | None]:
    """The files that made the file at canonical ``path`` (``sharing.Sources``), and for a model when it was last made
    here (``_made``, None for a file document): a file's (``sharing.file_sources``); a model's, from the build closure
    its ``.xbf`` holds (``sharing.model_sources``), refused by the failure contract where its files are not the ones
    the ``.xbf`` was made from, naming ``cad run`` of its script."""
    from cad.engine import previous
    from cad_server import sharing
    from cad_server._internal.cli_errors import Failure
    from cad_server.cli.import_ import _command

    projects = sharing.project_roots()
    if kind != "xbf":
        return sharing.file_sources(path, kind, projects=projects), None
    made = _made(path)
    try:
        return sharing.model_sources(path, made, projects=projects), made
    except sharing.Stale as stale:
        try:
            told = (previous.of(Path(path)) or {}).get("source") or {}
        except (OSError, UnicodeDecodeError, ValueError):
            told = {}
        script = previous.absolute(told.get("path"), Path(os.path.dirname(path))) or stale.path
        again = _command("run", script)
        name = os.path.basename(path)
        what = (f"{stale.path} changed after {name} was last made, so its share would not hold what made it"
                if stale.why == "changed" else f"{stale.path}, which built {name}, is gone")
        raise Failure(f"{what}: run it again (`{again}`), then share it",
                      "failed" if stale.why == "changed" else "not_found", next=[again]) from None
    except (sharing.Unsharable, OSError) as error:
        raise Failure(f"{os.path.basename(path)}'s files cannot be shared: {error}") from None


def _share(target: str, *, yes: bool, as_json: bool, prog: str, words: list[str]) -> int:
    from cad.engine.ids import file_id
    from cad_server import sharing
    from cad_server._internal.api import share_url
    from cad_server._internal.cli_errors import Failure, classify
    from cad_server._internal.consent import retry

    path, kind = _target(target)
    kept = sharing.settings()
    if not kept["on"]:
        raise Failure("sharing is off on this computer, so nothing was uploaded: the person turns it on with "
                      "`cad share on`", "declined")
    service = share_url()
    sources, made = _sources(path, kind)
    if not kept["agreed"]:
        if not yes:
            command = retry(prog, words)
            raise Failure("\n".join(agreement_lines(service, command, _goes(kind, sources), sources)),
                          "confirmation_required", next=[command], user_action=True)
        try:
            sharing.keep(agree=True)
        except OSError as error:
            raise Failure(f"could not keep the person's agreement, so nothing was uploaded: {error}") from None
    ident = file_id(path)
    with _locked(ident, os.path.basename(path), prog) as folder:
        try:
            rows = sharing.records()
        except OSError as error:  # what cannot be read is none (a sandbox may refuse it): a new share, said
            rows = []
            print(f"{prog}: warning: could not read this computer's shares ({error.strerror or error}), so this is "
                  "a new share", file=sys.stderr, flush=True)
        earlier = sharing.recorded(rows, service, path)
        try:
            manifest = sharing.bundle(path, folder / sharing.VIEW)
        except (ValueError, RuntimeError, OSError) as error:
            # The engine's refusal or failure of the bundle (``ExportRefused``, ``NotHeld``, ``EngineError``), said by
            # the failure contract in its words.
            raise classify(error) from None
        if made is not None and _made(path) != made:
            sources, made = _sources(path, kind)  # built again meanwhile: the files of the model its view shows
        share = sharing.share_of(earlier) if earlier is not None else sharing.Share.new(service)
        found = _view(folder, share)
        shown = manifest.get("document") or {}
        document = {"id": ident, "kind": str(shown.get("kind") or kind),
                    "name": str(shown.get("name") or os.path.basename(path)), "path": path}
        # The share's name, which its zip's folder is named for: a model's .xbf's stem (its model's name, as @xbf
        # names the file), else the file's name; the same whether a worker holds the model or its file is read.
        title = sharing.share_name(Path(path).stem if kind == "xbf" else os.path.basename(path))
        try:
            sent = _sent(share, found, sources, title, sharing.stored(folder, share), prog)
        except sharing.Refused as refusal:
            if refusal.status != 403:
                raise _refused(refusal) from None
            share = sharing.Share.new(service)  # that id is no longer this computer's to write: a new share, whole
            found = _view(folder, share)
            try:
                sent = _sent(share, found, sources, title, None, prog)
            except sharing.Refused as again:
                raise _refused(again) from None
        record = sharing.record_of(share, document, sent.answer, sources)  # with where its files are, for an import
        unkept = None
        try:
            sharing.keep(record=record, stored=sent.stored)
        except OSError as error:
            unkept = str(error)
    again = earlier is not None and earlier["id"] == share.id
    what = _what(kind, [file.path for file in found], sources)
    notes = _notes(sources, kind, document["name"])
    if as_json:
        print(json.dumps({"ok": True, "view": share.view, "zip": share.zip, "delete": share.remove,
                          "expires": sent.answer["expires"], "id": share.id, "again": again,
                          "document": {name: document[name] for name in ("id", "kind", "name", "path")},
                          "files": {"count": len(sources.files), "bytes": sources.size, "entry": sources.entry,
                                    "file": sources.shared, "root": sources.root,
                                    "paths": [file.path for file in sources.files],
                                    "left_out": [{"path": left, "reason": why} for left, why in sources.left_out],
                                    "unseen": sources.unseen},
                          "sent": {**what, **sent.travelled, "format": sharing.FORMAT},
                          "stored": {"files": sent.answer["files"], "bytes": sent.answer["bytes"]},
                          "kept": unkept is None}, separators=(",", ":")), flush=True)
    else:
        print(f"Shared {document['name']}, {KINDS.get(kind, kind)}: {what['what']}; {_travelled(sent, again)}",
              flush=True)
        for line in notes:
            print(line)
        print(f"View:    {share.view}")
        print(f"Files:   {share.zip}")
        print(f"Delete:  {share.remove}")
        print(f"Expires: {_when(sent.answer['expires'])}, {sharing.EXPIRY_DAYS} days after this share"
              f"{' (the same link as before)' if again else ''}; sharing it again keeps the link and starts the "
              f"{sharing.EXPIRY_DAYS} days again", flush=True)
    if unkept is not None:
        print(f"{prog}: warning: this computer's library could not keep the share ({unkept}): sharing it again "
              "makes a new link, and only its delete link deletes this one", file=sys.stderr, flush=True)
    return 0


def _view(folder: Path, share: Any) -> list[Any]:
    """The view bundle's files in the file's folder of cad's cache, as ``share`` holds them (``sharing.view_files``:
    its document named by the share, never by this computer's id of it, a digest of its path), or the failure."""
    from cad_server import sharing
    from cad_server._internal.cli_errors import Failure

    try:
        return sharing.view_files(folder / sharing.VIEW, share)
    except (sharing.Unsharable, OSError) as error:
        raise Failure(f"the view bundle cannot be shared: {error}") from None


# Why a file that made a document was left out of its share, in a line's words.
_LEFT_OUT = {"outside": "left out, outside the project", "gone": "left out, no longer on the disk",
             "name": "left out, named in a way a share cannot hold",
             "control": "left out, a version control's file (a .git folder's), which no share holds"}


def _files(sources: Any) -> list[str]:
    """What of this computer's goes, a line each: the files' root and each file's path under it, as the share and its
    zip hold them; then the files left out, by why (``_left``)."""
    went = [f"Its files, from {sources.root}: {', '.join(file.path for file in sources.files)}"] if sources.files else []
    return went + _left(sources)


def _left(sources: Any) -> list[str]:
    """The files left out of a share, a line for each reason, each file by its path on this computer."""
    lines = []
    for why, said in _LEFT_OUT.items():
        paths = [path for path, reason in sources.left_out if reason == why]
        if paths:
            lines.append(f"{said[0].upper()}{said[1:]}: {', '.join(paths)}")
    return lines


def _notes(sources: Any, kind: str, name: str) -> list[str]:
    """What the share's files are, and are not, a line each: the files' root and their paths under it, the files left
    out, by why (``_files``); a build that read a file the engine could not see; a model whose ``.xbf`` names no code
    (no build closure)."""
    lines = _files(sources)
    if sources.unseen:
        lines.append("Its build read a file cad could not see, which the share does not hold: an import may not "
                     "rebuild it without that file")
    if kind == "xbf" and sources.entry is None:
        lines.append(f"Its .xbf alone went: no build closure names the code that made {name} (a shape a program "
                     "handed over, or a file exported from another)")
    return lines


def _records() -> list[dict[str, Any]]:
    """This computer's shares, as its library holds them (``sharing.records``), or the failure that says they cannot
    be read."""
    from cad_server import sharing
    from cad_server._internal.cli_errors import Failure

    try:
        return sharing.records()
    except OSError as error:
        raise Failure(f"could not read this computer's shares ({sharing.library_path()}): "
                      f"{error.strerror or error}") from None


def _sent(share: Any, view: list[Any], sources: Any, name: str, stored: dict[str, Any] | None, prog: str) -> Any:
    """The share of the view's files and the files that made it sent and committed (``sharing.send``), a wait the
    service asks for said once in a line; the network out of reach, and a file changed meanwhile, said in their one
    line. ``Refused`` for the caller."""
    from cad_server import sharing
    from cad_server._internal.cli_errors import Failure

    told = threading.Lock()

    def waiting(seconds: float) -> None:
        if told.acquire(blocking=False):
            print(f"{prog}: the share service asks this computer to wait {seconds:.0f} seconds before it sends more: "
                  "waiting", file=sys.stderr, flush=True)

    try:
        return sharing.send(share, view, sources, stored, name=name, waiting=waiting)
    except sharing.Unreachable as error:
        raise Failure(_unreached(share.service, error)) from None
    except (sharing.Unsharable, OSError) as error:
        raise Failure(f"the share cannot be sent: {error}") from None


def _unreached(service: str, error: Exception) -> str:
    """What a request the service did not answer whole says: its answer cut off part way (``sharing.Cut``), which
    another try may get whole; else that the network here does not reach it, which a sandbox may be why of."""
    from urllib.parse import urlsplit

    from cad_server import sharing

    if isinstance(error, sharing.Cut):
        return f"the transfer with the share service was cut off part way: {error}. Try again"
    host = urlsplit(service).netloc or service
    return (f"the network here does not reach the share service: {error}. Where a sandbox limits the hosts this "
            f"shell may reach, it must allow {host}")


def _refused(refusal: Any) -> Any:
    from cad_server._internal.cli_errors import Failure

    return Failure(f"the share service refused {refusal.what} ({refusal.status}): {refusal.error}"
                   + (f"; {refusal.hint}" if refusal.hint else ""))


def _what(kind: str, paths: list[str], sources: Any) -> dict[str, Any]:
    """What the share holds, in words (``what``): the files that made it (``sources``), and its view, from its
    files' paths, with its parts (``parts``: a model's or a STEP's parts, a robot's mesh files; None for a mesh's, a
    drawing's, a board's or a schematic's view)."""
    parts = sorted({path.split("/")[1] for path in paths if path.startswith("parts/") and path.count("/") >= 2})
    meshes = [path for path in paths if path.startswith("meshes/") or (path.startswith("parts/")
                                                                       and path.count("/") == 1)]
    count = len(sources.files)
    if kind == "xbf":
        code = count - 1  # the .xbf is one of them
        files = f"its .xbf and the {code} file{'s' if code != 1 else ''} that made it" if code else "its .xbf"
    elif kind in PROJECT and count > 1:
        files = f"the file itself with {count - 1} file{'s' if count != 2 else ''} of its project"
    elif count > 1:
        files = f"the file itself with {count - 1} file{'s' if count != 2 else ''} it draws from"
    else:
        files = "the file itself" if count else "none of its files"
    if kind in MESHES:
        view, counted = "its view", None
    elif kind == "dxf":
        view, counted = "its view (its drawing, as the viewer draws it)", None
    elif kind == "kicad_pcb":
        view, counted = "its view (its layers, in 2D)", None
    elif kind == "kicad_sch":
        sheets = [path for path in paths if path.startswith("sheets/")]
        view, counted = f"its view ({len(sheets)} sheet{'s' if len(sheets) != 1 else ''})", None
    elif kind in ("urdf", "srdf"):
        view = f"its view (its links and joints, with {len(meshes)} mesh file{'s' if len(meshes) != 1 else ''})"
        counted = len(meshes)
    else:
        view = (f"its view ({len(parts)} part{'s' if len(parts) != 1 else ''} as meshes, with their names and "
                f"measurements{' and its joints' if 'kinematics.json' in paths else ''})")
        counted = len(parts)
    return {"what": f"{files} and {view}", "parts": counted}


def _travelled(sent: Any, again: bool) -> str:
    """What went this time, in words: every file of a new share, else the files that changed, beside the whole."""
    files, size, whole = sent.travelled["files"], sent.travelled["bytes"], _size(sent.answer["bytes"])
    counted = f"{files} file{'s' if files != 1 else ''}"
    if not again:
        return f"{counted}, {_size(size)} uploaded"
    if not files:
        return f"nothing changed, nothing uploaded ({whole} in all)"
    return f"{counted} changed, {_size(size)} uploaded ({whole} in all)"


def _size(count: int) -> str:
    for unit, scale in (("MiB", 1024 * 1024), ("KiB", 1024)):
        if count >= scale:
            return f"{count / scale:.1f} {unit}"
    return f"{count} B"


def _when(expires: str) -> str:
    from datetime import datetime, timezone

    try:
        found = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except ValueError:
        return expires
    if found.tzinfo is not None:
        found = found.astimezone(timezone.utc)
    return found.strftime("%Y-%m-%d %H:%M UTC")


# --- status, on, off ---------------------------------------------------------------------------------------------


def _status(as_json: bool) -> int:
    from cad_server import sharing
    from cad_server._internal.api import share_url

    kept, service = sharing.settings(), share_url()
    live = [row for row in _records() if not sharing.expired(row)]
    if as_json:
        print(json.dumps({"ok": True, "sharing": "on" if kept["on"] else "off", "agreed": kept["agreed"],
                          "service": service, "shares": [
                              {"document": {name: row["document"].get(name) for name in ("id", "kind", "name", "path")},
                               "view": row["view"], "zip": sharing.share_of(row).zip, "delete": row["remove"],
                               "expires": row["expires"]}
                              for row in live]}, separators=(",", ":")), flush=True)
        return 0
    state = ("off: `cad share` uploads nothing until `cad share on`" if not kept["on"] else
             "on, agreed on this computer" if kept["agreed"] else "on; the first share asks for the person's yes")
    print(f"sharing: {state}")
    print(f"service: {service}")
    print(f"{len(live)} live share{'s' if len(live) != 1 else ''}{':' if live else ''}")
    for row in live:
        where = row["document"].get("path")
        print(f"  {row['document']['name']} ({row['document']['kind']}), until {_when(row['expires'])}"
              + (f": {where}" if where else ""))
        print(f"    view:   {row['view']}")
        print(f"    files:  {sharing.share_of(row).zip}")
        print(f"    delete: {row['remove']}")
    return 0


def _switch(word: str, as_json: bool) -> int:
    from cad_server import sharing
    from cad_server._internal.cli_errors import Failure

    try:
        sharing.keep(set=word)
    except OSError as error:
        raise Failure(f"could not keep the setting: {error}") from None
    if as_json:
        print(json.dumps({"ok": True, "sharing": word}, separators=(",", ":")), flush=True)
    elif word == "off":
        print("sharing: off: `cad share` uploads nothing until `cad share on`; what is shared stays until it expires "
              "or `cad share delete` removes it")
    else:
        print("sharing: on")
    return 0


# --- delete ------------------------------------------------------------------------------------------------------


def _delete(what: str, *, yes: bool, as_json: bool, prog: str, words: list[str]) -> int:
    from cad.engine.ids import canonical, is_id
    from cad_server import sharing
    from cad_server._internal.api import share_url
    from cad_server._internal.cli_errors import Failure
    from cad_server._internal.consent import confirm, retry

    service = share_url()
    rows = _records()
    link = sharing.parse_link(what)
    if link is not None:
        origin, ident, secret = link
        if origin != service:
            raise Failure(f"that link is of {origin}, not of the share service this cad uses ({service})",
                          "invalid_argument")
        record = next((row for row in rows if row["service"] == service and row["id"] == ident), None)
        if secret is None:
            if record is None:
                raise Failure("a view link deletes nothing, and this computer keeps no share of it: delete it with "
                              "its delete link", "invalid_argument")
            secret = record["delete"]
        share = sharing.share_of(record) if record is not None else sharing.Share(service, ident, "", secret)
    else:
        if what.strip().lower().startswith(("http://", "https://")):
            # Not said back: a mistyped link may still hold a share's id or secret.
            raise Failure("that is no link of a share: a share's view link is <origin>/<id>, its delete link "
                          "<origin>/<id>#delete=<secret>", "invalid_argument")
        # A file by its canonical path, which is there or not; an id by the file it is of.
        path = None if is_id(what) else canonical(os.path.join(os.getcwd(), os.path.expanduser(what)))
        record = next((row for row in rows if row["service"] == service and (
            row["document"]["id"] == what if path is None else row["document"].get("path") == path)), None)
        if record is None:
            raise Failure(f"this computer keeps no share of {what} at {service}: `cad share status` lists the ones "
                          "it keeps, and a share's delete link deletes it from anywhere", "not_found")
        share, secret = sharing.share_of(record), record["delete"]
    subject = f"the share of {record['document']['name']}" if record is not None else "the share that link names"
    confirm(f"deleting {subject}", f"Delete {subject}?", yes=yes, as_json=as_json, command=retry(prog, words),
            preview=[f"{prog} delete removes {subject} from the share service: its links open nothing from then on. "
                     "This cannot be undone."])
    with _locked(record["document"]["id"], record["document"]["name"], prog) if record is not None \
            else contextlib.nullcontext():
        try:
            deleted = sharing.delete(share, secret)
        except sharing.Unreachable as error:
            raise Failure(_unreached(service, error)) from None
        except sharing.Refused as refusal:
            raise _refused(refusal) from None
        if record is not None:
            try:
                sharing.keep(forget=share.id)  # its record, and what it kept in its file's folder of the cache
            except OSError as error:
                print(f"{prog}: warning: could not forget the share's record ({error})", file=sys.stderr, flush=True)
    if as_json:
        print(json.dumps({"ok": True, "deleted": deleted, "share": share.view,
                          "document": None if record is None else {key: record["document"].get(key)
                                                                   for key in ("id", "kind", "name", "path")}},
                         separators=(",", ":")), flush=True)
    else:
        print(f"Deleted {subject}: its links open nothing now" if deleted else
              f"{subject[0].upper()}{subject[1:]} was gone already (it expired, or was deleted): its links open "
              "nothing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
