"""A picture guide: a ``simple`` work instruction, laid out for anyone to follow.

The first page shows the finished assembly and what you need, a picture of each
part with its count. Then each step is its number, one short sentence and a big
picture of the whole assembly so far: the step's parts in blue, an arrow where
the step gives one, parts still to come left out. There are no tables, no blanks
to fill in and no document numbers. A value keeps its source, printed small under
it, and one nobody has stated says so in plain words.
"""

from __future__ import annotations

import re
from pathlib import Path

from cad._internal.work_instruction_pages import (
    COVER_PX,
    FILL,
    GUIDE_PX,
    MARGIN,
    PT,
    _citation,
    _Cell,
    _Flow,
    _group,
    _rect,
    _text_cell,
    parts,
    read_pixels,
)

TITLE, LEAD, HEAD, STEP, TEXT, SMALL = 26.0, 12.0, 14.0, 15.0, 11.0, 8.5
GREY, FAINT, AMBER, AMBER_FACE, NOTE_FACE = "#555555", "#bbbbbb", "#9a5b00", "#fff4e0", "#eef2f8"
BADGE = 10.0  # a step's number, its circle's diameter
BOX = 7.0  # the box to tick
TILES, TILE_GAP = 4, 4.0  # what you need, to a row
NOTICES = {"WARNING": "Warning", "CAUTION": "Careful", "NOTE": "Tip"}
NOT_DECIDED = "not decided yet"


def plain(name: str) -> str:
    """A part's name as a reader says it: a label's underscores are the model's, not theirs."""
    return name.replace("_", " ").strip().capitalize() if "_" in name else name


def _plain_item(item: str) -> str:
    """An open item in the words the page uses."""
    item = re.sub(r"^step (\S+) \(\S+\): ", r"Step \1: ", item)
    item = re.sub(r"^(.+): no step installs it$", lambda m: f"{plain(m.group(1))}: no step uses it yet", item)
    return re.sub(r" not stated$", f" {NOT_DECIDED}", item)


class _Guide(_Flow):
    @property
    def body_top(self) -> float:
        return self.h - MARGIN

    @property
    def body_bottom(self) -> float:
        return MARGIN + 7.0


def _image(flow: _Flow, path: Path | None, x: float, top: float, width: float, height: float) -> None:
    if path is None:
        return
    pixels = read_pixels(path)
    # Written as it was drawn: matplotlib would otherwise resample a page's pictures into one.
    flow.add(lambda ax: ax.imshow(pixels, extent=(x, x + width, top - height, top), interpolation="none", zorder=1))


def _heading(flow: _Flow, title: str, keep: float) -> None:
    cell = _text_cell(flow.measure, title, flow.inner, HEAD, "bold")
    flow.room(cell.height + 5.0 + keep, title)
    flow.y -= 3.0
    flow.cell(cell, title)
    flow.y -= 2.0


def _lines(flow: _Flow, lines: list[str], what: str, *, color: str = "black") -> None:
    for line in lines:
        cell = _Cell(flow.measure, flow.inner)
        cell.text(line, TEXT, color=color)
        cell.gap(0.8)
        flow.cell(cell, what)


def _tile(flow: _Flow, cell: _Cell, top: float, x: float, size: float, path: Path | None) -> None:
    _image(flow, path, x, top, size, size)
    flow.add(lambda ax: ax.add_patch(_rect(x, top - size, size, size, lw=0.4, edge=FAINT)))
    flow.add(lambda ax: cell.draw(ax, x, top - size - 1.5))


def _need(flow: _Flow, wi, pictures: dict) -> None:
    """What you need: a picture of each part with its count, then what the model does not show."""
    width = (flow.inner - (TILES - 1) * TILE_GAP) / TILES
    lines = parts(wi)
    _heading(flow, "What you need", width + 12.0)
    for start in range(0, len(lines), TILES):
        row = lines[start:start + TILES]
        cells = []
        for name, refs, _steps in row:
            cell = _Cell(flow.measure, width)
            cell.text(f"×{len(refs)}  {plain(name)}", TEXT, weight="bold")
            cells.append(cell)
        height = width + 1.5 + max(cell.height for cell in cells) + 3.0
        flow.room(height, "what you need")
        top = flow.y
        for offset, cell in enumerate(cells):
            _tile(flow, cell, top, MARGIN + offset * (width + TILE_GAP), width, pictures.get(f"part-{start + offset}"))
        flow.y -= height
    hardware = [line.value for step in wi.steps for op in step.ops if op.kind == "fasten"
                for line in op.lines if line.caption == "Hardware"]
    also = list(dict.fromkeys([*hardware, *(record.name for record in wi.materials)]))
    if also:
        _lines(flow, [f"Also: {', '.join(also)}"], "what you need")
    tools = wi.equipment()
    if tools:
        _lines(flow, [f"Tools: {', '.join(tools)}"], "what you need")


def _cover(flow: _Flow, wi, open_items: list[str], pictures: dict) -> None:
    flow.cell(_text_cell(flow.measure, wi.title, flow.inner, TITLE, "bold"), "the title")
    flow.y -= 1.0
    if wi.scope:
        cell = _Cell(flow.measure, flow.inner)
        cell.text(wi.scope.value, LEAD, color=GREY)
        if wi.scope.source is not None:
            cell.text(_citation(wi.scope.source), SMALL, color=GREY)
        flow.cell(cell, "the scope")
    cover = pictures.get("cover")
    if cover is not None:
        height = flow.inner * COVER_PX[1] / COVER_PX[0]
        flow.y -= 2.0
        _image(flow, cover, MARGIN, flow.y, flow.inner, height)
        flow.y -= height
    _need(flow, wi, pictures)
    if wi.safety:
        _heading(flow, "Stay safe", 8.0)
        for line in wi.safety:
            _notice(flow, "CAUTION", line)
    if open_items:
        _heading(flow, "Still to decide", 8.0)
        _lines(flow, [_plain_item(item) for item in open_items], "still to decide", color=AMBER)


def _notice(flow: _Flow, kind: str, line) -> None:
    cell = _Cell(flow.measure, flow.inner - 8.0)
    careful = kind != "NOTE"
    cell.text(f"{NOTICES[kind]}: {line.value}" if line.caption else line.value, TEXT,
              color=AMBER if careful else "black")
    if line.source is not None:
        cell.text(_citation(line.source), SMALL, color=GREY)
    elif line.cite:
        cell.text(f"Where this number comes from: {NOT_DECIDED}", SMALL, color=AMBER)
    height = cell.height + 3.0
    flow.room(height, "a notice")
    top = flow.y
    flow.add(lambda ax: ax.add_patch(_rect(MARGIN, top - height, flow.inner, height, lw=0, edge="none",
                                           face=AMBER_FACE if careful else NOTE_FACE, zorder=0)))
    flow.add(lambda ax: cell.draw(ax, MARGIN + 4.0, top - 1.5))
    flow.y -= height + 1.5


def _body(flow: _Flow, step) -> _Cell:
    """What the step says under its picture: what it uses, then each thing it asks for."""
    cell = _Cell(flow.measure, flow.inner)
    if step.units:
        cell.text("You need: " + ", ".join(f"×{len(refs)} {plain(name)}" for name, refs in _group(step.units)),
                  TEXT, color=GREY)
    if any(where == "title" for where, _name in step.missing):
        cell.text(f"Where this number comes from: {NOT_DECIDED}", SMALL, color=AMBER)
    for op in step.ops:
        shown = None  # a source prints once for the lines of one operation it covers
        cell.gap(0.8)
        if op.surfaces:
            cell.text("The purple outline shows where.", TEXT, color=GREY)
        for line in op.lines:
            caption = "Check" if line.caption == "Inspect" else line.caption
            if line.value is None:
                cell.text(f"{caption}: {NOT_DECIDED}", TEXT, color=AMBER)
            elif op.kind == "instruct":
                cell.text(line.value, TEXT)
            else:
                cell.text(f"{caption}: {line.value}", TEXT)
            if line.source is not None and line.source != shown:
                cell.text(_citation(line.source), SMALL, color=GREY)
            elif line.source is None and line.cite:
                cell.text(f"Where this number comes from: {NOT_DECIDED}", SMALL, color=AMBER)
            shown = line.source or shown
        if op.record:
            cell.text(f"Write down: {op.record}", TEXT)
    return cell


def _step(flow: _Flow, step, pictures: dict) -> None:
    title = _Cell(flow.measure, flow.inner - BADGE - BOX - 8.0)
    title.text(step.title, STEP, weight="bold")
    head = max(title.height, BADGE)
    path = pictures.get(step.number)
    height = flow.inner * GUIDE_PX[1] / GUIDE_PX[0] if path is not None else 0.0
    body = _body(flow, step)
    notes = sum(_notice_height(flow, notice) for notice in step.notices)
    flow.room(head + 1.5 + notes + height + body.height + 5.0, f"step {step.label}")
    top = flow.y
    radius = BADGE / 2
    x = MARGIN + radius

    def badge(ax) -> None:
        from matplotlib.patches import Circle

        ax.add_patch(Circle((x, top - radius), radius, facecolor=FILL, edgecolor="none", zorder=2))
        ax.text(x, top - radius - STEP * PT * 0.36, step.label, fontsize=STEP, weight="bold", color="black",
                ha="center", va="baseline", zorder=3)

    flow.add(badge)
    flow.add(lambda ax: title.draw(ax, MARGIN + BADGE + 4.0, top - (head - title.height) / 2))
    flow.add(lambda ax: ax.add_patch(_rect(flow.w - MARGIN - BOX, top - (head + BOX) / 2, BOX, BOX, lw=0.9, edge=GREY)))
    flow.y -= head + 1.5
    for notice in step.notices:
        _notice(flow, notice.caption, notice)
    if path is not None:
        _image(flow, path, MARGIN, flow.y, flow.inner, height)
        flow.y -= height + 1.5
    if body.height:
        flow.cell(body, f"step {step.label}")
    flow.y -= 5.0


def layout(wi, open_items: list[str], pictures: dict) -> _Flow:
    """The pages as draw commands: the cover, then the steps."""
    flow = _Guide(wi, len(open_items))
    _cover(flow, wi, open_items, pictures)
    flow.new_page()
    cell = _Cell(flow.measure, flow.inner)
    cell.text("Blue shows what you add in each step.", TEXT, color=GREY)
    cell.gap(2.0)
    flow.cell(cell, "the key")
    for step in wi.steps:
        _step(flow, step, pictures)
    return flow


def _notice_height(flow: _Flow, notice) -> float:
    cell = _Cell(flow.measure, flow.inner - 8.0)
    cell.text(f"{NOTICES[notice.caption]}: {notice.value}", TEXT)
    return cell.height + (SMALL * PT * 1.3 if notice.source is not None or notice.cite else 0.0) + 4.5


def footer(ax, flow: _Flow, page: int) -> None:
    wi = flow.wi
    left = f"{wi.title}  {wi.number} Rev {wi.revision}" if wi.number else wi.title
    right = f"Page {page} of {len(flow.pages)}"
    if wi.status == "draft":
        right = f"Draft  ·  {right}"
    ax.text(MARGIN, MARGIN - 2.0, left, fontsize=SMALL, color=GREY, va="baseline")
    ax.text(flow.w - MARGIN, MARGIN - 2.0, right, fontsize=SMALL, color=GREY, va="baseline", ha="right")
