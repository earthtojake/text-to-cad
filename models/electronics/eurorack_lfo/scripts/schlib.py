"""A tiny writer for KiCad schematic sheets: symbols copied from KiCad's stock libraries, each pin given a
stub wire and a label, power symbol, hierarchical label or no-connect; wires, junctions, boxes and text.
Standard library only. Coordinates are millimetres on the sheet, y down, every point on the 1.27 mm grid."""

from __future__ import annotations

import math
import uuid as _uuid

import kilib

PROJECT = "twin_orbit"
G = 1.27
_NS = _uuid.UUID("5d1e0000-0000-4000-8000-00000000c0de")


def uid(*key: object) -> str:
    """A stable uuid from a key, so a second run writes the same file."""
    return str(_uuid.uuid5(_NS, "/".join(map(str, key))))


def snap(v: float) -> float:
    return round(round(v / G) * G, 4)


def f(v: float) -> str:
    return f"{round(v, 4):g}"


_FONT = "(effects (font (size 1.27 1.27)))"
_HIDE = "(effects (font (size 1.27 1.27)) (hide yes))"

POWER_UP = {"+12V", "-12V", "PWR_FLAG"}       # graphic above its pin
POWER_DOWN = {"GND"}                          # graphic below its pin
POWER_NETS = {"+12V", "-12V", "GND"}

_DIR = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}  # library frame, y up


def _rot(x: float, y: float, a: int) -> tuple[float, float]:
    r = math.radians(a)
    return (round(x * math.cos(r) - y * math.sin(r), 4), round(x * math.sin(r) + y * math.cos(r), 4))


class Pin:
    def __init__(self, part: "Part", number: str, at: tuple[float, float], out: tuple[int, int], etype: str):
        self.part, self.number, self.at, self.out, self.etype = part, number, at, out, etype

    def end(self, length: float = 2.54) -> tuple[float, float]:
        return (round(self.at[0] + self.out[0] * length, 4), round(self.at[1] + self.out[1] * length, 4))


class Part:
    def __init__(self, sheet: "Sheet", lib: str, name: str, refs: dict[str, str], value: str, at, rot=0, unit=1,
                 footprint="", fields=None, ref_offset=None, value_offset=None, hide_value=False, mirror=""):
        self.sheet, self.lib, self.name, self.refs, self.value = sheet, lib, name, refs, value
        self.at = (snap(at[0]), snap(at[1]))
        self.rot, self.unit, self.footprint = rot, unit, footprint
        self.fields = fields or {}
        self.ref_offset, self.value_offset, self.hide_value = ref_offset, value_offset, hide_value
        self.mirror = mirror
        self.lib_id = f"{lib}:{name}"
        sheet.need(lib, name)
        self._pins = kilib.pins(sheet.libsyms[self.lib_id])
        self.key = (sheet.name, next(iter(refs.values())), unit)

    def pin(self, number: str) -> Pin:
        entry = self._pins.get((self.unit, number)) or self._pins.get((0, number))
        if entry is None:
            raise KeyError(f"{self.lib_id} unit {self.unit} has no pin {number}")
        x, y, a, etype = entry
        if self.mirror == "y":
            x, a = -x, {0: 180, 180: 0}.get(a, a)
        elif self.mirror == "x":
            y, a = -y, {90: 270, 270: 90}.get(a, a)
        rx, ry = _rot(x, y, self.rot)
        at = (round(self.at[0] + rx, 4), round(self.at[1] - ry, 4))
        dx, dy = _DIR[a]
        ox, oy = _rot(-dx, -dy, self.rot)
        return Pin(self, number, at, (int(round(ox)), int(round(-oy))), etype)

    def sexpr(self) -> str:
        x, y = self.at
        ref0 = next(iter(self.refs.values()))
        roff = self.ref_offset or (2.54, -1.27)
        voff = self.value_offset or (2.54, 1.27)
        hidden_ref = ref0.startswith("#")
        fa = 90 if self.rot in (90, 270) else 0
        props = [f'(property "Reference" "{ref0}" (at {f(x + roff[0])} {f(y + roff[1])} {fa}) {_HIDE if hidden_ref else "(effects (font (size 1.27 1.27)) (justify left))"})',
                 f'(property "Value" "{self.value}" (at {f(x + voff[0])} {f(y + voff[1])} {fa}) {_HIDE if (self.hide_value) else "(effects (font (size 1.27 1.27)) (justify left))"})',
                 f'(property "Footprint" "{self.footprint}" (at {f(x)} {f(y)} 0) {_HIDE})',
                 f'(property "Datasheet" "{self.fields.get("Datasheet", "")}" (at {f(x)} {f(y)} 0) {_HIDE})']
        for k, v in self.fields.items():
            if k != "Datasheet":
                props.append(f'(property "{k}" "{v}" (at {f(x)} {f(y)} 0) {_HIDE})')
        numbers = sorted({n for (u, n) in self._pins if u in (0, self.unit)})
        pins = " ".join(f'(pin "{n}" (uuid "{uid(*self.key, "pin", n)}"))' for n in numbers)
        inst = " ".join(f'(path "{path}" (reference "{ref}") (unit {self.unit}))' for path, ref in self.refs.items())
        mir = f" (mirror {self.mirror})" if self.mirror else ""
        return (f'(symbol (lib_id "{self.lib_id}") (at {f(x)} {f(y)} {self.rot}){mir} (unit {self.unit}) (exclude_from_sim no) '
                f'(in_bom {"no" if hidden_ref else "yes"}) (on_board {"no" if hidden_ref else "yes"}) (dnp no) '
                f'(uuid "{uid(*self.key)}")\n    ' + "\n    ".join(props) + f"\n    {pins}\n    (instances (project \"{PROJECT}\" {inst})))")


class Sheet:
    def __init__(self, name: str, uuid: str, paths: list[str], title: str, paper: str = "A4", pwr_bases=(1, 2)):
        self.name, self.uuid, self.paths, self.title, self.paper = name, uuid, paths, title, paper
        self.pwr_bases = pwr_bases
        self.libsyms: dict[str, str] = {}
        self.parts: list[Part] = []
        self.items: list[str] = []
        self._pwr = 0
        self.connections: list[tuple[str, str, str]] = []  # (ref0, pin, net) intent, for the check

    def need(self, lib: str, name: str) -> None:
        lib_id = f"{lib}:{name}"
        if lib_id not in self.libsyms:
            self.libsyms[lib_id] = kilib.flat_symbol(lib, name)

    def part(self, *a, **k) -> Part:
        p = Part(self, *a, **k)
        self.parts.append(p)
        return p

    # --- drawing primitives -------------------------------------------------------------------
    def wire(self, *pts) -> None:
        for a, b in zip(pts, pts[1:]):
            self.items.append(f'(wire (pts (xy {f(a[0])} {f(a[1])}) (xy {f(b[0])} {f(b[1])})) (stroke (width 0) (type default)) '
                              f'(uuid "{uid(self.name, "wire", a, b)}"))')

    def junction(self, p) -> None:
        self.items.append(f'(junction (at {f(p[0])} {f(p[1])}) (diameter 0) (color 0 0 0 0) (uuid "{uid(self.name, "junction", p)}"))')

    def noconnect(self, p) -> None:
        self.items.append(f'(no_connect (at {f(p[0])} {f(p[1])}) (uuid "{uid(self.name, "nc", p)}"))')

    def label(self, text: str, p, direction=(1, 0), kind="label", shape="passive") -> None:
        angle = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}[tuple(direction)]
        just = "left" if angle in (0, 90) else "right"
        if kind == "label":
            self.items.append(f'(label "{text}" (at {f(p[0])} {f(p[1])} {angle}) (effects (font (size 1.27 1.27)) (justify {just} bottom)) '
                              f'(uuid "{uid(self.name, "label", text, p)}"))')
        else:
            self.items.append(f'(hierarchical_label "{text}" (shape {shape}) (at {f(p[0])} {f(p[1])} {angle}) '
                              f'(effects (font (size 1.27 1.27)) (justify {just})) (uuid "{uid(self.name, "hlabel", text, p)}"))')

    def power(self, net: str, p, direction) -> None:
        """A power symbol whose pin is at p, its graphic pointing along direction (sheet frame)."""
        name = net
        self.need("power", name)
        d = tuple(direction)
        if name in POWER_DOWN:
            rot = {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}[d]
        else:
            rot = {(0, -1): 0, (-1, 0): 90, (0, 1): 180, (1, 0): 270}[d]
        self._pwr += 1
        n = self._pwr
        refs = {path: f"#{'FLG' if name == 'PWR_FLAG' else 'PWR'}{self.pwr_bases[i]}{n:02d}" for i, path in enumerate(self.paths)}
        part = Part(self, "power", name, refs, name if name != "PWR_FLAG" else "PWR_FLAG", p, rot=rot, unit=1)
        part.key = (self.name, "pwr", name, p)
        self.parts.append(part)

    def text(self, s: str, p, size=1.27, bold=False) -> None:
        b = " (bold yes)" if bold else ""
        self.items.append(f'(text "{s}" (exclude_from_sim no) (at {f(p[0])} {f(p[1])} 0) (effects (font (size {size} {size}){b}) (justify left bottom)) '
                          f'(uuid "{uid(self.name, "text", s, p)}"))')

    def box(self, x0, y0, x1, y1, title: str) -> None:
        self.items.append(f'(rectangle (start {f(x0)} {f(y0)}) (end {f(x1)} {f(y1)}) (stroke (width 0.254) (type dash) (color 72 72 72 1)) (fill (type none)) '
                          f'(uuid "{uid(self.name, "box", title)}"))')
        self.text(title, (x0 + 1.27, y0 + 3.81), size=1.778, bold=True)

    # --- connections --------------------------------------------------------------------------
    def connect(self, pin: Pin, net: str, stub: float = 2.54, label_dir=None) -> tuple[float, float]:
        """Stub out of the pin, then: power symbol, no-connect, hierarchical label (^NAME) or local label."""
        self.connections.append((next(iter(pin.part.refs.values())), pin.number, net))
        if net == "NC":
            self.noconnect(pin.at)
            return pin.at
        end = pin.end(stub)
        self.wire(pin.at, end)
        if net in POWER_NETS or net == "PWR_FLAG":
            d = pin.out
            want = (0, 1) if net in ("GND", "-12V") else (0, -1)
            if d[1] == 0:  # a horizontal stub turns toward the symbol's natural side
                turn = (end[0], round(end[1] + want[1] * 2.54, 4))
                self.wire(end, turn)
                end, d = turn, want
            self.power(net, end, d)
        elif net.startswith("^"):
            self.label(net[1:], end, label_dir or pin.out, kind="hier", shape=net_shape.get(net[1:], "passive"))
        else:
            self.label(net, end, label_dir or pin.out)
        return end

    def sexpr(self) -> str:
        libs = "\n  ".join(self.libsyms.values())
        body = "\n  ".join([p.sexpr() for p in self.parts] + self.items)
        return (f'(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0") (uuid "{self.uuid}") (paper "{self.paper}")\n'
                f'  (title_block (title "{self.title}") (rev "A") (company "text-to-cad demo"))\n'
                f'  (lib_symbols\n  {libs}\n  )\n  {body}\n  @@SHEETS@@\n  (embedded_fonts no)\n)\n')


net_shape: dict[str, str] = {}
