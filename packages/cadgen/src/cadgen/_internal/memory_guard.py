"""A hard ceiling on one build's memory, so a runaway kernel operation ends the
BUILD instead of the machine.

A model can always author a boolean the kernel cannot finish -- a fillet-heavy
casting used as a tool, a fuzzy fuse over a thousand tangent faces -- and OCCT
answers by allocating until the OS steps in. On 2026-09-02 that took a
workstation down overnight: single build processes reached 100-230 GB and the
kernel's memory killer took unrelated processes with them, while the builds
themselves printed nothing. The daemon's dead-worker message and the runner's
teaching errors are useless if the machine is gone.

The guard samples this process's PEAK resident size once a second and, past the
cap, prints one line naming the cap, the stage the build was in, and the
override, then exits the process. RESIDENT is the whole contract on every
platform: ``ru_maxrss`` on POSIX and ``PeakWorkingSetSize`` on Windows both
count pages the process actually held, so the ceiling bounds residency and not
commit -- a runaway that commits far more than RAM and is paged out can plateau
under the cap on either. That is the same ceiling POSIX has always had; a
Windows-only commit bound would make the two platforms trip at different
things. It exits rather than raising because the
runaway is inside a C++ call that Python cannot interrupt: ``KeyboardInterrupt``
would be delivered when the boolean returns, which is never. Locks are
``flock``-held and released by the kernel on exit; progress records are UI.

Default: half of the memory budget the daemon pool already sizes itself by
(the cgroup limit inside a container, else physical RAM), never below 4 GB.
A legitimate full build of a 2,500-part engine measured 4.1 GB, so a 64 GB
workstation gives 8x headroom. ``CADGEN_MAX_RSS_GB`` overrides; ``0`` disables.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Callable

ENV_VAR = "CADGEN_MAX_RSS_GB"
DEFAULT_FRACTION_OF_BUDGET = 0.5
FLOOR_BYTES = 4 * 1024**3
SAMPLE_SECONDS = 1.0
EXIT_CODE = 137  # the code the OS killer would have produced, so wrappers treat both alike


def _scale_ru_maxrss(ru_maxrss: int, platform: str) -> int:
    """``ru_maxrss`` in BYTES.

    macOS reports bytes; every other POSIX host this runs on reports kilobytes.
    Darwin is the exception, not "the BSDs" -- FreeBSD reports kilobytes like
    Linux does. Taking ``platform`` as an argument is what lets one host test
    both scalings."""
    return int(ru_maxrss) if platform == "darwin" else int(ru_maxrss) * 1024


def _posix_peak_rss() -> int | None:
    """Peak RSS from ``getrusage``, or None where there is no ``resource`` module.

    The import is HERE and not at module scope on purpose: ``resource`` is
    POSIX-only, this module is imported on the hot path of every build (the
    generation runner and every verbose stage line), and a module-scope import
    took every Windows build down with ``ModuleNotFoundError``."""
    try:
        import resource
    except ImportError:
        return None
    return _scale_ru_maxrss(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, sys.platform)


def _load_kernel32():
    """kernel32, already mapped into every Windows process. The seam tests patch."""
    import ctypes

    return ctypes.WinDLL("kernel32", use_last_error=True)


_WINDOWS_COUNTERS_TYPE = None


def _windows_counters_type():
    """``PROCESS_MEMORY_COUNTERS``, the BASE struct (not the ``_EX`` variant).

    The field spellings are load-bearing, and both mistakes are silent:
    ``cb`` and ``PageFaultCount`` are DWORD, so ``c_uint32`` -- ``c_ulong`` is 8
    bytes on LP64 hosts, which would move every field after them. The remaining
    eight are SIZE_T, so ``c_size_t`` -- ``c_ulong`` is 4 bytes on Win64, which
    would read ``PeakWorkingSetSize`` from the wrong offset and return a
    plausible wrong number rather than an error."""
    global _WINDOWS_COUNTERS_TYPE
    if _WINDOWS_COUNTERS_TYPE is not None:
        return _WINDOWS_COUNTERS_TYPE
    import ctypes

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_uint32),
            ("PageFaultCount", ctypes.c_uint32),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    _WINDOWS_COUNTERS_TYPE = PROCESS_MEMORY_COUNTERS
    return _WINDOWS_COUNTERS_TYPE


def _windows_reader(load_library=None) -> Callable[[], int | None] | None:
    """A callable giving this process's peak working set in bytes, or None when
    the counter cannot be read at all.

    ``K32GetProcessMemoryInfo`` lives in kernel32 (psapi's export forwards to it
    on Win7+ and this package requires Python >= 3.11, which will not start on
    anything older), so nothing extra has to be loaded."""
    import ctypes

    counters_type = _windows_counters_type()
    try:
        kernel32 = (load_library or _load_kernel32)()
        get_process_memory_info = kernel32.K32GetProcessMemoryInfo
        get_current_process = kernel32.GetCurrentProcess
        # DECLARING both signatures is what carries the handle, and the restype
        # alone would not. With no ``argtypes`` ctypes converts a Python int
        # argument to a MASKED 32-bit C int, so the ``(HANDLE)-1`` pseudo-handle
        # would reach the callee only by way of libffi sign-extending that -1
        # back to 64 bits -- correct by accident, on an undocumented rule.
        # ``c_void_p`` in ``argtypes`` passes all 64 bits and removes the bet.
        get_current_process.argtypes = []
        get_current_process.restype = ctypes.c_void_p
        get_process_memory_info.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(counters_type),
            ctypes.c_uint32,
        ]
        get_process_memory_info.restype = ctypes.c_int  # Win32 BOOL
    except (OSError, AttributeError):
        return None

    size = ctypes.sizeof(counters_type)

    def read() -> int | None:
        counters = counters_type()
        counters.cb = size  # the struct describes its own size, base vs _EX
        try:
            ok = get_process_memory_info(get_current_process(), ctypes.pointer(counters), size)
        except Exception:  # noqa: BLE001 - the contract here is a number or None
            # Deliberately everything: this runs on the guard's sampling thread
            # AND on every verbose stage line, so an escape would fail the build
            # rather than the reading. ``ctypes.ArgumentError`` is neither an
            # OSError nor an AttributeError, which is how a narrow tuple here
            # reproduces the outage this module was rewritten for.
            return None
        if not ok:  # a false Win32 BOOL means nothing was written
            return None
        return int(counters.PeakWorkingSetSize)

    return read


_WINDOWS_READER: Callable[[], int | None] | None = None
_WINDOWS_READER_RESOLVED = False


def _forget_windows_reader() -> None:
    """Drop the cached reader. Tests only -- a resolved None would otherwise leak."""
    global _WINDOWS_READER, _WINDOWS_READER_RESOLVED
    _WINDOWS_READER = None
    _WINDOWS_READER_RESOLVED = False


def _windows_peak_rss() -> int | None:
    global _WINDOWS_READER, _WINDOWS_READER_RESOLVED
    if not _WINDOWS_READER_RESOLVED:
        _WINDOWS_READER = _windows_reader()
        _WINDOWS_READER_RESOLVED = True
    if _WINDOWS_READER is None:
        return None
    return _WINDOWS_READER()


def peak_rss_bytes() -> int:
    """This process's peak resident size in bytes; ``0`` when it cannot be measured.

    Unmeasurable FAILS OPEN. ``MemoryGuard.check`` returns early on
    ``peak <= cap``, so 0 simply never trips a positive cap. Raising is the bug
    this replaced, and a large sentinel would be worse still: ``abort`` defaults
    to ``os._exit``, so a fabricated number would kill the build with no
    traceback and nothing to catch."""
    peak = _windows_peak_rss() if sys.platform == "win32" else _posix_peak_rss()
    return peak if peak and peak > 0 else 0


def format_gb(value: int | float) -> str:
    return f"{value / 1024**3:.1f} GB"


def resolve_cap_bytes(environ=None) -> int | None:
    """The cap in bytes, or None when disabled.

    ``CADGEN_MAX_RSS_GB``: a positive number of gigabytes; ``0`` disables; an
    unparsable value is ignored (the default applies) rather than disabling the
    guard by accident."""
    env = os.environ if environ is None else environ
    raw = str(env.get(ENV_VAR, "")).strip()
    if raw:
        try:
            gigabytes = float(raw)
        except ValueError:
            gigabytes = None
        if gigabytes is not None:
            if gigabytes <= 0:
                return None
            return int(gigabytes * 1024**3)
    from cadgen.daemon.pool import memory_budget

    budget = memory_budget()
    if budget is None:
        return FLOOR_BYTES
    return max(FLOOR_BYTES, int(budget * DEFAULT_FRACTION_OF_BUDGET))


class MemoryGuard:
    """Watch the process's peak RSS on a daemon thread; abort past the cap.

    ``read_peak`` and ``abort`` are injectable for tests. ``describe_stage`` is
    consulted at abort time so the message names what the build was doing."""

    def __init__(
        self,
        cap_bytes: int | None,
        *,
        label: str,
        describe_stage: Callable[[], str] | None = None,
        read_peak: Callable[[], int] = peak_rss_bytes,
        abort: Callable[[int], None] | None = None,
        sample_seconds: float = SAMPLE_SECONDS,
    ) -> None:
        self.cap_bytes = cap_bytes
        self.label = label
        self.describe_stage = describe_stage or (lambda: "")
        self.read_peak = read_peak
        self.abort = abort or (lambda code: os._exit(code))
        self.sample_seconds = sample_seconds
        self.tripped_at: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def check(self) -> bool:
        """One sample; True when the cap was exceeded (and the abort was invoked)."""
        if self.cap_bytes is None:
            return False
        peak = self.read_peak()
        if peak <= self.cap_bytes:
            return False
        self.tripped_at = peak
        stage = self.describe_stage()
        where = f" during {stage}" if stage else ""
        sys.stderr.write(
            f"cadgen: {self.label} exceeded the build memory cap{where}: peak {format_gb(peak)} "
            f"> cap {format_gb(self.cap_bytes)}. Aborting this build so the machine keeps running. "
            f"A runaway kernel operation (a boolean or fillet that never converges) is the usual cause; "
            f"the stage named above is where to look. Raise the cap with {ENV_VAR}=<gigabytes>, or "
            f"{ENV_VAR}=0 to disable the guard.\n"
        )
        sys.stderr.flush()
        self.abort(EXIT_CODE)
        return True

    def _run(self) -> None:
        while not self._stop.wait(self.sample_seconds):
            if self.check():
                return

    def _announce_if_inactive(self) -> None:
        """Say so, once, when the counter cannot be read.

        A guard whose peak reads 0 is INSTALLED BUT INERT: ``check`` returns
        early on ``peak <= cap`` forever, so the build looks guarded and is not.
        Failing open is right -- a fabricated number would kill builds with no
        traceback -- but failing open SILENTLY is how the same machine dies
        twice. There is no legitimate 0 among the platforms this runs on (POSIX
        has ``resource``, Windows has kernel32), so this line only prints when
        something is genuinely broken, and only once per build."""
        if self.cap_bytes is None or self.read_peak() > 0:
            return
        sys.stderr.write(
            f"cadgen: the build memory cap is {format_gb(self.cap_bytes)}, but this process's peak "
            f"memory cannot be read on {sys.platform} -- the guard is INACTIVE for this build.\n"
        )
        sys.stderr.flush()

    def __enter__(self) -> "MemoryGuard":
        if self.cap_bytes is not None:
            self._announce_if_inactive()
            self._thread = threading.Thread(target=self._run, name="cadgen-memory-guard", daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.sample_seconds * 2)
