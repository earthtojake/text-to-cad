"""``kicad_pcb.edit(path)`` and ``kicad_sch.edit(path)``: a KiCad board or schematic edited in place, through
KiCad's IPC API, in a ``with`` block::

    from cad import kicad_pcb, kicad_sch

    with kicad_sch.edit("design.kicad_sch") as s, kicad_pcb.edit("design.kicad_pcb") as b:
        ...                                # s, b: KiPy's open Schematic and Board (kicode's)

An edit is no producer: the file is the source, changed where it is, in the caller's process. Entering the
block starts a private, headless ``kicad-cli api-server --socket <path> <file>`` (the finder and the private
homes of ``_program``: kicode's kicad-cli and ``kicode.environment``; one ``CAD_KICAD_CLI`` names without
``api-server``, any stable KiCad's for now, refused before it starts; ``--socket`` takes a plain path, KiPy
the ``ipc://`` form) and connects KiPy (kicode's, ``kicode.KiCad``) to it: ready when it answers, never when a
path appears (Windows serves a named pipe, no file). One server holds a project (a board and a schematic of
one ``.kicad_pro``): an edit of the other file of a project an enclosing edit already serves joins that
server, KiCad opening the file in it (``OpenDocument``), and the server stops when the edit that started it
ends. A shell whose sandbox refuses sockets (an agent app's, by default) cannot run that server: the edit
asks first, binding a socket of its own beside the server's (``_refused``), and refuses in one line, saying
to run the script outside the sandbox, before any server starts -- KiCad's server, refused, says nothing
and never answers. A server slow to answer (KiCad's first start from a new environment) is said once.

The block is handed the open document. A file not there yet is made by KiCad (``CreateDocument``, with its
project where it has none). On a normal exit the document is saved when the block changed it (KiCad's own
``is_document_modified``) or KiCad made it, so a block that changes nothing leaves the file byte for byte, in
its own format; when the block raises, nothing is saved and the exception goes on. A save is whole or none:
when KiCad's fails (it may have written some files of a hierarchy first), every file the save writes -- the
document, its project and, for a schematic, each sheet file of its hierarchy as KiCad holds it -- is put
back as it was, a file it made is removed, and the edit raises ``KicadRunError`` with KiCad's words and what
its server logged. Each document of a
shared server is saved at its own block's exit, by the same rules. A board's block is handed KiPy's board
watched (``_drift``): the nets its ``create_items`` and ``update_items`` give items are noted, and after the
save every item KiCad saved on another net (its connectivity takes copper onto the net of a pad it overlaps)
is a warning on stderr and one of the board's ``net_changes``. A ``.kicad_prl`` (KiCad's local
settings) the edit made beside its file is removed once its server stops, and so is a folder made for a new
file that ends with no file in it.

A schematic's symbol libraries are its project's own ``sym-lib-table`` (beside the ``.kicad_pro``,
``${KIPRJMOD}`` its folder), which KiCad reads; they are loaded before the block runs (headless, KiCad loads
none until asked), and a placement from a library the project does not have is refused in one line naming
the library and how to add it. The server's KiCad homes are private, with no global table: a person's own
KiCad configuration is never read or written.

KiPy's ``KiCad.check_version()`` is never called: kicode's KiPy is the one built with its kicad-cli, and a
kicad-cli ``CAD_KICAD_CLI`` names may be another nightly's, which KiPy still reads and edits. Upstream
``kipy`` is never imported: it and kicode register the same protobuf files and cannot share a process.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._program import (KicadRunError, check_api_server, check_version, find_kicad_cli, kicad_version, private_run,
                       quiet)

__all__ = ["edit"]

# How long kicad-cli api-server may take to answer for its document, and to stop when asked; how long a
# schematic's symbol libraries may take to load.
START_SECONDS = 120.0
STOP_SECONDS = 10.0
LIBRARY_SECONDS = 120.0
_POLL = 0.05
# How long the server may take to answer before the edit says, once, what it waits for: a warm start
# answers in about 2 s; KiCad's first start from a new environment, about a minute on macOS, which checks
# each of its new libraries as it first loads them.
NOTICE_SECONDS = 8.0


# A Unix socket's path is at most 104 bytes on macOS (108 on Linux), and a sandbox's TMPDIR can be deep.
_SOCKET_PATH_MAX = 100


@contextmanager
def _socket(folder: Path) -> Iterator[Path]:
    """The api-server's address, a plain path: a socket file on POSIX, the name of a named pipe on Windows
    (where no file appears). The first of these whose path fits a socket's (a path too long would have
    kicad-cli say it listens and never bind): inside the private folder; in a short folder of its own
    directly in the temporary folder (``TMPDIR``, which a sandbox lets a program write); in one under /tmp
    (only this user's), which a sandbox may refuse. A folder of its own is removed afterwards. None fits:
    ``KicadRunError`` in one line, naming the cause and what to do."""
    path = folder / "api.sock"
    if sys.platform.startswith("win") or _fits(path):
        yield path
        return
    why: list[str] = []
    for parent in dict.fromkeys((tempfile.gettempdir(), "/tmp")):
        if not _fits(Path(parent) / "k12345678" / "api.sock"):  # mkdtemp's name: its prefix and eight letters
            why.append(f"{parent} is too deep")
            continue
        try:
            short = Path(tempfile.mkdtemp(prefix="k", dir=parent))
        except OSError as error:
            why.append(f"{parent} refused a folder ({error.strerror or error})")
            continue
        try:
            yield short / "api.sock"
        finally:
            shutil.rmtree(short, ignore_errors=True)
        return
    raise KicadRunError(f"an edit's KiCad api-server listens on a socket whose path is at most {_SOCKET_PATH_MAX} "
                        f"bytes, and no folder here gives one ({'; '.join(why)}): set TMPDIR to a shorter folder this "
                        "program may write, then run it again")


def _fits(path: Path) -> bool:
    return len(os.fsencode(path)) <= _SOCKET_PATH_MAX


def _refused(socket_path: Path) -> str | None:
    """Why this process may not listen on a Unix socket beside ``socket_path``, as the api-server must: a
    sandbox that refuses sockets (macOS Seatbelt, deny by default: an agent app's shell in its
    default mode), whose refusal the child inherits. KiCad's api-server says nothing then and never answers,
    so it is asked here, in a moment, before the server starts. None where it may (and on Windows, which
    serves a named pipe), or where the probe fails for any other reason than a refusal."""
    if sys.platform.startswith("win"):
        return None
    import socket as sockets

    probe = socket_path.with_name("try.sock")  # as long as api.sock: it fits where that does
    try:
        listener = sockets.socket(sockets.AF_UNIX, sockets.SOCK_STREAM)
    except PermissionError as error:
        return error.strerror or str(error)
    except OSError:
        return None
    try:
        listener.bind(str(probe))
        listener.listen(1)
    except PermissionError as error:
        return error.strerror or str(error)
    except OSError:
        return None
    finally:
        listener.close()
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
    return None


def _sandboxed(kind: "_Kind", why: str) -> KicadRunError:
    return KicadRunError(f"{kind.type_id}.edit runs KiCad's edit server on a local socket, and this shell's sandbox "
                         f"refuses one ({why}): run the script again outside the sandbox (an agent app's "
                         "unsandboxed or escalated run); reading, checking and exporting the file work here")


@contextmanager
def _stopped_on_signals(server: subprocess.Popen) -> Iterator[None]:
    """SIGTERM and SIGHUP (how agent hosts cancel a command) stop the api-server before the script exits, as
    Ctrl-C (SIGINT) does: each becomes SystemExit inside the run, so its ``finally`` stops the server and
    removes its folder; the earlier handlers come back afterwards. Only the main thread can set handlers;
    SIGKILL can never be caught."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def leave(signum: int, _frame: Any) -> None:
        raise SystemExit(128 + signum)

    names = [name for name in ("SIGTERM", "SIGHUP") if hasattr(signal, name)]
    earlier = {name: signal.signal(getattr(signal, name), leave) for name in names}
    try:
        yield
    finally:
        for name, handler in earlier.items():
            signal.signal(getattr(signal, name), handler)


def format_of(path: Path) -> str | None:
    """A board's or a schematic's file format, its ``(version YYYYMMDD)``; None for a file not there."""
    try:
        with path.open("rb") as file:
            head = file.read(512).decode("utf-8", "replace")
    except FileNotFoundError:
        return None
    found = re.search(r"\(version\s+(\d+)\)", head)
    return found.group(1) if found else None


def _stop(server: subprocess.Popen) -> None:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=STOP_SECONDS)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


def _kipy() -> Any:
    """KiPy's ``KiCad`` class (kicode's), imported before any server is started: without it there is nothing
    to run."""
    try:
        from kicode import KiCad  # pyrefly: ignore[missing-import] - the kicad extra, installed where an edit runs
    except ImportError:
        raise ImportError("kicad_pcb.edit and kicad_sch.edit change a file through KiCad's IPC API, whose client and "
                          "kicad-cli are the kicad extra's (kicode): install cad[kicad], or run the script with cad run"
                          ) from None
    return KiCad


def _client(kicad: Any, socket: Path) -> Any:
    """KiPy, connected to the server's socket (its ``ipc://`` form)."""
    return kicad(socket_path=f"ipc://{socket}", client_name="cad", timeout_ms=60000)


def _connecting(error: BaseException) -> bool:
    """Whether ``error`` is a connection not made yet: KiPy's ``ConnectionError`` (its own class, by name) or
    the operating system's."""
    return isinstance(error, OSError) or type(error).__name__ == "ConnectionError"


def _document(kicad: Any, server: subprocess.Popen, log: Path, kind: "_Kind", path: Path, create: bool) -> Any:
    """The open document, once the server answers for it. Ready is a connection, on every OS: KiPy dials the
    server and pings it until it answers (a connection error until it listens), and the server says it is
    not ready to reply until it has loaded the file. A file not there yet is made first (``create``: KiCad's
    ``CreateDocument``, once the server listens). Any other refusal, a server that exits, or one that has not
    answered within ``START_SECONDS``, is a failure; one that has not answered within ``NOTICE_SECONDS`` says,
    once, on stderr, what it waits for (``_waiting``), so a caller watching a quiet run knows it is going."""
    started = time.monotonic()
    deadline, listened, made, noticed = started + START_SECONDS, False, not create, False
    while True:
        try:
            kicad.ping()
            listened = True
            if not made:
                kicad.create_document(str(path), kind.doctype())
                made = True
            return getattr(kicad, kind.getter)()
        except Exception as error:  # noqa: BLE001 - KiPy's errors, by kind and by the words it says while loading
            if not _connecting(error) and "not ready" not in str(error).lower():
                raise
            if server.poll() is not None:
                said = quiet(log.read_text(encoding="utf-8", errors="replace")) if log.exists() else ""
                stage = f"loaded the {kind.noun}" if listened else "listened"
                raise KicadRunError(f"kicad-cli api-server stopped before it {stage} (exit status "
                                    f"{server.returncode})" + (f": {said}" if said else "")) from None
            if time.monotonic() > deadline:
                stage = f"load the {kind.noun}" if listened else "answer"
                raise KicadRunError(f"kicad-cli api-server did not {stage} within {START_SECONDS:g} s") from None
            if not noticed and time.monotonic() - started > NOTICE_SECONDS:
                noticed = True
                print(_waiting(kind, path, listened), file=sys.stderr, flush=True)
        time.sleep(_POLL)


def _waiting(kind: "_Kind", path: Path, listened: bool) -> str:
    """What a slow start says, once: what it waits for, and that it is still going."""
    if listened:
        return f"{kind.type_id}.edit: KiCad is loading {path.name}; waiting for it (up to {START_SECONDS:g} s)"
    return (f"{kind.type_id}.edit: waiting for KiCad's edit server to start (up to {START_SECONDS:g} s): its first "
            "start from a new environment can take a minute")


@dataclass(frozen=True)
class _Kind:
    """What an edit opens: a board or a schematic -- the word for it, its document type's id, KiPy's getter of
    the open document and KiCad's document type for it."""

    noun: str
    type_id: str
    getter: str
    doctype_name: str

    def doctype(self) -> Any:
        from kicode.proto.common.types import DocumentType  # pyrefly: ignore[missing-import] - the kicad extra

        return getattr(DocumentType, self.doctype_name)


_BOARD = _Kind("board", "kicad_pcb", "get_board", "DOCTYPE_PCB")
_SCHEMATIC = _Kind("schematic", "kicad_sch", "get_schematic", "DOCTYPE_SCHEMATIC")
_KINDS = {".kicad_pcb": _BOARD, ".kicad_sch": _SCHEMATIC}


def _modified(document: Any) -> bool:
    """Whether the function changed the open document since it was loaded (KiCad's own modified state). A
    server that cannot say (a nightly ``CAD_KICAD_CLI`` names that predates the request) is answered as
    changed, so the document is saved as it was before the rule."""
    try:
        return bool(document.is_document_modified())
    except Exception as error:  # noqa: BLE001 - KiPy's ApiError, by kind
        if type(error).__name__ == "ApiError" or isinstance(error, AttributeError):
            return True
        raise


@contextmanager
def _made_for(path: Path) -> Iterator[None]:
    """``path``'s folder, made for KiCad to make the file in (the edit's path is the request), and removed
    again, as far up as this made it, when the edit leaves no file there."""
    made = [folder for folder in (path.parent, *path.parent.parents) if not folder.exists()]
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        yield
    finally:
        if not path.exists():
            for folder in made:
                try:
                    folder.rmdir()
                except OSError:
                    break


@contextmanager
def _local_settings_as_found(path: Path) -> Iterator[None]:
    """A ``.kicad_prl`` (KiCad's local settings: the editor's view of the project) an edit makes beside
    ``path`` is removed afterwards; one that was there is never touched."""
    prl = path.with_suffix(".kicad_prl")
    was = prl.exists()
    try:
        yield
    finally:
        if not was:
            try:
                prl.unlink(missing_ok=True)
            except OSError:
                pass


def _library_of(lib_id: Any) -> str:
    """The library nickname of a symbol's id: ``"Device"`` of ``"Device:R"`` or of a ``LibraryIdentifier``."""
    if isinstance(lib_id, str):
        return lib_id.partition(":")[0]
    return str(getattr(lib_id, "library", "") or getattr(getattr(lib_id, "proto", None), "library_nickname", ""))


def _no_library(nickname: str, table: Path, have: list[str]) -> str:
    """The one line a placement from a library the project does not list says: the library, the project's table
    (or that it has none), and the row that adds it."""
    row = f'(lib (name "{nickname}")(type "KiCad")(uri "${{KIPRJMOD}}/{nickname}.kicad_sym")(options "")(descr ""))'
    if table.is_file():
        return (f"no symbol library {nickname!r} in this project's sym-lib-table ({table}, which lists "
                f"{', '.join(have) or 'none'}): add {row} to it, the uri naming the library's .kicad_sym file, "
                "and run the script again")
    return (f"no symbol library {nickname!r}: this project has no sym-lib-table ({table}), and its symbol "
            f"libraries are that table's alone; write it, (sym_lib_table (version 7) {row}), the uri naming the "
            "library's .kicad_sym file, and run the script again")


def _with_libraries(kicad: Any, schematic: Any, path: Path) -> Any:
    """The open schematic, its project's symbol libraries loaded first (headless, KiCad loads none until it is
    asked; its ``place_symbol_from_library`` says "symbol not found" until then), and a placement from a
    library the project does not list refused before KiCad is asked, in one line: the library, the
    project's table, and the row that adds it. A library listed that did not load is said once, here, and
    named again by a placement from it."""
    from kicode.proto.common.types.library_types_pb2 import LibraryLoadStatus, LibraryType  # pyrefly: ignore[missing-import]
    from kicode.schematic import Schematic  # pyrefly: ignore[missing-import] - the kicad extra

    kicad.load_all_libraries(LibraryType.LT_SYMBOL)
    statuses = kicad.wait_for_libraries(LibraryType.LT_SYMBOL, timeout_s=LIBRARY_SECONDS)
    libraries = {status.nickname: status for status in statuses}
    loaded = LibraryLoadStatus.LLS_LOADED
    for nickname, status in libraries.items():
        if status.status != loaded:
            message = getattr(status, "error_message", "") or "it did not load"
            print(f"warning: symbol library {nickname} did not load: {message}", file=sys.stderr)
    table = path.parent / "sym-lib-table"  # KiCad reads the project's own, in its folder

    class ProjectSchematic(Schematic):  # pyrefly: ignore[invalid-inheritance]
        """KiPy's Schematic, its placements from a library checked against the project's libraries."""

        def place_symbol_from_library(self, lib_id: Any, *args: Any, **options: Any) -> Any:
            nickname = _library_of(lib_id)
            status = libraries.get(nickname)
            if status is None:
                raise LookupError(_no_library(nickname, table, sorted(libraries)))
            if status.status != loaded:
                raise LookupError(f"symbol library {nickname!r} did not load: "
                                  f"{getattr(status, 'error_message', '') or 'KiCad gave no reason'}")
            return super().place_symbol_from_library(lib_id, *args, **options)

        def for_sheet(self, sheet: Any) -> Any:
            scoped = super().for_sheet(sheet)
            return ProjectSchematic(scoped.client, scoped.document)

    return ProjectSchematic(schematic.client, schematic.document)


@dataclass
class _Server:
    """One headless api-server, serving a project's board and schematic to the edits of this thread: KiPy's
    client of it, the files its edits have open, and what is undone once it stops (``after``: a folder made
    for a new file, the local settings KiCad wrote); ``log``, what the server says."""

    client: Any
    open: set[Path] = field(default_factory=set)
    after: ExitStack = field(default_factory=ExitStack)
    said: set[Path] = field(default_factory=set)  # the projects KiCad made for its edits, said once
    log: Path | None = None


def _saved_files(opened: Any, path: Path, kind: _Kind) -> list[Path]:
    """The files a save of ``opened`` may write: ``path``, its project's ``.kicad_pro`` and, for a schematic,
    every sheet file of its hierarchy as KiCad holds it (a sheet the block made among them), and the
    schematics beside it."""
    files = [path, path.with_suffix(".kicad_pro")]
    if kind is _SCHEMATIC:
        try:
            sheets = list(opened.get_hierarchy())
        except Exception:  # noqa: BLE001 - KiPy's ApiError: a server without the request; the files beside it
            sheets = []
        files += [path.parent / name for name in (getattr(sheet, "filename", "") for sheet in sheets) if name]
        files += sorted(path.parent.glob("*.kicad_sch"))
    return list(dict.fromkeys(Path(os.path.abspath(file)) for file in files))


def _logged(log: Path | None, since: int) -> str:
    """The errors the server logged after byte ``since`` of its log, one line."""
    if log is None:
        return ""
    try:
        with log.open("rb") as file:
            file.seek(since)
            text = file.read().decode("utf-8", "replace")
    except OSError:
        return ""
    # wxWidgets stamps each line with the time ("01:47:22 PM: ", a narrow no-break space before PM on macOS).
    lines = [re.sub(r"^\d\d:\d\d:\d\d(\s?[AP]M)?:\s*", "", line.strip()) for line in quiet(text).splitlines()]
    return "; ".join(line for line in lines if "error" in line.lower())


def _save(opened: Any, path: Path, kind: _Kind, server: _Server) -> None:
    """``opened`` saved whole, or none of it: when KiCad's save fails, each file it may have written is put back
    as it was (one it made removed) and ``KicadRunError`` says why, in KiCad's words and its server's log."""
    from cad._internal.atomic_replace import write_bytes_atomic

    files = _saved_files(opened, path, kind)
    kept = {file: file.read_bytes() if file.is_file() else None for file in files}
    since = server.log.stat().st_size if server.log is not None and server.log.exists() else 0
    try:
        opened.save()
    except Exception as error:  # noqa: BLE001 - KiPy's ApiError, by kind: KiCad's own refusal
        if type(error).__name__ != "ApiError":
            raise
        for file, data in kept.items():
            try:
                if data is None:
                    file.unlink(missing_ok=True)
                elif not file.is_file() or file.read_bytes() != data:
                    write_bytes_atomic(file, data)
            except OSError:
                pass
        said = str(error).removeprefix("KiCad returned error: ")
        logged = _logged(server.log, since)
        raise KicadRunError(f"KiCad could not save {path.name}: {said}" + (f" ({logged})" if logged else "")
                            + "; nothing is saved: every file the save writes is as it was") from None


def _moved(watch: Any, before: str | None, path: Path, opened: Any) -> None:
    """The items of the board just saved whose net KiCad changed (``_drift``): each said as a warning on stderr,
    and kept as the board's ``net_changes``. A board that cannot be read back says so instead."""
    from ._drift import say

    if not path.is_file():
        return
    try:
        changes = watch.check(before, path)
    except (OSError, ValueError, UnicodeDecodeError) as error:
        print(f"warning: {path.name}: its nets could not be checked after the save ({error})", file=sys.stderr)
        return
    opened.net_changes = tuple(changes)
    say(changes, path.name)


# The servers the edits of this process run, by project: its folder, its name and the thread editing it.
_SERVERS: dict[tuple[Path, str, int], _Server] = {}


def _project(path: Path) -> tuple[Path, str, int]:
    return path.parent, path.stem, threading.get_ident()


@contextmanager
def _serving(path: Path, kind: _Kind, create: bool, cli: Path | None, kicad: Any) -> Iterator[tuple[_Server, Any]]:
    """A new server for ``path``'s project, with ``path`` opened in it (made by KiCad when ``create``):
    yields the server, registered for the project's other file to join, and the open document; stopped, its
    folder removed and what it leaves undone afterwards, whatever happened."""
    if cli is None:
        cli = find_kicad_cli()
        check_version(cli, kicad_version(cli))
    check_api_server(cli)
    with ExitStack() as after:
        if create:
            after.enter_context(_made_for(path))
        after.enter_context(_local_settings_as_found(path))
        with private_run("cad-kicad-api-", cli) as (folder, env), _socket(folder) as socket:
            refused = _refused(socket)
            if refused is not None:
                raise _sandboxed(kind, refused)
            log = folder / "api-server.log"
            command = [str(cli), "api-server", "--socket", str(socket), *([] if create else [str(path)])]
            with log.open("w", encoding="utf-8") as said:
                process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=said,
                                           stderr=subprocess.STDOUT)
                key = _project(path)
                try:
                    with _stopped_on_signals(process):
                        client = _client(kicad, socket)
                        opened = _document(client, process, log, kind, path, create)
                        server = _Server(client, {path}, after, log=log)  # what a joining edit leaves undone goes there too
                        _SERVERS[key] = server
                        yield server, opened
                finally:
                    _SERVERS.pop(key, None)
                    _stop(process)
        # Here, once the server has stopped (KiCad writes its local settings until then), ``after`` undoes
        # what the edits left: the local settings they made, a folder made for a file that is not there.


def _join(server: _Server, kind: _Kind, path: Path, create: bool) -> Any:
    """``path`` opened in the project's server an enclosing edit started (made by KiCad when ``create``)."""
    if path in server.open:
        raise RuntimeError(f"{kind.type_id}.edit: {path} is open in an edit already; one edit a file")
    if create:
        server.after.enter_context(_made_for(path))
    server.after.enter_context(_local_settings_as_found(path))
    if create:
        server.client.create_document(str(path), kind.doctype())
    else:
        server.client.open_document(str(path), kind.doctype())
    server.open.add(path)
    return getattr(server.client, kind.getter)()


@contextmanager
def edit(path: Path | str, document_type: str, *, cli: Path | None = None) -> Iterator[Any]:
    """``kicad_pcb.edit(path)`` and ``kicad_sch.edit(path)``: the open board or schematic at ``path``, in a
    ``with`` block (the module's doc). ``document_type`` is the type whose ``edit`` was called; a file of the
    other is refused by name before anything starts."""
    path = Path(os.fspath(path)).expanduser().absolute()
    kind = _KINDS.get(path.suffix.lower())
    if kind is None or kind.type_id != document_type:
        found = f"a {kind.type_id}" if kind is not None else "no KiCad file"
        raise ValueError(f"{path.name} is {found}, not a {document_type}"
                         + (f": use cad.{kind.type_id}.edit" if kind is not None else ""))
    if path.exists() and not path.is_file():
        raise IsADirectoryError(f"{document_type}.edit: {path} is not a file")
    create = not path.exists()
    kicad = _kipy()
    before, project = format_of(path), path.with_suffix(".kicad_pro").exists()
    with ExitStack() as stack:
        server = _SERVERS.get(_project(path))
        if server is None:
            server, opened = stack.enter_context(_serving(path, kind, create, cli, kicad))
        else:
            opened = _join(server, kind, path, create)
            stack.callback(server.open.discard, path)
        watch = None
        if kind is _SCHEMATIC:
            opened = _with_libraries(server.client, opened, path)
        else:
            from ._drift import Watch

            watch = Watch()
            opened = watch.board(opened)
        yield opened  # a raise leaves the file as it was: nothing is saved, and the exception goes on
        saved = create or _modified(opened)
        if saved:
            was = None if create or watch is None else path.read_text(encoding="utf-8", errors="replace")
            _save(opened, path, kind, server)
            if watch is not None:
                _moved(watch, was, path, opened)
    if create:
        made = None if project or path.with_suffix(".kicad_pro") in server.said else path.with_suffix(".kicad_pro")
        server.said.add(path.with_suffix(".kicad_pro"))
        print(f"made {path}, a new {kind.noun}" + (f", and its project {made.name}" if made else ""), file=sys.stderr)
    after = format_of(path)
    if saved and before and after and before != after:
        print(f"warning: {path.name} is saved in the {kind.noun} format of the KiCad that ran it ({after}, was "
              f"{before}): a KiCad older than that can no longer open it", file=sys.stderr)
