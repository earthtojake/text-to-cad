"""What KiCad and the review find, each finding as one plain sentence naming what it is about.

KiCad's messages name the rule ("Clearance violation (netclass 'Default' clearance 0.2000 mm;
actual 0.1500 mm)") and list the items apart. A person reviewing a board, and an agent fixing
it, read one sentence: the things, then what is wrong with them. A type this table does not
know, or a message it cannot read the numbers from, reads as KiCad wrote it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

__all__ = ["Finding", "FindingItem", "kind_title", "name_item", "summarize"]


@dataclass(frozen=True)
class FindingItem:
    """What a finding is about: KiCad's words for it, a board reference to it when it has one
    (a pad, a part, or copper at a point), and where it is."""

    text: str
    ref: str | None = None
    at: tuple[float, float] | None = None


@dataclass(frozen=True)
class Finding:
    """One thing KiCad or the review reported, positions in the frame of whoever read it."""

    check: str  # "erc", "drc", "parity", "unconnected" or "review"
    severity: str  # "error" or "warning"
    type: str  # KiCad's own key, e.g. "clearance", "pin_not_connected"
    description: str
    items: tuple[FindingItem, ...] = ()
    summary: str = ""  # one plain sentence (:func:`summarize`); KiCad's own words when empty

    def render(self) -> str:
        where = "; ".join(
            item.text + (f" at ({item.at[0]:g}, {item.at[1]:g})" if item.at is not None else "") for item in self.items
        )
        return f"{self.severity} [{self.check} {self.type}] {self.summary or self.description}" + (f": {where}" if where else "")

    def as_json(self) -> dict:
        """The finding as ``cadgen pcb validate --json`` and a build's report write it."""
        return {
            "check": self.check,
            "severity": self.severity,
            "type": self.type,
            "description": self.description,
            "summary": self.summary or self.description,
            "items": [
                {"description": item.text, "position": list(item.at) if item.at is not None else None}
                for item in self.items
            ],
        }


_EDGE = "the board edge"

_ITEMS: tuple[tuple[re.Pattern, Callable[[re.Match], str]], ...] = (
    (re.compile(r"^.+ on Edge\.Cuts"), lambda m: _EDGE),
    (re.compile(r"^NPTH pad(?: \[[^\]]*\])? of (\S+)"), lambda m: f"a {m[1]} mounting hole"),
    (re.compile(r"^(?:(?:PTH|SMD) )?[Pp]ad (\S+)(?: \[([^\]]*)\])? of (\S+)"),
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
    if not actual:
        return None
    required = list(_MM.finditer(description[: actual.start()]))  # the one nearest "; actual", not a number in a rule name
    if not required:
        return None
    return _mm(required[-1][1]), _mm(actual[1])


def _two(names: Sequence[str]) -> str | None:
    return f"{names[0]} and {names[1]}" if len(names) >= 2 else None


def _off_edge(names: Sequence[str]) -> str | None:
    """The first item that is not the board edge itself."""
    return next((name for name in names if name != _EDGE), None)


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


# type -> (names, limits) -> sentence or None (None: KiCad's own words)
_SENTENCES: dict[str, Callable[[list[str], tuple[str, str] | None], str | None]] = {
    "clearance": lambda n, l: l and _two(n) and f"{_cap(_two(n))} are {l[1]} apart; the rules need {l[0]}",
    "hole_clearance": lambda n, l: l and n and f"{_cap(n[0])} is {l[1]} from a hole; the rules need {l[0]}",
    "copper_edge_clearance": lambda n, l: l and _off_edge(n) and f"{_cap(_off_edge(n))} is {l[1]} from the board edge; the rules need {l[0]}",
    "track_width": lambda n, l: l and n and f"{_cap(n[0])} is {l[1]} wide; the rules need at least {l[0]}",
    "annular_width": lambda n, l: l and n and f"{_cap(n[0])} has a {l[1]} ring of copper round its hole; the rules need at least {l[0]}",
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
}


# The review's own checks, whose descriptions are each finding's measurements.
_TITLES = {
    "decoupling_missing": "No decoupling capacitor",
    "decoupling_far": "Decoupling capacitor too far",
    "track_current": "Track too thin for its current",
}


def kind_title(type: str, description: str) -> str:
    """What every finding of a type is called, as one list heading: KiCad's message without the
    numbers it puts in brackets ("Clearance violation"), or the review check's name."""
    return _TITLES.get(type) or re.sub(r"\s*\(.*\)\s*$", "", description) or type.replace("_", " ")


def summarize(check: str, type: str, description: str, items: Sequence[str]) -> str:
    """One sentence for a finding: its items by name, then what is wrong with them."""
    names = [name_item(text) for text in items]
    if type == "pin_to_pin":  # KiCad's one message for every pin-type conflict, with the two types in it
        types = re.search(r"Pins of type (.+?) and (.+?) are connected", description)
        if types and _two(names):
            return f"{_cap(_two(names))} are connected, but their pin types ({types[1].lower()} and {types[2].lower()}) conflict"
        return description
    sentence = _SENTENCES.get(type)
    if sentence is None:
        return description
    return sentence(names, _limits(description)) or description
