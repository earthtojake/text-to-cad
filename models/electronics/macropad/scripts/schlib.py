"""Write KiCad schematic sheets as text (the pcb skill's documented fallback to the IPC edit), copying
each symbol from KiCad's stock libraries into the sheet's lib_symbols. Pin positions use KiCad's own
transform (the library frame is y up, the sheet y down; angle counter-clockwise)."""
from __future__ import annotations

import math
import os
import uuid as _uuid

from sexp import Sym, dump, find, first, parse

SYMBOL_DIR = os.environ.get("KICAD10_SYMBOL_DIR", "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols")
PROJECT = "macropad"
NS = _uuid.UUID("6d1c9a4e-2b7f-4c1a-9e55-0b5a1c0de000")


def uid(*parts) -> str:
    """A stable uuid from a name, so a rerun writes the same file (and the board's links survive)."""
    return str(_uuid.uuid5(NS, "/".join(str(p) for p in parts)))


_LIBS: dict[str, dict] = {}


def _library(lib: str) -> dict:
    if lib not in _LIBS:
        tree = parse(open(f"{SYMBOL_DIR}/{lib}.kicad_sym", encoding="utf-8").read())[0]
        _LIBS[lib] = {s[1]: s for s in find(tree, "symbol")}
    return _LIBS[lib]


def lib_symbol(lib_id: str):
    """The symbol flattened as a schematic embeds it: an `extends` resolved into its base's units."""
    lib, name = lib_id.split(":")
    syms = _library(lib)
    sym = syms[name]
    ext = first(sym, "extends")
    if ext is None:
        out = [x for x in sym]
        out[1] = lib_id
        return out
    base = syms[ext[1]]
    base_name = base[1]
    out = [Sym("symbol"), lib_id]
    for item in base[2:]:
        if isinstance(item, list) and item and item[0] == "property":
            continue
        if isinstance(item, list) and item and item[0] == "symbol":
            unit = [x for x in item]
            unit[1] = unit[1].replace(base_name, name, 1)
            out.append(unit)
        else:
            out.append(item)
    props = [x for x in sym if isinstance(x, list) and x and x[0] == "property"]
    # properties after the header flags, before the units
    head = [x for x in out[2:] if not (isinstance(x, list) and x and x[0] == "symbol")]
    units = [x for x in out[2:] if isinstance(x, list) and x and x[0] == "symbol"]
    return [Sym("symbol"), lib_id, *head, *props, *units]


def pins_of(lib_id: str) -> dict[str, list[tuple[float, float, float, str, str]]]:
    """number -> [(x, y, angle, name, type)] in the library frame (unit 1 and shared units)."""
    sym = lib_symbol(lib_id)
    out: dict[str, list] = {}
    for unit in find(sym, "symbol"):
        for pin in find(unit, "pin"):
            at = first(pin, "at")
            out.setdefault(first(pin, "number")[1], []).append(
                (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0, first(pin, "name")[1], str(pin[1])))
    return out


def transform(angle: float, mirror: str | None = None):
    q = round(angle / 90) % 4
    cos, sin = ((1, 0), (0, 1), (-1, 0), (0, -1))[q]

    def apply(px, py):
        x, y = px, -py
        x, y = x * cos + y * sin, -x * sin + y * cos
        if mirror == "x":
            y = -y
        elif mirror == "y":
            x = -x
        return x, y
    return apply


def r(v: float) -> float:
    """Every coordinate on KiCad's 1.27 mm (50 mil) connection grid."""
    return round(round(v / 1.27) * 1.27, 4)


class Placed:
    def __init__(self, sheet, lib_id, ref, x, y, angle):
        self.sheet, self.lib_id, self.ref, self.x, self.y, self.angle = sheet, lib_id, ref, x, y, angle
        self._pins = pins_of(lib_id)
        self.t = transform(angle)

    def pin(self, number: str) -> tuple[float, float]:
        px, py, *_ = self._pins[number][0]
        dx, dy = self.t(px, py)
        return (r(self.x + dx), r(self.y + dy))

    def out(self, number: str) -> tuple[float, float]:
        """Unit vector pointing away from the body, on the sheet."""
        _, _, a, *_ = self._pins[number][0]
        a = math.radians(a + 180)
        dx, dy = self.t(math.cos(a), math.sin(a))
        return (round(dx), round(dy))


class Sheet:
    def __init__(self, name: str, file: str, path: str, title: str, paper: str = "A4", root_uuid: str = ""):
        self.name, self.file, self.path, self.title, self.paper = name, file, path, title, paper
        self.uuid = root_uuid or uid("sheet", file)
        self.items: list = []
        self.used: dict[str, list] = {}
        self.pwr = 0
        self.placed: dict[str, Placed] = {}

    # -- symbols ---------------------------------------------------------------------------------
    def symbol(self, lib_id, ref, value, x, y, angle=0, footprint="", fields=None, in_bom=True, on_board=True,
               hide_value=False, ref_at=None, value_at=None, mirror=None):
        if lib_id not in self.used:
            self.used[lib_id] = lib_symbol(lib_id)
        x, y = r(x), r(y)
        p = Placed(self, lib_id, ref, x, y, angle)
        self.placed[ref] = p
        is_power = lib_id.startswith("power:")
        u = uid(self.file, "sym", ref)
        # field placement: beside the body
        if ref_at is None:
            ref_at = (x + 2.54, y - 1.27) if not is_power else (x, y + (3.81 if "GND" in lib_id else -3.81))
        if value_at is None:
            value_at = (x + 2.54, y + 1.27) if not is_power else (x, y + (5.08 if "GND" in lib_id else -5.08))
        just = [Sym("justify"), Sym("left")] if not is_power else None

        def prop(name, val, at, hide=False, j=just, size=1.27):
            node = [Sym("property"), name, val, [Sym("at"), r(at[0]), r(at[1]), angle if (angle in (90, 270) and not is_power) else 0]]
            eff = [Sym("effects"), [Sym("font"), [Sym("size"), size, size]]]
            if j:
                eff.append(j)
            if hide:
                node.append([Sym("hide"), Sym("yes")])
            node.append(eff)
            return node
        node = [Sym("symbol"), [Sym("lib_id"), lib_id], [Sym("at"), r(x), r(y), angle]]
        if mirror:
            node.append([Sym("mirror"), Sym(mirror)])
        node += [[Sym("unit"), 1], [Sym("exclude_from_sim"), Sym("no")],
                 [Sym("in_bom"), Sym("yes" if in_bom and not is_power else "no")],
                 [Sym("on_board"), Sym("yes" if on_board else "no")], [Sym("dnp"), Sym("no")],
                 [Sym("uuid"), u],
                 prop("Reference", ref, ref_at, hide=is_power),
                 prop("Value", value, value_at, hide=hide_value),
                 prop("Footprint", footprint, (x, y), hide=True),
                 prop("Datasheet", (fields or {}).pop("Datasheet", ""), (x, y), hide=True)]
        for k, v in (fields or {}).items():
            node.append(prop(k, v, (x, y), hide=True))
        for number in p._pins:
            node.append([Sym("pin"), number, [Sym("uuid"), uid(self.file, "pin", ref, number)]])
        node.append([Sym("instances"), [Sym("project"), PROJECT,
                                       [Sym("path"), self.path, [Sym("reference"), ref], [Sym("unit"), 1]]]])
        self.items.append(node)
        return p

    def power(self, net: str, at, angle=0):
        self.pwr += 1
        ref = f"#PWR{self.file[:2].upper()}{self.pwr:02d}" if net != "PWR_FLAG" else f"#FLG{self.file[:2].upper()}{self.pwr:02d}"
        lib = f"power:{net}"
        x, y = at
        if net == "PWR_FLAG":
            return self.symbol(lib, ref, "PWR_FLAG", x, y, angle, ref_at=(x, y - 2.54), value_at=(x, y - 4.2))
        if angle == 180:
            return self.symbol(lib, ref, net, x, y, angle, ref_at=(x, y - 3.81), value_at=(x, y - 5.08))
        if angle in (90, 270):
            off = -5.08 if angle == 270 else 5.08
            return self.symbol(lib, ref, net, x, y, angle, ref_at=(x + off, y + 2), value_at=(x + off, y))
        return self.symbol(lib, ref, net, x, y, angle)

    # -- connection items ---------------------------------------------------------------------------
    def wire(self, *pts):
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            self.items.append([Sym("wire"), [Sym("pts"), [Sym("xy"), r(a[0]), r(a[1])], [Sym("xy"), r(b[0]), r(b[1])]],
                               [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]],
                               [Sym("uuid"), uid(self.file, "wire", a, b)]])

    def junction(self, at):
        self.items.append([Sym("junction"), [Sym("at"), r(at[0]), r(at[1])], [Sym("diameter"), 0],
                           [Sym("color"), 0, 0, 0, 0], [Sym("uuid"), uid(self.file, "junction", at)]])

    def nc(self, at):
        self.items.append([Sym("no_connect"), [Sym("at"), r(at[0]), r(at[1])], [Sym("uuid"), uid(self.file, "nc", at)]])

    def label(self, text, at, direction=(1, 0), kind="label", shape="bidirectional"):
        angle = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[direction]
        just = {0: "left", 180: "right", 90: "left", 270: "right"}[angle]
        eff = [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]], [Sym("justify"), Sym(just)] if kind != "label" else
               [Sym("justify"), Sym(just), Sym("bottom")]]
        if kind == "label":
            node = [Sym("label"), text, [Sym("at"), r(at[0]), r(at[1]), angle], eff]
        else:
            node = [Sym("hierarchical_label"), text, [Sym("shape"), Sym(shape)], [Sym("at"), r(at[0]), r(at[1]), angle], eff]
        node.append([Sym("uuid"), uid(self.file, kind, text, at)])
        self.items.append(node)

    def stub(self, part: Placed, number: str, net: str | None, length=2.54, kind="label", shape="bidirectional",
             power_angle=None):
        """A short wire straight out of a pin, then its label, power symbol or a no-connect."""
        a = part.pin(number)
        if net is None:
            self.nc(a)
            return a
        d = part.out(number)
        b = (r(a[0] + d[0] * length), r(a[1] + d[1] * length))
        self.wire(a, b)
        if kind == "power":
            if power_angle is None:
                power_angle = 0 if net != "GND" else 0
            self.power(net, b, power_angle)
        else:
            self.label(net, b, d, kind=kind, shape=shape)
        return b

    def text(self, s, at, size=1.8, bold=True):
        self.items.append([Sym("text"), s, [Sym("exclude_from_sim"), Sym("no")], [Sym("at"), r(at[0]), r(at[1]), 0],
                           [Sym("effects"), [Sym("font"), [Sym("size"), size, size]] + ([[Sym("bold"), Sym("yes")]] if bold else []),
                            [Sym("justify"), Sym("left"), Sym("bottom")]], [Sym("uuid"), uid(self.file, "text", s, at)]])

    def box(self, x0, y0, x1, y1, title=None):
        self.items.append([Sym("rectangle"), [Sym("start"), r(x0), r(y0)], [Sym("end"), r(x1), r(y1)],
                           [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("dash")]], [Sym("fill"), [Sym("type"), Sym("none")]],
                           [Sym("uuid"), uid(self.file, "box", x0, y0)]])
        if title:
            self.text(title, (x0 + 1.27, y0 + 3.0), size=1.6)

    def sheet_symbol(self, child: "Sheet", x, y, w, h, pins, page):
        """pins: [(name, shape, side 'left'|'right', y)]"""
        node = [Sym("sheet"), [Sym("at"), r(x), r(y)], [Sym("size"), r(w), r(h)], [Sym("exclude_from_sim"), Sym("no")],
                [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")], [Sym("dnp"), Sym("no")],
                [Sym("fields_autoplaced"), Sym("yes")],
                [Sym("stroke"), [Sym("width"), 0.1524], [Sym("type"), Sym("solid")]],
                [Sym("fill"), [Sym("color"), 0, 0, 0, 0.0]], [Sym("uuid"), child.sheet_uuid],
                [Sym("property"), "Sheetname", child.name, [Sym("at"), r(x), r(y - 0.72), 0],
                 [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]], [Sym("justify"), Sym("left"), Sym("bottom")]]],
                [Sym("property"), "Sheetfile", child.file, [Sym("at"), r(x), r(y + h + 0.59), 0],
                 [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]], [Sym("justify"), Sym("left"), Sym("top")]]]]
        ends = {}
        for name, shape, side, py in pins:
            px = x if side == "left" else x + w
            ang = 180 if side == "left" else 0
            node.append([Sym("pin"), name, Sym(shape), [Sym("at"), r(px), r(py), ang],
                         [Sym("uuid"), uid(child.file, "sheetpin", name)],
                         [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]],
                          [Sym("justify"), Sym("left" if side == "left" else "right")]]])
            ends[name] = (r(px), r(py))
        node.append([Sym("instances"), [Sym("project"), PROJECT, [Sym("path"), self.path, [Sym("page"), str(page)]]]])
        self.items.append(node)
        return ends

    # -- file -----------------------------------------------------------------------------------
    def write(self, folder: str, root=False, date="2026-11-06", rev="A"):
        head = [Sym("kicad_sch"), [Sym("version"), 20250114], [Sym("generator"), "eeschema"],
                [Sym("generator_version"), "9.0"], [Sym("uuid"), self.uuid], [Sym("paper"), self.paper],
                [Sym("title_block"), [Sym("title"), self.title], [Sym("date"), date], [Sym("rev"), rev],
                 [Sym("company"), "Nine macropad (text-to-cad demo)"]],
                [Sym("lib_symbols"), *self.used.values()]]
        tail = []
        if root:
            tail = [[Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]]]
        tail.append([Sym("embedded_fonts"), Sym("no")])
        text = dump(head + self.items + tail) + "\n"
        with open(os.path.join(folder, self.file), "w", encoding="utf-8") as fh:
            fh.write(text)
