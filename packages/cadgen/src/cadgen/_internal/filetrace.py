"""What a build reads, seen where every reader ends up: the C library's open.

Nothing is declared. A model reads its data any way it likes -- ``open()``,
numpy, build123d's importers, an OCCT reader in C++, a font FreeType loads --
and each of those opens the file through the C library (kernel32 on Windows).
cadgen's tracer, a small native library shipped per platform in
``_runtime/native``, rewires every library loaded in this process to call it
first: while :func:`capture` is open, each file opened is logged with its size
and mtime at that moment, so a file that changes after the build read it is
caught rather than hashed as if it had been read that way.

The folders a build lists come from Python's ``os.listdir`` / ``os.scandir``
audit events, by frame: a folder the model's code globbed (or a library it
called did) is an input; the import system listing folders to find modules is
not, and neither is cadgen's own bookkeeping.

An input file is one the build read and did not write, that is not code --
Python source is tracked by reach, a compiled library belongs to the
environment -- and that lies outside the machine: the interpreter and its
packages, cadgen itself, the store, and the folders the operating system owns.
An application whose data a model is made from may still live in one of the
machine's folders (KiCad's symbol and footprint libraries under
``/usr/share/kicad`` or Program Files): :func:`claim_inputs` names such a folder,
and what a build reads there is an input like any other.
"""

from __future__ import annotations

import contextlib
import ctypes
import functools
import os
import platform
import stat
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

__all__ = ["CHANGED", "Trace", "capture", "claim_inputs", "paused"]

#: The hash an input is recorded with when it changed after the build read it.
#: It matches no file, so the next gate rebuilds.
CHANGED = "changed while building"

_CODE_SUFFIXES = frozenset({".py", ".pyc", ".pyi", ".pth", ".so", ".pyd", ".dylib", ".dll"})
_PROTOCOL = 2  # filetrace.c's FILETRACE_VERSION: what its log records mean

_LOCK = threading.Lock()
_TRACER: ctypes.CDLL | None = None
_OPEN: list["Trace"] = []  # the captures in progress, outermost first
_LOG: str | None = None  # the outermost capture's log
_HOOKED = False
_CLAIMED: set[Path] = set()  # folders whose files are inputs even inside the machine's folders


def _library_name() -> str:
    system = {"darwin": "macos", "win32": "windows"}.get(sys.platform, sys.platform)
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    suffix = {"macos": "dylib", "windows": "dll"}.get(system, "so")
    return f"filetrace-{system}-{machine}.{suffix}"


def _tracer() -> ctypes.CDLL:
    """The tracer, installed in this process: once, and for good."""
    global _TRACER
    with _LOCK:
        if _TRACER is None:
            from cadgen.assets import AssetMissing, runtime_build_hint, runtime_root

            path = runtime_root() / "native" / _library_name()
            if not path.is_file():
                raise AssetMissing(
                    f"cadgen's file tracer for this platform ({path.name}) is missing, and without "
                    "it a build cannot see the files it reads. " + runtime_build_hint(path, overridable=False)
                )
            library = ctypes.CDLL(str(path))
            library.cadgen_filetrace_begin.argtypes = [ctypes.c_char_p]
            library.cadgen_filetrace_end.restype = None
            if library.cadgen_filetrace_install() != _PROTOCOL:
                raise RuntimeError(f"cadgen's file tracer ({path}) could not install in this process")
            _TRACER = library
        return _TRACER


@dataclass
class Trace:
    """What one capture saw opened and listed."""

    read: dict[str, set[tuple[int, int]]] = field(default_factory=dict)  # path -> {(size, mtime_ns)} at open
    updated: set[str] = field(default_factory=set)  # read paths opened to read and write
    written: set[str] = field(default_factory=set)
    listed: set[str] = field(default_factory=set)
    unnamed: int = 0  # files opened whose path the tracer could not write down

    def _parse(self, log: bytes, *, own: str) -> None:
        for record in log.split(b"\0"):
            if not record:
                continue
            kind, size, mtime, raw = record.split(b"\t", 3)
            path = os.fsdecode(raw)
            if kind == b"x":
                self.unnamed += 1
            elif path == own:
                continue
            elif kind == b"w":
                self.written.add(path)
            else:
                self.read.setdefault(path, set()).add((int(size), int(mtime)))
                if kind == b"u":
                    self.updated.add(path)

    def inputs(self, *, outputs: Iterable[Path] = ()) -> tuple[dict[Path, str], set[Path]]:
        """The files this build read, each with its content hash -- or
        :data:`CHANGED` when it no longer holds what was read -- and the
        folders its code listed. A file opened to read and write (a database,
        ``r+``) is read while it still holds what it held; one the build
        changed or removed is the build's own."""
        if self.unnamed:
            raise RuntimeError(
                f"this build opened {self.unnamed} file(s) whose path could not be recorded (a path "
                "longer than the system allows, or a working directory that was removed), so what "
                "it read cannot be tracked."
            )
        from cadgen._internal.source_hash import _sha256_file

        excluded = _environment_roots()
        with _LOCK:
            claimed = tuple(_CLAIMED)

        def environments(path: Path) -> bool:
            return any(path.is_relative_to(root) for root in excluded) and not any(
                path.is_relative_to(root) for root in claimed
            )

        written = {_resolved(path) for path in (*self.written, *outputs)}
        updated = {_resolved(path) for path in self.updated}
        opened: dict[Path, set[tuple[int, int]]] = {}
        for raw, seen in self.read.items():
            path = _resolved(raw)
            if path is None or path in written or path.suffix.lower() in _CODE_SUFFIXES:
                continue
            if not environments(path):
                opened.setdefault(path, set()).update(seen)
        files: dict[Path, str] = {}
        for path, seen in opened.items():
            try:
                before = os.stat(path)
                digest = _sha256_file(path)
                after = os.stat(path)
            except OSError:
                if path not in updated:
                    files[path] = CHANGED  # read, then gone
                continue
            if not stat.S_ISREG(before.st_mode):
                continue
            now = (before.st_size, before.st_mtime_ns)
            if seen == {now} and (after.st_size, after.st_mtime_ns) == now:
                files[path] = digest
            elif path not in updated:
                files[path] = CHANGED
        folders = {
            folder
            for folder in map(_resolved, self.listed)
            if folder is not None and folder.is_dir() and not environments(folder)
        }
        return files, folders


def claim_inputs(folder: str | Path) -> None:
    """Make what a build reads under ``folder`` an input, even where the machine's folders lie.

    For an application's data a model is made from, installed where the
    operating system keeps programs: KiCad's libraries in ``/usr/share/kicad``
    are a board's inputs as much as they are in an app bundle.
    """
    resolved = _resolved(folder)
    if resolved is not None:
        with _LOCK:
            _CLAIMED.add(resolved)


def _resolved(path: str | Path) -> Path | None:
    try:
        return Path(path).resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def _environment_roots() -> tuple[Path, ...]:
    """Where a read is the environment's, not the model's: the interpreter and its
    packages, cadgen, the store, and the machine."""
    from cadgen._internal.source_hash import _excluded_roots
    from cadgen.store.paths import store_root

    return (*_excluded_roots(), store_root().resolve(), *_machine_roots())


@functools.lru_cache(maxsize=1)
def _machine_roots() -> tuple[Path, ...]:
    """The folders the operating system owns: fonts, time zones, locale data, its
    libraries. A build reads them as part of the machine, as it does its Python."""
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        names = [os.environ.get(name, "") for name in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData")]
        names.append(os.path.join(local, "Microsoft", "Windows", "Fonts") if local else "")
    else:
        names = ["/dev", "/proc", "/sys", "/run", "/etc", "/usr", "/lib", "/lib64", "/bin", "/sbin", "/nix/store",
                 "/System", "/Library", "/private/etc", "/private/var/db"]
        names += [os.path.expanduser(name) for name in ("~/Library/Fonts", "~/.fonts", "~/.local/share/fonts")]
    return tuple(root for root in map(_resolved, filter(None, names)) if root is not None)


@contextlib.contextmanager
def capture() -> Iterator[Trace]:
    """Record what the code run inside opens and lists. Nests: an inner capture
    sees its own stretch of the log, the outer one all of it."""
    global _LOG
    tracer = _tracer()
    _hook_listings()
    # Classify before the hook can fire: computing the roots imports sysconfig
    # data, whose own work would otherwise reach a half-built classifier.
    _environment_roots()
    trace = Trace()
    outermost = not _OPEN
    if outermost:
        from cadgen._internal.temp_leftovers import TRACE_PREFIX, TRACE_SUFFIX, owned_prefix

        # Named after this process, so a sweep can tell whether its owner is gone.
        handle, _LOG = tempfile.mkstemp(prefix=owned_prefix(TRACE_PREFIX), suffix=TRACE_SUFFIX)
        os.close(handle)
        if tracer.cadgen_filetrace_begin(os.fsencode(_LOG)) != 0:
            raise OSError(f"cadgen's file tracer could not open its log {_LOG}")
    log = _LOG
    assert log is not None
    start = os.stat(log).st_size
    _OPEN.append(trace)
    try:
        yield trace
    finally:
        _OPEN.pop()
        if outermost:
            tracer.cadgen_filetrace_end()
            _LOG = None
        with open(log, "rb") as handle:
            handle.seek(start)
            trace._parse(handle.read(), own=log)
        if outermost:
            os.unlink(log)


@contextlib.contextmanager
def paused() -> Iterator[None]:
    """cadgen's own reading on this thread -- the gate hashing a child's files
    and outputs -- unseen by the capture: a child is an input by its result."""
    tracer = _TRACER
    if tracer is None:
        yield
        return
    tracer.cadgen_filetrace_pause(1)
    try:
        yield
    finally:
        tracer.cadgen_filetrace_pause(0)


def _hook_listings() -> None:
    """Install, once, the audit hook that hears every Python-level folder listing."""
    global _HOOKED
    with _LOCK:
        if not _HOOKED:
            sys.addaudithook(_listing_audit)
            _HOOKED = True


def _listing_audit(event: str, args: tuple) -> None:
    if not _OPEN or event not in ("os.listdir", "os.scandir"):
        return
    try:
        target = args[0] if args else None
        if not _listed_by_model(sys._getframe(1)):
            return
        folder = _descriptor_path(target) if isinstance(target, int) else os.path.abspath(
            os.fsdecode(target if target is not None else "."))
        if folder is None:
            return
        for trace in tuple(_OPEN):
            trace.listed.add(folder)
    except Exception:  # noqa: BLE001 - an audit hook must never fail the call it observes
        pass


def _descriptor_path(fd: int) -> str | None:
    """The folder an open descriptor names (``os.fwalk``, ``scandir(fd)``)."""
    try:
        if sys.platform == "darwin":
            import fcntl

            return os.fsdecode(fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).split(b"\0", 1)[0])
        return os.readlink(f"/proc/self/fd/{fd}")
    except (OSError, AttributeError, ValueError):
        return None


def _listed_by_model(frame) -> bool:
    """Whether the innermost caller outside the standard library and installed
    packages is the model's code: the import system listing a folder for an
    import, and cadgen for its own bookkeeping, are not."""
    while frame is not None:
        kind = _frame_kind(frame.f_code.co_filename)
        if kind != "other":
            return kind == "model"
        frame = frame.f_back
    return False


@functools.lru_cache(maxsize=8192)
def _frame_kind(filename: str) -> str:
    """"cadgen", "model", "import" (the import system) or "other" for a frame's source file."""
    if filename.startswith("<frozen importlib"):
        return "import"
    if not filename or filename.startswith("<"):
        return "other"
    from cadgen._internal.source_hash import _PACKAGE_ROOT, is_first_party_source_file

    path = _resolved(filename)
    if path is None:
        return "other"
    if path.is_relative_to(_PACKAGE_ROOT):
        return "cadgen"
    return "model" if is_first_party_source_file(path) else "other"
