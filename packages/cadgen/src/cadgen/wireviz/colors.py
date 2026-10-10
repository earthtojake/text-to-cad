"""Wire colours in WireViz's words: two-letter codes, and the standard colour sequences.

A colour is one code (``RD``) or several run together for a striped wire
(``WHGN``: white with a green stripe). The codes are IEC 60757's, plus the few
WireViz adds for bare and plated conductors. A colour code names a standard
sequence a multi-core cable's wires follow (DIN 47100, the IEC 60062 order, a
telephone 25-pair cable, Ethernet's T568A/B), and a cable with more wires than
its sequence starts the sequence again, as WireViz does.

These are the standards' sequences, written out here; nothing is read from
WireViz, which cadgen never imports.
"""

from __future__ import annotations

__all__ = ["COLOR_CODES", "COLOR_NAMES", "split_colors"]

#: Every two-letter code, with the colour it names.
COLOR_NAMES: dict[str, str] = {
    "BK": "black",
    "WH": "white",
    "GY": "grey",
    "PK": "pink",
    "RD": "red",
    "OG": "orange",
    "YE": "yellow",
    "OL": "olive green",
    "GN": "green",
    "TQ": "turquoise",
    "LB": "light blue",
    "BU": "blue",
    "VT": "violet",
    "BN": "brown",
    "BG": "beige",
    "IV": "ivory",
    "SL": "slate",
    "CU": "copper (bare)",
    "SN": "tin (tinned bare)",
    "SR": "silver",
    "GD": "gold",
}

_TEL_MAJOR = ("WH", "RD", "BK", "YE", "VT")
_TEL_MINOR = ("BU", "OG", "GN", "BN", "SL")

#: The standard sequences a cable's ``color_code=`` names.
COLOR_CODES: dict[str, tuple[str, ...]] = {
    # DIN 47100: the first ten single colours, then pairs, then triples.
    "DIN": (
        "WH", "BN", "GN", "YE", "GY", "PK", "BU", "RD", "BK", "VT", "GYPK", "RDBU",
        "WHGN", "BNGN", "WHYE", "YEBN", "WHGY", "GYBN", "WHPK", "PKBN", "WHBU", "BNBU",
        "WHRD", "BNRD", "WHBK", "BNBK", "GYGN", "YEGY", "PKGN", "YEPK", "GNBU", "YEBU",
        "GNRD", "YERD", "GNBK", "YEBK", "GYBU", "PKBU", "GYRD", "PKRD", "GYBK", "PKBK",
        "BUBK", "RDBK", "WHBNBK", "YEGNBK", "GYPKBK", "RDBUBK", "WHGNBK", "BNGNBK",
        "WHYEBK", "YEBNBK", "WHGYBK", "GYBNBK", "WHPKBK", "PKBNBK", "WHBUBK",
        "BNBUBK", "WHRDBK", "BNRDBK",
    ),
    # IEC 60062's digit order, 1 to 0.
    "IEC": ("BN", "RD", "OG", "YE", "GN", "BU", "VT", "GY", "WH", "BK"),
    "BW": ("BK", "WH"),
    # The 25-pair telephone code: each pair's ring (minor/major) then tip (major/minor)...
    "TEL": tuple(
        code
        for major in _TEL_MAJOR
        for minor in _TEL_MINOR
        for code in (minor + major, major + minor)
    ),
    # ...and the alternative: tip then ring, the first five tips' ring a plain colour.
    "TELALT": tuple(
        code
        for major in _TEL_MAJOR
        for minor in _TEL_MINOR
        for code in ((major + minor, minor) if major == "WH" else (major + minor, minor + major))
    ),
    "T568A": ("WHGN", "GN", "WHOG", "BU", "WHBU", "OG", "WHBN", "BN"),
    "T568B": ("WHOG", "OG", "WHGN", "BU", "WHBU", "GN", "WHBN", "BN"),
}


def split_colors(text: str) -> list[str] | None:
    """``"WHGN"`` -> ``["WH", "GN"]``; ``None`` when any part is not a code."""
    if not isinstance(text, str) or not text or len(text) % 2:
        return None
    parts = [text[index : index + 2] for index in range(0, len(text), 2)]
    return parts if all(part in COLOR_NAMES for part in parts) else None
