"""Sharing a document: its view bundle packed as one archive and uploaded to the share service, for anyone with
its link to open in the hosted viewer (``cad share``, ``cad_server.cli.share``; the engine's **Sharing**).

What is here is the client's half of the protocol, the standard library alone:

- **names** (``Share.new``): a share's id (16 random bytes), its key (32: an AES-256-GCM key, which the service
  encrypts the archive with and forgets), its write secret and its delete secret (32 each), every one from
  ``secrets``, base64url without padding; the service keeps only each secret's SHA-256;
- **links** (``Share.view``, ``Share.remove``): ``<origin>/<id>#key=<key>`` and ``<origin>/<id>#delete=<secret>``,
  whose part after ``#`` no browser sends to a server;
- **the archive** (``archive``, ``cad-share/1``): the bundle folder as a gzip-compressed ustar archive, every
  regular file by its path, sorted, each with mtime 0, mode 0644, uid and gid 0 and empty owner names, gzip's
  mtime 0, so the same bundle makes the same bytes; ``thumbnail.png`` left out; a path that does not fit a ustar
  header refused (``Unsharable``), never written another way; held to ``LIMIT`` before it is sent;
- **the API** (``upload``, ``delete``): ``PUT`` and ``DELETE /v1/shares/<id>`` with ``urllib``, in the calling
  process, so an agent app's sandbox sees the connection and its network rules apply; proxies as ``urllib`` takes
  them from the environment. A connection that cannot be made, or an answer that is not the service's (a proxy's
  refusal: no JSON ``error``), is ``Unreachable``; the service's own refusal is ``Refused``, with its ``error``
  and ``hint``;
- **what is kept** (``state``, ``change``): the person's agreement and whether sharing is on (the settings'
  ``share`` section: ``{"agreed": <ISO time>, "on": false}``, on where ``on`` is absent), and each share's record
  (``shares.json`` in the state folder, readable and writable by this user alone: ``RECORDS``). A command asks the
  running server to write them (``{"op": "share"}``: ``answer``), as it does every other write a shell's sandbox may
  be refused, and writes them itself where none answers.

The key and the two secrets leave this module only inside the two links, in a record, and in the request headers
the protocol puts them in: never in an exception's words, a log or telemetry.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import os
import re
import secrets
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FORMAT = "cad-share/1"
RECORDS = "shares.json"
RECORDS_FORMAT = "cad-shares/1"
SECTION = "share"
# The largest archive sent: the service's default cap (a deployment may set another, and refuses past it, 413).
LIMIT = 25 * 1024 * 1024
EXPIRY_DAYS = 7
# Left out of every archive: the picture a page last kept, which may be of an earlier version of the document.
LEFT_OUT = frozenset({"thumbnail.png"})
# How long one request may take: an archive of ``LIMIT`` over a slow link.
TIMEOUT_SECONDS = 120.0
# The most of an answer read: every answer of the API but a share's bytes is a small JSON object.
ANSWER_BYTES = 64 * 1024

_ID = re.compile(r"[A-Za-z0-9_-]{22}")
_SECRET = re.compile(r"[A-Za-z0-9_-]{43}")
# A ustar header's fields (POSIX.1-1988): a name of 100 bytes, and a prefix of 155 split off at a ``/``.
_NAME_BYTES, _PREFIX_BYTES = 100, 155


class Unsharable(ValueError):
    """A bundle the archive cannot hold as the protocol says: its words."""


class Unreachable(ConnectionError):
    """No answer of the service's: the connection could not be made, or something else answered for it."""


class Refused(Exception):
    """The service's own refusal: its status, ``error`` and ``hint``."""

    def __init__(self, status: int, error: str, hint: str = "") -> None:
        super().__init__(f"{error} ({hint})" if hint else error)
        self.status, self.error, self.hint = status, error, hint


def _token(size: int) -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(size)).rstrip(b"=").decode("ascii")


def digest(secret: str) -> str:
    """A secret as the service keeps it: the lowercase hex SHA-256 of its 43-character text (its ASCII bytes), never
    of the bytes it decodes to; the service hashes an ``Authorization`` bearer's text the same way."""
    return hashlib.sha256(secret.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class Share:
    """One share's names: its id, its key and its two secrets (the module), and the origin it lives at."""

    service: str
    id: str
    key: str
    write: str
    delete: str

    @classmethod
    def new(cls, service: str) -> Share:
        return cls(service, _token(16), _token(32), _token(32), _token(32))

    @property
    def view(self) -> str:
        return f"{self.service}/{self.id}#key={self.key}"

    @property
    def remove(self) -> str:
        return f"{self.service}/{self.id}#delete={self.delete}"

    @property
    def page(self) -> str:
        """The share's address with no fragment: what may be said of it where no secret may."""
        return f"{self.service}/{self.id}"

    def __repr__(self) -> str:  # never the key or a secret, wherever a share is printed
        return f"Share({self.page!r})"


# --- the archive -------------------------------------------------------------------------------------------------


def fits_ustar(path: str) -> bool:
    """Whether ``path`` fits a ustar header: its name alone, or split at a ``/`` into a prefix and a name."""
    if len(path.encode("utf-8")) <= _NAME_BYTES:
        return True
    parts = path.split("/")
    return any(len("/".join(parts[:cut]).encode("utf-8")) <= _PREFIX_BYTES
               and 0 < len("/".join(parts[cut:]).encode("utf-8")) <= _NAME_BYTES for cut in range(1, len(parts)))


def entries(folder: Path) -> list[str]:
    """The bundle's files the archive holds, by their paths relative to ``folder``, sorted: every regular file but
    ``LEFT_OUT``'s, ``manifest.json`` among them. A link or anything else that is no regular file, or a path that
    does not fit a ustar header, is refused (``Unsharable``)."""
    found: list[str] = []
    for root, folders, files in os.walk(folder):
        for name in (*folders, *files):
            if os.path.islink(os.path.join(root, name)):
                raise Unsharable(f"the view bundle holds a link, {name}, which a share does not take")
        for name in files:
            full = Path(root) / name
            relative = full.relative_to(folder).as_posix()
            if not full.is_file():
                raise Unsharable(f"the view bundle holds {relative}, which is no regular file")
            if relative not in LEFT_OUT:
                found.append(relative)
    found.sort()
    if "manifest.json" not in found:
        raise Unsharable("the folder holds no view bundle: it has no manifest.json")
    for relative in found:
        if not fits_ustar(relative):
            raise Unsharable(f"the view bundle's path {relative} does not fit an archive's header (a name of 100 "
                             "bytes, under a folder of 155)")
    return found


def archive(folder: Path) -> tuple[bytes, list[str]]:
    """The bundle in ``folder`` as one ``cad-share/1`` archive (the module), and the paths it holds."""
    paths = entries(folder)
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.USTAR_FORMAT, encoding="utf-8") as tar:
            for path in paths:
                data = (folder / path).read_bytes()
                entry = tarfile.TarInfo(path)
                entry.size, entry.mtime, entry.mode, entry.type = len(data), 0, 0o644, tarfile.REGTYPE
                entry.uid = entry.gid = 0
                entry.uname = entry.gname = ""
                tar.addfile(entry, io.BytesIO(data))
    return buffer.getvalue(), paths


def bundle(target: str, folder: Path) -> dict[str, Any]:
    """``target``'s view bundle (a document id the engine holds, or a file's path) written into ``folder`` by the
    running server, as ``cad <type> export TARGET DST.view`` writes one (the engine's **View bundle**): its manifest.
    Called from here, never from a ``__main__``, so the export says nothing of the folder it wrote."""
    from cad.engine import api

    api.export(target, folder)
    return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))


# --- the API -----------------------------------------------------------------------------------------------------


def _answer(raw: bytes) -> dict[str, Any] | None:
    try:
        found = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def _host(service: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(service).netloc or service


def _call(method: str, share: Share, headers: dict[str, str], body: bytes | None = None,
          timeout: float = TIMEOUT_SECONDS) -> tuple[int, dict[str, Any] | None]:
    """One request of the API, from this process: its status and its JSON answer (None for none). A connection that
    cannot be made, or a refusal that is not the service's -- no JSON ``error``, as a proxy's is -- is
    ``Unreachable``, in words that hold no secret."""
    import http.client
    import urllib.error
    import urllib.request

    url = f"{share.service}/v1/shares/{share.id}"
    request = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": "cad", **headers})
    try:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310 - http(s) only (``share_url``)
                return answer.status, _answer(answer.read(ANSWER_BYTES))
        except urllib.error.HTTPError as refusal:
            found = _answer(refusal.read(ANSWER_BYTES))
            if found is None or not isinstance(found.get("error"), str):
                raise Unreachable(f"something other than the share service answered for {_host(share.service)} "
                                  f"(HTTP {refusal.code})") from None
            return refusal.code, found
    except Unreachable:
        raise
    except TimeoutError:
        raise Unreachable(f"{_host(share.service)} did not answer within {timeout:.0f} seconds") from None
    except urllib.error.URLError as error:
        raise Unreachable(f"{_host(share.service)} could not be reached ({error.reason})") from None
    except (OSError, http.client.HTTPException) as error:
        raise Unreachable(f"{_host(share.service)} could not be reached ({type(error).__name__}: {error})") from None


def _refused(status: int, found: dict[str, Any] | None) -> Refused:
    found = found or {}
    error = found.get("error") if isinstance(found.get("error"), str) else f"HTTP {status}"
    hint = found.get("hint") if isinstance(found.get("hint"), str) else ""
    return Refused(status, error, hint)


def upload(share: Share, body: bytes) -> dict[str, Any]:
    """``PUT /v1/shares/<id>``: the archive uploaded, or uploaded again over the share of the same id and write
    secret. The service's answer, ``{"id", "expires", "bytes", "made"}`` (``made``: 201, a new share; 200, one
    replaced); ``Refused`` for its refusal (a 403: a share of that id another write secret made; a 409: its create lost
    a race, worth one more try)."""
    status, found = _call("PUT", share, {"Authorization": f"Bearer {share.write}", "Cad-Share-Key": share.key,
                                          "Cad-Delete-Hash": digest(share.delete), "Content-Type": "application/gzip",
                                          "Content-Length": str(len(body))}, body)
    if status not in (200, 201) or found is None or not isinstance(found.get("expires"), str):
        raise _refused(status, found)
    return {"id": found.get("id"), "expires": found["expires"], "bytes": found.get("bytes"), "made": status == 201}


def delete(share: Share, secret: str) -> bool:
    """``DELETE /v1/shares/<id>`` with a share's delete (or write) secret: True where it was deleted, False where
    the service holds no share of that id (expired, or deleted before); ``Refused`` otherwise (a 403: a secret that
    matches neither of its hashes)."""
    status, found = _call("DELETE", share, {"Authorization": f"Bearer {secret}"})
    if status == 204 or (200 <= status < 300):
        return True
    if status == 404:
        return False
    raise _refused(status, found)


def parse_link(link: str) -> tuple[str, str, str, str] | None:
    """A share's link as ``(origin, id, word, value)`` -- ``word`` ``key`` for a view link, ``delete`` for a delete
    link -- or None for text that is neither."""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(link.strip())
    except ValueError:
        return None
    ident = parts.path.strip("/")
    word, _, value = parts.fragment.partition("=")
    if parts.scheme not in ("http", "https") or not parts.netloc or not _ID.fullmatch(ident) \
            or word not in ("key", "delete") or not _SECRET.fullmatch(value):
        return None
    return f"{parts.scheme}://{parts.netloc}", ident, word, value


# --- what is kept ------------------------------------------------------------------------------------------------


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def expired(record: dict[str, Any]) -> bool:
    """Whether a record's share is past its expiry, as the service said it: then the service holds it no more."""
    try:
        when = datetime.fromisoformat(str(record.get("expires")).replace("Z", "+00:00"))
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when <= datetime.now(timezone.utc)


def records_path() -> Path:
    from cad.engine.places import state_dir

    return state_dir() / RECORDS


def records(path: Path | None = None) -> list[dict[str, Any]]:
    """Every share's record this computer keeps (``RECORDS``), the expired among them; [] where there are none.
    ``OSError`` where the file is there and cannot be read."""
    try:
        text = (path or records_path()).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    try:
        found = json.loads(text)
    except ValueError:
        return []
    rows = found.get("shares") if isinstance(found, dict) else None
    return [row for row in rows if _record(row)] if isinstance(rows, list) else []


def settings() -> dict[str, Any]:
    """Whether sharing is ``on`` (on unless the person turned it off) and whether this computer's person
    ``agreed``."""
    from cad_server.settings import read_section

    try:
        kept = read_section(SECTION)
    except OSError:
        kept = {}
    return {"on": kept.get("on") is not False, "agreed": isinstance(kept.get("agreed"), str)}


def share_of(record: dict[str, Any]) -> Share:
    return Share(record["service"], record["id"], record["key"], record["write"], record["delete"])


def record_of(share: Share, document: dict[str, Any], answer: dict[str, Any], sent: int) -> dict[str, Any]:
    """A share's record: its names and links, where it lives, when it expires, the document it is of
    (``{"id", "kind", "name", "path"}``: ``path`` a file's, else None), when it was last uploaded and how many bytes
    went."""
    return {"id": share.id, "key": share.key, "write": share.write, "delete": share.delete,
            "service": share.service, "view": share.view, "remove": share.remove, "expires": answer["expires"],
            "document": document, "shared": now(), "bytes": sent}


def _record(row: Any) -> bool:
    """Whether ``row`` is a share's record (``record_of``): what the server keeps for a command, and nothing else."""
    if not isinstance(row, dict):
        return False
    document = row.get("document")
    return (isinstance(row.get("id"), str) and _ID.fullmatch(row["id"]) is not None
            and all(isinstance(row.get(name), str) and _SECRET.fullmatch(row[name]) for name in ("key", "write",
                                                                                                 "delete"))
            and all(isinstance(row.get(name), str) for name in ("view", "remove", "expires", "shared"))
            and isinstance(row.get("service"), str) and row["service"].startswith(("https://", "http://"))
            and isinstance(row.get("bytes"), int) and isinstance(document, dict)
            and all(isinstance(document.get(name), str) for name in ("id", "kind", "name"))
            and isinstance(document.get("path"), (str, type(None))))


def _write_records(path: Path, rows: list[dict[str, Any]]) -> None:
    """The records written whole, readable and writable by this user alone (a file made 0600 in the same folder,
    then put in place), so no other user of the computer reads a key or a secret."""
    from cad._internal.atomic_replace import replace_atomic

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as file:
            file.write((json.dumps({"format": RECORDS_FORMAT, "shares": rows}, indent=1, sort_keys=True)
                        + "\n").encode("utf-8"))
        os.chmod(temporary, 0o600)
        replace_atomic(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def change(request: dict[str, Any]) -> dict[str, Any]:
    """One change of what is kept, in this process: ``{"set": "on"|"off"}``, ``{"agree": true}``, ``{"record": <a
    share's record>}`` (kept in place of any record of the same share, or of the same document at the same service)
    or ``{"forget": <share id>}``. Every record past its expiry is dropped as the records are written. ``{"ok":
    true, "settings"}``, or ``{"failed"}`` in one line for a change it does not take. ``OSError`` where the state
    folder cannot be written."""
    from cad_server._internal.file_lock import state
    from cad_server.settings import update_section

    asked = [name for name in ("set", "agree", "record", "forget") if name in request]
    if len(asked) != 1:
        return {"failed": "a change of what sharing keeps is one of set, agree, record or forget"}
    if "set" in request:
        if request["set"] not in ("on", "off"):
            return {"failed": "sharing is set on or off"}
        update_section(SECTION, lambda kept: {**{k: v for k, v in kept.items() if k != "on"},
                                              **({} if request["set"] == "on" else {"on": False})})
    elif "agree" in request:
        if request["agree"] is not True:
            return {"failed": "an agreement is true"}
        update_section(SECTION, lambda kept: {**kept, "agreed": now()})
    else:
        record, forget = request.get("record"), request.get("forget")
        if "record" in request and not _record(record):
            return {"failed": "not a share's record"}
        if "forget" in request and not (isinstance(forget, str) and _ID.fullmatch(forget)):
            return {"failed": "forget names a share's id"}
        path = records_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with state(path.parent):
            rows = [row for row in records(path) if not expired(row)]
            if record is not None:
                rows = [row for row in rows if row["id"] != record["id"] and not (
                    row["service"] == record["service"] and row["document"]["id"] == record["document"]["id"])]
                rows.append(record)
            else:
                rows = [row for row in rows if row["id"] != forget]
            _write_records(path, rows)
    return {"ok": True, "settings": settings()}


def answer(request: dict[str, Any]) -> dict[str, Any]:
    """The server's answer to ``{"op": "share", ...}``: the change made for a command (``change``), so a shell
    whose sandbox may not write cad's state folder (an agent app's) keeps a share with no permission asked."""
    try:
        return change({name: value for name, value in request.items() if name != "op"})
    except OSError as error:
        return {"failed": f"could not keep it: {error.strerror or error}"}


def keep(**asked: Any) -> dict[str, Any]:
    """``change`` made by the running server where one answers that knows it, else in this process -- a sandboxed
    shell's command asks the server, as ``cad update auto`` does. ``OSError`` in either's words where it could not."""
    from cad.engine import client

    try:
        found = client.request({"op": "share", **asked}, start=False, timeout=10.0)
    except ConnectionError:
        found = None
    if isinstance(found, dict) and str(found.get("failed", "")).startswith("unknown request"):
        found = None  # a server of a release before sharing: written here
    if found is None:
        found = change(asked)
    if found.get("ok") is not True:
        raise OSError(str(found.get("failed") or "the cad server did not keep it"))
    return found
