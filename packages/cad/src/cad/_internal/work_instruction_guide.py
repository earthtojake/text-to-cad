"""A picture guide: a ``simple`` work instruction, laid out for anyone to follow.

Laid out the way a kit's printed manual is. The first page shows the finished
assembly and what you need: a picture of each part with its count, the screws and
nuts by size, and the tools with what each one is for. The steps open with how to
read them. Each step is its number, one short sentence, a box of what it uses (each
part's picture and count, its screws by size) and a big picture of the whole
assembly so far: the step's parts in blue, pulled back along the way they go in
with a thin line to their place where the step gives an arrow, parts still to come
left out. There are no tables, no blanks to fill in and no document numbers. A value keeps its source, printed small under
it, and one nobody has stated says so in plain words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from cad._internal.work_instruction_pages import (
    COVER_PX,
    FILL,
    GUIDE_LINE,
    GUIDE_PX,
    MARGIN,
    PT,
    _citation,
    _Cell,
    _fit,
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
BOX_FACE = "#f2f3f5"  # a step's parts box, and the key's
CHIP = 9.0  # a screw's size, beside its picture
STEP_TILE = 15.0  # a part's picture in a step's parts box
SCREW_INK = "#3a3a3a"
INK = "#1d1d1f"  # a step's number: dark, so blue on the page means only what the step adds
DOT, DOT_GAP = 1.6, 1.4  # the footer's step dots


@dataclass(frozen=True)
class Hardware:
    """Screws, nuts or washers of one size, as a step's ``fasten`` names them: how many in all (``None``
    where a step gives no count) and the tools that drive them."""

    name: str
    qty: int | None
    tools: tuple[str, ...] = ()


def hardware(steps) -> list[Hardware]:
    """The hardware ``steps`` fasten, one line per name in first-used order, counts added up."""
    found: dict[str, list] = {}
    for step in steps:
        for op in step.ops:
            if op.hardware is None:
                continue
            name, qty = op.hardware
            line = found.setdefault(name, [0, []])
            line[0] = None if line[0] is None or qty is None else line[0] + qty
            if op.tool and op.tool not in line[1]:
                line[1].append(op.tool)
    return [Hardware(name, qty, tuple(tools)) for name, (qty, tools) in found.items()]


def _kind(name: str) -> str:
    lowered = name.lower()
    return "nut" if "nut" in lowered else "washer" if "washer" in lowered else "screw"


def _glyph_width(name: str) -> float:
    """How wide a hardware line's picture is: a screw's shank in proportion to its length (``M3×10``)."""
    if _kind(name) != "screw":
        return 3.4
    found = re.search(r"[x×]\s*(\d+(?:\.\d+)?)", name, re.IGNORECASE)
    return 1.8 + (min(max(float(found.group(1)) * 0.35, 3.0), 8.0) if found else 5.0)


def _glyph(ax, name: str, x: float, y: float) -> None:
    """A small side-on picture of a screw, nut or washer, its middle at height ``y``."""
    from matplotlib.patches import Circle, Rectangle, RegularPolygon

    kind = _kind(name)
    if kind == "nut":
        ax.add_patch(RegularPolygon((x + 1.7, y), 6, radius=1.7, facecolor=SCREW_INK, edgecolor="none", zorder=3))
        ax.add_patch(Circle((x + 1.7, y), 0.7, facecolor="white", edgecolor="none", zorder=4))
        return
    if kind == "washer":
        ax.add_patch(Circle((x + 1.7, y), 1.7, facecolor=SCREW_INK, edgecolor="none", zorder=3))
        ax.add_patch(Circle((x + 1.7, y), 0.8, facecolor="white", edgecolor="none", zorder=4))
        return
    shank = _glyph_width(name) - 1.8
    ax.add_patch(Rectangle((x, y - 1.4), 1.8, 2.8, facecolor=SCREW_INK, edgecolor="none", zorder=3))
    ax.add_patch(Rectangle((x + 1.8, y - 0.65), shank, 1.3, facecolor="white", edgecolor=SCREW_INK, lw=0.5, zorder=3))
    tick = x + 2.3
    while tick < x + 1.8 + shank - 0.2:
        ax.plot([tick, tick + 0.3], [y - 0.65, y + 0.65], color=SCREW_INK, lw=0.3, zorder=4)
        tick += 0.55


def _chip_text(line: Hardware) -> str:
    return f"{line.name}  ×{line.qty}" if line.qty else line.name


def _chips(flow: _Flow, lines: list[Hardware], x0: float, width: float) -> list[tuple[float, float, Hardware]]:
    """Where each hardware line goes in rows ``width`` wide from ``x0``: (x, row, line)."""
    placed, x, row = [], x0, 0
    for line in lines:
        w = _glyph_width(line.name) + 2.0 + flow.measure.width(_chip_text(line), CHIP) + 6.0
        if x > x0 and x + w > x0 + width:
            x, row = x0, row + 1
        placed.append((x, row, line))
        x += w
    return placed


CHIP_ROW = 6.0


def _draw_chips(flow: _Flow, placed, top: float) -> None:
    for x, row, line in placed:
        y = top - row * CHIP_ROW - CHIP_ROW / 2

        def draw(ax, x=x, y=y, line=line) -> None:
            _glyph(ax, line.name, x, y)
            ax.text(x + _glyph_width(line.name) + 2.0, y - CHIP * PT * 0.35, _chip_text(line), fontsize=CHIP,
                    weight="bold", color="black", va="baseline", zorder=3)

        flow.add(draw)


def plain(name: str) -> str:
    """A part's name as a reader says it: a label's underscores are the model's, not theirs."""
    return name.replace("_", " ").strip().capitalize() if "_" in name else name


def _plain_item(item: str) -> str:
    """An open item in the words the page uses."""
    item = re.sub(r"^step (\S+) \(\S+\): ", r"Step \1: ", item)
    item = re.sub(r"^(.+): no step installs it$", lambda m: f"{plain(m.group(1))}: no step uses it yet", item)
    return re.sub(r" not stated$", f" {NOT_DECIDED}", item)


class _Guide(_Flow):
    def __init__(self, wi, open_count: int) -> None:
        self.steps_on: dict[int, list[int]] = {}  # page index -> the steps that start on it
        super().__init__(wi, open_count)

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
    screws = hardware(wi.steps)
    if screws:
        _heading(flow, "Screws and nuts", CHIP_ROW)
        placed = _chips(flow, screws, MARGIN + PAD, flow.inner - 2 * PAD)
        height = (placed[-1][1] + 1) * CHIP_ROW + 2 * PAD
        flow.room(height, "screws and nuts")
        top = flow.y
        flow.add(lambda ax: ax.add_patch(_rect(MARGIN, top - height, flow.inner, height, lw=0, edge="none",
                                               face=BOX_FACE, zorder=0)))
        _draw_chips(flow, placed, top - PAD)
        flow.y -= height + 1.0
    also = list(dict.fromkeys(record.name for record in wi.materials))
    if also:
        _lines(flow, [f"Also: {', '.join(also)}"], "what you need")
    tools = wi.equipment()
    if tools:
        _heading(flow, "Tools", TOOL_ROW)
        drives = {tool: [line.name for line in screws if tool in line.tools] for tool in tools}
        _tools(flow, [(tool, f"for {' and '.join(drives[tool])}" if drives[tool] else "") for tool in tools])


TOOL_ROW, TOOLS_PER_ROW = 13.0, 3


def _tool_glyph(ax, name: str, x: float, y: float) -> None:
    """A tool drawn small, by what its name says it is: a hex key's L, a screwdriver, a wrench."""
    from matplotlib.patches import Circle, FancyBboxPatch

    lowered = name.lower()
    if "hex" in lowered or "allen" in lowered:
        ax.plot([x + 1.0, x + 1.0, x + 4.0], [y + 4.0, y - 3.5, y - 3.5], color=SCREW_INK, lw=2.6,
                solid_capstyle="round", solid_joinstyle="round", zorder=3)
    elif "screwdriver" in lowered:
        ax.add_patch(FancyBboxPatch((x + 0.4, y + 0.6), 2.4, 3.6, boxstyle="round,pad=0.3", facecolor=SCREW_INK,
                                    edgecolor="none", zorder=3))
        ax.plot([x + 1.6, x + 1.6], [y + 0.6, y - 4.0], color=SCREW_INK, lw=1.2, zorder=3)
    elif "wrench" in lowered or "spanner" in lowered:
        ax.plot([x + 0.8, x + 3.6], [y - 3.6, y + 2.2], color=SCREW_INK, lw=2.0, solid_capstyle="round", zorder=3)
        ax.add_patch(Circle((x + 3.8, y + 2.8), 1.5, facecolor=SCREW_INK, edgecolor="none", zorder=3))
        ax.add_patch(Circle((x + 4.3, y + 3.4), 0.7, facecolor=BOX_FACE, edgecolor="none", zorder=4))
    else:
        ax.add_patch(Circle((x + 2.2, y), 1.0, facecolor=SCREW_INK, edgecolor="none", zorder=3))


def _tools(flow: _Flow, tools: list[tuple[str, str]]) -> None:
    """The tools as a kit's manual shows them: a small drawing, the tool's name, what it is for."""
    width = (flow.inner - (TOOLS_PER_ROW - 1) * TILE_GAP) / TOOLS_PER_ROW
    for start in range(0, len(tools), TOOLS_PER_ROW):
        flow.room(TOOL_ROW, "tools")
        top = flow.y
        for offset, (name, use) in enumerate(tools[start:start + TOOLS_PER_ROW]):
            x = MARGIN + offset * (width + TILE_GAP)

            def draw(ax, x=x, top=top, name=name, use=use) -> None:
                ax.add_patch(_rect(x, top - TOOL_ROW + 1.5, width, TOOL_ROW - 1.5, lw=0, edge="none", face=BOX_FACE,
                                   zorder=0))
                middle = top - (TOOL_ROW - 1.5) / 2
                _tool_glyph(ax, name, x + 2.0, middle)
                text, small = _fit(flow.measure, name, TEXT - 1.0, width - 11.0)
                ax.text(x + 9.0, middle + (0.6 if use else -small * PT * 0.35), text, fontsize=small, weight="bold",
                        va="baseline", zorder=3)
                if use:
                    words, size = _fit(flow.measure, use, SMALL, width - 11.0)
                    ax.text(x + 9.0, middle - SMALL * PT * 1.2, words, fontsize=size, color=GREY, va="baseline",
                            zorder=3)

            flow.add(draw)
        flow.y -= TOOL_ROW


def _cover(flow: _Flow, wi, open_items: list[str], pictures: dict) -> None:
    flow.cell(_text_cell(flow.measure, "A S S E M B L Y   I N S T R U C T I O N S", flow.inner, SMALL, "bold"),
              "the title")
    flow.y -= 1.0
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


def says(step, *, surfaces: bool = True, need: bool = True) -> list[tuple[str, str]]:
    """What a step says beyond its title, as ``(kind, text)``: what it uses, then each thing it asks
    for. A kind is ``need``, ``text``, ``small`` (a source) or ``open`` (what nobody has decided).
    ``surfaces`` says where a picture outlines them; the page plays no outlines. ``need=False``
    leaves out what it uses, which the guide's parts box shows."""
    lines = []
    if step.units and need:
        lines.append(("need", "You need: " + ", ".join(f"×{len(refs)} {plain(name)}"
                                                       for name, refs in _group(step.units))))
    if any(where == "title" for where, _name in step.missing):
        lines.append(("open", f"Where this number comes from: {NOT_DECIDED}"))
    for op in step.ops:
        shown = None  # a source prints once for the lines of one operation it covers
        if op.surfaces and surfaces:
            lines.append(("need", "The purple outline shows where."))
        for line in op.lines:
            if not need and line.caption in ("Hardware", "Tool"):  # in the parts box, and the tools on the cover
                continue
            caption = "Check" if line.caption == "Inspect" else line.caption
            if line.value is None:
                lines.append(("open", f"{caption}: {NOT_DECIDED}"))
            else:
                lines.append(("text", line.value if op.kind == "instruct" else f"{caption}: {line.value}"))
            if line.source is not None and line.source != shown:
                lines.append(("small", _citation(line.source)))
            elif line.source is None and line.cite:
                lines.append(("open", f"Where this number comes from: {NOT_DECIDED}"))
            shown = line.source or shown
        if op.record:
            lines.append(("text", f"Write down: {op.record}"))
    return lines


def _body(flow: _Flow, step) -> _Cell:
    """What the step says under its picture."""
    cell = _Cell(flow.measure, flow.inner)
    for kind, text in says(step, need=False):
        small = kind == "small"
        cell.text(text, SMALL if small else TEXT, color={"need": GREY, "small": GREY, "open": AMBER}.get(kind, "black"))
    return cell


PAD = 2.5  # inside a parts box
CORNER = 0.34  # the most of the page's width a parts box over its picture's corner takes


def _box_plan(flow: _Flow, step, pictures: dict, index_of: dict[str, int], width: float):
    """A step's parts box at most ``width`` wide, laid out: each part's picture and count, then its
    screws by size; with the box's own width and height (0 when the step uses nothing)."""
    inner = width - 2 * PAD
    tiles = [(pictures.get(f"part-{index_of[refs[0]]}"), len(refs)) for _name, refs in _group(step.units)]
    per_row = max(1, min(len(tiles) or 1, int((inner + 3.0) // (STEP_TILE + 3.0))))
    chips = _chips(flow, hardware([step]), MARGIN + PAD, inner)
    tile_rows = -(-len(tiles) // per_row)
    chip_rows = chips[-1][1] + 1 if chips else 0
    if not tile_rows and not chip_rows:
        return tiles, per_row, chips, 0.0, 0.0
    used = per_row * (STEP_TILE + 3.0) - 3.0 if tiles else 0.0
    for x, _row, line in chips:
        used = max(used, x - MARGIN - PAD + _glyph_width(line.name) + 2.0
                   + flow.measure.width(_chip_text(line), CHIP, "bold") + 1.0)
    return tiles, per_row, chips, used + 2 * PAD, 2 * PAD + tile_rows * (STEP_TILE + 4.5) + chip_rows * CHIP_ROW


def _parts_box(flow: _Flow, plan, top: float) -> None:
    """What the step uses, in a grey box from ``top`` at the left margin: as a kit's manual opens
    each step."""
    tiles, per_row, chips, width, height = plan
    if not height:
        return
    flow.add(lambda ax: ax.add_patch(_rect(MARGIN, top - height, width, height, lw=0, edge="none",
                                           face=BOX_FACE, zorder=2)))
    for index, (path, count) in enumerate(tiles):
        row, col = divmod(index, per_row)
        x = MARGIN + PAD + col * (STEP_TILE + 3.0)
        y = top - PAD - row * (STEP_TILE + 4.5)
        if path is not None:
            pixels = read_pixels(path)
            flow.add(lambda ax, x=x, y=y, pixels=pixels: ax.imshow(
                pixels, extent=(x, x + STEP_TILE, y - STEP_TILE, y), interpolation="none", zorder=3))
        flow.add(lambda ax, x=x, y=y, count=count: ax.text(
            x + STEP_TILE, y - STEP_TILE - 0.6 - CHIP * PT, f"×{count}", fontsize=CHIP, weight="bold",
            ha="right", va="baseline", zorder=3))
    rows = -(-len(tiles) // per_row)
    _draw_chips(flow, chips, top - PAD - rows * (STEP_TILE + 4.5))


def _step(flow: _Flow, step, pictures: dict, index_of: dict[str, int]) -> None:
    title = _Cell(flow.measure, flow.inner - BADGE - BOX - 8.0)
    title.text(step.title, STEP, weight="bold")
    head = max(title.height, BADGE)
    path = pictures.get(step.number)
    height = flow.inner * GUIDE_PX[1] / GUIDE_PX[0] if path is not None else 0.0
    body = _body(flow, step)
    notes = sum(_notice_height(flow, notice) for notice in step.notices)
    # The box sits in the picture's top-left corner, where the assembly's framing leaves room; above
    # the picture when there is none, or the box would cover too much of it.
    box = _box_plan(flow, step, pictures, index_of, flow.inner * CORNER)
    over = path is not None and box[4] <= 0.55 * height
    if not over and box[4]:
        box = _box_plan(flow, step, pictures, index_of, flow.inner)
    above = box[4] + 1.5 if box[4] and not over else 0.0
    flow.room(head + 1.5 + notes + above + height + body.height + 5.0, f"step {step.label}")
    top = flow.y
    radius = BADGE / 2
    x = MARGIN + radius

    def badge(ax) -> None:
        from matplotlib.patches import Circle

        ax.add_patch(Circle((x, top - radius), radius, facecolor=INK, edgecolor="none", zorder=2))
        ax.text(x, top - radius - STEP * PT * 0.36, step.label, fontsize=STEP, weight="bold", color="white",
                ha="center", va="baseline", zorder=3)

    flow.add(badge)
    flow.steps_on.setdefault(len(flow.pages) - 1, []).append(step.number)
    flow.add(lambda ax: title.draw(ax, MARGIN + BADGE + 4.0, top - (head - title.height) / 2))
    flow.add(lambda ax: ax.add_patch(_rect(flow.w - MARGIN - BOX, top - (head + BOX) / 2, BOX, BOX, lw=0.9, edge=GREY)))
    flow.y -= head + 1.5
    for notice in step.notices:
        _notice(flow, notice.caption, notice)
    if box[4] and not over:
        _parts_box(flow, box, flow.y)
        flow.y -= box[4] + 1.5
    if path is not None:
        _image(flow, path, MARGIN, flow.y, flow.inner, height)
        if over:
            _parts_box(flow, box, flow.y)
        flow.y -= height + 1.5
    if body.height:
        flow.cell(body, f"step {step.label}")
    flow.y -= 5.0


def layout(wi, open_items: list[str], pictures: dict) -> _Flow:
    """The pages as draw commands: the cover, then the steps."""
    flow = _Guide(wi, len(open_items))
    _cover(flow, wi, open_items, pictures)
    flow.new_page()
    _key(flow, wi.pictures and any(step.arrow for step in wi.steps))
    index_of = {ref: index for index, (_name, refs, _steps) in enumerate(parts(wi)) for ref in refs}
    for step in wi.steps:
        _step(flow, step, pictures, index_of)
    return flow


KEY = 8.0  # a key's swatch


def _key(flow: _Flow, lines: bool) -> None:
    """How to read the steps, as a kit's manual opens them: blue is what the step adds, white what is
    already in, the grey box what it uses, and (where a step pulls its parts out) the thin line to where
    each one goes."""
    from matplotlib.patches import FancyArrowPatch

    entries = [("new", "New in this step"), ("old", "Already in"), ("box", "What the step uses")]
    if lines:
        entries.append(("line", "Where it goes"))
    height = PAD * 2 + 5.0 + KEY + 1.0
    flow.room(height + 3.0, "the key")
    top = flow.y
    flow.add(lambda ax: ax.add_patch(_rect(MARGIN, top - height, flow.inner, height, lw=0, edge="none",
                                           face=BOX_FACE, zorder=0)))
    flow.add(lambda ax: ax.text(MARGIN + PAD, top - PAD - TEXT * PT * 0.8, "How to read", fontsize=TEXT,
                                weight="bold", va="baseline", zorder=3))
    step = (flow.inner - 2 * PAD) / len(entries)
    y = top - PAD - 5.0
    for index, (kind, words) in enumerate(entries):
        x = MARGIN + PAD + index * step

        def draw(ax, x=x, kind=kind, words=words) -> None:
            if kind == "new":
                ax.add_patch(_rect(x, y - KEY, KEY, KEY, lw=0.5, edge="black", face=FILL, zorder=3))
            elif kind == "old":
                ax.add_patch(_rect(x, y - KEY, KEY, KEY, lw=0.5, edge="black", face="white", zorder=3))
            elif kind == "box":
                ax.add_patch(_rect(x, y - KEY, KEY, KEY, lw=0.5, edge=GREY, face="white", zorder=3))
                ax.text(x + KEY - 0.6, y - KEY + 0.8, "×1", fontsize=SMALL - 1.5, weight="bold", ha="right",
                        va="baseline", zorder=4)
            else:
                ax.add_patch(FancyArrowPatch((x + KEY / 2, y), (x + KEY / 2, y - KEY), arrowstyle="-|>",
                                             mutation_scale=5, lw=0.8, color=GUIDE_LINE, zorder=3))
            ax.text(x + KEY + 2.0, y - KEY / 2 - TEXT * PT * 0.35, words, fontsize=TEXT - 1.5, color="black",
                    va="baseline", zorder=3)

        flow.add(draw)
    flow.y -= height + 3.0


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
    here = getattr(flow, "steps_on", {}).get(page - 1)
    if here:  # a dot per step, this page's dark: how far through the build you are
        from matplotlib.patches import Circle

        count = len(wi.steps)
        x0 = flow.w / 2 - (count * DOT + (count - 1) * DOT_GAP) / 2 + DOT / 2
        for index, step in enumerate(wi.steps):
            ax.add_patch(Circle((x0 + index * (DOT + DOT_GAP), MARGIN - 1.2), DOT / 2, edgecolor="none", zorder=3,
                                facecolor=INK if step.number in here else FAINT))
