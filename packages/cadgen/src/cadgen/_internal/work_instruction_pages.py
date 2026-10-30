"""The pages of a work instruction: each step's picture, and the PDF.

The document is laid out the way aerospace shops lay out a work instruction or
a NASA/AFRL assembly procedure: front pages (title block, scope, applicable
documents with their revisions, safety, parts, materials with lot and expiry
blanks, equipment with calibration blanks, the operations overview, open
items, revisions, approvals), then the procedure as a ruled table -- one row
per action, STEP | INSTRUCTION | FIGURE | TECH | QA -- with WARNING, CAUTION
and NOTE boxed above the step they govern, operation headings between groups
of steps, and a QA close-out row at the end. Every page carries the
instruction's number, revision and ``PAGE n OF m``.

``write_pdf`` lays the document out as pages of draw commands first, so every
page's header can say ``PAGE n OF m``, then renders them with matplotlib to a
temporary file renamed into place: a failed run leaves no document behind.

The pictures are one snapshot job, drawn by the engine: for each step the
assembly as it stands after the step, as hidden-line art -- black edges on
faces of the page's colour, so the one colour on the page means what the
legend says. Parts a later step installs are hidden. The parts the step
installs are filled: the snapshot draws them in one flat colour
(``display.tint``), so a fill is exactly where those parts show. The surfaces
the step names (a bond line, a mating face) are outlined in a second colour.
Each picture's camera looks from the instruction's direction (or its step's
own) and is placed exactly, not fitted to what is visible: on the step's parts
(``frame="step"``, the default), so the view moves from step to step, or on the
whole assembly (``frame="assembly"``), the same camera on every such picture.
"""

from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from cadgen.work_instruction import UNNAMED, Source

FILL = "#79a9f3"  # the parts a step installs: a light blue the black edges read over
SURFACE = "#8250df"
PICTURE_PX = (800, 600)
PAGE_MM = {"A4": (210.0, 297.0), "LETTER": (215.9, 279.4)}
MARGIN = 12.0
PT = 25.4 / 72.0  # millimetres per point
BODY, SMALL, HEAD, TITLE = 8.0, 6.5, 11.0, 15.0
LEAD = 1.3  # line height, in multiples of the font size
RULE = "#999999"


# --- pictures ----------------------------------------------------------------


@dataclass(frozen=True)
class Picture:
    """What one step's picture shows: by leaf occurrence ref."""

    step: int
    hide: tuple[str, ...]
    tint: tuple[str, ...]
    surfaces: tuple[str, ...]
    camera: str
    frame: str = "step"
    focus: tuple[str, ...] = ()  # what a step-framed figure fits: its parts, else its marked faces' parts


def picture_plan(wi) -> list[Picture]:
    """Each step that has a picture: what it hides, tints and marks. A step with
    nothing installed yet (a preparation step before the first part) has none."""
    leaves = [leaf.ref for leaf in wi.leaves()]
    installed: set[str] = set()
    plan = []
    for step in wi.steps:
        installed.update(step.install)
        surfaces = tuple(ref for op in step.ops for ref, _owner in op.surfaces)
        for ref, owner in (pair for op in step.ops for pair in op.surfaces):
            if owner not in installed:
                raise ValueError(
                    f"step {step.label} marks {ref}, on {owner}, which no step up to and including step "
                    f"{step.label} installs"
                )
        if not (wi.pictures and step.picture and installed):
            continue
        plan.append(Picture(step.number, tuple(ref for ref in leaves if ref not in installed),
                            step.install, surfaces, step.camera or wi.camera, step.frame,
                            step.install or tuple(dict.fromkeys(owner for op in step.ops
                                                                for _ref, owner in op.surfaces))))
    return plan


def _outline(mark_id: str, face, color: str, tolerance: float) -> dict:
    """A stroke round a face's outer boundary, in the document's frame (a document's scene
    coordinates are its millimetres)."""
    wire = face.outer_wire()
    count = max(16, min(512, int(wire.length / max(tolerance * 4, 1e-6))))
    points = [wire.position_at(i / count) for i in range(count)]
    return {"id": mark_id, "kind": "stroke", "color": color, "width": 4, "closed": True,
            "points": [round(c, 4) for point in points for c in (point.X, point.Y, point.Z)]}


def _extent(wi) -> tuple[list[float], float]:
    """The whole assembly's centre and bounding diagonal. A figure framed on the whole assembly
    (``frame="assembly"``) is fitted to both; one framed on its step (the default, ``_fit_step``)
    takes its distance from the diagonal and is sized within it."""
    from build123d import Compound

    box = Compound([leaf.shape() for leaf in wi.leaves()]).bounding_box()
    centre = [(box.min.X + box.max.X) / 2, (box.min.Y + box.max.Y) / 2, (box.min.Z + box.max.Z) / 2]
    return [round(c, 4) for c in centre], math.dist((box.min.X, box.min.Y, box.min.Z),
                                                    (box.max.X, box.max.Y, box.max.Z))


def _fit_step(leaves, picture, diagonal: float) -> tuple[list[float], float]:
    """Frame a figure on the parts its step installs, with room around them for
    what they go onto: half-height the parts' own size (about twice their extent
    across the figure), never under a tenth of the assembly nor over half of it."""
    from build123d import Compound

    box = Compound([leaves[ref].shape() for ref in picture.focus]).bounding_box()
    centre = [round((lo + hi) / 2, 4) for lo, hi in ((box.min.X, box.max.X), (box.min.Y, box.max.Y),
                                                     (box.min.Z, box.max.Z))]
    size = math.dist((box.min.X, box.min.Y, box.min.Z), (box.max.X, box.max.Y, box.max.Z))
    return centre, min(max(size, 0.1 * diagonal), 0.5 * diagonal)


def _camera(preset: str, target: list[float], half: float, diagonal: float) -> dict:
    """The snapshot's own camera object for a preset direction, placed exactly: the position
    along the preset's direction from the target, its up, and the orthographic half-height."""
    from cadgen.engine.render.occt import PRESETS

    direction, up = PRESETS[preset]
    norm = math.sqrt(sum(c * c for c in direction))
    position = [round(t + c / norm * 2 * diagonal, 4) for t, c in zip(target, direction)]
    return {"position": position, "target": target, "up": list(up), "orthographicHalfHeight": round(half, 4)}


def picture_jobs(wi, folder: Path) -> dict[int, dict]:
    """Each step's picture as a snapshot job: {step number: job}. Its view is hidden-line, the
    parts the step installs filled (``display.tint``: flat, in front of whatever they stand
    behind, behind whatever stands in front of them), later parts hidden, the surfaces it names
    outlined."""
    leaves = {leaf.ref: leaf for leaf in wi.leaves()}
    centre, diagonal = _extent(wi)
    tolerance = max(diagonal * 0.002, 0.01)
    jobs = {}
    for picture in picture_plan(wi):
        target, half = centre, 0.5 * diagonal
        if picture.frame == "step" and picture.focus:
            target, half = _fit_step(leaves, picture, diagonal)
        display: dict = {"mode": "hidden-line"}
        if picture.hide:
            display["hidden"] = list(picture.hide)
        if picture.tint:
            display["tint"] = {"parts": list(picture.tint), "color": FILL}
        job = {"input": wi.source, "camera": _camera(picture.camera, target, half, diagonal), "display": display,
               "output": {"tightFrame": False, "transparent": True},
               "outputs": [{"path": str(folder / f"step-{picture.step}.png"), "width": PICTURE_PX[0],
                            "height": PICTURE_PX[1]}]}
        marks = [_outline(f"step{picture.step}-{ref}", wi.scene.face_shape(ref), SURFACE, tolerance)
                 for ref in picture.surfaces]
        if marks:
            job["annotation"] = {"units": "mm", "marks": marks}
        jobs[picture.step] = job
    return jobs


def render_pictures(wi, folder: Path) -> dict[int, Path]:
    """Render every step's picture in one snapshot job; {step number: PNG}."""
    jobs = picture_jobs(wi, folder)
    if not jobs:
        return {}
    import cadgen

    cadgen.snapshot(job={"jobs": list(jobs.values())}, progress=False)
    return {step: Path(job["outputs"][0]["path"]) for step, job in jobs.items()}


# --- layout ------------------------------------------------------------------

Draw = Callable[[object], None]


class _Measure:
    def __init__(self) -> None:
        from matplotlib.font_manager import FontProperties
        from matplotlib.textpath import TextToPath

        self._path = TextToPath()
        self._props = {weight: FontProperties(family="DejaVu Sans", weight=weight) for weight in ("normal", "bold")}

    def width(self, text: str, size: float, weight: str = "normal") -> float:
        if not text:
            return 0.0
        props = self._props[weight].copy()
        props.set_size(size)
        w, _h, _d = self._path.get_text_width_height_descent(text, props, ismath=False)
        return w * PT

    def wrap(self, text: str, size: float, width: float, weight: str = "normal") -> list[str]:
        lines: list[str] = []
        for paragraph in text.split("\n"):
            line = ""
            for word in paragraph.split(" "):
                candidate = f"{line} {word}" if line else word
                if not line or self.width(candidate, size, weight) <= width:
                    line = candidate
                    continue
                lines.append(line)
                line = word
            while self.width(line, size, weight) > width and len(line) > 1:  # one word wider than the column
                cut = max(1, int(len(line) * width / self.width(line, size, weight)))
                lines.append(line[:cut])
                line = line[cut:]
            lines.append(line)
        return lines


def _line_h(size: float) -> float:
    return size * PT * LEAD


class _Cell:
    """Content stacked top-down in a column of a given width: its height is known
    before it is placed, so a row can be sized, kept whole and moved to a new page."""

    def __init__(self, measure: _Measure, width: float) -> None:
        self.m = measure
        self.width = width
        self.height = 0.0
        self._draws: list[Callable[[object, float, float], None]] = []

    def text(self, value: str, size: float = BODY, *, weight: str = "normal", color: str = "black",
             indent: float = 0.0) -> None:
        for line in self.m.wrap(value, size, self.width - indent, weight):
            y = self.height + size * PT
            self._draws.append(lambda ax, x, top, line=line, y=y: ax.text(
                x + indent, top - y, line, fontsize=size, weight=weight, color=color, va="baseline", ha="left"))
            self.height += _line_h(size)

    def not_stated(self, caption: str = "", size: float = BODY) -> None:
        """A caption and the hatched NOT STATED box: engineering owes this value."""
        lead = f"{caption}: " if caption else ""
        lead_w = self.m.width(lead, size, "bold")
        box_w = self.m.width("NOT STATED", SMALL, "bold") + 4.0
        self.height += 1.4  # the box stands taller than the text: clear the line above
        y = self.height + size * PT
        self._draws.append(lambda ax, x, top, y=y: _not_stated(ax, x, top - y, lead, lead_w, box_w, size))
        self.height += _line_h(size) + 1.0

    def blanks(self, captions: tuple[str, ...], *, per_row: int = 2) -> None:
        """Fill-ins the floor writes: a caption over a line, ``per_row`` to a row."""
        width = self.width / per_row
        for start in range(0, len(captions), per_row):
            top_y = self.height
            for i, caption in enumerate(captions[start:start + per_row]):
                self._draws.append(lambda ax, x, top, i=i, caption=caption, top_y=top_y: _blank(
                    ax, x + i * width, top - top_y, width - 3.0, caption))
            self.height += 8.0

    def gap(self, mm: float) -> None:
        self.height += mm

    def draw(self, ax, x: float, top: float) -> None:
        for draw in self._draws:
            draw(ax, x, top)


def _rect(x, y, w, h, *, lw, edge, face="none", zorder=2):
    from matplotlib.patches import Rectangle

    return Rectangle((x, y), w, h, linewidth=lw, edgecolor=edge, facecolor=face, zorder=zorder)


def _not_stated(ax, x, baseline, lead, lead_w, box_w, size) -> None:
    from matplotlib.patches import Rectangle

    if lead:
        ax.text(x, baseline, lead, fontsize=size, weight="bold", va="baseline", ha="left")
    bx = x + lead_w
    ax.add_patch(Rectangle((bx, baseline - 1.2), box_w, SMALL * PT + 2.4, linewidth=0.8, edgecolor="black",
                           facecolor="white", hatch="////", zorder=2))
    ax.text(bx + 2.0, baseline, "NOT STATED", fontsize=SMALL, weight="bold", va="baseline", ha="left", zorder=3,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.5})


def _blank(ax, x, top, width, caption) -> None:
    ax.text(x, top - SMALL * PT, caption.upper(), fontsize=SMALL - 0.5, color="#555555", va="baseline", ha="left")
    ax.plot([x, x + width], [top - 6.5, top - 6.5], lw=0.5, color="black")


class _Flow:
    """Pages of draw commands, filled top-down; a block that does not fit starts a page."""

    def __init__(self, wi, open_count: int) -> None:
        self.wi = wi
        self.w, self.h = PAGE_MM[wi.size]
        self.measure = _Measure()
        self.open_count = open_count
        self.pages: list[list[Draw]] = []
        self.on_new_page: Callable[[], None] | None = None
        self.new_page()

    @property
    def inner(self) -> float:
        return self.w - 2 * MARGIN

    @property
    def body_top(self) -> float:
        return self.h - MARGIN - 17.0 - (7.0 if self.wi.status == "draft" else 0.0)

    @property
    def body_bottom(self) -> float:
        return MARGIN + 6.0

    def new_page(self) -> None:
        self.pages.append([])
        self.y = self.body_top
        if self.on_new_page is not None:
            self.on_new_page()

    def room(self, height: float, what: str) -> None:
        if self.y - height >= self.body_bottom:
            return
        self.new_page()
        if self.y - height < self.body_bottom:
            raise ValueError(f"{what} is taller than a page ({height:.0f} mm); split it into shorter steps")

    def add(self, draw: Draw) -> None:
        self.pages[-1].append(draw)

    def cell(self, cell: _Cell, what: str, *, x: float = MARGIN) -> None:
        self.room(cell.height, what)
        top = self.y
        self.add(lambda ax: cell.draw(ax, x, top))
        self.y -= cell.height

    def rule(self, *, gap: float = 1.5, weight: float = 0.6, color: str = "black") -> None:
        y = self.y - gap / 2
        self.add(lambda ax: ax.plot([MARGIN, self.w - MARGIN], [y, y], lw=weight, color=color))
        self.y -= gap

    def table(self, columns: list[tuple[str, float]], rows: list[list[str | None]], what: str,
              *, blank_columns: tuple[int, ...] = ()) -> None:
        """A ruled table; ``None`` prints NOT STATED; a ``blank_columns`` cell is a line to fill in."""
        xs = [MARGIN]
        for _title, width in columns[:-1]:
            xs.append(xs[-1] + width)
        def header() -> None:
            self._table_row([(_text_cell(self.measure, title, width, SMALL, "bold"), x, width)
                             for (title, width), x in zip(columns, xs)], what, shade=True)

        titled = any(title for title, _width in columns)
        if titled:
            header()
        outer = self.on_new_page
        if titled:  # a table that runs onto the next page repeats its headings there
            self.on_new_page = header
        try:
            self._rows(rows, columns, xs, what, blank_columns)
        finally:
            self.on_new_page = outer

    def _rows(self, rows, columns, xs, what: str, blank_columns: tuple[int, ...]) -> None:
        for row in rows:
            cells = []
            for i, (value, (_title, width), x) in enumerate(zip(row, columns, xs)):
                cell = _Cell(self.measure, width - 3.0)
                if i in blank_columns:
                    cell.gap(4.5)
                    cell._draws.append(lambda ax, x0, top, w=width: ax.plot(
                        [x0, x0 + w - 4.0], [top - 4.5, top - 4.5], lw=0.5, color="black"))
                elif value is None:
                    cell.not_stated()
                else:
                    cell.text(value)
                cells.append((cell, x, width))
            self._table_row(cells, what)

    def _table_row(self, cells, what: str, *, shade: bool = False) -> None:
        height = max(cell.height for cell, _x, _w in cells) + 2.4
        self.room(height, what)
        top = self.y
        if shade:
            self.add(lambda ax: ax.add_patch(_rect(MARGIN, top - height, self.inner, height, lw=0, edge="none",
                                                   face="#eeeeee", zorder=1)))
        for cell, x, _w in cells:
            self.add(lambda ax, cell=cell, x=x: cell.draw(ax, x + 1.5, top - 1.2))
        self.add(lambda ax: ax.plot([MARGIN, self.w - MARGIN], [top - height] * 2, lw=0.3, color=RULE))
        self.y -= height


def _text_cell(measure, value, width, size=BODY, weight="normal") -> _Cell:
    cell = _Cell(measure, width - 3.0)
    cell.text(value, size, weight=weight)
    return cell


def _fit(measure: _Measure, text: str, size: float, width: float, *, smallest: float = 7.0) -> tuple[str, float]:
    """``text`` at the largest size down to ``smallest`` that fits ``width``; past
    that, cut with an ellipsis -- the full title is on the front page, wrapped."""
    while size > smallest and measure.width(text, size, "bold") > width:
        size -= 0.5
    while measure.width(text, size, "bold") > width and len(text) > 1:
        text = text[:-2].rstrip() + "…"
    return text, size


def _header(ax, measure: _Measure, wi, w, h, page: int, count: int, open_count: int) -> None:
    layout = wi.layout
    top = h - MARGIN
    ax.add_patch(_rect(MARGIN, top - 15.0, w - 2 * MARGIN, 15.0, lw=0.6, edge="black"))
    number = f"{wi.number}  REV {wi.revision}"
    room = w - 2 * MARGIN - 10.0 - measure.width(number, HEAD, "bold")
    title, size = _fit(measure, wi.title, HEAD + 1, room)
    ax.text(MARGIN + 2.5, top - 6.5, title, fontsize=size, weight="bold", va="baseline")
    ax.text(w - MARGIN - 2.5, top - 6.5, number, fontsize=HEAD, weight="bold", va="baseline", ha="right")
    detail = f"{layout.company.upper()}   {layout.title}" if layout.company else layout.title
    if wi.part_number:
        detail += f"   ASSEMBLY P/N {wi.part_number}"
    if wi.drawing is not None:
        detail += f"   DRAWING {wi.drawing.name}"
    ax.text(MARGIN + 2.5, top - 12.0, detail, fontsize=SMALL, va="baseline", color="#333333")
    ax.text(w - MARGIN - 2.5, top - 12.0, f"PAGE {page} OF {count}", fontsize=SMALL, va="baseline", ha="right")
    if wi.status == "draft":
        ax.add_patch(_rect(MARGIN, top - 22.0, w - 2 * MARGIN, 5.5, lw=0.8, edge="black", face="#eeeeee"))
        items = f"{open_count} OPEN ITEM{'S' if open_count != 1 else ''}" if open_count else "NO OPEN ITEMS"
        ax.text(w / 2, top - 20.4, f"DRAFT — NOT FOR PRODUCTION — {items}", fontsize=BODY,
                weight="bold", va="baseline", ha="center")
    ax.text(MARGIN, MARGIN - 4.0, f"Generated from {wi.source_name}", fontsize=SMALL - 1, color="#666666",
            va="baseline")


# --- the front pages ---------------------------------------------------------


def _section(flow: _Flow, title: str, *, keep: float = 18.0) -> None:
    """A heading, kept on a page with ``keep`` millimetres of what follows it."""
    flow.room(keep + 8.0, title)
    flow.y -= 3.0
    flow.cell(_text_cell(flow.measure, title, flow.inner, BODY + 0.5, "bold"), title)
    flow.rule()


def _same(ref: str, name: str) -> tuple[str, str]:
    """What groups a unit with others: its name, only ever identical (``bearing_6202`` and
    ``bearing_6204`` are two parts, never a guess at one); a part with no name stands alone."""
    return (name, "") if name != UNNAMED else (name, ref)


def _group(units) -> list[tuple[str, list[str]]]:
    """(name, refs) for units that carry one name, in first-seen order."""
    groups: dict[tuple[str, str], list[str]] = {}
    for ref, name in units:
        groups.setdefault(_same(ref, name), []).append(ref)
    return [(name, refs) for (name, _ref), refs in groups.items()]


def _refs(refs: list[str]) -> str:
    return " ".join(refs) if len(refs) <= 4 else f"{refs[0]} {refs[1]} … {refs[-1]} ({len(refs)})"


def parts(wi) -> list[tuple[str, list[str], list[str]]]:
    """The parts list at the level the steps install them, in build order: (name,
    refs, step labels). A subassembly a step installs whole is one line, parts that
    carry one name are one line with their quantity, and parts no step installs come last."""
    members: dict[tuple[str, str], list[tuple[str, str | None]]] = {}  # _same -> (ref, step label)
    for step in wi.steps:
        for ref, name in step.units:
            members.setdefault(_same(ref, name), []).append((ref, step.label))
    for leaf in wi.leaves():
        if leaf.ref not in wi._installed:
            name = leaf.label or UNNAMED
            members.setdefault(_same(leaf.ref, name), []).append((leaf.ref, None))
    return [(name, [ref for ref, _label in found],
             list(dict.fromkeys(label for _ref, label in found if label is not None)))
            for (name, _ref), found in members.items()]


def _front(flow: _Flow, wi, open_items: list[str]) -> None:
    m = flow.measure
    layout = wi.layout
    flow.cell(_text_cell(m, layout.title, flow.inner, SMALL, "bold"), "the title")
    flow.cell(_text_cell(m, wi.title, flow.inner, TITLE, "bold"), "the title")
    flow.y -= 2.0
    info = [["Number", f"{wi.number} Rev {wi.revision}"], ["Assembly", wi.source_name]]
    if wi.part_number:
        info.append(["Part number", wi.part_number])
    if wi.drawing is not None:
        info.append(["Drawing", wi.drawing.name])
    info.append(["Status", wi.status.upper()])
    flow.table([("", 38.0), ("", flow.inner - 38.0)], info, "the title block")
    if layout.traceability:
        blanks = _Cell(m, flow.inner)
        blanks.blanks(("Work order", "Serial no.", "Started"), per_row=3)
        flow.cell(blanks, "the title block")

    if wi.scope:
        _section(flow, "SCOPE")
        flow.cell(_front_line(m, wi.scope, flow.inner), "the scope")

    _section(flow, "APPLICABLE DOCUMENTS")
    documents = wi.documents()
    if documents:
        flow.table([("DOCUMENT", 60.0), ("TITLE", flow.inner - 60.0)], [[n, t] for n, t in documents], "documents")
    else:
        flow.cell(_text_cell(m, "None cited.", flow.inner), "documents")

    if wi.emphasis == "process":
        references = wi.references()
        if references:
            _section(flow, "PROCESS REFERENCES")
            flow.table([("DOCUMENT", 60.0), ("SECTION", flow.inner - 100.0), ("STEPS", 40.0)],
                       [[document, where, ", ".join(labels)] for document, where, labels in references],
                       "process references")

    _section(flow, "SAFETY")
    for line in wi.safety:
        flow.cell(_front_line(m, line, flow.inner, bullet="• "), "safety")
    if not wi.safety:
        flow.cell(_text_cell(m, "None stated.", flow.inner), "safety")

    _section(flow, "PARTS")
    rows = [[name, str(len(refs)), ", ".join(steps) or None, _refs(refs)] for name, refs, steps in parts(wi)]
    flow.table([("PART", 70.0), ("QTY", 14.0), (layout.step_label, 22.0), ("OCCURRENCES", flow.inner - 106.0)],
               rows, "parts")

    if wi.materials:
        _section(flow, "MATERIALS")
        if layout.traceability:
            flow.table([("MATERIAL", 58.0), ("PER", flow.inner - 118.0), ("LOT / BATCH", 34.0), ("EXPIRY", 26.0)],
                       [[r.name, r.per.cite(), "", ""] for r in wi.materials], "materials", blank_columns=(2, 3))
        else:
            flow.table([("MATERIAL", 58.0), ("PER", flow.inner - 58.0)],
                       [[r.name, r.per.cite()] for r in wi.materials], "materials")

    equipment = wi.equipment()
    if equipment:
        _section(flow, "EQUIPMENT")
        if layout.calibration:
            flow.table([("ITEM", flow.inner - 70.0), ("ID", 36.0), ("CAL DUE", 34.0)],
                       [[item, "", ""] for item in equipment], "equipment", blank_columns=(1, 2))
        else:
            flow.table([("ITEM", flow.inner)], [[item] for item in equipment], "equipment")

    if wi.operations:
        _section(flow, "OPERATIONS")
        rows = []
        for index, title in enumerate(wi.operations, start=1):
            labels = [s.label for s in wi.steps if s.operation == index]
            span = f"{labels[0]}–{labels[-1]}" if len(labels) > 1 else (labels[0] if labels else "")
            rows.append([str(index), title, span])
        flow.table([("OP", 14.0), ("OPERATION", flow.inner - 44.0), (layout.step_label + "S", 30.0)], rows,
                   "operations")

    if wi.status == "draft":
        _section(flow, "OPEN ITEMS")
        text = "\n".join(f"• {item}" for item in open_items) or \
            "None: every value is stated and every part is installed."
        for line in text.split("\n"):
            flow.cell(_text_cell(m, line, flow.inner), "open items")

    if wi.revisions:
        _section(flow, "REVISIONS")
        flow.table([("REV", 16.0), ("DATE", 30.0), ("CHANGE", flow.inner - 46.0)],
                   [list(row) for row in wi.revisions], "revisions")

    if layout.approvals:
        _section(flow, "APPROVALS", keep=26.0)
        approvals = _Cell(m, flow.inner)
        roles = [role + (f": {wi.author}" if wi.author and index == 0 else "")
                 for index, role in enumerate(layout.approvals)]
        approvals.blanks(tuple(cell for role in roles for cell in (role, "Date")), per_row=2)
        flow.cell(approvals, "approvals")


# --- the procedure -----------------------------------------------------------

STEP_W, FIG_W, STAMP_W = 12.0, 46.0, 17.0


def _columns(flow: _Flow) -> list[tuple[str, float]]:
    """The step column, the instruction, the figure (visual emphasis only), then one
    column per sign-off the layout names."""
    layout = flow.wi.layout
    figure = flow.wi.emphasis == "visual" and layout.figures
    instruction = flow.inner - STEP_W - (FIG_W if figure else 0.0) - STAMP_W * len(layout.stamps)
    columns = [(layout.step_label, STEP_W), (layout.instruction_label, instruction)]
    if figure:
        columns.append(("FIGURE", FIG_W))
    return columns + [(stamp, STAMP_W) for stamp in layout.stamps]


def _column_header(flow: _Flow) -> None:
    x = MARGIN
    cells = []
    for title, width in _columns(flow):
        cells.append((_text_cell(flow.measure, title, width, SMALL, "bold"), x, width))
        x += width
    flow._table_row(cells, "the column headings", shade=True)


def _legend(flow: _Flow) -> None:
    cell = _Cell(flow.measure, flow.inner)
    cell.text("FIGURES: the assembly after the step, in line art. Filled blue: the parts this step installs. "
              "Outlined purple: the surfaces it names. Lines only: parts installed earlier.", SMALL, color="#333333")
    flow.cell(cell, "the figure key")
    flow.y -= 1.0


def _instruction(flow: _Flow, wi, step, width: float) -> _Cell:
    cell = _Cell(flow.measure, width - 3.0)
    cell.text(step.title, BODY + 0.5, weight="bold")
    if any(where == "title" for where, _name in step.missing):
        cell.not_stated("source", SMALL)
    if step.units:
        cell.text("Install: " + ", ".join(
            f"{name} ×{len(refs)} ({_refs(refs)})" if len(refs) > 1 else f"{name} ({refs[0]})"
            for name, refs in _group(step.units)), SMALL, color="#333333")
    names = {leaf.ref: leaf.label or UNNAMED for leaf in wi.leaves()}
    for op in step.ops:
        shown: Source | None = None  # a citation prints once for the lines of one operation it covers
        cell.gap(0.8)
        if op.surfaces:
            cell.text("Surfaces: " + ", ".join(f"{names.get(owner, owner)} ({ref})" for ref, owner in op.surfaces),
                      SMALL, color="#333333")
        for line in op.lines:
            if line.value is None:
                cell.not_stated(line.caption)
            elif op.kind == "instruct":
                cell.text(line.value)
            else:
                cell.text(f"{line.caption}: {line.value}")
            if line.source is not None and line.source != shown:
                cell.text(_citation(line.source), SMALL, color="#444444", indent=3.0)
            elif line.source is None and line.cite:
                cell.not_stated("source", SMALL)
            shown = line.source or shown
        records = op.records if op.records is not None else _records(op.kind)
        captions = (records if wi.layout.traceability else ()) + ((op.record,) if op.record else ())
        if captions:
            cell.blanks(captions)
    return cell


def _figure(path: Path | None, width: float):
    if path is None:
        return 0.0, None
    import matplotlib.image as mpimg

    pixels = mpimg.imread(str(path))
    if pixels.shape[-1] == 4:  # over white: a page has no use for an alpha mask beside each picture
        alpha = pixels[..., 3:4]
        pixels = pixels[..., :3] * alpha + (1.0 - alpha)
    w = width - 3.0
    h = w * PICTURE_PX[1] / PICTURE_PX[0]

    def draw(ax, x: float, top: float) -> None:
        ax.imshow(pixels, extent=(x, x + w, top - h, top), interpolation="antialiased", zorder=1)
        ax.add_patch(_rect(x, top - h, w, h, lw=0.3, edge="#bbbbbb"))

    return h, draw


def _front_line(measure, line, width, bullet: str = "") -> _Cell:
    """A front-page line, its citation under it, or NOT STATED where it states a value it cites no source for."""
    cell = _text_cell(measure, bullet + line.value, width)
    if line.source is not None:
        cell.text(_citation(line.source), SMALL, color="#444444", indent=3.0)
    elif line.cite:
        cell.not_stated("source", SMALL)
    return cell


def _citation(source) -> str:
    """``per PS-3300 Rev B §3.1``, or ``stated by A. Zhou, 2026-10-23`` as it is."""
    return source.cite() if source.kind == "stated" else f"per {source.cite()}"


def _notice(flow: _Flow, notice) -> _Cell:
    cell = _Cell(flow.measure, flow.inner - 6.0)
    cell.text(notice.caption, BODY, weight="bold")
    cell.text(notice.value)
    if notice.source is not None:
        cell.text(_citation(notice.source), SMALL, color="#444444")
    elif notice.cite:
        cell.not_stated("source", SMALL)
    return cell


def _stamps(flow: _Flow, xs: list[float], hold: bool) -> list[tuple[_Cell, float]]:
    """The sign-off cells: a hold point writes HOLD in the last, where work stops."""
    count = len(flow.wi.layout.stamps)
    cells = []
    for index in range(count):
        cell = _Cell(flow.measure, STAMP_W - 3.0)
        if hold and index == count - 1:
            cell.text("HOLD", SMALL, weight="bold")
        cells.append((cell, xs[len(xs) - count + index]))
    return cells


def _procedure(flow: _Flow, wi, pictures: dict[int, Path]) -> None:
    flow.on_new_page = None
    flow.new_page()
    flow.cell(_text_cell(flow.measure, "PROCEDURE", flow.inner, BODY + 0.5, "bold"), "PROCEDURE")
    flow.rule()
    if pictures:
        _legend(flow)
    _column_header(flow)
    flow.on_new_page = lambda: _column_header(flow)
    columns = _columns(flow)
    xs = [MARGIN]
    for _title, width in columns[:-1]:
        xs.append(xs[-1] + width)
    operation = None
    for step in wi.steps:
        notices = [_notice(flow, notice) for notice in step.notices]
        body = _instruction(flow, wi, step, columns[1][1])
        fig_h, fig = _figure(pictures.get(step.number), FIG_W)
        row_h = max(body.height, fig_h, 10.0) + 3.0
        notice_h = sum(n.height + 3.0 for n in notices)
        if step.operation is not None and step.operation != operation:
            operation = step.operation
            head = _text_cell(flow.measure, f"OPERATION {operation}   {wi.operations[operation - 1]}", flow.inner,
                              BODY, "bold")
            # A heading stays on the page with its first step.
            flow.room(head.height + 2.4 + notice_h + row_h, f"step {step.label}")
            flow._table_row([(head, MARGIN, flow.inner)], f"operation {operation}", shade=True)
        flow.room(notice_h + row_h, f"step {step.label}")
        for notice, n in zip(step.notices, notices):
            top = flow.y
            h = n.height + 3.0
            heavy = notice.caption in ("WARNING", "CAUTION")
            flow.add(lambda ax, top=top, h=h, heavy=heavy: ax.add_patch(_rect(
                MARGIN + 0.5, top - h + 0.5, flow.inner - 1.0, h - 1.0, lw=1.2 if heavy else 0.5, edge="black")))
            flow.add(lambda ax, n=n, top=top: n.draw(ax, MARGIN + 3.0, top - 1.5))
            flow.y -= h
        top = flow.y
        number = _text_cell(flow.measure, step.label, STEP_W, BODY, "bold")
        _row(flow, xs, top, row_h, [(number, xs[0]), (body, xs[1])] + _stamps(flow, xs, step.hold), step.hold)
        if fig is not None:
            flow.add(lambda ax, fig=fig, top=top: fig(ax, xs[2] + 1.5, top - 1.5))
        flow.y -= row_h
    if not wi.layout.close_out:
        return
    close = _Cell(flow.measure, columns[1][1] - 3.0)
    close.text("Close-out", BODY + 0.5, weight="bold")
    close.text("Every step above is signed off; any nonconformance is recorded.")
    close.blanks(("NCR numbers",), per_row=1)
    row_h = close.height + 3.0
    flow.room(row_h, "the close-out")
    hold = wi.layout.holds
    _row(flow, xs, flow.y, row_h, [(close, xs[1])] + _stamps(flow, xs, hold), hold)
    flow.y -= row_h


def _row(flow: _Flow, xs: list[float], top: float, height: float, cells, hold: bool) -> None:
    """One procedure row at ``top``: its cells, column rules and bottom rule. A hold
    point shades the last sign-off cell: work stops there until it is stamped."""
    if hold:
        flow.add(lambda ax: ax.add_patch(_rect(xs[-1], top - height, STAMP_W, height, lw=0, edge="none",
                                               face="#e6e6e6", zorder=0)))
    for cell, x in cells:
        flow.add(lambda ax, cell=cell, x=x: cell.draw(ax, x + 1.5, top - 1.5))
    for x in xs[1:]:
        flow.add(lambda ax, x=x: ax.plot([x, x], [top, top - height], lw=0.3, color=RULE))
    flow.add(lambda ax: ax.plot([MARGIN, flow.w - MARGIN], [top - height] * 2, lw=0.3, color=RULE))


def _records(kind: str) -> tuple[str, ...]:
    from cadgen.work_instruction import RECORDS

    return RECORDS.get(kind, ())


# --- the PDF -----------------------------------------------------------------


def layout(wi, open_items: list[str], pictures: dict[int, Path]) -> _Flow:
    """The pages as draw commands: the front pages, then the procedure table."""
    flow = _Flow(wi, len(open_items))
    _front(flow, wi, open_items)
    _procedure(flow, wi, pictures)
    return flow


def draw_page(ax, flow: _Flow, index: int, open_count: int) -> None:
    """Page ``index`` (from 1), its header first, onto a matplotlib axes in millimetres."""
    _header(ax, flow.measure, flow.wi, flow.w, flow.h, index, len(flow.pages), open_count)
    for draw in flow.pages[index - 1]:
        draw(ax)


def write_pdf(wi, path: Path, *, open_items: list[str]) -> int:
    """Lay out and write the instruction, whole or not at all (``pdf_pages``); returns the page count."""
    from cadgen._internal.pdf_pages import matplotlib_pdf, write_pages

    matplotlib_pdf("@work_instruction")  # a missing renderer is refused before any picture is drawn
    picture_plan(wi)  # refuses a mark on a part not yet installed, before any render
    with tempfile.TemporaryDirectory(prefix="cadgen-wi-") as folder:
        pictures = render_pictures(wi, Path(folder)) if wi.pictures else {}
        flow = layout(wi, open_items, pictures)
        count = len(flow.pages)
        write_pages(path, [(flow.w, flow.h, lambda ax, index=index: draw_page(ax, flow, index, len(open_items)))
                           for index in range(1, count + 1)], decorator="@work_instruction")
    return count
