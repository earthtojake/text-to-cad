"""``cad share`` -- a document shared for anyone with its link to open in the hosted viewer, and to download the files
that made it, with no sign-in, for 7 days after its last share (``cad_server.sharing``; the engine's **Sharing**).

- ``cad share TARGET [--yes]``: TARGET a document id the engine holds, or a file the viewer opens. What goes is the
  files that made it -- a model's script, the modules of its project the build imported and the files it read, from
  its build closure (``sharing.model_sources``); a file document's file itself (``sharing.file_sources``) -- and its
  view: the running server writes the document's view bundle into the document's folder in cad's cache, over the
  one it wrote there last, as ``cad <type> export TARGET DST.view`` writes one. This process uploads the files the
  share lacks, in packs, and commits the share (``sharing.send``) -- never the server, so an agent app's sandbox sees
  the connection and its network rules apply. A model whose files changed after its last run, or whose script or a
  module is gone, is refused in a line naming the file and the command that runs it again: its files would not be
  the ones that built its view. One ``cad share`` of a document runs at a time: another waits ``LOCK_SECONDS``,
  saying so, then is refused in a line. It prints the view link, the files' link, the delete link, the expiry, one
  line of what travelled, and a line for what was left out. The same document shared again from this computer is
  the same share: the link stays, the 7 days start again, and only what changed travels. Where the service refuses
  its names (403), or its record is past its expiry or is not one this cad reads (``cad-share/1``'s), it is a new
  share. A KiCad board or schematic and a folder are refused: they have no bundle.
- The first share on a computer needs the person's yes: without ``--yes`` it is refused, in lines an agent can
  pass on (what goes -- the code and the files that made it, which anyone with the link can download, and the view --,
  where, who can open it, for how long, how to delete it), naming the same command with ``--yes``, which records the
  agreement. ``cad share off`` refuses every share, ``--yes`` or not, until ``cad share on``.
- ``cad share status``: whether sharing is on, whether this computer agreed, and its live shares with their links.
- ``cad share delete TARGET|LINK [--yes]``: the share of a TARGET this computer shared, or the share a link names (a
  delete link, or the view link of a share this computer keeps), deleted from the service, asked first as every
  command that destroys is (``cad_server._internal.consent``); its document's folder in cad's cache goes with it.

``--json`` answers in one JSON object. Writes of the agreement, the setting, the records and the cache's folders are
the running server's where one answers (``sharing.keep``), else this process's. A share's id and its secrets are said
only inside the two links: never in any other line.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_PROG = "cad share"
ACTIONS = ("status", "on", "off", "delete")
DESCRIPTION = (
    "Share a document: anyone with its link opens it in the hosted viewer, and downloads the files that made it (the "
    "link's .zip, which `cad fork` writes into a folder), with no sign-in, until 7 days after its last share. TARGET "
    "is a document id the engine holds or a file the viewer opens. What goes is the files that made it -- a model's "
    "script, the modules of its project that it imports and the files it reads, as its last run built it (run it "
    "again after an edit); a file's file itself, with a robot description's mesh files -- and its view: its shapes as "
    "meshes with their names, measurements and joints. Never the xbf, nor an installed library. Sharing it again "
    "keeps the link and sends only what changed. The first share on a computer needs the person's yes (--yes). "
    "`status` says whether sharing is on and lists this computer's live shares; `on` and `off` turn it on and off; "
    "`delete` removes a share.")
KINDS = {"model": "a model", "xbf": "an .xbf", "step": "a STEP", "stl": "an STL", "glb": "a GLB", "3mf": "a 3MF",
         "dxf": "a DXF", "urdf": "a URDF", "srdf": "an SRDF"}
MESHES = frozenset({"stl", "glb", "3mf"})
UNBUNDLED = {"kicad_pcb": "a KiCad board", "kicad_sch": "a KiCad schematic"}
# How long a share waits for another ``cad share`` of the same document to end before it is refused.
LOCK_SECONDS = 60.0


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog=prog, description=DESCRIPTION,
                            usage=f"%(prog)s [-h] TARGET [--yes] [--json]\n       {prog} status|on|off [--json]\n"
                                  f"       {prog} delete TARGET|LINK [--yes] [--json]")
    parser.add_argument("target", metavar="TARGET",
                        help="a document id the engine holds, or a file the viewer opens (a KiCad board or schematic "
                             "and a folder have no bundle to share); or status, on, off or delete")
    parser.add_argument("link", nargs="?", metavar="TARGET|LINK",
                        help="after delete: the TARGET this computer shared, or a share's delete link")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="share: the person agrees to sharing, kept for this computer; delete: delete without "
                             "asking. Where nobody can be asked (an agent, a pipe, --json) neither runs without it")
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
        parser.error("delete names the TARGET this computer shared, or a share's delete link")
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


def _source(target: str) -> tuple[str, str | None]:
    """What a TARGET names: ``(the export's source, the file's absolute path or None for a document id)``; refused
    by the failure contract, as ``cad viewer`` refuses a FILE, where it is no document (a model's script, a path
    that is not there, a file of no document type: every type is one the viewer opens), or has no view bundle."""
    import shlex

    from cad.engine.ids import is_id
    from cad.registry import type_of
    from cad_server._internal.cli_errors import Failure

    if is_id(target):
        return target, None
    path = os.path.abspath(os.path.join(os.getcwd(), os.path.expanduser(target)))
    script = target.partition("::")[0]
    if script.lower().endswith(".py"):
        raise Failure(f"{target} is a model's script, not a CAD file: `cad run {shlex.quote(script)}` builds its "
                      "models and prints each one's id, which `cad share` takes", "wrong_type")
    if os.path.isdir(path):
        raise Failure(f"{target} is a folder, which has no view bundle: share one of its files", "wrong_type")
    if not os.path.exists(path):
        raise Failure(f"no such file: {target}", "not_found")
    found = type_of(path)
    if found is None or not os.path.isfile(path):
        raise Failure(f"no CAD file at {path}", "wrong_type")
    if found.id in UNBUNDLED:
        raise Failure(f"{target} is {UNBUNDLED[found.id]}, which has no view bundle yet, so it cannot be shared",
                      "wrong_type")
    return path, path


def _goes(kind: str, sources: Any) -> str:
    """What a share of a document of ``kind`` (its type's id) takes of it, in words: its files (``sources``), which
    anyone with the link can download, and its view."""
    count = len(sources.files)
    counted = f"{count} file{'s' if count != 1 else ''}"
    if kind == "model":
        files = f"the model's code and the files it reads ({counted})"
    elif count > 1:
        files = f"the file itself with {count - 1} file{'s' if count != 2 else ''} it draws from beside it"
    else:
        files = "the file itself"
    view = ("its shapes as meshes, with their names, measurements and joints" if kind in ("model", "xbf", "step") else
            "its drawing" if kind == "dxf" else "its links, joints and meshes" if kind in ("urdf", "srdf") else
            "the mesh as the viewer draws it")
    return f"{files}, which anyone with the link can download, and its view: {view}"


def agreement_lines(service: str, command: str, goes: str) -> list[str]:
    """What the first share says, refused, for the person to agree to: what goes (``goes``: ``_goes``), where, who
    can open it, for how long, how to delete it, and the command that goes on once they agree."""
    from cad_server import sharing

    return [
        "sharing needs the person's yes, once on this computer; nothing was uploaded.",
        f"  What goes: {goes}. Never the xbf, nor an installed library.",
        f"  Where: {service}, which keeps it encrypted under a key made from the link, and keeps neither the link "
        "nor the key.",
        "  Who: anyone with the link can open it and download its files, with no sign-in.",
        f"  How long: until {sharing.EXPIRY_DAYS} days after its last share (sharing it again keeps the link, sends "
        f"only what changed and starts the {sharing.EXPIRY_DAYS} days again).",
        "  Delete: the delete link it prints removes it, as does `cad share delete TARGET`.",
        f"Ask the person; once they agree, run `{command}`. `cad share off` turns sharing off on this computer.",
    ]


@contextlib.contextmanager
def _locked(document: str, name: str, prog: str) -> Iterator[Path]:
    """The document's folder in cad's cache (``sharing.folder_of``), made by the running server where one answers
    (``sharing.keep``), with its lock held for the block: one ``cad share`` of a document at a time. Where another
    holds it, a line says so and the lock is waited for ``LOCK_SECONDS``; then the command is refused in a line."""
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


@dataclass(frozen=True)
class _Built:
    """A model's last run, as the engine says it (``model_info``, by ``inspect``'s ``build`` query): when it was
    (``at``, its ``builtAt``), its script, the folder its build closure's paths are relative to (its xbf's where it
    declares one, else its script's: None where the run's record cannot say which), the command that runs it again
    (``again``) and its name."""

    at: float | None
    script: str
    folder: str | None
    again: str
    name: str


def _built(ident: str, live: dict[str, Any], closure: dict[str, Any] | None) -> _Built:
    """``_Built`` of the model ``ident`` names, from what the engine says of its last run (``live``) and its build
    closure."""
    from cad.engine.previous import absolute
    from cad.engine.records import rerun

    source = live.get("source") or {}
    script = os.path.normpath(str(source.get("script") or ""))
    given = live.get("with")
    again = rerun(script, live.get("python") if isinstance(live.get("python"), str) else None,
                  [item for item in given if isinstance(item, str)] if isinstance(given, list) else None)
    at = live.get("builtAt") if isinstance(live.get("builtAt"), (int, float)) else None
    # The folder the closure names its script from: its declared xbf's, as its last run in this engine wrote it; else
    # the script's; else the one its path climbs down from (``src/arm.py``: an xbf above the script, which a model
    # taken from the cache after a restart names no more). Whichever spells the script's path from it exactly as the
    # closure does (``previous``'s ``relpath``): ``../src/arm.py`` resolves from any folder beside the xbf's, and the
    # files inside that one would be other files.
    xbf = [str(path) for path in live.get("files") or [] if str(path).lower().endswith(".xbf")]
    told = (closure or {}).get("source")
    named = told.get("path") if isinstance(told, dict) else None
    steps = named.split("/") if isinstance(named, str) else []
    above = (str(Path(*Path(script).parts[:-len(steps)])) if steps and ".." not in steps
             and len(Path(script).parts) > len(steps) else None)

    def spelled(folder: str) -> str:
        try:
            return Path(os.path.relpath(script, folder)).as_posix()
        except ValueError:  # another drive: the closure names it by its whole path
            return Path(script).as_posix()

    folder = next((folder for folder in [*(os.path.dirname(path) for path in xbf[:1]), os.path.dirname(script),
                                         *([above] if above else [])]
                   if isinstance(named, str) and spelled(folder) == named
                   and os.path.normcase(absolute(named, Path(folder))) == os.path.normcase(script)), None)
    return _Built(at, script, folder, again, str(source.get("explicit_name") or source.get("name") or ident))


def _last_run(ident: str) -> dict[str, Any]:
    """What the engine says of a document it holds by its id (``inspect``'s ``build`` query): ``live``, a model's last
    run (``model_info``), or ``file``, a file's ``path``."""
    from cad.engine import api

    found = api.inspect(ident, query="build", progress=False)
    return found if isinstance(found, dict) else {}


def _sources(source: str, path: str | None) -> tuple[Any, _Built | None, str]:
    """The files that made the document TARGET names (``sharing.Sources``) and its type's id: a file's
    (``sharing.file_sources``), by its path or its document's id; a model's, from its build closure and its last run
    (``sharing.model_sources``), refused by the failure contract where its files are not the ones its last run built
    from, naming the command that runs it again. With a model's last run (``_Built``), else None."""
    from cad.engine import api
    from cad.registry import type_of
    from cad_server import sharing
    from cad_server._internal.cli_errors import Failure

    found = _last_run(source) if path is None else {}
    if path is None and not found.get("live") and isinstance((found.get("file") or {}).get("path"), str):
        path = found["file"]["path"]  # a file's document, named by its id
    if path is not None:
        kind = getattr(type_of(path), "id", "")
        return sharing.file_sources(path, kind), None, kind
    closure = api.inspect(source, query="structure", progress=False).get("closure")
    built = _built(source, found.get("live") or {}, closure)
    if not isinstance(closure, dict):  # a shape a program handed over: no closure names what made it
        return sharing.Sources(), built, "model"
    if built.folder is None:
        raise Failure(f"cad cannot tell from {built.name}'s last run where its files are: run it again "
                      f"(`{built.again}`), then share it", "failed", next=[built.again])
    try:
        return sharing.model_sources(closure, built.script, built.folder, built.at), built, "model"
    except sharing.Stale as stale:
        what = (f"{stale.path} changed after {built.name} was built, so its share would not be what built its view"
                if stale.why == "changed" else f"{stale.path}, which built {built.name}, is gone")
        raise Failure(f"{what}: run it again (`{built.again}`), then share it",
                      "failed" if stale.why == "changed" else "not_found", next=[built.again]) from None
    except (sharing.Unsharable, OSError) as error:
        raise Failure(f"{built.name}'s files cannot be shared: {error}") from None


def _share(target: str, *, yes: bool, as_json: bool, prog: str, words: list[str]) -> int:
    from cad.engine.ids import file_id
    from cad_server import sharing
    from cad_server._internal.api import share_url
    from cad_server._internal.cli_errors import Failure, classify
    from cad_server._internal.consent import retry

    source, path = _source(target)
    kept = sharing.settings()
    if not kept["on"]:
        raise Failure("sharing is off on this computer, so nothing was uploaded: the person turns it on with "
                      "`cad share on`", "declined")
    service = share_url()
    try:
        sources, built, kind = _sources(source, path)
    except (ValueError, RuntimeError, OSError) as error:
        raise classify(error) from None  # the engine's refusal (a document it does not hold), or the disk's
    if not kept["agreed"]:
        if not yes:
            command = retry(prog, words)
            raise Failure("\n".join(agreement_lines(service, command, _goes(kind, sources))), "confirmation_required",
                          next=[command], user_action=True)
        try:
            sharing.keep(agree=True)
        except OSError as error:
            raise Failure(f"could not keep the person's agreement, so nothing was uploaded: {error}") from None
    ident = source if path is None else file_id(path)
    with _locked(ident, target, prog) as folder:
        try:
            rows = sharing.records()
        except OSError as error:  # what cannot be read is none (a sandbox may refuse it): a new share, said
            rows = []
            print(f"{prog}: warning: could not read this computer's shares ({error.strerror or error}), so this is "
                  "a new share", file=sys.stderr, flush=True)
        earlier = next((row for row in rows if row["service"] == service and row["document"]["id"] == ident
                        and not sharing.expired(row)), None)
        try:
            manifest = sharing.bundle(source, folder / sharing.BUNDLE)
            if built is not None and (_last_run(source).get("live") or {}).get("builtAt") != built.at:
                sources, built, kind = _sources(source, path)  # built again meanwhile: the files of the run it shows
        except (ValueError, RuntimeError, OSError) as error:
            # The engine's refusal or failure of the bundle (``ExportRefused``, ``NotHeld``, ``EngineError``), said by
            # the failure contract in its words.
            raise classify(error) from None
        try:
            found = sharing.view_files(folder / sharing.BUNDLE)
        except (sharing.Unsharable, OSError) as error:
            raise Failure(f"the view bundle cannot be shared: {error}") from None
        shown = manifest.get("document") or {}
        document = {"id": ident, "kind": str(shown.get("kind")), "name": str(shown.get("name")), "path": path}
        title = sharing.share_name(shown.get("name"))
        share = sharing.share_of(earlier) if earlier is not None else sharing.Share.new(service)
        try:
            sent = _sent(share, found, sources, title, sharing.stored(folder, share), prog)
        except sharing.Refused as refusal:
            if refusal.status != 403:
                raise _refused(refusal) from None
            share = sharing.Share.new(service)  # that id is no longer this computer's to write: a new share, whole
            try:
                sent = _sent(share, found, sources, title, None, prog)
            except sharing.Refused as again:
                raise _refused(again) from None
        record = sharing.record_of(share, document, sent.answer, sources)  # with where its files are, for a fork
        unkept = None
        try:
            sharing.keep(record=record, stored=sent.stored)
        except OSError as error:
            unkept = str(error)
    again = earlier is not None and earlier["id"] == share.id
    what = _what(document["kind"], [file.path for file in found], sources)
    notes = _notes(sources, built)
    if as_json:
        print(json.dumps({"ok": True, "view": share.view, "zip": share.zip, "delete": share.remove,
                          "expires": sent.answer["expires"], "id": share.id, "again": again,
                          "document": {name: document[name] for name in ("id", "kind", "name")},
                          "files": {"count": len(sources.files), "bytes": sources.size, "entry": sources.entry,
                                    "left_out": [{"path": left, "reason": why} for left, why in sources.left_out],
                                    "unseen": sources.unseen},
                          "sent": {**what, **sent.travelled, "format": sharing.FORMAT},
                          "stored": {"files": sent.answer["files"], "bytes": sent.answer["bytes"]},
                          "kept": unkept is None}, separators=(",", ":")), flush=True)
    else:
        print(f"Shared {document['name']}, {KINDS.get(document['kind'], document['kind'])}: {what['what']}; "
              f"{_travelled(sent, again)}", flush=True)
        for line in notes:
            print(line)
        print(f"View:    {share.view}")
        print(f"Files:   {share.zip}")
        print(f"Delete:  {share.remove}")
        print(f"Expires: {_when(sent.answer['expires'])}, {sharing.EXPIRY_DAYS} days after this share"
              f"{' (the same link as before)' if again else ''}; sharing it again keeps the link and starts the "
              f"{sharing.EXPIRY_DAYS} days again", flush=True)
    if unkept is not None:
        print(f"{prog}: warning: this computer could not keep the share's record ({unkept}): sharing it again "
              "makes a new link, and only its delete link deletes this one", file=sys.stderr, flush=True)
    return 0


# Why a file that made a document was left out of its share, in a line's words.
_LEFT_OUT = {"outside": "left out, outside the project", "gone": "left out, no longer on the disk",
             "name": "left out, named in a way a share cannot hold"}


def _notes(sources: Any, built: _Built | None) -> list[str]:
    """What the share's files are not, a line each: the files left out, by why; a build that read a file the engine
    could not see; a document no build closure names the code of."""
    lines = []
    for why, said in _LEFT_OUT.items():
        paths = [path for path, reason in sources.left_out if reason == why]
        if paths:
            lines.append(f"{said[0].upper()}{said[1:]}: {', '.join(paths)}")
    if sources.unseen:
        lines.append("Its build read a file cad could not see, which the share does not hold: a fork may not rebuild "
                     "it without that file")
    if built is not None and not sources.files:
        lines.append(f"No files went: no build closure names the code that made {built.name} (a shape a program "
                     "handed over)")
    return lines


def _records() -> list[dict[str, Any]]:
    """This computer's records of its shares (``sharing.records``), or the failure that says they cannot be read."""
    from cad_server import sharing
    from cad_server._internal.cli_errors import Failure

    try:
        return sharing.records()
    except OSError as error:
        raise Failure(f"could not read this computer's shares ({sharing.records_path()}): "
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
    from urllib.parse import urlsplit

    host = urlsplit(service).netloc or service
    return (f"the network here does not reach the share service: {error}. Where a sandbox limits the hosts this "
            f"shell may reach, it must allow {host}")


def _refused(refusal: Any) -> Any:
    from cad_server._internal.cli_errors import Failure

    return Failure(f"the share service refused {refusal.what} ({refusal.status}): {refusal.error}"
                   + (f"; {refusal.hint}" if refusal.hint else ""))


def _what(kind: str, paths: list[str], sources: Any) -> dict[str, Any]:
    """What the share holds, in words (``what``): the files that made it (``sources``), and its view, from its
    files' paths, with its parts (``parts``: a robot's mesh files; None for a mesh's or a drawing's view)."""
    parts = sorted({path.split("/")[1] for path in paths if path.startswith("parts/") and path.count("/") >= 2})
    meshes = [path for path in paths if path.startswith("meshes/") or (path.startswith("parts/")
                                                                       and path.count("/") == 1)]
    count = len(sources.files)
    if kind == "model":
        files = f"its {count} file{'s' if count != 1 else ''}"
    elif count > 1:
        files = f"the file itself with {count - 1} file{'s' if count != 2 else ''} it draws from"
    else:
        files = "the file itself" if count else "none of its files"
    if kind in MESHES:
        view, counted = "its view", None
    elif kind == "dxf":
        view, counted = "its view (its drawing, as the viewer draws it)", None
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
                              {"document": {name: row["document"][name] for name in ("id", "kind", "name")},
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
        print(f"  {row['document']['name']} ({row['document']['kind']}), until {_when(row['expires'])}")
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
    from cad.engine.ids import file_id, is_id
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
        if is_id(what):
            ident, path = what, None
        else:
            path = os.path.abspath(os.path.join(os.getcwd(), os.path.expanduser(what)))
            ident = file_id(path)
        record = next((row for row in rows if row["service"] == service and (
            row["document"]["id"] == ident or (path is not None and row["document"]["path"] == path))), None)
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
                sharing.keep(forget=share.id)  # its record, and its document's folder in the cache
            except OSError as error:
                print(f"{prog}: warning: could not forget the share's record ({error})", file=sys.stderr, flush=True)
    if as_json:
        print(json.dumps({"ok": True, "deleted": deleted, "share": share.view,
                          "document": None if record is None else {key: record["document"][key]
                                                                   for key in ("id", "kind", "name")}},
                         separators=(",", ":")), flush=True)
    else:
        print(f"Deleted {subject}: its links open nothing now" if deleted else
              f"{subject[0].upper()}{subject[1:]} was gone already (it expired, or was deleted): its links open "
              "nothing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
