"""What the public verb functions return: the JSON line protocol, typed.

Every ``build`` / ``validate`` verb answers with one of these frozen
dataclasses rather than a loose dict, so the library call and the generated CLI
carry the SAME shape — ``--json`` is just ``dataclasses.asdict`` of the value
the library already returned (design/format-doors.md).

Stdlib only, on purpose: importing a result type must never pull in the CAD
kernel, because the public namespaces (``cadgen.step``, ``cadgen.stl``, ...)
import this at module scope and must stay inside the ~0.2s pre-gate budget.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "BuildResult",
    "CompileResult",
    "InspectResult",
    "MeshExportFile",
    "MeshExportResult",
    "SnapshotFile",
    "SnapshotResult",
    "SnapshotTimings",
    "ValidationIssue",
    "ValidationResult",
]


def _display(path: Path | None) -> str:
    """Cwd-relative where that is meaningful, else absolute. Messages only."""
    if path is None:
        return "-"
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except (OSError, ValueError):
        return str(path)


@dataclass(frozen=True)
class CompileResult:
    """The outcome of compiling one document into its tree.

    ``cadgen step compile`` is a STORE action: bytes in, a tree in the store,
    the document itself untouched. It is deliberately not a `build` — nothing
    new appears on disk beside the model — and it is INTERNAL: the doors and
    the viewer compile a document's missing tree on demand, so no skill
    teaches it.
    """

    ok: bool
    #: The document that was compiled. Its bytes are the tree's key.
    document: Path | None
    #: The hash of the tree describing the compiled geometry.
    tree: str | None
    #: True when the tree already existed, so nothing was compiled.
    skipped: bool

    def human_lines(self) -> list[str]:
        head = "current" if self.skipped else "compiled"
        return [f"{head} {_display(self.document) if self.document else (self.tree or '')}"]


@dataclass(frozen=True)
class BuildResult:
    """The outcome of writing one NEW document.

    ``cadgen step build IN OUT`` re-emits an existing document in cadgen's own
    dialect (OCCT read -> tree in the store -> the canonical XCAF writer),
    optionally annotating it with kinematics and animation. Unlike ``compile``,
    something new lands on disk — which is what earns the name.
    """

    ok: bool
    #: The document this build WROTE.
    document: Path | None
    #: The hash of the tree the written document's geometry came from.
    tree: str | None
    #: True when the freshness gate said the output was already current.
    skipped: bool
    #: Declared artifacts produced (or healed) by THIS run. Outputs the ledger
    #: already found current are not listed: the field answers "what did this
    #: run write", not "what does the model declare".
    exports: tuple[Path, ...] = ()
    #: True when the bytes were already current and only the sidecar (the
    #: kinematics/animation annotation) was refreshed.
    sidecar_only: bool = False

    def human_lines(self) -> list[str]:
        if self.sidecar_only:
            return [f"annotated {_display(self.document)} (bytes unchanged)"]
        head = "current" if self.skipped else "built"
        lines = [f"{head} {_display(self.document) if self.document else (self.tree or '')}"]
        lines += [f"wrote {path.suffix.lstrip('.').upper()}: {_display(path)}" for path in self.exports]
        return lines


def _format_bytes(value: float) -> str:
    """GiB past a gigabyte, MiB below it. Matches the exporter's own refusal."""
    if value >= 1024 ** 3:
        return f"{value / 1024 ** 3:.2f} GiB"
    return f"{value / 1024 ** 2:.1f} MiB"


def _animation_summary(animation: dict | None) -> str:
    """`` (showcase, 120 samples @ 30 fps, 4s, 3 moving)`` — what a GLB carries.

    Empty for a static export. The moving count is what catches the clip that
    resolved but animated nothing: a typo'd label throws, but a clip whose
    targets all sit still exports a file that plays and does not move.

    A morph bake adds its own clause, because without it the line is misleading
    twice over: a deforming tube's weights channel counts toward ``moving`` the
    same as a part that travels, so 48 baked tendons read as 48 occurrences on
    the move — and the numbers that decide whether the file is any GOOD (how many
    targets it cost, how close they track, and the playback texture that has to
    fit on a GPU) would appear nowhere a human looks.

    A file the LEDGER served was not re-sampled, so only the request is known and
    the counts it cannot answer are simply absent: `` (showcase, 30 fps)``.
    Printing nothing there would report a clip-carrying file as static.
    """
    if not animation:
        return ""
    parts = [str(animation.get("clip"))]
    samples = animation.get("samples")
    parts.append(
        f"{animation.get('fps')} fps" if samples is None
        else f"{samples} samples @ {animation.get('fps')} fps"
    )
    seconds = animation.get("seconds")
    if seconds is not None:
        parts.append(f"{float(seconds):g}s")
    channels = animation.get("channels")
    if channels is not None:
        parts.append(f"{channels} moving")
    deform = animation.get("deform")
    if isinstance(deform, dict):
        parts.append(
            f"{deform.get('mode')} on {deform.get('nodes')} of them: "
            f"{deform.get('targets')} targets, "
            f"{float(deform.get('deviationMm', 0)):g}mm of {float(deform.get('toleranceMm', 0)):g}mm, "
            f"{_format_bytes(float(deform.get('runtimeBytes', 0)))} at playback"
        )
    return f" ({', '.join(parts)})"


@dataclass(frozen=True)
class MeshExportFile:
    """One mesh output of a format door, and the tolerances it was written at."""

    path: Path
    fmt: str
    #: True when the mesh-export ledger already had this document at this
    #: tolerance pair, so nothing was re-tessellated.
    skipped: bool
    #: The EFFECTIVE pair (run-level arg > declaration > @step model policy >
    #: tessellator default, which is ``None``).
    mesh_tolerance: float | None = None
    mesh_angular_tolerance: float | None = None
    #: The clip baked into this file, for an animated GLB: ``{clip, fps,
    #: samples, seconds, start, channels}``. ``None`` for a static export, which
    #: is every other file this door writes. Reported because the schedule is
    #: DERIVED — a clip states its own duration — so a wrong clip or a wrong
    #: span shows up without opening the file. A ``skipped`` file was not
    #: re-sampled, so ``samples`` and ``channels`` are ``None`` there: the clip
    #: and the request's own schedule are all this side knows.
    animation: dict | None = None


@dataclass(frozen=True)
class MeshExportResult:
    """The outcome of one format door's ``build``."""

    ok: bool
    files: tuple[MeshExportFile, ...] = ()
    #: What an animated export could not carry: an effect ``drop`` froze, tubes
    #: shipped at rest, a span past the end of a clip that does not loop. ``ok``
    #: stays true — these are choices the caller made — but a file that made them
    #: silently is the failure the animated door exists to avoid, so they are IN
    #: the result rather than only on the log, where ``--json`` never sees them.
    warnings: tuple[str, ...] = ()

    def human_lines(self) -> list[str]:
        lines = [
            f"{'current' if entry.skipped else 'wrote'} {entry.fmt.upper()}: "
            f"{_display(entry.path)}{_animation_summary(entry.animation)}"
            for entry in self.files
        ]
        lines += [f"warning: {warning}" for warning in self.warnings]
        return lines


@dataclass(frozen=True)
class SnapshotFile:
    """One file a snapshot run wrote: a still, or a video of an animation clip."""

    path: Path
    #: The encoding the render produced: ``png``, ``mp4``, ``gif``, or whatever
    #: suffix a text output carried. It follows the RENDER, not the request — an
    #: SVG served under a ``.png`` name still reports ``svg``.
    kind: str
    #: What this output framed: the camera preset, ``azimuth:elevation`` pair, or
    #: view label the output declared. Empty when the job named none.
    view: str = ""
    #: WHICH document this file rendered: the job's input path as given. Two
    #: renders of one path are otherwise indistinguishable in the result, so a
    #: stale render reads the same as a fresh one.
    input: str = ""
    #: The hash of the tree this file rendered — the geometry's identity, so
    #: two renders of one path are distinguishable when the tree changed
    #: between them. Empty for inputs that render without a tree (meshes,
    #: drawings, robot descriptions).
    tree: str = ""
    #: ``--video`` only: what the sequence covers. A still leaves all three at
    #: zero. The frames themselves are never here — they are the file.
    frames: int = 0
    fps: int = 0
    seconds: float = 0.0


@dataclass(frozen=True)
class SnapshotTimings:
    """What the run cost. Resolution (building a cold model's package) is NOT in
    here: it happens before the renderer starts and reports its own phases."""

    #: Render jobs in the packet. One for the ``--input`` shortcut, N for a
    #: ``--job`` packet.
    job_count: int = 0
    #: Wall time across every job's render, in milliseconds.
    total_ms: float = 0.0


@dataclass(frozen=True)
class SnapshotResult:
    """The outcome of one snapshot run.

    The renderer answers with a browser payload — base64 image bytes, viewport
    internals, per-stage timings — and none of that is a caller's business: the
    files are already on disk by the time this exists, so what a caller needs is
    WHICH paths were written. ``--json`` is this dataclass, so the library call
    and the CLI report the same thing (design/format-doors.md).
    """

    ok: bool
    #: Every file this run wrote, in the order the packet declared them.
    files: tuple[SnapshotFile, ...] = ()
    #: ``--mode list`` only: the model's part occurrences, each carrying the
    #: ``ref`` that pastes straight into ``--focus``/``--hide`` and ``inspect``.
    #: Empty for every mode that renders.
    parts: tuple[dict, ...] = ()
    #: Non-fatal notes from the renderer (an unresolved selector, a clamped
    #: frame budget). ``ok`` stays true.
    warnings: tuple[str, ...] = ()
    timings: SnapshotTimings = field(default_factory=SnapshotTimings)
    #: ``--debug`` only: how each job's artifact resolved (cache hit, source,
    #: timing), one entry per job that reported any. Empty otherwise.
    debug: tuple[dict, ...] = ()

    def human_lines(self) -> list[str]:
        # A list-mode run writes no files: its whole answer is the inventory —
        # `[]` when the model has no part occurrences — and it is read by an
        # agent, so it stays one compact JSON line.
        if not self.files:
            return [json.dumps(list(self.parts), separators=(",", ":"))]
        lines = [
            # A video says what it covers: the path alone cannot be checked
            # against the clip the caller asked for, and the frame count is the
            # first thing that is wrong when the request was.
            f"saved video: {entry.path} ({entry.frames} frames, {entry.fps} fps, "
            f"{entry.seconds:g}s)"
            if entry.frames
            else f"saved snapshot: {entry.path}"
            for entry in self.files
        ]
        lines += [f"warning: {warning}" for warning in self.warnings]
        return lines


@dataclass(frozen=True)
class InspectResult:
    """The outcome of one ``cadgen step inspect`` subcommand.

    Inspection answers with a DOCUMENT rather than a summary — refs, facts,
    planes, measurements — and that document is the product: an agent reads it,
    and every subcommand shapes it differently. So the typed result carries the
    document rather than flattening it, and adds the two things a caller needs
    without parsing it: whether the inspection succeeded, and which subcommand
    produced it.
    """

    ok: bool
    #: ``refs`` | ``diff`` | ``frame`` | ``measure`` | ``align`` | ``interfere``
    #: | ``validate`` — the inspection that ran.
    command: str
    #: That subcommand's own JSON document, exactly as the CLI prints it.
    report: dict = field(default_factory=dict)

    def human_lines(self) -> list[str]:
        return [json.dumps(self.report, separators=(",", ":"))]


@dataclass(frozen=True)
class ValidationIssue:
    """One conformance finding against a robot description.

    ``code`` and ``hint`` carry what the checkers already produce: the skills
    teach fixing findings BY CODE, so dropping the code at the result boundary
    would make the typed result less useful than the dict it replaced.
    """

    severity: str  # "error" | "warning" | "info"
    message: str
    #: The offending element or reference, when the checker knows it.
    element: str | None = None
    #: The checker's stable identifier for this class of finding.
    code: str | None = None
    #: How to fix it, when the checker has something specific to say.
    hint: str | None = None

    def human_line(self) -> str:
        code = f"{self.code}" if self.code else ""
        element = f" at {self.element}" if self.element else ""
        hint = f" Hint: {self.hint}" if self.hint else ""
        return f"{self.severity}: {code}{element}: {self.message}{hint}"


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of one ``validate`` verb."""

    ok: bool
    path: Path
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)
    #: One line describing what was validated (link/joint counts and so on).
    #: Empty when the document did not parse far enough to describe.
    summary: str = ""

    def human_lines(self) -> list[str]:
        lines = [issue.human_line() for issue in self.issues]
        if self.ok:
            lines.append(self.summary or f"OK {_display(self.path)}")
        else:
            blocking = sum(1 for issue in self.issues if issue.severity == "error")
            lines.append(f"FAILED {_display(self.path)}: {blocking or len(self.issues)} blocking finding(s)")
        return lines
