"""Natural-order catalog sort matching JS ``localeCompare(numeric, base)``.

cadDirectoryScanner.compareEntries sorts catalog entries by ``file`` with
``localeCompare(a, b, undefined, {numeric: true, sensitivity: "base"})`` — V8's
ICU root collation. Python's default sort is codepoint-ordered and
case-sensitive, so a naive ``sorted(..., key=file)`` reorders the sidebar/tree.

Rather than depend on PyICU, we reproduce the rule empirically derived from V8
output for the realistic filename charset (alphanumerics + ``_ - . + ~ space``):

- Primary ordering is **punctuation < digits < letters** (verified: ``["0","9","a","z"]``
  and ``["a ","a_","a.","a1"]``).
- Punctuation orders ``space < _ < - < . < + < ~`` (others fall back after these,
  by codepoint).
- Digit runs compare as integers (``v2.9 < v2.10 < v10.1``).
- Letters are case-/diacritic-insensitive (casefold); ties keep input order
  (Python's stable sort, matching V8's stable sort + ``sensitivity:"base"``).

Each character becomes an element tuple ``(class, ordinal, text)`` where class is
0=punct, 1=digit-run, 2=letter, so list comparison yields the V8 order. Exotic
punctuation outside the known set may still diverge — that residue is documented
and only affects tree ordering, never content.
"""

from __future__ import annotations

# space < _ < - < . < + < ~  (empirically from V8 localeCompare)
_PUNCT_ORDER = {" ": 0, "_": 1, "-": 2, ".": 3, "+": 4, "~": 5}
_DIGITS = "0123456789"


def natural_key(value: str):
    text = str(value or "")
    key = []
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if ch in _DIGITS:
            j = i
            while j < length and text[j] in _DIGITS:
                j += 1
            key.append((1, int(text[i:j]), ""))
            i = j
        elif ch.isalpha():
            key.append((2, 0, ch.casefold()))
            i += 1
        else:
            key.append((0, _PUNCT_ORDER.get(ch, 6 + ord(ch)), ""))
            i += 1
    return key


def sort_catalog_entries(entries):
    """Stable sort a list of catalog-entry dicts by their ``file`` field."""
    return sorted(entries, key=lambda entry: natural_key(entry.get("file", "")))
