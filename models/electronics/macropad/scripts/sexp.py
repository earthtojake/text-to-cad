"""A small S-expression reader and writer for KiCad's files (symbols, footprints): enough to copy a
library symbol into a schematic's lib_symbols and to read its pins."""
from __future__ import annotations

import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


class Sym(str):
    """A bare atom (not a quoted string)."""


def parse(text: str):
    stack, out = [], []
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError(f"bad token at {pos}: {text[pos:pos+40]!r}")
        pos = m.end()
        if m.group(1):
            stack.append(out)
            out = []
        elif m.group(2):
            done = out
            out = stack.pop()
            out.append(done)
        elif m.group(3) is not None:
            out.append(m.group(3).replace('\\"', '"').replace("\\\\", "\\"))
        else:
            out.append(Sym(m.group(4)))
    return out


def dump(node, indent=0) -> str:
    pad = "\t" * indent
    if isinstance(node, list):
        if not node:
            return "()"
        simple = all(not isinstance(x, list) for x in node)
        if simple:
            return "(" + " ".join(dump(x) for x in node) + ")"
        head = []
        rest = node
        while rest and not isinstance(rest[0], list):
            head.append(dump(rest[0]))
            rest = rest[1:]
        inner = "\n".join(pad + "\t" + dump(x, indent + 1) for x in rest)
        return "(" + " ".join(head) + "\n" + inner + "\n" + pad + ")"
    if isinstance(node, Sym):
        return str(node)
    if isinstance(node, (int, float)):
        return fmt(node)
    s = str(node).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def fmt(v: float) -> str:
    if isinstance(v, int):
        return str(v)
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def find(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def first(node, key):
    got = find(node, key)
    return got[0] if got else None
