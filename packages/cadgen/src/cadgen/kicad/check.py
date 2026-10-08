"""KiCad's verdict on a board: fill its zones, run ERC and DRC, keep the result.

:func:`build_board` is what an ``@pcb`` build runs. It stages the project's
three documents in a temporary folder and asks ``kicad-cli`` for:

- the ERC of the schematic;
- the DRC of the board, with the schematic-to-board parity check, after
  refilling every zone (``--refill-zones --save-board``).

A board that asked for autorouting (``board.autoroute()``) is routed by
Freerouting before it is staged (:mod:`cadgen.kicad.route`): its tracks and
vias join cadgen's tree, so KiCad fills around them and checks them like any
the script drew.

KiCad's saved board is read back for one thing only, the copper it filled each
zone with (``filled_polygon``), which is merged into cadgen's own tree by zone
UUID. The board cadgen writes is therefore cadgen's bytes (and the router's)
plus KiCad's fill: the same board always writes the same file.

:func:`check_project` runs the same checks on any KiCad project, a person's
included, for ``cadgen pcb validate``.

Positions in findings are in the board script's coordinates: millimetres, y
up, from the board's drill/place origin (where cadgen puts the script's
origin; on a board KiCad's GUI drew, wherever its author left that origin).
"""

from __future__ import annotations

import copy
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from cadgen.kicad import sexpr
from cadgen.kicad.cli import Finding, drc_findings, erc_findings, run_kicad_cli
from cadgen.kicad.design import Board, DesignError
from cadgen.kicad.install import KicadInstall, find_kicad
from cadgen.kicad.project import project_texts

__all__ = ["BoardBuild", "ProjectCheck", "build_board", "check_project", "fixes", "is_blocking"]

# What to do about the findings whose fix KiCad's own words do not give, in
# the board API's words. Only a board script's build prints these: a project
# drawn in KiCad is fixed in KiCad.
_FIXES = {
    "power_pin_not_driven": (
        "a power input's net has no source ERC can see. Mark the net power_flag=True when it is fed "
        "from off the board (a connector, a battery) or through a passive part (a fuse, a diode, a "
        "ferrite); otherwise connect the output that should drive it"
    ),
    "pin_not_connected": "connect the pin to a net, or board.no_connect(pin) when it is unused",
    "starved_thermal": (
        "the pour reaches a pad through fewer thermal spokes than it needs (crowded pins, a pad at "
        "the pour's edge): run a track from the pad into the pour, or connect pads solid with "
        "board.zone(..., pads=\"solid\")"
    ),
    "solder_mask_bridge": "pads of different nets sit closer than the solder mask can separate: move the parts apart",
    "hole_clearance": (
        "copper is nearer a hole than min_hole_clearance. When both are one part's own (a connector's "
        "pads beside its locating pegs, as its maker drew them), relax the rule for that part alone: "
        'board.rule("""(rule "J1 pads" (constraint hole_clearance (min 0.15mm)) '
        "(condition \"A.memberOfFootprint('J1') && B.memberOfFootprint('J1')\"))\"\"\"); otherwise move the copper"
    ),
}

# A board's custom rules are checked by a rule of cadgen's own, staged after
# them: it fails on every outline segment, so its findings prove KiCad read
# the file. KiCad drops a .kicad_dru it cannot parse -- every rule in it --
# without a word, which would let a board pass checks its author wrote.
_LOADED = "cadgen: custom rules loaded"
_CANARY = (
    f'(rule "{_LOADED}" (severity error) '
    "(constraint assertion \"A.Layer != 'Edge.Cuts'\") (condition \"A.Layer == 'Edge.Cuts'\"))\n"
)
_OUTLINE_ITEMS = ("gr_line", "gr_arc", "gr_circle", "gr_rect", "gr_poly", "gr_curve")


def is_blocking(finding: Finding) -> bool:
    """An error stops a build; an unrouted connection only makes the board a draft; the review only advises."""
    return finding.severity == "error" and finding.check not in ("unconnected", "review")


def _reviewed(tree: list, project: Path, currents: Mapping[str, float] | None = None) -> list[Finding]:
    """The review's findings on a board (``cadgen.kicad.review``), in the script's coordinates."""
    from cadgen.kicad.board_index import read_index
    from cadgen.kicad.review import net_currents, review

    index = read_index(tree, project=project)
    to_script = _to_script(_origin(tree))
    return [
        Finding(
            check=found.check, severity=found.severity, type=found.type, description=found.description,
            items=tuple((item.text, to_script(*item.at) if item.at else None) for item in found.items),
            summary=found.summary,
        )
        for found in review(index, net_currents(project) if currents is None else currents)
    ]


def fixes(findings) -> list[str]:
    """One line per kind of finding whose fix is not in KiCad's message, in the board API's words."""
    kinds = dict.fromkeys(finding.type for finding in findings if finding.type in _FIXES)
    return [f"{kind}: {_FIXES[kind]}" for kind in kinds]


@dataclass(frozen=True)
class ProjectCheck:
    findings: tuple[Finding, ...]

    @property
    def errors(self) -> list[Finding]:
        return [finding for finding in self.findings if is_blocking(finding)]

    @property
    def warnings(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.severity == "warning"]

    @property
    def unrouted(self) -> int:
        return sum(1 for finding in self.findings if finding.check == "unconnected")

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class BoardBuild(ProjectCheck):
    name: str = ""
    pro: str = ""
    sch: str = ""
    pcb: str = ""
    dru: str = ""


def _origin(pcb_tree: list) -> tuple[float, float]:
    setup = sexpr.find(pcb_tree, "setup")
    origin = sexpr.find(setup, "aux_axis_origin") if setup is not None else None
    if origin is None or len(origin) < 3:
        return 0.0, 0.0
    return float(origin[1]), float(origin[2])


def _to_script(origin: tuple[float, float]):
    def convert(x: float, y: float) -> tuple[float, float]:
        return round(x - origin[0], 4), round(origin[1] - y, 4)

    return convert


def _merge_fills(ours: list, kicad_text: str) -> list:
    theirs = sexpr.parse(kicad_text)
    fills: dict[str, tuple[list | None, list[list]]] = {}
    for zone in sexpr.find_all(theirs, "zone"):
        fills[str(sexpr.value(zone, "uuid"))] = (sexpr.find(zone, "fill"), list(sexpr.find_all(zone, "filled_polygon")))
    merged = copy.deepcopy(ours)
    for zone in sexpr.find_all(merged, "zone"):
        found = fills.get(str(sexpr.value(zone, "uuid")))
        if found is None:
            continue
        fill, polygons = found
        if fill is not None:
            for index, child in enumerate(zone):
                if isinstance(child, list) and child and child[0] == "fill":
                    zone[index] = fill
                    break
        zone.extend(polygons)
    return merged


def _has_outline(pcb_tree: list) -> bool:
    return any(
        sexpr.head(item) in _OUTLINE_ITEMS and sexpr.value(item, "layer") == "Edge.Cuts"
        for item in pcb_tree[1:]
        if isinstance(item, list)
    )


def _without_canary(findings: list[Finding]) -> tuple[list[Finding], bool]:
    """KiCad's findings less the canary's, and whether the canary fired."""
    kept = [finding for finding in findings if _LOADED not in finding.description]
    return kept, len(kept) != len(findings)


def build_board(board: Board, *, name: str, install: KicadInstall | None = None, script_root=None) -> BoardBuild:
    """The board's documents, its zones filled by KiCad, and KiCad's findings.

    ``script_root`` is the model script's folder, which the parts' ``Script`` fields are relative to.
    """
    install = install or find_kicad()
    texts = project_texts(board, name=name, script_root=script_root)
    pcb_tree, pcb_text = texts.pcb_tree, texts.pcb
    if board.autoroute_request is not None:
        # Freerouting routes first, so its tracks are filled around and checked like drawn ones.
        from cadgen.kicad.route import route_board

        pcb_tree = route_board(board, pcb_tree, project=texts.pro, name=name).tree
        pcb_text = sexpr.dumps(pcb_tree)
    with tempfile.TemporaryDirectory(prefix="cadgen-pcb-") as folder:
        stage = Path(folder)
        (stage / f"{name}.kicad_pro").write_text(texts.pro)
        (stage / f"{name}.kicad_sch").write_text(texts.sch)
        (stage / f"{name}.kicad_pcb").write_text(pcb_text)
        (stage / f"{name}.kicad_dru").write_text(texts.dru + (_CANARY if board.design_rules else ""))
        run_kicad_cli(install, ["sch", "erc", "--format", "json", "-o", "erc.json", f"{name}.kicad_sch"], cwd=stage)
        run_kicad_cli(
            install,
            ["pcb", "drc", "--format", "json", "--schematic-parity", "--refill-zones", "--save-board", "-o", "drc.json", f"{name}.kicad_pcb"],
            cwd=stage,
        )
        board_findings, loaded = _without_canary(drc_findings(stage / "drc.json", to_script=_to_script(_origin(pcb_tree))))
        if board.design_rules and not loaded:
            raise DesignError(
                "KiCad could not read the board's custom rules, so it applied none of them: a board.rule(...) "
                "has a mistake KiCad's rule parser rejects (an unknown constraint, property or function, or a "
                "condition that is not an expression). Check each against KiCad's custom rules syntax."
            )
        findings = erc_findings(stage / "erc.json") + board_findings
        filled = _merge_fills(pcb_tree, (stage / f"{name}.kicad_pcb").read_text())
        findings += _reviewed(filled, stage / f"{name}.kicad_pro", board.net_currents)
    return BoardBuild(findings=tuple(findings), name=name, pro=texts.pro, sch=texts.sch, pcb=sexpr.dumps(filled), dru=texts.dru)


def check_project(path: Path, *, install: KicadInstall | None = None) -> ProjectCheck:
    """ERC and DRC of the KiCad project ``path`` (its ``.kicad_pcb``, ``.kicad_sch`` or ``.kicad_pro``).

    The project's KiCad files are copied to a temporary folder first, so
    checking a project never writes into it.
    """
    install = install or find_kicad()
    path = Path(path).expanduser().resolve()
    if path.suffix not in {".kicad_pcb", ".kicad_sch", ".kicad_pro"}:
        raise ValueError(f"{path.name} is not a KiCad project file (.kicad_pcb, .kicad_sch or .kicad_pro)")
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist")
    stem, folder = path.stem, path.parent
    pcb, sch = folder / f"{stem}.kicad_pcb", folder / f"{stem}.kicad_sch"
    if not pcb.is_file() and not sch.is_file():
        raise FileNotFoundError(f"{folder} has neither {stem}.kicad_pcb nor {stem}.kicad_sch")
    findings: list[Finding] = []
    with tempfile.TemporaryDirectory(prefix="cadgen-pcb-check-") as staging:
        stage = Path(staging)
        for entry in folder.iterdir():
            if entry.is_file() and (entry.suffix.startswith(".kicad_") or entry.name.endswith("-lib-table")):
                shutil.copy2(entry, stage / entry.name)
        if sch.is_file():
            run_kicad_cli(install, ["sch", "erc", "--format", "json", "-o", "erc.json", sch.name], cwd=stage)
            findings.extend(erc_findings(stage / "erc.json"))
        if pcb.is_file():
            tree = sexpr.parse(pcb.read_text(encoding="utf-8"))
            rules = stage / f"{stem}.kicad_dru"
            canary = rules.is_file() and _has_outline(tree)
            if canary:
                rules.write_text(rules.read_text(encoding="utf-8").rstrip() + "\n" + _CANARY, encoding="utf-8")
            args = ["pcb", "drc", "--format", "json", "--refill-zones", "-o", "drc.json", pcb.name]
            if sch.is_file():
                args.insert(4, "--schematic-parity")
            run_kicad_cli(install, args, cwd=stage)
            board_findings, loaded = _without_canary(drc_findings(stage / "drc.json", to_script=_to_script(_origin(tree))))
            if canary and not loaded:
                board_findings.insert(0, Finding(
                    check="drc",
                    severity="error",
                    type="custom_rules_unreadable",
                    description=(
                        f"KiCad could not read {rules.name}, so it applied none of its custom rules: one has a "
                        "mistake KiCad's rule parser rejects (open Board Setup > Custom Rules and check the syntax)"
                    ),
                    items=(),
                ))
            findings.extend(board_findings)
            findings.extend(_reviewed(tree, stage / f"{stem}.kicad_pro"))
    return ProjectCheck(findings=tuple(findings))
