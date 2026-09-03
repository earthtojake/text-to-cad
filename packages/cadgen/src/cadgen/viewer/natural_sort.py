"""Catalog order: a reproduction of

    localeCompare(a, b, undefined, {numeric: true, sensitivity: "base"})

which is V8's ICU ROOT COLLATION at PRIMARY strength with numeric ordering. It
is not a natural sort and it is not codepoint order: punctuation sorts before
digits before letters, case and accents fold to equality, ``ss``/``ae``/``oe``/
``dz``/``fi``/``xii``/fullwidth all expand, digit runs compare as arbitrary-
precision integers, and leading zeros are invisible.

None of that is typed here. ``collation.json`` beside this module is DERIVED by
running the real collator over the whole Unicode repertoire
(``tests_server/golden/gen_golden.mjs``), and this file is a table walker:

* ``ignorableRanges``  codepoints with no primary weight, found by asking the
  collator whether ``"m" + ch + "m"`` compares equal to ``"mm"``. This is NOT the
  ``Cc`` category — U+0000-0008 and U+00AD are ignorable while TAB, LF, VT, FF,
  CR and U+0085 are not.
* ``expansions``       codepoint -> the atom string it collates equal to,
  already driven to a FIXED POINT so the walker never guesses. Every value was
  verified against the collator; NFKD alone is wrong (U+00B2 decomposes to "2"
  but does not collate equal to it).
* ``contractions``     the mirror image: a SEQUENCE that collates as one unit
  with its own primary weight. An L1-ignorable is ignorable on its own yet can
  carry weight after some bases — ICU contracts ARABIC ALEF + HAMZA ABOVE into
  the weight of ALEF WITH HAMZA ABOVE, which is not alef's. Measured:
  ``cmp("m<U+0654>m", "mm") == 0`` but ``cmp("m<U+0623>m", "m<U+0627>m") == -1``.
* ``bucketRuns``       run-length-encoded primary-weight buckets over the atoms.

THE ORDERING TRAP THIS FILE EXISTS TO GET RIGHT
-----------------------------------------------
An L1-ignorable is ignorable for WEIGHTING but it TERMINATES A NUMERIC RUN.
Measured against V8:

    cmp("1<U+00AD>2", "12")  == -1        (not 0)
    cmp("11", "1<U+00AD>1")  == +1
    cmp("ab", "a<U+00AD>b")  ==  0        (letters are unaffected)

So digit runs are segmented on the sequence WITH ignorables still present, and
only then are the ignorables dropped. Dropping them first — the obvious
ordering — makes "1<SHY>2" and "12" compare equal and silently misfiles every
name with an invisible character between two digits.

RESIDUE
-------
None known. ``tests_server/test_parity.py`` sorts a generated adversarial corpus
— realistic CAD names, every ignorable-between-digits case, the whole Arabic
presentation-forms block, and 2000 random codepoints across all planes — and
asserts the order matches V8 exactly, plus a full 160,000-pair sign matrix. If a
future Unicode/ICU version introduces a divergence, that test is where it
surfaces; record it here rather than loosening the assertion.
"""

from __future__ import annotations

import bisect
import json
import threading
import unicodedata
from pathlib import Path

__all__ = ["collation_key", "sort_catalog_entries", "COLLATION_PATH"]

COLLATION_PATH = Path(__file__).resolve().parent / "collation.json"

_LOCK = threading.Lock()
_TABLE: "_CollationTable | None" = None


class _CollationTable:
    __slots__ = (
        "ignorable_starts",
        "ignorable_ends",
        "expansions",
        "contractions",
        "max_contraction_length",
        "run_starts",
        "run_buckets",
        "run_lengths",
        "zero_bucket",
        "max_bucket",
        "char_bucket",
    )

    # -1 means "L1-ignorable". A plain dict is enough for thread safety here:
    # every entry is derived purely from its key, so a racing insert can only
    # ever write the same value twice.
    IGNORABLE = -1
    CACHE_LIMIT = 1 << 16

    def __init__(self, payload: dict) -> None:
        ranges = payload["ignorableRanges"]
        self.ignorable_starts = [lo for lo, _ in ranges]
        self.ignorable_ends = [hi for _, hi in ranges]
        self.expansions = {chr(int(cp)): value for cp, value in payload["expansions"].items()}
        self.contractions = dict(payload["contractions"])
        self.max_contraction_length = payload["maxContractionLength"]
        runs = payload["bucketRuns"]
        self.run_starts = [start for start, _, _ in runs]
        self.run_buckets = [bucket for _, bucket, _ in runs]
        self.run_lengths = [length for _, _, length in runs]
        self.zero_bucket = payload["zeroBucket"]
        last = len(runs) - 1
        self.max_bucket = self.run_buckets[last] + self.run_lengths[last]
        # Two bisects per character is the whole cost of the key function, and
        # the catalog is re-sorted on every status poll. Memoise the answer;
        # real filenames reuse a few dozen characters.
        self.char_bucket: dict[str, int] = {}

    def classify(self, char: str) -> int:
        """Bucket for ``char``, or ``IGNORABLE``."""
        cached = self.char_bucket.get(char)
        if cached is not None:
            return cached
        codepoint = ord(char)
        value = self.IGNORABLE if self.is_ignorable(codepoint) else self.bucket(codepoint)
        if len(self.char_bucket) >= self.CACHE_LIMIT:
            self.char_bucket.clear()
        self.char_bucket[char] = value
        return value

    def is_ignorable(self, codepoint: int) -> bool:
        index = bisect.bisect_right(self.ignorable_starts, codepoint) - 1
        return index >= 0 and codepoint <= self.ignorable_ends[index]

    def bucket(self, codepoint: int) -> int:
        index = bisect.bisect_right(self.run_starts, codepoint) - 1
        if index >= 0:
            start = self.run_starts[index]
            offset = codepoint - start
            if offset < self.run_lengths[index]:
                return self.run_buckets[index] + offset
        # Unknown to the table: a codepoint assigned after the fixture was
        # generated. Sort it deterministically past everything known rather
        # than raising, and let the parity test catch the version skew.
        return self.max_bucket + 1 + codepoint


def _table() -> _CollationTable:
    global _TABLE
    with _LOCK:
        if _TABLE is None:
            _TABLE = _CollationTable(json.loads(COLLATION_PATH.read_text(encoding="utf-8")))
        return _TABLE


def collation_key(value: str) -> list[tuple[int, int]]:
    """A sort key whose lexicographic order reproduces the collator's sign.

    Equal-comparing strings produce EQUAL keys, which matters as much as the
    order: the catalog sort is stable and ``sensitivity: "base"`` produces a lot
    of ties, so tied entries must keep their directory-walk order.
    """
    table = _table()
    atoms: list[str] = []
    for char in unicodedata.normalize("NFD", str(value or "")):
        expansion = table.expansions.get(char)
        if expansion is None:
            atoms.append(char)
        else:
            atoms.extend(expansion)

    zero = table.zero_bucket
    nine = zero + 9
    contractions = table.contractions
    longest = table.max_contraction_length
    classify = table.classify
    ignorable_marker = table.IGNORABLE
    tokens: list[tuple[int, int]] = []
    index = 0
    count = len(atoms)
    while index < count:
        # A contraction outranks everything: its constituents include
        # characters that are individually ignorable but are NOT here. Longest
        # match wins, so base+two-marks beats base+one-mark.
        if longest > 1:
            matched = False
            for length in range(min(longest, count - index), 1, -1):
                bucket = contractions.get("".join(atoms[index : index + length]))
                if bucket is not None:
                    tokens.append((bucket, -1))
                    index += length
                    matched = True
                    break
            if matched:
                continue

        bucket = classify(atoms[index])
        if bucket == ignorable_marker:
            # Contributes no weight, but stepping over it here is exactly what
            # ends a digit run — see the module docstring.
            index += 1
            continue
        if zero <= bucket <= nine:
            # ICU orders decimal digits numerically regardless of script and
            # mixes scripts freely inside one run, so the value accumulates
            # across whatever digit atoms are adjacent.
            number = 0
            while index < count:
                digit_bucket = classify(atoms[index])
                if not zero <= digit_bucket <= nine:
                    break
                number = number * 10 + (digit_bucket - zero)
                index += 1
            tokens.append((zero, number))
        else:
            tokens.append((bucket, -1))
            index += 1
    return tokens


def sort_catalog_entries(entries):
    """``[...entries].sort((a, b) => localeCompare(a.file, b.file, ...))``.

    Non-mutating, and the key coerces the same way the JS does: a missing,
    ``None`` or empty ``file`` all key as ``""``.
    """
    return sorted(entries, key=lambda entry: collation_key(_file_key(entry)))


def _file_key(entry) -> str:
    value = entry.get("file") if isinstance(entry, dict) else getattr(entry, "file", None)
    # JS `String(a.file || "")`: 0, "", None and a missing key all become "".
    if not value:
        return ""
    return str(value)
