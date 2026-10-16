"""The public ``pcb`` namespace: the ``@pcb`` decorator and the board's verbs.

``@pcb`` DECLARES a printed circuit board: the decorated function fills an
empty KiCad board, handed to it as :class:`cadgen.kipy.board.Board`, with raw
kicad-python calls -- footprints from the libraries the project's
``fp-lib-table`` declares, nets named on pads and tracks, zones, design rules,
net classes, exports. Calling the decorated function BUILDS: it starts KiCad's
own headless API server (``kicad-cli api-server``), creates the document, runs
the function, refills the zones, counts what is unrouted, saves, stops the
server, runs KiCad's design rule check on the saved file and prints one line,
then every finding, errors first, in the text ``cadgen pcb drc`` prints::

    blinky.kicad_pcb: 3 parts, 7 tracks, 1 via, 1 zone, 0 unconnected, DRC 0 errors 0 warnings, 4.6 s

The board is saved before it is checked -- a half-routed board is the normal
state for hours, and the viewer wants the file -- and the exit code stays 0
whatever DRC finds: ``cadgen pcb drc`` is the exit-1 check for CI and scripts.
Flags ride ``sys.argv`` as every cadgen script's do: ``--no-drc`` skips the
check, ``--force`` overwrites a board something else saved (below), and a build
that fails in a script run prints one ``FAILED:`` line and exits 1 as every cadgen
script does (``--verbose`` for the traceback, ``--json`` for the envelope). ``pcb.drc(board)``
runs the check alone on a saved board, the one check the API does not offer;
``pcb.snapshot`` draws one. They are the same object -- this module is callable
-- so ``from cadgen import pcb`` gives a board script all of them::

    from cadgen import pcb
    from cadgen.kipy.board_types import Net
    from cadgen.kipy.geometry import Angle, Vector2

    @pcb
    def blinky(board):
        r1 = board.place_footprint_from_library("Resistor_SMD:R_0603_1608Metric",
                                                Vector2.from_xy_mm(0, 5), Angle.from_degrees(-90))
        r1.reference_field.text.value = "R1"
        for pad in r1.definition.pads:
            pad.net = Net(name={"1": "VBUS", "2": "LED"}[pad.number])
        board.update_items([r1])

    if __name__ == "__main__":
        blinky()

``python blinky.py`` writes ``blinky.kicad_pcb`` beside the script (``@pcb(path=...)``
names another, relative to the script), with KiCad's ``.kicad_pro`` and
``.kicad_prl`` beside it: every file is KiCad's, written by KiCad. Beside the
board sits ``fp-lib-table``, KiCad's project library table, naming the
footprint libraries the board uses (``${KICAD10_FOOTPRINT_DIR}/Resistor_SMD.pretty``
for a stock one, ``${KIPRJMOD}/my.pretty`` for the board's own); the build loads
exactly those. The server runs with an empty settings directory of its own, so
no user library table is loaded. Coordinates and units are KiCad's
(:mod:`cadgen.kipy.util.units`). No schematic.

A build overwrites the board file, so it refuses to overwrite what it did not
write. It records the SHA-256 of the board it saved as the project text
variable ``CADGEN_BUILD``; KiCad writes the project's text variables into the
board file as well, so the hash covers every line of the file but its own.
Before a build, an existing board whose record is missing or does not match
its bytes -- KiCad saved it, a hand edit, a foreign board at that path -- stops
the build with one sentence naming the file and ``--force``. A first build into
an empty directory needs nothing.

The build is one server per call and nothing resident: no daemon, store or
file tracer is involved, and importing this module never touches KiCad.
:func:`connect` is the one seam between the build and KiCad.
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from cadgen._internal.snapshot_door import plot_snapshot_verb
from cadgen.kicad.cli import Finding, issues
from cadgen.results import ValidationResult

__all__ = ["drc", "snapshot"]

#: ``cadgen pcb snapshot``'s verb: a board drawn as the viewer draws it.
snapshot = plot_snapshot_verb("pcb")

# The client's per-request timeout. A library load can stall the server for a
# moment and a save is one request; the build never waits on anything else.
_TIMEOUT_MS = 120_000
_LIBRARY_TIMEOUT_S = 300.0

#: The project text variable a build records the saved board's hash in.
RECORD = "CADGEN_BUILD"
_RECORD_LINE = f'(property "{RECORD}" '.encode()


class BoardError(RuntimeError):
    """What a build could not do with the board's files: a library table row that did not
    load, a footprint no declared library has, a board file something else saved. The
    message says what to do."""


@dataclass(frozen=True)
class DrcReport:
    """KiCad's design rule check of the saved board: the counts and every finding."""

    errors: int
    warnings: int
    findings: tuple[Finding, ...]

    def lines(self) -> list[str]:
        """Every finding as ``cadgen pcb drc`` prints it, errors first."""
        return [issue.human_line() for issue in issues(self.findings)]


@dataclass(frozen=True)
class BoardBuild:
    """What one ``@pcb`` call wrote: the files, what is on the board, what DRC found."""

    board: Path  #: the ``.kicad_pcb``
    project: Path  #: its ``.kicad_pro`` beside it
    parts: int
    tracks: int
    vias: int
    zones: int
    unconnected: int  #: pads not copper-connected to the first pad of their net
    drc: DrcReport | None  #: ``None`` under ``--no-drc``
    seconds: float

    def report(self) -> str:
        from cadgen._internal.doors import display_path

        checked = f"DRC {_count(self.drc.errors, 'error')} {_count(self.drc.warnings, 'warning')}, " if self.drc else ""
        return (
            f"{display_path(self.board)}: {_count(self.parts, 'part')}, {_count(self.tracks, 'track')}, "
            f"{_count(self.vias, 'via')}, {_count(self.zones, 'zone')}, {self.unconnected} unconnected, "
            f"{checked}{self.seconds:.1f} s"
        )


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def pcb(func: Callable[[Any], Any] | None = None, *, path: str | None = None):
    """Declare a board. Usable bare (``@pcb``) or configured (``@pcb(path="boards/x.kicad_pcb")``).

    The function takes the board (:class:`cadgen.kipy.board.Board`) and returns
    nothing. The decorated function takes no arguments and builds the board when
    called: ``<script dir>/<function name>.kicad_pcb``, or ``path`` relative to
    the script's directory. KiCad reads the project library table,
    ``fp-lib-table``, from the board's directory.
    """
    if path is not None and not str(path).endswith(".kicad_pcb"):
        raise ValueError(f"@pcb(path=...) names the board file, so it ends in .kicad_pcb: {path!r}")

    def apply(function: Callable[[Any], Any]) -> Callable[[], BoardBuild]:
        script = Path(inspect.getsourcefile(function) or function.__code__.co_filename).resolve()
        target = script.parent / (path if path is not None else f"{function.__name__}.kicad_pcb")

        @functools.wraps(function)
        def build(*args: Any, **kwargs: Any) -> BoardBuild:
            if args or kwargs:
                raise TypeError(f"{function.__name__}() takes no arguments: calling it builds {target.name}")
            try:
                return _build(function, target)
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception as error:
                if function.__module__ != "__main__":
                    raise
                # Declared in the script being run, the failure is the script's: one line on
                # stderr and exit 1, as a @step script's is. Imported, it is the caller's.
                from cadgen._internal.cli_from_function import report_failure

                report_failure(error, prog=f"python {script.name}", as_json="--json" in sys.argv[1:], verbose="--verbose" in sys.argv[1:])
                raise SystemExit(1) from None

        build.board_path = target  # type: ignore[attr-defined]
        return build

    return apply(func) if func is not None else apply


def connect(cli: Path, settings: Path):
    """A ``cadgen.kipy.KiCad`` on a fresh headless server, its settings in ``settings``.
    The server is the program behind ``cli`` (:func:`cadgen.kicad.install.unwrap`: a
    wrapper script would swallow the signal that stops it), started in this process's
    environment with ``KICAD_CONFIG_HOME`` and the wrapper's variables set for the start
    and restored after it. The one seam between a build and KiCad."""
    from cadgen.kicad.install import unwrap
    from cadgen.kipy import KiCad

    program, environment = unwrap(cli)
    variables = {**environment, "KICAD_CONFIG_HOME": str(settings)}
    previous = {name: os.environ.get(name) for name in variables}
    os.environ.update(variables)
    try:
        return KiCad(headless=True, kicad_cli_path=str(program), timeout_ms=_TIMEOUT_MS)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _start(cli: Path, settings: Path):
    """The connected client, or why KiCad could not be started: a kicad-cli too old to have
    ``api-server`` is the usual reason, and is named as such."""
    from cadgen.kicad.install import check_version, kicad_version
    from cadgen.kipy.errors import ConnectionError as KicadConnectionError

    try:
        kicad = connect(cli, settings)
    except (OSError, TimeoutError, KicadConnectionError) as error:
        version = check_version(cli, kicad_version(cli))
        raise RuntimeError(f"{cli} (KiCad {version}) could not start its API server: {error}") from None
    try:
        version = kicad.get_version()
        check_version(cli, f"{version.major}.{version.minor}.{version.patch}")
    except BaseException:
        kicad.close()
        raise
    return kicad


def signature(board: Path) -> tuple[str | None, str]:
    """``(recorded, actual)`` for a saved board: the hash its ``CADGEN_BUILD`` property
    carries, if any, and the SHA-256 of every other line. KiCad saves the project's text
    variables into the board as ``(property "NAME" "VALUE")`` lines, so the record sits in
    the file it covers and is the one line left out of the hash."""
    recorded = None
    digest = hashlib.sha256()
    for line in board.read_bytes().splitlines(keepends=True):
        if line.lstrip().startswith(_RECORD_LINE):
            recorded = line.split(b'"')[3].decode("ascii", "replace")
            continue
        digest.update(line)
    return recorded, digest.hexdigest()


def _build(function: Callable[[Any], Any], target: Path) -> BoardBuild:
    from cadgen._internal.doors import display_path
    from cadgen.kicad.cli import run_drc
    from cadgen.kicad.install import find_kicad_cli
    from cadgen.kipy.board import Board
    from cadgen.kipy.errors import ApiError
    from cadgen.kipy.proto.common.types.base_types_pb2 import DocumentType
    from cadgen.kipy.proto.common.types.library_types_pb2 import LibraryLoadStatus, LibraryType

    started = time.perf_counter()
    flags = sys.argv[1:]
    if target.exists() and "--force" not in flags:
        recorded, actual = signature(target)
        if recorded != actual:
            raise BoardError(
                f"{display_path(target)} was last saved by something other than this script (KiCad, an "
                "editor, another tool), so the build leaves it alone: pass --force to overwrite it"
            )
    cli = find_kicad_cli()
    target.parent.mkdir(parents=True, exist_ok=True)
    settings = Path(tempfile.mkdtemp(prefix="cadgen-kicad-"))
    try:
        kicad = _start(cli, settings)
        try:
            # An existing file is overwritten by the save: the document starts empty either way.
            document = kicad.create_document(str(target), DocumentType.DOCTYPE_PCB)
            try:
                kicad.load_all_libraries([LibraryType.LT_FOOTPRINT])
                rows = kicad.wait_for_libraries([LibraryType.LT_FOOTPRINT], interval_ms=50, timeout_s=_LIBRARY_TIMEOUT_S)
                table = ", ".join(f"{row.nickname} ({LibraryLoadStatus.Name(row.status)})" for row in rows) or "no rows"
                failed = [row for row in rows if row.status != LibraryLoadStatus.LLS_LOADED]
                if failed:
                    raise BoardError(
                        f"{target.parent / 'fp-lib-table'}: "
                        + "; ".join(f"{row.nickname}: {LibraryLoadStatus.Name(row.status)}" + (f", {row.error_message}" if row.error_message else "") for row in failed)
                    )
                # The board is built on the specifier create_document returned, not on
                # kicad.get_board(): today's nightly reports the open document's project path
                # without its trailing slash, and the project commands (net classes,
                # assignments, text variables) then find no such project. The client is the
                # one thing kipy keeps private here; this is the one place cadgen reaches it.
                board = Board(kicad._client, document)  # noqa: SLF001
                try:
                    function(board)
                except ApiError as error:
                    if "not found" in str(error):
                        raise BoardError(
                            f"{error.raw_message or error}; the project library table {target.parent / 'fp-lib-table'} "
                            f"loaded {table}: add the library the footprint is in"
                        ) from error
                    raise
                board.refill_zones()
                unconnected = _unconnected(board)
                counts = (len(board.get_footprints()), len(board.get_tracks()), len(board.get_vias()), len(board.get_zones()))
                board.save()
                # The record is the saved file's hash, so it is set after the first save and
                # written by a second, which changes the record's own line and no other.
                project = board.get_project()
                variables = project.get_text_variables()
                variables[RECORD] = signature(target)[1]
                project.set_text_variables(variables)
                board.save()
            except BaseException:
                # Nothing is saved. The document is closed unsaved so KiCad takes its own lock
                # file with it; a server that cannot even do that is simply stopped.
                try:
                    kicad.close_document(document)
                except Exception:  # noqa: BLE001 - the failure being raised is the one that matters
                    pass
                raise
            kicad.close_document(document)
        finally:
            kicad.close()
    finally:
        shutil.rmtree(settings, ignore_errors=True)
    drc = None
    if "--no-drc" not in flags:
        findings = tuple(run_drc(cli, target))
        drc = DrcReport(
            errors=sum(1 for finding in findings if finding.severity == "error"),
            warnings=sum(1 for finding in findings if finding.severity == "warning"),
            findings=findings,
        )
    result = BoardBuild(
        board=target,
        project=target.with_suffix(".kicad_pro"),
        parts=counts[0],
        tracks=counts[1],
        vias=counts[2],
        zones=counts[3],
        unconnected=unconnected,
        drc=drc,
        seconds=time.perf_counter() - started,
    )
    print(result.report())
    for line in drc.lines() if drc else ():
        print(line)
    sys.stdout.flush()
    return result


def _unconnected(board) -> int:
    """Pads with no copper path to the first pad of their net, over tracks, vias and the
    filled zones; a net of one pad has nothing to connect."""
    by_net: dict[str, list] = {}
    for pad in board.get_pads():
        if pad.net.name:
            by_net.setdefault(pad.net.name, []).append(pad)
    missing = 0
    for pads in by_net.values():
        if len(pads) < 2:
            continue
        reached = {item.id.value for item in board.get_connected_items([pads[0]])}
        missing += sum(1 for pad in pads[1:] if pad.id.value not in reached)
    return missing


def drc(board: Path) -> ValidationResult:
    """Check the KiCad board BOARD with KiCad's design rule check.

    Runs ``kicad-cli pcb drc`` on the saved file with every severity reported
    and lists each violation and unconnected item with where it is (millimetres
    from the board's origin). The board fails when any error-severity violation
    or any unconnected item exists; warnings are reported and do not fail it.

    board: the .kicad_pcb to check (its .kicad_pro beside it carries the rules).
    """
    from cadgen._internal.validation_door import display_path, failed, resolved_target
    from cadgen.kicad.cli import run_drc
    from cadgen.kicad.install import KicadMissingError, check_version, find_kicad_cli, kicad_version

    target = resolved_target(board, label="pcb")
    if target.suffix.lower() != ".kicad_pcb":
        return failed(target, "target must be a KiCad board (.kicad_pcb)")
    if not target.is_file():
        return failed(target, "file not found")
    try:
        cli = find_kicad_cli()
        check_version(cli, kicad_version(cli))
    except KicadMissingError as error:
        return failed(target, str(error), code="kicad_missing")
    findings = run_drc(cli, target)
    errors = sum(1 for finding in findings if finding.severity == "error")
    unconnected = sum(1 for finding in findings if finding.check == "unconnected")
    warnings = sum(1 for finding in findings if finding.severity == "warning")
    return ValidationResult(
        ok=not (errors or unconnected),
        path=target,
        issues=issues(findings),
        summary="" if errors or unconnected else f"OK {display_path(target)}: DRC clean ({warnings} warning(s))",
    )


class _Namespace(ModuleType):
    """``cadgen.pcb`` is the decorator and the verb namespace in one object: Python gives a
    package one attribute per submodule name, so the module itself is callable."""

    def __call__(self, func: Callable[[Any], Any] | None = None, *, path: str | None = None):
        return pcb(func, path=path)


sys.modules[__name__].__class__ = _Namespace
