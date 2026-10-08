"""A KiCad finding as one plain sentence naming what it is about.

KiCad's messages name the rule ("Clearance violation (netclass 'Default' clearance 0.2000 mm;
actual 0.1500 mm)") and list the items apart. A person reviewing a board, and an agent fixing
it, read one sentence: the things, then what is wrong with them. A type this table does not
know, or a message it cannot read the numbers from, reads as KiCad wrote it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

_ITEMS: tuple[tuple[re.Pattern, Callable[[re.Match], str]], ...] = (
    (re.compile(r"^Pad (\S+)(?: \[([^\]]*)\])? of (\S+)"),
     lambda m: f"{m[3]} pad {m[1]}" + (f" ({m[2]})" if m[2] and m[2] != m[1] else "")),
    (re.compile(r"^Symbol (\S+) Pin (\S+) \[([^,\]]*)"),
     lambda m: f"{m[1]} pin {m[2]}" + (f" ({m[3]})" if m[3] and m[3] != m[2] else "")),
    (re.compile(r"^(?:Track|Arc) \[([^\]]*)\]"), lambda m: f"the {m[1]} track"),
    (re.compile(r"^Via \[([^\]]*)\]"), lambda m: f"a {m[1]} via"),
    (re.compile(r"^Zone \[([^\]]*)\]"), lambda m: f"the {m[1]} pour"),
    (re.compile(r"^(?:Global |Hierarchical )?Label '([^']*)'"), lambda m: f"label {m[1]}"),
    (re.compile(r"^(?:Footprint|Symbol) (\S+)"), lambda m: m[1]),
)

_MM = re.compile(r"(\d+(?:\.\d+)?) mm")
_ACTUAL = re.compile(r"actual (\d+(?:\.\d+)?) mm")


def name_item(text: str) -> str:
    """A finding's item as a person names it: ``U2 pad 7 (VDD)``, ``the SDA track``."""
    for pattern, name in _ITEMS:
        match = pattern.match(text)
        if match:
            return name(match)
    return text


def _mm(value: str) -> str:
    return f"{round(float(value), 3):g} mm"


def _limits(description: str) -> tuple[str, str] | None:
    """(required, actual) from a message like "... clearance 0.2000 mm; actual 0.1500 mm)"."""
    actual = _ACTUAL.search(description)
    required = _MM.search(description)
    if not actual or not required or required.start() >= actual.start():
        return None
    return _mm(required[1]), _mm(actual[1])


def _two(names: Sequence[str]) -> str | None:
    return f"{names[0]} and {names[1]}" if len(names) >= 2 else None


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


# type -> (names, limits) -> sentence or None (None: KiCad's own words)
_SENTENCES: dict[str, Callable[[list[str], tuple[str, str] | None], str | None]] = {
    "clearance": lambda n, l: l and _two(n) and f"{_cap(_two(n))} are {l[1]} apart; the rules need {l[0]}",
    "hole_clearance": lambda n, l: l and n and f"{_cap(n[0])} is {l[1]} from a hole; the rules need {l[0]}",
    "copper_edge_clearance": lambda n, l: l and n and f"{_cap(n[0])} is {l[1]} from the board edge; the rules need {l[0]}",
    "track_width": lambda n, l: l and n and f"{_cap(n[0])} is {l[1]} wide; the rules need {l[0]}",
    "annular_width": lambda n, l: l and n and f"{_cap(n[0])} has a {l[1]} ring of copper round its hole; the rules need {l[0]}",
    "courtyards_overlap": lambda n, l: _two(n) and f"{_cap(_two(n))} overlap",
    "shorting_items": lambda n, l: _two(n) and f"{_cap(_two(n))} short two nets together",
    "unconnected_items": lambda n, l: _two(n) and f"{_cap(_two(n))} still need a track",
    "starved_thermal": lambda n, l: n and f"{_cap(n[0])} reaches its pour through too few thermal spokes",
    "solder_mask_bridge": lambda n, l: _two(n) and f"{_cap(_two(n))} are too close for the solder mask between them",
    "silk_over_copper": lambda n, l: n and f"Silkscreen of {n[0]} prints on bare copper",
    "via_dangling": lambda n, l: n and f"{_cap(n[0])} connects to nothing",
    "track_dangling": lambda n, l: n and f"{_cap(n[0])} has an end that connects to nothing",
    "pin_not_connected": lambda n, l: n and f"{_cap(n[0])} isn't connected to anything",
    "power_pin_not_driven": lambda n, l: n and f"{_cap(n[0])} is a power input that nothing powers",
    "label_dangling": lambda n, l: n and f"{_cap(n[0])} connects to nothing",
    "pin_to_pin": lambda n, l: _two(n) and f"{_cap(_two(n))} are connected but shouldn't be (two outputs, or an output and power)",
}


def summarize(check: str, type: str, description: str, items: Sequence[str]) -> str:
    """One sentence for a finding: its items by name, then what is wrong with them."""
    sentence = _SENTENCES.get(type)
    if sentence is None:
        return description
    return sentence([name_item(text) for text in items], _limits(description)) or description
