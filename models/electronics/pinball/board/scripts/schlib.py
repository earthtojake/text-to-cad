"""Write KiCad schematic sheets as text (the pcb skill's documented way to write a hierarchy), each symbol copied
from the project's library (pinball.kicad_sym, power.kicad_sym) into its sheet's lib_symbols. Pin positions use
KiCad's own transform (the library frame is y up, the sheet y down; angle counter-clockwise). Every uuid comes
from its item's name, so a rerun writes the same files and the board's links survive."""
from __future__ import annotations

import math
import os
import uuid as _uuid

from cad.engine.formats.kicad.sexpr import Sym, dumps, find, find_all, parse

PROJECT = "pinball"
NS = _uuid.UUID("3f0c9a4e-2b7f-4c1a-9e55-5c1c0de0ba11")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def uid(*parts) -> str:
    return str(_uuid.uuid5(NS, "/".join(str(p) for p in parts)))


_LIBS: dict[str, dict] = {}


def _library(lib: str) -> dict:
    if lib not in _LIBS:
        tree = parse(open(os.path.join(HERE, f"{lib}.kicad_sym"), encoding="utf-8").read())
        _LIBS[lib] = {s[1]: s for s in find_all(tree, "symbol")}
    return _LIBS[lib]


def lib_symbol(lib_id: str):
    lib, name = lib_id.split(":")
    out = [x for x in _library(lib)[name]]
    out[1] = lib_id
    return out


def pins_of(lib_id: str) -> dict[str, list[tuple[float, float, float, str, str]]]:
    """number -> [(x, y, angle, name, type)] in the library frame."""
    out: dict[str, list] = {}
    for unit in find_all(lib_symbol(lib_id), "symbol"):
        for pin in find_all(unit, "pin"):
            at = find(pin, "at")
            out.setdefault(find(pin, "number")[1], []).append(
                (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0, find(pin, "name")[1], str(pin[1])))
    return out


def transform(angle: float):
    q = round(angle / 90) % 4
    cos, sin = ((1, 0), (0, 1), (-1, 0), (0, -1))[q]

    def apply(px, py):
        x, y = px, -py
        return x * cos + y * sin, -x * sin + y * cos
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

    def out(self, number: str) -> tuple[int, int]:
        """Unit vector pointing away from the body, on the sheet."""
        _, _, a, *_ = self._pins[number][0]
        a = math.radians(a + 180)
        dx, dy = self.t(math.cos(a), math.sin(a))
        return (round(dx), round(dy))


class Sheet:
    def __init__(self, name: str, file: str, path: str, title: str, paper: str = "A3", root_uuid: str = ""):
        self.name, self.file, self.path, self.title, self.paper = name, file, path, title, paper
        self.uuid = root_uuid or uid("sheet", file)
        self.sheet_uuid = uid("sheetsym", file)
        self.items: list = []
        self.used: dict[str, list] = {}
        self.placed: dict[str, Placed] = {}
        self.ends: list = []            # wire ends and pin ends, for the junction dots

    # -- symbols ---------------------------------------------------------------------------------
    def symbol(self, lib_id, ref, x, y, angle=0, value=None, footprint=None, fields=None, in_bom=True, on_board=True,
               hide_value=False, ref_at=None, value_at=None):
        if lib_id not in self.used:
            self.used[lib_id] = lib_symbol(lib_id)
        x, y = r(x), r(y)
        p = Placed(self, lib_id, ref, x, y, angle)
        self.placed[ref] = p
        is_power = lib_id.startswith("power:")
        props = {pr[1]: pr[2] for pr in find_all(self.used[lib_id], "property")}
        if value is None:
            value = props.get("Value", "")
        if footprint is None:
            footprint = props.get("Footprint", "")
        extra = {k: props[k] for k in ("MPN", "Manufacturer", "LCSC") if props.get(k)}
        extra.update(fields or {})
        # a power symbol's text stands beyond its glyph: below a ground, above a supply, the other way when turned over
        side = (1 if "GND" in lib_id else -1) * (-1 if round(angle) % 360 == 180 else 1)
        if ref_at is None:
            ref_at = (x + 2.54, y - 1.27) if not is_power else (x, y + side * 3.81)
        if value_at is None:
            value_at = (x + 2.54, y + 1.27) if not is_power else (x, y + side * 5.08)
        # KiCad draws a field of a symbol turned 180 or 270 degrees upright by mirroring its justification: ask for
        # the opposite, so the text runs right from `ref_at` / `value_at` as it does on an unturned symbol
        just = None if is_power else [Sym("justify"), Sym("right" if round(angle) % 360 in (180, 270) else "left")]

        def prop(name, val, at, hide=False, j=just, size=1.27):
            # KiCad turns a field with its symbol: a field stands level on a turned symbol at the symbol's angle
            node = [Sym("property"), name, val, [Sym("at"), r(at[0]), r(at[1]), angle if angle in (90, 270) and not is_power else 0]]
            eff = [Sym("effects"), [Sym("font"), [Sym("size"), size, size]]]
            if j:
                eff.append(j)
            if hide:
                node.append([Sym("hide"), Sym("yes")])
            node.append(eff)
            return node
        node = [Sym("symbol"), [Sym("lib_id"), lib_id], [Sym("at"), x, y, angle]]
        node += [[Sym("unit"), 1], [Sym("exclude_from_sim"), Sym("no")],
                 [Sym("in_bom"), Sym("yes" if in_bom and not is_power else "no")],
                 [Sym("on_board"), Sym("yes" if on_board else "no")], [Sym("dnp"), Sym("no")],
                 [Sym("uuid"), uid(self.file, "sym", ref)],
                 prop("Reference", ref, ref_at, hide=is_power),
                 prop("Value", value, value_at, hide=hide_value),
                 prop("Footprint", footprint, (x, y), hide=True),
                 prop("Datasheet", props.get("Datasheet", ""), (x, y), hide=True)]
        for k, v in extra.items():
            node.append(prop(k, v, (x, y), hide=True))
        for number in p._pins:
            node.append([Sym("pin"), number, [Sym("uuid"), uid(self.file, "pin", ref, number)]])
        node.append([Sym("instances"), [Sym("project"), PROJECT,
                                       [Sym("path"), self.path, [Sym("reference"), ref], [Sym("unit"), 1]]]])
        self.items.append(node)
        # pins stacked on one point (IOVDD's six) are one end: no junction dot at a lone pin
        for at in dict.fromkeys(p.pin(number) for number in p._pins):
            self.ends.append(at)
        return p

    _pwr = 0

    def power(self, net: str, at, angle=None):
        """A power symbol whose pin is at `at`: ground points down, a supply up (angle overrides)."""
        Sheet._pwr += 1
        ref = f"#PWR{Sheet._pwr:04d}" if net != "PWR_FLAG" else f"#FLG{Sheet._pwr:04d}"
        x, y = r(at[0]), r(at[1])
        if angle is None:
            angle = 0
        if net == "PWR_FLAG":
            return self.symbol("power:PWR_FLAG", ref, x, y, angle, value="PWR_FLAG", ref_at=(x, y - 2.54),
                               value_at=(x, y - 4.2), hide_value=True)
        return self.symbol(f"power:{net}", ref, x, y, angle, value=net)

    # -- connection items ---------------------------------------------------------------------------
    def wire(self, *pts):
        for a, b in zip(pts, pts[1:]):
            a, b = (r(a[0]), r(a[1])), (r(b[0]), r(b[1]))
            if a == b:
                continue
            assert a[0] == b[0] or a[1] == b[1], f"{self.file}: a slanted wire {a} {b}"
            self.items.append([Sym("wire"), [Sym("pts"), [Sym("xy"), a[0], a[1]], [Sym("xy"), b[0], b[1]]],
                               [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]],
                               [Sym("uuid"), uid(self.file, "wire", a, b)]])
            self.ends += [a, b]

    def junction(self, at):
        at = (r(at[0]), r(at[1]))
        self.items.append([Sym("junction"), [Sym("at"), at[0], at[1]], [Sym("diameter"), 0],
                           [Sym("color"), 0, 0, 0, 0], [Sym("uuid"), uid(self.file, "junction", at)]])

    def nc(self, at):
        at = (r(at[0]), r(at[1]))
        self.items.append([Sym("no_connect"), [Sym("at"), at[0], at[1]], [Sym("uuid"), uid(self.file, "nc", at)]])

    def label(self, text, at, direction=(1, 0), kind="label", shape="bidirectional"):
        angle = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[tuple(direction)]
        just = {0: "left", 180: "right", 90: "left", 270: "right"}[angle]
        at = (r(at[0]), r(at[1]))
        eff = [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]], [Sym("justify"), Sym(just)] if kind != "label" else
               [Sym("justify"), Sym(just), Sym("bottom")]]
        if kind == "label":
            node = [Sym("label"), text, [Sym("at"), at[0], at[1], angle], eff]
        else:
            node = [Sym("hierarchical_label"), text, [Sym("shape"), Sym(shape)], [Sym("at"), at[0], at[1], angle], eff]
        node.append([Sym("uuid"), uid(self.file, kind, text, at)])
        self.items.append(node)
        self.ends.append(at)

    def stub(self, part: Placed, number: str, net, length=2.54, kind="label", shape="bidirectional"):
        """A short wire straight out of a pin, then its label, power symbol or (net None) a no-connect."""
        a = part.pin(number)
        if net is None:
            self.nc(a)
            return a
        d = part.out(number)
        b = (r(a[0] + d[0] * length), r(a[1] + d[1] * length))
        self.wire(a, b)
        if kind == "power":
            self.power(net, b)
        else:
            self.label(net, b, d, kind=kind, shape=shape)
        return b

    def text(self, s, at, size=1.27, bold=False):
        self.items.append([Sym("text"), s, [Sym("exclude_from_sim"), Sym("no")], [Sym("at"), r(at[0]), r(at[1]), 0],
                           [Sym("effects"), [Sym("font"), [Sym("size"), size, size], *([[Sym("bold"), Sym("yes")]] if bold else [])],
                            [Sym("justify"), Sym("left"), Sym("bottom")]], [Sym("uuid"), uid(self.file, "text", s, at)]])

    def box(self, x0, y0, x1, y1, title=None):
        """A subcircuit's dashed box and its title."""
        self.items.append([Sym("rectangle"), [Sym("start"), r(x0), r(y0)], [Sym("end"), r(x1), r(y1)],
                           [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("dash")]], [Sym("fill"), [Sym("type"), Sym("none")]],
                           [Sym("uuid"), uid(self.file, "box", x0, y0)]])
        if title:
            self.text(title, (x0 + 1.27, y0 + 3.81), size=1.8, bold=True)

    def sheet_symbol(self, child: "Sheet", x, y, w, h, pins, page):
        """pins: [(name, shape, side 'left'|'right', y)]; returns name -> the pin's point."""
        x, y = r(x), r(y)
        w, h = r(w), r(h)
        node = [Sym("sheet"), [Sym("at"), x, y], [Sym("size"), w, h], [Sym("exclude_from_sim"), Sym("no")],
                [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")], [Sym("dnp"), Sym("no")],
                [Sym("fields_autoplaced"), Sym("yes")],
                [Sym("stroke"), [Sym("width"), 0.1524], [Sym("type"), Sym("solid")]],
                [Sym("fill"), [Sym("color"), 255, 255, 230, 1]], [Sym("uuid"), child.sheet_uuid],
                [Sym("property"), "Sheetname", child.name, [Sym("at"), x, round(y - 0.7116, 4), 0],
                 [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]], [Sym("justify"), Sym("left"), Sym("bottom")]]],
                [Sym("property"), "Sheetfile", child.file, [Sym("at"), x, round(y + h + 0.5846, 4), 0],
                 [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]], [Sym("justify"), Sym("left"), Sym("top")]]]]
        ends = {}
        for name, shape, side, py in pins:
            px = x if side == "left" else r(x + w)
            ang = 180 if side == "left" else 0
            node.append([Sym("pin"), name, Sym(shape), [Sym("at"), px, r(py), ang],
                         [Sym("uuid"), uid(child.file, "sheetpin", name)],
                         [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]],
                          [Sym("justify"), Sym("left" if side == "left" else "right")]]])
            ends[name] = (px, r(py))
            self.ends.append(ends[name])
        node.append([Sym("instances"), [Sym("project"), PROJECT, [Sym("path"), self.path, [Sym("page"), str(page)]]]])
        self.items.append(node)
        return ends

    # -- file -----------------------------------------------------------------------------------
    def write(self, folder: str, root=False, date="2026-11-08", rev="A", company="SHORT CIRCUIT (text-to-cad demo)"):
        head = [Sym("kicad_sch"), [Sym("version"), 20250114], [Sym("generator"), "eeschema"],
                [Sym("generator_version"), "9.0"], [Sym("uuid"), self.uuid], [Sym("paper"), self.paper],
                [Sym("title_block"), [Sym("title"), self.title], [Sym("date"), date], [Sym("rev"), rev],
                 [Sym("company"), company]],
                [Sym("lib_symbols"), *self.used.values()]]
        tail = []
        if root:
            tail = [[Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]]]
        tail.append([Sym("embedded_fonts"), Sym("no")])
        text = dumps(head + self.items + tail) + "\n"
        with open(os.path.join(folder, self.file), "w", encoding="utf-8") as fh:
            fh.write(text)
