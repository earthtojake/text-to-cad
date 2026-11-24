"""``cad share`` -- a document shared for anyone with its link to open in the hosted viewer, with no sign-in, for 7
days after its last share (``cad_server.sharing``; the engine's **Sharing**).

- ``cad share TARGET [--yes]``: TARGET a document id the engine holds, or a file the viewer opens. The running
  server writes the document's view bundle into a temporary folder, as ``cad <type> export TARGET DST.view`` writes
  one; this process packs it (``sharing.archive``) and uploads it (``sharing.upload``) -- never the server, so an
  agent app's sandbox sees the connection and its network rules apply. It prints the view link, the delete link,
  the expiry and one line of what travelled. The same document shared again from this computer is uploaded again
  under the same names: the link stays, and the 7 days start again; where the service refuses them (403), it is a
  new share. A KiCad board or schematic and a folder are refused: they have no bundle.
- The first share on a computer needs the person's yes: without ``--yes`` it is refused, in lines an agent can
  pass on (what goes, where, who can open it, for how long, how to delete it), naming the same command with
  ``--yes``, which records the agreement. ``cad share off`` refuses every share, ``--yes`` or not, until ``cad
  share on``.
- ``cad share status``: whether sharing is on, whether this computer agreed, and its live shares with their links.
- ``cad share delete TARGET|LINK [--yes]``: the share of a TARGET this computer shared, or the share a delete
  link names, deleted from the service, asked first as every command that destroys is
  (``cad_server._internal.consent``).

``--json`` answers in one JSON object. Writes of the agreement, the setting and the records are the running
server's where one answers (``sharing.keep``), else this process's. The key and the secrets are said only inside
the two links: never in any other line.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DEFAULT_PROG = "cad share"
ACTIONS = ("status", "on", "off", "delete")
DESCRIPTION = (
    "Share a document: anyone with its link opens it in the hosted viewer, with no sign-in, until 7 days after its "
    "last share. TARGET is a document id the engine holds or a file the viewer opens. What goes is its view bundle: "
    "a model's, an .xbf's or a STEP's shapes as meshes with their names, measurements and joints, never its code or "
    "the CAD file; an STL, a GLB or a 3MF is the file itself. The first share on a computer needs the person's yes "
    "(--yes). `status` says whether sharing is on and lists this computer's live shares; `on` and `off` turn it on "
    "and off; `delete` removes a share.")
KINDS = {"model": "a model", "xbf": "an .xbf", "step": "a STEP", "stl": "an STL", "glb": "a GLB", "3mf": "a 3MF",
         "dxf": "a DXF", "urdf": "a URDF", "srdf": "an SRDF"}
MESHES = frozenset({"stl", "glb", "3mf"})
UNBUNDLED = {"kicad_pcb": "a KiCad board", "kicad_sch": "a KiCad schematic"}


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


def agreement_lines(service: str, command: str) -> list[str]:
    """What the first share says, refused, for the person to agree to: what goes, where, who can open it, for how
    long, how to delete it, and the command that goes on once they agree."""
    from cad_server import sharing

    return [
        "sharing needs the person's yes, once on this computer; nothing was uploaded.",
        "  What goes: a model's, an .xbf's or a STEP's shapes as meshes, with their names, measurements and joints, "
        "never its code or the CAD file; an STL, a GLB or a 3MF is the file itself (a DXF its drawing, a URDF or an "
        "SRDF its links, joints and mesh files).",
        f"  Where: {service}, which stores it encrypted with a key only the link holds.",
        "  Who: anyone with the link can open it, with no sign-in.",
        f"  How long: until {sharing.EXPIRY_DAYS} days after its last share (sharing it again keeps the link and "
        f"starts the {sharing.EXPIRY_DAYS} days again).",
        "  Delete: the delete link it prints removes it, as does `cad share delete TARGET`.",
        f"Ask the person; once they agree, run `{command}`. `cad share off` turns sharing off on this computer.",
    ]


def _share(target: str, *, yes: bool, as_json: bool, prog: str, words: list[str]) -> int:
    from cad_server import sharing
    from cad_server._internal.api import share_url
    from cad_server._internal.cli_errors import Failure
    from cad_server._internal.consent import retry

    source, path = _source(target)
    kept = sharing.settings()
    if not kept["on"]:
        raise Failure("sharing is off on this computer, so nothing was uploaded: the person turns it on with "
                      "`cad share on`", "declined")
    service = share_url()
    if not kept["agreed"]:
        if not yes:
            command = retry(prog, words)
            raise Failure("\n".join(agreement_lines(service, command)), "confirmation_required", next=[command],
                          user_action=True)
        try:
            sharing.keep(agree=True)
        except OSError as error:
            raise Failure(f"could not keep the person's agreement, so nothing was uploaded: {error}") from None
    folder = Path(tempfile.mkdtemp(prefix="cad-share-"))
    try:
        try:
            manifest = sharing.bundle(source, folder / "share.view")
        except (ValueError, RuntimeError, OSError) as error:
            # The engine's refusal or failure of the bundle (``ExportRefused``, ``NotHeld``, ``EngineError``), said by
            # the failure contract in its words.
            from cad_server._internal.cli_errors import classify

            raise classify(error) from None
        try:
            body, paths = sharing.archive(folder / "share.view")
        except (sharing.Unsharable, OSError) as error:
            raise Failure(f"the view bundle cannot be shared: {error}") from None
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    if len(body) > sharing.LIMIT:
        raise Failure(f"{_size(len(body))} is more than the {_size(sharing.LIMIT)} a share takes, so nothing was "
                      "uploaded")
    shown = manifest.get("document") or {}
    document = {"id": str(shown.get("id")), "kind": str(shown.get("kind")), "name": str(shown.get("name")),
                "path": path}
    earlier = next((row for row in _records() if row["service"] == service
                    and row["document"]["id"] == document["id"]), None)
    share = sharing.share_of(earlier) if earlier is not None else sharing.Share.new(service)
    try:
        answer = _uploaded(share, body)
    except sharing.Refused as refusal:
        if refusal.status != 403:
            raise _refused("the upload", refusal) from None
        share = sharing.Share.new(service)  # that id is no longer this computer's to write: a new share
        try:
            answer = _uploaded(share, body)
        except sharing.Refused as again:
            raise _refused("the upload", again) from None
    record = sharing.record_of(share, document, answer, len(body))
    unkept = None
    try:
        sharing.keep(record=record)
    except OSError as error:
        unkept = str(error)
    again = earlier is not None and earlier["id"] == share.id
    sent = _sent(document["kind"], paths, len(body))
    if as_json:
        print(json.dumps({"ok": True, "view": share.view, "delete": share.remove, "expires": answer["expires"],
                          "id": share.id, "again": again, "document": {name: document[name] for name in
                                                                       ("id", "kind", "name")},
                          "sent": sent, "kept": unkept is None}, separators=(",", ":")), flush=True)
    else:
        print(f"Shared {document['name']}, {KINDS.get(document['kind'], document['kind'])}: {sent['what']}, "
              f"{_size(len(body))} uploaded; {sent['without']}", flush=True)
        print(f"View:    {share.view}")
        print(f"Delete:  {share.remove}")
        print(f"Expires: {_when(answer['expires'])}, {sharing.EXPIRY_DAYS} days after this share"
              f"{' (the same link as before)' if again else ''}; sharing it again keeps the link and starts the "
              f"{sharing.EXPIRY_DAYS} days again", flush=True)
    if unkept is not None:
        print(f"{prog}: warning: this computer could not keep the share's record ({unkept}): sharing it again "
              "makes a new link, and only its delete link deletes this one", file=sys.stderr, flush=True)
    return 0


def _records() -> list[dict[str, Any]]:
    """This computer's records of its shares (``sharing.records``), or the failure that says they cannot be read."""
    from cad_server import sharing
    from cad_server._internal.cli_errors import Failure

    try:
        return sharing.records()
    except OSError as error:
        raise Failure(f"could not read this computer's shares ({sharing.records_path()}): "
                      f"{error.strerror or error}") from None


def _uploaded(share: Any, body: bytes) -> dict[str, Any]:
    """The upload (``sharing.upload``), tried once more where the service lost a race to create it (409), which is
    transient; the network out of reach said in its one line."""
    from cad_server import sharing
    from cad_server._internal.cli_errors import Failure

    for attempt in (1, 2):
        try:
            return sharing.upload(share, body)
        except sharing.Unreachable as error:
            raise Failure(_unreached(share.service, error)) from None
        except sharing.Refused as refusal:
            if refusal.status != 409 or attempt == 2:
                raise
    raise AssertionError("unreachable")


def _unreached(service: str, error: Exception) -> str:
    from urllib.parse import urlsplit

    host = urlsplit(service).netloc or service
    return (f"the network here does not reach the share service: {error}. Where a sandbox limits the hosts this "
            f"shell may reach, it must allow {host}")


def _refused(what: str, refusal: Any) -> Any:
    from cad_server._internal.cli_errors import Failure

    return Failure(f"the share service refused {what} ({refusal.status}): {refusal.error}"
                   + (f"; {refusal.hint}" if refusal.hint else ""))


def _sent(kind: str, paths: list[str], size: int) -> dict[str, Any]:
    """What travelled, from the archive's paths: in words (``what``, ``without``) and as data."""
    parts = sorted({path.split("/")[1] for path in paths if path.startswith("parts/") and path.count("/") >= 2})
    meshes = [path for path in paths if path.startswith("meshes/") or (path.startswith("parts/")
                                                                       and path.count("/") == 1)]
    if kind in MESHES:
        what, without, counted = "the file itself", "no code went", None
    elif kind == "dxf":
        what, without, counted = "its drawing, as the viewer draws it", "no code or CAD file went", None
    elif kind in ("urdf", "srdf"):
        what = f"its links and joints, with {len(meshes)} mesh file{'s' if len(meshes) != 1 else ''}"
        without, counted = "no code went, nor the description's own file", len(meshes)
    else:
        what = (f"{len(parts)} part{'s' if len(parts) != 1 else ''} as meshes, with their names and measurements"
                + (" and its joints" if "kinematics.json" in paths else ""))
        without, counted = "no code or CAD file went", len(parts)
    return {"what": what, "without": without, "parts": counted, "files": len(paths), "bytes": size,
            "format": "cad-share/1", "code": False, "cad_file": kind in MESHES}


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
                               "view": row["view"], "delete": row["remove"], "expires": row["expires"]}
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
        origin, ident, word, secret = link
        if origin != service:
            raise Failure(f"that link is of {origin}, not of the share service this cad uses ({service})",
                          "invalid_argument")
        record = next((row for row in rows if row["service"] == service and row["id"] == ident), None)
        if word == "key":
            if record is None:
                raise Failure("a view link deletes nothing, and this computer keeps no share of it: delete it with "
                              "its delete link", "invalid_argument")
            secret = record["delete"]
        share = sharing.Share(service, ident, "", "", secret)
    else:
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
    name = record["document"]["name"] if record is not None else share.page
    confirm(f"deleting the share of {name}", f"Delete the share of {name}?", yes=yes, as_json=as_json,
            command=retry(prog, words),
            preview=[f"{prog} delete removes {share.page} from the share service: its links open nothing from then "
                     "on. This cannot be undone."])
    try:
        deleted = sharing.delete(share, secret)
    except sharing.Unreachable as error:
        raise Failure(_unreached(service, error)) from None
    except sharing.Refused as refusal:
        raise _refused("the delete", refusal) from None
    if any(row["id"] == share.id for row in rows):
        try:
            sharing.keep(forget=share.id)
        except OSError as error:
            print(f"{prog}: warning: could not forget the share's record ({error})", file=sys.stderr, flush=True)
    if as_json:
        print(json.dumps({"ok": True, "deleted": deleted, "share": share.page,
                          "document": None if record is None else {key: record["document"][key]
                                                                   for key in ("id", "kind", "name")}},
                         separators=(",", ":")), flush=True)
    else:
        print(f"Deleted the share of {name}: {share.page} opens nothing now" if deleted else
              f"The share of {name} was gone already (it expired, or was deleted): {share.page} opens nothing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
