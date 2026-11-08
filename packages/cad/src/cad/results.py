"""The operations' shared result types: what every check returns, typed.

Every check -- ``dfm``, ``solve``, ``drc``, ``erc`` and ``validate`` (``cad.urdf.validate``, ``cad.stl.dfm``,
``cad.kicad_pcb.drc``, ...) -- answers with a ``CheckResult`` (a stress study's, ``FeaResult``, one with its setup and
the files its solve wrote) -- whether it passed, the file, its findings, each with a severity, a code
and a location, and what it measured, where it measures -- rather than a loose dict, so the library call
and the CLI carry the SAME shape: ``cad <type> dfm --json`` is ``dataclasses.asdict`` of the value the library returned.
``ValidationResult`` and ``ValidationIssue``, their 0.10 names, are aliases that take the 0.10 call shapes
(``ValidationIssue(severity, message, element=, code=, hint=)``, ``ValidationResult(ok, path, issues=,
summary=)``) and make these.

Stdlib only, on purpose: importing a result type must never pull in the CAD kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["CheckFinding", "CheckResult", "ExportResult", "FeaFace", "FeaPair", "FeaPart", "FeaResult"]


def _display(path: Path | None) -> str:
    """Cwd-relative where that is meaningful, else as given. Messages only."""
    if path is None:
        return "-"
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except (OSError, ValueError):
        return str(path)


@dataclass(frozen=True)
class CheckFinding:
    """One finding of a check (``dfm``, ``drc``, ``erc``, ``validate``).

    ``code`` and ``hint`` carry what the checkers already produce: the skills
    teach fixing findings BY CODE, so dropping the code at the result boundary
    would make the typed result less useful than the dict it replaced.
    """

    severity: str  # "error" | "warning" | "info"
    #: The checker's stable identifier for this class of finding.
    code: str | None
    message: str
    #: Where in the file: the offending element or reference, when the checker knows it.
    location: str | None = None
    #: How to fix it, when the checker has something specific to say.
    hint: str | None = None

    @property
    def element(self) -> str | None:
        """Its location, by the name it had before checks shared one shape."""
        return self.location

    def human_line(self) -> str:
        code = f"{self.code}" if self.code else ""
        element = f" at {self.location}" if self.location else ""
        hint = f" Hint: {self.hint}" if self.hint else ""
        return f"{self.severity}: {code}{element}: {self.message}{hint}"


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check (``dfm``, ``drc``, ``erc``, ``validate``)."""

    ok: bool
    path: Path
    findings: tuple[CheckFinding, ...] = field(default_factory=tuple)
    #: One line describing what was validated (link/joint counts and so on).
    #: Empty when the document did not parse far enough to describe.
    summary: str = ""
    #: What the check measured, by family, as plain data (a manufacturing check's draft, undercuts,
    #: walls, ...); empty for a check that measures nothing.
    measurements: dict[str, Any] = field(default_factory=dict)

    @property
    def issues(self) -> tuple[CheckFinding, ...]:
        """Its findings, by the name they had before checks shared one shape."""
        return self.findings

    def human_lines(self) -> list[str]:
        lines = [finding.human_line() for finding in self.findings]
        if self.ok:
            lines.append(self.summary or f"OK {_display(self.path)}")
        else:
            blocking = sum(1 for finding in self.findings if finding.severity == "error")
            lines.append(f"FAILED {_display(self.path)}: {blocking or len(self.findings)} blocking finding(s)")
        return lines


@dataclass(frozen=True)
class ExportResult:
    """The outcome of an ``export`` that writes files of its own kinds (``cad.kicad_pcb.export``): the
    source, what it was exported as, the files written, and what was said beside (a part without its 3D
    model), one line each."""

    path: Path
    to: str
    written: tuple[Path, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def human_lines(self) -> list[str]:
        return [*(f"warning: {line}" for line in self.warnings), *(f"wrote {path}" for path in self.written)]


@dataclass(frozen=True)
class FeaFace:
    """One B-rep face of a part, as a stress study's setup lists it (``cad <type> solve`` with no study): the ref a
    study names it by, and enough geometry to pick it from a description."""

    #: The face's ref (``bracket/face 17``), as the viewer copies it.
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
class FeaPart:
    """One part of a document, as a stress study's setup lists it."""

    #: The part occurrence's ref (``arm``).
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

    def line(check: dict) -> str:
        # A share under 1 % reads "0.00×" to two places: say it is under 1 % of the limit instead.
        share = "under 1% of it" if 0 <= check["ratio"] < 0.01 else f"{check['ratio']:.2f}× it"
        return (f"check '{check['label']}': {check['value']:g}{unit(check)} against a {check['limit']:g}{unit(check)} limit, "
                f"{share}, {check['status']}")

    return [line(check) for check in s.get("checks", [])]


@dataclass(frozen=True)
class FeaResult(CheckResult):
    """The outcome of a stress study (``cad.<type>.solve``, ``cad <type> solve``; ``result.json`` in the folder a solve
    writes holds it): a check, so ``ok``, the document
    (``path``), its findings and ``measurements`` are every check's, and ``--json`` is this whole result.

    With no study it is the study's setup, which writes nothing: the document's parts (``parts``), the pairs that
    touch within the contact tolerance a study bonds by (``pairs``, ``contact_tolerance_mm``) and the faces of one
    part (``faces``, of ``occurrence``), each with the ref a study names it by. Overlapping parts are a warning.

    With a study it is the solve: ``written`` the files it wrote into its folder (``result.json``, ``result.glb``,
    ``result.vtu``, the pictures where they could be drawn, ``ccx.inp`` where asked), and ``measurements`` the numbers -- an engineer's first answer (the peak von Mises stress, nodal and at
    the integration points, the safety factor, the largest displacement, the applied force against the reactions,
    an assembly's weakest part and each part's own), each check the study asked for judged (``checks``), and what
    the file's fields do not carry under its own key (``mesh``, ``timings``, the ``study`` as given, its ``material``, each
    named face in ``named_faces``, each fixture's reaction, an assembly's ``connections`` and ``overlaps``, the
    first solve when a finer one was written in ``refined``). ``ok`` is the validators' rule: false when any
    finding is an error -- the part yields or misses a check, whose result is written all the same since it shows
    where the part fails, or the study stopped before the solve (a part nothing holds), with nothing written.
    """

    #: The part the faces are of (setup), or the occurrence or assembly solved.
    occurrence: str = ""
    #: The files the solve wrote into its folder; none for a setup or a study stopped early.
    written: tuple[Path, ...] = field(default_factory=tuple)
    contact_tolerance_mm: float | None = None
    parts: tuple[FeaPart, ...] = field(default_factory=tuple)
    pairs: tuple[FeaPair, ...] = field(default_factory=tuple)
    faces: tuple[FeaFace, ...] = field(default_factory=tuple)

    def _written(self, name: str) -> Path | None:
        return next((Path(path) for path in self.written if Path(path).name == name), None)

    @property
    def folder(self) -> Path | None:
        """The folder the solve wrote its results into, or None (a setup, or a study stopped before the solve)."""
        found = self._written("result.json")
        return None if found is None else found.parent

    @property
    def glb(self) -> Path | None:
        """``result.glb``: the deformed surface coloured by its stress, which any viewer opens."""
        return self._written("result.glb")

    @property
    def vtu(self) -> Path | None:
        """``result.vtu``: the volume mesh and its fields, for meshio, PyVista or ParaView."""
        return self._written("result.vtu")

    @property
    def pictures(self) -> tuple[Path, ...]:
        """``stress.png`` and ``displacement.png``, where the engine's stills could draw them; else none."""
        return tuple(found for name in ("stress.png", "displacement.png") if (found := self._written(name)))

    @property
    def deck(self) -> Path | None:
        """``ccx.inp``, the input CalculiX solved, where the solve was asked to keep it; or None."""
        return self._written("ccx.inp")

    @property
    def solved(self) -> bool:
        """Whether this is a solve's result: a study ran and its results were written."""
        return self.folder is not None

    def as_data(self) -> dict[str, Any]:
        """The result as plain data, as ``--json`` prints it and ``result.json`` holds it: paths as text, tuples as
        lists. :meth:`from_data` reads it back."""
        import dataclasses

        def plain(value: Any) -> Any:
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, dict):
                return {str(key): plain(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [plain(item) for item in value]
            return value

        return plain(dataclasses.asdict(self))

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "FeaResult":
        """The result again from its data (``dataclasses.asdict`` of one, as ``--json`` and the runner of one operation
        carry it)."""
        return cls(ok=bool(data["ok"]), path=Path(data["path"]),
                   findings=tuple(CheckFinding(**finding) for finding in data.get("findings") or ()),
                   summary=str(data.get("summary") or ""), measurements=dict(data.get("measurements") or {}),
                   occurrence=str(data.get("occurrence") or ""),
                   written=tuple(Path(path) for path in data.get("written") or ()),
                   contact_tolerance_mm=data.get("contact_tolerance_mm"),
                   parts=tuple(FeaPart(**part) for part in data.get("parts") or ()),
                   pairs=tuple(FeaPair(**{**pair, "between": tuple(pair["between"]), "refs": tuple(pair["refs"])})
                               for pair in data.get("pairs") or ()),
                   faces=tuple(FeaFace(**{**face, "center_mm": tuple(face["center_mm"]),
                                          "normal": None if face.get("normal") is None else tuple(face["normal"])})
                               for face in data.get("faces") or ()))

    def human_lines(self) -> list[str]:
        lines = self._solve_lines() if self.solved else self._setup_lines()
        lines += [finding.human_line() for finding in self.findings]
        if not self.ok:
            blocking = sum(1 for finding in self.findings if finding.severity == "error")
            lines.append(f"FAILED {_display(self.path)}: {blocking or len(self.findings)} blocking finding(s)")
        return lines

    def _setup_lines(self) -> list[str]:
        if not self.parts and not self.faces:
            return [f"not solved: {_display(self.path)}"]
        overlapping = sum(1 for pair in self.pairs if pair.type == "overlapping")
        near = sum(1 for pair in self.pairs if pair.type == "not_connected")
        touching = (
            f"{len(self.pairs) - overlapping - near} touching pairs"
            + (f", {near} near {'miss' if near == 1 else 'misses'}" if near else "")
            + (f", {overlapping} overlapping" if overlapping else "")
        )
        lines = [f"{_display(self.path)}: {len(self.parts)} parts, {touching}"]
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
        if self.faces:
            lines.append(f"{self.occurrence}: {len(self.faces)} faces")
            for face in self.faces:
                c = face.center_mm
                lines.append(
                    f"  {face.ref:<10} {face.area_mm2:>10.2f} mm^2  at ({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f})  {face.hint}")
        return lines

    def _solve_lines(self) -> list[str]:
        from cad._internal.fea.checks import safety_factor_text  # stdlib only; kept out of module import time

        s = self.measurements
        mesh = s.get("mesh") or {}
        size = f"{mesh.get('elements')} tets, {mesh.get('dofs')} DOF, {mesh.get('size_mm')} mm elements"

        solver = f"; solver {mesh['solver']}" if mesh.get("solver") else ""
        return [
            f"solved {self.occurrence} of {_display(self.path)}: {size}{solver}",
            *_stress_lines(s, safety_factor_text),
            *_check_lines(s),
            f"max displacement {s.get('max_displacement_mm')} mm at {s.get('max_displacement_at_mm')}",
            f"applied {s.get('applied_force_N')} N, reactions {s.get('reaction_force_N')} N",
            f"wrote {', '.join(Path(path).name for path in self.written)} into {_display(self.folder)} "
            f"(deformation x{s.get('deformation_scale')} in result.glb and the pictures)",
        ]


class _ValidationIssue(CheckFinding):
    """``ValidationIssue``, 0.10's name and call shape for a finding: ``(severity, message, element=None,
    code=None, hint=None)``, its location read as ``element`` as ever."""

    def __init__(self, severity: str, message: str, element: str | None = None, code: str | None = None,
                 hint: str | None = None) -> None:
        super().__init__(severity, code, message, element, hint)


class _ValidationResult(CheckResult):
    """``ValidationResult``, 0.10's name and call shape for a result: ``(ok, path, issues=(), summary="")``, its
    findings read as ``issues`` as ever."""

    def __init__(self, ok: bool, path: Path, issues: tuple[CheckFinding, ...] = (), summary: str = "") -> None:
        super().__init__(ok, path, tuple(issues), summary)


def __getattr__(name: str):
    from cad._internal.aliases import lookup

    return lookup(__name__, name)
