"""Small helpers shared by the generator scripts: balanced S-expression blocks out of KiCad's stock
libraries, flattened symbols (``extends`` resolved), and pin geometry. Standard library only."""

from __future__ import annotations

import os
import re
from pathlib import Path

# KiCad's stock libraries, where the project's library tables find them (KICAD10_SYMBOL_DIR and
# KICAD10_FOOTPRINT_DIR); unset, macOS's KiCad.app.
KICAD = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport")
SYMBOLS = Path(os.environ.get("KICAD10_SYMBOL_DIR") or KICAD / "symbols")
FOOTPRINTS = Path(os.environ.get("KICAD10_FOOTPRINT_DIR") or KICAD / "footprints")


def block_at(text: str, start: int) -> str:
    """The balanced S-expression that opens at ``text[start]``."""
    depth = 0
    in_str = False
    i = start
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise ValueError("unbalanced")


def children(block: str, head: str) -> list[str]:
    """Every direct child block of ``block`` whose head is ``head`` (e.g. 'property')."""
    out = []
    depth = 0
    in_str = False
    i = 0
    while i < len(block):
        c = block[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
            if depth == 2 and block.startswith("(" + head, i) and block[i + 1 + len(head)] in " \n\t)":
                b = block_at(block, i)
                out.append(b)
                i += len(b)
                depth -= 1
                continue
        elif c == ")":
            depth -= 1
        i += 1
    return out


_cache: dict[str, str] = {}


def _lib(lib: str) -> str:
    if lib not in _cache:
        _cache[lib] = (SYMBOLS / f"{lib}.kicad_sym").read_text(encoding="utf-8")
    return _cache[lib]


def raw_symbol(lib: str, name: str) -> str:
    text = _lib(lib)
    m = re.search(r'\n\t\(symbol "' + re.escape(name) + r'"\n', text)
    if not m:
        raise KeyError(f"{lib}:{name}")
    return block_at(text, m.start() + 2)


def flat_symbol(lib: str, name: str) -> str:
    """The symbol's block with ``extends`` resolved (the parent's units, the child's properties),
    named ``lib:name`` as a schematic's ``lib_symbols`` holds it."""
    sym = raw_symbol(lib, name)
    m = re.search(r'\(extends "([^"]+)"\)', sym)
    if m:
        parent = flat_symbol(lib, m.group(1))
        pname = m.group(1)
        body = parent
        # the child's properties override the parent's of the same name; the parent's others stay
        mine = {re.match(r'\(property "([^"]+)"', p).group(1): p for p in children(sym, "property")}
        for prop in children(body, "property"):
            pname_ = re.match(r"\(property \"([^\"]+)\"", prop).group(1)
            if pname_ in mine:
                body = body.replace(prop, mine.pop(pname_), 1)
        if mine:
            head_end = body.index("\n")
            body = body[:head_end] + "".join("\n\t\t" + p for p in mine.values()) + body[head_end:]
        body = body.replace(f'(symbol "{lib}:{pname}"', f'(symbol "{name}"', 1)
        body = re.sub(r'\(symbol "' + re.escape(pname) + r'_(\d+)_(\d+)"', lambda mm: f'(symbol "{name}_{mm.group(1)}_{mm.group(2)}"', body)
        sym = body
    sym = sym.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)
    return sym


def pins(flat: str) -> dict[tuple[int, str], tuple[float, float, int, str]]:
    """(unit, number) -> (x, y, angle, electrical type), the library's frame (y up). Unit 0 = all units."""
    out = {}
    for unit_block in re.finditer(r'\(symbol "[^"]+_(\d+)_(\d+)"', flat):
        unit = int(unit_block.group(1))
        b = block_at(flat, unit_block.start())
        for p in children(b, "pin"):
            mt = re.match(r'\(pin (\w+) \w+\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)', p)
            num = re.search(r'\(number "([^"]*)"', p).group(1)
            out[(unit, num)] = (float(mt.group(2)), float(mt.group(3)), int(float(mt.group(4))), mt.group(1))
    return out
