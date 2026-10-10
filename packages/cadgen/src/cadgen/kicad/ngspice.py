"""ngspice, KiCad's simulator, driven in this process through its shared library.

The library is loaded once per process with :mod:`ctypes` and initialised the
way KiCad initialises it: KiCad's LTspice/PSpice compatibility
(``ngbehavior=ltpsa``), its code models, no paging and no prompts. Like
KiCad's, it reads a person's ``.spiceinit`` if there is one (ngspice offers no
safe way to skip it: its switches for that crash when called before
``ngSpice_Init`` and do nothing after). Simulations run one at a time under a
lock: load the circuit
(``ngSpice_Circ``), run one analysis, read every vector of the plot it made,
then remove the plot and the circuit.

A failed run raises :class:`NgspiceFailure` carrying ngspice's own words:
ngspice prints errors and keeps going, and a failed analysis can leave no new
plot or an empty one, so a run counts only when ngspice printed no error and
made the plot asked for (never an earlier run's). A fatal ngspice error never
ends the Python process: ngspice reports it through its ``ControlledExit``
callback instead of exiting, and the library is initialised again before its
next use (using it without that would crash the process).

The library is ``CADGEN_NGSPICE`` (a full path) when set, else the one beside
the KiCad :func:`cadgen.kicad.install.find_kicad` finds (KiCad ships ngspice on
macOS and Windows), else the system's (``libngspice.so.0``, a distribution's
``libngspice0``, which KiCad's Linux packages depend on). Nothing is loaded
until a simulation runs; when there is none, the error says how to get one.
"""

from __future__ import annotations

import contextlib
import ctypes
import ctypes.util
import locale
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

__all__ = ["NgspiceFailure", "Plot", "library_candidates", "simulate"]


class NgspiceFailure(RuntimeError):
    """ngspice did not complete a run: ``errors`` are its error lines, ``log`` all it printed."""

    def __init__(self, reason: str, *, errors: Sequence[str] = (), log: Sequence[str] = ()):
        super().__init__(reason)
        self.reason = reason
        self.errors = tuple(errors)
        self.log = tuple(log)


@dataclass(frozen=True)
class Plot:
    """One analysis's results: ``vectors`` by lowercased name (numpy arrays, complex for AC)."""

    name: str
    vectors: dict[str, Any]
    log: tuple[str, ...]
    warnings: tuple[str, ...]


# --- the C interface (ngspice's sharedspice.h) -----------------------------------


class _Complex(ctypes.Structure):
    _fields_ = [("real", ctypes.c_double), ("imag", ctypes.c_double)]


class _VectorInfo(ctypes.Structure):
    _fields_ = [
        ("v_name", ctypes.c_char_p),
        ("v_type", ctypes.c_int),
        ("v_flags", ctypes.c_short),
        ("v_realdata", ctypes.POINTER(ctypes.c_double)),
        ("v_compdata", ctypes.POINTER(_Complex)),
        ("v_length", ctypes.c_int),
    ]


_SendChar = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
_SendStat = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
_ControlledExit = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)
_BGThreadRunning = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)

# KiCad's settings; the rest of ngspice's defaults stand.
_SETTINGS = ("set noaskquit", "set nomoremode", "set ngbehavior=ltpsa")
# ngspice's own words for a run that went wrong (it prints them and carries on).
_ERROR_MARKERS = (
    "error",
    "singular matrix",
    "unrecognized parameter",
    "unknown parameter",
    "ignored",
    "can't find",
    "cannot find",
    "could not find",
    "not found",
    "aborted",
    "timestep too small",
    "fatal",
    "unknown subckt",
    "unknown model",
)


def library_candidates() -> list[str]:
    """Where ngspice's shared library may be, best first (paths or names the loader resolves)."""
    explicit = os.environ.get("CADGEN_NGSPICE", "").strip()
    if explicit:
        return [str(Path(explicit).expanduser())]
    found: list[str] = []
    from cadgen.kicad.install import KicadMissingError, find_kicad

    try:
        install = find_kicad()
    except KicadMissingError:
        install = None
    if install is not None and install.ngspice is not None:
        found.append(str(install.ngspice))
    system = ctypes.util.find_library("ngspice")
    if system:
        found.append(system)
    if sys.platform.startswith("linux"):
        found.append("libngspice.so.0")
    return list(dict.fromkeys(found))


def _missing(problems: Sequence[str]) -> Exception:
    from cadgen.kicad.install import KicadMissingError, install_hint

    linux = (
        " (KiCad's packages bring the libngspice0 library; it can be installed alone)"
        if sys.platform.startswith("linux")
        else ""
    )
    detail = f" (tried {'; '.join(problems)})" if problems else ""
    return KicadMissingError(
        f"ngspice, the simulator KiCad ships, was not found{detail}: {install_hint()}{linux}, "
        "or set CADGEN_NGSPICE to the ngspice shared library's path"
    )


def _codemodel_folder(library: str) -> Path | None:
    """The folder of ngspice's code models (``*.cm``) that belong with ``library``."""
    candidates: list[Path] = []
    path = Path(library)
    if path.is_absolute():
        base = path.resolve().parent
        candidates += [
            base / "ngspice",  # macOS: PlugIns/sim/ngspice beside PlugIns/sim/libngspice
            base.parent / "PlugIns" / "sim" / "ngspice",  # macOS: from Contents/Frameworks
            base.parent / "lib" / "ngspice",  # Windows: KiCad's bin/../lib/ngspice
            base.parent / "lib" / "kicad" / "ngspice",
        ]
    candidates += [Path("/usr/lib/ngspice"), Path("/usr/lib64/ngspice"), Path("/usr/local/lib/ngspice")]
    candidates += sorted(Path("/usr/lib").glob("*-linux-gnu*/ngspice"))
    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("*.cm")):
            return candidate
    return None


@contextlib.contextmanager
def _c_numbers() -> Iterator[None]:
    """ngspice reads and prints numbers with the C library: keep a '.' decimal point."""
    if locale.localeconv().get("decimal_point", ".") == ".":
        yield
        return
    previous = locale.setlocale(locale.LC_NUMERIC)
    locale.setlocale(locale.LC_NUMERIC, "C")
    try:
        yield
    finally:
        locale.setlocale(locale.LC_NUMERIC, previous)


class _Engine:
    """One loaded ngspice library and the state of its use in this process."""

    def __init__(self, library: str):
        self._dll_folder = None
        if sys.platform.startswith("win") and Path(library).is_absolute():
            self._dll_folder = os.add_dll_directory(str(Path(library).parent))  # KiCad's DLLs beside ngspice's
        self.library_path = library
        self.lib = ctypes.CDLL(library)
        self.codemodels = _codemodel_folder(library)
        self.lines: list[str] = []
        self.exited: tuple[int, bool, bool] | None = None
        self.dead = False
        self.ready = False
        # Kept on the engine: ctypes callbacks must outlive every call into ngspice.
        self._callbacks = (
            _SendChar(self._send_char),
            _SendStat(self._ignore),
            _ControlledExit(self._controlled_exit),
            _BGThreadRunning(self._ignore_running),
        )
        lib = self.lib
        lib.ngSpice_Init.argtypes = [_SendChar, _SendStat, _ControlledExit, ctypes.c_void_p, ctypes.c_void_p, _BGThreadRunning, ctypes.c_void_p]
        lib.ngSpice_Init.restype = ctypes.c_int
        lib.ngSpice_Command.argtypes = [ctypes.c_char_p]
        lib.ngSpice_Command.restype = ctypes.c_int
        lib.ngSpice_Circ.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
        lib.ngSpice_Circ.restype = ctypes.c_int
        lib.ngSpice_CurPlot.restype = ctypes.c_char_p
        lib.ngSpice_AllVecs.argtypes = [ctypes.c_char_p]
        lib.ngSpice_AllVecs.restype = ctypes.POINTER(ctypes.c_char_p)
        lib.ngGet_Vec_Info.argtypes = [ctypes.c_char_p]
        lib.ngGet_Vec_Info.restype = ctypes.POINTER(_VectorInfo)

    # -- callbacks (ngspice calls them from inside a call into it) --

    def _send_char(self, text: bytes | None, ident: int, user: Any) -> int:
        self.lines.append((text or b"").decode("utf-8", "replace"))
        return 0

    def _ignore(self, text: bytes | None, ident: int, user: Any) -> int:
        return 0

    def _ignore_running(self, running: bool, ident: int, user: Any) -> int:
        return 0

    def _controlled_exit(self, status: int, immediate: bool, quit_: bool, ident: int, user: Any) -> int:
        # ngspice wanted to exit. It has not: it returns to us, and must be
        # initialised again before it is used (or, when it asks to be unloaded
        # at once, never used again in this process).
        self.exited = (int(status), bool(immediate), bool(quit_))
        self.ready = False
        if immediate:
            self.dead = True
        return 0

    # -- calls --

    def command(self, text: str) -> int:
        return int(self.lib.ngSpice_Command(text.encode("utf-8")))

    def circuit(self, lines: Sequence[str]) -> int:
        encoded = [line.encode("utf-8") for line in lines]
        array = (ctypes.c_char_p * (len(encoded) + 1))(*encoded, None)
        return int(self.lib.ngSpice_Circ(array))

    def initialise(self) -> None:
        self.lines = []
        self.exited = None
        self.lib.ngSpice_Init(*self._callbacks[:3], None, None, self._callbacks[3], None)
        for setting in _SETTINGS:
            self.command(setting)
        if self.codemodels is not None:
            for model in sorted(self.codemodels.glob("*.cm")):
                self.command(f"codemodel '{model}'")
        log, self.lines = tuple(self.lines), []
        if self.exited is not None:
            raise NgspiceFailure(f"ngspice ({self.library_path}) would not start", log=log)
        self.ready = True

    def vectors(self, plot: str) -> dict[str, Any]:
        import numpy

        names_pointer = self.lib.ngSpice_AllVecs(plot.encode("utf-8"))
        names: list[str] = []
        if names_pointer:
            index = 0
            while names_pointer[index]:
                names.append(names_pointer[index].decode("utf-8", "replace"))
                index += 1
        found: dict[str, Any] = {}
        for name in names:
            info = self.lib.ngGet_Vec_Info(f"{plot}.{name}".encode("utf-8"))
            if not info:
                continue
            vector = info.contents
            length = int(vector.v_length)
            if length <= 0:
                found[name.lower()] = numpy.zeros(0)
            elif vector.v_compdata:
                doubles = ctypes.cast(vector.v_compdata, ctypes.POINTER(ctypes.c_double))
                found[name.lower()] = numpy.ctypeslib.as_array(doubles, shape=(2 * length,)).copy().view(numpy.complex128)
            elif vector.v_realdata:
                found[name.lower()] = numpy.ctypeslib.as_array(vector.v_realdata, shape=(length,)).copy()
        return found

    def run(self, lines: Sequence[str], analysis: str, *, plot_prefix: str) -> Plot:
        if self.dead:
            raise NgspiceFailure(
                "an earlier simulation in this process hit an ngspice error it cannot recover from; "
                "run the simulation in a new Python process"
            )
        if not self.ready:
            self.initialise()
        self.exited = None
        self.command("destroy all")  # no earlier plot can be read as this run's
        self.command("remcirc")
        if self.exited is not None:  # ready is False again: the next run starts ngspice afresh
            raise NgspiceFailure("ngspice stopped while clearing the previous simulation; run it again", log=tuple(self.lines))
        self.lines = []
        loaded = self.circuit(lines) == 0 and self.exited is None
        ran = loaded and self.command(analysis) == 0 and self.exited is None
        log = tuple(line.rstrip() for line in self.lines)
        errors = tuple(line for line in log if _is_error(line))
        warnings = tuple(line[len("stderr ") :] for line in log if line.startswith("stderr ") and not _is_error(line))
        if self.exited is not None:
            status, immediate, _quit = self.exited
            raise NgspiceFailure(
                f"ngspice stopped (exit status {status}){' and cannot be used again in this process' if immediate else ''}",
                errors=errors,
                log=log,
            )
        current = self.lib.ngSpice_CurPlot()
        plot = current.decode("utf-8", "replace") if current else ""
        try:
            if not loaded:
                raise NgspiceFailure("ngspice could not load the circuit", errors=errors, log=log)
            if not ran or errors or not plot.startswith(plot_prefix):
                raise NgspiceFailure(f"ngspice could not run `{analysis}`", errors=errors, log=log)
            vectors = self.vectors(plot)
            if not vectors:
                raise NgspiceFailure(f"`{analysis}` produced no results", errors=errors, log=log)
            return Plot(name=plot, vectors=vectors, log=log, warnings=warnings)
        finally:
            if self.exited is None:
                self.command("destroy all")
                self.command("remcirc")
            self.lines = []


def _is_error(line: str) -> bool:
    if not line.startswith("stderr "):
        return False
    text = line[len("stderr ") :].lower()
    return any(marker in text for marker in _ERROR_MARKERS)


_LOCK = threading.Lock()
_ENGINE: _Engine | None = None


def _engine() -> _Engine:
    global _ENGINE
    if _ENGINE is None:
        problems: list[str] = []
        for candidate in library_candidates():
            try:
                _ENGINE = _Engine(candidate)
                break
            except (OSError, AttributeError) as error:  # not loadable, or not ngspice's shared API
                problems.append(f"{candidate}: {error}")
        else:
            raise _missing(problems)
    return _ENGINE


def simulate(lines: Sequence[str], analysis: str, *, plot_prefix: str) -> Plot:
    """Run ``analysis`` (an ngspice command such as ``tran 1u 5m``) on the netlist ``lines``.

    ``plot_prefix`` is the plot the analysis makes (``op``, ``tran``, ``ac``,
    ``dc``). Raises :class:`NgspiceFailure` when ngspice reports a problem,
    and ``KicadMissingError`` when there is no ngspice to run.
    """
    with _LOCK:
        engine = _engine()
        with _c_numbers():
            return engine.run(lines, analysis, plot_prefix=plot_prefix)
