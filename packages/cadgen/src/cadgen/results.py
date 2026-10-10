"""What the public verb functions return: the JSON line protocol, typed.

Every ``build`` / ``validate`` verb answers with one of these frozen
dataclasses rather than a loose dict, so the library call and the generated CLI
carry the SAME shape — ``--json`` is just ``dataclasses.asdict`` of the value
the library already returned.

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
    "FeaFace",
    "FeaFacesResult",
    "FeaPair",
    "FeaPart",
    "FeaPartsResult",
    "FeaResult",
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
    from cadgen._internal.doors import display_path

    return "-" if path is None else display_path(path)


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
    #: True when the bytes were already current and only the sidecar (the
    #: kinematics/animation annotation) was refreshed.
    sidecar_only: bool = False

    def human_lines(self) -> list[str]:
        if self.sidecar_only:
            return [f"annotated {_display(self.document)} (bytes unchanged)"]
        head = "current" if self.skipped else "built"
        return [f"{head} {_display(self.document) if self.document else (self.tree or '')}"]


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
    #: The EFFECTIVE pair the file was written at: the door's argument, else the
    #: tessellator's default (1.5e-3 / 0.35) -- a number either way, never null.
    #: A door reads no model declaration.
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
    internals, per-stage timings — the normal result omits that payload: the
    files are already on disk by the time this exists, so what a caller needs is
    WHICH paths were written. ``--json`` is this dataclass, so the library call
    and the CLI report the same thing.
    """

    ok: bool
    #: Every file this run wrote, in the order the packet declared them.
    files: tuple[SnapshotFile, ...] = ()
    #: ``--mode list`` only: the model's part occurrences, each carrying the
    #: ``ref`` accepted by ``--focus``/``--hide`` and ``scene.resolve(ref)``.
    #: Empty for every mode that renders.
    parts: tuple[dict, ...] = ()
    #: Non-fatal notes from the renderer (an unresolved selector, a clamped
    #: frame budget). ``ok`` stays true.
    warnings: tuple[str, ...] = ()
    timings: SnapshotTimings = field(default_factory=SnapshotTimings)
    #: ``--debug`` only: artifact resolution and measured browser stages,
    #: one attributed entry per job that reported any. Empty otherwise.
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
        # `--debug` without `--json` still answers: one compact JSON line per input,
        # so the diagnostics asked for are never computed and then thrown away.
        lines += [f"debug: {json.dumps(entry, separators=(',', ':'), sort_keys=True)}" for entry in self.debug]
        return lines


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


@dataclass(frozen=True)
class FeaFace:
    """One B-rep face of a part, as ``cadgen fea faces`` lists it: the selector a
    study names it by, and enough geometry to pick it from a description."""

    #: The viewer's selector (``#o1.f17``).
    ref: str
    area_mm2: float
    #: Centre of mass, mm.
    center_mm: tuple[float, float, float]
    #: ``plane``, ``cylinder``, ``torus``, ... (the underlying surface type).
    surface: str
    #: Unit normal for a plane, else ``None``.
    normal: tuple[float, float, float] | None
    #: ``plane, normal -Z, largest`` -- words an agent can match to a request.
    hint: str


@dataclass(frozen=True)
class FeaFacesResult:
    """The outcome of ``cadgen fea faces``: the faces of one part occurrence."""

    ok: bool
    document: Path
    occurrence: str
    faces: tuple[FeaFace, ...] = ()

    def human_lines(self) -> list[str]:
        lines = [f"{self.occurrence} in {_display(self.document)}: {len(self.faces)} faces"]
        for face in self.faces:
            c = face.center_mm
            lines.append(
                f"  {face.ref:<10} {face.area_mm2:>10.2f} mm^2  at ({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f})  {face.hint}"
            )
        return lines


def _stress_lines(s: dict, safety_factor_text) -> list[str]:
    """The stress lines of a result: one scope per line (the part, then the assembly, then each part)."""
    def factor(value):
        return "n/a" if value is None else safety_factor_text(value)

    if not s.get("weakest_part"):
        return [
            f"max von Mises {s.get('max_von_mises_MPa')} MPa (Gauss {s.get('max_von_mises_gauss_MPa')} MPa), "
            f"yield {s.get('yield_MPa')} MPa, safety factor {factor(s.get('safety_factor'))}"
        ]
    lines = [
        f"weakest part '{s['weakest_part']}': peak {s.get('weakest_part_peak_MPa')} MPa, "
        f"yield {s.get('yield_MPa')} MPa, safety factor {factor(s.get('safety_factor'))}",
        f"assembly peak von Mises {s.get('max_von_mises_MPa')} MPa (Gauss {s.get('max_von_mises_gauss_MPa')} MPa)",
    ]
    for part in s.get("parts", []):
        lines.append(
            f"  '{part['name']}' ({part['material']}): peak {part['peak_MPa']} MPa, yield {part['yield_MPa']} MPa, "
            f"safety factor {factor(part['safety_factor'])}, moves up to {part['max_displacement_mm']} mm"
        )
    return lines


def _check_lines(s: dict) -> list[str]:
    """One line per check the study asked for: what it measured against its limit, and whether it passes."""
    def unit(check: dict) -> str:  # " MPa", or nothing for a unitless check (a safety factor)
        return f" {check['unit']}" if check["unit"] else ""

    return [
        f"check '{check['label']}': {check['value']:g}{unit(check)} against a {check['limit']:g}{unit(check)} limit, "
        f"{check['ratio']:.2f}× it, {check['status']}"
        for check in s.get("checks", [])
    ]


@dataclass(frozen=True)
class FeaResult:
    """The outcome of ``cadgen fea solve``: where the results went, and the numbers.

    ``summary`` carries the answer an engineer asks for first: max von Mises
    (nodal and Gauss-point), safety factor against yield, max displacement,
    the applied-versus-reaction balance, and each check the study asked for
    judged (``checks``: the verdict's). Another ``analysis`` (modal, thermal,
    ...) writes its own summary and CLI lines. ``fit`` lists the steps the
    fit-the-budget ladder took, each printed as an "adapted: ..." line. ``findings`` is what an engineer
    would say about it, errors first, in the KiCad findings' shape. The GLB is
    what the viewer shows; the JSON sidecar holds this whole result plus the
    study it came from.
    """

    ok: bool
    document: Path
    occurrence: str
    #: ``None`` when the study stopped before the solve (``ok`` is false; ``findings`` say why).
    glb: Path | None
    sidecar: Path | None
    vtu: Path | None = None
    summary: dict = field(default_factory=dict)
    mesh: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    findings: tuple[dict, ...] = ()
    #: The analysis that was run (``static`` unless the study named another).
    analysis: str = "static"
    #: The fit-the-budget ladder's steps, in order (``rung``, ``words``, ``accuracy``, ...); empty when none was taken.
    fit: tuple[dict, ...] = ()

    def human_lines(self) -> list[str]:
        from cadgen._internal.fea.checks import safety_factor_text  # stdlib only; kept out of module import time

        if not self.ok:
            return [f"not solved: {_display(self.document)}"] + [f"{finding['severity']}: {finding['summary']}" for finding in self.findings]
        if self.analysis != "static":
            return self._analysis_lines()
        s = self.summary
        safety = s.get("safety_factor")
        lines = [
            f"solved {self.occurrence} of {_display(self.document)}: {self.mesh.get('elements')} tets, "
            f"{self.mesh.get('dofs')} DOF, {self.mesh.get('size_mm')} mm elements",
            *_stress_lines(s, safety_factor_text),
            *_check_lines(s),
            f"max displacement {s.get('max_displacement_mm')} mm at {s.get('max_displacement_at_mm')}",
            f"applied {s.get('applied_force_N')} N, reactions {s.get('reaction_force_N')} N",
            f"wrote GLB: {_display(self.glb)} (deformation x{s.get('deformation_scale')}), sidecar: {_display(self.sidecar)}"
            + (f", VTU: {_display(self.vtu)}" if self.vtu else ""),
        ]
        lines += self._fit_lines()
        lines += [f"{finding['severity']}: {finding['summary']}" for finding in self.findings]
        lines += [f"warning: {warning}" for warning in self.warnings]
        return lines

    def _fit_lines(self) -> list[str]:
        """One line per fit-the-budget step: what was adapted, and what it may have cost."""
        return [
            f"adapted: {step['words']}" + (f" ({step['accuracy']})" if step.get("accuracy") else "")
            for step in self.fit
        ]

    def _analysis_lines(self) -> list[str]:
        """A non-static analysis: its own lines (``Analysis.human_lines``), then the files, fit steps, findings and warnings."""
        from cadgen._internal.fea.analyses import get_analysis  # stdlib only; kept out of module import time

        lines = [
            f"solved {self.occurrence} of {_display(self.document)} ({self.analysis}): {self.mesh.get('elements')} tets, "
            f"{self.mesh.get('dofs')} DOF, {self.mesh.get('size_mm')} mm elements",
            *get_analysis(self.analysis).human_lines(self.summary),
            *_check_lines(self.summary),
            f"wrote GLB: {_display(self.glb)}, sidecar: {_display(self.sidecar)}" + (f", VTU: {_display(self.vtu)}" if self.vtu else ""),
        ]
        lines += self._fit_lines()
        lines += [f"{finding['severity']}: {finding['summary']}" for finding in self.findings]
        lines += [f"warning: {warning}" for warning in self.warnings]
        return lines


@dataclass(frozen=True)
class FeaPart:
    """One part of an assembly, as ``cadgen fea parts`` lists it."""

    #: The occurrence selector (``#o1.2``), what a study's faces are scoped by.
    ref: str
    name: str
    volume_mm3: float


@dataclass(frozen=True)
class FeaPair:
    """Two parts that touch or nearly touch, and what a study does with them by default."""

    #: The part names, the smaller part (the one attached) first.
    between: tuple[str, str]
    refs: tuple[str, str]
    #: The area the two faces share, mm^2.
    area_mm2: float
    #: The gap between the faces, mm (0 = touching).
    gap_mm: float
    #: ``bonded`` (glued into one body), ``not_connected`` (too far apart to bond) or
    #: ``overlapping`` (the solids share volume, so the pair is not bonded).
    type: str
    #: The volume the two solids share, mm^3 (``overlapping`` only).
    overlap_mm3: float = 0.0
    #: How deep the solids overlap, mm, for an interference within the tolerance: ``bonded``, the glue closes it.
    interference_mm: float = 0.0


@dataclass(frozen=True)
class FeaPartsResult:
    """The outcome of ``cadgen fea parts``: the parts of an assembly and its touching pairs."""

    ok: bool
    document: Path
    contact_tolerance_mm: float
    parts: tuple[FeaPart, ...] = ()
    pairs: tuple[FeaPair, ...] = ()

    def human_lines(self) -> list[str]:
        overlapping = sum(1 for pair in self.pairs if pair.type == "overlapping")
        near = sum(1 for pair in self.pairs if pair.type == "not_connected")
        touching = (
            f"{len(self.pairs) - overlapping - near} touching pairs"
            + (f", {near} near {'miss' if near == 1 else 'misses'}" if near else "")
            + (f", {overlapping} overlapping" if overlapping else "")
        )
        lines = [f"{_display(self.document)}: {len(self.parts)} parts, {touching}"]
        for part in self.parts:
            lines.append(f"  {part.ref:<8} {part.name}  {part.volume_mm3:.4g} mm^3")
        for pair in self.pairs:
            a, b = pair.between
            if pair.type == "overlapping":
                lines.append(f"{a} ↔ {b} · overlapping · {pair.overlap_mm3:.4g} mm³")
            elif pair.type == "bonded":
                gap = f" · gap {pair.gap_mm:.3g} mm" if pair.gap_mm else ""
                gap += f" · interference {pair.interference_mm:.2g} mm" if pair.interference_mm else ""
                lines.append(f"{a} ↔ {b} · {pair.area_mm2:.4g} mm²{gap} · bonded")
            else:
                lines.append(f"{a} ↔ {b} · gap {pair.gap_mm:.3g} mm · not connected")
        return lines
